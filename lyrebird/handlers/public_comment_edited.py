"""Handle public comment edited: update mirrored private comment."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.mapping import (
    build_mirrored_comment_body,
    find_mirrored_comment,
    resolve_mapping,
)

logger = logging.getLogger(__name__)


def handle(client: Github, config: Config, payload: dict) -> None:
    public_issue = payload["issue"]
    comment = payload["comment"]

    mapping = resolve_mapping(client, config, public_issue)
    if mapping is None:
        logger.warning(
            "No mapping for public #%d, skipping comment edit", public_issue["number"]
        )
        return

    mirrored = find_mirrored_comment(mapping.private_issue, comment["id"])
    new_body = build_mirrored_comment_body(
        author=comment["user"]["login"],
        permalink=comment["html_url"],
        body=comment.get("body") or "",
        public_comment_id=comment["id"],
    )

    if mirrored:
        mirrored.edit(body=new_body)
        logger.info(
            "Updated mirrored comment for public comment %d on private #%d",
            comment["id"],
            mapping.private_issue_number,
        )
    else:
        # Comment not found — create it (rare but safe)
        mapping.private_issue.create_comment(new_body)
        logger.info(
            "Created missing mirrored comment for public comment %d on private #%d",
            comment["id"],
            mapping.private_issue_number,
        )
