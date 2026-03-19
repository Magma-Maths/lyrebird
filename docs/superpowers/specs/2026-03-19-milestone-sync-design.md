# Milestone Synchronization & Label Property Sync

## Overview

Extend Lyrebird with bidirectional milestone synchronization between public and private repos, plus label property (color, description) reconciliation. Milestone-to-issue assignment syncs in real-time via webhooks; milestone metadata (edits, renames) and label properties sync during scheduled `sync.py` runs.

## Requirements

- **Bidirectional** milestone-to-issue assignment sync (real-time)
- **Auto-create** milestones in the target repo with all fields (title, description, due date, state)
- **Milestone metadata sync** (description, due date, state) via `sync.py`
- **Label property sync** (color, description) for labels existing in both repos via `sync.py`
- **Match milestones by title** (case-sensitive, matching GitHub's behavior); users must use identical titles in both repos
- **Always-on** — no config flag needed

## Approach: Shared Milestone Resolver (Approach B)

Extract a shared `resolve_or_create_milestone()` helper used by both real-time handlers and sync. Follows existing codebase patterns while avoiding duplication.

## Known Limitations

- **Milestone renames are not detected during sync.** If a milestone is renamed in one repo, sync will treat it as a new milestone and create it in the other repo; the old-named milestone becomes orphaned. Users should rename milestones in both repos manually. A future improvement could add HTML comment markers to milestone descriptions for identity tracking across renames.
- **Milestone title matching is case-sensitive.** "v1.0" and "V1.0" are treated as different milestones, consistent with GitHub's behavior.

## Design

### 1. New Module: `lyrebird/milestones.py`

Shared milestone helper module (parallel to `mapping.py`).

**`find_milestone_by_title(repo, title) -> Milestone | None`**
Iterates milestones in the repo (both open and closed) to find one matching the given title. Matching is case-sensitive. Returns the PyGithub `Milestone` object or `None`.

**`resolve_or_create_milestone(target_repo, source_milestone) -> Milestone`**
Looks up a milestone by title in `target_repo`. If found, returns it. If not, creates it with all fields copied from `source_milestone` (title, description, due date, state — including closed milestones). Returns the new/existing milestone.

**`sync_milestone_properties(target_milestone, source_milestone) -> bool`**
Compares description, due date, and state. If any differ, updates the target. Returns whether an update was made. Does **not** sync title — title renames are not detected (see Known Limitations).

### 2. Real-Time Handlers

**`handlers/public_issue_milestoned.py`** — handles both `milestoned` and `demilestoned` actions:

1. Resolve the private issue via `resolve_mapping()`
2. If no mapping found, log and return (issue not yet mirrored)
3. On `milestoned`: call `resolve_or_create_milestone(private_repo, source_milestone)` then set the private issue's milestone
4. On `demilestoned`: set the private issue's milestone to `None`

**`handlers/private_issue_milestoned.py`** — same logic, opposite direction:

1. Parse the public issue URL from the private issue body markers
2. If no body markers found, log and return (not a mirrored issue)
3. On `milestoned`: call `resolve_or_create_milestone(public_repo, source_milestone)` then set the public issue's milestone
4. On `demilestoned`: set the public issue's milestone to `None`

**Milestone at issue creation:** The existing `public_issue_opened` handler must be updated to mirror the milestone (if present) when creating the private issue. GitHub fires the `milestoned` event before the private mirror exists, so the real-time handler will miss it. This parallels how `public_issue_opened` already mirrors labels and issue type.

**Loop prevention:** Both handlers inherit the existing `is_bot_event()` check in `cli.py`. When a handler sets a milestone on the target issue, the resulting webhook event is from the bot and gets filtered.

**Idempotency:** Setting a milestone to the same value is a no-op at the GitHub API level.

**Payload structure:** Both `milestoned` and `demilestoned` events include the milestone under `payload["milestone"]`. For `milestoned`, `payload["issue"]["milestone"]` also reflects the current milestone, but handlers should read from `payload["milestone"]` for consistency.

### 3. Dispatch Routes and Workflow Changes

**`dispatch.py`** — four new route entries and two new imports (`public_issue_milestoned`, `private_issue_milestoned`):

```python
# PUBLIC_ROUTES
("issues", "milestoned"):   public_issue_milestoned.handle,
("issues", "demilestoned"): public_issue_milestoned.handle,

# PRIVATE_ROUTES
("issues", "milestoned"):   private_issue_milestoned.handle,
("issues", "demilestoned"): private_issue_milestoned.handle,
```

**`workflows/public-dispatch.yml`** — add `milestoned` and `demilestoned` to the `issues` event types list.

**`workflows/handle-private-issue.yml`** — add `milestoned` and `demilestoned` to the `issues` event types list.

No new workflow files needed.

> **Reminder:** Updated workflows must be installed/deployed to both repos after implementation.

### 4. Sync Extensions

Three additions to `sync.py`. The `SyncStats` dataclass gains new counters: `milestones_created`, `milestones_updated`, `milestones_assigned`, `labels_properties_synced`.

**Milestone metadata sync** (runs before issue passes):

1. Fetch all milestones (open + closed) from both repos
2. Match by title (case-sensitive)
3. Matched pairs: call `sync_milestone_properties()` to reconcile description, due date, state. Conflict resolution: most-recently-updated milestone wins (using `milestone.updated_at`).
4. Unmatched milestones: create in the other repo (safe, idempotent). Rename/delete detection is not attempted (see Known Limitations).

**Label property sync** (runs after milestone sync, before issue passes):

1. Fetch all labels from both repos
2. For labels with matching names that exist in both repos, compare color and description
3. If they differ, the **public repo is authoritative** — the public label's properties are copied to the private label. (GitHub labels lack an `updated_at` field, so timestamp-based conflict resolution is not possible.)
4. No creation of missing labels — labels are only created as a side effect of issue mirroring, never proactively synced into existence. Consistent with existing behavior where private labels are never pushed to the public repo.

**Issue milestone assignment sync** (added to existing per-issue logic):

- **Pass 1** (public→private): if the public issue's milestone differs from the private issue's milestone, sync public→private via `resolve_or_create_milestone()`
- **Pass 2** (private→public): if the private issue's milestone differs from the public issue's milestone, sync private→public via `resolve_or_create_milestone()`. Only applies when the private change was by a human (not bot), consistent with Pass 2's existing behavior.
- If source has no milestone but target does, set target milestone to `None`

### 5. Testing

**New test files:**

**`tests/handlers/test_public_issue_milestoned.py`**
- Milestoned: creates milestone in private repo if missing, assigns to private issue
- Milestoned: reuses existing milestone if title matches
- Demilestoned: removes milestone from private issue
- Milestoned with no mapping: logs and returns (no-op)
- All milestone fields copied on auto-create (title, description, due date, state)

**`tests/handlers/test_private_issue_milestoned.py`**
- Milestoned: creates milestone in public repo if missing, assigns to public issue
- Milestoned: reuses existing milestone if title matches
- Demilestoned: removes milestone from public issue
- Private issue without body markers: returns early (not a mirrored issue)
- All milestone fields copied on auto-create

**`tests/test_milestones.py`**
- `find_milestone_by_title`: found (open), found (closed), not found, case-sensitive mismatch
- `resolve_or_create_milestone`: existing returns it, missing creates with all fields
- `sync_milestone_properties`: updates changed fields, no-op when identical, returns bool

**`tests/test_sync.py` additions:**
- Milestone metadata sync: matched pair updates properties, unmatched creates in other repo
- Label property sync: matched labels with differing color/description get updated (public authoritative), unmatched labels left alone
- Issue milestone assignment sync: milestone added, removed, changed

**Existing test updates:**

**`tests/handlers/test_public_issue_opened.py`**
- New case: issue opened with milestone — milestone is mirrored to private issue

**`tests/conftest.py` additions:**
- `make_mock_milestone()` helper with configurable title, description, due_on, state, number
- Milestone field added to `make_mock_issue()` (default `None`)
