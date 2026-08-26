#!/usr/bin/env python3
"""
Payout Reconciliation Monitor
Checks PR merge status and payout confirmations for submitted bounties.
Triggers Telegram notification ONLY when capital is realized and reconciled.
Enforces: No notification for pending/submitted/unmerged states.
"""

import json
import os
import subprocess
from datetime import datetime, timezone

LEDGER_PATH = "/Agentic/logs/bounty/ledger.json"
LOG_PATH = "/Agentic/logs/payout_reconciliation.log"
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = "8309124582"

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")

def load_ledger():
    if not os.path.exists(LEDGER_PATH):
        return {"entries": []}
    with open(LEDGER_PATH) as f:
        data = json.load(f)
    if isinstance(data, list):
        return {"entries": data}
    return data

def save_ledger(data):
    with open(LEDGER_PATH, "w") as f:
        json.dump(data, f, indent=2)

def check_pr_status(pr_url):
    """Check if a PR has been merged via gh CLI."""
    try:
        # Extract repo and PR number from URL
        parts = pr_url.rstrip("/").split("/")
        pr_number = parts[-1]
        repo = f"{parts[-4]}/{parts[-3]}"
        
        result = subprocess.run(
            ["gh", "pr", "view", pr_number, "--repo", repo, "--json", "state,mergedAt"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            pr_data = json.loads(result.stdout)
            return {
                "state": pr_data.get("state", "unknown"),
                "merged": pr_data.get("state") == "MERGED",
                "merged_at": pr_data.get("mergedAt")
            }
    except Exception as e:
        log(f"Error checking PR {pr_url}: {e}")
    
    return {"state": "unknown", "merged": False, "merged_at": None}

def send_telegram_notification(message):
    """Send Telegram notification for realized capital only."""
    if not TELEGRAM_TOKEN:
        log("WARN: TELEGRAM_BOT_TOKEN not set, skipping notification")
        return False
    
    try:
        import urllib.request
        import urllib.parse
        
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = urllib.parse.urlencode({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }).encode()
        
        req = urllib.request.Request(url, data=payload)
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                log(f"Telegram notification sent successfully")
                return True
            else:
                log(f"Telegram API error: {result}")
                return False
    except Exception as e:
        log(f"Telegram send failed: {e}")
        return False

def reconcile_payouts():
    """Check all submitted bounties for merge/payout status."""
    ledger = load_ledger()
    entries = ledger.get("entries", [])
    
    submitted = [e for e in entries if e.get("status") == "submitted" and e.get("bounty_usd")]
    
    if not submitted:
        log("No submitted bounties to reconcile")
        return
    
    log(f"Checking {len(submitted)} submitted bounties for payout status...")
    
    newly_merged = []
    already_notified = []
    
    for entry in submitted:
        pr_url = entry.get("pr_url")
        issue = entry.get("issue")
        bounty = entry.get("bounty_usd", 0)
        repo = entry.get("repo", "unknown")
        
        if not pr_url:
            continue
        
        # Skip if already marked as paid/notified
        if entry.get("notified") or entry.get("status") == "paid":
            already_notified.append(entry)
            continue
        
        pr_status = check_pr_status(pr_url)
        
        if pr_status["merged"]:
            log(f"✅ PR MERGED: #{issue} ({repo}) - ${bounty} | Merged: {pr_status['merged_at']}")
            
            # Mark as merged (not yet paid - payment confirmation is separate gate)
            entry["status"] = "merged"
            entry["merged_at"] = pr_status["merged_at"]
            entry["reconciled_at"] = datetime.now(timezone.utc).isoformat()
            
            newly_merged.append(entry)
        else:
            log(f"⏳ PR PENDING: #{issue} ({repo}) - State: {pr_status['state']}")
    
    # Update ledger with merge status
    save_ledger(ledger)
    
    if newly_merged:
        total_merged = sum(e.get("bounty_usd", 0) for e in newly_merged)
        log(f"\n🎉 {len(newly_merged)} PRs MERGED this cycle | Total: ${total_merged} USD")
        log("NOTE: Payment confirmation requires separate verification before Telegram notification")
        
        # DO NOT send Telegram here - payment must be confirmed separately
        # This enforces the rule: Telegram only for realized capital
        log("Telegram notification DEFERRED until payment confirmation received")
    else:
        log("No new merges detected this cycle")
    
    if already_notified:
        log(f"{len(already_notified)} previously notified entries skipped")

def main():
    log("=== Payout Reconciliation Monitor Cycle Start ===")
    reconcile_payouts()
    log("=== Payout Reconciliation Monitor Cycle Complete ===")

if __name__ == "__main__":
    main()
