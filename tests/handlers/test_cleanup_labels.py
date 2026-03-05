"""Tests for _cleanup_labels shared helper."""

from __future__ import annotations

from unittest.mock import MagicMock

from lyrebird.handlers._cleanup_labels import cleanup_private_resolution_labels


def test_removes_all_resolution_and_status_labels(config):
    priv_issue = MagicMock()
    labels = []
    for name in [
        "resolution:completed",
        "resolution:none",
    ]:
        lbl = MagicMock()
        lbl.name = name
        labels.append(lbl)
    priv_issue.get_labels.return_value = labels

    cleanup_private_resolution_labels(config, priv_issue)

    removed = {c[0][0] for c in priv_issue.remove_from_labels.call_args_list}
    assert removed == {
        "resolution:completed",
        "resolution:none",
    }


def test_unrelated_labels_untouched(config):
    priv_issue = MagicMock()
    lbl = MagicMock()
    lbl.name = "bug"
    priv_issue.get_labels.return_value = [lbl]

    cleanup_private_resolution_labels(config, priv_issue)

    priv_issue.remove_from_labels.assert_not_called()


def test_missing_labels_no_error(config):
    priv_issue = MagicMock()
    lbl = MagicMock()
    lbl.name = "resolution:completed"
    priv_issue.get_labels.return_value = [lbl]
    priv_issue.remove_from_labels.side_effect = Exception("not found")

    # Should not raise
    cleanup_private_resolution_labels(config, priv_issue)


def test_empty_labels_no_error(config):
    """No labels at all — nothing to remove, no error."""
    priv_issue = MagicMock()
    priv_issue.get_labels.return_value = []

    cleanup_private_resolution_labels(config, priv_issue)

    priv_issue.remove_from_labels.assert_not_called()


def test_multiple_resolution_labels(config):
    """All resolution label variants are removed when present."""
    priv_issue = MagicMock()
    labels = []
    for name in [
        "resolution:completed",
        "resolution:not-planned",
        "resolution:cannot-reproduce",
    ]:
        lbl = MagicMock()
        lbl.name = name
        labels.append(lbl)
    priv_issue.get_labels.return_value = labels

    cleanup_private_resolution_labels(config, priv_issue)

    removed = {c[0][0] for c in priv_issue.remove_from_labels.call_args_list}
    assert removed == {
        "resolution:completed",
        "resolution:not-planned",
        "resolution:cannot-reproduce",
    }


def test_partial_match_only_removes_matching(config):
    """Only cleanup-eligible labels are removed; others stay."""
    priv_issue = MagicMock()
    labels = []
    for name in ["resolution:completed", "bug", "enhancement"]:
        lbl = MagicMock()
        lbl.name = name
        labels.append(lbl)
    priv_issue.get_labels.return_value = labels

    cleanup_private_resolution_labels(config, priv_issue)

    removed = {c[0][0] for c in priv_issue.remove_from_labels.call_args_list}
    assert removed == {"resolution:completed"}
    assert "bug" not in removed
    assert "enhancement" not in removed
