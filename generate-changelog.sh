 #!/usr/bin/env bash
 # generate-changelog.sh — Generate structured CHANGELOG.md from git history
 # Usage: ./generate-changelog.sh [output_file]
 set -euo pipefail
 
 OUTPUT="${1:-CHANGELOG.md}"
 LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
 
 if [ -z "$LAST_TAG" ]; then
   RANGE="HEAD"
 else
   RANGE="${LAST_TAG}..HEAD"
 fi
 
 ADDED=""
 FIXED=""
 CHANGED=""
 REMOVED=""
 
 while IFS= read -r line; do
   msg=$(echo "$line" | sed 's/^[a-f0-9]* //')
   lower=$(echo "$msg" | tr '[:upper:]' '[:lower:]')
   
   if echo "$lower" | grep -qE '^\s*(feat|add|new|introduce)'; then
     ADDED="${ADDED}- ${msg}\n"
   elif echo "$lower" | grep -qE '^\s*(fix|bug|patch|resolve)'; then
     FIXED="${FIXED}- ${msg}\n"
   elif echo "$lower" | grep -qE '^\s*(remove|delete|drop|deprecate)'; then
     REMOVED="${REMOVED}- ${msg}\n"
   else
     CHANGED="${CHANGED}- ${msg}\n"
   fi
 done < <(git log --pretty=format:"%h %s" $RANGE)
 
 {
   echo "# Changelog"
   echo ""
   echo "## [Unreleased]"
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
 } > "$OUTPUT"
 
 echo "✅ Generated $OUTPUT from commits since ${LAST_TAG:-initial commit}"
