 #!/usr/bin/env bash
 set -euo pipefail
 
 REPO_DIR="${1:-.}"
 cd "$REPO_DIR"
 
 LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
 if [ -n "$LAST_TAG" ]; then
   RANGE="$LAST_TAG..HEAD"
 else
   RANGE="HEAD"
 fi
 
 DATE=$(date +%Y-%m-%d)
 VERSION="${LAST_TAG:-Unreleased}"
 
 ADDED=""
 FIXED=""
 CHANGED=""
 REMOVED=""
 
 while IFS= read -r line; do
   msg=$(echo "$line" | sed 's/^[a-f0-9]* //')
   case "$msg" in
     feat:*|feat\(*) ADDED+="- $msg"$'\n' ;;
     fix:*|fix\(*) FIXED+="- $msg"$'\n' ;;
     revert:*|revert\(*) REMOVED+="- $msg"$'\n' ;;
     *) CHANGED+="- $msg"$'\n' ;;
   esac
 done < <(git log --pretty=format:"%h %s" $RANGE)
 
 {
   echo "# Changelog"
   echo ""
   echo "## [$VERSION] - $DATE"
   if [ -n "$ADDED" ]; then
     echo ""
     echo "### Added"
     printf "%s" "$ADDED"
   fi
   if [ -n "$FIXED" ]; then
     echo ""
     echo "### Fixed"
     printf "%s" "$FIXED"
   fi
   if [ -n "$CHANGED" ]; then
     echo ""
     echo "### Changed"
     printf "%s" "$CHANGED"
   fi
   if [ -n "$REMOVED" ]; then
     echo ""
     echo "### Removed"
     printf "%s" "$REMOVED"
   fi
 } > CHANGELOG.md
 
 cat CHANGELOG.md
