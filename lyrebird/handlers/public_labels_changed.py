"""Handle public label added/removed: mirror to private issue."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.mapping import resolve_mapping

logger = logging.getLogger(__name__)


def handle(client: Github, config: Config, payload: dict) -> None:
    public_issue = payload["issue"]
    action = payload["action"]  # "labeled" or "unlabeled"
    label_data = payload.get("label", {})
    label_name = label_data.get("name", "")

    if not label_name:
        return

    mapping = resolve_mapping(client, config, public_issue)
    if mapping is None:
        logger.warning(
            "No mapping for public #%d, skipping label change",
            public_issue["number"],
        )
        return

    priv_repo = mapping.private_issue.repository

    if action == "labeled":
        # Ensure label exists in private repo
        _ensure_label(priv_repo, label_data)
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


def _ensure_label(repo, label_data: dict) -> None:
    """Create label in repo if it doesn't exist."""
    try:
        repo.get_label(label_data["name"])
    except Exception:
        try:
            color = label_data.get("color", "ededed")
            description = label_data.get("description", "") or ""
            repo.create_label(
                name=label_data["name"],
                color=color,
                description=description,
            )
        except Exception:
            logger.warning("Could not create label %s", label_data["name"])
