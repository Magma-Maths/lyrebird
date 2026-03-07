"""Handle private issue reopened: clean up resolution, reopen public, and audit."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.handlers._cleanup_labels import cleanup_private_resolution_labels
from lyrebird.mapping import parse_private_body_markers, public_number_from_url

logger = logging.getLogger(__name__)


def handle(client: Github, config: Config, payload: dict) -> None:
    issue = payload["issue"]
    issue_body = issue.get("body") or ""

    # Only act on private issues linked to a public issue
    markers = parse_private_body_markers(issue_body)
    if not markers:
        logger.debug("Private #%d has no public mapping, skipping", issue["number"])
        return

    priv_repo = client.get_repo(config.private_repo)
    priv_issue = priv_repo.get_issue(issue["number"])

    cleanup_private_resolution_labels(config, priv_issue)

    # Audit comment
    sender = payload.get("sender", {}).get("login", "unknown")
    priv_issue.create_comment(f"Private issue reopened by @{sender}.")

    # Reopen public issue if it's closed
    public_url, _ = markers
    public_number = public_number_from_url(public_url)
    pub_repo = client.get_repo(config.public_repo)
    pub_issue = pub_repo.get_issue(public_number)
    if pub_issue.state != "open":
        pub_issue.edit(state="open")
        pub_issue.create_comment(
            "This issue has been reopened for further investigation."
        )

    logger.info("Private #%d reopened, cleaned resolution labels", issue["number"])
