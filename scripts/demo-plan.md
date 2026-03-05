# Demo Script Plan (`demo.sh`)

## Core Philosophy

The script creates 5 issues, each demonstrating a different workflow. To make the
resulting timeline self-explanatory for collaborators, the script posts an
**announcer comment** on the private issue before each action. This means when a
collaborator opens a private issue, they can read it like a narrated walkthrough:

1. *Announcer:* "Adding a 'bug' label on the public side — Lyrebird will mirror it here automatically."
2. *(Lyrebird mirrors the label)*
3. *Announcer:* "Posting a `/anon` reply to show anonymous messaging."
4. *(Lyrebird posts the anonymous reply on public)*

Announcer comments are posted by the same bot token, so they appear inline in the
timeline alongside Lyrebird's mirrored content.

## The 5 Scenarios

### Issue 1: Bug Report Lifecycle
**Public title:** `Bug: crash when loading files larger than 2GB`
**Shows:** mirroring, comments, edits, labels, type sync

1. Create public issue (detailed bug report). Wait for mirror.
2. **Announce:** "A public user is posting additional debug info (a stack trace)."
3. Post public comment with stack trace. Wait for sync.
4. **Announce:** "The reporter is editing the issue to add environment details (OS, version, RAM). The private body will update in place."
5. Edit public issue title and body. Wait for sync.
6. **Announce:** "Adding a 'bug' label on the public side — Lyrebird will mirror it here."
7. Add `bug` label on public. Wait for sync.
8. **Announce:** "Setting the issue type to 'Bug' — Lyrebird will mirror it here."
9. Set issue type to Bug on public. Wait for sync.

### Issue 2: Edits and Deletions
**Public title:** `Error message is misleading when config file is missing`
**Shows:** comment editing, comment deletion → tombstone

1. Create public issue. Wait for mirror.
2. **Announce:** "A public user is posting a comment with their config file."
3. Post public comment ("Here's my config: ...includes a fake password..."). Wait for sync.
4. **Announce:** "The user realized they pasted a password. They're editing the comment to redact it — Lyrebird will update the mirrored copy."
5. Edit public comment (redact the password). Wait for sync.
6. **Announce:** "The user decided to delete the comment entirely. Lyrebird will replace the mirrored copy with a tombstone to preserve context."
7. Delete public comment. Wait for sync → tombstone.

### Issue 3: Slash Commands
**Public title:** `How to configure parallel processing?`
**Shows:** `/anon`

1. Create public issue (user question). Wait for mirror.
2. **Announce:** "A team member will reply using `/anon`. This posts an anonymous comment on the public issue."
3. Post `/anon` with a helpful answer including a code example. Wait for sync.
4. **Announce:** "Another team member adds an anonymous follow-up using `/anon`."
5. Post `/anon` with a version compatibility note. Wait for sync.

### Issue 4: Close/Reopen Lifecycle
**Public title:** `Typo in the getting started guide`
**Shows:** public close → private closed, reopen → both reopened

1. Create public issue. Wait for mirror.
2. **Announce:** "The reporter is closing the public issue (they found the typo was already fixed). Lyrebird will close this private issue too."
3. Close public issue. Wait for sync → private closed.
4. **Announce:** "The reporter reopened — turns out the typo is on a different page. Lyrebird will reopen this private issue too."
5. Reopen public issue. Wait for sync → both reopened.

### Issue 5: Resolution Enforcement
**Public title:** `Feature request: dark mode`
**Shows:** nudge on improper close, proper label + close

1. Create public issue (feature request). Wait for mirror.
2. **Announce:** "A team member is closing this private issue *without* a resolution label. Lyrebird will detect this and add a `needs-public-resolution` label with a comment explaining how to close properly."
3. Close private issue natively. Wait for sync → nudge + `needs-public-resolution`.
4. **Announce:** "Reopening to fix the closure. Will add a resolution label and close again properly."
5. Reopen private issue. Wait for sync.
6. Post `/anon` with a custom note, add `external:not-planned` label, close. Wait for sync → both closed.

## Summary Output

At the end, print a grid of links to all 5 public and 5 private issues:

```
  1. Bug report lifecycle (mirroring, edits, labels, type sync)
     Public:  <url>
     Private: <url>

  2. Edits and deletions (comment edit, comment deletion → tombstone)
     Public:  <url>
     Private: <url>

  3. Slash commands (/anon)
     Public:  <url>
     Private: <url>

  4. Close/reopen lifecycle (bidirectional state sync)
     Public:  <url>
     Private: <url>

  5. Resolution enforcement (nudge → proper label + close)
     Public:  <url>
     Private: <url>
```
