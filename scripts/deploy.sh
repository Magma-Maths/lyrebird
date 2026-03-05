#!/usr/bin/env bash
#
# Deploys lyrebird to an existing pair of public/private repos.
#
# What it does:
#   1. Sets repository variables and secrets on both repos
#   2. Copies workflow files into each repo (on a branch, opens a PR)
#
# Usage:
#   cp scripts/.env.example scripts/.env   # fill in values for your real repos
#   ./scripts/deploy.sh              # deploy via PRs
#   ./scripts/deploy.sh --no-pr      # push directly to main
#
# Prerequisites:
#   - gh CLI authenticated (gh auth login)
#   - A GitHub App with Actions read/write and Issues read/write permissions
#   - Both repos already exist

set -euo pipefail

USE_PR=true
if [[ "${1:-}" == "--no-pr" ]]; then
    USE_PR=false
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LYREBIRD_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

# ── Load .env ────────────────────────────────────────────────────────────────

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Error: $ENV_FILE not found."
    echo "  cp scripts/.env.example scripts/.env"
    echo "  # fill in your values, then re-run"
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

# Verify repos exist
for REPO in "$PUBLIC_REPO" "$PRIVATE_REPO"; do
    if ! gh repo view "$REPO" &>/dev/null; then
        echo "Error: repo $REPO not found. This script expects existing repos."
        exit 1
    fi
done

echo "Configuration:"
echo "  Org:          $ORG"
echo "  Public repo:  $PUBLIC_REPO"
echo "  Private repo: $PRIVATE_REPO"
echo "  Lyrebird:     $LYREBIRD_REPO"
echo "  App ID:       $APP_ID"
echo "  Bot login:    $BOT_LOGIN"
echo
read -rp "Proceed? [y/N] " confirm
if [[ "${confirm,,}" != "y" ]]; then
    echo "Aborted."
    exit 0
fi

# ── Set variables and secrets ────────────────────────────────────────────────

echo
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

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo
echo "==> Deploying workflow files..."

deploy_workflows() {
    local repo="$1"
    local clone_dir="$2"
    shift 2
    local files=("$@")

    echo "  $repo"
    cd "$WORK"
    gh repo clone "$repo" "$clone_dir" -- -q
    cd "$clone_dir"

    if [[ "$USE_PR" == true ]]; then
        git checkout -b lyrebird/deploy-workflows
    fi

    mkdir -p .github/workflows
    for f in "${files[@]}"; do
        cp "$LYREBIRD_DIR/workflows/$f" .github/workflows/
    done
    git add .github/workflows/

    if git diff --cached --quiet; then
        echo "    No changes (workflows already up to date)"
        return
    fi

    git commit -q -m "ci: add lyrebird workflows"

    if [[ "$USE_PR" == true ]]; then
        git push -q -u origin lyrebird/deploy-workflows
        gh pr create --title "Add lyrebird workflows" --body "Deploys lyrebird workflow files."
        echo "    PR created"
    else
        git push -q origin main
        echo "    Pushed to main"
    fi
}

deploy_workflows "$PUBLIC_REPO" public-clone \
    public-dispatch.yml

deploy_workflows "$PRIVATE_REPO" private-clone \
    handle-public-event.yml \
    handle-private-issue.yml \
    handle-private-comment.yml

# ── Create delayed-5min environment on private repo ──────────────────────────

echo
echo "==> Creating delayed-5min environment on $PRIVATE_REPO..."

ENV_RESPONSE=$(gh api --method PUT "repos/$PRIVATE_REPO/environments/delayed-5min" \
    --input - <<< '{"wait_timer": 5}' 2>&1) || {
    echo "  ⚠ Could not create environment (may need admin access)"
    ENV_RESPONSE=""
}
if [[ -n "$ENV_RESPONSE" ]]; then
    ACTUAL_TIMER=$(echo "$ENV_RESPONSE" | jq -r '.protection_rules[]? | select(.type == "wait_timer") | .wait_timer // empty' 2>/dev/null)
    if [[ "$ACTUAL_TIMER" == "5" ]]; then
        echo "  delayed-5min (5 min wait timer)"
    else
        echo "  delayed-5min created, but wait timer was NOT set."
        echo "  Wait timers on private repos require GitHub Enterprise."
        echo "  The delayed-close-check job will still run, but without the 5-minute delay."
    fi
fi

# ── Done ─────────────────────────────────────────────────────────────────────

echo
echo "Done! Make sure your GitHub App has access to both repos:"
echo "  https://github.com/organizations/$ORG/settings/installations"
