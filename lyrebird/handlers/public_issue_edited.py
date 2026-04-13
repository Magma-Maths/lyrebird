"""Handle public issue edited: ensure mirror exists, then update title and body."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.handlers._ensure_mapping import ensure_private_mapping
from lyrebird.mapping import (
    build_private_issue_title,
    update_private_body_public_section,
)

logger = logging.getLogger(__name__)


def handle(client: Github, config: Config, payload: dict) -> None:
    public_issue = payload["issue"]
    mapping = ensure_private_mapping(client, config, public_issue)

    private_issue = mapping.private_issue
    new_title = build_private_issue_title(public_issue)
    new_body = update_private_body_public_section(
        private_issue.body or "",
        public_issue.get("body") or "",
    )

    private_issue.edit(title=new_title, body=new_body)
    logger.info(
        "Updated private #%d from public #%d edit",
        mapping.private_issue_number,
        public_issue["number"],
    )
