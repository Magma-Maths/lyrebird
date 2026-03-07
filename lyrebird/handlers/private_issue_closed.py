"""Handle private issue closed: close public, post resolution note if present."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.mapping import parse_private_body_markers, public_number_from_url

logger = logging.getLogger(__name__)


def handle(client: Github, config: Config, payload: dict) -> None:
    issue = payload["issue"]
    issue_body = issue.get("body") or ""

    markers = parse_private_body_markers(issue_body)
    if markers is None:
        return

    public_url, _ = markers
    public_number = public_number_from_url(public_url)

    priv_repo = client.get_repo(config.private_repo)
    priv_issue = priv_repo.get_issue(issue["number"])

    # Count resolution labels
    all_resolution_labels = config.all_resolution_label_names()
    current_labels = [lbl.name for lbl in priv_issue.get_labels()]
    resolution_labels_present = [
        lbl for lbl in current_labels if lbl in all_resolution_labels
    ]

    pub_repo = client.get_repo(config.public_repo)
    pub_issue = pub_repo.get_issue(public_number)

    if pub_issue.state != "closed":
        if len(resolution_labels_present) == 1:
            # Post resolution note before closing
            label_name = resolution_labels_present[0]
            resolution_key = config.resolution_key_for_label(label_name)
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
        else:
            # 0 or >1 resolution labels — close public with no comment;
            # the delayed close check handler will nudge after grace period
            pub_issue.edit(state="closed")
            logger.info(
                "Closed public #%d (no single resolution label) from private #%d",
                public_number,
                issue["number"],
            )
