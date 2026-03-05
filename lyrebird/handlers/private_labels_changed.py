"""Handle private label changes: mirror to public if label exists there."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.mapping import parse_private_body_markers

logger = logging.getLogger(__name__)


def handle(client: Github, config: Config, payload: dict) -> None:
    issue = payload["issue"]
    action = payload["action"]  # "labeled" or "unlabeled"
    label_data = payload.get("label", {})
    label_name = label_data.get("name", "")

    if not label_name:
        return

    issue_body = issue.get("body") or ""
    markers = parse_private_body_markers(issue_body)
    if markers is None:
        # Not a mirrored issue
        return

    public_url, _ = markers
    parts = public_url.rstrip("/").split("/")
    public_number = int(parts[-1])

    pub_repo = client.get_repo(config.public_repo)

    # Only mirror if the label exists on the public repo
    try:
        pub_repo.get_label(label_name)
    except Exception:
        logger.info(
            "Label '%s' does not exist on public repo, skipping", label_name
        )
        return

    pub_issue = pub_repo.get_issue(public_number)

    if action == "labeled":
        pub_issue.add_to_labels(label_name)
        logger.info("Added label '%s' to public #%d", label_name, public_number)
    elif action == "unlabeled":
        try:
            pub_issue.remove_from_labels(label_name)
            logger.info(
                "Removed label '%s' from public #%d", label_name, public_number
            )
        except Exception:
            pass

    # Special: if a resolution label is added while private is closed,
    # check if we should close the public issue
    if action == "labeled" and label_name in config.all_resolution_label_names():
        priv_repo = client.get_repo(config.private_repo)
        priv_issue = priv_repo.get_issue(issue["number"])
        if priv_issue.state == "closed":
            _maybe_close_public_on_label(client, config, priv_issue, pub_repo, public_number)


def _maybe_close_public_on_label(
    client: Github, config: Config, priv_issue, pub_repo, public_number: int
) -> None:
    """If private is closed and now has exactly 1 resolution label, post note and close public."""
    all_resolution_labels = config.all_resolution_label_names()
    current_labels = [lbl.name for lbl in priv_issue.get_labels()]
    resolution_present = [l for l in current_labels if l in all_resolution_labels]

    if len(resolution_present) != 1:
        return

    label_name = resolution_present[0]
    resolution_key = config.resolution_key_for_label(label_name)

    pub_issue = pub_repo.get_issue(public_number)

    note = config.resolution_note(resolution_key)
    if note:
        pub_issue.create_comment(note)

    # Close public if not already closed
    if pub_issue.state != "closed":
        state_reason = config.resolution_state_reason(resolution_key)
        if state_reason:
            pub_issue.edit(state="closed", state_reason=state_reason)
        else:
            pub_issue.edit(state="closed")

    # Remove resolution:none
    if config.needs_resolution_label in current_labels:
        try:
            priv_issue.remove_from_labels(config.needs_resolution_label)
        except Exception:
            pass

    logger.info(
        "Posted resolution note on public #%d after label added to closed private #%d",
        public_number,
        priv_issue.number,
    )
