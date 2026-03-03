"""Handle public comment deleted: tombstone the mirrored private comment."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from github import Github

from lyrebird.config import Config
from lyrebird.mapping import (
    build_tombstone_comment_body,
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
            "No mapping for public #%d, skipping comment delete",
            public_issue["number"],
        )
        return

    mirrored = find_mirrored_comment(mapping.private_issue, comment["id"])
    if mirrored is None:
        logger.info(
            "No mirrored comment for public comment %d, nothing to tombstone",
            comment["id"],
        )
        return

    tombstone = build_tombstone_comment_body(
        author=comment["user"]["login"],
        permalink=comment["html_url"],
        timestamp=datetime.now(timezone.utc).isoformat(),
        public_comment_id=comment["id"],
    )
    mirrored.edit(body=tombstone)
    logger.info(
        "Tombstoned mirrored comment for public comment %d on private #%d",
        comment["id"],
        mapping.private_issue_number,
    )
