"""Reconcile public issues with their private mirrors.

Intended to run on a schedule (e.g. daily cron) to catch any events
that were missed due to runner failures or transient errors.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from github import Github
from github.Repository import Repository

from lyrebird.config import Config
from lyrebird.handlers._set_issue_type import set_issue_type
from lyrebird.mapping import (
    build_mapping_comment,
    build_mirrored_comment_body,
    build_private_issue_body,
    build_private_issue_title,
    build_tombstone_comment_body,
    parse_private_body_markers,
    parse_public_comment_id,
    resolve_mapping,
    update_private_body_public_section,
)

logger = logging.getLogger(__name__)


@dataclass
class SyncStats:
    """Counters for a sync run."""

    scanned: int = 0
    created: int = 0
    state_updated: int = 0
    titles_updated: int = 0
    bodies_updated: int = 0
    comments_mirrored: int = 0
    comments_updated: int = 0
    comments_tombstoned: int = 0
    labels_synced: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Scanned: {self.scanned} public issues",
            f"Created: {self.created} private mirrors",
            f"State updated: {self.state_updated}",
            f"Titles updated: {self.titles_updated}",
            f"Bodies updated: {self.bodies_updated}",
            f"Comments mirrored: {self.comments_mirrored}",
            f"Comments updated: {self.comments_updated}",
            f"Comments tombstoned: {self.comments_tombstoned}",
            f"Labels synced: {self.labels_synced}",
            f"Errors: {len(self.errors)}",
        ]
        if self.errors:
            lines.append("")
            for err in self.errors:
                lines.append(f"  - {err}")
        return "\n".join(lines)


def sync(
    client: Github,
    config: Config,
    since_hours: int | None = 25,
) -> SyncStats:
    """Sync public issues to their private mirrors.

    Two passes:
    1. Iterate recently-updated public issues to ensure private mirrors
       are up to date (creates missing mirrors, syncs state/title/body/
       labels/comments).
    2. Iterate recently-updated private issues to catch missed
       private-to-public state cascades (e.g. human closed private but
       the workflow that should have closed public failed).

    Args:
        since_hours: Only check issues updated in the last N hours.
                     None means scan all issues.
    """
    stats = SyncStats()

    pub_repo = client.get_repo(config.public_repo)
    priv_repo = client.get_repo(config.private_repo)

    since_dt = None
    if since_hours is not None:
        since_dt = datetime.now(timezone.utc) - timedelta(hours=since_hours)

    kwargs: dict = {"state": "all", "sort": "updated", "direction": "desc"}
    if since_dt is not None:
        kwargs["since"] = since_dt

    # Pass 1: Public issues
    seen_private: set[int] = set()

    for pub_issue in pub_repo.get_issues(**kwargs):
        if pub_issue.pull_request is not None:
            continue

        stats.scanned += 1
        try:
            priv_num = _sync_issue(
                client, config, pub_repo, priv_repo, pub_issue, stats
            )
            if priv_num is not None:
                seen_private.add(priv_num)
        except Exception as exc:
            msg = f"public #{pub_issue.number}: {exc}"
            logger.error("Sync error: %s", msg)
            stats.errors.append(msg)

    # Pass 2: Private issues — catch missed private-to-public state cascades.
    # A human may have closed/reopened a private issue but the workflow that
    # should have cascaded the state change to public failed.  If the public
    # issue wasn't updated recently it won't appear in pass 1, so we need to
    # scan private issues independently.
    priv_kwargs: dict = {"state": "all", "sort": "updated", "direction": "desc"}
    if since_dt is not None:
        priv_kwargs["since"] = since_dt

    for priv_issue in priv_repo.get_issues(**priv_kwargs):
        if priv_issue.pull_request is not None:
            continue
        if priv_issue.number in seen_private:
            continue

        try:
            _check_private_state(config, pub_repo, priv_issue, stats)
        except Exception as exc:
            msg = f"private #{priv_issue.number}: {exc}"
            logger.error("Sync error (private pass): %s", msg)
            stats.errors.append(msg)

    return stats


# ── Per-issue sync (pass 1) ─────────────────────────────────────────────────


def _sync_issue(
    client: Github,
    config: Config,
    pub_repo: Repository,
    priv_repo: Repository,
    pub_issue,
    stats: SyncStats,
) -> int | None:
    """Sync a single public issue with its private mirror.

    Returns the private issue number if found/created.
    """
    pub_dict = {
        "number": pub_issue.number,
        "node_id": pub_issue.raw_data["node_id"],
        "html_url": pub_issue.html_url,
        "title": pub_issue.title,
        "body": pub_issue.body or "",
        "user": {"login": pub_issue.user.login},
        "labels": [
            {
                "name": lbl.name,
                "color": lbl.color,
                "description": lbl.description or "",
            }
            for lbl in pub_issue.labels
        ],
    }

    mapping = resolve_mapping(client, config, pub_dict)

    if mapping is None:
        priv_issue = _create_private_mirror(
            client, config, priv_repo, pub_repo, pub_issue, pub_dict, stats
        )
        # If public issue is already closed, close the new mirror too
        if pub_issue.state == "closed":
            state_reason = pub_issue.raw_data.get("state_reason")
            priv_issue.edit(state="closed", state_reason=state_reason)
            stats.state_updated += 1
        return priv_issue.number

    priv_issue = mapping.private_issue

    # Sync state (bidirectional)
    _sync_state(config, pub_issue, priv_issue, stats)

    # Sync title
    expected_title = build_private_issue_title(pub_dict)
    if priv_issue.title != expected_title:
        priv_issue.edit(title=expected_title)
        stats.titles_updated += 1
        logger.info("Updated title for private #%d", priv_issue.number)

    # Sync body (public section only)
    new_body = update_private_body_public_section(
        priv_issue.body or "", pub_issue.body or ""
    )
    if new_body != (priv_issue.body or ""):
        priv_issue.edit(body=new_body)
        stats.bodies_updated += 1
        logger.info("Updated body for private #%d", priv_issue.number)

    # Sync labels (ensure all public labels exist on private, remove extras)
    _sync_labels(config, priv_repo, priv_issue, pub_issue, stats)

    # Sync comments (find missing or edited mirrored comments)
    _sync_comments(priv_issue, pub_issue, stats)

    return priv_issue.number


# ── State sync ───────────────────────────────────────────────────────────────


def _sync_state(
    config: Config, pub_issue, priv_issue, stats: SyncStats
) -> None:
    """Reconcile open/closed state between public and private issues."""
    if pub_issue.state == priv_issue.state:
        if pub_issue.state == "closed":
            _ensure_resolution_note(config, pub_issue, priv_issue, stats)
        return

    if _last_state_change_is_bot(config, priv_issue):
        # Public is authoritative — cascade to private
        if pub_issue.state == "closed":
            state_reason = pub_issue.raw_data.get("state_reason")
            priv_issue.edit(state="closed", state_reason=state_reason)
        else:
            priv_issue.edit(state="open")
        stats.state_updated += 1
        logger.info(
            "Synced state public->private for private #%d to %s",
            priv_issue.number,
            pub_issue.state,
        )
    else:
        # Private is authoritative — cascade to public
        _sync_state_to_public(config, pub_issue, priv_issue, stats)


def _sync_state_to_public(
    config: Config, pub_issue, priv_issue, stats: SyncStats
) -> None:
    """Push private issue state to public (missed cascade)."""
    if priv_issue.state == "closed":
        note, state_reason = _get_resolution_info(config, priv_issue)
        if note:
            pub_issue.create_comment(note)
        pub_issue.edit(
            state="closed",
            state_reason=state_reason or "completed",
        )
    else:
        pub_issue.edit(state="open")
    stats.state_updated += 1
    logger.info(
        "Synced state private->public for public %s to %s",
        pub_issue.html_url,
        priv_issue.state,
    )


def _get_resolution_info(
    config: Config,
    priv_issue,
) -> tuple[str | None, str | None]:
    """Get the resolution note and state_reason from a private issue's labels."""
    for lbl in priv_issue.get_labels():
        key = config.resolution_key_for_label(lbl.name)
        if key:
            return config.resolution_note(key), config.resolution_state_reason(key)
    return None, None


def _ensure_resolution_note(
    config: Config, pub_issue, priv_issue, stats: SyncStats
) -> None:
    """Post the resolution note if both issues are closed but the note is missing."""
    note, _ = _get_resolution_info(config, priv_issue)
    if not note:
        return

    # Check whether the note was already posted
    for comment in pub_issue.get_comments():
        if (comment.body or "").strip() == note.strip():
            return

    pub_issue.create_comment(note)
    stats.state_updated += 1
    logger.info(
        "Posted missing resolution note on public %s from private #%d",
        pub_issue.html_url,
        priv_issue.number,
    )


def _check_private_state(
    config: Config, pub_repo: Repository, priv_issue, stats: SyncStats
) -> None:
    """Check a private issue for missed private-to-public state cascade."""
    markers = parse_private_body_markers(priv_issue.body or "")
    if not markers:
        return  # Not a mirror

    pub_url, _ = markers
    pub_number = int(pub_url.rsplit("/", 1)[1])
    pub_issue = pub_repo.get_issue(pub_number)

    if pub_issue.state == priv_issue.state:
        if pub_issue.state == "closed":
            _ensure_resolution_note(config, pub_issue, priv_issue, stats)
        return

    # Only push if a human changed the private state
    if _last_state_change_is_bot(config, priv_issue):
        return

    _sync_state_to_public(config, pub_issue, priv_issue, stats)


def _last_state_change_is_bot(config: Config, issue) -> bool:
    """Return True if the last state-changing event was by the bot (or none exist).

    PyGithub returns events in chronological order, so we must iterate
    all of them to find the last closed/reopened one.  For long-lived
    issues this can be expensive, but there is no reverse-order API.
    """
    events = list(issue.get_events())
    state_events = [e for e in events if e.event in ("closed", "reopened")]
    if not state_events:
        return True

    last_event = state_events[-1]
    actor_login = last_event.actor.login if last_event.actor else None
    return actor_login == config.bot_login


# ── Creation ─────────────────────────────────────────────────────────────────


def _create_private_mirror(
    client: Github,
    config: Config,
    priv_repo: Repository,
    pub_repo: Repository,
    pub_issue,
    pub_dict: dict,
    stats: SyncStats,
):
    """Create a private issue for a public issue that has no mirror.

    Returns the newly created private issue.
    """
    title = build_private_issue_title(pub_dict)
    body = build_private_issue_body(config, pub_dict)

    # Ensure labels exist
    label_names = []
    for lbl in pub_issue.labels:
        _ensure_label(priv_repo, lbl)
        label_names.append(lbl.name)

    priv_issue = priv_repo.create_issue(
        title=title,
        body=body,
        labels=label_names,
    )
    logger.info(
        "Created private #%d for public #%d",
        priv_issue.number,
        pub_issue.number,
    )

    # Mirror issue type if present
    issue_type = pub_issue.raw_data.get("type")
    if issue_type:
        type_name = issue_type.get("name") if isinstance(issue_type, dict) else None
        if type_name:
            set_issue_type(client, priv_issue, type_name)

    # Post mapping comment on public issue
    node_id = pub_dict["node_id"]
    mapping_text = build_mapping_comment(config, node_id, priv_issue.number)
    pub_issue.create_comment(mapping_text)

    stats.created += 1
    return priv_issue


# ── Labels ───────────────────────────────────────────────────────────────────


def _sync_labels(
    config: Config, priv_repo, priv_issue, pub_issue, stats: SyncStats
) -> None:
    """Ensure public labels are on private issue; remove non-protected extras."""
    pub_label_names = {lbl.name for lbl in pub_issue.labels}
    priv_labels = list(priv_issue.get_labels())
    priv_label_names = {lbl.name for lbl in priv_labels}

    # Labels that belong to the private workflow and should not be removed
    protected = config.all_resolution_label_names() | {config.needs_resolution_label}

    # Add missing
    for lbl in pub_issue.labels:
        if lbl.name not in priv_label_names:
            _ensure_label(priv_repo, lbl)
            try:
                priv_issue.add_to_labels(lbl.name)
                stats.labels_synced += 1
                logger.info(
                    "Added label '%s' to private #%d",
                    lbl.name,
                    priv_issue.number,
                )
            except Exception:
                logger.warning(
                    "Could not add label '%s' to private #%d",
                    lbl.name,
                    priv_issue.number,
                )

    # Remove extras (but not protected private-workflow labels)
    for lbl in priv_labels:
        if lbl.name not in pub_label_names and lbl.name not in protected:
            try:
                priv_issue.remove_from_labels(lbl.name)
                stats.labels_synced += 1
                logger.info(
                    "Removed label '%s' from private #%d",
                    lbl.name,
                    priv_issue.number,
                )
            except Exception:
                logger.warning(
                    "Could not remove label '%s' from private #%d",
                    lbl.name,
                    priv_issue.number,
                )


def _ensure_label(repo, label) -> None:
    """Create label in repo if it doesn't exist. Accepts PyGithub Label objects."""
    name = label.name if hasattr(label, "name") else label["name"]
    try:
        repo.get_label(name)
    except Exception:
        try:
            color = (
                label.color
                if hasattr(label, "color")
                else label.get("color", "ededed")
            )
            desc = (
                label.description
                if hasattr(label, "description")
                else label.get("description", "")
            ) or ""
            repo.create_label(name=name, color=color, description=desc)
        except Exception:
            logger.warning("Could not create label %s", name)


# ── Comments ─────────────────────────────────────────────────────────────────


def _sync_comments(priv_issue, pub_issue, stats: SyncStats) -> None:
    """Mirror missing comments, update edited ones, tombstone deleted ones."""
    # Build map of public comments by ID (excluding mapping comments)
    pub_comments: dict[int, object] = {}
    for pc in pub_issue.get_comments():
        if "<!-- mapping:" in (pc.body or ""):
            continue
        pub_comments[pc.id] = pc

    # Build map of existing mirrored private comments by public comment ID
    mirrored: dict[int, object] = {}
    for priv_comment in priv_issue.get_comments():
        cid = parse_public_comment_id(priv_comment.body or "")
        if cid is not None:
            mirrored[cid] = priv_comment

    # Mirror new comments and update edited ones
    for pub_id, pub_comment in pub_comments.items():
        expected_body = build_mirrored_comment_body(
            author=pub_comment.user.login,
            permalink=pub_comment.html_url,
            body=pub_comment.body or "",
            public_comment_id=pub_id,
        )

        if pub_id not in mirrored:
            priv_issue.create_comment(expected_body)
            stats.comments_mirrored += 1
            logger.info(
                "Mirrored comment %d to private #%d",
                pub_id,
                priv_issue.number,
            )
        else:
            existing = mirrored[pub_id]
            if existing.body != expected_body:
                existing.edit(body=expected_body)
                stats.comments_updated += 1
                logger.info(
                    "Updated mirrored comment %d on private #%d",
                    pub_id,
                    priv_issue.number,
                )

    # Tombstone mirrored comments whose public originals no longer exist
    for pub_id, priv_comment in mirrored.items():
        if pub_id in pub_comments:
            continue
        if "deleted on public" in (priv_comment.body or ""):
            continue  # Already tombstoned
        tombstone = build_tombstone_comment_body(
            author="unknown",
            permalink=pub_issue.html_url,
            timestamp=datetime.now(timezone.utc).isoformat(),
            public_comment_id=pub_id,
        )
        priv_comment.edit(body=tombstone)
        stats.comments_tombstoned += 1
        logger.info(
            "Tombstoned orphaned mirror for comment %d on private #%d",
            pub_id,
            priv_issue.number,
        )
