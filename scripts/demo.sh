#!/usr/bin/env bash
#
# Generates demo issues to showcase Lyrebird features.
# Creates five separate issues, each demonstrating a different workflow.
# Posts "announcer" comments on private issues before each action so the
# timeline is self-explanatory for collaborators browsing the repos later.
#
# Usage:
#   ./scripts/demo.sh [public-repo] [private-repo]
#   ./scripts/demo.sh  # uses defaults from scripts/.env

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ $# -ge 2 ]]; then
    PUBLIC_REPO="$1"
    PRIVATE_REPO="$2"
elif [[ -f "$SCRIPT_DIR/.env" ]]; then
    # shellcheck source=/dev/null
    source "$SCRIPT_DIR/.env"
    PUBLIC_REPO="$ORG/$PUBLIC_REPO_NAME"
    PRIVATE_REPO="$ORG/$PRIVATE_REPO_NAME"
else
    echo "Usage: $0 <public-repo> <private-repo>"
    echo "   or: create scripts/.env (see scripts/.env.example)"
    exit 1
fi

step() {
    echo
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  $1"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

wait_for_run() {
    local repo="$1"
    local workflow="${2:-}"
    local wait_job="${3:-}"
    local wf_args=()
    if [[ -n "$workflow" ]]; then
        wf_args=(--workflow "$workflow")
    fi
    echo "  Waiting for $workflow on $repo..."
    sleep 5
    for _ in $(seq 1 24); do
        # Find the most recent non-skipped run
        local run_id status conclusion
        read -r run_id status conclusion < <(
            gh run list --repo "$repo" "${wf_args[@]}" --limit 5 \
                --json databaseId,status,conclusion \
                --jq '[.[] | select(.status != "completed" or .conclusion != "skipped")][0]
                      | [.databaseId, .status, .conclusion] | @tsv' 2>/dev/null
        ) || true

        if [[ -z "$run_id" || "$run_id" == "null" ]]; then
            sleep 5
            continue
        fi

        # If waiting for a specific job and run is still going, check job status
        if [[ -n "$wait_job" && "$status" != "completed" ]]; then
            local job_conclusion
            job_conclusion=$(gh api "repos/$repo/actions/runs/$run_id/jobs" \
                --jq ".jobs[] | select(.name == \"$wait_job\") | .conclusion // empty" 2>/dev/null || echo "")
            if [[ "$job_conclusion" == "success" ]]; then
                echo "  ✓ Done"
                return
            elif [[ -n "$job_conclusion" ]]; then
                echo "  ✗ Job '$wait_job' failed: $job_conclusion"
                return
            fi
            sleep 5
            continue
        fi

        if [[ "$status" == "completed" ]]; then
            if [[ "$conclusion" == "success" ]]; then
                echo "  ✓ Done"
            else
                echo "  ✗ Workflow failed: $conclusion"
                echo "    gh run list --repo $repo ${wf_args[*]} --limit 1"
            fi
            return
        fi
        sleep 5
    done
    echo "  ⚠ Timed out (2 min). Check manually."
}

find_private_issue() {
    local pub_num="$1"
    for _ in $(seq 1 3); do
        local num
        num=$(gh issue list --repo "$PRIVATE_REPO" --search "[public #$pub_num]" --json number --jq '.[0].number' 2>/dev/null || echo "")
        if [[ -n "$num" ]]; then
            echo "$num"
            return
        fi
        sleep 3
    done
    echo ""
}

announce() {
    local priv_num="$1"
    local message="$2"
    echo "  📢 $message"
    gh issue comment "$priv_num" \
        --repo "$PRIVATE_REPO" \
        --body "**🔔 Demo narrator:** $message" \
        >/dev/null 2>&1
}

CHECKS_PASSED=0
CHECKS_FAILED=0

check() {
    local desc="$1"
    shift
    if "$@" 2>/dev/null; then
        echo "  ✓ CHECK: $desc"
        ((CHECKS_PASSED++)) || true
    else
        echo "  ✗ CHECK: $desc"
        ((CHECKS_FAILED++)) || true
    fi
}

check_title_contains() {
    gh issue view "$2" --repo "$1" --json title --jq '.title' | grep -q "$3"
}

check_state() {
    [[ $(gh issue view "$2" --repo "$1" --json state --jq '.state') == "$3" ]]
}

check_has_label() {
    gh issue view "$2" --repo "$1" --json labels --jq '.labels[].name' | grep -q "^${3}$"
}

check_comments_contain() {
    gh api "repos/$1/issues/$2/comments" --jq '.[].body' | grep -q "$3"
}

echo
echo "Lyrebird Demo Generator"
echo "======================="
echo "  Public repo:  $PUBLIC_REPO"
echo "  Private repo: $PRIVATE_REPO"
echo
echo "  This will create 5 demo issues to showcase Lyrebird's features."
echo
sleep 3

# Ensure "bug" label exists
gh label create "bug" --repo "$PUBLIC_REPO" --color "d73a4a" --force 2>/dev/null || true

# ═══════════════════════════════════════════════════════════════════════════
# Issue 1: Bug report lifecycle
#   Shows: mirroring, comments, edits, labels, type sync
# ═══════════════════════════════════════════════════════════════════════════

step "Issue 1: Bug report lifecycle"

ISSUE1_URL=$(gh issue create \
    --repo "$PUBLIC_REPO" \
    --title "Bug: crash when loading large files" \
    --body "When I try to load a file larger than 2GB, the application crashes with a segfault.

**Steps to reproduce:**
1. Open the application
2. Go to File > Open
3. Select a file larger than 2GB
4. Application crashes

**Expected:** The file should load, or show an error message.

**Environment:** Linux, version 3.1.0" \
    2>&1)
ISSUE1_NUM=$(echo "$ISSUE1_URL" | grep -oP '\d+$')
echo "  Created public #$ISSUE1_NUM: Bug report"
echo "  $ISSUE1_URL"

wait_for_run "$PUBLIC_REPO" "public-dispatch.yml"
wait_for_run "$PRIVATE_REPO" "handle-public-event.yml"

PRIVATE1_NUM=$(find_private_issue "$ISSUE1_NUM")
if [[ -z "$PRIVATE1_NUM" ]]; then
    echo "  ⚠ Could not find private mirror. Skipping rest of Issue 1."
else
    echo "  Mirrored to private #$PRIVATE1_NUM"
    check "Private issue title has [public #$ISSUE1_NUM] prefix" \
        check_title_contains "$PRIVATE_REPO" "$PRIVATE1_NUM" "\[public #$ISSUE1_NUM\]"

    # Comment
    announce "$PRIVATE1_NUM" "A public user is posting additional debug info (a stack trace)."
    gh issue comment "$ISSUE1_NUM" \
        --repo "$PUBLIC_REPO" \
        --body "I just tested with version 3.1.1 and the same crash happens. Here's the stack trace:

\`\`\`
Segfault at 0x7fff5fbff8e0
  in load_file() at src/io/reader.c:142
  in main() at src/main.c:58
\`\`\`

This might be related to the mmap allocation."

    wait_for_run "$PUBLIC_REPO" "public-dispatch.yml"
    wait_for_run "$PRIVATE_REPO" "handle-public-event.yml"
    echo "  ✓ Comment mirrored"
    check "Comment mirrored to private" \
        check_comments_contain "$PRIVATE_REPO" "$PRIVATE1_NUM" "mmap"

    # Edit
    announce "$PRIVATE1_NUM" "The reporter is editing the issue to add environment details (OS, version, RAM). The private body will update in place."
    gh issue edit "$ISSUE1_NUM" \
        --repo "$PUBLIC_REPO" \
        --title "Bug: crash when loading files larger than 2GB" \
        --body "When I try to load a file larger than 2GB, the application crashes with a segfault.

**Steps to reproduce:**
1. Open the application
2. Go to File > Open
3. Select a file larger than 2GB (tested with 2.1GB and 4GB files)
4. Application crashes immediately

**Expected:** The file should load, or show a clear error message.

**Environment:**
- OS: Ubuntu 22.04
- Version: 3.1.0 and 3.1.1 (both crash)
- RAM: 16GB

*(Edited: added version and OS details)*"

    wait_for_run "$PUBLIC_REPO" "public-dispatch.yml"
    wait_for_run "$PRIVATE_REPO" "handle-public-event.yml"
    echo "  ✓ Edit mirrored"
    check "Title updated on private" \
        check_title_contains "$PRIVATE_REPO" "$PRIVATE1_NUM" "files larger than 2GB"

    # Label
    announce "$PRIVATE1_NUM" "Adding a 'bug' label on the public side — Lyrebird will mirror it here."
    gh issue edit "$ISSUE1_NUM" --repo "$PUBLIC_REPO" --add-label "bug"

    wait_for_run "$PUBLIC_REPO" "public-dispatch.yml"
    wait_for_run "$PRIVATE_REPO" "handle-public-event.yml"
    echo "  ✓ Label mirrored"
    check "Bug label on private issue" \
        check_has_label "$PRIVATE_REPO" "$PRIVATE1_NUM" "bug"

    # Type
    announce "$PRIVATE1_NUM" "Setting the issue type to 'Bug' on the public side — Lyrebird will mirror it here."
    gh api --method PATCH "repos/$PUBLIC_REPO/issues/$ISSUE1_NUM" -f type=Bug >/dev/null 2>&1 || echo "  ⚠ Could not set issue type (may not be enabled on this repo)"

    wait_for_run "$PUBLIC_REPO" "public-dispatch.yml"
    wait_for_run "$PRIVATE_REPO" "handle-public-event.yml"
    echo "  ✓ Type mirrored"
fi

echo
echo "  Issue 1 complete: $ISSUE1_URL"

# ═══════════════════════════════════════════════════════════════════════════
# Issue 2: Edits and deletions
#   Shows: comment editing, comment deletion → tombstone
# ═══════════════════════════════════════════════════════════════════════════

step "Issue 2: Edits and deletions"

ISSUE2_URL=$(gh issue create \
    --repo "$PUBLIC_REPO" \
    --title "Error message is misleading when config file is missing" \
    --body "When the config file is missing, the error says 'permission denied' instead of 'file not found'. This is confusing.

\`\`\`
$ myapp --config /nonexistent/path
Error: permission denied
\`\`\`

Expected: \`Error: config file not found: /nonexistent/path\`" \
    2>&1)
ISSUE2_NUM=$(echo "$ISSUE2_URL" | grep -oP '\d+$')
echo "  Created public #$ISSUE2_NUM: Misleading error message"
echo "  $ISSUE2_URL"

wait_for_run "$PUBLIC_REPO" "public-dispatch.yml"
wait_for_run "$PRIVATE_REPO" "handle-public-event.yml"

PRIVATE2_NUM=$(find_private_issue "$ISSUE2_NUM")
if [[ -z "$PRIVATE2_NUM" ]]; then
    echo "  ⚠ Could not find private mirror. Skipping rest of Issue 2."
else
    echo "  Mirrored to private #$PRIVATE2_NUM"

    # Post comment with "sensitive" info
    announce "$PRIVATE2_NUM" "A public user is posting a comment with their config file."
    COMMENT2_URL=$(gh issue comment "$ISSUE2_NUM" \
        --repo "$PUBLIC_REPO" \
        --body "Here's my config file, maybe it helps:

\`\`\`yaml
database:
  host: db.example.com
  user: admin
  password: hunter2
  port: 5432
\`\`\`

Let me know if you need anything else." \
        2>&1)

    wait_for_run "$PUBLIC_REPO" "public-dispatch.yml"
    wait_for_run "$PRIVATE_REPO" "handle-public-event.yml"
    echo "  ✓ Comment mirrored"

    # Edit comment to redact password
    COMMENT2_ID=$(echo "$COMMENT2_URL" | grep -oP '\d+$')
    announce "$PRIVATE2_NUM" "The user realized they pasted a password. They're editing the comment to redact it — Lyrebird will update the mirrored copy."
    gh api --method PATCH "repos/$PUBLIC_REPO/issues/comments/$COMMENT2_ID" \
        -f body="Here's my config file, maybe it helps:

\`\`\`yaml
database:
  host: db.example.com
  user: admin
  password: ********
  port: 5432
\`\`\`

Let me know if you need anything else.

*(Edited: redacted password)*" \
        >/dev/null 2>&1

    wait_for_run "$PUBLIC_REPO" "public-dispatch.yml"
    wait_for_run "$PRIVATE_REPO" "handle-public-event.yml"
    echo "  ✓ Comment edit mirrored"
    check "Redacted password in mirrored comment" \
        check_comments_contain "$PRIVATE_REPO" "$PRIVATE2_NUM" "redacted password"

    # Delete comment entirely
    announce "$PRIVATE2_NUM" "The user decided to delete the comment entirely. Lyrebird will replace the mirrored copy with a tombstone to preserve context."
    gh api -X DELETE "repos/$PUBLIC_REPO/issues/comments/$COMMENT2_ID" --silent 2>/dev/null || true

    wait_for_run "$PUBLIC_REPO" "public-dispatch.yml"
    wait_for_run "$PRIVATE_REPO" "handle-public-event.yml"
    echo "  ✓ Comment replaced with tombstone"
    check "Tombstone comment on private" \
        check_comments_contain "$PRIVATE_REPO" "$PRIVATE2_NUM" "deleted"
fi

echo
echo "  Issue 2 complete: $ISSUE2_URL"

# ═══════════════════════════════════════════════════════════════════════════
# Issue 3: Slash commands
#   Shows: /anon
# ═══════════════════════════════════════════════════════════════════════════

step "Issue 3: Slash commands"

ISSUE3_URL=$(gh issue create \
    --repo "$PUBLIC_REPO" \
    --title "How to configure parallel processing?" \
    --body "I'm trying to use the parallel processing feature but can't find where to configure the number of workers.

I've looked in the docs but only found references to the old API. Is this still supported?

Thanks!" \
    2>&1)
ISSUE3_NUM=$(echo "$ISSUE3_URL" | grep -oP '\d+$')
echo "  Created public #$ISSUE3_NUM: User question"
echo "  $ISSUE3_URL"

wait_for_run "$PUBLIC_REPO" "public-dispatch.yml"
wait_for_run "$PRIVATE_REPO" "handle-public-event.yml"

PRIVATE3_NUM=$(find_private_issue "$ISSUE3_NUM")
if [[ -z "$PRIVATE3_NUM" ]]; then
    echo "  ⚠ Could not find private mirror. Skipping rest of Issue 3."
else
    echo "  Mirrored to private #$PRIVATE3_NUM"

    # /anon — anonymous reply
    announce "$PRIVATE3_NUM" "A team member will reply using \`/anon\`. This posts an anonymous comment on the public issue."
    gh issue comment "$PRIVATE3_NUM" \
        --repo "$PRIVATE_REPO" \
        --body '/anon Yes, parallel processing is still supported! You can configure it in `config.yml`:

```yaml
processing:
  workers: 4
  chunk_size: 1024
```

The docs are being updated — sorry for the confusion.'

    wait_for_run "$PRIVATE_REPO" "handle-private-comment.yml"
    echo "  ✓ Anonymous reply posted on public issue"
    check "Anonymous reply visible on public issue" \
        check_comments_contain "$PUBLIC_REPO" "$ISSUE3_NUM" "parallel processing"

    # /anon — anonymous follow-up
    announce "$PRIVATE3_NUM" "Another team member adds an anonymous follow-up using \`/anon\`."
    gh issue comment "$PRIVATE3_NUM" \
        --repo "$PRIVATE_REPO" \
        --body "/anon Note: if you're on version < 3.0, you'll need to upgrade first. The parallel API was rewritten in 3.0."

    wait_for_run "$PRIVATE_REPO" "handle-private-comment.yml"
    echo "  ✓ Anonymous follow-up posted on public issue"
fi

echo
echo "  Issue 3 complete: $ISSUE3_URL"

# ═══════════════════════════════════════════════════════════════════════════
# Issue 4: Close/reopen lifecycle
#   Shows: public close → private closed + label, reopen → both reopened
# ═══════════════════════════════════════════════════════════════════════════

step "Issue 4: Close/reopen lifecycle"

ISSUE4_URL=$(gh issue create \
    --repo "$PUBLIC_REPO" \
    --title "Typo in the getting started guide" \
    --body "On the Getting Started page, step 3 says 'run \`make biuld\`' — should be \`make build\`." \
    2>&1)
ISSUE4_NUM=$(echo "$ISSUE4_URL" | grep -oP '\d+$')
echo "  Created public #$ISSUE4_NUM: Typo report"
echo "  $ISSUE4_URL"

wait_for_run "$PUBLIC_REPO" "public-dispatch.yml"
wait_for_run "$PRIVATE_REPO" "handle-public-event.yml"

PRIVATE4_NUM=$(find_private_issue "$ISSUE4_NUM")
if [[ -z "$PRIVATE4_NUM" ]]; then
    echo "  ⚠ Could not find private mirror. Skipping rest of Issue 4."
else
    echo "  Mirrored to private #$PRIVATE4_NUM"

    # Close public
    announce "$PRIVATE4_NUM" "The reporter is closing the public issue (they found the typo was already fixed). Lyrebird will close this private issue too."
    gh issue close "$ISSUE4_NUM" --repo "$PUBLIC_REPO"

    wait_for_run "$PUBLIC_REPO" "public-dispatch.yml"
    wait_for_run "$PRIVATE_REPO" "handle-public-event.yml"
    echo "  ✓ Private issue closed"
    check "Private issue is closed" \
        check_state "$PRIVATE_REPO" "$PRIVATE4_NUM" "CLOSED"

    # Reopen public
    announce "$PRIVATE4_NUM" "The reporter reopened — turns out the typo is on a different page. Lyrebird will reopen this private issue too."
    gh issue reopen "$ISSUE4_NUM" --repo "$PUBLIC_REPO"

    wait_for_run "$PUBLIC_REPO" "public-dispatch.yml"
    wait_for_run "$PRIVATE_REPO" "handle-public-event.yml"
    echo "  ✓ Both issues reopened"
    check "Private issue is open" \
        check_state "$PRIVATE_REPO" "$PRIVATE4_NUM" "OPEN"
    check "Public issue is open" \
        check_state "$PUBLIC_REPO" "$ISSUE4_NUM" "OPEN"
fi

echo
echo "  Issue 4 complete: $ISSUE4_URL"

# ═══════════════════════════════════════════════════════════════════════════
# Issue 5: Resolution enforcement
#   Shows: closing private without resolution (nudge), then proper close
# ═══════════════════════════════════════════════════════════════════════════

step "Issue 5: Resolution enforcement"

ISSUE5_URL=$(gh issue create \
    --repo "$PUBLIC_REPO" \
    --title "Feature request: dark mode" \
    --body "It would be great to have a dark mode option. My eyes hurt when working late at night.

Other tools in this space already support it (e.g., Tool X, Tool Y)." \
    2>&1)
ISSUE5_NUM=$(echo "$ISSUE5_URL" | grep -oP '\d+$')
echo "  Created public #$ISSUE5_NUM: Feature request"
echo "  $ISSUE5_URL"

wait_for_run "$PUBLIC_REPO" "public-dispatch.yml"
wait_for_run "$PRIVATE_REPO" "handle-public-event.yml"

PRIVATE5_NUM=$(find_private_issue "$ISSUE5_NUM")
if [[ -z "$PRIVATE5_NUM" ]]; then
    echo "  ⚠ Could not find private mirror. Skipping rest of Issue 5."
else
    echo "  Mirrored to private #$PRIVATE5_NUM"

    # Close private without resolution label — triggers nudge
    announce "$PRIVATE5_NUM" "A team member is closing this private issue *without* a resolution label. Lyrebird will close the public issue immediately and, after a 5-minute grace period, add a \`resolution:none\` label with a nudge comment."
    gh issue close "$PRIVATE5_NUM" --repo "$PRIVATE_REPO"

    wait_for_run "$PRIVATE_REPO" "handle-private-issue.yml" "handle"
    echo "  ✓ Public issue closed; delayed check will add 'resolution:none' if no label is added"
    check "Public issue is closed" \
        check_state "$PUBLIC_REPO" "$ISSUE5_NUM" "CLOSED"

    # Reopen and close properly with resolution label
    announce "$PRIVATE5_NUM" "Reopening to fix the closure. Will add a resolution label and close again properly."
    gh issue reopen "$PRIVATE5_NUM" --repo "$PRIVATE_REPO"

    wait_for_run "$PRIVATE_REPO" "handle-private-issue.yml" "handle"

    # Post a note via /anon, then add resolution label and close
    gh issue comment "$PRIVATE5_NUM" \
        --repo "$PRIVATE_REPO" \
        --body "/anon Thanks for the suggestion! Dark mode isn't on our roadmap right now, but we'll keep this in mind for future releases."

    wait_for_run "$PRIVATE_REPO" "handle-private-comment.yml"

    gh issue edit "$PRIVATE5_NUM" --repo "$PRIVATE_REPO" --add-label "resolution:not-planned"
    gh issue close "$PRIVATE5_NUM" --repo "$PRIVATE_REPO"

    wait_for_run "$PRIVATE_REPO" "handle-private-issue.yml" "handle"
    echo "  ✓ Both issues closed with 'not-planned' resolution"
    check "Public issue is closed" \
        check_state "$PUBLIC_REPO" "$ISSUE5_NUM" "CLOSED"
    check "Resolution note posted on public" \
        check_comments_contain "$PUBLIC_REPO" "$ISSUE5_NUM" "not planned"
fi

echo
echo "  Issue 5 complete: $ISSUE5_URL"

# ═══════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════

step "Demo complete!"

echo
echo "  Five demo issues have been created:"
echo
echo "  1. Bug report lifecycle (mirroring, edits, labels, type sync)"
echo "     Public:  $ISSUE1_URL"
if [[ -n "${PRIVATE1_NUM:-}" ]]; then
echo "     Private: https://github.com/$PRIVATE_REPO/issues/$PRIVATE1_NUM"
fi
echo
echo "  2. Edits and deletions (comment edit, comment deletion → tombstone)"
echo "     Public:  $ISSUE2_URL"
if [[ -n "${PRIVATE2_NUM:-}" ]]; then
echo "     Private: https://github.com/$PRIVATE_REPO/issues/$PRIVATE2_NUM"
fi
echo
echo "  3. Slash commands (/anon)"
echo "     Public:  $ISSUE3_URL"
if [[ -n "${PRIVATE3_NUM:-}" ]]; then
echo "     Private: https://github.com/$PRIVATE_REPO/issues/$PRIVATE3_NUM"
fi
echo
echo "  4. Close/reopen lifecycle (bidirectional state sync)"
echo "     Public:  $ISSUE4_URL"
if [[ -n "${PRIVATE4_NUM:-}" ]]; then
echo "     Private: https://github.com/$PRIVATE_REPO/issues/$PRIVATE4_NUM"
fi
echo
echo "  5. Resolution enforcement (nudge → proper label + close)"
echo "     Public:  $ISSUE5_URL"
if [[ -n "${PRIVATE5_NUM:-}" ]]; then
echo "     Private: https://github.com/$PRIVATE_REPO/issues/$PRIVATE5_NUM"
fi
echo
echo "  Verification: $CHECKS_PASSED passed, $CHECKS_FAILED failed"
if [[ $CHECKS_FAILED -gt 0 ]]; then
    echo "  ⚠ Some checks failed — review the output above."
fi
echo
echo "  Share these links with your collaborators to explore!"
echo
echo "  Clean up (close all generated issues):"
echo "    gh issue close $ISSUE1_NUM $ISSUE2_NUM $ISSUE3_NUM $ISSUE4_NUM $ISSUE5_NUM --repo $PUBLIC_REPO"
echo "    gh issue close ${PRIVATE1_NUM:-} ${PRIVATE2_NUM:-} ${PRIVATE3_NUM:-} ${PRIVATE4_NUM:-} ${PRIVATE5_NUM:-} --repo $PRIVATE_REPO"
echo
