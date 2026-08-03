"""Contract tests for the shared area-assignment helper."""

from __future__ import annotations

from unittest.mock import MagicMock

from lyrebird.handlers._assign_area_owner import (
    assign_area_owner,
    assign_area_owner_by_number,
)


def _priv_issue(number: int = 10, state: str = "open", assignees=None):
    issue = MagicMock()
    issue.number = number
    issue.state = state
    issue.assignees = assignees if assignees is not None else []
    return issue


def test_assigns_owner_to_open_unassigned_issue(config):
    priv_issue = _priv_issue()

    assert assign_area_owner(config, priv_issue, ["Lattices"]) == "assaferan"
    priv_issue.add_to_assignees.assert_called_once_with("assaferan")


def test_unmapped_label_skips_repository_fetch(config, mock_client):
    assert assign_area_owner_by_number(mock_client, config, 10, ["impact:high"]) is None
    mock_client.get_repo.assert_not_called()


def test_closed_issue_is_not_assigned(config):
    priv_issue = _priv_issue(state="closed")

    assert assign_area_owner(config, priv_issue, ["Lattices"]) is None
    priv_issue.add_to_assignees.assert_not_called()


def test_existing_assignee_is_not_replaced(config):
    priv_issue = _priv_issue(assignees=[MagicMock()])

    assert assign_area_owner(config, priv_issue, ["Lattices"]) is None
    priv_issue.add_to_assignees.assert_not_called()


def test_refetch_failure_is_logged_and_swallowed(config, mock_client, caplog):
    mock_priv_repo = MagicMock()
    mock_priv_repo.get_issue.side_effect = RuntimeError("502 Bad Gateway")
    mock_client.get_repo.return_value = mock_priv_repo

    assert assign_area_owner_by_number(mock_client, config, 10, ["Lattices"]) is None
    assert "Could not fetch private #10" in caplog.text
