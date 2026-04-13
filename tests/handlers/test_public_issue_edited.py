"""Tests for public_issue_edited handler."""

from __future__ import annotations

from unittest.mock import MagicMock

from lyrebird.handlers.public_issue_edited import handle
from tests.conftest import make_mock_issue, make_private_issue_body, make_public_issue_payload


def test_updates_private_title_and_body(config, mock_client):
    public_issue = make_public_issue_payload(title="Updated title", body="Updated body")
    payload = {
        "issue": public_issue,
        "sender": {"login": "reporter", "type": "User"},
    }

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue_obj = make_mock_issue(number=42)

    # Mapping comment exists
    mapping_comment = MagicMock()
    mapping_comment.body = (
        "<!-- mapping: public_issue_node_id=I_kwDOTest private_issue_number=10 -->"
    )
    mock_pub_issue_obj.get_comments.return_value = [mapping_comment]

    mock_private = make_mock_issue(number=10)
    mock_private.body = make_private_issue_body()

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    mock_pub_repo.get_issue.return_value = mock_pub_issue_obj
    mock_priv_repo.get_issue.return_value = mock_private

    handle(mock_client, config, payload)

    mock_private.edit.assert_called_once()
    edit_kwargs = mock_private.edit.call_args.kwargs
    assert "[public #42] Updated title" == edit_kwargs["title"]
    assert "Updated body" in edit_kwargs["body"]


def test_no_mapping_bootstraps_then_edits(config, mock_client):
    """When no mapping exists, bootstrap the private mirror from the edited payload."""
    public_issue = make_public_issue_payload(title="Edited title", body="Edited body")
    payload = {"issue": public_issue}

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue_obj = make_mock_issue(number=42)
    mock_pub_issue_obj.get_comments.return_value = []
    mock_priv_repo.get_issues.return_value = []

    # Bootstrap creates this private issue
    mock_priv_issue = MagicMock()
    mock_priv_issue.number = 99
    mock_priv_issue.body = make_private_issue_body(
        public_number=42, public_body="Edited body"
    )
    mock_priv_repo.create_issue.return_value = mock_priv_issue

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    mock_pub_repo.get_issue.return_value = mock_pub_issue_obj

    handle(mock_client, config, payload)

    # Private issue bootstrapped with the edited title/body
    mock_priv_repo.create_issue.assert_called_once()
    create_kwargs = mock_priv_repo.create_issue.call_args.kwargs
    assert "[public #42] Edited title" == create_kwargs["title"]
    assert "Edited body" in create_kwargs["body"]
