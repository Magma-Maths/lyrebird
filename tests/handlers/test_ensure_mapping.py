"""Tests for ensure_private_mapping bootstrap helper."""

from __future__ import annotations

from unittest.mock import MagicMock

from lyrebird.handlers._ensure_mapping import ensure_private_mapping
from tests.conftest import (
    make_mock_issue,
    make_private_issue_body,
    make_public_issue_payload,
    setup_missing_mapping,
)


def test_returns_existing_mapping_without_creating(config, mock_client):
    """If mapping comment already exists, do not create a new private issue."""
    public_issue = make_public_issue_payload()

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue_obj = make_mock_issue(number=42)

    mapping_comment = MagicMock()
    mapping_comment.body = (
        "<!-- mapping: public_issue_node_id=I_kwDOTest private_issue_number=10 -->"
    )
    mock_pub_issue_obj.get_comments.return_value = [mapping_comment]

    existing_private = make_mock_issue(number=10)

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    mock_pub_repo.get_issue.return_value = mock_pub_issue_obj
    mock_priv_repo.get_issue.return_value = existing_private

    result = ensure_private_mapping(mock_client, config, public_issue)

    assert result.private_issue_number == 10
    assert result.was_bootstrapped is False
    mock_priv_repo.create_issue.assert_not_called()


def test_creates_private_issue_when_no_mapping(config, mock_client):
    """When neither mapping comment nor fallback body markers exist, create the mirror."""
    public_issue = make_public_issue_payload(title="Bug X", body="Body X")
    mock_pub_repo, mock_priv_repo, mock_pub_issue_obj, _ = setup_missing_mapping(config, mock_client)

    result = ensure_private_mapping(mock_client, config, public_issue)

    assert result.private_issue_number == 99
    assert result.was_bootstrapped is True
    mock_priv_repo.create_issue.assert_called_once()
    create_kwargs = mock_priv_repo.create_issue.call_args.kwargs
    assert "[public #42] Bug X" == create_kwargs["title"]
    assert "Body X" in create_kwargs["body"]

    # Mapping comment posted on public
    mock_pub_issue_obj.create_comment.assert_called_once()
    mapping_text = mock_pub_issue_obj.create_comment.call_args[0][0]
    assert "private_issue_number=99" in mapping_text

    # pub_issue was fetched once (threaded through resolve_mapping) — the
    # optimization that saves one HTTP call on the bootstrap path.
    assert mock_pub_repo.get_issue.call_count == 1


def test_bootstrap_mirrors_labels_type_and_milestone(config, mock_client):
    """Bootstrap uses the full current state from the payload: labels, type, milestone."""
    public_issue = make_public_issue_payload(
        labels=[{"name": "bug", "color": "d73a4a", "description": ""}],
        milestone={
            "title": "v1.0",
            "description": "First release",
            "due_on": "2026-06-01T00:00:00Z",
            "state": "open",
            "number": 1,
        },
    )
    public_issue["type"] = {"name": "Bug"}

    _, mock_priv_repo, _, mock_priv_issue = setup_missing_mapping(config, mock_client)

    created_ms = MagicMock()
    created_ms.title = "v1.0"
    mock_priv_repo.create_milestone.return_value = created_ms

    ensure_private_mapping(mock_client, config, public_issue)

    create_kwargs = mock_priv_repo.create_issue.call_args.kwargs
    assert "bug" in create_kwargs["labels"]

    mock_priv_repo.create_milestone.assert_called_once()
    edit_calls = mock_priv_issue.edit.call_args_list
    assert any(
        call.kwargs.get("milestone") is created_ms for call in edit_calls
    ), "milestone should have been assigned via edit()"

    # Issue type set via the mocked requester
    mock_client._Github__requester.requestJsonAndCheck.assert_called()


def test_bootstrap_assigns_area_owner_from_payload_labels(config, mock_client):
    """The mirror the bootstrap creates carries the area label, so it is the
    bootstrap that has to assign the owner."""
    public_issue = make_public_issue_payload(
        labels=[{"name": "Lattices", "color": "d73a4a", "description": ""}]
    )
    _, _, _, mock_priv_issue = setup_missing_mapping(config, mock_client)

    ensure_private_mapping(mock_client, config, public_issue)

    mock_priv_issue.add_to_assignees.assert_called_once_with("assaferan")


def test_bootstrap_does_not_assign_for_unmapped_labels(config, mock_client):
    public_issue = make_public_issue_payload(
        labels=[{"name": "bug", "color": "d73a4a", "description": ""}]
    )
    _, _, _, mock_priv_issue = setup_missing_mapping(config, mock_client)

    ensure_private_mapping(mock_client, config, public_issue)

    mock_priv_issue.add_to_assignees.assert_not_called()


def test_bootstrap_with_two_area_labels_assigns_only_first_owner(config, mock_client):
    """With two mapped labels the first one in payload order wins, once."""
    public_issue = make_public_issue_payload(
        labels=[
            {"name": "Lattices", "color": "d73a4a", "description": ""},
            {"name": "Algebras", "color": "0075ca", "description": ""},
        ]
    )
    _, _, _, mock_priv_issue = setup_missing_mapping(config, mock_client)

    ensure_private_mapping(mock_client, config, public_issue)

    mock_priv_issue.add_to_assignees.assert_called_once_with("assaferan")


def test_bootstrap_self_heals_via_fallback_body_search(config, mock_client):
    """If the mapping comment is missing but a private issue already has the body marker,
    resolve_mapping self-heals and ensure_private_mapping returns without creating."""
    public_issue = make_public_issue_payload()

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue_obj = make_mock_issue(number=42)
    mock_pub_issue_obj.get_comments.return_value = []

    existing_private = make_mock_issue(number=10)
    existing_private.body = make_private_issue_body(
        public_number=42, public_node_id="I_kwDOTest"
    )
    mock_priv_repo.get_issues.return_value = [existing_private]

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    mock_pub_repo.get_issue.return_value = mock_pub_issue_obj
    mock_priv_repo.get_issue.return_value = existing_private

    result = ensure_private_mapping(mock_client, config, public_issue)

    assert result.private_issue_number == 10
    assert result.was_bootstrapped is False
    mock_priv_repo.create_issue.assert_not_called()
