"""Handle public issue closed/reopened: ensure mirror, sync state, post audit comment."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.handlers._cleanup_labels import cleanup_private_resolution_labels
from lyrebird.handlers._ensure_mapping import ensure_private_mapping

logger = logging.getLogger(__name__)


def handle(client: Github, config: Config, payload: dict) -> None:
    public_issue = payload["issue"]
    action = payload["action"]  # "closed" or "reopened"
    sender = payload.get("sender", {}).get("login", "unknown")

    mapping = ensure_private_mapping(
        client,
        config,
        public_issue,
        assign_owner_on_bootstrap=action != "closed",
    )

    if mapping.was_bootstrapped and action == "reopened":
        # Rare race: both `opened` and `closed` were dropped by the Actions
        # concurrency queue, so `reopened` is the first event to run. Bootstrap
        # already created the mirror in the open state, matching what the
        # reopen would produce — and posting "reopened by @X" on a mirror that
        # was never closed from the private side's perspective would be
        # misleading. The `closed` path does not short-circuit because
        # bootstrap can only create in open state and the close is still needed.
        logger.info(
            "Bootstrapped mirror on reopened event for public #%d (opened+closed both dropped)",
            public_issue["number"],
        )
        return

    private_issue = mapping.private_issue
    is_reporter = sender == public_issue["user"]["login"]

    if action == "closed":
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
