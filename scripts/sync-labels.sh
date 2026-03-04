#!/usr/bin/env bash
#
# Copies labels from one repo to another.
#
# Usage:
#   ./scripts/sync-labels.sh <source-repo> <target-repo> [label-pattern] [--force]
#
# Examples:
#   # Copy all labels
#   ./scripts/sync-labels.sh yourorg/public-repo yourorg/private-repo
#
#   # Copy only labels matching a pattern (grep regex)
#   ./scripts/sync-labels.sh yourorg/public-repo yourorg/private-repo "^bug$|^enhancement$"
#
#   # Copy labels starting with "priority:"
#   ./scripts/sync-labels.sh yourorg/public-repo yourorg/private-repo "^priority:"
#
#   # Overwrite existing labels (update color and description)
#   ./scripts/sync-labels.sh yourorg/public-repo yourorg/private-repo --force
#
# By default, existing labels in the target are skipped.
# With --force, existing labels are updated to match the source.

set -euo pipefail

FORCE=false
PATTERN=""
POSITIONAL=()

for arg in "$@"; do
    case "$arg" in
        --force) FORCE=true ;;
        *) POSITIONAL+=("$arg") ;;
    esac
done

if [[ ${#POSITIONAL[@]} -lt 2 ]]; then
    echo "Usage: $0 <source-repo> <target-repo> [label-pattern] [--force]"
    exit 1
fi

SOURCE="${POSITIONAL[0]}"
TARGET="${POSITIONAL[1]}"
PATTERN="${POSITIONAL[2]:-}"

# Fetch all labels from source
echo "Fetching labels from $SOURCE..."
LABELS=$(gh label list --repo "$SOURCE" --limit 200 --json name,color,description)

if [[ -n "$PATTERN" ]]; then
    LABELS=$(echo "$LABELS" | jq -c --arg p "$PATTERN" '[.[] | select(.name | test($p))]')
fi

COUNT=$(echo "$LABELS" | jq length)
if [[ "$COUNT" -eq 0 ]]; then
    echo "No labels matched."
    exit 0
fi

echo "Labels to copy ($COUNT):"
echo "$LABELS" | jq -r '.[].name' | sed 's/^/  /'
echo
if [[ "$FORCE" == true ]]; then
    echo "(--force: existing labels will be updated)"
    echo
fi
read -rp "Copy these to $TARGET? [y/N] " confirm
if [[ "${confirm,,}" != "y" ]]; then
    echo "Aborted."
    exit 0
fi

# Fetch existing labels in target
EXISTING=$(gh label list --repo "$TARGET" --limit 200 --json name | jq -r '.[].name')

echo "$LABELS" | jq -c '.[]' | while read -r label; do
    NAME=$(echo "$label" | jq -r '.name')
    COLOR=$(echo "$label" | jq -r '.color')
    DESC=$(echo "$label" | jq -r '.description // ""')

    ARGS=(--repo "$TARGET" --color "$COLOR")
    if [[ -n "$DESC" ]]; then
        ARGS+=(--description "$DESC")
    fi
    if [[ "$FORCE" == true ]]; then
        ARGS+=(--force)
    fi

    if gh label create "$NAME" "${ARGS[@]}" 2>/dev/null; then
        echo "  ok: $NAME"
    else
        echo "  skip: $NAME (already exists)"
    fi
done

echo
echo "Done."
