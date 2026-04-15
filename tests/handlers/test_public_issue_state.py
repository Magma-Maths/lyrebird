"""Tests for public_issue_state handler (close/reopen)."""

from __future__ import annotations

from unittest.mock import MagicMock

from lyrebird.handlers.public_issue_state import handle
from tests.conftest import (
    make_mock_issue,
    make_public_issue_payload,
    setup_missing_mapping,
)


def _setup_mocks(config, mock_client):
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

    return mock_private


def test_close_posts_audit(config, mock_client):
    public_issue = make_public_issue_payload(user_login="reporter")
    payload = {
        "action": "closed",
        "issue": public_issue,
        "sender": {"login": "closer", "type": "User"},
    }

    mock_private = _setup_mocks(config, mock_client)
    handle(mock_client, config, payload)

    mock_private.create_comment.assert_called_once()
    audit = mock_private.create_comment.call_args[0][0]
    assert "closed by @closer" in audit


def test_close_by_reporter_notes_reporter(config, mock_client):
    public_issue = make_public_issue_payload(user_login="reporter")
    payload = {
        "action": "closed",
        "issue": public_issue,
        "sender": {"login": "reporter", "type": "User"},
    }

    mock_private = _setup_mocks(config, mock_client)
    handle(mock_client, config, payload)

    audit = mock_private.create_comment.call_args[0][0]
    assert "original reporter" in audit


def test_reopen_posts_audit(config, mock_client):
    """Reopen posts cross-repo attribution on private (who reopened on public)."""
    public_issue = make_public_issue_payload(user_login="reporter")
    payload = {
        "action": "reopened",
        "issue": public_issue,
        "sender": {"login": "reporter", "type": "User"},
    }

    mock_private = _setup_mocks(config, mock_client)
    mock_private.get_labels.return_value = []

    handle(mock_client, config, payload)

    audit = mock_private.create_comment.call_args[0][0]
    assert "reopened by @reporter" in audit
    assert "original reporter" in audit


def test_close_also_closes_private(config, mock_client):
    public_issue = make_public_issue_payload(user_login="reporter")
    payload = {
        "action": "closed",
        "issue": public_issue,
        "sender": {"login": "closer", "type": "User"},
    }

    mock_private = _setup_mocks(config, mock_client)
    handle(mock_client, config, payload)

    mock_private.edit.assert_called_once_with(state="closed")


def test_reopen_also_reopens_private(config, mock_client):
    public_issue = make_public_issue_payload(user_login="reporter")
    payload = {
        "action": "reopened",
        "issue": public_issue,
        "sender": {"login": "reporter", "type": "User"},
    }

    mock_private = _setup_mocks(config, mock_client)
    handle(mock_client, config, payload)

    mock_private.edit.assert_called_once_with(state="open")


def test_close_with_state_reason(config, mock_client):
    public_issue = make_public_issue_payload(user_login="reporter")
    # GitHub payloads include state_reason in the 'issue' object
    public_issue["state_reason"] = "not_planned"
    payload = {
        "action": "closed",
        "issue": public_issue,
        "sender": {"login": "closer", "type": "User"},
    }

    mock_private = _setup_mocks(config, mock_client)
    handle(mock_client, config, payload)

    # We want to sync both state AND state_reason
    mock_private.edit.assert_called_once_with(state="closed", state_reason="not_planned")


def test_reopen_cleans_resolution_labels(config, mock_client):
    public_issue = make_public_issue_payload(user_login="reporter")
    payload = {
        "action": "reopened",
        "issue": public_issue,
        "sender": {"login": "reporter", "type": "User"},
    }

    mock_private = _setup_mocks(config, mock_client)

    # Add resolution labels to the private issue
    lbl1 = MagicMock()
    lbl1.name = "resolution:completed"
    lbl2 = MagicMock()
    lbl2.name = "resolution:none"
    mock_private.get_labels.return_value = [lbl1, lbl2]

    handle(mock_client, config, payload)

    removed = {c[0][0] for c in mock_private.remove_from_labels.call_args_list}
    assert "resolution:completed" in removed
    assert "resolution:none" in removed


def test_reopen_bootstraps_when_no_mapping_short_circuits(config, mock_client):
    """Rare race: both `opened` and `closed` were dropped, so `reopened` is the
    first event to actually run. Bootstrap already creates the mirror in open
    state; the handler must short-circuit to avoid posting a misleading
    "reopened by @X" audit comment on a mirror that was never closed from the
    private side's perspective."""
    public_issue = make_public_issue_payload(state="open", user_login="reporter")
    payload = {
        "issue": public_issue,
        "action": "reopened",
        "sender": {"login": "maintainer", "type": "User"},
    }

    _, mock_priv_repo, _, mock_priv_issue = setup_missing_mapping(config, mock_client)

    handle(mock_client, config, payload)

    # Bootstrap happened
    mock_priv_repo.create_issue.assert_called_once()
    # Handler short-circuited: no audit comment, no state edit, no cleanup.
    mock_priv_issue.create_comment.assert_not_called()
    mock_priv_issue.edit.assert_not_called()
    mock_priv_issue.remove_from_labels.assert_not_called()


def test_close_bootstraps_when_no_mapping(config, mock_client):
    """When `closed` arrives before `opened` ran, bootstrap the mirror then close it."""
    public_issue = make_public_issue_payload(state="closed")
    public_issue["state_reason"] = "completed"
    payload = {
        "issue": public_issue,
        "action": "closed",
        "sender": {"login": "reporter", "type": "User"},
    }

    _, mock_priv_repo, _, mock_priv_issue = setup_missing_mapping(config, mock_client)

    handle(mock_client, config, payload)

    # Bootstrap happened
    mock_priv_repo.create_issue.assert_called_once()
    # And the private issue was then closed with state_reason propagated
    # (bootstrap can only create in open state, so close is always needed).
    edit_calls = mock_priv_issue.edit.call_args_list
    assert any(
        c.kwargs.get("state") == "closed"
        and c.kwargs.get("state_reason") == "completed"
        for c in edit_calls
    ), "private issue should have been closed with state_reason=completed"


def test_reopen_by_non_reporter_no_reporter_note(config, mock_client):
    """Reopen by someone other than reporter omits '(original reporter)'."""
    public_issue = make_public_issue_payload(user_login="reporter")
    payload = {
        "action": "reopened",
        "issue": public_issue,
        "sender": {"login": "maintainer", "type": "User"},
    }

    mock_private = _setup_mocks(config, mock_client)
    mock_private.get_labels.return_value = []

    handle(mock_client, config, payload)

    audit = mock_private.create_comment.call_args[0][0]
    assert "reopened by @maintainer" in audit
    assert "original reporter" not in audit


def test_missing_sender_uses_unknown(config, mock_client):
    """Missing sender in payload falls back to 'unknown'."""
    public_issue = make_public_issue_payload(user_login="reporter")
    payload = {
        "action": "closed",
        "issue": public_issue,
        # no "sender" key
    }

    mock_private = _setup_mocks(config, mock_client)

    handle(mock_client, config, payload)

    audit = mock_private.create_comment.call_args[0][0]
    assert "closed by @unknown" in audit
