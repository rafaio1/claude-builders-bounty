#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${1:-.}"
OUTPUT_FILE="${2:-CHANGELOG.md}"

cd "$REPO_DIR"

# Get last tag or use initial commit
LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || git rev-list --max-parents=0 HEAD)

if [ -z "$LAST_TAG" ]; then
  echo "Error: No commits found in repository" >&2
  exit 1
fi

# Collect commits since last tag
COMMITS=$(git log "${LAST_TAG}..HEAD" --pretty=format:"%s" 2>/dev/null || git log --pretty=format:"%s")

if [ -z "$COMMITS" ]; then
  echo "# Changelog" > "$OUTPUT_FILE"
  echo "" >> "$OUTPUT_FILE"
  echo "No changes since last release." >> "$OUTPUT_FILE"
  exit 0
fi

# Initialize sections
ADDED=""
FIXED=""
CHANGED=""
REMOVED=""

# Categorize commits
while IFS= read -r line; do
  lower=$(echo "$line" | tr '[:upper:]' '[:lower:]')
  if echo "$lower" | grep -qE '^(fix|bugfix|bug|patch)'; then
    FIXED="${FIXED}- ${line}\n"
  elif echo "$lower" | grep -qE '^(add|feat|feature|new|introduce)'; then
    ADDED="${ADDED}- ${line}\n"
  elif echo "$lower" | grep -qE '^(remove|delete|drop|deprecate)'; then
    REMOVED="${REMOVED}- ${line}\n"
  else
    CHANGED="${CHANGED}- ${line}\n"
  fi
done <<< "$COMMITS"

# Write CHANGELOG.md
{
  echo "# Changelog"
  echo ""
  echo "## [Unreleased] - $(date +%Y-%m-%d)"
  echo ""
  
  if [ -n "$ADDED" ]; then
    echo "### Added"
    echo -e "$ADDED"
  fi
  
  if [ -n "$FIXED" ]; then
    echo "### Fixed"
    echo -e "$FIXED"
  fi
  
  if [ -n "$CHANGED" ]; then
    echo "### Changed"
    echo -e "$CHANGED"
  fi
  
  if [ -n "$REMOVED" ]; then
    echo "### Removed"
    echo -e "$REMOVED"
  fi
} > "$OUTPUT_FILE"

echo "Generated $OUTPUT_FILE from commits since $LAST_TAG"
