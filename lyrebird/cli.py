"""CLI entry point for lyrebird."""

from __future__ import annotations

import json
import logging
import os
import sys

from github import Auth, Github

from lyrebird.config import load_config
from lyrebird.dispatch import route
from lyrebird.loop_prevention import is_bot_event

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # Load config
    config = load_config()

    # Create GitHub client
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        logger.error("GITHUB_TOKEN is required")
        sys.exit(1)
    client = Github(auth=Auth.Token(token))

    # Parse payload
    payload_str = os.environ.get("EVENT_PAYLOAD")
    if not payload_str:
        payload_file = os.environ.get("EVENT_PAYLOAD_FILE")
        if payload_file:
            with open(payload_file) as f:
                payload_str = f.read()
    if not payload_str:
        logger.error("EVENT_PAYLOAD or EVENT_PAYLOAD_FILE is required")
        sys.exit(1)

    payload = json.loads(payload_str)

    # Determine event source and routing
    event_name = os.environ.get("EVENT_NAME", "")
    action = os.environ.get("EVENT_ACTION", "")
    source = os.environ.get("EVENT_SOURCE", "public")

    if not event_name or not action:
        logger.error("EVENT_NAME and EVENT_ACTION are required")
        sys.exit(1)

    # Loop prevention
    if is_bot_event(config, payload):
        logger.info("Ignoring bot event from %s", payload.get("sender", {}).get("login"))
        return

    # Dispatch
    logger.info(
        "Processing %s/%s (source=%s) node_id=%s",
        event_name, action, source,
        payload.get("issue", {}).get("node_id", "unknown"),
    )
    route(client, config, event_name, action, payload, source=source)
    logger.info("Done")
