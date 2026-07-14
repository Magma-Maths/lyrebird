"""Tests for private_labels_changed handler."""

from __future__ import annotations

from unittest.mock import MagicMock

from lyrebird.handlers.private_labels_changed import handle
from tests.conftest import make_private_issue_body


def test_mirrors_label_to_public_if_exists(config, mock_client):
    payload = {
        "action": "labeled",
        "issue": {
            "number": 10,
            "body": make_private_issue_body(),
            "state": "open",
        },
        "label": {"name": "bug", "color": "d73a4a"},
        "sender": {"login": "engineer", "type": "User"},
    }

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue = MagicMock()
    mock_pub_repo.get_issue.return_value = mock_pub_issue
    # Label exists on public repo
    mock_pub_repo.get_label.return_value = MagicMock()

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo

    handle(mock_client, config, payload)

    mock_pub_issue.add_to_labels.assert_called_with("bug")


def test_skips_label_not_on_public(config, mock_client):
    payload = {
        "action": "labeled",
        "issue": {
            "number": 10,
            "body": make_private_issue_body(),
            "state": "open",
        },
        "label": {"name": "internal-only"},
        "sender": {"login": "engineer", "type": "User"},
    }

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    # Label does NOT exist on public
    mock_pub_repo.get_label.side_effect = Exception("not found")

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo

    handle(mock_client, config, payload)

    # Should not try to get public issue
    mock_pub_repo.get_issue.assert_not_called()


def test_not_mirrored_skips(config, mock_client):
    payload = {
        "action": "labeled",
        "issue": {
            "number": 10,
            "body": "regular issue no markers",
            "state": "open",
        },
        "label": {"name": "bug"},
        "sender": {"login": "engineer", "type": "User"},
    }

    handle(mock_client, config, payload)
    # No error, just returns


def _wire_priv_issue(mock_client, config, assignees):
    """Wire mock_client so the private repo returns an issue with the given
    assignees list.  Returns the mock private issue."""
    mock_priv_repo = MagicMock()
    mock_priv_issue = MagicMock()
    mock_priv_issue.number = 10
    mock_priv_issue.assignees = assignees
    mock_priv_repo.get_issue.return_value = mock_priv_issue
    # Public repo mock: label does not exist so mirroring is a no-op.
    mock_pub_repo = MagicMock()
    mock_pub_repo.get_label.side_effect = Exception("not found")

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    return mock_priv_issue


def test_assigns_area_owner_when_unassigned(config, mock_client):
    payload = {
        "action": "labeled",
        "issue": {"number": 10, "body": make_private_issue_body(), "state": "open"},
        "label": {"name": "Lattices"},
        "sender": {"login": "triager", "type": "User"},
    }
    priv_issue = _wire_priv_issue(mock_client, config, assignees=[])

    handle(mock_client, config, payload)

    priv_issue.add_to_assignees.assert_called_once_with("assaferan")


def test_does_not_override_existing_assignee(config, mock_client):
    existing = MagicMock()
    existing.login = "someone"
    payload = {
        "action": "labeled",
        "issue": {"number": 10, "body": make_private_issue_body(), "state": "open"},
        "label": {"name": "Lattices"},
        "sender": {"login": "triager", "type": "User"},
    }
    priv_issue = _wire_priv_issue(mock_client, config, assignees=[existing])

    handle(mock_client, config, payload)

    priv_issue.add_to_assignees.assert_not_called()


def test_non_area_label_does_not_assign(config, mock_client):
    payload = {
        "action": "labeled",
        "issue": {"number": 10, "body": make_private_issue_body(), "state": "open"},
        "label": {"name": "impact:high"},
        "sender": {"login": "triager", "type": "User"},
    }
    priv_issue = _wire_priv_issue(mock_client, config, assignees=[])

    handle(mock_client, config, payload)

    priv_issue.add_to_assignees.assert_not_called()


def test_unlabeled_area_does_not_assign(config, mock_client):
    payload = {
        "action": "unlabeled",
        "issue": {"number": 10, "body": make_private_issue_body(), "state": "open"},
        "label": {"name": "Lattices"},
        "sender": {"login": "triager", "type": "User"},
    }
    priv_issue = _wire_priv_issue(mock_client, config, assignees=[])

    handle(mock_client, config, payload)

    priv_issue.add_to_assignees.assert_not_called()


def test_assigns_area_owner_on_non_mirrored_issue(config, mock_client):
    """Native (non-mirrored) private issues still get an area owner even
    though they have no public markers."""
    payload = {
        "action": "labeled",
        "issue": {"number": 10, "body": "native issue, no markers", "state": "open"},
        "label": {"name": "Algebras"},
        "sender": {"login": "triager", "type": "User"},
    }
    priv_issue = _wire_priv_issue(mock_client, config, assignees=[])

    handle(mock_client, config, payload)

    priv_issue.add_to_assignees.assert_called_once_with("jvoight")


def test_resolution_label_on_closed_posts_note_when_public_already_closed(config, mock_client):
    """When a resolution label is added to a closed private issue whose public is already closed,
    the resolution note should still be posted."""
    payload = {
        "action": "labeled",
        "issue": {
            "number": 10,
            "body": make_private_issue_body(),
            "state": "closed",
        },
        "label": {"name": "resolution:completed"},
        "sender": {"login": "engineer", "type": "User"},
    }

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue = MagicMock()
    mock_pub_issue.state = "closed"  # Already closed by private_issue_closed handler
    mock_pub_repo.get_issue.return_value = mock_pub_issue
    mock_pub_repo.get_label.return_value = MagicMock()  # Label exists on public

    mock_priv_issue = MagicMock()
    mock_priv_issue.state = "closed"
    mock_priv_issue.number = 10
    lbl = MagicMock()
    lbl.name = "resolution:completed"
    mock_priv_issue.get_labels.return_value = [lbl]
    mock_priv_repo.get_issue.return_value = mock_priv_issue

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo

    handle(mock_client, config, payload)

    # Should post note even though public is already closed
    mock_pub_issue.create_comment.assert_called_once()
    note = mock_pub_issue.create_comment.call_args[0][0]
    assert "has been fixed" in note
    # Should NOT try to close again (already closed)
    mock_pub_issue.edit.assert_not_called()


def test_resolution_label_on_closed_removes_resolution_none(config, mock_client):
    """Adding a resolution label to a closed private issue removes resolution:none."""
    payload = {
        "action": "labeled",
        "issue": {
            "number": 10,
            "body": make_private_issue_body(),
            "state": "closed",
        },
        "label": {"name": "resolution:not-planned"},
        "sender": {"login": "engineer", "type": "User"},
    }

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue = MagicMock()
    mock_pub_issue.state = "closed"
    mock_pub_repo.get_issue.return_value = mock_pub_issue
    mock_pub_repo.get_label.return_value = MagicMock()

    mock_priv_issue = MagicMock()
    mock_priv_issue.state = "closed"
    mock_priv_issue.number = 10
    lbl1 = MagicMock()
    lbl1.name = "resolution:not-planned"
    lbl2 = MagicMock()
    lbl2.name = "resolution:none"
    mock_priv_issue.get_labels.return_value = [lbl1, lbl2]
    mock_priv_repo.get_issue.return_value = mock_priv_issue

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo

    handle(mock_client, config, payload)

    # Should post note
    mock_pub_issue.create_comment.assert_called_once()
    # Should remove resolution:none
    mock_priv_issue.remove_from_labels.assert_called_once_with("resolution:none")


def test_resolution_label_not_on_public_still_posts_note(config, mock_client):
    """When a resolution label is added to a closed private issue but the label
    does NOT exist on the public repo, the resolution note should still be posted."""
    payload = {
        "action": "labeled",
        "issue": {
            "number": 10,
            "body": make_private_issue_body(),
            "state": "closed",
        },
        "label": {"name": "resolution:completed"},
        "sender": {"login": "engineer", "type": "User"},
    }

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue = MagicMock()
    mock_pub_issue.state = "closed"
    mock_pub_repo.get_issue.return_value = mock_pub_issue
    # Label does NOT exist on public repo
    mock_pub_repo.get_label.side_effect = Exception("not found")

    mock_priv_issue = MagicMock()
    mock_priv_issue.state = "closed"
    mock_priv_issue.number = 10
    lbl = MagicMock()
    lbl.name = "resolution:completed"
    mock_priv_issue.get_labels.return_value = [lbl]
    mock_priv_repo.get_issue.return_value = mock_priv_issue

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo

    handle(mock_client, config, payload)

    # Should still post note even though label doesn't exist on public
    mock_pub_issue.create_comment.assert_called_once()
    note = mock_pub_issue.create_comment.call_args[0][0]
    assert "has been fixed" in note
