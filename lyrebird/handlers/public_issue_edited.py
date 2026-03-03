"""Handle public issue edited: update private title and body."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.mapping import (
    build_private_issue_title,
    resolve_mapping,
    update_private_body_public_section,
)

logger = logging.getLogger(__name__)


def handle(client: Github, config: Config, payload: dict) -> None:
    public_issue = payload["issue"]
    mapping = resolve_mapping(client, config, public_issue)
    if mapping is None:
        logger.warning("No mapping for public #%d, skipping edit", public_issue["number"])
        return

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
