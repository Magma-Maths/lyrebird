"""Load configuration from environment variables."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


# Default public close notes keyed by resolution key.
DEFAULT_RESOLUTION_NOTES: dict[str, tuple[str, str | None]] = {
    "completed": (
        "Fixed on main. Thanks for the report. "
        "If you still see this after updating, please comment here with details.",
        "completed",
    ),
    "not-planned": (
        "Closing as not planned at this time. "
        "Thanks for taking the time to report it.",
        "not_planned",
    ),
    "cannot-reproduce": (
        "We could not reproduce this with the information available. "
        "If you can share steps/logs, we can reopen.",
        "not_planned",
    ),
}


@dataclass(frozen=True)
class Config:
    """Immutable runtime configuration."""

    public_repo: str
    private_repo: str
    bot_login: str

    # resolution key -> (label name, public note, optional state_reason)
    resolution_labels: dict[str, tuple[str, str, str | None]] = field(
        default_factory=dict
    )

    mapping_comment_template: str = (
        "Internal tracking: {private_repo}#{private_issue_number}"
    )
    closed_label: str = "public:closed"
    closed_by_reporter_label: str = "public:closed-by-reporter"
    needs_resolution_label: str = "needs-public-resolution"

    @property
    def public_owner(self) -> str:
        return self.public_repo.split("/")[0]

    @property
    def public_name(self) -> str:
        return self.public_repo.split("/")[1]

    @property
    def private_owner(self) -> str:
        return self.private_repo.split("/")[0]

    @property
    def private_name(self) -> str:
        return self.private_repo.split("/")[1]

    def resolution_label_name(self, key: str) -> str | None:
        """Return the label name for a resolution key, or None."""
        entry = self.resolution_labels.get(key)
        return entry[0] if entry else None

    def resolution_note(self, key: str) -> str | None:
        entry = self.resolution_labels.get(key)
        return entry[1] if entry else None

    def resolution_state_reason(self, key: str) -> str | None:
        entry = self.resolution_labels.get(key)
        return entry[2] if entry else None

    def all_resolution_label_names(self) -> set[str]:
        return {v[0] for v in self.resolution_labels.values()}

    def resolution_key_for_label(self, label_name: str) -> str | None:
        """Return the resolution key for a given label name, or None."""
        for key, (name, _, _) in self.resolution_labels.items():
            if name == label_name:
                return key
        return None


def _build_resolution_labels(
    raw: str | None,
) -> dict[str, tuple[str, str, str | None]]:
    """Parse RESOLUTION_LABELS JSON or build defaults.

    Expected JSON format:
    {
        "completed": {"label": "external:completed", "note": "...", "state_reason": "completed"},
        ...
    }
    If not provided, uses DEFAULT_RESOLUTION_NOTES with label prefix "external:".
    """
    if raw:
        data = json.loads(raw)
        result: dict[str, tuple[str, str, str | None]] = {}
        for key, val in data.items():
            result[key] = (
                val["label"],
                val["note"],
                val.get("state_reason"),
            )
        return result

    # Default: key -> (external:<key>, default note, default state_reason)
    result = {}
    for key, (note, state_reason) in DEFAULT_RESOLUTION_NOTES.items():
        result[key] = (f"external:{key}", note, state_reason)
    return result


def load_config() -> Config:
    """Build Config from environment variables."""
    return Config(
        public_repo=os.environ["PUBLIC_REPO"],
        private_repo=os.environ["PRIVATE_REPO"],
        bot_login=os.environ.get("BOT_LOGIN", "lyrebird[bot]"),
        resolution_labels=_build_resolution_labels(
            os.environ.get("RESOLUTION_LABELS")
        ),
        mapping_comment_template=os.environ.get(
            "MAPPING_COMMENT_TEMPLATE",
            "Internal tracking: {private_repo}#{private_issue_number}",
        ),
        closed_label=os.environ.get("CLOSED_LABEL", "public:closed"),
        closed_by_reporter_label=os.environ.get(
            "CLOSED_BY_REPORTER_LABEL", "public:closed-by-reporter"
        ),
        needs_resolution_label=os.environ.get(
            "NEEDS_RESOLUTION_LABEL", "needs-public-resolution"
        ),
    )
