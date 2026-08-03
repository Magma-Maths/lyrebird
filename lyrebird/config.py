"""Load configuration from environment variables."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# Default public close notes keyed by resolution key.
DEFAULT_RESOLUTION_NOTES: dict[str, tuple[str, str | None]] = {
    "completed": (
        "This has been fixed and will be available in the next update. "
        "Thanks for the report. "
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
    "custom": ("", None),
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

    # area label name -> default assignee login (see AREA_ASSIGNEES env)
    area_assignees: dict[str, str] = field(default_factory=dict)

    mapping_comment_template: str = (
        "Thanks for the report! Our team is tracking this and will post updates here."
    )
    needs_resolution_label: str = "resolution:none"

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

    def assignee_for_area(self, label_name: str) -> str | None:
        """Return the default assignee login for an area label, or None."""
        return self.area_assignees.get(label_name)


def _build_resolution_labels(
    raw: str | None,
) -> dict[str, tuple[str, str, str | None]]:
    """Parse RESOLUTION_LABELS JSON or build defaults.

    Expected JSON format:
    {
        "completed": {"label": "resolution:completed", "note": "...", "state_reason": "completed"},
        ...
    }
    If not provided, uses DEFAULT_RESOLUTION_NOTES with label prefix "resolution:".
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

    # Default: key -> (resolution:<key>, default note, default state_reason)
    result = {}
    for key, (note, state_reason) in DEFAULT_RESOLUTION_NOTES.items():
        result[key] = (f"resolution:{key}", note, state_reason)
    return result


def _build_area_assignees(raw: str | None) -> dict[str, str]:
    """Parse AREA_ASSIGNEES JSON into an area-label -> assignee-login map.

    Expected JSON format (an object mapping area label names to a single
    GitHub login):
    {
        "Lattices": "assaferan",
        "Algebras": "jvoight",
        ...
    }
    Missing, empty, or malformed means no auto-assignment happens.  A bad map
    disables only this feature; every other private-issue behaviour is
    unaffected.
    """
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        logger.warning(
            "AREA_ASSIGNEES is not valid JSON; area auto-assignment is disabled"
        )
        return {}
    if not isinstance(data, dict):
        logger.warning(
            "AREA_ASSIGNEES must be a JSON object; area auto-assignment is disabled"
        )
        return {}
    result: dict[str, str] = {}
    for key, val in data.items():
        if not key:
            continue
        if not isinstance(val, str) or not val.strip():
            logger.warning(
                "AREA_ASSIGNEES entry %r has an empty or non-string login; ignoring it",
                key,
            )
            continue
        result[key] = val.strip()
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
        area_assignees=_build_area_assignees(os.environ.get("AREA_ASSIGNEES")),
        mapping_comment_template=os.environ.get(
            "MAPPING_COMMENT_TEMPLATE",
            "Thanks for the report! Our team is tracking this and will post updates here.",
        ),
        needs_resolution_label=os.environ.get(
            "NEEDS_RESOLUTION_LABEL", "resolution:none"
        ),
    )
