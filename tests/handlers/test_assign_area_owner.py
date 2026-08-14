"""Contract tests for the shared area-assignment helper."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, PropertyMock

from lyrebird.handlers._assign_area_owner import (
    assign_area_owner,
    assign_area_owner_by_number,
)
from tests.conftest import wire_assignee_tracking


def _priv_issue(number: int = 10, state: str = "open", assignees=None):
    issue = MagicMock()
    issue.number = number
    issue.state = state
    issue.assignees = assignees if assignees is not None else []
    return wire_assignee_tracking(issue)


def _named_user(login: str):
    user = MagicMock()
    user.login = login
    return user


def _assignment_event(action: str, assignee: str, assigner: str):
    event = MagicMock()
    event.event = action
    event.assignee = _named_user(assignee)
    event.actor = _named_user(assignee)
    event.assigner = _named_user(assigner)
    return event


def _refresh_with_assignees(issue, *logins: str):
    def _refresh():
        issue.assignees = [_named_user(login) for login in logins]

    return _refresh


def _warnings(caplog):
    return [r for r in caplog.records if r.levelno >= logging.WARNING]


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


def test_silently_dropped_assignment_is_warned(config, caplog):
    # GitHub answers 201 and drops a login with no push access on the repo, so
    # the refreshed issue comes back with its assignee list unchanged.
    priv_issue = _priv_issue()
    priv_issue.add_to_assignees.side_effect = None

    result = assign_area_owner(config, priv_issue, ["Lattices"])

    assert result is None
    assert len(_warnings(caplog)) == 1
    message = _warnings(caplog)[0].getMessage()
    assert "assaferan" in message
    assert "#10" in message


def test_confirmed_assignment_is_not_warned(config, caplog):
    priv_issue = _priv_issue()

    assert assign_area_owner(config, priv_issue, ["Lattices"]) == "assaferan"
    assert _warnings(caplog) == []


def test_lost_assignment_race_yields_to_concurrent_assignee(config):
    priv_issue = _priv_issue()

    def _assign_with_race(*_):
        priv_issue.assignees = [
            _named_user("assaferan"),
            _named_user("concurrent-owner"),
        ]

    def _remove_to_concurrent_owner(*_):
        priv_issue.assignees = [_named_user("concurrent-owner")]

    priv_issue.add_to_assignees.side_effect = _assign_with_race
    priv_issue.get_events.return_value = [
        _assignment_event("assigned", "assaferan", "lyrebird[bot]")
    ]
    priv_issue.update.side_effect = _refresh_with_assignees(
        priv_issue, "assaferan", "concurrent-owner"
    )
    priv_issue.remove_from_assignees.side_effect = _remove_to_concurrent_owner

    assert assign_area_owner(config, priv_issue, ["Lattices"]) is None
    priv_issue.remove_from_assignees.assert_called_once_with("assaferan")


def test_yield_keeps_login_when_co_assignee_vanished_on_refresh(config, caplog):
    priv_issue = _priv_issue()

    def _assign_with_race(*_):
        priv_issue.assignees = [
            _named_user("assaferan"),
            _named_user("concurrent-owner"),
        ]

    priv_issue.add_to_assignees.side_effect = _assign_with_race
    priv_issue.get_events.return_value = [
        _assignment_event("assigned", "assaferan", "lyrebird[bot]")
    ]
    priv_issue.update.side_effect = _refresh_with_assignees(priv_issue, "assaferan")
    caplog.set_level(logging.INFO)

    assert assign_area_owner(config, priv_issue, ["Lattices"]) == "assaferan"
    priv_issue.remove_from_assignees.assert_not_called()
    assert "Assigned 'assaferan' to private #10" in caplog.text


def test_yield_warns_when_refresh_leaves_issue_unassigned(config, caplog):
    priv_issue = _priv_issue()

    def _assign_with_race(*_):
        priv_issue.assignees = [
            _named_user("assaferan"),
            _named_user("concurrent-owner"),
        ]

    priv_issue.add_to_assignees.side_effect = _assign_with_race
    priv_issue.get_events.return_value = [
        _assignment_event("assigned", "assaferan", "lyrebird[bot]")
    ]
    priv_issue.update.side_effect = _refresh_with_assignees(priv_issue)

    assert assign_area_owner(config, priv_issue, ["Lattices"]) is None
    priv_issue.remove_from_assignees.assert_not_called()
    assert "ended unassigned after concurrent yields" in caplog.text


def test_yield_keeps_login_when_refresh_state_is_unreadable(config, caplog):
    priv_issue = _priv_issue()

    def _assign_with_race(*_):
        priv_issue.assignees = [
            _named_user("assaferan"),
            _named_user("concurrent-owner"),
        ]

    def _refresh_with_unreadable_state():
        priv_issue.assignees = None

    priv_issue.add_to_assignees.side_effect = _assign_with_race
    priv_issue.get_events.return_value = [
        _assignment_event("assigned", "assaferan", "lyrebird[bot]")
    ]
    priv_issue.update.side_effect = _refresh_with_unreadable_state

    assert assign_area_owner(config, priv_issue, ["Lattices"]) == "assaferan"
    priv_issue.remove_from_assignees.assert_not_called()
    assert "post-write assignee state could not be verified for private #10" in caplog.text


def test_yield_warns_when_removal_leaves_issue_unassigned(config, caplog):
    priv_issue = _priv_issue()

    def _assign_with_race(*_):
        priv_issue.assignees = [
            _named_user("assaferan"),
            _named_user("concurrent-owner"),
        ]

    def _remove_and_leave_unassigned(*_):
        priv_issue.assignees = []

    priv_issue.add_to_assignees.side_effect = _assign_with_race
    priv_issue.get_events.return_value = [
        _assignment_event("assigned", "assaferan", "lyrebird[bot]")
    ]
    priv_issue.update.side_effect = _refresh_with_assignees(
        priv_issue, "assaferan", "concurrent-owner"
    )
    priv_issue.remove_from_assignees.side_effect = _remove_and_leave_unassigned

    assert assign_area_owner(config, priv_issue, ["Lattices"]) is None
    priv_issue.remove_from_assignees.assert_called_once_with("assaferan")
    assert "ended unassigned after concurrent yields" in caplog.text


def test_yield_warns_when_post_removal_assignee_state_is_unreadable(config, caplog):
    priv_issue = _priv_issue()

    def _assign_with_race(*_):
        priv_issue.assignees = [
            _named_user("assaferan"),
            _named_user("concurrent-owner"),
        ]

    def _remove_with_unreadable_response(*_):
        priv_issue.assignees = None

    priv_issue.add_to_assignees.side_effect = _assign_with_race
    priv_issue.get_events.return_value = [
        _assignment_event("assigned", "assaferan", "lyrebird[bot]")
    ]
    priv_issue.update.side_effect = _refresh_with_assignees(
        priv_issue, "assaferan", "concurrent-owner"
    )
    priv_issue.remove_from_assignees.side_effect = _remove_with_unreadable_response

    assert assign_area_owner(config, priv_issue, ["Lattices"]) is None
    priv_issue.remove_from_assignees.assert_called_once_with("assaferan")
    assert "post-removal assignee state could not be verified for private #10" in caplog.text
    assert "yielded to concurrent assignee" not in caplog.text


def test_unreadable_post_write_state_warns_and_keeps_login(config, caplog):
    priv_issue = _priv_issue()

    def _drop_the_list(*_):
        priv_issue.assignees = None

    priv_issue.add_to_assignees.side_effect = _drop_the_list

    assert assign_area_owner(config, priv_issue, ["Lattices"]) == "assaferan"
    priv_issue.remove_from_assignees.assert_not_called()
    assert "post-write assignee state could not be verified for private #10" in caplog.text


def test_human_provenance_race_keeps_all_assignees(config, caplog):
    """A human assignment during the POST race is never removed."""
    priv_issue = _priv_issue()

    def _assign_with_race(*_):
        priv_issue.assignees = [
            _named_user("assaferan"),
            _named_user("concurrent-owner"),
        ]

    priv_issue.add_to_assignees.side_effect = _assign_with_race
    priv_issue.get_events.return_value = [
        _assignment_event("assigned", "assaferan", "lyrebird[bot]"),
        _assignment_event("unassigned", "assaferan", "engineer"),
        _assignment_event("assigned", "assaferan", "engineer"),
    ]
    assert assign_area_owner(config, priv_issue, ["Lattices"]) is None
    priv_issue.remove_from_assignees.assert_not_called()
    assert len(_warnings(caplog)) == 1
    assert "multiple assignees" in _warnings(caplog)[0].getMessage()
    assert "assaferan, concurrent-owner" in _warnings(caplog)[0].getMessage()


def test_clean_assignment_keeps_owner_without_removal(config):
    priv_issue = _priv_issue()

    assert assign_area_owner(config, priv_issue, ["Lattices"]) == "assaferan"
    priv_issue.remove_from_assignees.assert_not_called()
    priv_issue.get_events.assert_not_called()


def test_unavailable_race_provenance_keeps_all_assignees(config, caplog):
    priv_issue = _priv_issue()

    def _assign_with_race(*_):
        priv_issue.assignees = [
            _named_user("assaferan"),
            _named_user("concurrent-owner"),
        ]

    priv_issue.add_to_assignees.side_effect = _assign_with_race
    priv_issue.get_events.side_effect = RuntimeError("502 Bad Gateway")

    assert assign_area_owner(config, priv_issue, ["Lattices"]) is None
    priv_issue.remove_from_assignees.assert_not_called()
    assert len(_warnings(caplog)) == 1
    assert "may need manual attention" in _warnings(caplog)[0].getMessage()


def test_empty_event_history_keeps_all_assignees(config, caplog):
    priv_issue = _priv_issue()

    def _assign_with_race(*_):
        priv_issue.assignees = [
            _named_user("assaferan"),
            _named_user("concurrent-owner"),
        ]

    priv_issue.add_to_assignees.side_effect = _assign_with_race
    priv_issue.get_events.return_value = []

    assert assign_area_owner(config, priv_issue, ["Lattices"]) is None
    priv_issue.remove_from_assignees.assert_not_called()
    assert len(_warnings(caplog)) == 1
    assert "assaferan" in _warnings(caplog)[0].getMessage()


def test_latest_unassignment_provenance_keeps_all_assignees(config, caplog):
    priv_issue = _priv_issue()

    def _assign_with_race(*_):
        priv_issue.assignees = [
            _named_user("assaferan"),
            _named_user("concurrent-owner"),
        ]

    priv_issue.add_to_assignees.side_effect = _assign_with_race
    priv_issue.get_events.return_value = [
        _assignment_event("assigned", "assaferan", "lyrebird[bot]"),
        _assignment_event("unassigned", "assaferan", "engineer"),
    ]

    assert assign_area_owner(config, priv_issue, ["Lattices"]) is None
    priv_issue.remove_from_assignees.assert_not_called()
    assert len(_warnings(caplog)) == 1
    assert "assaferan" in _warnings(caplog)[0].getMessage()


def test_lost_assignment_race_contains_removal_failure(config, caplog):
    priv_issue = _priv_issue()

    def _assign_with_race(*_):
        priv_issue.assignees = [
            _named_user("assaferan"),
            _named_user("concurrent-owner"),
        ]

    priv_issue.add_to_assignees.side_effect = _assign_with_race
    priv_issue.get_events.return_value = [
        _assignment_event("assigned", "assaferan", "lyrebird[bot]")
    ]
    priv_issue.update.side_effect = _refresh_with_assignees(
        priv_issue, "assaferan", "concurrent-owner"
    )
    priv_issue.remove_from_assignees.side_effect = RuntimeError("502 Bad Gateway")

    assert assign_area_owner(config, priv_issue, ["Lattices"]) is None
    priv_issue.remove_from_assignees.assert_called_once_with("assaferan")
    assert "removal attempt for 'assaferan' failed with outcome unknown" in caplog.text
    assert "assignees need manual verification" in caplog.text
    assert "Failed to assign" not in caplog.text


def test_canonical_login_casing_is_not_a_failure(config, caplog):
    # GitHub echoes the account's own spelling of a login, which need not match
    # the configured one.
    priv_issue = _priv_issue()

    def _assign_canonical(*_):
        priv_issue.assignees = [_named_user("AssafEran")]

    priv_issue.add_to_assignees.side_effect = _assign_canonical

    assert assign_area_owner(config, priv_issue, ["Lattices"]) == "assaferan"
    assert _warnings(caplog) == []


def test_unreadable_assignee_login_is_warned(config, caplog):
    priv_issue = _priv_issue()
    exploding = MagicMock()
    type(exploding).login = PropertyMock(side_effect=RuntimeError("502 Bad Gateway"))

    def _assign_unreadable(*_):
        priv_issue.assignees = [exploding]

    priv_issue.add_to_assignees.side_effect = _assign_unreadable

    assert assign_area_owner(config, priv_issue, ["Lattices"]) == "assaferan"
    assert "post-write assignee state could not be verified for private #10" in caplog.text


def test_unreadable_assignee_list_is_warned(config, caplog):
    # `.assignees` answers the pre-check, then every later read gets the 502.
    priv_issue = MagicMock()
    priv_issue.number = 10
    priv_issue.state = "open"
    reads = 0

    def _assignees():
        nonlocal reads
        reads += 1
        if reads == 1:
            return []
        raise RuntimeError("502 Bad Gateway")

    type(priv_issue).assignees = PropertyMock(side_effect=_assignees)

    assert assign_area_owner(config, priv_issue, ["Lattices"]) == "assaferan"
    assert "post-write assignee state could not be verified for private #10" in caplog.text


def test_missing_assignee_list_is_warned(config, caplog):
    # A response body without an `assignees` field leaves the attribute unset,
    # which PyGithub surfaces as None.
    priv_issue = _priv_issue()

    def _drop_the_list(*_):
        priv_issue.assignees = None

    priv_issue.add_to_assignees.side_effect = _drop_the_list

    assert assign_area_owner(config, priv_issue, ["Lattices"]) == "assaferan"
    assert "post-write assignee state could not be verified for private #10" in caplog.text
