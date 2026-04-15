"""Tests for public_issue_milestoned handler."""

from __future__ import annotations

from unittest.mock import MagicMock

from lyrebird.handlers.public_issue_milestoned import handle
from tests.conftest import (
    make_mock_issue,
    make_mock_milestone,
    make_private_issue_body,
    make_public_issue_payload,
    setup_missing_mapping,
)


def _make_milestone_payload(
    action: str = "milestoned",
    issue_number: int = 42,
    issue_node_id: str = "I_kwDOTest",
    milestone_title: str = "v1.0",
) -> dict:
    milestone = {
        "title": milestone_title,
        "description": "Release milestone",
        "due_on": "2026-06-01T00:00:00Z",
        "state": "open",
        "number": 1,
    }
    # Real GitHub webhooks populate milestone in BOTH places for milestoned events.
    # For demilestoned, issue.milestone is None but the top-level milestone is the
    # just-removed one.
    issue_milestone = milestone if action == "milestoned" else None
    return {
        "action": action,
        "issue": make_public_issue_payload(
            number=issue_number,
            node_id=issue_node_id,
            milestone=issue_milestone,
        ),
        "milestone": milestone,
        "sender": {"login": "reporter", "type": "User"},
    }


class TestMilestoned:
    def test_creates_milestone_if_missing_and_assigns(self, config, mock_client):
        payload = _make_milestone_payload()
        mock_pub_repo = MagicMock()
        mock_priv_repo = MagicMock()
        mock_pub_issue = make_mock_issue(number=42)
        mock_pub_issue.get_comments.return_value = []
        mock_priv_issue = make_mock_issue(number=100)
        mock_priv_issue.body = make_private_issue_body()
        mock_priv_repo.get_issues.return_value = [mock_priv_issue]
        mock_priv_repo.get_milestones.return_value = []
        created_ms = make_mock_milestone(title="v1.0")
        mock_priv_repo.create_milestone.return_value = created_ms

        def get_repo(name):
            if name == config.public_repo:
                return mock_pub_repo
            return mock_priv_repo

        mock_client.get_repo.side_effect = get_repo
        mock_pub_repo.get_issue.return_value = mock_pub_issue
        mock_priv_repo.get_issue.return_value = mock_priv_issue

        handle(mock_client, config, payload)

        mock_priv_repo.create_milestone.assert_called_once()
        mock_priv_issue.edit.assert_called_once()
        assert mock_priv_issue.edit.call_args.kwargs["milestone"] is created_ms

    def test_reuses_existing_milestone(self, config, mock_client):
        payload = _make_milestone_payload()
        mock_pub_repo = MagicMock()
        mock_priv_repo = MagicMock()
        mock_pub_issue = make_mock_issue(number=42)
        mapping_comment = MagicMock()
        mapping_comment.body = "<!-- mapping: public_issue_node_id=I_kwDOTest private_issue_number=100 -->"
        mock_pub_issue.get_comments.return_value = [mapping_comment]
        mock_priv_issue = make_mock_issue(number=100)
        existing_ms = make_mock_milestone(title="v1.0")
        mock_priv_repo.get_milestones.return_value = [existing_ms]

        def get_repo(name):
            if name == config.public_repo:
                return mock_pub_repo
            return mock_priv_repo

        mock_client.get_repo.side_effect = get_repo
        mock_pub_repo.get_issue.return_value = mock_pub_issue
        mock_priv_repo.get_issue.return_value = mock_priv_issue

        handle(mock_client, config, payload)

        mock_priv_repo.create_milestone.assert_not_called()
        mock_priv_issue.edit.assert_called_once()
        assert mock_priv_issue.edit.call_args.kwargs["milestone"] is existing_ms

    def test_bootstraps_when_no_mapping(self, config, mock_client):
        """When `milestoned` arrives before `opened` ran, bootstrap the mirror."""
        payload = _make_milestone_payload()
        _, mock_priv_repo, _, mock_priv_issue = setup_missing_mapping(config, mock_client)

        created_ms = MagicMock()
        created_ms.title = "v1.0"
        mock_priv_repo.create_milestone.return_value = created_ms

        handle(mock_client, config, payload)

        mock_priv_repo.create_issue.assert_called_once()
        # Bootstrap sets the milestone once via .edit(milestone=...); handler
        # short-circuits so there should be exactly one milestone edit.
        milestone_edits = [
            c for c in mock_priv_issue.edit.call_args_list
            if "milestone" in c.kwargs
        ]
        assert len(milestone_edits) == 1


class TestDemilestonedBootstrap:
    def test_demilestoned_bootstraps_then_clears(self, config, mock_client):
        """When `demilestoned` arrives before `opened`, the handler must explicitly
        clear the milestone on the newly bootstrapped mirror — bootstrap sees
        issue.milestone=None and skips assignment, so there's nothing to clear
        (harmless), but we still fall through for symmetry with `unlabeled`/`untyped`."""
        payload = _make_milestone_payload(action="demilestoned")
        _, mock_priv_repo, _, mock_priv_issue = setup_missing_mapping(config, mock_client)

        handle(mock_client, config, payload)

        mock_priv_repo.create_issue.assert_called_once()
        # Bootstrap skipped milestone (issue.milestone=None). Handler falls
        # through and explicitly sets milestone=None on the mirror.
        milestone_edits = [
            c for c in mock_priv_issue.edit.call_args_list
            if "milestone" in c.kwargs
        ]
        assert len(milestone_edits) == 1
        assert milestone_edits[0].kwargs["milestone"] is None


class TestDemilestoned:
    def test_removes_milestone_from_private(self, config, mock_client):
        payload = _make_milestone_payload(action="demilestoned")
        mock_pub_repo = MagicMock()
        mock_priv_repo = MagicMock()
        mock_pub_issue = make_mock_issue(number=42)
        mapping_comment = MagicMock()
        mapping_comment.body = "<!-- mapping: public_issue_node_id=I_kwDOTest private_issue_number=100 -->"
        mock_pub_issue.get_comments.return_value = [mapping_comment]
        mock_priv_issue = make_mock_issue(number=100)

        def get_repo(name):
            if name == config.public_repo:
                return mock_pub_repo
            return mock_priv_repo

        mock_client.get_repo.side_effect = get_repo
        mock_pub_repo.get_issue.return_value = mock_pub_issue
        mock_priv_repo.get_issue.return_value = mock_priv_issue

        handle(mock_client, config, payload)

        mock_priv_issue.edit.assert_called_once_with(milestone=None)
