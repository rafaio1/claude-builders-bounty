#!/bin/bash
# ContábilHub Lead Monitor - Checks for new comments on outreach issues
set -e

TRACKER="state/contabilhub_outreach_tracker.json"
LOG="logs/contabilhub_monitor.log"
mkdir -p logs

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting monitor cycle..." >> "$LOG"

# Extract repos and issue numbers from tracker
jq -r '.leads[] | select(.status == "contacted") | "\(.repo) \(.issue)"' "$TRACKER" | while read repo issue; do
  comments=$(gh issue view "$issue" --repo "$repo" --json comments --jq '.comments | length' 2>/dev/null || echo "0")
  if [ "$comments" -gt "0" ]; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ALERT: $repo#$issue has $comments comment(s)" >> "$LOG"
    # Update tracker status to 'responded'
    jq --arg repo "$repo" --argjson issue "$issue" '
      (.leads[] | select(.repo == $repo and .issue == $issue)).status = "responded"
    ' "$TRACKER" > "${TRACKER}.tmp" && mv "${TRACKER}.tmp" "$TRACKER"
  fi
done

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Cycle complete." >> "$LOG"
