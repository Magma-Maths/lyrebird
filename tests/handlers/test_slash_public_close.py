"""Tests for slash_public_close handler."""

from __future__ import annotations

from unittest.mock import MagicMock

from lyrebird.handlers.slash_public_close import handle
from tests.conftest import make_private_issue_body


def _make_payload(body: str = "/public-close completed This has been fixed"):
    return {
        "issue": {
            "number": 10,
            "body": make_private_issue_body(),
            "state": "open",
        },
        "comment": {
            "id": 501,
            "body": body,
            "html_url": "https://github.com/testorg/private-repo/issues/10#issuecomment-501",
            "user": {"login": "engineer"},
        },
        "sender": {"login": "engineer", "type": "User"},
    }


def _setup_mocks(config, mock_client):
    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()

    mock_priv_issue = MagicMock()
    mock_priv_issue.state = "open"
    lbl = MagicMock()
    lbl.name = "some-label"
    mock_priv_issue.get_labels.return_value = [lbl]
    mock_priv_repo.get_issue.return_value = mock_priv_issue

    mock_pub_issue = MagicMock()
    mock_pub_issue.state = "open"
    mock_pub_comment = MagicMock()
    mock_pub_comment.html_url = "https://github.com/testorg/public-repo/issues/42#issuecomment-700"
    mock_pub_issue.create_comment.return_value = mock_pub_comment
    mock_pub_repo.get_issue.return_value = mock_pub_issue

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    return mock_priv_issue, mock_pub_issue, mock_priv_repo, mock_pub_repo


def test_full_close_flow(config, mock_client):
    payload = _make_payload("/public-close completed This has been fixed")
    priv_issue, pub_issue, _, _ = _setup_mocks(config, mock_client)

    handle(mock_client, config, payload)

    # Should add resolution label
    priv_issue.add_to_labels.assert_called_with("external:completed")
    # Should close private
    priv_issue.edit.assert_any_call(state="closed")
    # Should post note on public
    pub_issue.create_comment.assert_called_once_with("**@engineer**:\n\nThis has been fixed")
    # Should close public
    pub_issue.edit.assert_called_once_with(state="closed", state_reason="completed")


def test_full_close_flow_anonymous(config, mock_client):
    payload = _make_payload("/public-close completed --anon This has been fixed")
    priv_issue, pub_issue, _, _ = _setup_mocks(config, mock_client)

    handle(mock_client, config, payload)

    pub_issue.create_comment.assert_called_once_with("This has been fixed")


def test_invalid_resolution(config, mock_client):
    payload = _make_payload("/public-close invalid-key some note")
    priv_issue, pub_issue, _, _ = _setup_mocks(config, mock_client)

    handle(mock_client, config, payload)

    # Should post error, not close anything
    priv_issue.create_comment.assert_called_once()
    msg = priv_issue.create_comment.call_args[0][0]
    assert "Unknown resolution" in msg
    pub_issue.create_comment.assert_not_called()


def test_default_note_when_no_custom_note(config, mock_client):
    payload = _make_payload("/public-close completed")
    priv_issue, pub_issue, _, _ = _setup_mocks(config, mock_client)

    handle(mock_client, config, payload)

    # Should use default note from config without attribution
    pub_issue.create_comment.assert_called_once()
    note = pub_issue.create_comment.call_args[0][0]
    assert "has been fixed" in note
    assert "**@engineer**:" not in note


def test_normalizes_resolution_labels(config, mock_client):
    """If issue has a different resolution label, replace it."""
    payload = _make_payload("/public-close not-planned Not planned")
    priv_issue, pub_issue, _, _ = _setup_mocks(config, mock_client)

    # Issue already has external:completed
    lbl = MagicMock()
    lbl.name = "external:completed"
    priv_issue.get_labels.return_value = [lbl]

    handle(mock_client, config, payload)

    # Should remove old resolution label and add new one
    priv_issue.remove_from_labels.assert_called_with("external:completed")
    priv_issue.add_to_labels.assert_called_with("external:not-planned")
