"""Handle /public-close slash command: close public issue with resolution."""

from __future__ import annotations

import logging
import re

from github import Github

from lyrebird.config import Config
from lyrebird.mapping import parse_private_body_markers

logger = logging.getLogger(__name__)

SLASH_CLOSE_RE = re.compile(r"^/public-close\s+(\S+)\s*(.*)", re.DOTALL)


def handle(client: Github, config: Config, payload: dict) -> None:
    comment = payload["comment"]
    issue = payload["issue"]
    body = (comment.get("body") or "").strip()

    match = SLASH_CLOSE_RE.match(body)
    if not match:
        # Missing resolution argument
        priv_repo = client.get_repo(config.private_repo)
        priv_issue = priv_repo.get_issue(issue["number"])
        allowed = ", ".join(f"`{k}`" for k in config.resolution_labels)
        priv_issue.create_comment(
            f"Usage: `/public-close <resolution> [note]`\n\n"
            f"Allowed resolutions: {allowed}"
        )
        return

    resolution_key = match.group(1).strip()
    note = match.group(2).strip()

    # Step 1: Validate resolution
    if resolution_key not in config.resolution_labels:
        priv_repo = client.get_repo(config.private_repo)
        priv_issue = priv_repo.get_issue(issue["number"])
        allowed = ", ".join(f"`{k}`" for k in config.resolution_labels)
        priv_issue.create_comment(
            f"Unknown resolution `{resolution_key}`. "
            f"Allowed values: {allowed}"
        )
        return

    # Find mapped public issue
    issue_body = issue.get("body") or ""
    markers = parse_private_body_markers(issue_body)
    if markers is None:
        priv_repo = client.get_repo(config.private_repo)
        priv_issue = priv_repo.get_issue(issue["number"])
        priv_issue.create_comment(
            "This issue is not linked to a public issue. `/public-close` has no effect."
        )
        return

    public_url, _ = markers
    parts = public_url.rstrip("/").split("/")
    public_number = int(parts[-1])

    priv_repo = client.get_repo(config.private_repo)
    priv_issue = priv_repo.get_issue(issue["number"])

    # Step 2: Normalize resolution labels
    target_label = config.resolution_label_name(resolution_key)
    all_resolution_labels = config.all_resolution_label_names()
    current_labels = [lbl.name for lbl in priv_issue.get_labels()]

    for lbl_name in current_labels:
        if lbl_name in all_resolution_labels and lbl_name != target_label:
            try:
                priv_issue.remove_from_labels(lbl_name)
            except Exception:
                pass

    if target_label not in current_labels:
        _ensure_label(priv_repo, target_label)
        priv_issue.add_to_labels(target_label)

    # Remove needs-resolution if present
    if config.needs_resolution_label in current_labels:
        try:
            priv_issue.remove_from_labels(config.needs_resolution_label)
        except Exception:
            pass

    # Step 3: Close private issue (idempotent)
    if priv_issue.state != "closed":
        priv_issue.edit(state="closed")

    # Step 4: Post note on public issue
    pub_repo = client.get_repo(config.public_repo)
    pub_issue = pub_repo.get_issue(public_number)

    public_note = note if note else config.resolution_note(resolution_key)
    public_comment = pub_issue.create_comment(public_note)

    # Step 5: Close public issue (if not already closed)
    if pub_issue.state != "closed":
        state_reason = config.resolution_state_reason(resolution_key)
        if state_reason:
            pub_issue.edit(state="closed", state_reason=state_reason)
        else:
            pub_issue.edit(state="closed")

    # Step 6: Acknowledge in private
    priv_issue.create_comment(
        f"Closed public issue with resolution `{resolution_key}`: "
        f"{public_comment.html_url}"
    )
    logger.info(
        "/public-close %s on private #%d -> closed public #%d",
        resolution_key,
        issue["number"],
        public_number,
    )


def _ensure_label(repo, label_name: str) -> None:
    """Create label if it doesn't exist."""
    try:
        repo.get_label(label_name)
    except Exception:
        try:
            repo.create_label(name=label_name, color="e4e669")
        except Exception:
            pass
