"""Handle /anon slash command: post anonymous message on public issue."""

from __future__ import annotations

import logging
import re

from github import Github

from lyrebird.config import Config
from lyrebird.mapping import parse_private_body_markers, public_number_from_url

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
    public_number = public_number_from_url(public_url)

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

    # Label bookkeeping for closed issues
    if issue.get("state") == "closed":
        current_labels = {lbl.name for lbl in priv_issue.get_labels()}
        # Remove resolution:none if present
        if config.needs_resolution_label in current_labels:
            try:
                priv_issue.remove_from_labels(config.needs_resolution_label)
            except Exception:
                pass
        # Add resolution:custom if no resolution label present
        resolution_labels_present = current_labels & config.all_resolution_label_names()
        # Exclude resolution:none from counting as a "real" resolution
        resolution_labels_present -= {config.needs_resolution_label}
        if not resolution_labels_present:
            custom_label = config.resolution_label_name("custom")
            if custom_label:
                priv_issue.add_to_labels(custom_label)
