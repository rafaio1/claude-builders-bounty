#!/usr/bin/env python3
"""
Revenue Orchestrator - Central coordinator for all autonomous revenue streams.
Integrates: bounties, vuln reports, DeFi platforms, OpenBugBounty.
Enforces: no Telegram for non-realized revenue, ledger reconciliation, cycle continuity.
"""

import json
import os
import sys
from datetime import datetime, timezone

LEDGER_PATH = "/Agentic/logs/bounty/ledger.json"
ORCHESTRATOR_LOG = "/Agentic/logs/revenue_orchestrator.log"
TELEGRAM_CONFIG = "/Agentic/config/telegram.json"

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(ORCHESTRATOR_LOG), exist_ok=True)
    with open(ORCHESTRATOR_LOG, "a") as f:
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

def get_platform_status():
    """Aggregate status across all revenue platforms."""
    ledger = load_ledger()
    entries = ledger.get("entries", [])
    
    platforms = {}
    for e in entries:
        ptype = e.get("type", "")
        platform = e.get("platform", "")
        
        if ptype == "platform_registration":
            platforms[platform] = {
                "status": e.get("status", "unknown"),
                "token_delivery": e.get("token_delivery", "unknown"),
                "registered": e.get("status") == "active"
            }
        elif ptype == "platform_discovery":
            if platform not in platforms:
                platforms[platform] = {
                    "status": "discovered",
                    "autonomous_friendly": e.get("autonomous_friendly", False),
                    "categories": e.get("categories", [])
                }
        elif ptype == "vuln_pipeline_status":
            platforms["vuln_pipeline"] = {
                "status": e.get("status", "unknown"),
                "autonomous_capable": e.get("autonomous_capable", []),
                "human_required": e.get("human_required", [])
            }
    
    return platforms

def get_bounty_summary():
    """Summarize bounty submission status."""
    ledger = load_ledger()
    entries = ledger.get("entries", [])
    
    submitted = [e for e in entries if e.get("status") == "submitted" and e.get("bounty_usd")]
    total_pending = sum(e.get("bounty_usd", 0) for e in submitted)
    
    repos = {}
    for e in submitted:
        repo = e.get("repo", "unknown")
        if repo not in repos:
            repos[repo] = {"count": 0, "total_usd": 0}
        repos[repo]["count"] += 1
        repos[repo]["total_usd"] += e.get("bounty_usd", 0)
    
    return {
        "total_submitted_prs": len(submitted),
        "total_pending_usd": total_pending,
        "by_repo": repos,
        "realized_usd": 0  # Only updated when payout confirmed
    }

def check_telegram_eligibility():
    """Check if any realized revenue qualifies for Telegram notification."""
    ledger = load_ledger()
    entries = ledger.get("entries", [])
    
    # Only notify on confirmed, reconciled capital
    eligible = [
        e for e in entries 
        if e.get("status") == "paid" 
        and e.get("reconciled") == True
        and e.get("notified") != True
    ]
    
    return eligible

def run_cycle():
    """Execute one orchestration cycle."""
    log("=== Revenue Orchestrator Cycle Start ===")
    
    # Step 1: Platform status aggregation
    platforms = get_platform_status()
    log(f"Platforms tracked: {len(platforms)}")
    for name, status in platforms.items():
        log(f"  {name}: {status.get('status', 'unknown')}")
    
    # Step 2: Bounty summary
    bounty_summary = get_bounty_summary()
    log(f"Bounties: {bounty_summary['total_submitted_prs']} PRs submitted, ${bounty_summary['total_pending_usd']} pending")
    for repo, info in bounty_summary["by_repo"].items():
        log(f"  {repo}: {info['count']} PRs, ${info['total_usd']}")
    
    # Step 3: Telegram eligibility check (no send - only realized revenue)
    eligible_notifications = check_telegram_eligibility()
    if eligible_notifications:
        log(f"ALERT: {len(eligible_notifications)} realized payments eligible for Telegram notification")
        for e in eligible_notifications:
            log(f"  -> ${e.get('bounty_usd', 0)} from {e.get('repo', e.get('platform', 'unknown'))}")
    else:
        log("No realized revenue eligible for Telegram (rule enforced)")
    
    # Step 4: Update orchestrator state in ledger
    ledger = load_ledger()
    entries = ledger.get("entries", [])
    
    orch_entry = {
        "type": "orchestrator_cycle",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "platforms_tracked": len(platforms),
        "bounties_pending_usd": bounty_summary["total_pending_usd"],
        "bounties_submitted_count": bounty_summary["total_submitted_prs"],
        "telegram_eligible_count": len(eligible_notifications),
        "status": "operational"
    }
    
    # Keep only last 10 orchestrator cycles
    existing_cycles = [e for e in entries if e.get("type") == "orchestrator_cycle"]
    other_entries = [e for e in entries if e.get("type") != "orchestrator_cycle"]
    
    recent_cycles = sorted(existing_cycles, key=lambda x: x.get("timestamp", ""), reverse=True)[:9]
    recent_cycles.insert(0, orch_entry)
    
    ledger["entries"] = other_entries + recent_cycles
    save_ledger(ledger)
    
    log(f"Cycle complete: {bounty_summary['total_pending_usd']} USD pending across {bounty_summary['total_submitted_prs']} submissions")
    log("=== Revenue Orchestrator Cycle Complete ===")
    
    return {
        "platforms": platforms,
        "bounty_summary": bounty_summary,
        "telegram_eligible": len(eligible_notifications)
    }

if __name__ == "__main__":
    result = run_cycle()
    print(json.dumps(result, indent=2))
