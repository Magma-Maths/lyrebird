"""Tests for lyrebird.sync — daily reconciliation of public/private issues."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lyrebird.sync import SyncStats, sync
from tests.conftest import make_mock_comment


def _make_pub_issue(
    number=42,
    node_id="I_kwDOTest",
    title="Bug report",
    body="Something is broken",
    labels=None,
    user_login="reporter",
    html_url=None,
    state="open",
    state_reason=None,
):
    """Create a mock public issue (PyGithub Issue-like)."""
    issue = MagicMock()
    issue.number = number
    issue.title = title
    issue.body = body
    issue.state = state
    issue.html_url = html_url or f"https://github.com/testorg/public-repo/issues/{number}"
    issue.pull_request = None  # Not a PR
    issue.raw_data = {
        "node_id": node_id,
        "type": None,
        "state_reason": state_reason,
    }
    issue.user = MagicMock()
    issue.user.login = user_login

    label_mocks = []
    for lbl in labels or []:
        m = MagicMock()
        m.name = lbl["name"]
        m.color = lbl.get("color", "ededed")
        m.description = lbl.get("description", "")
        label_mocks.append(m)
    issue.labels = label_mocks
    issue.get_comments = MagicMock(return_value=[])
    return issue


def _make_priv_issue(
    number=100,
    title="[public #42] Bug report",
    body=None,
    labels=None,
    state="open",
):
    """Create a mock private issue."""
    if body is None:
        body = (
            "**Public issue**: https://github.com/testorg/public-repo/issues/42\n"
            "**Author**: @reporter\n"
            "\n"
            "<!-- BEGIN PUBLIC BODY -->\n"
            "Something is broken\n"
            "<!-- END PUBLIC BODY -->\n"
            "\n"
            "<!-- public_issue_url: https://github.com/testorg/public-repo/issues/42 -->\n"
            "<!-- public_issue_node_id: I_kwDOTest -->"
        )
    issue = MagicMock()
    issue.number = number
    issue.title = title
    issue.body = body
    issue.state = state
    issue.pull_request = None

    label_mocks = []
    for name in labels or []:
        m = MagicMock()
        m.name = name
        label_mocks.append(m)
    issue.get_labels.return_value = label_mocks
    issue.get_comments = MagicMock(return_value=[])
    issue.get_events = MagicMock(return_value=[])
    return issue


def _setup_repos(config, mock_client, pub_issues, priv_issues=None):
    """Wire up mock repos and client.get_repo routing.

    Returns (pub_repo, priv_repo).
    """
    pub_repo = MagicMock()
    pub_repo.get_issues.return_value = pub_issues

    priv_repo = MagicMock()
    priv_repo.get_issues.return_value = priv_issues or []

    def get_repo(name):
        if name == config.public_repo:
            return pub_repo
        return priv_repo

    mock_client.get_repo.side_effect = get_repo
    return pub_repo, priv_repo


MAPPING_BODY = (
    "<!-- mapping: public_issue_node_id=I_kwDOTest private_issue_number=100 -->"
)


# ── Creation ─────────────────────────────────────────────────────────────────


class TestCreatesMissingPrivateIssue:
    def test_creates_private_issue_and_mapping_comment(self, config, mock_client):
        """When a public issue has no mirror, sync creates one + mapping comment."""
        pub_issue = _make_pub_issue()
        priv_issue = _make_priv_issue()

        pub_repo, priv_repo = _setup_repos(config, mock_client, [pub_issue])
        pub_repo.get_issue.return_value = pub_issue
        priv_repo.create_issue.return_value = priv_issue

        # resolve_mapping finds nothing
        pub_issue.get_comments.return_value = []

        stats = sync(mock_client, config, since_hours=None)

        assert stats.created == 1
        assert stats.scanned == 1
        priv_repo.create_issue.assert_called_once()
        pub_issue.create_comment.assert_called_once()
        assert "<!-- mapping:" in pub_issue.create_comment.call_args[0][0]

    def test_closes_new_mirror_when_public_already_closed(self, config, mock_client):
        """When mirroring a closed public issue, the new private issue is also closed."""
        pub_issue = _make_pub_issue(state="closed", state_reason="completed")
        priv_issue = _make_priv_issue()

        pub_repo, priv_repo = _setup_repos(config, mock_client, [pub_issue])
        pub_repo.get_issue.return_value = pub_issue
        priv_repo.create_issue.return_value = priv_issue
        pub_issue.get_comments.return_value = []

        stats = sync(mock_client, config, since_hours=None)

        assert stats.created == 1
        assert stats.state_updated == 1
        priv_issue.edit.assert_any_call(state="closed", state_reason="completed")


class TestSkipsAlreadyMirroredIssue:
    def test_no_creation_when_mapping_exists(self, config, mock_client):
        """When a mapping comment exists, sync doesn't create a new private issue."""
        priv_issue = _make_priv_issue()
        mapping_comment = make_mock_comment(body=MAPPING_BODY)

        pub_issue = _make_pub_issue()
        pub_issue.get_comments.return_value = [mapping_comment]

        pub_repo, priv_repo = _setup_repos(config, mock_client, [pub_issue])
        pub_repo.get_issue.return_value = pub_issue
        priv_repo.get_issue.return_value = priv_issue

        stats = sync(mock_client, config, since_hours=None)

        assert stats.created == 0
        assert stats.scanned == 1
        priv_repo.create_issue.assert_not_called()


# ── Title / Body sync ───────────────────────────────────────────────────────


class TestUpdatesStaleTitle:
    def test_updates_title_when_drifted(self, config, mock_client):
        priv_issue = _make_priv_issue(title="[public #42] Old title")
        mapping_comment = make_mock_comment(body=MAPPING_BODY)

        pub_issue = _make_pub_issue(title="New title")
        pub_issue.get_comments.return_value = [mapping_comment]

        pub_repo, priv_repo = _setup_repos(config, mock_client, [pub_issue])
        pub_repo.get_issue.return_value = pub_issue
        priv_repo.get_issue.return_value = priv_issue

        stats = sync(mock_client, config, since_hours=None)

        assert stats.titles_updated == 1
        priv_issue.edit.assert_any_call(title="[public #42] New title")


class TestUpdatesStaleBody:
    def test_updates_body_when_public_section_drifted(self, config, mock_client):
        old_body = (
            "**Public issue**: https://github.com/testorg/public-repo/issues/42\n"
            "**Author**: @reporter\n"
            "\n"
            "<!-- BEGIN PUBLIC BODY -->\n"
            "Old body text\n"
            "<!-- END PUBLIC BODY -->\n"
            "\n"
            "<!-- public_issue_url: https://github.com/testorg/public-repo/issues/42 -->\n"
            "<!-- public_issue_node_id: I_kwDOTest -->"
        )
        priv_issue = _make_priv_issue(body=old_body)
        mapping_comment = make_mock_comment(body=MAPPING_BODY)

        pub_issue = _make_pub_issue(body="Updated body text")
        pub_issue.get_comments.return_value = [mapping_comment]

        pub_repo, priv_repo = _setup_repos(config, mock_client, [pub_issue])
        pub_repo.get_issue.return_value = pub_issue
        priv_repo.get_issue.return_value = priv_issue

        stats = sync(mock_client, config, since_hours=None)

        assert stats.bodies_updated == 1
        body_call = [c for c in priv_issue.edit.call_args_list if "body" in c.kwargs]
        assert len(body_call) == 1
        assert "Updated body text" in body_call[0].kwargs["body"]


# ── State sync ───────────────────────────────────────────────────────────────


class TestSyncsStatePublicToPrivate:
    def test_closes_private_when_public_closed(self, config, mock_client):
        """Public closed + last private event by bot → close private."""
        priv_issue = _make_priv_issue(state="open")
        bot_event = MagicMock()
        bot_event.event = "reopened"
        bot_event.actor.login = config.bot_login
        priv_issue.get_events.return_value = [bot_event]

        mapping_comment = make_mock_comment(body=MAPPING_BODY)
        pub_issue = _make_pub_issue(state="closed", state_reason="completed")
        pub_issue.get_comments.return_value = [mapping_comment]

        pub_repo, priv_repo = _setup_repos(config, mock_client, [pub_issue])
        pub_repo.get_issue.return_value = pub_issue
        priv_repo.get_issue.return_value = priv_issue

        stats = sync(mock_client, config, since_hours=None)

        assert stats.state_updated == 1
        priv_issue.edit.assert_any_call(state="closed", state_reason="completed")

    def test_reopens_private_when_public_reopened(self, config, mock_client):
        """Public open + last private event by bot → reopen private."""
        priv_issue = _make_priv_issue(state="closed")
        bot_event = MagicMock()
        bot_event.event = "closed"
        bot_event.actor.login = config.bot_login
        priv_issue.get_events.return_value = [bot_event]

        mapping_comment = make_mock_comment(body=MAPPING_BODY)
        pub_issue = _make_pub_issue(state="open")
        pub_issue.get_comments.return_value = [mapping_comment]

        pub_repo, priv_repo = _setup_repos(config, mock_client, [pub_issue])
        pub_repo.get_issue.return_value = pub_issue
        priv_repo.get_issue.return_value = priv_issue

        stats = sync(mock_client, config, since_hours=None)

        assert stats.state_updated == 1
        priv_issue.edit.assert_any_call(state="open")


class TestSyncsStatePrivateToPublic:
    def test_closes_public_when_human_closed_private(self, config, mock_client):
        """Human closed private → sync should close public (missed cascade)."""
        priv_issue = _make_priv_issue(state="closed")
        human_event = MagicMock()
        human_event.event = "closed"
        human_event.actor.login = "some-human"
        priv_issue.get_events.return_value = [human_event]

        mapping_comment = make_mock_comment(body=MAPPING_BODY)
        pub_issue = _make_pub_issue(state="open")
        pub_issue.get_comments.return_value = [mapping_comment]

        pub_repo, priv_repo = _setup_repos(config, mock_client, [pub_issue])
        pub_repo.get_issue.return_value = pub_issue
        priv_repo.get_issue.return_value = priv_issue

        stats = sync(mock_client, config, since_hours=None)

        assert stats.state_updated == 1
        pub_issue.edit.assert_any_call(state="closed", state_reason="completed")

    def test_closes_public_with_resolution_note(self, config, mock_client):
        """Human closed private with resolution label → posts note on public."""
        priv_issue = _make_priv_issue(
            state="closed", labels=["resolution:completed"]
        )
        human_event = MagicMock()
        human_event.event = "closed"
        human_event.actor.login = "some-human"
        priv_issue.get_events.return_value = [human_event]

        mapping_comment = make_mock_comment(body=MAPPING_BODY)
        pub_issue = _make_pub_issue(state="open")
        pub_issue.get_comments.return_value = [mapping_comment]

        pub_repo, priv_repo = _setup_repos(config, mock_client, [pub_issue])
        pub_repo.get_issue.return_value = pub_issue
        priv_repo.get_issue.return_value = priv_issue

        stats = sync(mock_client, config, since_hours=None)

        assert stats.state_updated == 1
        pub_issue.edit.assert_any_call(state="closed", state_reason="completed")
        # Resolution note posted
        pub_issue.create_comment.assert_called_once()
        note = pub_issue.create_comment.call_args[0][0]
        assert "fixed" in note.lower()

    def test_reopens_public_when_human_reopened_private(self, config, mock_client):
        """Human reopened private → sync should reopen public."""
        priv_issue = _make_priv_issue(state="open")
        human_event = MagicMock()
        human_event.event = "reopened"
        human_event.actor.login = "some-human"
        priv_issue.get_events.return_value = [human_event]

        mapping_comment = make_mock_comment(body=MAPPING_BODY)
        pub_issue = _make_pub_issue(state="closed")
        pub_issue.get_comments.return_value = [mapping_comment]

        pub_repo, priv_repo = _setup_repos(config, mock_client, [pub_issue])
        pub_repo.get_issue.return_value = pub_issue
        priv_repo.get_issue.return_value = priv_issue

        stats = sync(mock_client, config, since_hours=None)

        assert stats.state_updated == 1
        pub_issue.edit.assert_any_call(state="open")

    def test_no_state_change_when_states_match(self, config, mock_client):
        """No state sync when both issues have the same state."""
        priv_issue = _make_priv_issue(state="open")
        mapping_comment = make_mock_comment(body=MAPPING_BODY)

        pub_issue = _make_pub_issue(state="open")
        pub_issue.get_comments.return_value = [mapping_comment]

        pub_repo, priv_repo = _setup_repos(config, mock_client, [pub_issue])
        pub_repo.get_issue.return_value = pub_issue
        priv_repo.get_issue.return_value = priv_issue

        stats = sync(mock_client, config, since_hours=None)

        assert stats.state_updated == 0
        state_edits = [
            c for c in priv_issue.edit.call_args_list if "state" in c.kwargs
        ]
        assert not state_edits

    def test_no_events_means_public_authoritative(self, config, mock_client):
        """When private issue has no state events, public state wins."""
        priv_issue = _make_priv_issue(state="open")
        priv_issue.get_events.return_value = []  # no events

        mapping_comment = make_mock_comment(body=MAPPING_BODY)
        pub_issue = _make_pub_issue(state="closed", state_reason="not_planned")
        pub_issue.get_comments.return_value = [mapping_comment]

        pub_repo, priv_repo = _setup_repos(config, mock_client, [pub_issue])
        pub_repo.get_issue.return_value = pub_issue
        priv_repo.get_issue.return_value = priv_issue

        stats = sync(mock_client, config, since_hours=None)

        assert stats.state_updated == 1
        priv_issue.edit.assert_any_call(state="closed", state_reason="not_planned")


# ── Pass 2: Private-to-public cascade ────────────────────────────────────────


class TestPrivatePass:
    def test_catches_missed_private_to_public_close(self, config, mock_client):
        """Pass 2 closes public when human closed private (not seen in pass 1)."""
        priv_issue = _make_priv_issue(state="closed")
        human_event = MagicMock()
        human_event.event = "closed"
        human_event.actor.login = "some-human"
        priv_issue.get_events.return_value = [human_event]

        pub_issue = _make_pub_issue(state="open")

        # Pass 1 finds no public issues; pass 2 finds the private issue
        pub_repo, priv_repo = _setup_repos(
            config, mock_client, [], [priv_issue]
        )
        pub_repo.get_issue.return_value = pub_issue

        stats = sync(mock_client, config, since_hours=None)

        assert stats.state_updated == 1
        pub_issue.edit.assert_called_once_with(
            state="closed", state_reason="completed"
        )

    def test_skips_already_seen_private_issues(self, config, mock_client):
        """Pass 2 skips private issues already handled in pass 1."""
        priv_issue = _make_priv_issue(state="open")
        mapping_comment = make_mock_comment(body=MAPPING_BODY)

        pub_issue = _make_pub_issue(state="open")
        pub_issue.get_comments.return_value = [mapping_comment]

        # Same private issue appears in both passes
        pub_repo, priv_repo = _setup_repos(
            config, mock_client, [pub_issue], [priv_issue]
        )
        pub_repo.get_issue.return_value = pub_issue
        priv_repo.get_issue.return_value = priv_issue

        stats = sync(mock_client, config, since_hours=None)

        # No double-processing
        assert stats.state_updated == 0

    def test_skips_non_mirror_private_issues(self, config, mock_client):
        """Pass 2 skips private issues that aren't mirrors (no body markers)."""
        native_issue = MagicMock()
        native_issue.number = 999
        native_issue.body = "Just a regular private issue with no markers"
        native_issue.state = "closed"
        native_issue.pull_request = None
        native_issue.get_events = MagicMock(return_value=[])

        pub_repo, priv_repo = _setup_repos(
            config, mock_client, [], [native_issue]
        )

        stats = sync(mock_client, config, since_hours=None)

        assert stats.state_updated == 0
        pub_repo.get_issue.assert_not_called()

    def test_skips_bot_state_change_in_pass2(self, config, mock_client):
        """Pass 2 skips if the private state change was by the bot."""
        priv_issue = _make_priv_issue(state="closed")
        bot_event = MagicMock()
        bot_event.event = "closed"
        bot_event.actor.login = config.bot_login
        priv_issue.get_events.return_value = [bot_event]

        pub_issue = _make_pub_issue(state="open")

        pub_repo, priv_repo = _setup_repos(
            config, mock_client, [], [priv_issue]
        )
        pub_repo.get_issue.return_value = pub_issue

        stats = sync(mock_client, config, since_hours=None)

        assert stats.state_updated == 0
        pub_issue.edit.assert_not_called()


# ── Comments ─────────────────────────────────────────────────────────────────


class TestMirrorsMissingComment:
    def test_creates_mirrored_comment(self, config, mock_client):
        priv_issue = _make_priv_issue()
        priv_issue.get_comments.return_value = []
        mapping_comment = make_mock_comment(body=MAPPING_BODY)

        pub_comment = make_mock_comment(
            comment_id=500,
            body="Help, this is urgent!",
            user_login="someone",
        )
        pub_issue = _make_pub_issue()
        pub_issue.get_comments.return_value = [mapping_comment, pub_comment]

        pub_repo, priv_repo = _setup_repos(config, mock_client, [pub_issue])
        pub_repo.get_issue.return_value = pub_issue
        priv_repo.get_issue.return_value = priv_issue

        stats = sync(mock_client, config, since_hours=None)

        assert stats.comments_mirrored == 1
        priv_issue.create_comment.assert_called_once()
        mirrored_body = priv_issue.create_comment.call_args[0][0]
        assert "<!-- public_comment_id: 500 -->" in mirrored_body
        assert "Help, this is urgent!" in mirrored_body


class TestSkipsAlreadyMirroredComment:
    def test_no_duplicate_when_comment_already_mirrored(self, config, mock_client):
        """When a comment is already mirrored (and up to date), no action taken."""
        pub_comment = make_mock_comment(
            comment_id=500,
            body="Already here",
            user_login="commenter",
            html_url="https://example.com/500",
        )
        # Build the priv comment body to exactly match what build_mirrored_comment_body produces
        priv_comment = make_mock_comment(
            body=(
                "From @commenter at https://example.com/500:\n\n"
                "Already here\n\n"
                "<!-- public_comment_id: 500 -->"
            )
        )
        priv_issue = _make_priv_issue()
        priv_issue.get_comments.return_value = [priv_comment]

        mapping_comment = make_mock_comment(body=MAPPING_BODY)
        pub_issue = _make_pub_issue()
        pub_issue.get_comments.return_value = [mapping_comment, pub_comment]

        pub_repo, priv_repo = _setup_repos(config, mock_client, [pub_issue])
        pub_repo.get_issue.return_value = pub_issue
        priv_repo.get_issue.return_value = priv_issue

        stats = sync(mock_client, config, since_hours=None)

        assert stats.comments_mirrored == 0
        assert stats.comments_updated == 0
        priv_issue.create_comment.assert_not_called()


class TestSkipsMappingComments:
    def test_does_not_mirror_mapping_comment(self, config, mock_client):
        priv_issue = _make_priv_issue()
        priv_issue.get_comments.return_value = []

        mapping_comment = make_mock_comment(
            body="Thanks for the report!\n\n" + MAPPING_BODY
        )
        pub_issue = _make_pub_issue()
        pub_issue.get_comments.return_value = [mapping_comment]

        pub_repo, priv_repo = _setup_repos(config, mock_client, [pub_issue])
        pub_repo.get_issue.return_value = pub_issue
        priv_repo.get_issue.return_value = priv_issue

        stats = sync(mock_client, config, since_hours=None)

        assert stats.comments_mirrored == 0
        priv_issue.create_comment.assert_not_called()


class TestUpdatesEditedComments:
    def test_updates_mirrored_comment_when_content_differs(self, config, mock_client):
        priv_comment = make_mock_comment(
            body=(
                "From @someone at https://example.com/500:\n\n"
                "Old content\n\n"
                "<!-- public_comment_id: 500 -->"
            )
        )
        priv_issue = _make_priv_issue()
        priv_issue.get_comments.return_value = [priv_comment]

        mapping_comment = make_mock_comment(body=MAPPING_BODY)
        pub_comment = make_mock_comment(
            comment_id=500,
            body="New content",
            user_login="someone",
            html_url="https://example.com/500",
        )
        pub_issue = _make_pub_issue()
        pub_issue.get_comments.return_value = [mapping_comment, pub_comment]

        pub_repo, priv_repo = _setup_repos(config, mock_client, [pub_issue])
        pub_repo.get_issue.return_value = pub_issue
        priv_repo.get_issue.return_value = priv_issue

        stats = sync(mock_client, config, since_hours=None)

        assert stats.comments_updated == 1
        priv_comment.edit.assert_called_once()
        assert "New content" in priv_comment.edit.call_args.kwargs["body"]


class TestTombstonesDeletedComments:
    def test_tombstones_orphaned_mirror(self, config, mock_client):
        """When a public comment is deleted, sync tombstones the private mirror."""
        priv_comment = make_mock_comment(
            body=(
                "From @someone at https://example.com/500:\n\n"
                "Original content\n\n"
                "<!-- public_comment_id: 500 -->"
            )
        )
        priv_issue = _make_priv_issue()
        priv_issue.get_comments.return_value = [priv_comment]

        # Public has no comments (the one with id 500 was deleted)
        mapping_comment = make_mock_comment(body=MAPPING_BODY)
        pub_issue = _make_pub_issue()
        pub_issue.get_comments.return_value = [mapping_comment]

        pub_repo, priv_repo = _setup_repos(config, mock_client, [pub_issue])
        pub_repo.get_issue.return_value = pub_issue
        priv_repo.get_issue.return_value = priv_issue

        stats = sync(mock_client, config, since_hours=None)

        assert stats.comments_tombstoned == 1
        priv_comment.edit.assert_called_once()
        assert "deleted on public" in priv_comment.edit.call_args.kwargs["body"]

    def test_skips_already_tombstoned_comment(self, config, mock_client):
        """Don't re-tombstone a comment that's already tombstoned."""
        priv_comment = make_mock_comment(
            body=(
                "From @someone at https://example.com/500:\n\n"
                "*(deleted on public at 2026-01-01T00:00:00)*\n\n"
                "<!-- public_comment_id: 500 -->"
            )
        )
        priv_issue = _make_priv_issue()
        priv_issue.get_comments.return_value = [priv_comment]

        mapping_comment = make_mock_comment(body=MAPPING_BODY)
        pub_issue = _make_pub_issue()
        pub_issue.get_comments.return_value = [mapping_comment]

        pub_repo, priv_repo = _setup_repos(config, mock_client, [pub_issue])
        pub_repo.get_issue.return_value = pub_issue
        priv_repo.get_issue.return_value = priv_issue

        stats = sync(mock_client, config, since_hours=None)

        assert stats.comments_tombstoned == 0
        priv_comment.edit.assert_not_called()


# ── Labels ───────────────────────────────────────────────────────────────────


class TestSyncsMissingLabel:
    def test_adds_missing_label_to_private(self, config, mock_client):
        priv_issue = _make_priv_issue(labels=[])
        mapping_comment = make_mock_comment(body=MAPPING_BODY)

        pub_issue = _make_pub_issue(labels=[{"name": "bug", "color": "d73a4a"}])
        pub_issue.get_comments.return_value = [mapping_comment]

        pub_repo, priv_repo = _setup_repos(config, mock_client, [pub_issue])
        pub_repo.get_issue.return_value = pub_issue
        priv_repo.get_issue.return_value = priv_issue

        stats = sync(mock_client, config, since_hours=None)

        assert stats.labels_synced == 1
        priv_issue.add_to_labels.assert_called_once_with("bug")


class TestRemovesExtraLabels:
    def test_removes_non_protected_label_not_on_public(self, config, mock_client):
        priv_issue = _make_priv_issue(labels=["stale"])
        mapping_comment = make_mock_comment(body=MAPPING_BODY)

        pub_issue = _make_pub_issue(labels=[])
        pub_issue.get_comments.return_value = [mapping_comment]

        pub_repo, priv_repo = _setup_repos(config, mock_client, [pub_issue])
        pub_repo.get_issue.return_value = pub_issue
        priv_repo.get_issue.return_value = priv_issue

        stats = sync(mock_client, config, since_hours=None)

        assert stats.labels_synced == 1
        priv_issue.remove_from_labels.assert_called_once_with("stale")


class TestProtectsResolutionLabels:
    def test_does_not_remove_resolution_label(self, config, mock_client):
        """Resolution labels on private should never be removed by sync."""
        priv_issue = _make_priv_issue(labels=["resolution:completed"])
        mapping_comment = make_mock_comment(body=MAPPING_BODY)

        pub_issue = _make_pub_issue(labels=[])
        pub_issue.get_comments.return_value = [mapping_comment]

        pub_repo, priv_repo = _setup_repos(config, mock_client, [pub_issue])
        pub_repo.get_issue.return_value = pub_issue
        priv_repo.get_issue.return_value = priv_issue

        stats = sync(mock_client, config, since_hours=None)

        priv_issue.remove_from_labels.assert_not_called()

    def test_does_not_remove_needs_resolution_label(self, config, mock_client):
        """The needs-resolution label should never be removed by sync."""
        priv_issue = _make_priv_issue(labels=["resolution:none"])
        mapping_comment = make_mock_comment(body=MAPPING_BODY)

        pub_issue = _make_pub_issue(labels=[])
        pub_issue.get_comments.return_value = [mapping_comment]

        pub_repo, priv_repo = _setup_repos(config, mock_client, [pub_issue])
        pub_repo.get_issue.return_value = pub_issue
        priv_repo.get_issue.return_value = priv_issue

        stats = sync(mock_client, config, since_hours=None)

        priv_issue.remove_from_labels.assert_not_called()

    def test_removes_non_protected_but_keeps_resolution(self, config, mock_client):
        """Sync removes non-protected extras but preserves resolution labels."""
        priv_issue = _make_priv_issue(labels=["stale", "resolution:completed"])
        mapping_comment = make_mock_comment(body=MAPPING_BODY)

        pub_issue = _make_pub_issue(labels=[])
        pub_issue.get_comments.return_value = [mapping_comment]

        pub_repo, priv_repo = _setup_repos(config, mock_client, [pub_issue])
        pub_repo.get_issue.return_value = pub_issue
        priv_repo.get_issue.return_value = priv_issue

        stats = sync(mock_client, config, since_hours=None)

        assert stats.labels_synced == 1
        priv_issue.remove_from_labels.assert_called_once_with("stale")


# ── Error handling ───────────────────────────────────────────────────────────


class TestReportsErrors:
    def test_records_error_and_continues(self, config, mock_client):
        good_issue = _make_pub_issue(number=1, node_id="I_good")
        bad_issue = _make_pub_issue(number=2, node_id="I_bad")

        # bad_issue raises on get_comments (during resolve_mapping)
        bad_issue.get_comments.side_effect = RuntimeError("API error")

        mapping_comment = make_mock_comment(
            body="<!-- mapping: public_issue_node_id=I_good private_issue_number=100 -->"
        )
        good_issue.get_comments.return_value = [mapping_comment]

        priv_issue = _make_priv_issue(number=100)

        pub_repo, priv_repo = _setup_repos(
            config, mock_client, [bad_issue, good_issue]
        )

        def get_pub_issue(num):
            if num == 1:
                return good_issue
            if num == 2:
                mock = MagicMock()
                mock.get_comments.side_effect = RuntimeError("API error")
                return mock
            return MagicMock()

        pub_repo.get_issue.side_effect = get_pub_issue
        priv_repo.get_issue.return_value = priv_issue

        stats = sync(mock_client, config, since_hours=None)

        assert stats.scanned == 2
        assert len(stats.errors) == 1
        assert "public #2" in stats.errors[0]


# ── SyncStats ────────────────────────────────────────────────────────────────


class TestSyncStats:
    def test_summary_format(self):
        stats = SyncStats(
            scanned=10,
            created=1,
            titles_updated=2,
            bodies_updated=3,
            comments_mirrored=4,
            labels_synced=5,
        )
        summary = stats.summary()
        assert "Scanned: 10" in summary
        assert "Created: 1" in summary
        assert "Errors: 0" in summary

    def test_summary_with_errors(self):
        stats = SyncStats(scanned=5, errors=["public #1: boom"])
        summary = stats.summary()
        assert "Errors: 1" in summary
        assert "public #1: boom" in summary
