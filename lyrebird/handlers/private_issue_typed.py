"""Handle private issue typed/untyped: mirror issue type to public."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.handlers._set_issue_type import set_issue_type
from lyrebird.mapping import parse_private_body_markers, public_number_from_url

logger = logging.getLogger(__name__)


def handle(client: Github, config: Config, payload: dict) -> None:
    issue = payload["issue"]
    issue_type = (issue.get("type") or {}).get("name")

    issue_body = issue.get("body") or ""
    markers = parse_private_body_markers(issue_body)
    if markers is None:
        return

    public_url, _ = markers
    public_number = public_number_from_url(public_url)

    pub_repo = client.get_repo(config.public_repo)
    pub_issue = pub_repo.get_issue(public_number)
    set_issue_type(client, pub_issue, issue_type)
