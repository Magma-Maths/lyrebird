"""Tests for private_issue_reopened handler."""

from __future__ import annotations

from unittest.mock import MagicMock

from lyrebird.handlers.private_issue_reopened import handle


def test_removes_resolution_and_needs_resolution(config, mock_client):
    payload = {
        "action": "reopened",
        "issue": {"number": 10, "body": "body", "state": "open"},
        "sender": {"login": "engineer", "type": "User"},
    }

    mock_priv_repo = MagicMock()
    mock_priv_issue = MagicMock()

    lbl1 = MagicMock()
    lbl1.name = "external:fixed"
    lbl2 = MagicMock()
    lbl2.name = "needs-public-resolution"
    lbl3 = MagicMock()
    lbl3.name = "unrelated"
    mock_priv_issue.get_labels.return_value = [lbl1, lbl2, lbl3]
    mock_priv_repo.get_issue.return_value = mock_priv_issue

    mock_client.get_repo.return_value = mock_priv_repo

    handle(mock_client, config, payload)

    mock_priv_issue.remove_from_labels.assert_any_call("external:fixed")
    mock_priv_issue.remove_from_labels.assert_any_call("needs-public-resolution")
    # Should NOT remove unrelated labels
    calls = [c[0][0] for c in mock_priv_issue.remove_from_labels.call_args_list]
    assert "unrelated" not in calls

    # Audit comment
    mock_priv_issue.create_comment.assert_called_once()
    msg = mock_priv_issue.create_comment.call_args[0][0]
    assert "reopened by @engineer" in msg
