#!/usr/bin/env bash
# Claude Code pre-tool-use hook: blocks destructive bash commands
# Logs to ~/.claude/hooks/blocked.log and prints explanation to stderr

LOG_DIR="$HOME/.claude/hooks"
LOG_FILE="$LOG_DIR/blocked.log"
mkdir -p "$LOG_DIR"

# Read JSON input from stdin
INPUT=$(cat)

# Extract command from tool_input.command (Bash tool) or similar fields
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // .tool_input.cmd // empty' 2>/dev/null)

if [ -z "$CMD" ]; then
  exit 0
fi

BLOCKED=0
REASON=""

# Check patterns (case-insensitive where appropriate)
if echo "$CMD" | grep -qiE '\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|(-[a-zA-Z]*f[a-zA-Z]*r))\b'; then
  BLOCKED=1
  REASON="rm -rf detected: recursive force delete is blocked by safety hook"
elif echo "$CMD" | grep -qiE '\bDROP\s+TABLE\b'; then
  BLOCKED=1
  REASON="DROP TABLE detected: destructive SQL DDL is blocked by safety hook"
elif echo "$CMD" | grep -qiE '\bgit\s+push\s+.*--force\b|\bgit\s+push\s+-f\b'; then
  BLOCKED=1
  REASON="git push --force detected: force-push is blocked by safety hook"
elif echo "$CMD" | grep -qiE '\bTRUNCATE\b'; then
  BLOCKED=1
  REASON="TRUNCATE detected: destructive table truncation is blocked by safety hook"
elif echo "$CMD" | grep -qiE '\bDELETE\s+FROM\b' && ! echo "$CMD" | grep -qiE '\bWHERE\b'; then
  BLOCKED=1
  REASON="DELETE FROM without WHERE detected: unbounded delete is blocked by safety hook"
fi

if [ "$BLOCKED" -eq 1 ]; then
  TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  PROJECT_PATH="${CLAUDE_PROJECT_PATH:-$(pwd)}"
  echo "$TIMESTAMP | $PROJECT_PATH | $CMD | $REASON" >> "$LOG_FILE"
  echo "⛔ BLOCKED: $REASON" >&2
  echo "Command logged to $LOG_FILE" >&2
  # Exit with non-zero to block execution; print JSON decision for Claude
  printf '{"decision":"block","reason":"%s"}\n' "$REASON"
  exit 1
fi

exit 0
