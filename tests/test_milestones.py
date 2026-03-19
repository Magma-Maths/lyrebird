"""Tests for lyrebird.milestones — shared milestone helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from lyrebird.milestones import (
    find_milestone_by_title,
    milestone_from_payload,
    resolve_or_create_milestone,
    sync_milestone_properties,
)
from tests.conftest import make_mock_milestone


class TestFindMilestoneByTitle:
    def test_finds_open_milestone(self):
        ms = make_mock_milestone(title="v1.0", state="open")
        repo = MagicMock()
        repo.get_milestones.return_value = [ms]

        result = find_milestone_by_title(repo, "v1.0")

        assert result is ms
        repo.get_milestones.assert_any_call(state="open")

    def test_finds_closed_milestone(self):
        repo = MagicMock()
        repo.get_milestones.side_effect = lambda state: (
            [] if state == "open" else [make_mock_milestone(title="v0.9", state="closed")]
        )

        result = find_milestone_by_title(repo, "v0.9")

        assert result is not None
        assert result.title == "v0.9"

    def test_returns_none_when_not_found(self):
        repo = MagicMock()
        repo.get_milestones.return_value = []

        result = find_milestone_by_title(repo, "nonexistent")

        assert result is None

    def test_case_sensitive_matching(self):
        ms = make_mock_milestone(title="V1.0")
        repo = MagicMock()
        repo.get_milestones.return_value = [ms]

        result = find_milestone_by_title(repo, "v1.0")

        assert result is None


class TestResolveOrCreateMilestone:
    def test_returns_existing_milestone(self):
        existing = make_mock_milestone(title="v1.0")
        repo = MagicMock()
        repo.get_milestones.return_value = [existing]

        source = make_mock_milestone(title="v1.0")
        result = resolve_or_create_milestone(repo, source)

        assert result is existing
        repo.create_milestone.assert_not_called()

    def test_creates_milestone_with_all_fields(self):
        from datetime import datetime, timezone

        repo = MagicMock()
        repo.get_milestones.return_value = []

        due = datetime(2026, 6, 1, tzinfo=timezone.utc)
        source = make_mock_milestone(
            title="v2.0",
            description="Second release",
            due_on="2026-06-01T00:00:00Z",
            state="open",
        )

        created = make_mock_milestone(title="v2.0")
        repo.create_milestone.return_value = created

        result = resolve_or_create_milestone(repo, source)

        assert result is created
        repo.create_milestone.assert_called_once_with(
            title="v2.0",
            description="Second release",
            due_on=source.due_on,
            state="open",
        )

    def test_creates_closed_milestone(self):
        repo = MagicMock()
        repo.get_milestones.return_value = []

        source = make_mock_milestone(title="v0.1", state="closed", due_on=None)
        created = make_mock_milestone(title="v0.1", state="closed")
        repo.create_milestone.return_value = created

        result = resolve_or_create_milestone(repo, source)

        assert result is created
        call_kwargs = repo.create_milestone.call_args.kwargs
        assert call_kwargs["state"] == "closed"


class TestSyncMilestoneProperties:
    def test_updates_changed_description(self):
        target = make_mock_milestone(description="old")
        source = make_mock_milestone(description="new")

        result = sync_milestone_properties(target, source)

        assert result is True
        target.edit.assert_called_once()
        call_kwargs = target.edit.call_args.kwargs
        assert call_kwargs["description"] == "new"

    def test_updates_changed_due_date(self):
        from datetime import datetime, timezone

        target = make_mock_milestone(due_on="2026-06-01T00:00:00Z")
        source = make_mock_milestone(due_on="2026-07-01T00:00:00Z")

        result = sync_milestone_properties(target, source)

        assert result is True
        target.edit.assert_called_once()

    def test_updates_changed_state(self):
        target = make_mock_milestone(state="open")
        source = make_mock_milestone(state="closed")

        result = sync_milestone_properties(target, source)

        assert result is True
        call_kwargs = target.edit.call_args.kwargs
        assert call_kwargs["state"] == "closed"

    def test_no_op_when_identical(self):
        target = make_mock_milestone(
            description="same", due_on="2026-06-01T00:00:00Z", state="open"
        )
        source = make_mock_milestone(
            description="same", due_on="2026-06-01T00:00:00Z", state="open"
        )

        result = sync_milestone_properties(target, source)

        assert result is False
        target.edit.assert_not_called()
