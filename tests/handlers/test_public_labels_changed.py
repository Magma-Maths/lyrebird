"""Tests for public_labels_changed handler."""

from __future__ import annotations

from unittest.mock import MagicMock

from lyrebird.handlers.public_labels_changed import handle
from tests.conftest import make_mock_issue, make_public_issue_payload


def test_adds_label_to_private(config, mock_client):
    public_issue = make_public_issue_payload()
    payload = {
        "action": "labeled",
        "issue": public_issue,
        "label": {"name": "bug", "color": "d73a4a", "description": ""},
        "sender": {"login": "triager", "type": "User"},
    }

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue_obj = make_mock_issue(number=42)

    mapping_comment = MagicMock()
    mapping_comment.body = (
        "<!-- mapping: public_issue_node_id=I_kwDOTest private_issue_number=10 -->"
    )
    mock_pub_issue_obj.get_comments.return_value = [mapping_comment]

    mock_private = make_mock_issue(number=10)
    # Need the repository attribute for _ensure_label
    mock_priv_repo_inner = MagicMock()
    type(mock_private).repository = property(lambda self: mock_priv_repo_inner)

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    mock_pub_repo.get_issue.return_value = mock_pub_issue_obj
    mock_priv_repo.get_issue.return_value = mock_private

    handle(mock_client, config, payload)

    mock_private.add_to_labels.assert_called_with("bug")


def test_removes_label_from_private(config, mock_client):
    public_issue = make_public_issue_payload()
    payload = {
        "action": "unlabeled",
        "issue": public_issue,
        "label": {"name": "bug", "color": "d73a4a"},
        "sender": {"login": "triager", "type": "User"},
    }

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue_obj = make_mock_issue(number=42)

    mapping_comment = MagicMock()
    mapping_comment.body = (
        "<!-- mapping: public_issue_node_id=I_kwDOTest private_issue_number=10 -->"
    )
    mock_pub_issue_obj.get_comments.return_value = [mapping_comment]

    mock_private = make_mock_issue(number=10)

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    mock_pub_repo.get_issue.return_value = mock_pub_issue_obj
    mock_priv_repo.get_issue.return_value = mock_private

    handle(mock_client, config, payload)

    mock_private.remove_from_labels.assert_called_with("bug")
