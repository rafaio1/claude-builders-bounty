#!/bin/bash
# Extract public emails from GitHub profiles for contacted leads
set -e

TRACKER="state/contabilhub_outreach_tracker.json"
OUT="state/contabilhub_lead_emails.json"
LOG="logs/contabilhub_enrich.log"
mkdir -p logs

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting email enrichment..." >> "$LOG"

jq -r '.leads[] | select(.status == "contacted") | .repo' "$TRACKER" | sort -u | while read repo; do
  owner=$(echo "$repo" | cut -d'/' -f1)
  # Check if we already have an email for this owner
  existing=$(jq -r --arg o "$owner" '.[$o] // empty' "$OUT" 2>/dev/null || echo "")
  if [ -n "$existing" ]; then
    continue
  fi
  
  # Try to get email from GitHub profile (public only)
  email=$(gh api "users/$owner" --jq '.email // empty' 2>/dev/null || echo "")
  
  if [ -n "$email" ] && [ "$email" != "null" ]; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] FOUND: $owner -> $email" >> "$LOG"
    # Update JSON file atomically
    tmp=$(mktemp)
    jq --arg o "$owner" --arg e "$email" '.[$o] = $e' "${OUT:-/dev/null}" 2>/dev/null > "$tmp" && mv "$tmp" "$OUT" || echo "{\"$owner\":\"$email\"}" > "$OUT"
  else
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] NO_PUBLIC_EMAIL: $owner" >> "$LOG"
  fi
  
  # Rate limit courtesy: 1s between profile lookups
  sleep 1
done

total=$(jq 'keys | length' "$OUT" 2>/dev/null || echo "0")
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Enrichment complete. Emails found: $total" >> "$LOG"
echo "Enrichment done. Total emails: $total"
