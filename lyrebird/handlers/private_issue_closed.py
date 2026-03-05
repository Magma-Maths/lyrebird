"""Handle private issue closed: enforce resolution label, maybe close public."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.mapping import parse_private_body_markers

logger = logging.getLogger(__name__)


def handle(client: Github, config: Config, payload: dict) -> None:
    issue = payload["issue"]
    issue_body = issue.get("body") or ""

    markers = parse_private_body_markers(issue_body)
    if markers is None:
        # Not a mirrored issue, nothing to do
        return

    public_url, _ = markers
    parts = public_url.rstrip("/").split("/")
    public_number = int(parts[-1])

    priv_repo = client.get_repo(config.private_repo)
    priv_issue = priv_repo.get_issue(issue["number"])

    # Count resolution labels
    all_resolution_labels = config.all_resolution_label_names()
    current_labels = [lbl.name for lbl in priv_issue.get_labels()]
    resolution_labels_present = [
        lbl for lbl in current_labels if lbl in all_resolution_labels
    ]

    if len(resolution_labels_present) == 1:
        # Exactly one resolution label — close public
        label_name = resolution_labels_present[0]
        resolution_key = config.resolution_key_for_label(label_name)

        pub_repo = client.get_repo(config.public_repo)
        pub_issue = pub_repo.get_issue(public_number)

        if pub_issue.state != "closed":
            note = config.resolution_note(resolution_key)
            if note:
                pub_issue.create_comment(note)
            state_reason = config.resolution_state_reason(resolution_key)
            if state_reason:
                pub_issue.edit(state="closed", state_reason=state_reason)
            else:
                pub_issue.edit(state="closed")
            logger.info(
                "Closed public #%d with resolution '%s' from private #%d",
                public_number,
                resolution_key,
                issue["number"],
            )

        # Remove needs-resolution if present
        if config.needs_resolution_label in current_labels:
            try:
                priv_issue.remove_from_labels(config.needs_resolution_label)
            except Exception:
                pass

    else:
        # 0 or >1 resolution labels — nudge
        _ensure_label(priv_repo, config.needs_resolution_label)
        if config.needs_resolution_label not in current_labels:
            priv_issue.add_to_labels(config.needs_resolution_label)

        allowed = ", ".join(
            f"`{name}`" for name in sorted(all_resolution_labels)
        )
        priv_issue.create_comment(
            "Public issue is still open. Add exactly one resolution label "
            f"({allowed}), then close again."
        )
        logger.info(
            "Private #%d closed with %d resolution labels, added %s",
            issue["number"],
            len(resolution_labels_present),
            config.needs_resolution_label,
        )


def _ensure_label(repo, label_name: str) -> None:
    try:
        repo.get_label(label_name)
    except Exception:
        try:
            repo.create_label(name=label_name, color="fbca04")
        except Exception:
            pass
