"""Handle public issue typed/untyped: mirror issue type to private."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.handlers._set_issue_type import set_issue_type
from lyrebird.mapping import resolve_mapping

logger = logging.getLogger(__name__)


def handle(client: Github, config: Config, payload: dict) -> None:
    public_issue = payload["issue"]
    issue_type = (public_issue.get("type") or {}).get("name")

    mapping = resolve_mapping(client, config, public_issue)
    if mapping is None:
        logger.info("No mapping for public #%d, skipping type sync", public_issue["number"])
        return

    priv_repo = client.get_repo(config.private_repo)
    priv_issue = priv_repo.get_issue(mapping.private_issue_number)
    set_issue_type(client, priv_issue, issue_type)
