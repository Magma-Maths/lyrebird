"""Tests for slash_anon handler."""

from __future__ import annotations

from unittest.mock import MagicMock

from lyrebird.handlers.slash_anon import handle
from tests.conftest import make_private_issue_body


def test_posts_anonymous_message_to_public(config, mock_client):
    payload = {
        "issue": {
            "number": 10,
            "body": make_private_issue_body(),
            "state": "open",
        },
        "comment": {
            "id": 500,
            "body": "/anon We're looking into this.",
            "html_url": "https://github.com/testorg/private-repo/issues/10#issuecomment-500",
            "user": {"login": "engineer"},
        },
        "sender": {"login": "engineer", "type": "User"},
    }

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue = MagicMock()
    mock_pub_comment = MagicMock()
    mock_pub_comment.html_url = "https://github.com/testorg/public-repo/issues/42#issuecomment-600"
    mock_pub_issue.create_comment.return_value = mock_pub_comment
    mock_pub_repo.get_issue.return_value = mock_pub_issue

    mock_priv_issue = MagicMock()
    mock_priv_repo.get_issue.return_value = mock_priv_issue

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo

    handle(mock_client, config, payload)

    mock_pub_issue.create_comment.assert_called_once_with("We're looking into this.")
    mock_priv_issue.create_comment.assert_called_once()
    ack = mock_priv_issue.create_comment.call_args[0][0]
    assert "Posted to public" in ack


def test_no_mapping_posts_error(config, mock_client):
    payload = {
        "issue": {
            "number": 10,
            "body": "Just a regular issue, no markers",
            "state": "open",
        },
        "comment": {
            "id": 500,
            "body": "/anon hello",
            "user": {"login": "engineer"},
        },
        "sender": {"login": "engineer", "type": "User"},
    }

    mock_priv_repo = MagicMock()
    mock_priv_issue = MagicMock()
    mock_priv_repo.get_issue.return_value = mock_priv_issue

    def get_repo(name):
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo

    handle(mock_client, config, payload)

    mock_priv_issue.create_comment.assert_called_once()
    msg = mock_priv_issue.create_comment.call_args[0][0]
    assert "not linked" in msg


def test_closed_issue_adds_custom_label_removes_none(config, mock_client):
    """On a closed issue with resolution:none, /anon removes it and adds resolution:custom."""
    payload = {
        "issue": {
            "number": 10,
            "body": make_private_issue_body(),
            "state": "closed",
        },
        "comment": {
            "id": 500,
            "body": "/anon Custom resolution message.",
            "user": {"login": "engineer"},
        },
        "sender": {"login": "engineer", "type": "User"},
    }

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue = MagicMock()
    mock_pub_comment = MagicMock()
    mock_pub_comment.html_url = "https://github.com/testorg/public-repo/issues/42#issuecomment-700"
    mock_pub_issue.create_comment.return_value = mock_pub_comment
    mock_pub_repo.get_issue.return_value = mock_pub_issue

    mock_priv_issue = MagicMock()
    # Has resolution:none label
    lbl_none = MagicMock()
    lbl_none.name = "resolution:none"
    mock_priv_issue.get_labels.return_value = [lbl_none]
    mock_priv_repo.get_issue.return_value = mock_priv_issue

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo

    handle(mock_client, config, payload)

    # Should remove resolution:none and add resolution:custom
    mock_priv_issue.remove_from_labels.assert_called_once_with("resolution:none")
    mock_priv_issue.add_to_labels.assert_called_once_with("resolution:custom")


def test_closed_issue_with_resolution_label_no_custom(config, mock_client):
    """On a closed issue with an existing resolution label, /anon does not add resolution:custom."""
    payload = {
        "issue": {
            "number": 10,
            "body": make_private_issue_body(),
            "state": "closed",
        },
        "comment": {
            "id": 500,
            "body": "/anon Additional info.",
            "user": {"login": "engineer"},
        },
        "sender": {"login": "engineer", "type": "User"},
    }

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue = MagicMock()
    mock_pub_comment = MagicMock()
    mock_pub_comment.html_url = "https://github.com/testorg/public-repo/issues/42#issuecomment-800"
    mock_pub_issue.create_comment.return_value = mock_pub_comment
    mock_pub_repo.get_issue.return_value = mock_pub_issue

    mock_priv_issue = MagicMock()
    lbl = MagicMock()
    lbl.name = "resolution:completed"
    mock_priv_issue.get_labels.return_value = [lbl]
    mock_priv_repo.get_issue.return_value = mock_priv_issue

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo

    handle(mock_client, config, payload)

    # Should NOT add resolution:custom (already has a resolution label)
    mock_priv_issue.add_to_labels.assert_not_called()
    mock_priv_issue.remove_from_labels.assert_not_called()
