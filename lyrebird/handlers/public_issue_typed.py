"""Handle public issue typed/untyped: ensure mirror, then sync issue type."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.handlers._ensure_mapping import ensure_private_mapping
from lyrebird.handlers._set_issue_type import set_issue_type

logger = logging.getLogger(__name__)


def handle(client: Github, config: Config, payload: dict) -> None:
    public_issue = payload["issue"]
    issue_type = (public_issue.get("type") or {}).get("name")

    mapping = ensure_private_mapping(client, config, public_issue)

    priv_repo = client.get_repo(config.private_repo)
    priv_issue = priv_repo.get_issue(mapping.private_issue_number)
    set_issue_type(client, priv_issue, issue_type)
