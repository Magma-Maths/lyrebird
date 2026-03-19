"""Shared helpers for milestone synchronization."""

from __future__ import annotations

import logging

from github.Milestone import Milestone
from github.Repository import Repository

logger = logging.getLogger(__name__)


def find_milestone_by_title(repo: Repository, title: str) -> Milestone | None:
    """Find a milestone by exact title (case-sensitive) in both open and closed states."""
    for state in ("open", "closed"):
        for ms in repo.get_milestones(state=state):
            if ms.title == title:
                return ms
    return None


def resolve_or_create_milestone(
    target_repo: Repository, source_milestone: Milestone
) -> Milestone:
    """Find or create a milestone in target_repo matching the source milestone's title.

    Copies all fields (title, description, due_on, state) on creation.
    """
    existing = find_milestone_by_title(target_repo, source_milestone.title)
    if existing is not None:
        return existing

    created = target_repo.create_milestone(
        title=source_milestone.title,
        description=source_milestone.description or "",
        due_on=source_milestone.due_on,
        state=source_milestone.state,
    )
    logger.info("Created milestone '%s' in %s", source_milestone.title, target_repo.full_name)
    return created


def sync_milestone_properties(
    target: Milestone, source: Milestone
) -> bool:
    """Update target milestone properties to match source. Returns True if updated."""
    updates: dict = {}

    if (target.description or "") != (source.description or ""):
        updates["description"] = source.description or ""
    if target.due_on != source.due_on:
        updates["due_on"] = source.due_on
    if target.state != source.state:
        updates["state"] = source.state

    if not updates:
        return False

    # PyGithub's Milestone.edit() requires title as a positional arg
    target.edit(title=target.title, **updates)
    logger.info("Updated milestone '%s': %s", target.title, list(updates.keys()))
    return True


def milestone_from_payload(data: dict):
    """Build a SimpleNamespace with milestone attributes from a webhook payload dict."""
    from datetime import datetime
    from types import SimpleNamespace

    due_on = None
    if data.get("due_on"):
        due_on = datetime.fromisoformat(data["due_on"].replace("Z", "+00:00"))

    return SimpleNamespace(
        title=data["title"],
        description=data.get("description") or "",
        due_on=due_on,
        state=data.get("state", "open"),
    )
