 #!/usr/bin/env bash
 set -euo pipefail
 
 # Generate structured CHANGELOG.md from git history since last tag
 # Usage: bash changelog.sh [output_file]
 
 OUTPUT="${1:-CHANGELOG.md}"
 
 # Get last tag or fallback to first commit
 LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || git rev-list --max-parents=0 HEAD)
 RANGE="${LAST_TAG}..HEAD"
 
 # If no tags exist, use all commits
 if ! git describe --tags --abbrev=0 >/dev/null 2>&1; then
   RANGE="HEAD"
 fi
 
 ADDED=""
 FIXED=""
 CHANGED=""
 REMOVED=""
 
 while IFS= read -r line; do
   msg=$(echo "$line" | sed 's/^[a-f0-9]* //')
   lower=$(echo "$msg" | tr '[:upper:]' '[:lower:]')
   
   if echo "$lower" | grep -qE '^(feat|add|new)[:( ]'; then
     ADDED="${ADDED}- ${msg}\n"
   elif echo "$lower" | grep -qE '^(fix|bugfix|patch)[:( ]'; then
     FIXED="${FIXED}- ${msg}\n"
   elif echo "$lower" | grep -qE '^(remove|delete|deprecate|drop)[:( ]'; then
     REMOVED="${REMOVED}- ${msg}\n"
   else
     CHANGED="${CHANGED}- ${msg}\n"
   fi
 done < <(git log "${RANGE}" --pretty=format:"%h %s" 2>/dev/null || git log --pretty=format:"%h %s")
 
 DATE=$(date +%Y-%m-%d)
 VERSION=$(git describe --tags --always 2>/dev/null || echo "unreleased")
 
 {
   echo "# Changelog"
   echo ""
   echo "## [${VERSION}] - ${DATE}"
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
 
 echo "Generated $OUTPUT successfully."
