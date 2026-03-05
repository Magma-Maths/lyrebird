"""Tests for private_issue_closed_check (delayed close check) handler."""

from __future__ import annotations

from unittest.mock import MagicMock

from lyrebird.handlers.private_issue_closed_check import handle
from tests.conftest import make_private_issue_body


def _make_payload():
    return {
        "action": "closed_check",
        "issue": {
            "number": 10,
            "body": make_private_issue_body(),
            "state": "closed",
        },
        "sender": {"login": "github-actions[bot]", "type": "Bot"},
    }


def _setup_mocks(config, mock_client, private_labels: list[str], state: str = "closed"):
    mock_priv_repo = MagicMock()
    mock_priv_issue = MagicMock()
    mock_priv_issue.number = 10
    mock_priv_issue.state = state
    label_mocks = []
    for name in private_labels:
        lbl = MagicMock()
        lbl.name = name
        label_mocks.append(lbl)
    mock_priv_issue.get_labels.return_value = label_mocks
    mock_priv_repo.get_issue.return_value = mock_priv_issue

    mock_client.get_repo.return_value = mock_priv_repo
    return mock_priv_issue


def test_reopened_during_grace_period_bails(config, mock_client):
    payload = _make_payload()
    priv_issue = _setup_mocks(config, mock_client, [], state="open")

    handle(mock_client, config, payload)

    priv_issue.add_to_labels.assert_not_called()
    priv_issue.create_comment.assert_not_called()


def test_has_resolution_label_does_nothing(config, mock_client):
    payload = _make_payload()
    priv_issue = _setup_mocks(
        config, mock_client, ["resolution:completed"]
    )

    handle(mock_client, config, payload)

    priv_issue.add_to_labels.assert_not_called()
    priv_issue.create_comment.assert_not_called()


def test_no_resolution_label_nudges(config, mock_client):
    payload = _make_payload()
    priv_issue = _setup_mocks(config, mock_client, ["unrelated"])

    handle(mock_client, config, payload)

    priv_issue.add_to_labels.assert_called_once_with("resolution:none")
    priv_issue.create_comment.assert_called_once()
    msg = priv_issue.create_comment.call_args[0][0]
    assert "No resolution posted" in msg
    assert "/anon" in msg


def test_not_mirrored_skips(config, mock_client):
    payload = {
        "action": "closed_check",
        "issue": {
            "number": 10,
            "body": "A regular issue with no markers",
            "state": "closed",
        },
    }

    handle(mock_client, config, payload)
    mock_client.get_repo.assert_not_called()


def test_already_has_resolution_none_skips_adding(config, mock_client):
    payload = _make_payload()
    priv_issue = _setup_mocks(
        config, mock_client, ["resolution:none"]
    )

    handle(mock_client, config, payload)

    # Should still post nudge comment but not add the label again
    priv_issue.add_to_labels.assert_not_called()
    priv_issue.create_comment.assert_called_once()


def test_multiple_resolution_labels_nudges(config, mock_client):
    payload = _make_payload()
    priv_issue = _setup_mocks(
        config, mock_client, ["resolution:completed", "resolution:not-planned"]
    )

    handle(mock_client, config, payload)

    # >1 resolution labels means no single resolution; nudge with different message
    priv_issue.add_to_labels.assert_called_once_with("resolution:none")
    priv_issue.create_comment.assert_called_once()
    msg = priv_issue.create_comment.call_args[0][0]
    assert "Multiple resolution labels" in msg
    assert "/anon" in msg
