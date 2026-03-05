# Plan: Private Issue Closure with Delayed Resolution Check

## Overview

When a private mirrored issue is closed, the public issue is always closed immediately. If a resolution label is present, the predefined note is posted right away. Otherwise, a 5-minute grace period (via a sleep step in the workflow) allows the maintainer to add a label or post a custom message via `/anon`. After the grace period, if nothing was done, the system nudges on private.

## Label naming

All resolution-related labels use the `resolution:` prefix:

| Label | Purpose |
|-------|---------|
| `resolution:completed` | Resolved as completed |
| `resolution:not-planned` | Resolved as not planned |
| `resolution:cannot-reproduce` | Could not reproduce |
| `resolution:custom` | Custom message posted via `/anon` |
| `resolution:none` | Nudge: no resolution posted yet |

This replaces the previous `external:` prefix and `needs-public-resolution` label.

## Flows

### 1. Private issue closed (`private_issue_closed.py`)

```
How many resolution labels?
+-- Exactly 1 -> close public with predefined note
+-- 0 or >1   -> close public with no comment
                  (delayed job handles the rest after 5 min)
```

**Changes:** Remove the current nudge logic from the close handler. The "no label" path just closes public and returns. The nudge moves to the delayed handler.

### 2. Delayed check -- new handler (`private_issue_closed_check.py`)

Runs 5 min after close via a sleep step in the workflow. Uses `EVENT_ACTION: closed_check` to dispatch through the normal route table (no CLI flag needed).

```
Issue still closed?
+-- No  -> bail out (reopened during the grace period)
+-- Yes -> Exactly 1 resolution label?
           +-- Yes -> do nothing (label handler already took care of it)
           +-- No  -> add resolution:none on private (if not already present),
                      post nudge comment:
                      "No resolution posted publicly. Add exactly one
                       resolution label, or use /anon."
```

**New file.** Receives the same payload. Fetches fresh label state from the API.

### 3. Resolution label added on closed private issue (`private_labels_changed.py`)

```
Issue closed AND resolution label added?
+-- Yes -> post resolution note on public issue
           if has resolution:none -> remove it
+-- No  -> existing behavior (mirror label to public)
```

**Changes:** Current `private_labels_changed.py` needs to handle this new case for closed issues.

### 4. `/anon` on a closed issue (`slash_anon.py`)

```
Issue closed AND (no resolution label OR has resolution:none)?
+-- Yes -> remove resolution:none (if present)
           add resolution:custom
+-- No  -> (existing behavior, just post the message)
```

The `/anon` message is always posted (existing behavior). The new logic just handles the label bookkeeping so the delayed check and label handler know a custom message was provided.

**Changes:** Add closed-issue label logic after posting the message.

## Config changes (`config.py`)

- Rename all resolution labels from `external:` to `resolution:` prefix
- Rename `needs-public-resolution` to `resolution:none`
- Add a `custom` resolution key with no predefined note and no state_reason:
  ```python
  "custom": ("resolution:custom", "", None)
  ```
  This label acts as a resolution label, so the delayed check sees it and skips the nudge.

## Workflow changes

- Add a delayed job to `handle-private-issue.yml` with a `sleep 300` step:
  ```yaml
  jobs:
    handle-event:
      # ... existing job ...

    delayed-close-check:
      if: github.event.action == 'closed'
      needs: handle-event
      runs-on: ubuntu-slim
      steps:
        - name: Wait 5 minutes
          run: sleep 300
        # ... same checkout/setup/install/token steps ...
        - name: Run delayed close check
          env:
            # ... same env vars ...
            EVENT_ACTION: closed_check   # override to route to delayed handler
          run: python -m lyrebird
  ```

## Dispatch changes (`dispatch.py`)

Add a route entry in `PRIVATE_ROUTES`:
```python
("issues", "closed_check"): private_issue_closed_check.handle,
```

No CLI changes needed. The delayed job sets `EVENT_ACTION: closed_check`, which routes through the normal dispatch table.

## Edge cases

### Label swap

If a maintainer adds resolution label A, then swaps to label B, the `private_labels_changed` handler fires for both `labeled` and `unlabeled`. On `labeled` with B, it posts/updates the note. This works naturally.

### `/anon` + resolution label

If someone uses `/anon` AND adds a resolution label, both the custom message and the predefined note end up on public. The `resolution:custom` label prevents the nudge, and the resolution label triggers its own note. This seems fine -- the maintainer is being explicit about both.

### Reopened during the 5-min window

The delayed check fetches fresh issue state from the API. If the issue was reopened before the check runs, it bails out immediately -- no nudge, no label.

### Multiple resolution labels (>1)

Same as 0 labels: close public with no comment, delayed check nudges to pick exactly one. The maintainer needs to remove extras so there's exactly one, which then triggers the note via `private_labels_changed`.

## Files to change

1. `lyrebird/config.py` -- rename `external:` to `resolution:`, rename `needs-public-resolution` to `resolution:none`, add `custom` key
2. `lyrebird/handlers/private_issue_closed.py` -- simplify: always close public, post note only with exactly 1 label
3. `lyrebird/handlers/private_issue_closed_check.py` -- new delayed handler
4. `lyrebird/handlers/private_labels_changed.py` -- handle resolution label added on closed issue
5. `lyrebird/handlers/slash_anon.py` -- label bookkeeping on closed issues
6. `lyrebird/handlers/_cleanup_labels.py` -- update for renamed labels
7. `lyrebird/dispatch.py` -- add `("issues", "closed_check")` route
8. `workflows/handle-private-issue.yml` -- add delayed-close-check job
9. `workflows/handle-private-comment.yml` -- update `RESOLUTION_LABELS` JSON
10. `workflows/handle-public-event.yml` -- update `RESOLUTION_LABELS` JSON
11. `scripts/setup-test-repos.sh` -- update label names, add `resolution:custom`
12. Tests, docs, demo -- update for renamed labels
