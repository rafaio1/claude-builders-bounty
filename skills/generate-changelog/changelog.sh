#!/usr/bin/env bash
# generate-changelog: Generate structured CHANGELOG.md from git history
# Usage: bash changelog.sh [output_file]
set -euo pipefail

OUTPUT="${CHANGELOG_OUTPUT:-${1:-CHANGELOG.md}}"
SINCE_TAG="${CHANGELOG_SINCE_TAG:-}"
MAX_COMMITS="${CHANGELOG_MAX_COMMITS:-0}"

# Find the last tag or fall back to initial commit
if [ -z "$SINCE_TAG" ]; then
    SINCE_TAG=$(git describe --tags --abbrev=0 2>/dev/null || git rev-list --max-parents=0 HEAD)
fi

# Get commits since tag
COMMITS=$(git log "${SINCE_TAG}..HEAD" --pretty=format:"%s|%h" --reverse)

if [ -z "$COMMITS" ]; then
    echo "No commits found since ${SINCE_TAG}"
    exit 0
fi

# Categorize commits
ADDED=""
FIXED=""
CHANGED=""
REMOVED=""
OTHER=""
COUNT=0

while IFS='|' read -r msg hash; do
    if [ "$MAX_COMMITS" -gt 0 ] && [ "$COUNT" -ge "$MAX_COMMITS" ]; then
        break
    fi
    
    case "$msg" in
        feat:*|feat\(*) ADDED="${ADDED}- ${msg} (${hash})\n" ;;
        fix:*|fix\(*) FIXED="${FIXED}- ${msg} (${hash})\n" ;;
        refactor:*|perf:*|style:*|refactor\(*|perf\(*|style\(*) CHANGED="${CHANGED}- ${msg} (${hash})\n" ;;
        revert:*|remove:*|delete:*|revert\(*|remove\(*|delete\(*) REMOVED="${REMOVED}- ${msg} (${hash})\n" ;;
        *) OTHER="${OTHER}- ${msg} (${hash})\n" ;;
    esac
    COUNT=$((COUNT + 1))
done <<< "$COMMITS"

# Build new section
DATE=$(date +%Y-%m-%d)
NEW_SECTION="## [Unreleased] - ${DATE}\n\n"

[ -n "$ADDED" ] && NEW_SECTION="${NEW_SECTION}### Added\n${ADDED}\n"
[ -n "$FIXED" ] && NEW_SECTION="${NEW_SECTION}### Fixed\n${FIXED}\n"
[ -n "$CHANGED" ] && NEW_SECTION="${NEW_SECTION}### Changed\n${CHANGED}\n"
[ -n "$REMOVED" ] && NEW_SECTION="${NEW_SECTION}### Removed\n${REMOVED}\n"
[ -n "$OTHER" ] && NEW_SECTION="${NEW_SECTION}### Other\n${OTHER}\n"

# Prepend to existing file or create new
if [ -f "$OUTPUT" ]; then
    EXISTING=$(tail -n +2 "$OUTPUT")
    printf "# Changelog\n\n%b\n%s" "$NEW_SECTION" "$EXISTING" > "$OUTPUT"
else
    printf "# Changelog\n\n%b" "$NEW_SECTION" > "$OUTPUT"
fi

echo "✅ Generated $OUTPUT with $COUNT entries since ${SINCE_TAG}"
