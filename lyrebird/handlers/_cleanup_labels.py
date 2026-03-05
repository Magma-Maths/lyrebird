"""Shared helper to remove resolution-related labels from a private issue."""

from __future__ import annotations

from lyrebird.config import Config


def cleanup_private_resolution_labels(config: Config, priv_issue) -> None:
    """Remove all resolution, needs-resolution, and public:closed labels."""
    current_labels = {lbl.name for lbl in priv_issue.get_labels()}
    to_remove = (
        config.all_resolution_label_names()
        | {config.needs_resolution_label, config.closed_label, config.closed_by_reporter_label}
    ) & current_labels

    for lbl_name in to_remove:
        try:
            priv_issue.remove_from_labels(lbl_name)
        except Exception:
            pass
