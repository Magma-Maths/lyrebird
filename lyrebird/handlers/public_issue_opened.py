"""Handle public issue opened: ensure private mirror exists."""

from __future__ import annotations

from github import Github

from lyrebird.config import Config
from lyrebird.handlers._ensure_mapping import ensure_private_mapping


def handle(client: Github, config: Config, payload: dict) -> None:
    ensure_private_mapping(client, config, payload["issue"])
