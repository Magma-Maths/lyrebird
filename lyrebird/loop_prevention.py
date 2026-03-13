"""Check whether an event should be ignored (sent by the bot itself)."""

from __future__ import annotations

from lyrebird.config import Config


def _is_bot_login(config: Config, login: str) -> bool:
    """Return True if *login* matches the configured bot identity."""
    if not config.bot_login:
        return False
    if login == config.bot_login:
        return True
    # GitHub Apps have type "Bot" and login "name[bot]".
    # Match even when bot_login is stored with or without the suffix.
    base = config.bot_login.removesuffix("[bot]")
    if login == f"{base}[bot]":
        return True
    return False


def is_bot_event(config: Config, payload: dict) -> bool:
    """Return True if the event sender is the integration identity."""
    sender = payload.get("sender", {})
    login = sender.get("login", "")
    sender_type = sender.get("type", "")

    if _is_bot_login(config, login):
        return True
    # GitHub Apps have type "Bot"
    if sender_type == "Bot" and login.endswith("[bot]"):
        base = config.bot_login.removesuffix("[bot]")
        if login == f"{base}[bot]":
            return True
    return False
