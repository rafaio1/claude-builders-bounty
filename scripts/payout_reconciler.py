#!/usr/bin/env python3
"""
Payout Reconciler v1.0 - Closes the Revenue Loop
Monitors merged PRs and freelance deliverables, verifies payment receipt,
and triggers Wise balance updates. Focus on FAST payout verification.
"""
import os, sys, json, time, subprocess, requests
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path("/Agentic")
LOG_FILE = ROOT / "logs" / "payout_reconciler.log"
LEDGER = ROOT / "data" / "aro" / "bounty_ledger.json"
WISE_STATE = ROOT / "data" / "aro" / "wise-state.json"

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[PAY] [{ts}] {msg}"
    print(line, flush=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def get_wise_balance():
    """Fetch current Wise USD/BRL balance"""
    api_key = os.getenv("WISE_API_KEY")
    profile_id = os.getenv("WISE_PROFILE_ID", "87614939")
    if not api_key:
        return None
    try:
        r = requests.get(
            f"https://api.wise.com/v4/profiles/{profile_id}/balances?types=STANDARD",
            headers={"Authorization": f"Bearer {api_key}"}, timeout=15
        )
        if r.status_code == 200:
            bals = r.json()
            usd = next((b for b in bals if b.get("currency") == "USD"), None)
            brl = next((b for b in bals if b.get("currency") == "BRL"), None)
            return {
                "USD": float(usd["amount"]["value"]) if usd else 0.0,
                "BRL": float(brl["amount"]["value"]) if brl else 0.0,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
    except Exception as e:
        log(f"Wise API error: {e}")
    return None

def check_merged_prs():
    """Check for recently merged bounty PRs that should have triggered payment"""
    try:
        cmd = ["gh", "search", "prs", "--merged-at=>2026-08-25", 
               "--author=rafaio1", "--json=repository,title,url,mergedAt"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode == 0:
            return json.loads(res.stdout)
    except Exception as e:
        log(f"PR search error: {e}")
    return []

def reconcile():
    """Main reconciliation cycle"""
    log("Starting payout reconciliation cycle")
    
    # 1. Get current Wise balance
    balance = get_wise_balance()
    if balance:
        log(f"Wise Balance: USD={balance['USD']:.2f} | BRL={balance['BRL']:.2f}")
        # Save state for delta tracking
        WISE_STATE.write_text(json.dumps(balance, indent=2))
    else:
        log("WARNING: Could not fetch Wise balance")
        
    # 2. Check for merged PRs awaiting payment confirmation
    merged = check_merged_prs()
    log(f"Found {len(merged)} recently merged PRs")
    
    # 3. Cross-reference with ledger to identify unpaid items
    ledger_data = {}
    if LEDGER.exists():
        try:
            ledger_data = json.loads(LEDGER.read_text())
        except: pass
    
    entries = ledger_data.get("entries", []) if isinstance(ledger_data, dict) else []
    unpaid = [e for e in entries if e.get("status") == "merged" and not e.get("paid")]
    
    if unpaid:
        log(f"⚠️  {len(unpaid)} MERGED but UNPAID bounties detected:")
        for u in unpaid[:5]:
            log(f"   - {u.get('repo', '?')}: {u.get('title', '?')} ({u.get('pr_url', '?')})")
    else:
        log("✅ All merged bounties marked as paid or no pending items")
        
    # 4. Generate revenue report
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "wise_balance": balance,
        "merged_prs_count": len(merged),
        "unpaid_bounties": len(unpaid),
        "action_required": len(unpaid) > 0
    }
    
    report_path = ROOT / "data" / "orchestrator" / "revenue_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))
    
    log("Reconciliation cycle complete")

if __name__ == "__main__":
    log("Payout Reconciler v1.0 starting")
    while True:
        try:
            reconcile()
            time.sleep(1800)  # Every 30 minutes
        except KeyboardInterrupt:
            break
        except Exception as e:
            log(f"Fatal: {e}")
            time.sleep(300)
