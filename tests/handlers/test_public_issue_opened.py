"""Tests for public_issue_opened handler."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

from lyrebird.handlers.public_issue_opened import handle
from tests.conftest import make_mock_issue, make_public_issue_payload


def test_creates_private_issue_and_mapping_comment(config, mock_client):
    """Normal flow: create private issue, then mapping comment on public."""
    public_issue = make_public_issue_payload()
    payload = {
        "issue": public_issue,
        "sender": {"login": "reporter", "type": "User"},
    }

    # Mock: resolve_mapping returns None (no existing mapping)
    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue_obj = make_mock_issue(number=42)
    mock_pub_issue_obj.get_comments.return_value = []  # No mapping comment

    mock_priv_issue = MagicMock()
    mock_priv_issue.number = 10
    mock_priv_repo.create_issue.return_value = mock_priv_issue

    # get_issues returns empty (no fallback match)
    mock_priv_repo.get_issues.return_value = []

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    mock_pub_repo.get_issue.return_value = mock_pub_issue_obj

    handle(mock_client, config, payload)

    # Should create private issue
    mock_priv_repo.create_issue.assert_called_once()
    create_args = mock_priv_repo.create_issue.call_args
    assert "[public #42]" in create_args.kwargs["title"]
    assert "Something is broken" in create_args.kwargs["body"]

    # Should post mapping comment on public issue
    mock_pub_issue_obj.create_comment.assert_called_once()
    mapping_text = mock_pub_issue_obj.create_comment.call_args[0][0]
    assert "private_issue_number=10" in mapping_text


def test_idempotent_when_mapping_exists(config, mock_client):
    """If mapping already exists, do not create another private issue."""
    public_issue = make_public_issue_payload()
    payload = {
        "issue": public_issue,
        "sender": {"login": "reporter", "type": "User"},
    }

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue_obj = make_mock_issue(number=42)

    # Mapping comment already exists
    mapping_comment = MagicMock()
    mapping_comment.body = (
        "Internal tracking: testorg/private-repo#10\n\n"
        "<!-- mapping: public_issue_node_id=I_kwDOTest private_issue_number=10 -->"
    )
    mock_pub_issue_obj.get_comments.return_value = [mapping_comment]

    mock_existing_private = make_mock_issue(number=10)

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    mock_pub_repo.get_issue.return_value = mock_pub_issue_obj
    mock_priv_repo.get_issue.return_value = mock_existing_private

    handle(mock_client, config, payload)

    # Should NOT create a new private issue
    mock_priv_repo.create_issue.assert_not_called()


def test_self_heals_missing_mapping_comment(config, mock_client):
    """If mapping comment is gone but private issue exists, self-heal."""
    public_issue = make_public_issue_payload()
    payload = {
        "issue": public_issue,
        "sender": {"login": "reporter", "type": "User"},
    }

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue_obj = make_mock_issue(number=42)
    mock_pub_issue_obj.get_comments.return_value = []  # No mapping comment

    # Fallback: private issue has body markers
    from tests.conftest import make_private_issue_body

    mock_private = make_mock_issue(number=10)
    mock_private.body = make_private_issue_body(
        public_number=42, public_node_id="I_kwDOTest"
    )
    mock_priv_repo.get_issues.return_value = [mock_private]

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    mock_pub_repo.get_issue.return_value = mock_pub_issue_obj
    mock_priv_repo.get_issue.return_value = mock_private

    handle(mock_client, config, payload)

    # Should NOT create a new private issue
    mock_priv_repo.create_issue.assert_not_called()
    # Should self-heal: post mapping comment
    mock_pub_issue_obj.create_comment.assert_called_once()
    healed_text = mock_pub_issue_obj.create_comment.call_args[0][0]
    assert "private_issue_number=10" in healed_text
