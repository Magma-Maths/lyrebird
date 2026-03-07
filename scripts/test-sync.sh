#!/usr/bin/env bash
#
# End-to-end test for `python -m lyrebird sync`.
#
# Self-sufficient: creates its own mirrored issues and comments if needed,
# then disables webhooks, creates deliberate drift, runs sync, and verifies.
#
# Usage:
#   ./scripts/test-sync.sh                  # uses scripts/.env
#   ./scripts/test-sync.sh org/pub org/priv # explicit repos
#
# Prerequisites:
#   - gh CLI authenticated
#   - Webhook workflows active on both repos (for setup phase)
#   - sync.yml workflow deployed to the private repo

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ $# -ge 2 ]]; then
    PUBLIC_REPO="$1"
    PRIVATE_REPO="$2"
    BOT_LOGIN="${3:-lyrebird[bot]}"
elif [[ -f "$SCRIPT_DIR/.env" ]]; then
    # shellcheck source=/dev/null
    source "$SCRIPT_DIR/.env"
    PUBLIC_REPO="$ORG/$PUBLIC_REPO_NAME"
    PRIVATE_REPO="$ORG/$PRIVATE_REPO_NAME"
    BOT_LOGIN="${BOT_LOGIN:-lyrebird[bot]}"
else
    echo "Usage: $0 <public-repo> <private-repo>"
    echo "   or: create scripts/.env"
    exit 1
fi

CHECKS_PASSED=0
CHECKS_FAILED=0

step() {
    echo
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  $1"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

check() {
    local desc="$1"
    shift
    if "$@" 2>/dev/null; then
        echo "  ✓ $desc"
        ((CHECKS_PASSED++)) || true
    else
        echo "  ✗ $desc"
        ((CHECKS_FAILED++)) || true
    fi
}

find_private_issue() {
    local pub_num="$1"
    gh issue list --repo "$PRIVATE_REPO" --state all --json number,title \
        --jq "[.[] | select(.title | startswith(\"[public #$pub_num]\"))][0].number // empty" \
        2>/dev/null || echo ""
}

issue_url() {
    echo "https://github.com/$1/issues/$2"
}

# ── check_* helpers ──────────────────────────────────────────────────────────
# Each prints diagnostic output so the user can see what was checked,
# then returns 0/1 for the `check` wrapper.

check_not_empty() {
    local value="$1"
    [[ -n "$value" ]]
}

check_title_contains() {
    local repo="$1" num="$2" pattern="$3"
    local actual
    actual=$(gh issue view "$num" --repo "$repo" --json title --jq '.title' 2>/dev/null)
    echo "    actual title: $actual"
    echo "$actual" | grep -q "$pattern"
}

check_body_contains() {
    local repo="$1" num="$2" pattern="$3"
    local actual
    actual=$(gh issue view "$num" --repo "$repo" --json body --jq '.body' 2>/dev/null)
    # Show first matching line or first 120 chars if no match
    local snippet
    snippet=$(echo "$actual" | grep "$pattern" | head -1)
    if [[ -n "$snippet" ]]; then
        echo "    matched: ${snippet:0:120}"
    else
        echo "    body (first 120): ${actual:0:120}"
    fi
    echo "$actual" | grep -q "$pattern"
}

check_state() {
    local repo="$1" num="$2" expected="$3"
    local actual
    actual=$(gh issue view "$num" --repo "$repo" --json state --jq '.state' 2>/dev/null)
    echo "    state: $actual (expected $expected)"
    [[ "$actual" == "$expected" ]]
}

check_has_label() {
    local repo="$1" num="$2" label="$3"
    local actual
    actual=$(gh issue view "$num" --repo "$repo" --json labels --jq '[.labels[].name] | join(", ")' 2>/dev/null)
    echo "    labels: [$actual]"
    echo "$actual" | tr ',' '\n' | sed 's/^ //' | grep -q "^${label}$"
}

check_not_has_label() {
    ! check_has_label "$@"
}

check_comments_contain() {
    local repo="$1" num="$2" pattern="$3"
    local count
    count=$(gh api "repos/$repo/issues/$num/comments" --jq "[.[].body | select(test(\"$pattern\"))] | length" 2>/dev/null)
    echo "    comments matching '$pattern': ${count:-0}"
    [[ "${count:-0}" -gt 0 ]]
}

get_title() {
    gh issue view "$2" --repo "$1" --json title --jq '.title'
}

get_body() {
    gh issue view "$2" --repo "$1" --json body --jq '.body'
}

# ── wait_* helpers ───────────────────────────────────────────────────────────

wait_for_mirror() {
    local pub_num="$1" timeout="${2:-180}"
    local elapsed=0
    while (( elapsed < timeout )); do
        local priv_num
        priv_num=$(find_private_issue "$pub_num")
        if [[ -n "$priv_num" ]]; then
            echo "$priv_num"
            return 0
        fi
        sleep 5
        ((elapsed += 5)) || true
    done
    return 1
}

wait_for_comment_mirror() {
    local pub_comment_id="$1" priv_num="$2" timeout="${3:-180}"
    local elapsed=0
    while (( elapsed < timeout )); do
        if gh api "repos/$PRIVATE_REPO/issues/$priv_num/comments" --jq '.[].body' 2>/dev/null \
            | grep -q "public_comment_id: $pub_comment_id"; then
            return 0
        fi
        sleep 5
        ((elapsed += 5)) || true
    done
    return 1
}

# ── Cleanup trap ─────────────────────────────────────────────────────────────
# Ensures workflows are re-enabled even if the script fails mid-way.

cleanup() {
    echo
    echo "  Re-enabling workflows..."
    for wf in "${PUBLIC_WORKFLOWS[@]}"; do
        [[ -z "$wf" ]] && continue
        gh workflow enable "$wf" --repo "$PUBLIC_REPO" 2>/dev/null || true
    done
    for wf in "${PRIVATE_WORKFLOWS[@]}"; do
        [[ -z "$wf" ]] && continue
        gh workflow enable "$wf" --repo "$PRIVATE_REPO" 2>/dev/null || true
    done
    echo "  Workflows re-enabled."
}

# Initialize arrays so the trap doesn't fail on unset variables
PUBLIC_WORKFLOWS=()
PRIVATE_WORKFLOWS=()
trap cleanup EXIT

# ── Preamble ─────────────────────────────────────────────────────────────────

echo
echo "Lyrebird Sync — End-to-End Test"
echo "================================"
echo "  Public repo:  $PUBLIC_REPO"
echo "  Private repo: $PRIVATE_REPO"
echo

# ── Phase 0: Ensure prerequisites ─────────────────────────────────────────

step "Phase 0: Ensure prerequisites"

# Find open mirrored pairs
SETUP_PAIRS=()
for pub_num in $(gh issue list --repo "$PUBLIC_REPO" --state open --json number --jq '.[].number' 2>/dev/null); do
    priv_num=$(find_private_issue "$pub_num")
    if [[ -n "$priv_num" ]]; then
        SETUP_PAIRS+=("$pub_num:$priv_num")
    fi
    [[ ${#SETUP_PAIRS[@]} -ge 3 ]] && break
done

echo "  Found ${#SETUP_PAIRS[@]} open mirrored pair(s)"

# Create issues if needed (workflows must be active for mirroring)
while [[ ${#SETUP_PAIRS[@]} -lt 3 ]]; do
    idx=$(( ${#SETUP_PAIRS[@]} + 1 ))
    echo "  Creating setup issue ($idx of 3 needed)..."
    url=$(gh issue create --repo "$PUBLIC_REPO" \
        --title "Sync test setup issue $idx" \
        --body "Created by test-sync.sh for sync testing." 2>&1)
    num=$(echo "$url" | grep -oE '[0-9]+$')
    echo "  Created public #$num, waiting for mirror..."
    priv_num=$(wait_for_mirror "$num") || {
        echo "  ✗ Timed out waiting for mirror of public #$num"
        echo "    Are the webhook workflows (public-dispatch + handle-public-event) active?"
        exit 1
    }
    echo "  ✓ Mirrored to private #$priv_num"
    SETUP_PAIRS+=("$num:$priv_num")
done

# Assign pairs for each drift group
EXISTING_PUB="${SETUP_PAIRS[0]%%:*}"
EXISTING_PRIV="${SETUP_PAIRS[0]##*:}"
STATE_PUB="${SETUP_PAIRS[1]%%:*}"
STATE_PRIV="${SETUP_PAIRS[1]##*:}"
CASCADE_PUB="${SETUP_PAIRS[2]%%:*}"
CASCADE_PRIV="${SETUP_PAIRS[2]##*:}"

echo "  Assigned: drifts 2-5,8-10 → pub #$EXISTING_PUB / priv #$EXISTING_PRIV"
echo "            drift 6         → pub #$STATE_PUB / priv #$STATE_PRIV"
echo "            drift 7         → pub #$CASCADE_PUB / priv #$CASCADE_PRIV"

# Ensure 2+ mirrored comments on EXISTING pair (needed for drifts 9/10)
MIRRORED_CIDS=()
for cid in $(gh api "repos/$PUBLIC_REPO/issues/$EXISTING_PUB/comments" \
    --jq '[.[] | select((.body // "") | contains("<!-- mapping:") | not)] | .[].id' 2>/dev/null); do
    if gh api "repos/$PRIVATE_REPO/issues/$EXISTING_PRIV/comments" --jq '.[].body' 2>/dev/null \
        | grep -q "public_comment_id: $cid"; then
        MIRRORED_CIDS+=("$cid")
    fi
    [[ ${#MIRRORED_CIDS[@]} -ge 2 ]] && break
done

echo "  Found ${#MIRRORED_CIDS[@]} mirrored comment(s) on pub #$EXISTING_PUB"

while [[ ${#MIRRORED_CIDS[@]} -lt 2 ]]; do
    idx=$(( ${#MIRRORED_CIDS[@]} + 1 ))
    echo "  Creating comment ($idx of 2 needed) on public #$EXISTING_PUB..."
    comment_url=$(gh issue comment "$EXISTING_PUB" --repo "$PUBLIC_REPO" \
        --body "Setup comment $idx for sync testing.")
    cid=$(echo "$comment_url" | grep -oE '[0-9]+$')
    echo "  Comment $cid created, waiting for mirror..."
    wait_for_comment_mirror "$cid" "$EXISTING_PRIV" || {
        echo "  ✗ Timed out waiting for comment mirror"
        exit 1
    }
    echo "  ✓ Comment mirrored"
    MIRRORED_CIDS+=("$cid")
done

echo
echo "  ✓ Prerequisites met: 3 mirrored pairs, ${#MIRRORED_CIDS[@]} mirrored comments"

# ── Phase 1: Disable workflows ──────────────────────────────────────────────

step "Phase 1: Disable workflows"

readarray -t PUBLIC_WORKFLOWS < <(gh workflow list --repo "$PUBLIC_REPO" --json name --jq '.[].name' 2>/dev/null)
readarray -t PRIVATE_WORKFLOWS < <(gh workflow list --repo "$PRIVATE_REPO" --json name --jq '.[].name' 2>/dev/null)

for wf in "${PUBLIC_WORKFLOWS[@]}"; do
    [[ -z "$wf" ]] && continue
    gh workflow disable "$wf" --repo "$PUBLIC_REPO" 2>/dev/null || true
    echo "  Disabled: $PUBLIC_REPO / $wf"
done
for wf in "${PRIVATE_WORKFLOWS[@]}"; do
    [[ -z "$wf" ]] && continue
    gh workflow disable "$wf" --repo "$PRIVATE_REPO" 2>/dev/null || true
    echo "  Disabled: $PRIVATE_REPO / $wf"
done

# ── Phase 2: Create drift ───────────────────────────────────────────────────

step "Phase 2: Create drift"

# --- Drift 1: Orphan public issue (no private mirror) ---
echo
echo "  [Drift 1] Creating orphan public issue..."
ORPHAN_URL=$(gh issue create \
    --repo "$PUBLIC_REPO" \
    --title "Sync test: orphan issue" \
    --body "This issue was created while webhooks were disabled. No private mirror exists." \
    --label "bug" \
    2>&1)
ORPHAN_NUM=$(echo "$ORPHAN_URL" | grep -oE '[0-9]+$')
echo "  Created public #$ORPHAN_NUM (no mirror)"

# --- Drift 2: Stale title ---
ORIGINAL_TITLE=$(get_title "$PUBLIC_REPO" "$EXISTING_PUB")
echo
echo "  [Drift 2] Editing public #$EXISTING_PUB title (private #$EXISTING_PRIV will be stale)..."
gh issue edit "$EXISTING_PUB" --repo "$PUBLIC_REPO" \
    --title "SYNC-TEST: $ORIGINAL_TITLE"
echo "  Renamed to 'SYNC-TEST: $ORIGINAL_TITLE'"

# --- Drift 3: Stale body ---
echo
echo "  [Drift 3] Editing public #$EXISTING_PUB body..."
ORIGINAL_BODY=$(get_body "$PUBLIC_REPO" "$EXISTING_PUB")
gh issue edit "$EXISTING_PUB" --repo "$PUBLIC_REPO" \
    --body "$ORIGINAL_BODY

---
*[sync-test marker: this paragraph was added while webhooks were down]*"
echo "  Appended sync-test marker to body"

# --- Drift 4: Missing comment ---
echo
echo "  [Drift 4] Adding comment to public #$EXISTING_PUB (private won't see it)..."
gh issue comment "$EXISTING_PUB" --repo "$PUBLIC_REPO" \
    --body "This comment was posted while webhooks were disabled. Sync should mirror it."
echo "  Comment added"

# --- Drift 5: Missing label ---
echo
echo "  [Drift 5] Adding label to public #$EXISTING_PUB..."
gh label create "sync-test" --repo "$PUBLIC_REPO" --color "0e8a16" --force 2>/dev/null || true
gh issue edit "$EXISTING_PUB" --repo "$PUBLIC_REPO" --add-label "sync-test"
echo "  Added 'sync-test' label"

# --- Drift 8: Label removal & protection ---
echo
echo "  [Drift 8] Adding labels to private #$EXISTING_PRIV (extra should be removed, resolution should stay)..."
gh label create "stale-label" --repo "$PRIVATE_REPO" --color "cfd3d7" --force 2>/dev/null || true
gh label create "resolution:completed" --repo "$PRIVATE_REPO" --color "008672" --force 2>/dev/null || true
gh issue edit "$EXISTING_PRIV" --repo "$PRIVATE_REPO" --add-label "stale-label,resolution:completed"
echo "  Added 'stale-label' (unprotected) and 'resolution:completed' (protected) to private"

# --- Drift 9: Comment edit ---
echo
echo "  [Drift 9] Editing an existing public comment (that already has a mirror)..."
EDIT_MIRROR_ID=""
PUB_COMMENTS=$(gh api "repos/$PUBLIC_REPO/issues/$EXISTING_PUB/comments" --jq '.[].id' 2>/dev/null)
for cid in $PUB_COMMENTS; do
    if gh api "repos/$PRIVATE_REPO/issues/$EXISTING_PRIV/comments" --jq '.[].body' 2>/dev/null | grep -q "public_comment_id: $cid"; then
        EDIT_MIRROR_ID="$cid"
        break
    fi
done

if [[ -n "$EDIT_MIRROR_ID" ]]; then
    gh api -X PATCH "repos/$PUBLIC_REPO/issues/comments/$EDIT_MIRROR_ID" -f body="This comment was EDITED while webhooks were down."
    echo "  Public comment $EDIT_MIRROR_ID edited"
else
    echo "  ⚠ No mirrored comment found to edit — skipping Drift 9"
fi

# --- Drift 10: Comment deletion (Tombstone) ---
echo
echo "  [Drift 10] Deleting a public comment (that already has a mirror)..."
MIRRORED_COMMENT_ID=""
for cid in $PUB_COMMENTS; do
    if [[ "$cid" == "$EDIT_MIRROR_ID" ]]; then continue; fi
    if gh api "repos/$PRIVATE_REPO/issues/$EXISTING_PRIV/comments" --jq '.[].body' 2>/dev/null | grep -q "public_comment_id: $cid"; then
        MIRRORED_COMMENT_ID="$cid"
        break
    fi
done

if [[ -n "$MIRRORED_COMMENT_ID" ]]; then
    gh api -X DELETE "repos/$PUBLIC_REPO/issues/comments/$MIRRORED_COMMENT_ID"
    echo "  Public comment $MIRRORED_COMMENT_ID deleted (mirror should be tombstoned)"
else
    echo "  ⚠ No second mirrored comment found to delete — skipping Drift 10"
fi

# --- Drift 6: Public closed but private still open (missed public→private cascade) ---
echo
echo "  [Drift 6] Closing public #$STATE_PUB (private #$STATE_PRIV stays open)..."
gh issue close "$STATE_PUB" --repo "$PUBLIC_REPO" --reason "completed"
echo "  Public closed, private still open"

# --- Drift 7: Private closed by human but public still open (missed private→public cascade) ---
echo
echo "  [Drift 7] Closing private #$CASCADE_PRIV (public #$CASCADE_PUB stays open)..."
gh issue close "$CASCADE_PRIV" --repo "$PRIVATE_REPO"
echo "  Private closed by human, public still open — sync pass 2 should catch this"

echo
echo "  Drift created. Waiting 5s for any straggler webhooks..."
sleep 5

# ── Phase 3: Run sync ───────────────────────────────────────────────────────

step "Phase 3: Run sync (via GitHub Actions)"

# Re-enable sync workflow so we can trigger it
gh workflow enable "Sync public issues" --repo "$PRIVATE_REPO" 2>/dev/null || true
echo "  Enabled: $PRIVATE_REPO / Sync public issues"

echo "  Triggering sync workflow..."
gh workflow run "Sync public issues" --repo "$PRIVATE_REPO"
sleep 3

# Wait for the workflow run to complete (up to 5 min)
echo "  Waiting for sync workflow to complete..."
SYNC_OK=false
for _ in $(seq 1 60); do
    read -r run_id status conclusion < <(
        gh run list --repo "$PRIVATE_REPO" --workflow "Sync public issues" --limit 1 \
            --json databaseId,status,conclusion \
            --jq '.[0] | [.databaseId, .status, .conclusion] | @tsv' 2>/dev/null
    ) || true

    if [[ "$status" == "completed" ]]; then
        if [[ "$conclusion" == "success" ]]; then
            echo "  ✓ Sync workflow completed successfully"
            SYNC_OK=true
        else
            echo "  ✗ Sync workflow failed: $conclusion"
        fi
        echo
        echo "  ── Workflow log (run $run_id) ──"
        gh run view "$run_id" --repo "$PRIVATE_REPO" --log 2>/dev/null \
            | sed 's/^/    /' || echo "    (could not fetch logs)"
        echo "  ── End log ──"
        break
    fi
    sleep 5
done
if [[ "$SYNC_OK" != "true" && "$status" != "completed" ]]; then
    echo "  ⚠ Timed out waiting for sync workflow (5 min)"
fi

# Disable sync workflow again (cleanup trap will re-enable all at exit)
gh workflow disable "Sync public issues" --repo "$PRIVATE_REPO" 2>/dev/null || true

# ── Phase 4: Verify ─────────────────────────────────────────────────────────

step "Phase 4: Verify"

# Check drift 1: orphan should now have a private mirror
echo
echo "  [Drift 1] Orphan public #$ORPHAN_NUM — missing private mirror"
echo "    public:  $(issue_url "$PUBLIC_REPO" "$ORPHAN_NUM")"
ORPHAN_PRIV=$(find_private_issue "$ORPHAN_NUM")
if [[ -n "$ORPHAN_PRIV" ]]; then
    echo "    private: $(issue_url "$PRIVATE_REPO" "$ORPHAN_PRIV")"
fi
check "Private mirror exists" check_not_empty "$ORPHAN_PRIV"
if [[ -n "$ORPHAN_PRIV" ]]; then
    check "Private title has [public #$ORPHAN_NUM] prefix" \
        check_title_contains "$PRIVATE_REPO" "$ORPHAN_PRIV" "\[public #$ORPHAN_NUM\]"
    check "Private body contains original text" \
        check_body_contains "$PRIVATE_REPO" "$ORPHAN_PRIV" "webhooks were disabled"
    check "Bug label mirrored to private" \
        check_has_label "$PRIVATE_REPO" "$ORPHAN_PRIV" "bug"
    check "Mapping comment posted on public" \
        check_comments_contain "$PUBLIC_REPO" "$ORPHAN_NUM" "mapping:"
fi

echo
echo "  [Drift 2-5] Title/body/comment/label sync"
echo "    public:  $(issue_url "$PUBLIC_REPO" "$EXISTING_PUB")"
echo "    private: $(issue_url "$PRIVATE_REPO" "$EXISTING_PRIV")"

echo
echo "  [Drift 2] Stale title..."
check "Private title updated to match public" \
    check_title_contains "$PRIVATE_REPO" "$EXISTING_PRIV" "SYNC-TEST:"

echo
echo "  [Drift 3] Stale body..."
check "Private body contains sync-test marker" \
    check_body_contains "$PRIVATE_REPO" "$EXISTING_PRIV" "sync-test marker"

echo
echo "  [Drift 4] Missing comment..."
check "Comment mirrored to private" \
    check_comments_contain "$PRIVATE_REPO" "$EXISTING_PRIV" "webhooks were disabled"

echo
echo "  [Drift 5] Missing label..."
check "sync-test label on private" \
    check_has_label "$PRIVATE_REPO" "$EXISTING_PRIV" "sync-test"

echo
echo "  [Drift 8] Label removal & protection..."
check "stale-label removed from private" \
    check_not_has_label "$PRIVATE_REPO" "$EXISTING_PRIV" "stale-label"
check "resolution:completed label protected" \
    check_has_label "$PRIVATE_REPO" "$EXISTING_PRIV" "resolution:completed"

echo
echo "  [Drift 9] Comment edit..."
if [[ -n "${EDIT_MIRROR_ID:-}" ]]; then
    check "Private mirror updated with edit content" \
        check_comments_contain "$PRIVATE_REPO" "$EXISTING_PRIV" "EDITED while webhooks"
else
    echo "    skipped (no mirrored comment edited)"
fi

echo
echo "  [Drift 10] Comment deletion (Tombstone)..."
if [[ -n "${MIRRORED_COMMENT_ID:-}" ]]; then
    check "Private mirror tombstoned" \
        check_comments_contain "$PRIVATE_REPO" "$EXISTING_PRIV" "deleted on public"
else
    echo "    skipped (no mirrored comment deleted)"
fi

# Check drift 6: public closed → private should be closed too
echo
echo "  [Drift 6] State sync public→private (missed close)"
echo "    public:  $(issue_url "$PUBLIC_REPO" "$STATE_PUB")"
echo "    private: $(issue_url "$PRIVATE_REPO" "$STATE_PRIV")"
check "Private issue is closed" \
    check_state "$PRIVATE_REPO" "$STATE_PRIV" "CLOSED"

# Check drift 7: private closed by human → public should be closed too
echo
echo "  [Drift 7] State sync private→public (missed cascade)"
echo "    private: $(issue_url "$PRIVATE_REPO" "$CASCADE_PRIV")"
echo "    public:  $(issue_url "$PUBLIC_REPO" "$CASCADE_PUB")"
check "Public issue is closed" \
    check_state "$PUBLIC_REPO" "$CASCADE_PUB" "CLOSED"

# ── Phase 5: Clean up ───────────────────────────────────────────────────────

step "Phase 5: Clean up"

# Revert title and body drift
echo "  Reverting public #$EXISTING_PUB title..."
gh issue edit "$EXISTING_PUB" --repo "$PUBLIC_REPO" --title "$ORIGINAL_TITLE"
echo "  Reverting public #$EXISTING_PUB body..."
gh issue edit "$EXISTING_PUB" --repo "$PUBLIC_REPO" --body "$ORIGINAL_BODY"

# Remove test labels
gh issue edit "$EXISTING_PUB" --repo "$PUBLIC_REPO" --remove-label "sync-test" 2>/dev/null || true
gh issue edit "$EXISTING_PRIV" --repo "$PRIVATE_REPO" --remove-label "resolution:completed" 2>/dev/null || true

# Reopen state-drift issues
echo "  Reopening public #$STATE_PUB and private #$STATE_PRIV..."
gh issue reopen "$STATE_PUB" --repo "$PUBLIC_REPO" 2>/dev/null || true
gh issue reopen "$STATE_PRIV" --repo "$PRIVATE_REPO" 2>/dev/null || true
echo "  Reopening public #$CASCADE_PUB and private #$CASCADE_PRIV..."
gh issue reopen "$CASCADE_PUB" --repo "$PUBLIC_REPO" 2>/dev/null || true
gh issue reopen "$CASCADE_PRIV" --repo "$PRIVATE_REPO" 2>/dev/null || true

# Close orphan issue
gh issue close "$ORPHAN_NUM" --repo "$PUBLIC_REPO" 2>/dev/null || true
if [[ -n "${ORPHAN_PRIV:-}" ]]; then
    gh issue close "$ORPHAN_PRIV" --repo "$PRIVATE_REPO" 2>/dev/null || true
fi

# Run sync one more time to bring private mirrors back in line with reverted public
echo "  Running post-cleanup sync to restore private mirrors..."
gh workflow enable "Sync public issues" --repo "$PRIVATE_REPO" 2>/dev/null || true
gh workflow run "Sync public issues" --repo "$PRIVATE_REPO"
sleep 3
for _ in $(seq 1 60); do
    status=$(gh run list --repo "$PRIVATE_REPO" --workflow "Sync public issues" --limit 1 \
        --json status --jq '.[0].status' 2>/dev/null || echo "")
    if [[ "$status" == "completed" ]]; then
        echo "  ✓ Post-cleanup sync complete"
        break
    fi
    sleep 5
done
gh workflow disable "Sync public issues" --repo "$PRIVATE_REPO" 2>/dev/null || true

# Workflows are re-enabled by the EXIT trap

# ── Summary ──────────────────────────────────────────────────────────────────

step "Results"

echo
echo "  Automated checks: $CHECKS_PASSED passed, $CHECKS_FAILED failed"
echo
echo "  Manual verification links:"
echo
echo "  Drift 1 (orphan mirror):"
echo "    public:  $(issue_url "$PUBLIC_REPO" "$ORPHAN_NUM")"
[[ -n "${ORPHAN_PRIV:-}" ]] && \
echo "    private: $(issue_url "$PRIVATE_REPO" "$ORPHAN_PRIV")"
echo "  Drift 2-5,8-10 (title/body/comment/label/tombstone):"
echo "    public:  $(issue_url "$PUBLIC_REPO" "$EXISTING_PUB")"
echo "    private: $(issue_url "$PRIVATE_REPO" "$EXISTING_PRIV")"
echo "  Drift 6 (public→private close):"
echo "    public:  $(issue_url "$PUBLIC_REPO" "$STATE_PUB")"
echo "    private: $(issue_url "$PRIVATE_REPO" "$STATE_PRIV")"
echo "  Drift 7 (private→public close):"
echo "    private: $(issue_url "$PRIVATE_REPO" "$CASCADE_PRIV")"
echo "    public:  $(issue_url "$PUBLIC_REPO" "$CASCADE_PUB")"
echo
if [[ $CHECKS_FAILED -gt 0 ]]; then
    echo "  ⚠ Some checks failed — review the output above."
    exit 1
else
    echo "  All checks passed!"
fi
