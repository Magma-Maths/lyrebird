"""Tests for private_issue_milestoned handler."""

from __future__ import annotations

from unittest.mock import MagicMock

from lyrebird.handlers.private_issue_milestoned import handle
from tests.conftest import (
    make_mock_issue,
    make_mock_milestone,
    make_private_issue_body,
)


def _make_private_milestone_payload(
    action: str = "milestoned",
    issue_number: int = 100,
    milestone_title: str = "v1.0",
) -> dict:
    return {
        "action": action,
        "issue": {
            "number": issue_number,
            "body": make_private_issue_body(),
            "node_id": "I_privNode",
            "title": "[public #42] Bug report",
            "state": "open",
            "html_url": f"https://github.com/testorg/private-repo/issues/{issue_number}",
            "user": {"login": "dev"},
        },
        "milestone": {
            "title": milestone_title,
            "description": "Release milestone",
            "due_on": "2026-06-01T00:00:00Z",
            "state": "open",
            "number": 1,
        },
        "sender": {"login": "dev", "type": "User"},
    }


class TestMilestoned:
    def test_creates_milestone_on_public_repo_and_assigns(self, config, mock_client):
        payload = _make_private_milestone_payload()
        mock_pub_repo = MagicMock()
        mock_priv_repo = MagicMock()
        mock_pub_issue = make_mock_issue(number=42)
        mock_pub_repo.get_milestones.return_value = []
        created_ms = make_mock_milestone(title="v1.0")
        mock_pub_repo.create_milestone.return_value = created_ms

        def get_repo(name):
            if name == config.public_repo:
                return mock_pub_repo
            return mock_priv_repo

        mock_client.get_repo.side_effect = get_repo
        mock_pub_repo.get_issue.return_value = mock_pub_issue

        handle(mock_client, config, payload)

        mock_pub_repo.create_milestone.assert_called_once()
        mock_pub_issue.edit.assert_called_once()
        assert mock_pub_issue.edit.call_args.kwargs["milestone"] is created_ms

    def test_reuses_existing_milestone_on_public(self, config, mock_client):
        payload = _make_private_milestone_payload()
        mock_pub_repo = MagicMock()
        mock_priv_repo = MagicMock()
        mock_pub_issue = make_mock_issue(number=42)
        existing_ms = make_mock_milestone(title="v1.0")
        mock_pub_repo.get_milestones.return_value = [existing_ms]

        def get_repo(name):
            if name == config.public_repo:
                return mock_pub_repo
            return mock_priv_repo

        mock_client.get_repo.side_effect = get_repo
        mock_pub_repo.get_issue.return_value = mock_pub_issue

        handle(mock_client, config, payload)

        mock_pub_repo.create_milestone.assert_not_called()
        assert mock_pub_issue.edit.call_args.kwargs["milestone"] is existing_ms

    def test_no_op_when_no_body_markers(self, config, mock_client):
        payload = _make_private_milestone_payload()
        payload["issue"]["body"] = "Just a regular private issue"
        mock_pub_repo = MagicMock()
        mock_priv_repo = MagicMock()

        def get_repo(name):
            if name == config.public_repo:
                return mock_pub_repo
            return mock_priv_repo

        mock_client.get_repo.side_effect = get_repo

        handle(mock_client, config, payload)

        mock_pub_repo.get_issue.assert_not_called()
        mock_pub_repo.create_milestone.assert_not_called()


class TestDemilestoned:
    def test_removes_milestone_from_public(self, config, mock_client):
        payload = _make_private_milestone_payload(action="demilestoned")
        mock_pub_repo = MagicMock()
        mock_priv_repo = MagicMock()
        mock_pub_issue = make_mock_issue(number=42)

        def get_repo(name):
            if name == config.public_repo:
                return mock_pub_repo
            return mock_priv_repo

        mock_client.get_repo.side_effect = get_repo
        mock_pub_repo.get_issue.return_value = mock_pub_issue

        handle(mock_client, config, payload)

        mock_pub_issue.edit.assert_called_once_with(milestone=None)
