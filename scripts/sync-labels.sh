#!/usr/bin/env bash
#
# Copies labels from one repo to another.
#
# Usage:
#   ./scripts/sync-labels.sh <source-repo> <target-repo> [label-pattern]
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
# Existing labels in the target are skipped (not overwritten).

set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <source-repo> <target-repo> [label-pattern]"
    exit 1
fi

SOURCE="$1"
TARGET="$2"
PATTERN="${3:-}"

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
read -rp "Copy these to $TARGET? [y/N] " confirm
if [[ "${confirm,,}" != "y" ]]; then
    echo "Aborted."
    exit 0
fi

# Fetch existing labels in target
EXISTING=$(gh label list --repo "$TARGET" --limit 200 --json name | jq -r '.[].name')

CREATED=0
SKIPPED=0

echo "$LABELS" | jq -c '.[]' | while read -r label; do
    NAME=$(echo "$label" | jq -r '.name')
    COLOR=$(echo "$label" | jq -r '.color')
    DESC=$(echo "$label" | jq -r '.description // ""')

    if echo "$EXISTING" | grep -qxF "$NAME"; then
        echo "  skip: $NAME (already exists)"
        SKIPPED=$((SKIPPED + 1))
    else
        if [[ -n "$DESC" ]]; then
            gh label create "$NAME" --repo "$TARGET" --color "$COLOR" --description "$DESC"
        else
            gh label create "$NAME" --repo "$TARGET" --color "$COLOR"
        fi
        echo "  created: $NAME"
        CREATED=$((CREATED + 1))
    fi
done

echo
echo "Done."
