# Bootstrap Missing Private Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every public event handler self-heal a missing private mirror so a dropped `opened` event can never leave an issue permanently unmirrored.

**Architecture:** Extract the "create private issue" logic from `public_issue_opened.handle` into a shared helper `ensure_private_mapping(client, config, public_issue)` in `lyrebird/handlers/_ensure_mapping.py`. The helper is idempotent: it returns the existing mapping if any, otherwise creates the private issue (with title, body, labels, type, milestone from the payload) and posts the mapping comment. Every public handler that currently calls `resolve_mapping()` and skips when `None` is changed to call `ensure_private_mapping()` instead, guaranteeing it has a mapping to work against.

**Tech Stack:** Python 3.12, PyGithub, pytest, Poetry.

**Background — why this is needed:** Public issue #37 on `Magma-Maths/Magma` fired 5 events on creation (`typed`, `labeled`, `opened`, `edited`, `edited`). The private repo workflow `handle-public-event.yml` uses `concurrency: group: public-event-<node_id>` with `cancel-in-progress: false`. GitHub's rule: only one pending run can exist per group — newer queued runs cancel the previously-pending one. Result: the `opened` run was cancelled while pending, and the subsequent `edited` runs logged `No mapping for public #37, skipping edit`. No private mirror was ever created. This plan makes every handler capable of bootstrapping the mirror, so the first run that wins the concurrency race creates it.

**Out of scope:**
- Changing the workflow concurrency policy (a GitHub Actions limitation with no clean fix).
- Backfilling tests for `public_issue_typed.py` beyond what's needed for this change.
- Manually recovering issue #37 — that is a one-off operator action, documented at the end.

---

## File Structure

**New files:**
- `lyrebird/handlers/_ensure_mapping.py` — the shared bootstrap helper.
- `tests/handlers/test_ensure_mapping.py` — unit tests for the helper.
- `tests/handlers/test_public_issue_typed.py` — minimal bootstrap test for `public_issue_typed.handle` (no existing test file).

**Modified files:**
- `lyrebird/handlers/public_issue_opened.py` — becomes a one-liner that delegates.
- `lyrebird/handlers/public_issue_edited.py` — uses `ensure_private_mapping`.
- `lyrebird/handlers/public_issue_typed.py` — uses `ensure_private_mapping`.
- `lyrebird/handlers/public_labels_changed.py` — uses `ensure_private_mapping`.
- `lyrebird/handlers/public_issue_milestoned.py` — uses `ensure_private_mapping`.
- `lyrebird/handlers/public_issue_state.py` — uses `ensure_private_mapping`.
- `lyrebird/handlers/public_comment_created.py` — uses `ensure_private_mapping`.
- `tests/handlers/test_public_issue_edited.py` — update `test_no_mapping_skips`.
- `tests/handlers/test_public_labels_changed.py` — add bootstrap test.
- `tests/handlers/test_public_issue_milestoned.py` — replace `test_no_op_when_no_mapping`.
- `tests/handlers/test_public_issue_state.py` — replace `test_no_mapping_returns_early`.
- `tests/handlers/test_public_comment_created.py` — add bootstrap test.

**Not touched (intentional):**
- `lyrebird/handlers/public_comment_edited.py` and `public_comment_deleted.py` — they operate on a specific mirrored comment; bootstrapping an issue with no mirrored comment for the target would produce an inconsistent partial state. Leave the warning-and-skip behaviour.
- `lyrebird/mapping.py` — the helper lives in `handlers/` alongside `_set_issue_type.py` and `_cleanup_labels.py` to avoid pulling `milestones` and `_set_issue_type` imports into `mapping.py` (which is a pure parsing/builder module).

---

## Task 1: Create `_ensure_mapping.py` helper (TDD)

**Files:**
- Create: `lyrebird/handlers/_ensure_mapping.py`
- Test: `tests/handlers/test_ensure_mapping.py`

- [ ] **Step 1: Write failing tests**

Create `tests/handlers/test_ensure_mapping.py`:

```python
"""Tests for ensure_private_mapping bootstrap helper."""

from __future__ import annotations

from unittest.mock import MagicMock

from lyrebird.handlers._ensure_mapping import ensure_private_mapping
from tests.conftest import (
    make_mock_issue,
    make_private_issue_body,
    make_public_issue_payload,
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
    mock_priv_repo.create_issue.assert_not_called()


def test_creates_private_issue_when_no_mapping(config, mock_client):
    """When neither mapping comment nor fallback body markers exist, create the mirror."""
    public_issue = make_public_issue_payload(title="Bug X", body="Body X")

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue_obj = make_mock_issue(number=42)
    mock_pub_issue_obj.get_comments.return_value = []
    mock_priv_repo.get_issues.return_value = []

    mock_priv_issue = MagicMock()
    mock_priv_issue.number = 99
    mock_priv_repo.create_issue.return_value = mock_priv_issue

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    mock_pub_repo.get_issue.return_value = mock_pub_issue_obj

    result = ensure_private_mapping(mock_client, config, public_issue)

    assert result.private_issue_number == 99
    mock_priv_repo.create_issue.assert_called_once()
    create_kwargs = mock_priv_repo.create_issue.call_args.kwargs
    assert "[public #42] Bug X" == create_kwargs["title"]
    assert "Body X" in create_kwargs["body"]

    # Mapping comment posted on public
    mock_pub_issue_obj.create_comment.assert_called_once()
    mapping_text = mock_pub_issue_obj.create_comment.call_args[0][0]
    assert "private_issue_number=99" in mapping_text


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

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue_obj = make_mock_issue(number=42)
    mock_pub_issue_obj.get_comments.return_value = []
    mock_priv_repo.get_issues.return_value = []
    mock_priv_repo.get_milestones.return_value = []

    mock_priv_issue = MagicMock()
    mock_priv_issue.number = 99
    mock_priv_repo.create_issue.return_value = mock_priv_issue

    created_ms = MagicMock()
    created_ms.title = "v1.0"
    mock_priv_repo.create_milestone.return_value = created_ms

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    mock_pub_repo.get_issue.return_value = mock_pub_issue_obj

    ensure_private_mapping(mock_client, config, public_issue)

    # Labels passed to create_issue
    create_kwargs = mock_priv_repo.create_issue.call_args.kwargs
    assert "bug" in create_kwargs["labels"]

    # Milestone created and assigned
    mock_priv_repo.create_milestone.assert_called_once()
    edit_calls = mock_priv_issue.edit.call_args_list
    assert any(
        call.kwargs.get("milestone") is created_ms for call in edit_calls
    ), "milestone should have been assigned via edit()"

    # Issue type set via requester (mocked client)
    mock_client._Github__requester.requestJsonAndCheck.assert_called()
    call_args = mock_client._Github__requester.requestJsonAndCheck.call_args
    assert call_args.kwargs.get("input", {}).get("type") == "Bug" or (
        len(call_args.args) >= 3 and call_args.args[2] == {"type": "Bug"}
    )


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
    mock_priv_repo.create_issue.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/handlers/test_ensure_mapping.py -v
```

Expected: ImportError or ModuleNotFoundError for `lyrebird.handlers._ensure_mapping`.

- [ ] **Step 3: Create the helper module**

Create `lyrebird/handlers/_ensure_mapping.py`:

```python
"""Idempotent bootstrap: ensure a public issue has a private mirror."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.handlers._set_issue_type import set_issue_type
from lyrebird.mapping import (
    PrivateMapping,
    build_mapping_comment,
    build_private_issue_body,
    build_private_issue_title,
    resolve_mapping,
)
from lyrebird.milestones import milestone_from_payload, resolve_or_create_milestone

logger = logging.getLogger(__name__)


def ensure_private_mapping(
    client: Github, config: Config, public_issue: dict
) -> PrivateMapping:
    """Return the private mapping, creating a new private issue if missing.

    This is the single entry point every public handler calls before touching
    the private mirror. If a previous `opened` event was dropped (e.g. cancelled
    by the Actions concurrency queue), the first handler that runs will create
    the mirror here using the full current state from the payload. Subsequent
    handlers find the mapping and proceed normally.
    """
    existing = resolve_mapping(client, config, public_issue)
    if existing is not None:
        return existing

    priv_repo = client.get_repo(config.private_repo)
    title = build_private_issue_title(public_issue)
    body = build_private_issue_body(config, public_issue)

    label_names = [lbl["name"] for lbl in public_issue.get("labels", [])]
    for lbl in public_issue.get("labels", []):
        ensure_label(priv_repo, lbl)

    private_issue = priv_repo.create_issue(
        title=title,
        body=body,
        labels=label_names if label_names else [],
    )
    logger.info(
        "Bootstrapped private issue #%d for public #%d",
        private_issue.number,
        public_issue["number"],
    )

    issue_type = (public_issue.get("type") or {}).get("name")
    if issue_type:
        set_issue_type(client, private_issue, issue_type)

    milestone_data = public_issue.get("milestone")
    if milestone_data:
        source_ms = milestone_from_payload(milestone_data)
        target_ms = resolve_or_create_milestone(priv_repo, source_ms)
        private_issue.edit(milestone=target_ms)

    pub_repo = client.get_repo(config.public_repo)
    pub_issue = pub_repo.get_issue(public_issue["number"])
    mapping_text = build_mapping_comment(
        config, public_issue["node_id"], private_issue.number
    )
    pub_issue.create_comment(mapping_text)
    logger.info("Posted mapping comment on public #%d", public_issue["number"])

    return PrivateMapping(
        private_issue=private_issue,
        private_issue_number=private_issue.number,
    )


def ensure_label(repo, label_data: dict) -> None:
    """Create label in repo if it doesn't exist. Silent on failure."""
    try:
        repo.get_label(label_data["name"])
    except Exception:
        try:
            color = label_data.get("color", "ededed")
            description = label_data.get("description", "") or ""
            repo.create_label(
                name=label_data["name"],
                color=color,
                description=description,
            )
        except Exception:
            logger.warning("Could not create label %s", label_data["name"])
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/handlers/test_ensure_mapping.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add lyrebird/handlers/_ensure_mapping.py tests/handlers/test_ensure_mapping.py
git commit -m "feat(handlers): add ensure_private_mapping bootstrap helper"
```

---

## Task 2: Refactor `public_issue_opened` to delegate

**Files:**
- Modify: `lyrebird/handlers/public_issue_opened.py`

- [ ] **Step 1: Replace handler body**

Rewrite `lyrebird/handlers/public_issue_opened.py` to:

```python
"""Handle public issue opened: ensure private mirror exists."""

from __future__ import annotations

from github import Github

from lyrebird.config import Config
from lyrebird.handlers._ensure_mapping import ensure_private_mapping


def handle(client: Github, config: Config, payload: dict) -> None:
    ensure_private_mapping(client, config, payload["issue"])
```

- [ ] **Step 2: Run existing tests to verify they still pass**

```bash
poetry run pytest tests/handlers/test_public_issue_opened.py -v
```

Expected: all 6 existing tests PASS unchanged. The handler now delegates but the behaviour visible from tests is identical (creates private issue, posts mapping comment, idempotent, self-heals, mirrors milestone, etc.).

- [ ] **Step 3: Commit**

```bash
git add lyrebird/handlers/public_issue_opened.py
git commit -m "refactor(handlers): delegate public_issue_opened to ensure_private_mapping"
```

---

## Task 3: Bootstrap in `public_issue_edited`

**Files:**
- Modify: `lyrebird/handlers/public_issue_edited.py`
- Modify: `tests/handlers/test_public_issue_edited.py`

- [ ] **Step 1: Rewrite the existing `test_no_mapping_skips` test**

In `tests/handlers/test_public_issue_edited.py`, replace `test_no_mapping_skips` with:

```python
def test_no_mapping_bootstraps_then_edits(config, mock_client):
    """When no mapping exists, bootstrap the private mirror from the edited payload."""
    public_issue = make_public_issue_payload(title="Edited title", body="Edited body")
    payload = {"issue": public_issue}

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue_obj = make_mock_issue(number=42)
    mock_pub_issue_obj.get_comments.return_value = []
    mock_priv_repo.get_issues.return_value = []

    # Bootstrap creates this private issue
    mock_priv_issue = MagicMock()
    mock_priv_issue.number = 99
    mock_priv_issue.body = make_private_issue_body(
        public_number=42, public_body="Edited body"
    )
    mock_priv_repo.create_issue.return_value = mock_priv_issue

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    mock_pub_repo.get_issue.return_value = mock_pub_issue_obj

    handle(mock_client, config, payload)

    # Private issue bootstrapped with the edited title/body
    mock_priv_repo.create_issue.assert_called_once()
    create_kwargs = mock_priv_repo.create_issue.call_args.kwargs
    assert "[public #42] Edited title" == create_kwargs["title"]
    assert "Edited body" in create_kwargs["body"]
```

- [ ] **Step 2: Run the test to see it fail**

```bash
poetry run pytest tests/handlers/test_public_issue_edited.py::test_no_mapping_bootstraps_then_edits -v
```

Expected: FAIL — handler currently warns and returns without creating anything, so `create_issue.assert_called_once()` fails.

- [ ] **Step 3: Update the handler**

Rewrite `lyrebird/handlers/public_issue_edited.py` to:

```python
"""Handle public issue edited: ensure mirror exists, then update title and body."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.handlers._ensure_mapping import ensure_private_mapping
from lyrebird.mapping import (
    build_private_issue_title,
    update_private_body_public_section,
)

logger = logging.getLogger(__name__)


def handle(client: Github, config: Config, payload: dict) -> None:
    public_issue = payload["issue"]
    mapping = ensure_private_mapping(client, config, public_issue)

    private_issue = mapping.private_issue
    new_title = build_private_issue_title(public_issue)
    new_body = update_private_body_public_section(
        private_issue.body or "",
        public_issue.get("body") or "",
    )

    private_issue.edit(title=new_title, body=new_body)
    logger.info(
        "Updated private #%d from public #%d edit",
        mapping.private_issue_number,
        public_issue["number"],
    )
```

- [ ] **Step 4: Run tests to verify pass**

```bash
poetry run pytest tests/handlers/test_public_issue_edited.py -v
```

Expected: both tests PASS (the existing `test_updates_private_title_and_body` continues to pass; the new bootstrap test passes).

- [ ] **Step 5: Commit**

```bash
git add lyrebird/handlers/public_issue_edited.py tests/handlers/test_public_issue_edited.py
git commit -m "fix(handlers): bootstrap mirror on public_issue_edited when missing"
```

---

## Task 4: Bootstrap in `public_issue_typed`

**Files:**
- Modify: `lyrebird/handlers/public_issue_typed.py`
- Create: `tests/handlers/test_public_issue_typed.py` (no existing test file)

- [ ] **Step 1: Create a new test file with a failing test**

Create `tests/handlers/test_public_issue_typed.py`:

```python
"""Tests for public_issue_typed handler."""

from __future__ import annotations

from unittest.mock import MagicMock

from lyrebird.handlers.public_issue_typed import handle
from tests.conftest import make_mock_issue, make_public_issue_payload


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

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue_obj = make_mock_issue(number=42)
    mock_pub_issue_obj.get_comments.return_value = []
    mock_priv_repo.get_issues.return_value = []

    mock_priv_issue = MagicMock()
    mock_priv_issue.number = 99
    mock_priv_repo.create_issue.return_value = mock_priv_issue

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    mock_pub_repo.get_issue.return_value = mock_pub_issue_obj
    mock_priv_repo.get_issue.return_value = mock_priv_issue

    handle(mock_client, config, payload)

    mock_priv_repo.create_issue.assert_called_once()
```

- [ ] **Step 2: Run the tests to see them fail**

```bash
poetry run pytest tests/handlers/test_public_issue_typed.py -v
```

Expected: `test_bootstraps_when_no_mapping` FAILS (handler currently logs and returns without creating). `test_sets_type_on_existing_private_mirror` should PASS — it just verifies pre-existing behaviour.

- [ ] **Step 3: Update the handler**

Rewrite `lyrebird/handlers/public_issue_typed.py` to:

```python
"""Handle public issue typed/untyped: ensure mirror, then sync issue type."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.handlers._ensure_mapping import ensure_private_mapping
from lyrebird.handlers._set_issue_type import set_issue_type

logger = logging.getLogger(__name__)


def handle(client: Github, config: Config, payload: dict) -> None:
    public_issue = payload["issue"]
    issue_type = (public_issue.get("type") or {}).get("name")

    mapping = ensure_private_mapping(client, config, public_issue)

    set_issue_type(client, mapping.private_issue, issue_type)
```

- [ ] **Step 4: Run tests to verify pass**

```bash
poetry run pytest tests/handlers/test_public_issue_typed.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add lyrebird/handlers/public_issue_typed.py tests/handlers/test_public_issue_typed.py
git commit -m "fix(handlers): bootstrap mirror on public_issue_typed when missing"
```

---

## Task 5: Bootstrap in `public_labels_changed`

**Files:**
- Modify: `lyrebird/handlers/public_labels_changed.py`
- Modify: `tests/handlers/test_public_labels_changed.py`

- [ ] **Step 1: Add a failing bootstrap test**

Append to `tests/handlers/test_public_labels_changed.py`:

```python
def test_bootstraps_when_no_mapping(config, mock_client):
    """When `labeled` arrives before `opened` ran, bootstrap the mirror."""
    public_issue = make_public_issue_payload(
        labels=[{"name": "bug", "color": "d73a4a", "description": ""}]
    )
    payload = {
        "issue": public_issue,
        "action": "labeled",
        "label": {"name": "bug", "color": "d73a4a", "description": ""},
    }

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue_obj = make_mock_issue(number=42)
    mock_pub_issue_obj.get_comments.return_value = []
    mock_priv_repo.get_issues.return_value = []

    mock_priv_issue = MagicMock()
    mock_priv_issue.number = 99
    mock_priv_repo.create_issue.return_value = mock_priv_issue

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    mock_pub_repo.get_issue.return_value = mock_pub_issue_obj

    handle(mock_client, config, payload)

    mock_priv_repo.create_issue.assert_called_once()
    create_kwargs = mock_priv_repo.create_issue.call_args.kwargs
    assert "bug" in create_kwargs["labels"]
```

Also make sure the test file imports `make_mock_issue` and `make_public_issue_payload` from `tests.conftest` at the top.

- [ ] **Step 2: Run the test to see it fail**

```bash
poetry run pytest tests/handlers/test_public_labels_changed.py::test_bootstraps_when_no_mapping -v
```

Expected: FAIL — `create_issue.assert_called_once()` fails because the current handler just warns and returns.

- [ ] **Step 3: Update the handler**

Rewrite `lyrebird/handlers/public_labels_changed.py` to:

```python
"""Handle public label added/removed: ensure mirror, then mirror label change."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.handlers._ensure_mapping import ensure_label, ensure_private_mapping

logger = logging.getLogger(__name__)


def handle(client: Github, config: Config, payload: dict) -> None:
    public_issue = payload["issue"]
    action = payload["action"]  # "labeled" or "unlabeled"
    label_data = payload.get("label", {})
    label_name = label_data.get("name", "")

    if not label_name:
        return

    mapping = ensure_private_mapping(client, config, public_issue)
    priv_repo = client.get_repo(config.private_repo)

    if action == "labeled":
        ensure_label(priv_repo, label_data)
        mapping.private_issue.add_to_labels(label_name)
        logger.info(
            "Added label '%s' to private #%d",
            label_name,
            mapping.private_issue_number,
        )
    elif action == "unlabeled":
        try:
            mapping.private_issue.remove_from_labels(label_name)
            logger.info(
                "Removed label '%s' from private #%d",
                label_name,
                mapping.private_issue_number,
            )
        except Exception:
            logger.info(
                "Label '%s' not on private #%d, nothing to remove",
                label_name,
                mapping.private_issue_number,
            )
```

- [ ] **Step 4: Run tests to verify pass**

```bash
poetry run pytest tests/handlers/test_public_labels_changed.py -v
```

Expected: all 4 tests PASS (3 original + 1 new bootstrap test).

- [ ] **Step 5: Commit**

```bash
git add lyrebird/handlers/public_labels_changed.py tests/handlers/test_public_labels_changed.py
git commit -m "fix(handlers): bootstrap mirror on public_labels_changed when missing"
```

---

## Task 6: Bootstrap in `public_issue_milestoned`

**Files:**
- Modify: `lyrebird/handlers/public_issue_milestoned.py`
- Modify: `tests/handlers/test_public_issue_milestoned.py`

- [ ] **Step 1: Replace `test_no_op_when_no_mapping` with a bootstrap test**

In `tests/handlers/test_public_issue_milestoned.py`, find `test_no_op_when_no_mapping` (at line ~94) and replace it with:

```python
    def test_bootstraps_when_no_mapping(self, config, mock_client):
        """When `milestoned` arrives before `opened` ran, bootstrap the mirror."""
        public_issue = make_public_issue_payload(
            milestone={
                "title": "v1.0",
                "description": "First release",
                "due_on": "2026-06-01T00:00:00Z",
                "state": "open",
                "number": 1,
            },
        )
        payload = {
            "issue": public_issue,
            "action": "milestoned",
            "milestone": {
                "title": "v1.0",
                "description": "First release",
                "due_on": "2026-06-01T00:00:00Z",
                "state": "open",
                "number": 1,
            },
        }

        mock_pub_repo = MagicMock()
        mock_priv_repo = MagicMock()
        mock_pub_issue_obj = make_mock_issue(number=42)
        mock_pub_issue_obj.get_comments.return_value = []
        mock_priv_repo.get_issues.return_value = []
        mock_priv_repo.get_milestones.return_value = []

        mock_priv_issue = MagicMock()
        mock_priv_issue.number = 99
        mock_priv_repo.create_issue.return_value = mock_priv_issue

        created_ms = MagicMock()
        created_ms.title = "v1.0"
        mock_priv_repo.create_milestone.return_value = created_ms

        def get_repo(name):
            if name == config.public_repo:
                return mock_pub_repo
            return mock_priv_repo

        mock_client.get_repo.side_effect = get_repo
        mock_pub_repo.get_issue.return_value = mock_pub_issue_obj
        mock_priv_repo.get_issue.return_value = mock_priv_issue

        handle(mock_client, config, payload)

        mock_priv_repo.create_issue.assert_called_once()
```

- [ ] **Step 2: Run the test to see it fail**

```bash
poetry run pytest tests/handlers/test_public_issue_milestoned.py::TestMilestoned::test_bootstraps_when_no_mapping -v
```

(Use whatever class name exists in the file — read it first if uncertain.) Expected: FAIL.

- [ ] **Step 3: Update the handler**

Rewrite `lyrebird/handlers/public_issue_milestoned.py` to:

```python
"""Handle public issue milestoned/demilestoned: ensure mirror, then sync milestone."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.handlers._ensure_mapping import ensure_private_mapping
from lyrebird.milestones import milestone_from_payload, resolve_or_create_milestone

logger = logging.getLogger(__name__)


def handle(client: Github, config: Config, payload: dict) -> None:
    action = payload["action"]
    public_issue = payload["issue"]

    mapping = ensure_private_mapping(client, config, public_issue)

    priv_repo = client.get_repo(config.private_repo)
    private_issue = mapping.private_issue

    if action == "milestoned":
        milestone_data = payload["milestone"]
        source_ms = milestone_from_payload(milestone_data)
        target_ms = resolve_or_create_milestone(priv_repo, source_ms)
        private_issue.edit(milestone=target_ms)
        logger.info(
            "Set milestone '%s' on private #%d",
            milestone_data["title"],
            private_issue.number,
        )
    elif action == "demilestoned":
        private_issue.edit(milestone=None)
        logger.info("Removed milestone from private #%d", private_issue.number)
```

- [ ] **Step 4: Run tests to verify pass**

```bash
poetry run pytest tests/handlers/test_public_issue_milestoned.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add lyrebird/handlers/public_issue_milestoned.py tests/handlers/test_public_issue_milestoned.py
git commit -m "fix(handlers): bootstrap mirror on public_issue_milestoned when missing"
```

---

## Task 7: Bootstrap in `public_issue_state`

**Files:**
- Modify: `lyrebird/handlers/public_issue_state.py`
- Modify: `tests/handlers/test_public_issue_state.py`

- [ ] **Step 1: Replace `test_no_mapping_returns_early` with a bootstrap test**

In `tests/handlers/test_public_issue_state.py`, find `test_no_mapping_returns_early` (at line ~155) and replace it with:

```python
def test_close_bootstraps_when_no_mapping(config, mock_client):
    """When `closed` arrives before `opened` ran, bootstrap the mirror then close it."""
    public_issue = make_public_issue_payload(state="closed")
    public_issue["state_reason"] = "completed"
    payload = {
        "issue": public_issue,
        "action": "closed",
        "sender": {"login": "reporter", "type": "User"},
    }

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue_obj = make_mock_issue(number=42)
    mock_pub_issue_obj.get_comments.return_value = []
    mock_priv_repo.get_issues.return_value = []

    mock_priv_issue = MagicMock()
    mock_priv_issue.number = 99
    mock_priv_repo.create_issue.return_value = mock_priv_issue

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    mock_pub_repo.get_issue.return_value = mock_pub_issue_obj

    handle(mock_client, config, payload)

    # Bootstrap happened
    mock_priv_repo.create_issue.assert_called_once()
    # And the private issue was then closed
    edit_calls = mock_priv_issue.edit.call_args_list
    assert any(
        c.kwargs.get("state") == "closed" for c in edit_calls
    ), "private issue should have been closed after bootstrap"
```

- [ ] **Step 2: Run the test to see it fail**

```bash
poetry run pytest tests/handlers/test_public_issue_state.py::test_close_bootstraps_when_no_mapping -v
```

Expected: FAIL.

- [ ] **Step 3: Update the handler**

Rewrite `lyrebird/handlers/public_issue_state.py` to:

```python
"""Handle public issue closed/reopened: ensure mirror, sync state, post audit comment."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.handlers._cleanup_labels import cleanup_private_resolution_labels
from lyrebird.handlers._ensure_mapping import ensure_private_mapping

logger = logging.getLogger(__name__)


def handle(client: Github, config: Config, payload: dict) -> None:
    public_issue = payload["issue"]
    action = payload["action"]  # "closed" or "reopened"
    sender = payload.get("sender", {}).get("login", "unknown")

    mapping = ensure_private_mapping(client, config, public_issue)

    private_issue = mapping.private_issue
    is_reporter = sender == public_issue["user"]["login"]

    if action == "closed":
        audit = f"Public issue closed by @{sender}"
        if is_reporter:
            audit += " (original reporter)"
        private_issue.create_comment(audit)

        state_reason = public_issue.get("state_reason")
        if state_reason:
            private_issue.edit(state="closed", state_reason=state_reason)
        else:
            private_issue.edit(state="closed")

    elif action == "reopened":
        cleanup_private_resolution_labels(config, private_issue)
        audit = f"Public issue reopened by @{sender}"
        if is_reporter:
            audit += " (original reporter)"
        private_issue.create_comment(audit)
        private_issue.edit(state="open")

    logger.info(
        "Handled public %s for private #%d",
        action,
        mapping.private_issue_number,
    )
```

- [ ] **Step 4: Run tests to verify pass**

```bash
poetry run pytest tests/handlers/test_public_issue_state.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add lyrebird/handlers/public_issue_state.py tests/handlers/test_public_issue_state.py
git commit -m "fix(handlers): bootstrap mirror on public_issue_state when missing"
```

---

## Task 8: Bootstrap in `public_comment_created`

**Files:**
- Modify: `lyrebird/handlers/public_comment_created.py`
- Modify: `tests/handlers/test_public_comment_created.py`

- [ ] **Step 1: Add a failing bootstrap test**

Append to `tests/handlers/test_public_comment_created.py`:

```python
def test_bootstraps_when_no_mapping(config, mock_client):
    """When a comment arrives before the issue's `opened` ran, bootstrap the mirror."""
    from tests.conftest import make_comment_payload

    payload = make_comment_payload(comment_id=555, body="First comment")

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue_obj = make_mock_issue(number=42)
    mock_pub_issue_obj.get_comments.return_value = []
    mock_priv_repo.get_issues.return_value = []

    mock_priv_issue = MagicMock()
    mock_priv_issue.number = 99
    mock_priv_repo.create_issue.return_value = mock_priv_issue

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    mock_pub_repo.get_issue.return_value = mock_pub_issue_obj
    mock_priv_repo.get_issue.return_value = mock_priv_issue

    handle(mock_client, config, payload)

    # Bootstrap happened
    mock_priv_repo.create_issue.assert_called_once()
    # Comment mirrored onto the bootstrapped private issue
    mock_priv_issue.create_comment.assert_called()
    mirrored = mock_priv_issue.create_comment.call_args[0][0]
    assert "First comment" in mirrored
```

Make sure `make_mock_issue` and `MagicMock` are imported at the top of the file.

- [ ] **Step 2: Run the test to see it fail**

```bash
poetry run pytest tests/handlers/test_public_comment_created.py::test_bootstraps_when_no_mapping -v
```

Expected: FAIL.

- [ ] **Step 3: Update the handler**

Rewrite `lyrebird/handlers/public_comment_created.py` to:

```python
"""Handle public comment created: ensure mirror exists, then mirror the comment."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.handlers._ensure_mapping import ensure_private_mapping
from lyrebird.mapping import build_mirrored_comment_body

logger = logging.getLogger(__name__)


def handle(client: Github, config: Config, payload: dict) -> None:
    public_issue = payload["issue"]
    comment = payload["comment"]

    # Defense-in-depth: never mirror the bot's own comments, even if
    # is_bot_event() in cli.py failed to catch this event.
    from lyrebird.loop_prevention import is_bot_login

    comment_author = comment.get("user", {}).get("login", "")
    if is_bot_login(config, comment_author):
        logger.info(
            "Skipping bot-authored comment %d on public #%d",
            comment["id"],
            public_issue["number"],
        )
        return

    mapping = ensure_private_mapping(client, config, public_issue)

    body = build_mirrored_comment_body(
        author=comment["user"]["login"],
        permalink=comment["html_url"],
        body=comment.get("body") or "",
        public_comment_id=comment["id"],
    )

    mapping.private_issue.create_comment(body)
    logger.info(
        "Mirrored comment %d to private #%d",
        comment["id"],
        mapping.private_issue_number,
    )
```

- [ ] **Step 4: Run tests to verify pass**

```bash
poetry run pytest tests/handlers/test_public_comment_created.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add lyrebird/handlers/public_comment_created.py tests/handlers/test_public_comment_created.py
git commit -m "fix(handlers): bootstrap mirror on public_comment_created when missing"
```

---

## Task 9: Run the full test suite

- [ ] **Step 1: Run everything**

```bash
poetry run pytest -v
```

Expected: all tests PASS. If anything fails, it is almost certainly a test I didn't know to update. Read the failure, update the relevant test to reflect the new bootstrap-on-missing behaviour, re-run, and commit a follow-up fix with message:

```bash
git commit -m "test(handlers): update tests for bootstrap-on-missing behaviour"
```

- [ ] **Step 2: Final commit if not already done**

No new changes expected beyond Step 1 fixes.

---

## Post-merge operator action (not a code task)

After the fix is deployed, public issue #37 on `Magma-Maths/Magma` still has no private mirror. Two ways to create it:

1. **Trigger any issue event**: make a trivial edit to issue #37 (add a space to the title, save, then revert). The `edited` event will now bootstrap the mirror.
2. **Re-run the original opened dispatch**: `gh run rerun 24350303469 --repo Magma-Maths/Magma` will replay the `opened` event from the public dispatcher, which then creates the mirror normally on the private side.

Option 1 is simpler and does not require remembering run IDs.

---

## Self-review checklist

**Spec coverage:** Every handler currently calling `resolve_mapping()` and returning early on `None` is now covered — `public_issue_edited`, `public_issue_typed`, `public_labels_changed`, `public_issue_milestoned`, `public_issue_state`, `public_comment_created` — plus `public_issue_opened` is refactored to share the same helper. `public_comment_edited` and `public_comment_deleted` are intentionally excluded (documented in File Structure section).

**Placeholder scan:** No TBD, TODO, "implement later", "similar to Task N", or handwaved error-handling instructions. Every code block contains the full code to write.

**Type consistency:** All tasks use the same helper name `ensure_private_mapping`, the same return type `PrivateMapping` from `lyrebird/mapping.py`, and the same module path `lyrebird.handlers._ensure_mapping`. The helper signature `(client, config, public_issue: dict) -> PrivateMapping` is used identically in every call site.
