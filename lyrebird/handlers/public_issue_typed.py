"""Handle public issue typed: mirror issue type to private."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.mapping import parse_private_body_markers, resolve_mapping

logger = logging.getLogger(__name__)


def handle(client: Github, config: Config, payload: dict) -> None:
    public_issue = payload["issue"]
    issue_type = (public_issue.get("type") or {}).get("name")

    # Resolve mapping to find private issue
    mapping = resolve_mapping(client, config, public_issue)
    if mapping is None:
        logger.info("No mapping found for public #%d, skipping type sync", public_issue["number"])
        return

    priv_repo = client.get_repo(config.private_repo)
    priv_issue = priv_repo.get_issue(mapping.private_issue_number)

    try:
        client._Github__requester.requestJsonAndCheck(
            "PATCH",
            priv_issue.url,
            input={"type": issue_type},
        )
        logger.info(
            "Set issue type '%s' on private #%d",
            issue_type,
            mapping.private_issue_number,
        )
    except Exception:
        logger.warning(
            "Could not set issue type '%s' on private #%d",
            issue_type,
            mapping.private_issue_number,
        )
