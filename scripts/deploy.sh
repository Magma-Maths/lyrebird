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
#   ./scripts/deploy.sh
#
# Prerequisites:
#   - gh CLI authenticated (gh auth login)
#   - A GitHub App with Actions read/write and Issues read/write permissions
#   - Both repos already exist

set -euo pipefail

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

# ── Deploy workflow files via PRs ────────────────────────────────────────────

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
BRANCH="lyrebird/deploy-workflows"

echo
echo "==> Deploying workflow files..."

# Public repo
echo "  $PUBLIC_REPO"
cd "$WORK"
gh repo clone "$PUBLIC_REPO" public-clone -- -q
cd public-clone
git checkout -b "$BRANCH"
mkdir -p .github/workflows
cp "$LYREBIRD_DIR/workflows/public-dispatch.yml" .github/workflows/
git add .github/workflows/public-dispatch.yml
if git diff --cached --quiet; then
    echo "    No changes (workflow already up to date)"
else
    git commit -q -m "ci: add lyrebird dispatch workflow"
    git push -q -u origin "$BRANCH"
    gh pr create --title "Add lyrebird dispatch workflow" --body "$(cat <<'EOF'
Adds the public-dispatch workflow that forwards issue and comment events
to the private repo for processing by lyrebird.
EOF
)"
    echo "    PR created"
fi

# Private repo
echo "  $PRIVATE_REPO"
cd "$WORK"
gh repo clone "$PRIVATE_REPO" private-clone -- -q
cd private-clone
git checkout -b "$BRANCH"
mkdir -p .github/workflows
cp "$LYREBIRD_DIR/workflows/handle-public-event.yml"     .github/workflows/
cp "$LYREBIRD_DIR/workflows/handle-private-issue.yml"    .github/workflows/
cp "$LYREBIRD_DIR/workflows/handle-private-comment.yml"  .github/workflows/
git add .github/workflows/
if git diff --cached --quiet; then
    echo "    No changes (workflows already up to date)"
else
    git commit -q -m "ci: add lyrebird handler workflows"
    git push -q -u origin "$BRANCH"
    gh pr create --title "Add lyrebird handler workflows" --body "$(cat <<'EOF'
Adds the lyrebird handler workflows:
- handle-public-event.yml — processes mirrored public events
- handle-private-issue.yml — handles private issue close/reopen
- handle-private-comment.yml — handles slash commands
EOF
)"
    echo "    PR created"
fi

# ── Done ─────────────────────────────────────────────────────────────────────

echo
echo "Done! Next steps:"
echo "  1. Review and merge the PRs above"
echo "  2. Make sure your GitHub App has access to both repos:"
echo "     https://github.com/organizations/$ORG/settings/installations"
