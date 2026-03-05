"""Handle public issue closed/reopened: update private labels + audit comment."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.handlers._cleanup_labels import cleanup_private_resolution_labels
from lyrebird.mapping import resolve_mapping

logger = logging.getLogger(__name__)


def handle(client: Github, config: Config, payload: dict) -> None:
    public_issue = payload["issue"]
    action = payload["action"]  # "closed" or "reopened"
    sender = payload.get("sender", {}).get("login", "unknown")

    mapping = resolve_mapping(client, config, public_issue)
    if mapping is None:
        logger.warning(
            "No mapping for public #%d, skipping state change",
            public_issue["number"],
        )
        return

    private_issue = mapping.private_issue
    priv_repo = private_issue.repository
    is_reporter = sender == public_issue["user"]["login"]

    if action == "closed":
        _ensure_and_add_label(priv_repo, private_issue, config.closed_label)
        if is_reporter:
            _ensure_and_add_label(
                priv_repo, private_issue, config.closed_by_reporter_label
            )
        audit = f"Public issue closed by @{sender}"
        if is_reporter:
            audit += " (original reporter)"
        private_issue.create_comment(audit)

        state_reason = public_issue.get("state_reason")
        if state_reason:
            private_issue.edit(state="closed", state_reason=state_reason)
        else:
            private_issue.edit(state="closed")

    elif action == "reopened":
        cleanup_private_resolution_labels(config, private_issue)
        audit = f"Public issue reopened by @{sender}"
        if is_reporter:
            audit += " (original reporter)"
        private_issue.create_comment(audit)
        private_issue.edit(state="open")

    logger.info(
        "Handled public %s for private #%d",
        action,
        mapping.private_issue_number,
    )


def _ensure_and_add_label(repo, issue, label_name: str) -> None:
    """Ensure label exists and add it to the issue."""
    try:
        repo.get_label(label_name)
    except Exception:
        try:
            repo.create_label(name=label_name, color="e4e669")
        except Exception:
            pass
    try:
        issue.add_to_labels(label_name)
    except Exception:
        pass
