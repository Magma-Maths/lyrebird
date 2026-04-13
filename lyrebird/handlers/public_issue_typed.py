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
    set_issue_type(client, mapping.private_issue, issue_type)
