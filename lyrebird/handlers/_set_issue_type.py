"""Shared helper to set issue type via the REST API (PyGithub doesn't support it)."""

from __future__ import annotations

import logging

from github import Github

logger = logging.getLogger(__name__)


def set_issue_type(client: Github, issue, type_name: str | None) -> None:
    """Set or clear the issue type on a PyGithub Issue object."""
    try:
        client._Github__requester.requestJsonAndCheck(
            "PATCH",
            issue.url,
            input={"type": type_name},
        )
        logger.info("Set issue type '%s' on #%d", type_name, issue.number)
    except Exception:
        logger.warning("Could not set issue type '%s' on #%d", type_name, issue.number)
