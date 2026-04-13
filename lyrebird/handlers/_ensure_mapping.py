"""Idempotent bootstrap: ensure a public issue has a private mirror."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.handlers._set_issue_type import set_issue_type
from lyrebird.mapping import (
    PrivateMapping,
    build_mapping_comment,
    build_private_issue_body,
    build_private_issue_title,
    resolve_mapping,
)
from lyrebird.milestones import milestone_from_payload, resolve_or_create_milestone

logger = logging.getLogger(__name__)


def ensure_private_mapping(
    client: Github, config: Config, public_issue: dict
) -> PrivateMapping:
    """Return the private mapping, creating a new private issue if missing.

    This is the single entry point every public handler calls before touching
    the private mirror. If a previous `opened` event was dropped (e.g. cancelled
    by the Actions concurrency queue), the first handler that runs will create
    the mirror here using the full current state from the payload. Subsequent
    handlers find the mapping and proceed normally.
    """
    existing = resolve_mapping(client, config, public_issue)
    if existing is not None:
        return existing

    priv_repo = client.get_repo(config.private_repo)
    title = build_private_issue_title(public_issue)
    body = build_private_issue_body(config, public_issue)

    label_names = [lbl["name"] for lbl in public_issue.get("labels", [])]
    for lbl in public_issue.get("labels", []):
        ensure_label(priv_repo, lbl)

    private_issue = priv_repo.create_issue(
        title=title,
        body=body,
        labels=label_names if label_names else [],
    )
    logger.info(
        "Bootstrapped private issue #%d for public #%d",
        private_issue.number,
        public_issue["number"],
    )

    issue_type = (public_issue.get("type") or {}).get("name")
    if issue_type:
        set_issue_type(client, private_issue, issue_type)

    milestone_data = public_issue.get("milestone")
    if milestone_data:
        source_ms = milestone_from_payload(milestone_data)
        target_ms = resolve_or_create_milestone(priv_repo, source_ms)
        private_issue.edit(milestone=target_ms)

    pub_repo = client.get_repo(config.public_repo)
    pub_issue = pub_repo.get_issue(public_issue["number"])
    mapping_text = build_mapping_comment(
        config, public_issue["node_id"], private_issue.number
    )
    pub_issue.create_comment(mapping_text)
    logger.info("Posted mapping comment on public #%d", public_issue["number"])

    return PrivateMapping(
        private_issue=private_issue,
        private_issue_number=private_issue.number,
    )


def ensure_label(repo, label_data: dict) -> None:
    """Create label in repo if it doesn't exist. Silent on failure."""
    try:
        repo.get_label(label_data["name"])
    except Exception:
        try:
            color = label_data.get("color", "ededed")
            description = label_data.get("description", "") or ""
            repo.create_label(
                name=label_data["name"],
                color=color,
                description=description,
            )
        except Exception:
            logger.warning("Could not create label %s", label_data["name"])
