"""Handle public comment created: mirror to private issue."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.mapping import build_mirrored_comment_body, resolve_mapping

logger = logging.getLogger(__name__)


def handle(client: Github, config: Config, payload: dict) -> None:
    public_issue = payload["issue"]
    comment = payload["comment"]

    # Defense-in-depth: never mirror the bot's own comments, even if
    # is_bot_event() in cli.py failed to catch this event.
    from lyrebird.loop_prevention import _is_bot_login

    comment_author = comment.get("user", {}).get("login", "")
    if _is_bot_login(config, comment_author):
        logger.info(
            "Skipping bot-authored comment %d on public #%d",
            comment["id"],
            public_issue["number"],
        )
        return

    mapping = resolve_mapping(client, config, public_issue)
    if mapping is None:
        logger.warning(
            "No mapping for public #%d, skipping comment", public_issue["number"]
        )
        return

    body = build_mirrored_comment_body(
        author=comment["user"]["login"],
        permalink=comment["html_url"],
        body=comment.get("body") or "",
        public_comment_id=comment["id"],
    )

    mapping.private_issue.create_comment(body)
    logger.info(
        "Mirrored comment %d to private #%d",
        comment["id"],
        mapping.private_issue_number,
    )
