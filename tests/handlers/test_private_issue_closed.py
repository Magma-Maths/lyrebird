"""Tests for private_issue_closed handler."""

from __future__ import annotations

from unittest.mock import MagicMock

from lyrebird.handlers.private_issue_closed import handle
from tests.conftest import make_private_issue_body


def _make_payload(labels: list[str] | None = None):
    return {
        "action": "closed",
        "issue": {
            "number": 10,
            "body": make_private_issue_body(),
            "state": "closed",
        },
        "sender": {"login": "engineer", "type": "User"},
    }


def _setup_mocks(config, mock_client, private_labels: list[str]):
    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()

    mock_priv_issue = MagicMock()
    mock_priv_issue.number = 10
    mock_priv_issue.state = "closed"
    label_mocks = []
    for name in private_labels:
        lbl = MagicMock()
        lbl.name = name
        label_mocks.append(lbl)
    mock_priv_issue.get_labels.return_value = label_mocks
    mock_priv_repo.get_issue.return_value = mock_priv_issue

    mock_pub_issue = MagicMock()
    mock_pub_issue.state = "open"
    mock_pub_repo.get_issue.return_value = mock_pub_issue

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    return mock_priv_issue, mock_pub_issue, mock_priv_repo


def test_one_resolution_label_closes_public(config, mock_client):
    payload = _make_payload()
    priv_issue, pub_issue, _ = _setup_mocks(
        config, mock_client, ["resolution:completed"]
    )

    handle(mock_client, config, payload)

    # Should post note and close public
    pub_issue.create_comment.assert_called_once()
    note = pub_issue.create_comment.call_args[0][0]
    assert "has been fixed" in note
    pub_issue.edit.assert_called_once()


def test_zero_resolution_labels_closes_public_no_comment(config, mock_client):
    payload = _make_payload()
    priv_issue, pub_issue, _ = _setup_mocks(
        config, mock_client, ["unrelated-label"]
    )

    handle(mock_client, config, payload)

    # Should close public with no comment (delayed handler takes over)
    pub_issue.edit.assert_called_once_with(state="closed")
    pub_issue.create_comment.assert_not_called()
    # Should NOT nudge on private
    priv_issue.add_to_labels.assert_not_called()
    priv_issue.create_comment.assert_not_called()


def test_multiple_resolution_labels_closes_public_no_comment(config, mock_client):
    payload = _make_payload()
    priv_issue, pub_issue, _ = _setup_mocks(
        config, mock_client, ["resolution:completed", "resolution:not-planned"]
    )

    handle(mock_client, config, payload)

    # Should close public with no comment
    pub_issue.edit.assert_called_once_with(state="closed")
    pub_issue.create_comment.assert_not_called()
    priv_issue.add_to_labels.assert_not_called()


def test_not_mirrored_issue_skips(config, mock_client):
    payload = {
        "action": "closed",
        "issue": {
            "number": 10,
            "body": "A regular private issue with no markers",
            "state": "closed",
        },
        "sender": {"login": "engineer", "type": "User"},
    }

    # Should not error — just return
    handle(mock_client, config, payload)


def test_public_already_closed_skips_close(config, mock_client):
    payload = _make_payload()
    priv_issue, pub_issue, _ = _setup_mocks(
        config, mock_client, ["resolution:completed"]
    )
    pub_issue.state = "closed"

    handle(mock_client, config, payload)

    # Should NOT try to close or comment on public
    pub_issue.create_comment.assert_not_called()
    pub_issue.edit.assert_not_called()
