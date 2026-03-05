# Plan: Bidirectional open/closed status sync

## Goal

Keep the open/closed status in sync between public and private mirrored issues.

## Already implemented

- **Private close with 1 resolution label** → closes public issue with a resolution note
- **Private close with 0 or 2+ resolution labels** → adds `needs-public-resolution` label and posts a nudge comment; public stays open
- **Adding a resolution label to an already-closed private issue** → triggers public closure if now exactly 1 label
- **Resolution label + close** → closes both sides with proper labeling
- **Private reopen** → removes resolution labels and `needs-public-resolution` from private
- **Public close** → closes private; posts audit comment
- **Public reopen** → reopens private; posts audit comment

## Shared helper

Both change #2 and #3 need to clean up the same set of labels on the private issue (resolution labels, `needs-public-resolution`). Extract a shared helper — e.g. `_cleanup_private_labels(config, priv_issue)` — to keep the logic in one place. Location TBD (could live in a small utility module or be co-located in one of the handlers and imported by the other).

## Changes needed

### 1. Public close → also close the private issue

**File**: `handlers/public_issue_state.py` (modify existing `action == "closed"` branch)

When a public issue is closed:
- Post audit comment
- Close the private issue (`state="closed"`)
- Loop safety: the bot closes the private issue, so the `private_issue_closed` handler fires but `is_bot_event()` filters it out

### 2. Public reopen → also reopen the private issue

**File**: `handlers/public_issue_state.py` (modify existing `action == "reopened"` branch)

When a public issue is reopened:
- Post audit comment
- Reopen the private issue (`state="open"`)
- Clean up resolution labels and `needs-public-resolution` on the private issue (same cleanup as private reopen handler)
- Loop safety: bot reopens private, `private_issue_reopened` handler fires but `is_bot_event()` filters it out

### 3. Private reopen → also reopen the public issue

**File**: `handlers/private_issue_reopened.py` (extend existing handler)

When a private issue is reopened:
- Keep existing behavior: remove resolution labels and `needs-public-resolution`, post audit comment on private
- **New**: parse private issue body with `parse_private_body_markers()` to find the public issue (currently this handler doesn't look up the public side at all)
- **New**: reopen the public issue (`state="open"`)
- **New**: post a note on the public issue: "This issue has been reopened for further investigation."
- Clean up resolution labels on the private issue
- Loop safety: bot reopens public, `public_issue_state` handler fires but `is_bot_event()` filters it out
