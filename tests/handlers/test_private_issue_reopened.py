"""Tests for private_issue_reopened handler."""

from __future__ import annotations

from unittest.mock import MagicMock, call

from lyrebird.handlers.private_issue_reopened import handle
from tests.conftest import make_private_issue_body


def _make_private_body():
    return make_private_issue_body(public_number=42, public_node_id="I_kwDOTest")


def test_removes_resolution_and_needs_resolution(config, mock_client):
    payload = {
        "action": "reopened",
        "issue": {"number": 10, "body": "body", "state": "open"},
        "sender": {"login": "engineer", "type": "User"},
    }

    mock_priv_repo = MagicMock()
    mock_priv_issue = MagicMock()

    lbl1 = MagicMock()
    lbl1.name = "external:completed"
    lbl2 = MagicMock()
    lbl2.name = "needs-public-resolution"
    lbl3 = MagicMock()
    lbl3.name = "unrelated"
    mock_priv_issue.get_labels.return_value = [lbl1, lbl2, lbl3]
    mock_priv_repo.get_issue.return_value = mock_priv_issue

    mock_client.get_repo.return_value = mock_priv_repo

    handle(mock_client, config, payload)

    mock_priv_issue.remove_from_labels.assert_any_call("external:completed")
    mock_priv_issue.remove_from_labels.assert_any_call("needs-public-resolution")
    # Should NOT remove unrelated labels
    calls = [c[0][0] for c in mock_priv_issue.remove_from_labels.call_args_list]
    assert "unrelated" not in calls

    # Audit comment
    mock_priv_issue.create_comment.assert_called_once()
    msg = mock_priv_issue.create_comment.call_args[0][0]
    assert "reopened by @engineer" in msg


def test_reopens_public_issue(config, mock_client):
    payload = {
        "action": "reopened",
        "issue": {"number": 10, "body": _make_private_body(), "state": "open"},
        "sender": {"login": "engineer", "type": "User"},
    }

    mock_priv_repo = MagicMock()
    mock_priv_issue = MagicMock()
    mock_priv_issue.get_labels.return_value = []
    mock_priv_repo.get_issue.return_value = mock_priv_issue

    mock_pub_repo = MagicMock()
    mock_pub_issue = MagicMock()
    mock_pub_issue.state = "closed"
    mock_pub_repo.get_issue.return_value = mock_pub_issue

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo

    handle(mock_client, config, payload)

    mock_pub_issue.edit.assert_called_once_with(state="open")
    mock_pub_issue.create_comment.assert_called_once()
    msg = mock_pub_issue.create_comment.call_args[0][0]
    assert "reopened" in msg


def test_skips_reopen_if_public_already_open(config, mock_client):
    payload = {
        "action": "reopened",
        "issue": {"number": 10, "body": _make_private_body(), "state": "open"},
        "sender": {"login": "engineer", "type": "User"},
    }

    mock_priv_repo = MagicMock()
    mock_priv_issue = MagicMock()
    mock_priv_issue.get_labels.return_value = []
    mock_priv_repo.get_issue.return_value = mock_priv_issue

    mock_pub_repo = MagicMock()
    mock_pub_issue = MagicMock()
    mock_pub_issue.state = "open"
    mock_pub_repo.get_issue.return_value = mock_pub_issue

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo

    handle(mock_client, config, payload)

    mock_pub_issue.edit.assert_not_called()
    mock_pub_issue.create_comment.assert_not_called()


def test_non_mirrored_issue_skips_public_reopen(config, mock_client):
    payload = {
        "action": "reopened",
        "issue": {"number": 10, "body": "no markers here", "state": "open"},
        "sender": {"login": "engineer", "type": "User"},
    }

    mock_priv_repo = MagicMock()
    mock_priv_issue = MagicMock()
    mock_priv_issue.get_labels.return_value = []
    mock_priv_repo.get_issue.return_value = mock_priv_issue

    mock_client.get_repo.return_value = mock_priv_repo

    handle(mock_client, config, payload)

    # Should only call get_repo once (for private repo), not for public
    mock_client.get_repo.assert_called_once_with(config.private_repo)


def test_no_body_skips_public_reopen(config, mock_client):
    payload = {
        "action": "reopened",
        "issue": {"number": 10, "body": None, "state": "open"},
        "sender": {"login": "engineer", "type": "User"},
    }

    mock_priv_repo = MagicMock()
    mock_priv_issue = MagicMock()
    mock_priv_issue.get_labels.return_value = []
    mock_priv_repo.get_issue.return_value = mock_priv_issue

    mock_client.get_repo.return_value = mock_priv_repo

    handle(mock_client, config, payload)

    # Should handle None body gracefully
    mock_priv_issue.create_comment.assert_called_once()


def test_multiple_resolution_labels_all_removed(config, mock_client):
    """All resolution labels are cleaned even if multiple are present."""
    payload = {
        "action": "reopened",
        "issue": {"number": 10, "body": "body", "state": "open"},
        "sender": {"login": "engineer", "type": "User"},
    }

    mock_priv_repo = MagicMock()
    mock_priv_issue = MagicMock()

    labels = []
    for name in [
        "external:completed",
        "external:not-planned",
        "external:cannot-reproduce",
        "needs-public-resolution",
    ]:
        lbl = MagicMock()
        lbl.name = name
        labels.append(lbl)
    mock_priv_issue.get_labels.return_value = labels
    mock_priv_repo.get_issue.return_value = mock_priv_issue

    mock_client.get_repo.return_value = mock_priv_repo

    handle(mock_client, config, payload)

    removed = {c[0][0] for c in mock_priv_issue.remove_from_labels.call_args_list}
    assert removed == {
        "external:completed",
        "external:not-planned",
        "external:cannot-reproduce",
        "needs-public-resolution",
    }


def test_missing_sender_uses_unknown(config, mock_client):
    """Missing sender falls back to 'unknown'."""
    payload = {
        "action": "reopened",
        "issue": {"number": 10, "body": "body", "state": "open"},
        # no "sender" key
    }

    mock_priv_repo = MagicMock()
    mock_priv_issue = MagicMock()
    mock_priv_issue.get_labels.return_value = []
    mock_priv_repo.get_issue.return_value = mock_priv_issue

    mock_client.get_repo.return_value = mock_priv_repo

    handle(mock_client, config, payload)

    msg = mock_priv_issue.create_comment.call_args[0][0]
    assert "reopened by @unknown" in msg


def test_always_posts_audit_even_without_markers(config, mock_client):
    """Audit comment is posted on private even when no public issue exists."""
    payload = {
        "action": "reopened",
        "issue": {"number": 10, "body": "no markers here", "state": "open"},
        "sender": {"login": "engineer", "type": "User"},
    }

    mock_priv_repo = MagicMock()
    mock_priv_issue = MagicMock()
    mock_priv_issue.get_labels.return_value = []
    mock_priv_repo.get_issue.return_value = mock_priv_issue

    mock_client.get_repo.return_value = mock_priv_repo

    handle(mock_client, config, payload)

    mock_priv_issue.create_comment.assert_called_once()
    msg = mock_priv_issue.create_comment.call_args[0][0]
    assert "reopened by @engineer" in msg
