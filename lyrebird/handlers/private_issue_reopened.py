"""Handle private issue reopened: clean up resolution and audit."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config

logger = logging.getLogger(__name__)


def handle(client: Github, config: Config, payload: dict) -> None:
    issue = payload["issue"]

    priv_repo = client.get_repo(config.private_repo)
    priv_issue = priv_repo.get_issue(issue["number"])

    current_labels = [lbl.name for lbl in priv_issue.get_labels()]
    all_resolution_labels = config.all_resolution_label_names()

    # Remove resolution labels
    for lbl_name in current_labels:
        if lbl_name in all_resolution_labels:
            try:
                priv_issue.remove_from_labels(lbl_name)
            except Exception:
                pass

    # Remove needs-public-resolution if present
    if config.needs_resolution_label in current_labels:
        try:
            priv_issue.remove_from_labels(config.needs_resolution_label)
        except Exception:
            pass

    # Audit comment
    sender = payload.get("sender", {}).get("login", "unknown")
    priv_issue.create_comment(f"Private issue reopened by @{sender}.")
    logger.info("Private #%d reopened, cleaned resolution labels", issue["number"])
