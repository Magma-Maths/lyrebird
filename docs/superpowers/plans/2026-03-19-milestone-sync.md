# Milestone Sync & Label Property Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bidirectional milestone synchronization and label property reconciliation to Lyrebird.

**Architecture:** New `milestones.py` module provides shared helpers (`find_milestone_by_title`, `resolve_or_create_milestone`, `sync_milestone_properties`). Two new handlers mirror milestone assignments in real-time. `sync.py` gains three new passes: milestone metadata, label properties, and per-issue milestone assignment. `public_issue_opened` is updated to mirror milestones at creation time.

**Tech Stack:** Python 3.10+, PyGithub, pytest

**Spec:** `docs/superpowers/specs/2026-03-19-milestone-sync-design.md`

---

### Task 1: Test infrastructure — `conftest.py` helpers

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add `make_mock_milestone()` helper**

```python
# Add after make_mock_comment() in tests/conftest.py

def make_mock_milestone(
    number: int = 1,
    title: str = "v1.0",
    description: str = "First release",
    due_on: str | None = "2026-06-01T00:00:00Z",
    state: str = "open",
):
    """Create a mock PyGithub Milestone object."""
    from datetime import datetime, timezone

    milestone = MagicMock()
    milestone.number = number
    milestone.title = title
    milestone.description = description
    milestone.state = state
    if due_on:
        milestone.due_on = datetime.fromisoformat(due_on.replace("Z", "+00:00"))
    else:
        milestone.due_on = None
    milestone.updated_at = datetime.now(timezone.utc)
    return milestone
```

- [ ] **Step 2: Add milestone parameter to `make_mock_issue()`**

Add `milestone=None` parameter to `make_mock_issue()`. After the `issue.user.login = user_login` line, add:

```python
    issue.milestone = milestone
```

- [ ] **Step 3: Add milestone field to `make_public_issue_payload()`**

Add `milestone: dict | None = None` parameter. In the returned dict, add:

```python
        "milestone": milestone,
```

- [ ] **Step 4: Run tests to verify nothing breaks**

Run: `poetry run pytest -x -q`
Expected: All existing tests pass.

- [ ] **Step 5: Commit**

```
test: add milestone mock helpers to conftest
```

---

### Task 2: `milestones.py` — shared helpers (tests first)

**Files:**
- Create: `tests/test_milestones.py`
- Create: `lyrebird/milestones.py`

- [ ] **Step 1: Write failing tests for `find_milestone_by_title`**

```python
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
        # Should query both open and closed
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_milestones.py -v`
Expected: FAIL (ImportError — module doesn't exist yet)

- [ ] **Step 3: Implement `find_milestone_by_title`**

Create `lyrebird/milestones.py`:

```python
"""Shared helpers for milestone synchronization."""

from __future__ import annotations

import logging

from github.Milestone import Milestone
from github.Repository import Repository

logger = logging.getLogger(__name__)


def find_milestone_by_title(repo: Repository, title: str) -> Milestone | None:
    """Find a milestone by exact title (case-sensitive) in both open and closed states."""
    for state in ("open", "closed"):
        for ms in repo.get_milestones(state=state):
            if ms.title == title:
                return ms
    return None
```

- [ ] **Step 4: Run tests to verify `find_milestone_by_title` tests pass**

Run: `poetry run pytest tests/test_milestones.py::TestFindMilestoneByTitle -v`
Expected: PASS

- [ ] **Step 5: Write failing tests for `resolve_or_create_milestone`**

Add to `tests/test_milestones.py`:

```python
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
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `poetry run pytest tests/test_milestones.py::TestResolveOrCreateMilestone -v`
Expected: FAIL (function not defined)

- [ ] **Step 7: Implement `resolve_or_create_milestone`**

Add to `lyrebird/milestones.py`:

```python
def resolve_or_create_milestone(
    target_repo: Repository, source_milestone: Milestone
) -> Milestone:
    """Find or create a milestone in target_repo matching the source milestone's title.

    Copies all fields (title, description, due_on, state) on creation.
    """
    existing = find_milestone_by_title(target_repo, source_milestone.title)
    if existing is not None:
        return existing

    created = target_repo.create_milestone(
        title=source_milestone.title,
        description=source_milestone.description or "",
        due_on=source_milestone.due_on,
        state=source_milestone.state,
    )
    logger.info("Created milestone '%s' in %s", source_milestone.title, target_repo.full_name)
    return created
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `poetry run pytest tests/test_milestones.py::TestResolveOrCreateMilestone -v`
Expected: PASS

- [ ] **Step 9: Write failing tests for `sync_milestone_properties`**

Add to `tests/test_milestones.py`:

```python
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
```

- [ ] **Step 10: Run tests to verify they fail**

Run: `poetry run pytest tests/test_milestones.py::TestSyncMilestoneProperties -v`
Expected: FAIL

- [ ] **Step 11: Implement `sync_milestone_properties`**

Add to `lyrebird/milestones.py`:

```python
def sync_milestone_properties(
    target: Milestone, source: Milestone
) -> bool:
    """Update target milestone properties to match source. Returns True if updated."""
    updates: dict = {}

    if (target.description or "") != (source.description or ""):
        updates["description"] = source.description or ""
    if target.due_on != source.due_on:
        updates["due_on"] = source.due_on
    if target.state != source.state:
        updates["state"] = source.state

    if not updates:
        return False

    # PyGithub's Milestone.edit() requires title as a positional arg
    target.edit(title=target.title, **updates)
    logger.info("Updated milestone '%s': %s", target.title, list(updates.keys()))
    return True


def milestone_from_payload(data: dict):
    """Build a SimpleNamespace with milestone attributes from a webhook payload dict."""
    from datetime import datetime
    from types import SimpleNamespace

    due_on = None
    if data.get("due_on"):
        due_on = datetime.fromisoformat(data["due_on"].replace("Z", "+00:00"))

    return SimpleNamespace(
        title=data["title"],
        description=data.get("description") or "",
        due_on=due_on,
        state=data.get("state", "open"),
    )
```

- [ ] **Step 12: Run all milestone tests**

Run: `poetry run pytest tests/test_milestones.py -v`
Expected: All PASS

- [ ] **Step 13: Commit**

```
feat(milestones): add shared milestone helper module with tests
```

---

### Task 3: `public_issue_milestoned` handler (tests first)

**Files:**
- Create: `tests/handlers/test_public_issue_milestoned.py`
- Create: `lyrebird/handlers/public_issue_milestoned.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for public_issue_milestoned handler."""

from __future__ import annotations

from unittest.mock import MagicMock

from lyrebird.handlers.public_issue_milestoned import handle
from tests.conftest import (
    make_mock_issue,
    make_mock_milestone,
    make_private_issue_body,
    make_public_issue_payload,
)


def _make_milestone_payload(
    action: str = "milestoned",
    issue_number: int = 42,
    issue_node_id: str = "I_kwDOTest",
    milestone_title: str = "v1.0",
) -> dict:
    """Build a milestone event payload."""
    return {
        "action": action,
        "issue": make_public_issue_payload(
            number=issue_number, node_id=issue_node_id
        ),
        "milestone": {
            "title": milestone_title,
            "description": "Release milestone",
            "due_on": "2026-06-01T00:00:00Z",
            "state": "open",
            "number": 1,
        },
        "sender": {"login": "reporter", "type": "User"},
    }


class TestMilestoned:
    def test_creates_milestone_if_missing_and_assigns(self, config, mock_client):
        """When private repo has no matching milestone, create it and assign."""
        payload = _make_milestone_payload()

        mock_pub_repo = MagicMock()
        mock_priv_repo = MagicMock()
        mock_pub_issue = make_mock_issue(number=42)
        mock_pub_issue.get_comments.return_value = []

        # Mapping: fallback finds private issue by body markers
        mock_priv_issue = make_mock_issue(number=100)
        mock_priv_issue.body = make_private_issue_body()
        mock_priv_repo.get_issues.return_value = [mock_priv_issue]

        # No existing milestone in private repo
        mock_priv_repo.get_milestones.return_value = []
        created_ms = make_mock_milestone(title="v1.0")
        mock_priv_repo.create_milestone.return_value = created_ms

        def get_repo(name):
            if name == config.public_repo:
                return mock_pub_repo
            return mock_priv_repo

        mock_client.get_repo.side_effect = get_repo
        mock_pub_repo.get_issue.return_value = mock_pub_issue
        mock_priv_repo.get_issue.return_value = mock_priv_issue

        handle(mock_client, config, payload)

        mock_priv_repo.create_milestone.assert_called_once()
        mock_priv_issue.edit.assert_called_once()
        assert mock_priv_issue.edit.call_args.kwargs["milestone"] is created_ms

    def test_reuses_existing_milestone(self, config, mock_client):
        """When private repo already has a milestone with the same title, reuse it."""
        payload = _make_milestone_payload()

        mock_pub_repo = MagicMock()
        mock_priv_repo = MagicMock()
        mock_pub_issue = make_mock_issue(number=42)

        # Mapping via comment
        mapping_comment = MagicMock()
        mapping_comment.body = (
            "<!-- mapping: public_issue_node_id=I_kwDOTest private_issue_number=100 -->"
        )
        mock_pub_issue.get_comments.return_value = [mapping_comment]

        mock_priv_issue = make_mock_issue(number=100)
        existing_ms = make_mock_milestone(title="v1.0")
        mock_priv_repo.get_milestones.return_value = [existing_ms]

        def get_repo(name):
            if name == config.public_repo:
                return mock_pub_repo
            return mock_priv_repo

        mock_client.get_repo.side_effect = get_repo
        mock_pub_repo.get_issue.return_value = mock_pub_issue
        mock_priv_repo.get_issue.return_value = mock_priv_issue

        handle(mock_client, config, payload)

        mock_priv_repo.create_milestone.assert_not_called()
        mock_priv_issue.edit.assert_called_once()
        assert mock_priv_issue.edit.call_args.kwargs["milestone"] is existing_ms

    def test_no_op_when_no_mapping(self, config, mock_client):
        """When no mapping exists, handler returns without action."""
        payload = _make_milestone_payload()

        mock_pub_repo = MagicMock()
        mock_priv_repo = MagicMock()
        mock_pub_issue = make_mock_issue(number=42)
        mock_pub_issue.get_comments.return_value = []
        mock_priv_repo.get_issues.return_value = []  # No fallback match

        def get_repo(name):
            if name == config.public_repo:
                return mock_pub_repo
            return mock_priv_repo

        mock_client.get_repo.side_effect = get_repo
        mock_pub_repo.get_issue.return_value = mock_pub_issue

        handle(mock_client, config, payload)

        mock_priv_repo.create_milestone.assert_not_called()


class TestDemilestoned:
    def test_removes_milestone_from_private(self, config, mock_client):
        """Demilestoned sets private issue milestone to None."""
        payload = _make_milestone_payload(action="demilestoned")

        mock_pub_repo = MagicMock()
        mock_priv_repo = MagicMock()
        mock_pub_issue = make_mock_issue(number=42)

        mapping_comment = MagicMock()
        mapping_comment.body = (
            "<!-- mapping: public_issue_node_id=I_kwDOTest private_issue_number=100 -->"
        )
        mock_pub_issue.get_comments.return_value = [mapping_comment]

        mock_priv_issue = make_mock_issue(number=100)

        def get_repo(name):
            if name == config.public_repo:
                return mock_pub_repo
            return mock_priv_repo

        mock_client.get_repo.side_effect = get_repo
        mock_pub_repo.get_issue.return_value = mock_pub_issue
        mock_priv_repo.get_issue.return_value = mock_priv_issue

        handle(mock_client, config, payload)

        mock_priv_issue.edit.assert_called_once_with(milestone=None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/handlers/test_public_issue_milestoned.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement `public_issue_milestoned.py`**

Create `lyrebird/handlers/public_issue_milestoned.py`:

```python
"""Handle public issue milestoned/demilestoned: mirror to private."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.mapping import resolve_mapping
from lyrebird.milestones import milestone_from_payload, resolve_or_create_milestone

logger = logging.getLogger(__name__)


def handle(client: Github, config: Config, payload: dict) -> None:
    action = payload["action"]
    public_issue = payload["issue"]

    mapping = resolve_mapping(client, config, public_issue)
    if mapping is None:
        logger.info(
            "No mapping for public #%d, skipping milestone sync",
            public_issue["number"],
        )
        return

    priv_repo = client.get_repo(config.private_repo)
    priv_issue = priv_repo.get_issue(mapping.private_issue_number)

    if action == "milestoned":
        milestone_data = payload["milestone"]
        source_ms = milestone_from_payload(milestone_data)
        target_ms = resolve_or_create_milestone(priv_repo, source_ms)
        priv_issue.edit(milestone=target_ms)
        logger.info(
            "Set milestone '%s' on private #%d",
            milestone_data["title"],
            priv_issue.number,
        )
    elif action == "demilestoned":
        priv_issue.edit(milestone=None)
        logger.info("Removed milestone from private #%d", priv_issue.number)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/handlers/test_public_issue_milestoned.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```
feat(handlers): add public_issue_milestoned handler with tests
```

---

### Task 4: `private_issue_milestoned` handler (tests first)

**Files:**
- Create: `tests/handlers/test_private_issue_milestoned.py`
- Create: `lyrebird/handlers/private_issue_milestoned.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for private_issue_milestoned handler."""

from __future__ import annotations

from unittest.mock import MagicMock

from lyrebird.handlers.private_issue_milestoned import handle
from tests.conftest import (
    make_mock_issue,
    make_mock_milestone,
    make_private_issue_body,
)


def _make_private_milestone_payload(
    action: str = "milestoned",
    issue_number: int = 100,
    milestone_title: str = "v1.0",
) -> dict:
    """Build a private milestone event payload."""
    return {
        "action": action,
        "issue": {
            "number": issue_number,
            "body": make_private_issue_body(),
            "node_id": "I_privNode",
            "title": "[public #42] Bug report",
            "state": "open",
            "html_url": f"https://github.com/testorg/private-repo/issues/{issue_number}",
            "user": {"login": "dev"},
        },
        "milestone": {
            "title": milestone_title,
            "description": "Release milestone",
            "due_on": "2026-06-01T00:00:00Z",
            "state": "open",
            "number": 1,
        },
        "sender": {"login": "dev", "type": "User"},
    }


class TestMilestoned:
    def test_creates_milestone_on_public_repo_and_assigns(self, config, mock_client):
        payload = _make_private_milestone_payload()

        mock_pub_repo = MagicMock()
        mock_priv_repo = MagicMock()
        mock_pub_issue = make_mock_issue(number=42)

        # No existing milestone in public repo
        mock_pub_repo.get_milestones.return_value = []
        created_ms = make_mock_milestone(title="v1.0")
        mock_pub_repo.create_milestone.return_value = created_ms

        def get_repo(name):
            if name == config.public_repo:
                return mock_pub_repo
            return mock_priv_repo

        mock_client.get_repo.side_effect = get_repo
        mock_pub_repo.get_issue.return_value = mock_pub_issue

        handle(mock_client, config, payload)

        mock_pub_repo.create_milestone.assert_called_once()
        mock_pub_issue.edit.assert_called_once()
        assert mock_pub_issue.edit.call_args.kwargs["milestone"] is created_ms

    def test_reuses_existing_milestone_on_public(self, config, mock_client):
        payload = _make_private_milestone_payload()

        mock_pub_repo = MagicMock()
        mock_priv_repo = MagicMock()
        mock_pub_issue = make_mock_issue(number=42)

        existing_ms = make_mock_milestone(title="v1.0")
        mock_pub_repo.get_milestones.return_value = [existing_ms]

        def get_repo(name):
            if name == config.public_repo:
                return mock_pub_repo
            return mock_priv_repo

        mock_client.get_repo.side_effect = get_repo
        mock_pub_repo.get_issue.return_value = mock_pub_issue

        handle(mock_client, config, payload)

        mock_pub_repo.create_milestone.assert_not_called()
        assert mock_pub_issue.edit.call_args.kwargs["milestone"] is existing_ms

    def test_no_op_when_no_body_markers(self, config, mock_client):
        """Private issue without body markers is not a mirror — skip."""
        payload = _make_private_milestone_payload()
        payload["issue"]["body"] = "Just a regular private issue"

        mock_pub_repo = MagicMock()
        mock_priv_repo = MagicMock()

        def get_repo(name):
            if name == config.public_repo:
                return mock_pub_repo
            return mock_priv_repo

        mock_client.get_repo.side_effect = get_repo

        handle(mock_client, config, payload)

        mock_pub_repo.get_issue.assert_not_called()
        mock_pub_repo.create_milestone.assert_not_called()


class TestDemilestoned:
    def test_removes_milestone_from_public(self, config, mock_client):
        payload = _make_private_milestone_payload(action="demilestoned")

        mock_pub_repo = MagicMock()
        mock_priv_repo = MagicMock()
        mock_pub_issue = make_mock_issue(number=42)

        def get_repo(name):
            if name == config.public_repo:
                return mock_pub_repo
            return mock_priv_repo

        mock_client.get_repo.side_effect = get_repo
        mock_pub_repo.get_issue.return_value = mock_pub_issue

        handle(mock_client, config, payload)

        mock_pub_issue.edit.assert_called_once_with(milestone=None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/handlers/test_private_issue_milestoned.py -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement `private_issue_milestoned.py`**

Create `lyrebird/handlers/private_issue_milestoned.py`:

```python
"""Handle private issue milestoned/demilestoned: mirror to public."""

from __future__ import annotations

import logging

from github import Github

from lyrebird.config import Config
from lyrebird.mapping import parse_private_body_markers, public_number_from_url
from lyrebird.milestones import milestone_from_payload, resolve_or_create_milestone

logger = logging.getLogger(__name__)


def handle(client: Github, config: Config, payload: dict) -> None:
    action = payload["action"]
    issue = payload["issue"]
    issue_body = issue.get("body") or ""

    markers = parse_private_body_markers(issue_body)
    if markers is None:
        logger.info(
            "Private #%d has no body markers, skipping milestone sync",
            issue["number"],
        )
        return

    public_url, _ = markers
    public_number = public_number_from_url(public_url)

    pub_repo = client.get_repo(config.public_repo)
    pub_issue = pub_repo.get_issue(public_number)

    if action == "milestoned":
        milestone_data = payload["milestone"]
        source_ms = milestone_from_payload(milestone_data)
        target_ms = resolve_or_create_milestone(pub_repo, source_ms)
        pub_issue.edit(milestone=target_ms)
        logger.info(
            "Set milestone '%s' on public #%d",
            milestone_data["title"],
            public_number,
        )
    elif action == "demilestoned":
        pub_issue.edit(milestone=None)
        logger.info("Removed milestone from public #%d", public_number)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/handlers/test_private_issue_milestoned.py -v`
Expected: All PASS

- [ ] **Step 5: Run all tests**

Run: `poetry run pytest -x -q`
Expected: All PASS

- [ ] **Step 6: Commit**

```
feat(handlers): add private_issue_milestoned handler with tests
```

---

### Task 5: Dispatch routes

**Files:**
- Modify: `lyrebird/dispatch.py`
- Modify: `tests/test_dispatch.py` (if it exists; read first)

- [ ] **Step 1: Read `tests/test_dispatch.py`**

Read to understand existing dispatch test patterns.

- [ ] **Step 2: Add imports and routes to `dispatch.py`**

Add to the import block at line 11-26:

```python
    private_issue_milestoned,
    public_issue_milestoned,
```

Add to `PUBLIC_ROUTES` (after the `untyped` entry):

```python
    ("issues", "milestoned"): public_issue_milestoned.handle,
    ("issues", "demilestoned"): public_issue_milestoned.handle,
```

Add to `PRIVATE_ROUTES` (after the `untyped` entry):

```python
    ("issues", "milestoned"): private_issue_milestoned.handle,
    ("issues", "demilestoned"): private_issue_milestoned.handle,
```

- [ ] **Step 3: Run all tests**

Run: `poetry run pytest -x -q`
Expected: All PASS

- [ ] **Step 4: Commit**

```
feat(dispatch): register milestone event routes
```

---

### Task 6: Mirror milestone in `public_issue_opened`

**Files:**
- Modify: `lyrebird/handlers/public_issue_opened.py`
- Modify: `tests/handlers/test_public_issue_opened.py`

- [ ] **Step 1: Write failing test**

Add to `tests/handlers/test_public_issue_opened.py`:

```python
def test_mirrors_milestone_on_creation(config, mock_client):
    """When public issue is created with a milestone, mirror it to private."""
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
        "sender": {"login": "reporter", "type": "User"},
    }

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue_obj = make_mock_issue(number=42)
    mock_pub_issue_obj.get_comments.return_value = []

    mock_priv_issue = MagicMock()
    mock_priv_issue.number = 10
    mock_priv_repo.create_issue.return_value = mock_priv_issue
    mock_priv_repo.get_issues.return_value = []

    # No existing milestone — will be created
    mock_priv_repo.get_milestones.return_value = []
    created_ms = MagicMock()
    created_ms.title = "v1.0"
    mock_priv_repo.create_milestone.return_value = created_ms

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    mock_pub_repo.get_issue.return_value = mock_pub_issue_obj

    handle(mock_client, config, payload)

    mock_priv_repo.create_milestone.assert_called_once()
    mock_priv_issue.edit.assert_called_once()
    assert mock_priv_issue.edit.call_args.kwargs["milestone"] is created_ms


def test_no_milestone_edit_when_no_milestone(config, mock_client):
    """When public issue has no milestone, don't call edit for milestone."""
    public_issue = make_public_issue_payload()
    payload = {
        "issue": public_issue,
        "sender": {"login": "reporter", "type": "User"},
    }

    mock_pub_repo = MagicMock()
    mock_priv_repo = MagicMock()
    mock_pub_issue_obj = make_mock_issue(number=42)
    mock_pub_issue_obj.get_comments.return_value = []

    mock_priv_issue = MagicMock()
    mock_priv_issue.number = 10
    mock_priv_repo.create_issue.return_value = mock_priv_issue
    mock_priv_repo.get_issues.return_value = []

    def get_repo(name):
        if name == config.public_repo:
            return mock_pub_repo
        return mock_priv_repo

    mock_client.get_repo.side_effect = get_repo
    mock_pub_repo.get_issue.return_value = mock_pub_issue_obj

    handle(mock_client, config, payload)

    # edit should NOT be called (no milestone to set)
    mock_priv_issue.edit.assert_not_called()
```

- [ ] **Step 2: Run tests to verify the new test fails**

Run: `poetry run pytest tests/handlers/test_public_issue_opened.py::test_mirrors_milestone_on_creation -v`
Expected: FAIL

- [ ] **Step 3: Modify `public_issue_opened.py` to mirror milestones**

Add import at the top of `public_issue_opened.py`:

```python
from lyrebird.milestones import resolve_or_create_milestone
```

Add after the `set_issue_type` block (after line 61) and before the mapping comment section:

```python
    # Mirror milestone if present
    milestone_data = public_issue.get("milestone")
    if milestone_data:
        from lyrebird.milestones import milestone_from_payload

        source_ms = milestone_from_payload(milestone_data)
        target_ms = resolve_or_create_milestone(priv_repo, source_ms)
        private_issue.edit(milestone=target_ms)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/handlers/test_public_issue_opened.py -v`
Expected: All PASS

- [ ] **Step 5: Run all tests**

Run: `poetry run pytest -x -q`
Expected: All PASS

- [ ] **Step 6: Commit**

```
feat(handlers): mirror milestone during public issue creation
```

---

### Task 7: Sync — milestone metadata reconciliation

**Files:**
- Modify: `lyrebird/sync.py`
- Modify: `tests/test_sync.py`

- [ ] **Step 1: Update `_setup_repos` to set default empty returns**

In `tests/test_sync.py`, modify `_setup_repos` to add default empty returns for `get_milestones` and `get_labels` so existing tests don't break when `sync()` gains the new milestone and label passes:

```python
def _setup_repos(config, mock_client, pub_issues, priv_issues=None):
    """Wire up mock repos and client.get_repo routing."""
    pub_repo = MagicMock()
    pub_repo.get_issues.return_value = pub_issues
    pub_repo.get_milestones.return_value = []
    pub_repo.get_labels.return_value = []

    priv_repo = MagicMock()
    priv_repo.get_issues.return_value = priv_issues or []
    priv_repo.get_milestones.return_value = []
    priv_repo.get_labels.return_value = []

    def get_repo(name):
        if name == config.public_repo:
            return pub_repo
        return priv_repo

    mock_client.get_repo.side_effect = get_repo
    return pub_repo, priv_repo
```

- [ ] **Step 2: Write failing tests for milestone metadata sync**

Add to `tests/test_sync.py`:

```python
from tests.conftest import make_mock_milestone


class TestSyncsMilestoneMetadata:
    def test_creates_missing_milestone_in_private(self, config, mock_client):
        """A public milestone with no title-match in private gets created."""
        pub_ms = make_mock_milestone(title="v2.0", description="New release")
        pub_repo, priv_repo = _setup_repos(config, mock_client, [])
        pub_repo.get_milestones.return_value = [pub_ms]
        priv_repo.get_milestones.return_value = []
        created = make_mock_milestone(title="v2.0")
        priv_repo.create_milestone.return_value = created

        stats = sync(mock_client, config, since_hours=None)

        priv_repo.create_milestone.assert_called_once()
        assert stats.milestones_created >= 1

    def test_creates_missing_milestone_in_public(self, config, mock_client):
        """A private milestone with no title-match in public gets created."""
        priv_ms = make_mock_milestone(title="internal-v3")
        pub_repo, priv_repo = _setup_repos(config, mock_client, [])
        pub_repo.get_milestones.return_value = []
        priv_repo.get_milestones.return_value = [priv_ms]
        created = make_mock_milestone(title="internal-v3")
        pub_repo.create_milestone.return_value = created

        stats = sync(mock_client, config, since_hours=None)

        pub_repo.create_milestone.assert_called_once()
        assert stats.milestones_created >= 1

    def test_updates_matched_milestone_properties(self, config, mock_client):
        """Matched milestones sync properties from more recently updated."""
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        pub_ms = make_mock_milestone(title="v1.0", description="old desc")
        pub_ms.updated_at = now - timedelta(hours=1)

        priv_ms = make_mock_milestone(title="v1.0", description="new desc")
        priv_ms.updated_at = now

        pub_repo, priv_repo = _setup_repos(config, mock_client, [])
        pub_repo.get_milestones.return_value = [pub_ms]
        priv_repo.get_milestones.return_value = [priv_ms]

        stats = sync(mock_client, config, since_hours=None)

        # Private is newer, so public should be updated
        pub_ms.edit.assert_called_once()
        assert pub_ms.edit.call_args.kwargs["description"] == "new desc"
        assert stats.milestones_updated >= 1

    def test_no_update_when_milestones_identical(self, config, mock_client):
        """No update when matched milestones have same properties."""
        pub_ms = make_mock_milestone(title="v1.0", description="same")
        priv_ms = make_mock_milestone(title="v1.0", description="same")

        pub_repo, priv_repo = _setup_repos(config, mock_client, [])
        pub_repo.get_milestones.return_value = [pub_ms]
        priv_repo.get_milestones.return_value = [priv_ms]

        stats = sync(mock_client, config, since_hours=None)

        pub_ms.edit.assert_not_called()
        priv_ms.edit.assert_not_called()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `poetry run pytest tests/test_sync.py::TestSyncsMilestoneMetadata -v`
Expected: FAIL (no `milestones_created` attribute on SyncStats)

- [ ] **Step 4: Add milestone counters to `SyncStats`**

Add to the `SyncStats` dataclass (after `labels_synced`):

```python
    milestones_created: int = 0
    milestones_updated: int = 0
    milestones_assigned: int = 0
    labels_properties_synced: int = 0
```

Add to `summary()`:

```python
            f"Milestones created: {self.milestones_created}",
            f"Milestones updated: {self.milestones_updated}",
            f"Milestones assigned: {self.milestones_assigned}",
            f"Labels properties synced: {self.labels_properties_synced}",
```

- [ ] **Step 5: Add `_sync_milestones` function to `sync.py`**

Add import at the top:

```python
from lyrebird.milestones import (
    find_milestone_by_title,
    resolve_or_create_milestone,
    sync_milestone_properties,
)
```

Add function before `_sync_issue`:

```python
def _sync_milestones(
    pub_repo: Repository, priv_repo: Repository, stats: SyncStats
) -> None:
    """Reconcile milestones between repos: create missing, update matched."""
    pub_milestones = {
        ms.title: ms
        for state in ("open", "closed")
        for ms in pub_repo.get_milestones(state=state)
    }
    priv_milestones = {
        ms.title: ms
        for state in ("open", "closed")
        for ms in priv_repo.get_milestones(state=state)
    }

    all_titles = set(pub_milestones) | set(priv_milestones)

    for title in all_titles:
        pub_ms = pub_milestones.get(title)
        priv_ms = priv_milestones.get(title)

        if pub_ms and priv_ms:
            # Both exist — sync properties from most recently updated
            if pub_ms.updated_at >= priv_ms.updated_at:
                if sync_milestone_properties(priv_ms, pub_ms):
                    stats.milestones_updated += 1
            else:
                if sync_milestone_properties(pub_ms, priv_ms):
                    stats.milestones_updated += 1
        elif pub_ms and not priv_ms:
            resolve_or_create_milestone(priv_repo, pub_ms)
            stats.milestones_created += 1
            logger.info("Created milestone '%s' in private repo", title)
        elif priv_ms and not pub_ms:
            resolve_or_create_milestone(pub_repo, priv_ms)
            stats.milestones_created += 1
            logger.info("Created milestone '%s' in public repo", title)
```

- [ ] **Step 6: Call `_sync_milestones` from `sync()` — before Pass 1**

In the `sync()` function, add after `priv_repo = client.get_repo(config.private_repo)` (line 90) and before `since_dt`:

```python
    # Milestone metadata sync (before issue passes)
    _sync_milestones(pub_repo, priv_repo, stats)
```

- [ ] **Step 7: Run milestone metadata tests**

Run: `poetry run pytest tests/test_sync.py::TestSyncsMilestoneMetadata -v`
Expected: All PASS

- [ ] **Step 8: Run all tests**

Run: `poetry run pytest -x -q`
Expected: All PASS

- [ ] **Step 9: Commit**

```
feat(sync): add milestone metadata reconciliation
```

---

### Task 8: Sync — label property reconciliation

**Files:**
- Modify: `lyrebird/sync.py`
- Modify: `tests/test_sync.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_sync.py`:

```python
class TestSyncsLabelProperties:
    def test_updates_private_label_color_to_match_public(self, config, mock_client):
        """Public is authoritative — private label color updated to match."""
        pub_label = MagicMock()
        pub_label.name = "bug"
        pub_label.color = "d73a4a"
        pub_label.description = "Bug report"

        priv_label = MagicMock()
        priv_label.name = "bug"
        priv_label.color = "000000"
        priv_label.description = "Bug report"

        pub_repo, priv_repo = _setup_repos(config, mock_client, [])
        pub_repo.get_labels.return_value = [pub_label]
        priv_repo.get_labels.return_value = [priv_label]
        # Need milestones to not error
        pub_repo.get_milestones.return_value = []
        priv_repo.get_milestones.return_value = []

        stats = sync(mock_client, config, since_hours=None)

        priv_label.edit.assert_called_once_with(
            name="bug", color="d73a4a", description="Bug report"
        )
        assert stats.labels_properties_synced >= 1

    def test_updates_private_label_description(self, config, mock_client):
        pub_label = MagicMock()
        pub_label.name = "enhancement"
        pub_label.color = "a2eeef"
        pub_label.description = "New feature"

        priv_label = MagicMock()
        priv_label.name = "enhancement"
        priv_label.color = "a2eeef"
        priv_label.description = ""

        pub_repo, priv_repo = _setup_repos(config, mock_client, [])
        pub_repo.get_labels.return_value = [pub_label]
        priv_repo.get_labels.return_value = [priv_label]
        pub_repo.get_milestones.return_value = []
        priv_repo.get_milestones.return_value = []

        stats = sync(mock_client, config, since_hours=None)

        priv_label.edit.assert_called_once()
        assert stats.labels_properties_synced >= 1

    def test_no_update_when_labels_identical(self, config, mock_client):
        pub_label = MagicMock()
        pub_label.name = "bug"
        pub_label.color = "d73a4a"
        pub_label.description = "Bug"

        priv_label = MagicMock()
        priv_label.name = "bug"
        priv_label.color = "d73a4a"
        priv_label.description = "Bug"

        pub_repo, priv_repo = _setup_repos(config, mock_client, [])
        pub_repo.get_labels.return_value = [pub_label]
        priv_repo.get_labels.return_value = [priv_label]
        pub_repo.get_milestones.return_value = []
        priv_repo.get_milestones.return_value = []

        stats = sync(mock_client, config, since_hours=None)

        priv_label.edit.assert_not_called()

    def test_does_not_create_missing_labels(self, config, mock_client):
        """Labels only in one repo should NOT be created in the other."""
        pub_label = MagicMock()
        pub_label.name = "public-only"
        pub_label.color = "ffffff"
        pub_label.description = ""

        pub_repo, priv_repo = _setup_repos(config, mock_client, [])
        pub_repo.get_labels.return_value = [pub_label]
        priv_repo.get_labels.return_value = []
        pub_repo.get_milestones.return_value = []
        priv_repo.get_milestones.return_value = []

        stats = sync(mock_client, config, since_hours=None)

        priv_repo.create_label.assert_not_called()
        pub_repo.create_label.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_sync.py::TestSyncsLabelProperties -v`
Expected: FAIL

- [ ] **Step 3: Add `_sync_label_properties` to `sync.py`**

```python
def _sync_label_properties(
    pub_repo: Repository, priv_repo: Repository, stats: SyncStats
) -> None:
    """Sync color and description for labels that exist in both repos.

    Public repo is authoritative (labels lack updated_at).
    """
    pub_labels = {lbl.name: lbl for lbl in pub_repo.get_labels()}
    priv_labels = {lbl.name: lbl for lbl in priv_repo.get_labels()}

    for name in pub_labels:
        if name not in priv_labels:
            continue

        pub_lbl = pub_labels[name]
        priv_lbl = priv_labels[name]

        pub_color = pub_lbl.color or ""
        priv_color = priv_lbl.color or ""
        pub_desc = pub_lbl.description or ""
        priv_desc = priv_lbl.description or ""

        if pub_color != priv_color or pub_desc != priv_desc:
            priv_lbl.edit(name=name, color=pub_color, description=pub_desc)
            stats.labels_properties_synced += 1
            logger.info("Updated label '%s' properties in private repo", name)
```

- [ ] **Step 4: Call `_sync_label_properties` from `sync()` — after milestones, before issue passes**

Add right after the `_sync_milestones` call:

```python
    # Label property sync (after milestones, before issues)
    _sync_label_properties(pub_repo, priv_repo, stats)
```

- [ ] **Step 5: Run label property tests**

Run: `poetry run pytest tests/test_sync.py::TestSyncsLabelProperties -v`
Expected: All PASS

- [ ] **Step 6: Run all tests**

Run: `poetry run pytest -x -q`
Expected: All PASS

- [ ] **Step 7: Commit**

```
feat(sync): add label property reconciliation (public authoritative)
```

---

### Task 9: Sync — issue milestone assignment

**Files:**
- Modify: `lyrebird/sync.py`
- Modify: `tests/test_sync.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_sync.py`:

```python
class TestSyncsIssueMilestone:
    def test_syncs_milestone_public_to_private(self, config, mock_client):
        """Pass 1: public issue has milestone, private doesn't — sync it."""
        pub_ms = make_mock_milestone(title="v1.0")
        priv_issue = _make_priv_issue()
        priv_issue.milestone = None
        mapping_comment = make_mock_comment(body=MAPPING_BODY)

        pub_issue = _make_pub_issue()
        pub_issue.milestone = pub_ms
        pub_issue.get_comments.return_value = [mapping_comment]

        pub_repo, priv_repo = _setup_repos(config, mock_client, [pub_issue])
        pub_repo.get_issue.return_value = pub_issue
        priv_repo.get_issue.return_value = priv_issue
        pub_repo.get_milestones.return_value = [pub_ms]
        priv_repo.get_milestones.return_value = []
        pub_repo.get_labels.return_value = []
        priv_repo.get_labels.return_value = []

        target_ms = make_mock_milestone(title="v1.0")
        priv_repo.create_milestone.return_value = target_ms

        stats = sync(mock_client, config, since_hours=None)

        assert stats.milestones_assigned >= 1
        milestone_edits = [
            c for c in priv_issue.edit.call_args_list
            if "milestone" in c.kwargs
        ]
        assert len(milestone_edits) >= 1

    def test_removes_milestone_when_public_has_none(self, config, mock_client):
        """Pass 1: public has no milestone but private does — remove it."""
        priv_ms = make_mock_milestone(title="v1.0")
        priv_issue = _make_priv_issue()
        priv_issue.milestone = priv_ms
        mapping_comment = make_mock_comment(body=MAPPING_BODY)

        pub_issue = _make_pub_issue()
        pub_issue.milestone = None
        pub_issue.get_comments.return_value = [mapping_comment]

        pub_repo, priv_repo = _setup_repos(config, mock_client, [pub_issue])
        pub_repo.get_issue.return_value = pub_issue
        priv_repo.get_issue.return_value = priv_issue
        pub_repo.get_milestones.return_value = []
        priv_repo.get_milestones.return_value = [priv_ms]
        pub_repo.get_labels.return_value = []
        priv_repo.get_labels.return_value = []

        stats = sync(mock_client, config, since_hours=None)

        milestone_edits = [
            c for c in priv_issue.edit.call_args_list
            if c.kwargs.get("milestone") is None
        ]
        assert len(milestone_edits) >= 1

    def test_no_change_when_milestones_match(self, config, mock_client):
        """No milestone edit when both issues have the same milestone."""
        pub_ms = make_mock_milestone(title="v1.0")
        priv_ms = make_mock_milestone(title="v1.0")

        priv_issue = _make_priv_issue()
        priv_issue.milestone = priv_ms
        mapping_comment = make_mock_comment(body=MAPPING_BODY)

        pub_issue = _make_pub_issue()
        pub_issue.milestone = pub_ms
        pub_issue.get_comments.return_value = [mapping_comment]

        pub_repo, priv_repo = _setup_repos(config, mock_client, [pub_issue])
        pub_repo.get_issue.return_value = pub_issue
        priv_repo.get_issue.return_value = priv_issue
        pub_repo.get_milestones.return_value = [pub_ms]
        priv_repo.get_milestones.return_value = [priv_ms]
        pub_repo.get_labels.return_value = []
        priv_repo.get_labels.return_value = []

        stats = sync(mock_client, config, since_hours=None)

        milestone_edits = [
            c for c in priv_issue.edit.call_args_list
            if "milestone" in c.kwargs
        ]
        assert len(milestone_edits) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/test_sync.py::TestSyncsIssueMilestone -v`
Expected: FAIL

- [ ] **Step 3: Add milestone sync to `_sync_issue` (Pass 1)**

In `_sync_issue()`, add after the `_sync_labels` call:

```python
    # Sync milestone (public → private)
    _sync_issue_milestone(priv_repo, priv_issue, pub_issue, stats)
```

Add the helper function:

```python
def _sync_issue_milestone(
    target_repo: Repository, target_issue, source_issue, stats: SyncStats
) -> None:
    """Sync milestone assignment from source issue to target issue."""
    source_ms_title = source_issue.milestone.title if source_issue.milestone else None
    target_ms_title = target_issue.milestone.title if target_issue.milestone else None

    if source_ms_title == target_ms_title:
        return

    if source_ms_title is None:
        target_issue.edit(milestone=None)
        stats.milestones_assigned += 1
        logger.info("Removed milestone from target #%d", target_issue.number)
    else:
        target_ms = resolve_or_create_milestone(target_repo, source_issue.milestone)
        target_issue.edit(milestone=target_ms)
        stats.milestones_assigned += 1
        logger.info(
            "Set milestone '%s' on target #%d",
            source_ms_title,
            target_issue.number,
        )
```

- [ ] **Step 4: Add milestone sync to `_check_private_state` (Pass 2)**

In `_check_private_state()`, `pub_repo` is already a parameter. After the state sync logic (the `_sync_state_to_public` call and the `if pub_issue.state == priv_issue.state:` block), add milestone sync for the private→public direction:

```python
    # Sync milestone (private → public)
    _sync_issue_milestone(pub_repo, pub_issue, priv_issue, stats)
```

- [ ] **Step 5: Run tests**

Run: `poetry run pytest tests/test_sync.py::TestSyncsIssueMilestone -v`
Expected: All PASS

- [ ] **Step 6: Run all tests**

Run: `poetry run pytest -x -q`
Expected: All PASS

- [ ] **Step 7: Commit**

```
feat(sync): add per-issue milestone assignment reconciliation
```

---

### Task 10: Workflow YAML updates

**Files:**
- Modify: `workflows/public-dispatch.yml`
- Modify: `workflows/handle-private-issue.yml`

- [ ] **Step 1: Update `public-dispatch.yml`**

Change line 10 from:

```yaml
    types: [opened, edited, labeled, unlabeled, closed, reopened, typed, untyped]
```

to:

```yaml
    types: [opened, edited, labeled, unlabeled, closed, reopened, typed, untyped, milestoned, demilestoned]
```

- [ ] **Step 2: Update `handle-private-issue.yml`**

Change line 9 from:

```yaml
    types: [closed, reopened, labeled, unlabeled, typed, untyped]
```

to:

```yaml
    types: [closed, reopened, labeled, unlabeled, typed, untyped, milestoned, demilestoned]
```

- [ ] **Step 3: Run all tests (sanity check)**

Run: `poetry run pytest -x -q`
Expected: All PASS

- [ ] **Step 4: Commit**

```
ci(workflows): add milestoned/demilestoned event types
```

- [ ] **Step 5: Remind user to deploy updated workflows**

Print: "Remember to deploy the updated workflows to both repos using `scripts/deploy.sh`."

---

### Task 11: Final verification

- [ ] **Step 1: Run full test suite**

Run: `poetry run pytest -v`
Expected: All PASS

- [ ] **Step 2: Verify no regressions in existing functionality**

Run: `poetry run pytest tests/handlers/ -v`
Expected: All PASS

- [ ] **Step 3: Verify new test count**

Run: `poetry run pytest --co -q | tail -5`
Expected: New tests visible for milestones, public_issue_milestoned, private_issue_milestoned, and sync extensions.
