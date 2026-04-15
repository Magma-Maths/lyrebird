"""Tests for public_issue_typed handler."""

from __future__ import annotations

from unittest.mock import MagicMock

from lyrebird.handlers.public_issue_typed import handle
from tests.conftest import (
    make_mock_issue,
    make_public_issue_payload,
    setup_missing_mapping,
)


def test_sets_type_on_existing_private_mirror(config, mock_client):
    """When mapping exists, set the type on the private issue."""
    public_issue = make_public_issue_payload()
    public_issue["type"] = {"name": "Bug"}
    payload = {"issue": public_issue, "action": "typed"}

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue_obj = make_mock_issue(number=42)

    mapping_comment = MagicMock()
    mapping_comment.body = (
        "<!-- mapping: public_issue_node_id=I_kwDOTest private_issue_number=10 -->"
    )
    mock_pub_issue_obj.get_comments.return_value = [mapping_comment]

    mock_private = make_mock_issue(number=10)
    mock_priv_repo.get_issue.return_value = mock_private

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    mock_pub_repo.get_issue.return_value = mock_pub_issue_obj

    handle(mock_client, config, payload)

    # set_issue_type uses requester directly
    mock_client._Github__requester.requestJsonAndCheck.assert_called()


def test_bootstraps_when_no_mapping(config, mock_client):
    """When the `typed` event arrives before `opened` ran, bootstrap the mirror."""
    public_issue = make_public_issue_payload()
    public_issue["type"] = {"name": "Bug"}
    payload = {"issue": public_issue, "action": "typed"}

    _, mock_priv_repo, _, _ = setup_missing_mapping(config, mock_client)

    handle(mock_client, config, payload)

    mock_priv_repo.create_issue.assert_called_once()
    # Bootstrap sets the type once; handler short-circuits instead of setting it again.
    assert mock_client._Github__requester.requestJsonAndCheck.call_count == 1


def test_untyped_bootstraps_then_clears(config, mock_client):
    """When `untyped` arrives before `opened`, the handler must explicitly clear
    the type — we can't trust that payload.issue.type is post-action state, so
    the short-circuit is scoped to `typed` only and `untyped` always passes
    None to set_issue_type regardless of what the payload contains."""
    public_issue = make_public_issue_payload()
    # Simulate pre-state delivery: issue.type still contains the removed type.
    public_issue["type"] = {"name": "Bug"}
    payload = {"issue": public_issue, "action": "untyped"}

    _, mock_priv_repo, _, _ = setup_missing_mapping(config, mock_client)

    handle(mock_client, config, payload)

    mock_priv_repo.create_issue.assert_called_once()
    # Bootstrap set type (1 call with "Bug"), handler then explicitly cleared
    # it (2nd call with None — NOT "Bug", even though issue.type still says Bug).
    call_args_list = mock_client._Github__requester.requestJsonAndCheck.call_args_list
    assert len(call_args_list) == 2
    # The second call is the handler's clear. Its `input` kwarg must be {"type": None}.
    second_call_input = call_args_list[1].kwargs.get("input") or (
        call_args_list[1].args[2] if len(call_args_list[1].args) >= 3 else None
    )
    assert second_call_input == {"type": None}, (
        f"expected untyped handler to clear type with None, got {second_call_input}"
    )


def test_untyped_clears_type_without_bootstrap(config, mock_client):
    """Non-bootstrap path: untyped event on an existing mapping must clear the
    type regardless of payload.issue.type, which may deliver pre-action state."""
    public_issue = make_public_issue_payload()
    # Simulate pre-state delivery: issue.type still contains the removed type.
    public_issue["type"] = {"name": "Bug"}
    payload = {"issue": public_issue, "action": "untyped"}

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue_obj = make_mock_issue(number=42)

    mapping_comment = MagicMock()
    mapping_comment.body = (
        "<!-- mapping: public_issue_node_id=I_kwDOTest private_issue_number=10 -->"
    )
    mock_pub_issue_obj.get_comments.return_value = [mapping_comment]

    mock_private = make_mock_issue(number=10)
    mock_priv_repo.get_issue.return_value = mock_private

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    mock_pub_repo.get_issue.return_value = mock_pub_issue_obj

    handle(mock_client, config, payload)

    # Handler called set_issue_type with None (not "Bug").
    call_args_list = mock_client._Github__requester.requestJsonAndCheck.call_args_list
    assert len(call_args_list) == 1
    first_call_input = call_args_list[0].kwargs.get("input") or (
        call_args_list[0].args[2] if len(call_args_list[0].args) >= 3 else None
    )
    assert first_call_input == {"type": None}, (
        f"expected untyped handler to clear type with None, got {first_call_input}"
    )
