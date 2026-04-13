"""Handle public label added/removed: ensure mirror, then mirror label change."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.handlers._ensure_mapping import ensure_label, ensure_private_mapping

logger = logging.getLogger(__name__)


def handle(client: Github, config: Config, payload: dict) -> None:
    public_issue = payload["issue"]
    action = payload["action"]  # "labeled" or "unlabeled"
    label_data = payload.get("label", {})
    label_name = label_data.get("name", "")

    if not label_name:
        return

    mapping = ensure_private_mapping(client, config, public_issue)
    priv_repo = mapping.private_issue.repository

    if action == "labeled":
        ensure_label(priv_repo, label_data)
        mapping.private_issue.add_to_labels(label_name)
        logger.info(
            "Added label '%s' to private #%d",
            label_name,
            mapping.private_issue_number,
        )
    elif action == "unlabeled":
        try:
            mapping.private_issue.remove_from_labels(label_name)
            logger.info(
                "Removed label '%s' from private #%d",
                label_name,
                mapping.private_issue_number,
            )
        except Exception:
            logger.info(
                "Label '%s' not on private #%d, nothing to remove",
                label_name,
                mapping.private_issue_number,
            )
