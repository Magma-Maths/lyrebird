"""Tests for public_issue_state handler (close/reopen)."""

from __future__ import annotations

from unittest.mock import MagicMock, call

from lyrebird.handlers.public_issue_state import handle
from tests.conftest import make_mock_issue, make_public_issue_payload


def _setup_mocks(config, mock_client):
    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue_obj = make_mock_issue(number=42)

    mapping_comment = MagicMock()
    mapping_comment.body = (
        "<!-- mapping: public_issue_node_id=I_kwDOTest private_issue_number=10 -->"
    )
    mock_pub_issue_obj.get_comments.return_value = [mapping_comment]

    mock_private = make_mock_issue(number=10)
    mock_priv_repo_inner = MagicMock()
    type(mock_private).repository = property(lambda self: mock_priv_repo_inner)

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    mock_pub_repo.get_issue.return_value = mock_pub_issue_obj
    mock_priv_repo.get_issue.return_value = mock_private

    return mock_private, mock_priv_repo_inner


def test_close_adds_label(config, mock_client):
    public_issue = make_public_issue_payload(user_login="reporter")
    payload = {
        "action": "closed",
        "issue": public_issue,
        "sender": {"login": "closer", "type": "User"},
    }

    mock_private, _ = _setup_mocks(config, mock_client)
    handle(mock_client, config, payload)

    mock_private.add_to_labels.assert_any_call("public:closed")
    mock_private.create_comment.assert_called_once()
    audit = mock_private.create_comment.call_args[0][0]
    assert "closed by @closer" in audit


def test_close_by_reporter_adds_both_labels(config, mock_client):
    public_issue = make_public_issue_payload(user_login="reporter")
    payload = {
        "action": "closed",
        "issue": public_issue,
        "sender": {"login": "reporter", "type": "User"},
    }

    mock_private, _ = _setup_mocks(config, mock_client)
    handle(mock_client, config, payload)

    mock_private.add_to_labels.assert_any_call("public:closed")
    mock_private.add_to_labels.assert_any_call("public:closed-by-reporter")
    audit = mock_private.create_comment.call_args[0][0]
    assert "original reporter" in audit


def test_reopen_removes_labels(config, mock_client):
    public_issue = make_public_issue_payload(user_login="reporter")
    payload = {
        "action": "reopened",
        "issue": public_issue,
        "sender": {"login": "reporter", "type": "User"},
    }

    mock_private, _ = _setup_mocks(config, mock_client)
    handle(mock_client, config, payload)

    mock_private.remove_from_labels.assert_any_call("public:closed")
    mock_private.remove_from_labels.assert_any_call("public:closed-by-reporter")
    audit = mock_private.create_comment.call_args[0][0]
    assert "reopened" in audit
