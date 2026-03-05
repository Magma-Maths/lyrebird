"""Delayed close check: nudge if no resolution was posted during grace period."""

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
        return

    priv_repo = client.get_repo(config.private_repo)
    priv_issue = priv_repo.get_issue(issue["number"])

    # Bail if reopened during grace period
    if priv_issue.state != "closed":
        logger.info(
            "Private #%d reopened during grace period, skipping nudge",
            issue["number"],
        )
        return

    # Count resolution labels (excluding resolution:none itself)
    all_resolution_labels = config.all_resolution_label_names()
    current_labels = {lbl.name for lbl in priv_issue.get_labels()}
    resolution_labels_present = (
        current_labels & all_resolution_labels
    ) - {config.needs_resolution_label}

    if len(resolution_labels_present) == 1:
        # Already handled by close handler or label handler
        return

    # No single resolution label — nudge
    if config.needs_resolution_label not in current_labels:
        priv_issue.add_to_labels(config.needs_resolution_label)

    allowed = ", ".join(
        f"`{name}`"
        for name in sorted(all_resolution_labels - {config.needs_resolution_label})
    )
    priv_issue.create_comment(
        "No resolution posted publicly. Add exactly one resolution label "
        f"({allowed}), or use `/anon`."
    )
    logger.info(
        "Private #%d closed without resolution, nudged after grace period",
        issue["number"],
    )
