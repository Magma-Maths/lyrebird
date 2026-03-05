"""Handle /anon slash command: post anonymous message on public issue."""

from __future__ import annotations

import logging
import re

from github import Github

from lyrebird.config import Config
from lyrebird.mapping import parse_private_body_markers

logger = logging.getLogger(__name__)

SLASH_ANON_RE = re.compile(r"^/anon\s+(.+)", re.DOTALL)


def handle(client: Github, config: Config, payload: dict) -> None:
    comment = payload["comment"]
    issue = payload["issue"]
    body = (comment.get("body") or "").strip()

    match = SLASH_ANON_RE.match(body)
    if not match:
        return

    message = match.group(1).strip()
    if not message:
        return

    # Find mapped public issue from private issue body
    issue_body = issue.get("body") or ""
    markers = parse_private_body_markers(issue_body)
    if markers is None:
        # Not a mirrored issue
        priv_repo = client.get_repo(config.private_repo)
        priv_issue = priv_repo.get_issue(issue["number"])
        priv_issue.create_comment(
            "This issue is not linked to a public issue. `/anon` has no effect."
        )
        logger.warning(
            "/anon on private #%d which has no public mapping", issue["number"]
        )
        return

    public_url, _ = markers
    # Extract public issue number from URL
    # URL format: https://github.com/ORG/REPO/issues/123
    parts = public_url.rstrip("/").split("/")
    public_number = int(parts[-1])

    pub_repo = client.get_repo(config.public_repo)
    pub_issue = pub_repo.get_issue(public_number)
    public_comment = pub_issue.create_comment(message)

    # Acknowledge in private
    priv_repo = client.get_repo(config.private_repo)
    priv_issue = priv_repo.get_issue(issue["number"])
    priv_issue.create_comment(
        f"Posted to public: {public_comment.html_url}"
    )
    logger.info(
        "/anon on private #%d -> public comment %s",
        issue["number"],
        public_comment.html_url,
    )
