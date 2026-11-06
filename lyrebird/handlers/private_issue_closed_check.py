"""Delayed close check: nudge if no resolution was posted during grace period."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.mapping import parse_private_body_markers, public_number_from_url

logger = logging.getLogger(__name__)


def _nudge_message(config: Config, public_url: str, present: set[str]) -> str:
    public_issue = f"Public issue [#{public_number_from_url(public_url)}]({public_url})"
    if len(present) > 1:
        labels = ", ".join(f"`{name}`" for name in sorted(present))
        return (
            f"{public_issue} was closed with no note because this "
            f"issue has {len(present)} resolution labels ({labels}). "
            "Remove them all, then add the one you want; adding it posts its note."
        )

    offered = [
        f"`{name}`"
        for name, note, _ in config.resolution_labels.values()
        if note and name != config.needs_resolution_label
    ]
    allowed = (
        ", ".join(offered[:-1]) + " or " + offered[-1]
        if len(offered) > 1
        else "".join(offered)
    )
    return (
        f"{public_issue} was closed with no note. "
        f"To post one, add a resolution label: {allowed}. "
        "To write your own note instead, comment `/anon <message>` here."
    )


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

    # No single resolution label - nudge
    if config.needs_resolution_label not in current_labels:
        priv_issue.add_to_labels(config.needs_resolution_label)

    msg = _nudge_message(config, markers[0], resolution_labels_present)
    priv_issue.create_comment(msg)
    logger.info(
        "Private #%d closed with %d resolution labels, nudged after grace period",
        issue["number"],
        len(resolution_labels_present),
    )
