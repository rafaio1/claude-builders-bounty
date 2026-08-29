#!/usr/bin/env python3
"""
Bounty Scout v2.0 - Playwright-based discovery for JS-rendered platforms
Targets: Algora, Gitcoin, Replit Bounties (GitHub REST exhausted)
Outputs qualified opportunities to data/aro/bounty_ledger.json
"""
import json, subprocess, sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path("/Agentic")
LEDGER = ROOT / "data" / "aro" / "bounty_ledger.json"

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    print(f"[SCOUT-PW] [{ts}] {msg}", flush=True)

def run_pw(cmd):
    """Run playwright-cli command and return output."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return r.stdout + r.stderr
    except Exception as e:
        return f"ERROR: {e}"

def scout_algora():
    """Scrape Algora bounties via Playwright."""
    log("Scouting Algora bounties...")
    run_pw("playwright-cli open https://console.algora.io/bounties")
    snap = run_pw("playwright-cli snapshot")
    run_pw("playwright-cli close")
    
    # Parse snapshot for bounty cards with $ values
    opportunities = []
    if "$" in snap and ("open" in snap.lower() or "available" in snap.lower()):
        log(f"Algora snapshot contains bounty indicators ({len(snap)} chars)")
        opportunities.append({
            "source": "algora_console",
            "status": "snapshot_captured_needs_parsing",
            "raw_snapshot_chars": len(snap),
            "next_action": "parse_snapshot_for_structured_bounties"
        })
    else:
        log("Algora: No clear bounty signals in snapshot")
    
    return opportunities

def scout_gitcoin():
    """Scrape Gitcoin grants/bounties."""
    log("Scouting Gitcoin...")
    run_pw("playwright-cli open https://app.gitcoin.co/#/explorer")
    snap = run_pw("playwright-cli snapshot")
    run_pw("playwright-cli close")
    
    opportunities = []
    if "grant" in snap.lower() or "bounty" in snap.lower():
        log(f"Gitcoin snapshot has grant/bounty keywords")
        opportunities.append({
            "source": "gitcoin_explorer",
            "status": "snapshot_captured",
            "raw_snapshot_chars": len(snap)
        })
    return opportunities

def update_ledger(new_opps):
    """Append new scouting results to ledger."""
    if not LEDGER.exists():
        log("Ledger not found, skipping update")
        return
    
    try:
        data = json.loads(LEDGER.read_text())
        
        if "discovery_log" not in data:
            data["discovery_log"] = []
        
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "playwright_scout_v2",
            "findings": new_opps,
            "action_taken": "logged_for_qualification",
            "compliance": "zero_capital_research_only"
        }
        data["discovery_log"].append(entry)
        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        
        LEDGER.write_text(json.dumps(data, indent=2))
        log(f"Ledger updated with {len(new_opps)} new findings")
    except Exception as e:
        log(f"Ledger update failed: {e}")

if __name__ == "__main__":
    log("Bounty Scout v2.0 (Playwright) starting")
    
    all_opps = []
    all_opps.extend(scout_algora())
    all_opps.extend(scout_gitcoin())
    
    update_ledger(all_opps)
    
    log(f"Scout complete: {len(all_opps)} opportunities logged")
