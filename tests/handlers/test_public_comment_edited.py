"""Tests for public_comment_edited handler."""

from __future__ import annotations

from unittest.mock import MagicMock

from lyrebird.handlers.public_comment_edited import handle
from tests.conftest import make_comment_payload, make_mock_comment, make_mock_issue


def test_updates_existing_mirrored_comment(config, mock_client):
    payload = make_comment_payload(
        comment_id=999,
        body="Updated comment",
        user_login="commenter",
    )

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue_obj = make_mock_issue(number=42)

    mapping_comment = MagicMock()
    mapping_comment.body = (
        "<!-- mapping: public_issue_node_id=I_kwDOTest private_issue_number=10 -->"
    )
    mock_pub_issue_obj.get_comments.return_value = [mapping_comment]

    # Existing mirrored comment
    mirrored = make_mock_comment(body="old\n<!-- public_comment_id: 999 -->")
    mock_private = make_mock_issue(number=10)
    mock_private.get_comments.return_value = [mirrored]

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    mock_pub_repo.get_issue.return_value = mock_pub_issue_obj
    mock_priv_repo.get_issue.return_value = mock_private

    handle(mock_client, config, payload)

    mirrored.edit.assert_called_once()
    new_body = mirrored.edit.call_args.kwargs["body"]
    assert "Updated comment" in new_body


def test_creates_if_mirrored_not_found(config, mock_client):
    payload = make_comment_payload(
        comment_id=999,
        body="Updated comment",
    )

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue_obj = make_mock_issue(number=42)

    mapping_comment = MagicMock()
    mapping_comment.body = (
        "<!-- mapping: public_issue_node_id=I_kwDOTest private_issue_number=10 -->"
    )
    mock_pub_issue_obj.get_comments.return_value = [mapping_comment]

    mock_private = make_mock_issue(number=10)
    mock_private.get_comments.return_value = []  # No mirrored comment

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    mock_pub_repo.get_issue.return_value = mock_pub_issue_obj
    mock_priv_repo.get_issue.return_value = mock_private

    handle(mock_client, config, payload)

    mock_private.create_comment.assert_called_once()
