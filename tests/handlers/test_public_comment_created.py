"""Tests for public_comment_created handler."""

from __future__ import annotations

from unittest.mock import MagicMock

from lyrebird.handlers.public_comment_created import handle
from tests.conftest import make_comment_payload, make_mock_issue


def test_mirrors_comment_to_private(config, mock_client):
    payload = make_comment_payload(
        comment_id=999,
        body="I can reproduce this",
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

    mock_private = make_mock_issue(number=10)

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    mock_pub_repo.get_issue.return_value = mock_pub_issue_obj
    mock_priv_repo.get_issue.return_value = mock_private

    handle(mock_client, config, payload)

    mock_private.create_comment.assert_called_once()
    comment_body = mock_private.create_comment.call_args[0][0]
    assert "From @commenter" in comment_body
    assert "I can reproduce this" in comment_body
    assert "public_comment_id: 999" in comment_body


def test_skips_bot_authored_comment(config, mock_client):
    """Bot-authored comments must not be mirrored (defense-in-depth)."""
    payload = make_comment_payload(
        comment_id=888,
        body="This has been fixed.",
        user_login="lyrebird[bot]",
    )

    handle(mock_client, config, payload)

    # Should return early — no repo lookups at all
    mock_client.get_repo.assert_not_called()
