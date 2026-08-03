"""Tests for public_labels_changed handler."""

from __future__ import annotations

from unittest.mock import MagicMock

from lyrebird.handlers.public_labels_changed import handle
from tests.conftest import (
    make_mock_issue,
    make_public_issue_payload,
    setup_missing_mapping,
)


def test_adds_label_to_private(config, mock_client):
    public_issue = make_public_issue_payload()
    payload = {
        "action": "labeled",
        "issue": public_issue,
        "label": {"name": "bug", "color": "d73a4a", "description": ""},
        "sender": {"login": "triager", "type": "User"},
    }

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue_obj = make_mock_issue(number=42)

    mapping_comment = MagicMock()
    mapping_comment.body = (
        "<!-- mapping: public_issue_node_id=I_kwDOTest private_issue_number=10 -->"
    )
    mock_pub_issue_obj.get_comments.return_value = [mapping_comment]

    mock_private = make_mock_issue(number=10)
    # Need the repository attribute for _ensure_label
    mock_priv_repo_inner = MagicMock()
    type(mock_private).repository = property(lambda self: mock_priv_repo_inner)

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    mock_pub_repo.get_issue.return_value = mock_pub_issue_obj
    mock_priv_repo.get_issue.return_value = mock_private

    handle(mock_client, config, payload)

    mock_private.add_to_labels.assert_called_with("bug")


def test_adds_label_even_when_ensure_label_fails(config, mock_client):
    """When the label exists with different casing (e.g. Documentation vs documentation),
    get_label and create_label both fail, but add_to_labels should still be attempted."""
    public_issue = make_public_issue_payload()
    payload = {
        "action": "labeled",
        "issue": public_issue,
        "label": {"name": "documentation", "color": "0075ca", "description": ""},
        "sender": {"login": "triager", "type": "User"},
    }

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue_obj = make_mock_issue(number=42)

    mapping_comment = MagicMock()
    mapping_comment.body = (
        "<!-- mapping: public_issue_node_id=I_kwDOTest private_issue_number=10 -->"
    )
    mock_pub_issue_obj.get_comments.return_value = [mapping_comment]

    mock_private = make_mock_issue(number=10)
    mock_priv_repo_inner = MagicMock()
    type(mock_private).repository = property(lambda self: mock_priv_repo_inner)
    # Simulate case mismatch: get_label("documentation") fails,
    # create_label("documentation") also fails (already exists as "Documentation")
    mock_priv_repo_inner.get_label.side_effect = Exception("not found")
    mock_priv_repo_inner.create_label.side_effect = Exception("already exists")

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    mock_pub_repo.get_issue.return_value = mock_pub_issue_obj
    mock_priv_repo.get_issue.return_value = mock_private

    handle(mock_client, config, payload)

    # Should still attempt to add the label to the issue
    mock_private.add_to_labels.assert_called_with("documentation")


def test_removes_label_from_private(config, mock_client):
    public_issue = make_public_issue_payload()
    payload = {
        "action": "unlabeled",
        "issue": public_issue,
        "label": {"name": "bug", "color": "d73a4a"},
        "sender": {"login": "triager", "type": "User"},
    }

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

    handle(mock_client, config, payload)

    mock_private.remove_from_labels.assert_called_with("bug")


def test_bootstraps_when_no_mapping(config, mock_client):
    """When `labeled` arrives before `opened` ran, bootstrap the mirror."""
    public_issue = make_public_issue_payload(
        labels=[{"name": "bug", "color": "d73a4a", "description": ""}]
    )
    payload = {
        "issue": public_issue,
        "action": "labeled",
        "label": {"name": "bug", "color": "d73a4a", "description": ""},
    }

    _, mock_priv_repo, _, mock_priv_issue = setup_missing_mapping(config, mock_client)

    handle(mock_client, config, payload)

    mock_priv_repo.create_issue.assert_called_once()
    create_kwargs = mock_priv_repo.create_issue.call_args.kwargs
    assert "bug" in create_kwargs["labels"]
    # Bootstrap already applied the label set; handler short-circuits.
    mock_priv_issue.add_to_labels.assert_not_called()
    mock_priv_issue.remove_from_labels.assert_not_called()


def _wire_existing_mapping(config, mock_client, mock_private):
    """Wire mock_client so resolve_mapping finds an existing mapping pointing at
    mock_private.  Returns the mock public issue object."""
    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue_obj = make_mock_issue(number=42)

    mapping_comment = MagicMock()
    mapping_comment.body = (
        "<!-- mapping: public_issue_node_id=I_kwDOTest private_issue_number=10 -->"
    )
    mock_pub_issue_obj.get_comments.return_value = [mapping_comment]

    mock_priv_repo_inner = MagicMock()
    type(mock_private).repository = property(lambda self: mock_priv_repo_inner)

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    mock_pub_repo.get_issue.return_value = mock_pub_issue_obj
    mock_priv_repo.get_issue.return_value = mock_private
    return mock_pub_issue_obj


def test_assigns_area_owner_when_public_area_label_added(config, mock_client):
    """A human labelling the public tracker still gets the private mirror
    assigned: the mirrored private `labeled` event comes from the bot and is
    dropped before any handler runs."""
    public_issue = make_public_issue_payload()
    payload = {
        "action": "labeled",
        "issue": public_issue,
        "label": {"name": "Lattices", "color": "d73a4a", "description": ""},
        "sender": {"login": "triager", "type": "User"},
    }

    mock_private = make_mock_issue(number=10)
    _wire_existing_mapping(config, mock_client, mock_private)

    handle(mock_client, config, payload)

    mock_private.add_to_labels.assert_called_with("Lattices")
    mock_private.add_to_assignees.assert_called_once_with("assaferan")


def test_public_label_does_not_override_existing_assignee(config, mock_client):
    public_issue = make_public_issue_payload()
    payload = {
        "action": "labeled",
        "issue": public_issue,
        "label": {"name": "Lattices", "color": "d73a4a", "description": ""},
        "sender": {"login": "triager", "type": "User"},
    }

    mock_private = make_mock_issue(number=10)
    mock_private.assignees = [MagicMock()]
    _wire_existing_mapping(config, mock_client, mock_private)

    handle(mock_client, config, payload)

    mock_private.add_to_labels.assert_called_with("Lattices")
    mock_private.add_to_assignees.assert_not_called()


def test_bootstrap_from_public_area_label_assigns_once(config, mock_client):
    """Bootstrap assigns, and the handler's short circuit keeps it to one call."""
    public_issue = make_public_issue_payload(
        labels=[{"name": "Lattices", "color": "d73a4a", "description": ""}]
    )
    payload = {
        "issue": public_issue,
        "action": "labeled",
        "label": {"name": "Lattices", "color": "d73a4a", "description": ""},
    }

    _, _, _, mock_priv_issue = setup_missing_mapping(config, mock_client)

    handle(mock_client, config, payload)

    mock_priv_issue.add_to_assignees.assert_called_once_with("assaferan")


def test_unlabeled_bootstraps_then_removes(config, mock_client):
    """Real `unlabeled` webhooks deliver pre-action `issue.labels` — the removed
    label is still present. Bootstrap creates the mirror with the stale label,
    then the handler must explicitly remove it."""
    # Public payload: unlabel event fires, issue.labels still includes "bug"
    # because real webhooks deliver pre-action state for unlabeled.
    public_issue = make_public_issue_payload(
        labels=[{"name": "bug", "color": "d73a4a", "description": ""}]
    )
    payload = {
        "issue": public_issue,
        "action": "unlabeled",
        "label": {"name": "bug", "color": "d73a4a", "description": ""},
    }

    _, mock_priv_repo, _, mock_priv_issue = setup_missing_mapping(config, mock_client)

    handle(mock_client, config, payload)

    # Bootstrap created the mirror with the stale label.
    mock_priv_repo.create_issue.assert_called_once()
    create_kwargs = mock_priv_repo.create_issue.call_args.kwargs
    assert "bug" in create_kwargs["labels"]
    # Handler then explicitly removed it.
    mock_priv_issue.remove_from_labels.assert_called_once_with("bug")
