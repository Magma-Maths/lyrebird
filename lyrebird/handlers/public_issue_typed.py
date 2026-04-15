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
    action = payload["action"]  # "typed" or "untyped"
    issue_type = (public_issue.get("type") or {}).get("name")

    mapping = ensure_private_mapping(client, config, public_issue)
    if mapping.was_bootstrapped and action == "typed":
        # Bootstrap already set the type. For `untyped`, fall through — we
        # can't trust that `payload.issue.type` is post-action state (GitHub
        # does not guarantee it), so explicitly clear the type.
        return

    set_issue_type(client, mapping.private_issue, issue_type)
