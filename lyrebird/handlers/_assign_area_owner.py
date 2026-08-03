"""Shared helper: assign an area's default owner to an unassigned private issue.

Lyrebird ignores events sent by its own App identity, so a label the bot applies
never comes back as a `labeled` event. Every site that puts an area label on a
private issue therefore has to run the assignment itself.
"""

from __future__ import annotations

import logging
from typing import Iterable

from github import Github

from lyrebird.config import Config

logger = logging.getLogger(__name__)


def _first_mapped_area(
    config: Config, label_names: Iterable[str]
) -> tuple[str, str] | None:
    """Return (label_name, login) for the first name with a configured owner."""
    for name in label_names:
        login = config.assignee_for_area(name)
        if login:
            return name, login
    return None


def assign_area_owner(
    config: Config, priv_issue, label_names: Iterable[str]
) -> str | None:
    """Assign the area owner for the first mapped label in *label_names*.

    Never overrides an existing assignment.  Returns the login assigned, or
    None when nothing was assigned.
    """
    match = _first_mapped_area(config, label_names)
    if match is None:
        # No area label (or no owner configured); nothing to do.
        return None
    label_name, login = match

    if priv_issue.assignees:
        logger.info(
            "Private #%s already assigned; leaving area owner untouched",
            priv_issue.number,
        )
        return None

    try:
        priv_issue.add_to_assignees(login)
        logger.info(
            "Assigned '%s' to private #%s for area label '%s'",
            login,
            priv_issue.number,
            label_name,
        )
    except Exception:
        logger.exception(
            "Failed to assign '%s' to private #%s for area label '%s'",
            login,
            priv_issue.number,
            label_name,
        )
        return None
    return login


def assign_area_owner_by_number(
    client: Github, config: Config, issue_number: int, label_names: Iterable[str]
) -> str | None:
    """Fetch private issue *issue_number*, then delegate to assign_area_owner.

    For callers that hold only a webhook payload dict, or whose issue object
    may be stale.  The mapped-label check runs first so a label with no owner
    costs no API call.
    """
    if _first_mapped_area(config, label_names) is None:
        return None
    priv_repo = client.get_repo(config.private_repo)
    priv_issue = priv_repo.get_issue(issue_number)
    return assign_area_owner(config, priv_issue, label_names)
