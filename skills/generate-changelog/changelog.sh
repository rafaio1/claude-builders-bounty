 #!/usr/bin/env bash
 set -euo pipefail
 
 REPO_DIR="${1:-.}"
 cd "$REPO_DIR"
 
 # Find last tag; if none, use root commit
 LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
 if [ -n "$LAST_TAG" ]; then
   RANGE="$LAST_TAG..HEAD"
 else
   RANGE="HEAD"
 fi
 
 DATE=$(date +%Y-%m-%d)
 VERSION="${LAST_TAG:-Unreleased}"
 
 declare -A ADDED FIXED CHANGED REMOVED
 
 while IFS= read -r line; do
   msg=$(echo "$line" | sed 's/^[a-f0-9]* //')
   case "$msg" in
     feat:*|feat\(*) ADDED+=("$msg"$'\n') ;;
     fix:*|fix\(*) FIXED+=("$msg"$'\n') ;;
     revert:*|revert\(*) REMOVED+=("$msg"$'\n') ;;
     *) CHANGED+=("$msg"$'\n') ;;
   esac
 done < <(git log --pretty=format:"%h %s" $RANGE)
 
 OUTPUT="# Changelog\n\n## [$VERSION] - $DATE\n"
 
 if [ ${#ADDED[@]} -gt 0 ]; then
   OUTPUT+="\n### Added\n"
   while IFS= read -r item; do
     [ -n "$item" ] && OUTPUT+="- $item\n"
   done <<< "${ADDED[@]}"
 fi
 
 if [ ${#FIXED[@]} -gt 0 ]; then
   OUTPUT+="\n### Fixed\n"
   while IFS= read -r item; do
     [ -n "$item" ] && OUTPUT+="- $item\n"
   done <<< "${FIXED[@]}"
 fi
 
 if [ ${#CHANGED[@]} -gt 0 ]; then
   OUTPUT+="\n### Changed\n"
   while IFS= read -r item; do
     [ -n "$item" ] && OUTPUT+="- $item\n"
   done <<< "${CHANGED[@]}"
 fi
 
 if [ ${#REMOVED[@]} -gt 0 ]; then
   OUTPUT+="\n### Removed\n"
   while IFS= read -r item; do
     [ -n "$item" ] && OUTPUT+="- $item\n"
   done <<< "${REMOVED[@]}"
 fi
 
 echo -e "$OUTPUT" > CHANGELOG.md
 cat CHANGELOG.md
