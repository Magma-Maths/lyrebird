"""Handle public issue milestoned/demilestoned: mirror to private."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.mapping import resolve_mapping
from lyrebird.milestones import milestone_from_payload, resolve_or_create_milestone

logger = logging.getLogger(__name__)


def handle(client: Github, config: Config, payload: dict) -> None:
    action = payload["action"]
    public_issue = payload["issue"]

    mapping = resolve_mapping(client, config, public_issue)
    if mapping is None:
        logger.info(
            "No mapping for public #%d, skipping milestone sync",
            public_issue["number"],
        )
        return

    priv_repo = client.get_repo(config.private_repo)
    priv_issue = priv_repo.get_issue(mapping.private_issue_number)

    if action == "milestoned":
        milestone_data = payload["milestone"]
        source_ms = milestone_from_payload(milestone_data)
        target_ms = resolve_or_create_milestone(priv_repo, source_ms)
        priv_issue.edit(milestone=target_ms)
        logger.info(
            "Set milestone '%s' on private #%d",
            milestone_data["title"],
            priv_issue.number,
        )
    elif action == "demilestoned":
        priv_issue.edit(milestone=None)
        logger.info("Removed milestone from private #%d", priv_issue.number)
