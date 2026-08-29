#!/usr/bin/env bash
# Claude Code pre-tool-use hook: blocks dangerous bash commands
# Acceptance: blocks rm -rf, DROP TABLE, git push --force, TRUNCATE, DELETE FROM without WHERE
set -euo pipefail

LOG_FILE="$HOME/.claude/hooks/blocked.log"
mkdir -p "$(dirname "$LOG_FILE")"

INPUT="$(cat)"
CMD="$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)"

if [ -z "$CMD" ]; then
  exit 0
fi

BLOCKED=0
REASON=""

if echo "$CMD" | grep -qiE '\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|(-[a-zA-Z]*f[a-zA-Z]*r))\b'; then
  BLOCKED=1; REASON="rm -rf is disabled by safety hook"
elif echo "$CMD" | grep -qiE '\bDROP\s+TABLE\b'; then
  BLOCKED=1; REASON="DROP TABLE is disabled by safety hook"
elif echo "$CMD" | grep -qiE '\bgit\s+push\s+.*--force\b'; then
  BLOCKED=1; REASON="git push --force is disabled by safety hook"
elif echo "$CMD" | grep -qiE '\bTRUNCATE\b'; then
  BLOCKED=1; REASON="TRUNCATE is disabled by safety hook"
elif echo "$CMD" | grep -qiE '\bDELETE\s+FROM\b' && ! echo "$CMD" | grep -qiE '\bWHERE\b'; then
  BLOCKED=1; REASON="DELETE FROM without WHERE is disabled by safety hook"
fi

if [ "$BLOCKED" -eq 1 ]; then
  TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  PWD_PATH="$(pwd)"
  printf '%s\t%s\t%s\t%s\n' "$TS" "$REASON" "$PWD_PATH" "$CMD" >> "$LOG_FILE"
  echo "{\"decision\":\"block\",\"reason\":\"$REASON\"}"
  exit 0
fi

exit 0
