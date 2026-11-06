"""Post a configured resolution on the public issue."""

from __future__ import annotations

from collections.abc import Iterable

from lyrebird.config import Config


def post_resolution(
    config: Config,
    priv_issue,
    pub_issue,
    resolution_key: str,
    current_labels: Iterable[str],
) -> None:
    note = config.resolution_note(resolution_key)
    if note:
        pub_issue.create_comment(note)

    if pub_issue.state != "closed":
        state_reason = config.resolution_state_reason(resolution_key)
        if state_reason:
            pub_issue.edit(state="closed", state_reason=state_reason)
        else:
            pub_issue.edit(state="closed")

    if config.needs_resolution_label in current_labels:
        try:
            priv_issue.remove_from_labels(config.needs_resolution_label)
        except Exception:
            pass
