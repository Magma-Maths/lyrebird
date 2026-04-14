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

    Bootstraps on demand because GitHub Actions' concurrency queue can silently
    drop `opened` events, so later events must be able to create the mirror.
    The returned PrivateMapping has `was_bootstrapped=True` when a new issue
    was created here — callers can use this to skip mutations already applied
    from the webhook payload's post-action state.
    """
    pub_repo = client.get_repo(config.public_repo)
    pub_issue = pub_repo.get_issue(public_issue["number"])

    existing = resolve_mapping(client, config, public_issue, pub_issue=pub_issue)
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

    mapping_text = build_mapping_comment(
        config, public_issue["node_id"], private_issue.number
    )
    pub_issue.create_comment(mapping_text)
    logger.info("Posted mapping comment on public #%d", public_issue["number"])

    return PrivateMapping(
        private_issue=private_issue,
        private_issue_number=private_issue.number,
        was_bootstrapped=True,
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
