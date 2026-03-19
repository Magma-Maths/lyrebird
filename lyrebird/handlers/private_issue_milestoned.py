"""Handle private issue milestoned/demilestoned: mirror to public."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.mapping import parse_private_body_markers, public_number_from_url
from lyrebird.milestones import milestone_from_payload, resolve_or_create_milestone

logger = logging.getLogger(__name__)


def handle(client: Github, config: Config, payload: dict) -> None:
    action = payload["action"]
    issue = payload["issue"]
    issue_body = issue.get("body") or ""

    markers = parse_private_body_markers(issue_body)
    if markers is None:
        logger.info(
            "Private #%d has no body markers, skipping milestone sync",
            issue["number"],
        )
        return

    public_url, _ = markers
    public_number = public_number_from_url(public_url)

    pub_repo = client.get_repo(config.public_repo)
    pub_issue = pub_repo.get_issue(public_number)

    if action == "milestoned":
        milestone_data = payload["milestone"]
        source_ms = milestone_from_payload(milestone_data)
        target_ms = resolve_or_create_milestone(pub_repo, source_ms)
        pub_issue.edit(milestone=target_ms)
        logger.info(
            "Set milestone '%s' on public #%d",
            milestone_data["title"],
            public_number,
        )
    elif action == "demilestoned":
        pub_issue.edit(milestone=None)
        logger.info("Removed milestone from public #%d", public_number)
