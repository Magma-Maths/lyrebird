"""Tests for private_issue_closed_check (delayed close check) handler."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest
from github import GithubException

from lyrebird.handlers import private_issue_reopened, private_labels_changed
from lyrebird.handlers.private_issue_closed_check import handle
from tests.conftest import make_mock_issue, make_private_issue_body


PUBLIC_URL = "https://github.com/testorg/public-repo/issues/42"
PR_CLOSER = {
    "__typename": "PullRequest",
    "url": "https://github.com/testorg/private-repo/pull/7",
}


def _make_payload():
    return {
        "action": "closed_check",
        "issue": {
            "number": 10,
            "body": make_private_issue_body(),
            "state": "closed",
            "closed_at": "2026-11-06T22:00:00Z",
        },
        "sender": {"login": "github-actions[bot]", "type": "Bot"},
    }


def _setup_mocks(
    config, mock_client, private_labels: list[str], state: str = "closed", closer=None
):
    mock_priv_repo = MagicMock()
    mock_priv_issue = make_mock_issue(number=10, state=state, labels=private_labels)
    mock_priv_issue.closed_at = datetime(2026, 11, 6, 22, 0, tzinfo=timezone.utc)
    current_labels = set(private_labels)
    current_state = {"state": state}
    mock_priv_issue.get_labels.side_effect = lambda: [
        SimpleNamespace(name=name) for name in sorted(current_labels)
    ]
    mock_priv_issue.add_to_labels.side_effect = lambda *names: current_labels.update(names)
    mock_priv_issue.remove_from_labels.side_effect = (
        lambda *names: current_labels.difference_update(names)
    )
    mock_priv_issue.edit.side_effect = lambda **fields: current_state.update(fields)

    def issue_snapshot(number):
        snapshot = make_mock_issue(number=number, state=current_state["state"])
        snapshot.closed_at = mock_priv_issue.closed_at
        snapshot.labels = [
            SimpleNamespace(name=name) for name in sorted(current_labels)
        ]
        for method in (
            "get_labels", "add_to_labels", "remove_from_labels", "edit", "create_comment"
        ):
            setattr(snapshot, method, getattr(mock_priv_issue, method))
        return snapshot

    mock_priv_repo.get_issue.side_effect = issue_snapshot
    mock_pub_repo = MagicMock()
    mock_pub_issue = make_mock_issue(number=42, state="closed")
    mock_pub_issue.edit.side_effect = lambda **fields: [
        setattr(mock_pub_issue, name, value) for name, value in fields.items()
    ]
    mock_pub_repo.get_issue.return_value = mock_pub_issue
    repos = {
        config.private_repo: mock_priv_repo,
        config.public_repo: mock_pub_repo,
    }
    mock_client.get_repo.side_effect = repos.__getitem__
    mock_client.requester.graphql_query.return_value = (
        {},
        {"data": {"repository": {"issue": {"timelineItems": {
            "nodes": [{"closer": closer}],
        }}}}},
    )
    return mock_priv_issue, mock_pub_issue


def test_reopened_during_grace_period_bails(config, mock_client):
    payload = _make_payload()
    priv_issue, _ = _setup_mocks(config, mock_client, [], state="open")

    handle(mock_client, config, payload)

    priv_issue.add_to_labels.assert_not_called()
    priv_issue.create_comment.assert_not_called()
    mock_client.requester.graphql_query.assert_not_called()


def test_has_resolution_label_does_nothing(config, mock_client):
    payload = _make_payload()
    priv_issue, pub_issue = _setup_mocks(
        config, mock_client, ["resolution:completed"], closer=PR_CLOSER
    )

    handle(mock_client, config, payload)

    priv_issue.add_to_labels.assert_not_called()
    priv_issue.create_comment.assert_not_called()
    pub_issue.create_comment.assert_not_called()
    mock_client.requester.graphql_query.assert_not_called()


@pytest.mark.parametrize("closer", [None, {"__typename": "ProjectV2"}])
def test_closed_by_hand_nudges(config, mock_client, closer):
    payload = _make_payload()
    priv_issue, pub_issue = _setup_mocks(
        config, mock_client, ["unrelated"], closer=closer
    )

    handle(mock_client, config, payload)

    priv_issue.add_to_labels.assert_called_once_with("resolution:none")
    priv_issue.create_comment.assert_called_once()
    pub_issue.create_comment.assert_not_called()
    msg = priv_issue.create_comment.call_args[0][0]
    assert msg == (
        f"Public issue [#42]({PUBLIC_URL}) was closed with no note. "
        "To post one, add a resolution label: `resolution:completed`, "
        "`resolution:not-planned` or `resolution:cannot-reproduce`. "
        "To write your own note instead, comment `/anon <message>` here."
    )


def test_not_mirrored_skips(config, mock_client):
    payload = {
        "action": "closed_check",
        "issue": {
            "number": 10,
            "body": "A regular issue with no markers",
            "state": "closed",
        },
    }

    handle(mock_client, config, payload)
    mock_client.get_repo.assert_not_called()


def test_already_has_resolution_none_skips_adding(config, mock_client):
    payload = _make_payload()
    priv_issue, _ = _setup_mocks(
        config, mock_client, ["resolution:none"]
    )

    handle(mock_client, config, payload)

    # Should still post nudge comment but not add the label again
    priv_issue.add_to_labels.assert_not_called()
    priv_issue.create_comment.assert_called_once()


def test_multiple_resolution_labels_nudges(config, mock_client):
    payload = _make_payload()
    priv_issue, pub_issue = _setup_mocks(
        config, mock_client, ["resolution:completed", "resolution:not-planned"],
        closer=PR_CLOSER,
    )

    handle(mock_client, config, payload)

    # >1 resolution labels means no single resolution; nudge with different message
    priv_issue.add_to_labels.assert_called_once_with("resolution:none")
    priv_issue.create_comment.assert_called_once()
    pub_issue.create_comment.assert_not_called()
    mock_client.requester.graphql_query.assert_not_called()
    msg = priv_issue.create_comment.call_args[0][0]
    assert msg == (
        f"Public issue [#42]({PUBLIC_URL}) was closed with no note because this "
        "issue has 2 resolution labels (`resolution:completed`, "
        "`resolution:not-planned`). Remove them all, then add the one you want; "
        "adding it posts its note."
    )


@pytest.mark.parametrize("closer", [
    PR_CLOSER,
    {
        "__typename": "Commit",
        "url": "https://github.com/testorg/private-repo/commit/abc1234",
    },
])
def test_closed_by_code_marks_completed(config, mock_client, closer):
    priv_issue, pub_issue = _setup_mocks(
        config, mock_client, ["unrelated"], closer=closer
    )

    handle(mock_client, config, _make_payload())

    priv_issue.add_to_labels.assert_called_once_with("resolution:completed")
    pub_issue.create_comment.assert_called_once_with(config.resolution_note("completed"))
    pub_issue.edit.assert_not_called()
    priv_issue.create_comment.assert_called_once_with(
        f"Closed by {closer['url']}: marked `resolution:completed` and posted "
        f"its note on public issue [#42]({PUBLIC_URL})."
    )
    mock_client.get_repo(config.public_repo).get_issue.assert_called_once_with(42)
    mock_client.requester.graphql_query.assert_called_once()
    query, variables = mock_client.requester.graphql_query.call_args[0]
    assert "itemTypes: [CLOSED_EVENT], last: 1" in query
    assert variables == {"owner": "testorg", "name": "private-repo", "number": 10}


def test_stale_close_check_does_not_complete_later_close(config, mock_client):
    priv_issue, pub_issue = _setup_mocks(config, mock_client, [], closer=PR_CLOSER)
    priv_issue.closed_at = datetime(2026, 11, 6, 22, 4, 30, tzinfo=timezone.utc)

    handle(mock_client, config, _make_payload())

    pub_issue.create_comment.assert_not_called()
    pub_issue.edit.assert_not_called()
    priv_issue.add_to_labels.assert_not_called()
    priv_issue.remove_from_labels.assert_not_called()
    priv_issue.create_comment.assert_not_called()

    priv_issue.add_to_labels("resolution:not-planned")
    payload = _make_payload()
    payload["action"] = "labeled"
    payload["label"] = {"name": "resolution:not-planned"}
    payload["issue"]["closed_at"] = "2026-11-06T22:04:30Z"
    private_labels_changed.handle(mock_client, config, payload)

    assert {label.name for label in priv_issue.get_labels()} == {"resolution:not-planned"}
    pub_issue.create_comment.assert_called_once_with(config.resolution_note("not-planned"))
    priv_issue.create_comment.assert_not_called()


def test_reopen_during_closer_lookup_stays_open(config, mock_client):
    priv_issue, pub_issue = _setup_mocks(
        config, mock_client, ["resolution:none"], closer=PR_CLOSER
    )
    priv_repo = mock_client.get_repo(config.private_repo)
    snapshots = []
    get_issue = priv_repo.get_issue.side_effect

    def fetch_issue(number):
        snapshot = get_issue(number)
        snapshots.append(snapshot)
        return snapshot

    priv_repo.get_issue.side_effect = fetch_issue
    closer_response = mock_client.requester.graphql_query.return_value

    def reopen(*args):
        priv_issue.edit(state="open")
        payload = _make_payload()
        payload["action"] = "reopened"
        payload["issue"]["state"] = "open"
        private_issue_reopened.handle(mock_client, config, payload)
        return closer_response

    mock_client.requester.graphql_query.side_effect = reopen

    handle(mock_client, config, _make_payload())

    assert snapshots[0].state == "closed"
    assert priv_repo.get_issue(10).state == "open"
    assert pub_issue.state == "open"
    pub_issue.edit.assert_called_once_with(state="open")
    pub_issue.create_comment.assert_not_called()
    priv_issue.add_to_labels.assert_not_called()
    priv_issue.create_comment.assert_not_called()
    assert list(priv_issue.get_labels()) == []


def test_manual_resolution_during_closer_lookup_wins(config, mock_client):
    priv_issue, pub_issue = _setup_mocks(config, mock_client, [], closer=PR_CLOSER)
    mock_client.get_repo(config.public_repo).get_label.side_effect = GithubException(
        404, {}, {}
    )
    closer_response = mock_client.requester.graphql_query.return_value

    def resolve_manually(*args):
        priv_issue.add_to_labels("resolution:not-planned")
        payload = _make_payload()
        payload["action"] = "labeled"
        payload["label"] = {"name": "resolution:not-planned"}
        private_labels_changed.handle(mock_client, config, payload)
        return closer_response

    mock_client.requester.graphql_query.side_effect = resolve_manually

    handle(mock_client, config, _make_payload())

    assert {label.name for label in priv_issue.get_labels()} == {
        "resolution:not-planned"
    }
    pub_issue.create_comment.assert_called_once_with(config.resolution_note("not-planned"))
    priv_issue.create_comment.assert_not_called()


def test_failed_completed_note_can_be_retried(config, mock_client):
    priv_issue, pub_issue = _setup_mocks(config, mock_client, [], closer=PR_CLOSER)
    pub_issue.create_comment.side_effect = [GithubException(503, {}, {}), MagicMock()]

    with pytest.raises(GithubException) as exc:
        handle(mock_client, config, _make_payload())

    assert exc.value.status == 503
    assert "resolution:completed" not in {
        label.name for label in priv_issue.get_labels()
    }
    priv_issue.add_to_labels.assert_not_called()
    priv_issue.create_comment.assert_not_called()

    handle(mock_client, config, _make_payload())

    note = config.resolution_note("completed")
    assert pub_issue.create_comment.call_args_list == [call(note), call(note)]
    priv_issue.add_to_labels.assert_called_once_with("resolution:completed")
    assert {label.name for label in priv_issue.get_labels()} == {"resolution:completed"}
    priv_issue.create_comment.assert_called_once_with(
        f"Closed by {PR_CLOSER['url']}: marked `resolution:completed` and posted "
        f"its note on public issue [#42]({PUBLIC_URL})."
    )


@pytest.mark.parametrize("response", [
    GithubException(502, {}, {}),
    ({}, {"data": {"repository": None}}),
    ({}, {"data": {"repository": {"issue": {"timelineItems": {"nodes": []}}}}}),
])
def test_closer_lookup_failure_nudges(config, mock_client, response, caplog):
    priv_issue, pub_issue = _setup_mocks(config, mock_client, [], closer=PR_CLOSER)
    if isinstance(response, Exception):
        mock_client.requester.graphql_query.side_effect = response
    else:
        mock_client.requester.graphql_query.return_value = response

    handle(mock_client, config, _make_payload())

    priv_issue.add_to_labels.assert_called_once_with("resolution:none")
    priv_issue.create_comment.assert_called_once()
    assert "To post one, add a resolution label:" in priv_issue.create_comment.call_args[0][0]
    pub_issue.create_comment.assert_not_called()
    assert "WARNING" in caplog.text


def test_closed_by_code_without_completed_label_nudges(config, mock_client):
    config = replace(config, resolution_labels={
        key: value for key, value in config.resolution_labels.items() if key != "completed"
    })
    priv_issue, pub_issue = _setup_mocks(config, mock_client, [], closer=PR_CLOSER)

    handle(mock_client, config, _make_payload())

    priv_issue.add_to_labels.assert_called_once_with("resolution:none")
    priv_issue.create_comment.assert_called_once_with(
        f"Public issue [#42]({PUBLIC_URL}) was closed with no note. "
        "To post one, add a resolution label: `resolution:not-planned` "
        "or `resolution:cannot-reproduce`. "
        "To write your own note instead, comment `/anon <message>` here."
    )
    pub_issue.create_comment.assert_not_called()


def test_completed_uses_config_and_removes_resolution_none(config, mock_client):
    config = replace(config, resolution_labels={
        "completed": ("done:fixed", "The fix is ready.", "completed"),
    }, needs_resolution_label="done:missing")
    priv_issue, pub_issue = _setup_mocks(
        config, mock_client, ["done:missing"], closer=PR_CLOSER
    )
    pub_issue.state = "open"

    handle(mock_client, config, _make_payload())

    priv_issue.add_to_labels.assert_called_once_with("done:fixed")
    priv_issue.remove_from_labels.assert_called_once_with("done:missing")
    pub_issue.create_comment.assert_called_once_with("The fix is ready.")
    pub_issue.edit.assert_called_once_with(state="closed", state_reason="completed")
    priv_issue.create_comment.assert_called_once_with(
        f"Closed by {PR_CLOSER['url']}: marked `done:fixed` and posted "
        f"its note on public issue [#42]({PUBLIC_URL})."
    )
