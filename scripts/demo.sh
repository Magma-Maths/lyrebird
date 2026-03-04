#!/usr/bin/env bash
#
# Interactive demo of Lyrebird features.
# Walks through each feature step-by-step, pausing to let you verify.
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

print_links() {
    echo
    if [[ -n "${ISSUE_URL:-}" ]]; then
        echo "  Public:  $ISSUE_URL"
    else
        echo "  Public:  https://github.com/$PUBLIC_REPO/issues"
    fi
    
    if [[ -n "${PRIVATE_ISSUE_URL:-}" ]]; then
        echo "  Private: $PRIVATE_ISSUE_URL"
    else
        echo "  Private: https://github.com/$PRIVATE_REPO/issues"
    fi
    echo
}

step() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  $1"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

wait_for_run() {
    local repo="$1"
    echo "  Waiting for workflow to complete on $repo..."
    sleep 5
    # Wait for the most recent run to finish
    for i in $(seq 1 24); do
        STATUS=$(gh run list --repo "$repo" --limit 1 --json status --jq '.[0].status' 2>/dev/null || echo "unknown")
        if [[ "$STATUS" == "completed" ]]; then
            CONCLUSION=$(gh run list --repo "$repo" --limit 1 --json conclusion --jq '.[0].conclusion' 2>/dev/null || echo "unknown")
            if [[ "$CONCLUSION" == "success" ]]; then
                echo "  ✓ Workflow completed successfully"
            else
                echo "  ✗ Workflow completed with: $CONCLUSION"
                echo "  Check: gh run list --repo $repo --limit 1"
            fi
            return
        fi
        sleep 5
    done
    echo "  ⚠ Timed out waiting for workflow (2 min). Check manually."
}

echo
echo "Lyrebird Demo Generator"
echo "======================="
echo "  Public repo:  $PUBLIC_REPO"
echo "  Private repo: $PRIVATE_REPO"
echo "  Running non-interactive script to populate repos..."
echo
sleep 3

# ── 1. Create a public issue ────────────────────────────────────────────────

step "1. Create a public issue → should be mirrored to private"

ISSUE_URL=$(gh issue create \
    --repo "$PUBLIC_REPO" \
    --title "Demo: something is broken" \
    --body "Steps to reproduce:
1. Do X
2. See error Y

Expected: Z should happen instead." \
    2>&1)

ISSUE_NUM=$(echo "$ISSUE_URL" | grep -oP '\d+$')
echo "  Created public issue #$ISSUE_NUM"
echo "  $ISSUE_URL"

wait_for_run "$PUBLIC_REPO"
wait_for_run "$PRIVATE_REPO"

echo "  Looking for private mirror..."
PRIVATE_ISSUE_NUM=$(gh issue list --repo "$PRIVATE_REPO" --search "[public #$ISSUE_NUM]" --json number --jq '.[0].number' 2>/dev/null)
if [[ -n "$PRIVATE_ISSUE_NUM" ]]; then
    PRIVATE_ISSUE_URL="https://github.com/$PRIVATE_REPO/issues/$PRIVATE_ISSUE_NUM"
    echo "  Found private issue #$PRIVATE_ISSUE_NUM"
fi

echo
echo "  → Check the private repo: a mirrored issue should appear titled"
echo "    '[public #$ISSUE_NUM] Demo: something is broken'"
echo "  → Check the public issue: a welcome comment should appear"
print_links

# ── 2. Comment on the public issue ──────────────────────────────────────────

step "2. Comment on public issue → should be mirrored to private"

COMMENT_URL=$(gh issue comment "$ISSUE_NUM" \
    --repo "$PUBLIC_REPO" \
    --body "Here's some additional info: I'm running version 3.2.1 on macOS." \
    2>&1)

echo "  Posted comment on public #$ISSUE_NUM"

wait_for_run "$PUBLIC_REPO"
wait_for_run "$PRIVATE_REPO"

echo
echo "  → Check the private mirror: the comment should appear there too"
print_links

# ── 3. Edit the public issue ────────────────────────────────────────────────

step "3. Edit the public issue title and body → private should update"

gh issue edit "$ISSUE_NUM" \
    --repo "$PUBLIC_REPO" \
    --title "Demo: something is broken (updated)" \
    --body "Steps to reproduce:
1. Do X (updated steps)
2. See error Y

Expected: Z should happen instead.

Environment: macOS 14, version 3.2.1"

echo "  Edited public #$ISSUE_NUM"

wait_for_run "$PUBLIC_REPO"
wait_for_run "$PRIVATE_REPO"

echo
echo "  → Check the private mirror: title and body should be updated"
print_links

# ── 4. Add a label on the public issue ──────────────────────────────────────

step "4. Add a label on public → should be mirrored to private"

# Create the label first if it doesn't exist
gh label create "bug" --repo "$PUBLIC_REPO" --color "d73a4a" --force 2>/dev/null || true
gh issue edit "$ISSUE_NUM" --repo "$PUBLIC_REPO" --add-label "bug"

echo "  Added 'bug' label to public #$ISSUE_NUM"

wait_for_run "$PUBLIC_REPO"
wait_for_run "$PRIVATE_REPO"

echo
echo "  → Check the private mirror: 'bug' label should appear"
print_links

# ── 5. Delete a comment on the public issue ─────────────────────────────────

step "5. Delete public comment → private becomes a tombstone"

COMMENT_ID=$(echo "$COMMENT_URL" | grep -oP '\d+$')
gh api -X DELETE "repos/$PUBLIC_REPO/issues/comments/$COMMENT_ID" --silent 2>/dev/null || echo "Could not delete comment"

echo "  Deleted comment on public #$ISSUE_NUM"

wait_for_run "$PUBLIC_REPO"
wait_for_run "$PRIVATE_REPO"

echo
echo "  → Check the private mirror: the mirrored comment should now be a '(deleted on public at ...)' tombstone"
print_links

# ── 6. /public command from private ─────────────────────────────────────────

step "6. Post /public from private → message appears on public issue"

if [[ -z "${PRIVATE_ISSUE_NUM:-}" ]]; then
    echo "  ⚠ Could not find private mirror. Skipping /public demo."
    print_links
else
    gh issue comment "$PRIVATE_ISSUE_NUM" \
        --repo "$PRIVATE_REPO" \
        --body "/public Thanks for reporting this! We've identified the issue and are working on a fix."

    echo "  Posted /public command on private #$PRIVATE_ISSUE_NUM"

    wait_for_run "$PRIVATE_REPO"

    echo
    echo "  → Check the public issue: the message should appear (attributed to you)"
    echo "  → Check the private issue: an acknowledgement with a link should appear"
    print_links

    # ── 7. /public --anon ────────────────────────────────────────────────────

    step "7. Post /public --anon from private → anonymous message on public"

    gh issue comment "$PRIVATE_ISSUE_NUM" \
        --repo "$PRIVATE_REPO" \
        --body "/public --anon We're still investigating. Will update soon."

    echo "  Posted /public --anon on private #$PRIVATE_ISSUE_NUM"

    wait_for_run "$PRIVATE_REPO"

    echo
    echo "  → Check the public issue: the message should appear WITHOUT your username"
    print_links

    # ── 8. Close the public issue ────────────────────────────────────────────

    step "8. Close public issue → private gets 'public:closed' label"

    gh issue close "$ISSUE_NUM" --repo "$PUBLIC_REPO"

    echo "  Closed public #$ISSUE_NUM"

    wait_for_run "$PUBLIC_REPO"
    wait_for_run "$PRIVATE_REPO"

    echo
    echo "  → Check private mirror: should have 'public:closed' label + audit comment"
    echo "  → Note: the private issue stays OPEN (you decide when to close it)"
    print_links

    # ── 9. Reopen public issue ───────────────────────────────────────────────

    step "9. Reopen public issue"

    gh issue reopen "$ISSUE_NUM" --repo "$PUBLIC_REPO"
    echo "  Reopened public #$ISSUE_NUM"

    wait_for_run "$PUBLIC_REPO"
    wait_for_run "$PRIVATE_REPO"

    echo "  → 'public:closed' label should be removed from private"
    print_links

    # ── 10. Close private without resolution label ───────────────────────────

    step "10. Close private without resolution label → nudges maintainer"

    gh issue close "$PRIVATE_ISSUE_NUM" --repo "$PRIVATE_REPO"
    echo "  Closed private #$PRIVATE_ISSUE_NUM (without adding a resolution label)"

    wait_for_run "$PRIVATE_REPO"

    echo "  → Check private mirror: it should now have a 'needs-public-resolution' label"
    echo "    and a comment explaining how to properly close the public issue."
    print_links

    # ── 11. /public-close ────────────────────────────────────────────────────

    step "11. Reopen private, then /public-close from private"
    
    gh issue reopen "$PRIVATE_ISSUE_NUM" --repo "$PRIVATE_REPO"
    echo "  Reopened private #$PRIVATE_ISSUE_NUM"

    wait_for_run "$PRIVATE_REPO"

    gh issue comment "$PRIVATE_ISSUE_NUM" \
        --repo "$PRIVATE_REPO" \
        --body "/public-close completed Thanks for the report! The fix will be in the next update."

    echo "  Posted /public-close on private #$PRIVATE_ISSUE_NUM"

    wait_for_run "$PRIVATE_REPO"

    echo
    echo "  → Public issue should be CLOSED with an attributed note"
    echo "  → Private issue should be CLOSED with 'external:completed' label"
    print_links
fi

# ── Done ────────────────────────────────────────────────────────────────────

step "Demo complete!"

echo
echo "  Summary of what was demonstrated:"
echo "    1. Public issue → mirrored to private"
echo "    2. Public comment → mirrored to private"
echo "    3. Public edit → updated in private"
echo "    4. Public label → mirrored to private"
echo "    5. Public comment delete → tombstone on private"
echo "    6. /public → attributed reply on public"
echo "    7. /public --anon → anonymous reply on public"
echo "    8. Public close → tracking label on private"
echo "    9. Public reopen → tracking label removed"
echo "   10. Close private without resolution → nudge comment & label"
echo "   11. /public-close → both issues closed with resolution"
echo
echo "  Clean up:"
echo "    gh issue list --repo $PUBLIC_REPO"
echo "    gh issue list --repo $PRIVATE_REPO"
echo
