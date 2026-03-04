"""Handle public issue opened: create private mirror + mapping comment."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.handlers._set_issue_type import set_issue_type
from lyrebird.mapping import (
    build_mapping_comment,
    build_private_issue_body,
    build_private_issue_title,
    resolve_mapping,
)

logger = logging.getLogger(__name__)


def handle(client: Github, config: Config, payload: dict) -> None:
    public_issue = payload["issue"]
    node_id = public_issue["node_id"]

    # Idempotency: check if mapping already exists
    existing = resolve_mapping(client, config, public_issue)
    if existing is not None:
        logger.info(
            "Mapping already exists for public #%d -> private #%d%s",
            public_issue["number"],
            existing.private_issue_number,
            " (self-healed)" if existing.was_self_healed else "",
        )
        return

    # Create private issue
    priv_repo = client.get_repo(config.private_repo)
    title = build_private_issue_title(public_issue)
    body = build_private_issue_body(config, public_issue)

    # Mirror public labels
    label_names = [lbl["name"] for lbl in public_issue.get("labels", [])]
    # Ensure labels exist in private repo
    for lbl in public_issue.get("labels", []):
        _ensure_label(priv_repo, lbl)

    private_issue = priv_repo.create_issue(
        title=title,
        body=body,
        labels=label_names if label_names else [],
    )
    logger.info(
        "Created private issue #%d for public #%d",
        private_issue.number,
        public_issue["number"],
    )

    # Mirror issue type if present
    issue_type = (public_issue.get("type") or {}).get("name")
    if issue_type:
        set_issue_type(client, private_issue, issue_type)

    # Post mapping comment on public issue (only after private creation succeeds)
    pub_repo = client.get_repo(config.public_repo)
    pub_issue = pub_repo.get_issue(public_issue["number"])
    mapping_text = build_mapping_comment(config, node_id, private_issue.number)
    pub_issue.create_comment(mapping_text)
    logger.info("Posted mapping comment on public #%d", public_issue["number"])


def _ensure_label(repo, label_data: dict) -> None:
    """Create label in repo if it doesn't exist."""
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
