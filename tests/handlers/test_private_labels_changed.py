"""Tests for private_labels_changed handler."""

from __future__ import annotations

from unittest.mock import MagicMock

from lyrebird.handlers.private_labels_changed import handle
from tests.conftest import make_private_issue_body


def test_mirrors_label_to_public_if_exists(config, mock_client):
    payload = {
        "action": "labeled",
        "issue": {
            "number": 10,
            "body": make_private_issue_body(),
            "state": "open",
        },
        "label": {"name": "bug", "color": "d73a4a"},
        "sender": {"login": "engineer", "type": "User"},
    }

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue = MagicMock()
    mock_pub_repo.get_issue.return_value = mock_pub_issue
    # Label exists on public repo
    mock_pub_repo.get_label.return_value = MagicMock()

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo

    handle(mock_client, config, payload)

    mock_pub_issue.add_to_labels.assert_called_with("bug")


def test_skips_label_not_on_public(config, mock_client):
    payload = {
        "action": "labeled",
        "issue": {
            "number": 10,
            "body": make_private_issue_body(),
            "state": "open",
        },
        "label": {"name": "internal-only"},
        "sender": {"login": "engineer", "type": "User"},
    }

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    # Label does NOT exist on public
    mock_pub_repo.get_label.side_effect = Exception("not found")

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo

    handle(mock_client, config, payload)

    # Should not try to get public issue
    mock_pub_repo.get_issue.assert_not_called()


def test_not_mirrored_skips(config, mock_client):
    payload = {
        "action": "labeled",
        "issue": {
            "number": 10,
            "body": "regular issue no markers",
            "state": "open",
        },
        "label": {"name": "bug"},
        "sender": {"login": "engineer", "type": "User"},
    }

    handle(mock_client, config, payload)
    # No error, just returns
