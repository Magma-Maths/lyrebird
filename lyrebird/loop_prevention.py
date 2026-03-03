"""Check whether an event should be ignored (sent by the bot itself)."""

from __future__ import annotations

from lyrebird.config import Config


def is_bot_event(config: Config, payload: dict) -> bool:
    """Return True if the event sender is the integration identity."""
    sender = payload.get("sender", {})
    login = sender.get("login", "")
    sender_type = sender.get("type", "")

    if login == config.bot_login:
        return True
    # GitHub Apps have type "Bot"
    if sender_type == "Bot" and login.endswith("[bot]"):
        # Check if the base name matches (e.g. "lyrebird" matches "lyrebird[bot]")
        base = config.bot_login.removesuffix("[bot]")
        if login == f"{base}[bot]":
            return True
    return False
