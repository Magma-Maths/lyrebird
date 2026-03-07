#!/usr/bin/env bash
#
# Sets up a pair of test repos for end-to-end lyrebird testing.
#
# Usage:
#   cp scripts/.env.example scripts/.env   # fill in APP_ID and PEM_FILE
#   ./scripts/setup-test-repos.sh
#
# Prerequisites:
#   - gh CLI authenticated (gh auth login)
#   - A GitHub App with Actions read/write and Issues read/write permissions
#   - The lyrebird repo already pushed to GitHub (the workflows check it out)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LYREBIRD_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

# ── Load .env ────────────────────────────────────────────────────────────────

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Error: $ENV_FILE not found."
    echo "  cp scripts/.env.example scripts/.env"
    echo "  # fill in APP_ID and PEM_FILE, then re-run"
    exit 1
fi

# shellcheck source=/dev/null
source "$ENV_FILE"

PUBLIC_REPO="$ORG/$PUBLIC_REPO_NAME"
PRIVATE_REPO="$ORG/$PRIVATE_REPO_NAME"

# ── Validate ─────────────────────────────────────────────────────────────────

missing=()
[[ -z "${APP_ID:-}" ]]            && missing+=("APP_ID")
[[ -z "${PEM_FILE:-}" ]]          && missing+=("PEM_FILE")
[[ -z "${ORG:-}" ]]               && missing+=("ORG")
[[ -z "${PUBLIC_REPO_NAME:-}" ]]  && missing+=("PUBLIC_REPO_NAME")
[[ -z "${PRIVATE_REPO_NAME:-}" ]] && missing+=("PRIVATE_REPO_NAME")
[[ -z "${LYREBIRD_REPO:-}" ]]     && missing+=("LYREBIRD_REPO")
[[ -z "${BOT_LOGIN:-}" ]]         && missing+=("BOT_LOGIN")
if [[ ${#missing[@]} -gt 0 ]]; then
    echo "Error: missing values in $ENV_FILE: ${missing[*]}"
    exit 1
fi
if [[ ! -f "$PEM_FILE" ]]; then
    echo "Error: PEM_FILE not found: $PEM_FILE"
    exit 1
fi

echo "Configuration:"
echo "  Org:          $ORG"
echo "  Public repo:  $PUBLIC_REPO"
echo "  Private repo: $PRIVATE_REPO"
echo "  Lyrebird:     $LYREBIRD_REPO"
echo "  App ID:       $APP_ID"
echo "  Bot login:    $BOT_LOGIN"
echo

# ── Delete existing test repos ───────────────────────────────────────────────

EXISTING=()
for REPO in "$PUBLIC_REPO" "$PRIVATE_REPO"; do
    if gh repo view "$REPO" &>/dev/null; then
        EXISTING+=("$REPO")
    fi
done

if [[ ${#EXISTING[@]} -gt 0 ]]; then
    echo "The following repos already exist and will be DELETED:"
    for REPO in "${EXISTING[@]}"; do
        echo "  - $REPO"
    done
    echo
    read -rp "Delete and recreate them? [y/N] " confirm
    if [[ "${confirm,,}" != "y" ]]; then
        echo "Aborted."
        exit 0
    fi
    echo
    for REPO in "${EXISTING[@]}"; do
        echo "  Deleting $REPO..."
        gh repo delete "$REPO" --yes
    done
fi

# ── Create repos ─────────────────────────────────────────────────────────────

echo "==> Creating repos..."

gh repo create "$PUBLIC_REPO" --private --description "Lyrebird test (public side)"
echo "  Created $PUBLIC_REPO"

gh repo create "$PRIVATE_REPO" --private --description "Lyrebird test (private side)"
echo "  Created $PRIVATE_REPO"

# ── Set variables and secrets ────────────────────────────────────────────────

echo "==> Setting variables and secrets..."

for REPO in "$PUBLIC_REPO" "$PRIVATE_REPO"; do
    echo "  $REPO"
    gh variable set LYREBIRD_APP_ID    --repo "$REPO" --body "$APP_ID"
    gh variable set LYREBIRD_REPO      --repo "$REPO" --body "$LYREBIRD_REPO"
    gh variable set PUBLIC_REPO        --repo "$REPO" --body "$PUBLIC_REPO"
    gh variable set PUBLIC_REPO_NAME   --repo "$REPO" --body "$PUBLIC_REPO_NAME"
    gh variable set PRIVATE_REPO       --repo "$REPO" --body "$PRIVATE_REPO"
    gh variable set PRIVATE_REPO_NAME  --repo "$REPO" --body "$PRIVATE_REPO_NAME"
    gh variable set BOT_LOGIN          --repo "$REPO" --body "$BOT_LOGIN"
    gh secret set LYREBIRD_APP_PRIVATE_KEY --repo "$REPO" < "$PEM_FILE"
done

# ── Deploy workflow files ────────────────────────────────────────────────────

echo "==> Deploying workflow files..."

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Public repo
echo "  $PUBLIC_REPO"
cd "$WORK"
mkdir public-clone && cd public-clone
git init -b main -q
git remote add origin "git@github.com:$PUBLIC_REPO.git"
mkdir -p .github/workflows
cp "$LYREBIRD_DIR/workflows/public-dispatch.yml" .github/workflows/
git add .
git commit -q -m "ci: add lyrebird dispatch workflow"
git push -q -u origin main

# Private repo
echo "  $PRIVATE_REPO"
cd "$WORK"
mkdir private-clone && cd private-clone
git init -b main -q
git remote add origin "git@github.com:$PRIVATE_REPO.git"
mkdir -p .github/workflows
cp "$LYREBIRD_DIR/workflows/handle-public-event.yml"     .github/workflows/
cp "$LYREBIRD_DIR/workflows/handle-private-issue.yml"    .github/workflows/
cp "$LYREBIRD_DIR/workflows/handle-private-comment.yml"  .github/workflows/
cp "$LYREBIRD_DIR/workflows/sync.yml"                    .github/workflows/
git add .
git commit -q -m "ci: add lyrebird handler workflows"
git push -q -u origin main

# ── Create resolution labels on private repo ─────────────────────────────────

echo "==> Creating resolution labels on $PRIVATE_REPO..."

gh label create "resolution:completed"        --repo "$PRIVATE_REPO" --color "0e8a16" --description "Resolved: completed"        --force 2>/dev/null && echo "  resolution:completed" || true
gh label create "resolution:not-planned"      --repo "$PRIVATE_REPO" --color "e4e669" --description "Resolved: not planned"      --force 2>/dev/null && echo "  resolution:not-planned" || true
gh label create "resolution:cannot-reproduce" --repo "$PRIVATE_REPO" --color "e4e669" --description "Resolved: cannot reproduce" --force 2>/dev/null && echo "  resolution:cannot-reproduce" || true
gh label create "resolution:custom"           --repo "$PRIVATE_REPO" --color "c5def5" --description "Custom resolution via /anon" --force 2>/dev/null && echo "  resolution:custom" || true
gh label create "resolution:none"             --repo "$PRIVATE_REPO" --color "fbca04" --description "Close requires a resolution label" --force 2>/dev/null && echo "  resolution:none" || true

# ── Done ─────────────────────────────────────────────────────────────────────

echo
echo "Done! Make sure your GitHub App has access to both repos:"
echo "  https://github.com/organizations/$ORG/settings/installations"
echo
echo "Test it:"
echo "  gh issue create --repo $PUBLIC_REPO --title 'Test issue' --body 'Does lyrebird work?'"
echo "  gh run list --repo $PUBLIC_REPO --limit 3"
echo "  gh run list --repo $PRIVATE_REPO --limit 3"
