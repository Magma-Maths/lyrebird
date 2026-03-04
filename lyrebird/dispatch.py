"""Route (event_name, action) pairs to handler functions."""

from __future__ import annotations

import logging
from typing import Callable

from github import Github

from lyrebird.config import Config
from lyrebird.handlers import (
    private_issue_closed,
    private_issue_reopened,
    private_labels_changed,
    public_comment_created,
    public_comment_deleted,
    public_comment_edited,
    public_issue_edited,
    public_issue_opened,
    public_issue_state,
    public_issue_typed,
    public_labels_changed,
    slash_public,
    slash_public_close,
)

logger = logging.getLogger(__name__)

Handler = Callable[[Github, Config, dict], None]


def _route_private_comment(client: Github, config: Config, payload: dict) -> None:
    """Dispatch private comments: slash commands or ignore."""
    body = (payload.get("comment", {}).get("body") or "").strip()
    if body.startswith("/public-close"):
        slash_public_close.handle(client, config, payload)
    elif body.startswith("/public"):
        slash_public.handle(client, config, payload)
    # else: not a slash command, ignore


# (event_name, action) → handler
PUBLIC_ROUTES: dict[tuple[str, str], Handler] = {
    ("issues", "opened"): public_issue_opened.handle,
    ("issues", "edited"): public_issue_edited.handle,
    ("issues", "labeled"): public_labels_changed.handle,
    ("issues", "unlabeled"): public_labels_changed.handle,
    ("issues", "closed"): public_issue_state.handle,
    ("issues", "reopened"): public_issue_state.handle,
    ("issues", "typed"): public_issue_typed.handle,
    ("issue_comment", "created"): public_comment_created.handle,
    ("issue_comment", "edited"): public_comment_edited.handle,
    ("issue_comment", "deleted"): public_comment_deleted.handle,
}

PRIVATE_ROUTES: dict[tuple[str, str], Handler] = {
    ("issues", "closed"): private_issue_closed.handle,
    ("issues", "reopened"): private_issue_reopened.handle,
    ("issues", "labeled"): private_labels_changed.handle,
    ("issues", "unlabeled"): private_labels_changed.handle,
    ("issue_comment", "created"): _route_private_comment,
}


def route(client: Github, config: Config, event_name: str, action: str,
          payload: dict, *, source: str = "public") -> None:
    """Find and call the handler for the given event."""
    routes = PUBLIC_ROUTES if source == "public" else PRIVATE_ROUTES
    handler = routes.get((event_name, action))
    if handler is None:
        logger.info("No handler for %s/%s (source=%s), skipping", event_name, action, source)
        return
    logger.info("Dispatching %s/%s (source=%s) to %s", event_name, action, source, getattr(handler, "__name__", repr(handler)))
    handler(client, config, payload)
