"""Tests for lyrebird.loop_prevention."""

from __future__ import annotations

from lyrebird.loop_prevention import is_bot_event


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
