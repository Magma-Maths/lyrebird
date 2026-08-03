"""Contract tests for the shared area-assignment helper."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

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


def _exploding_config(exc: Exception):
    """Config stand-in whose area lookup raises."""
    broken = MagicMock()
    broken.assignee_for_area.side_effect = exc
    broken.private_repo = "testorg/private-repo"
    return broken


def test_area_lookup_failure_is_contained(caplog):
    priv_issue = _priv_issue()

    result = assign_area_owner(
        _exploding_config(RuntimeError("bad map")), priv_issue, ["Lattices"]
    )

    assert result is None
    priv_issue.add_to_assignees.assert_not_called()
    assert "Failed to assign" in caplog.text


def test_area_lookup_failure_is_contained_by_number(mock_client, caplog):
    result = assign_area_owner_by_number(
        mock_client, _exploding_config(RuntimeError("bad map")), 10, ["Lattices"]
    )

    assert result is None
    mock_client.get_repo.assert_not_called()
    assert "Could not fetch private #10" in caplog.text


def test_failing_number_read_in_error_path_is_contained(config, caplog):
    # A transient API error on one lazily completed attribute makes every other
    # attribute fail the same way, including the one the error log wants.
    priv_issue = MagicMock()
    type(priv_issue).state = PropertyMock(side_effect=RuntimeError("502 Bad Gateway"))
    type(priv_issue).number = PropertyMock(side_effect=RuntimeError("502 Bad Gateway"))

    assert assign_area_owner(config, priv_issue, ["Lattices"]) is None
    assert "Failed to assign 'assaferan' to private #?" in caplog.text


def test_one_shot_label_iterable_is_assigned(config, mock_client):
    priv_issue = _priv_issue()
    mock_priv_repo = MagicMock()
    mock_priv_repo.get_issue.return_value = priv_issue
    mock_client.get_repo.return_value = mock_priv_repo

    label_names = (name for name in ["Lattices"])

    assert assign_area_owner_by_number(mock_client, config, 10, label_names) == "assaferan"
    priv_issue.add_to_assignees.assert_called_once_with("assaferan")
