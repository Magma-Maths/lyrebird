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

    # Baseline: how many requester calls fire during bootstrap (for set_issue_type
    # inside ensure_private_mapping). The handler must not add another one.
    handle(mock_client, config, payload)

    mock_priv_repo.create_issue.assert_called_once()
    # Bootstrap sets the type once; handler short-circuits instead of setting it again.
    assert mock_client._Github__requester.requestJsonAndCheck.call_count == 1
