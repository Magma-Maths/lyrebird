"""Tests for lyrebird.loop_prevention."""

from __future__ import annotations

from lyrebird.config import Config
from lyrebird.loop_prevention import _is_bot_login, is_bot_event


def test_bot_login_exact_match(config):
    payload = {"sender": {"login": "lyrebird[bot]", "type": "Bot"}}
    assert is_bot_event(config, payload) is True


def test_human_sender(config):
    payload = {"sender": {"login": "engineer", "type": "User"}}
    assert is_bot_event(config, payload) is False


def test_different_bot(config):
    payload = {"sender": {"login": "dependabot[bot]", "type": "Bot"}}
    assert is_bot_event(config, payload) is False


def test_missing_sender(config):
    payload = {}
    assert is_bot_event(config, payload) is False


def test_empty_sender(config):
    payload = {"sender": {}}
    assert is_bot_event(config, payload) is False


# --- _is_bot_login ---


def test_is_bot_login_exact(config):
    assert _is_bot_login(config, "lyrebird[bot]") is True


def test_is_bot_login_without_suffix():
    """bot_login='lyrebird-agent' still matches 'lyrebird-agent[bot]'."""
    cfg = Config(
        public_repo="o/p", private_repo="o/r", bot_login="lyrebird-agent"
    )
    assert _is_bot_login(cfg, "lyrebird-agent[bot]") is True
    assert _is_bot_login(cfg, "lyrebird-agent") is True


def test_is_bot_login_empty_bot_login():
    """Empty bot_login never matches."""
    cfg = Config(public_repo="o/p", private_repo="o/r", bot_login="")
    assert _is_bot_login(cfg, "lyrebird[bot]") is False
    assert _is_bot_login(cfg, "") is False
