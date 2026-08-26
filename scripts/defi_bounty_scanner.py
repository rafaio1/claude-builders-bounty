#!/usr/bin/env python3
"""
DeFi & Web3 Bounty Scanner
Scans DeFi protocols, DAOs, and web3 platforms for autonomous bounty opportunities.
Focuses on: smart contract audits, documentation, testing, governance tasks.
"""

import json
import os
import sys
from datetime import datetime, timezone

DEFI_PLATFORMS = {
    "gitcoin": {
        "url": "https://gitcoin.co/grants",
        "type": "grants",
        "autonomous_friendly": True,
        "payout": "crypto",
        "categories": ["defi", "dao", "infrastructure"]
    },
    "dework": {
        "url": "https://app.dework.xyz",
        "type": "bounties",
        "autonomous_friendly": True,
        "payout": "crypto",
        "categories": ["governance", "documentation", "development"]
    },
    "layer3": {
        "url": "https://layer3.xyz/bounties",
        "type": "bounties",
        "autonomous_friendly": True,
        "payout": "crypto",
        "categories": ["smart-contract", "testing", "audit"]
    },
    "immunefi": {
        "url": "https://immunefi.com/bounties",
        "type": "bug-bounty",
        "autonomous_friendly": False,
        "payout": "crypto",
        "categories": ["security", "smart-contract"],
        "note": "Requires manual submission but high payouts"
    },
    "code4rena": {
        "url": "https://code4rena.com",
        "type": "audit-contest",
        "autonomous_friendly": True,
        "payout": "crypto",
        "categories": ["smart-contract-audit"]
    }
}

CONFIG_PATH = "/Agentic/config/defi_platforms.json"
LOG_PATH = "/Agentic/logs/defi_bounty_scanner.log"

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {"platforms": DEFI_PLATFORMS, "scanned_programs": [], "last_scan": None}

def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

def scan_platform(platform_name, platform_info):
    """Scan a single platform for new bounties."""
    log(f"Scanning {platform_name}: {platform_info['url']}")
    
    # Document scan parameters for autonomous execution
    scan_params = {
        "platform": platform_name,
        "url": platform_info["url"],
        "autonomous_friendly": platform_info.get("autonomous_friendly", False),
        "payout_method": platform_info["payout"],
        "target_categories": platform_info["categories"],
        "scan_timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "ready_for_automation" if platform_info.get("autonomous_friendly") else "requires_review"
    }
    
    return scan_params

def update_ledger_with_platforms():
    """Add discovered platforms to bounty ledger for tracking."""
    ledger_path = "/Agentic/logs/bounty/ledger.json"
    if not os.path.exists(ledger_path):
        log("Ledger not found, skipping platform registration")
        return
    
    with open(ledger_path) as f:
        data = json.load(f)
    
    entries = data.get("entries", []) if isinstance(data, dict) else data
    
    added = 0
    for name, info in DEFI_PLATFORMS.items():
        exists = any(
            e.get("type") == "platform_discovery" and 
            e.get("platform") == name 
            for e in entries
        )
        if not exists:
            entries.append({
                "type": "platform_discovery",
                "platform": name,
                "url": info["url"],
                "autonomous_friendly": info.get("autonomous_friendly", False),
                "payout_method": info["payout"],
                "categories": info["categories"],
                "status": "discovered",
                "date_added": datetime.now(timezone.utc).isoformat()
            })
            added += 1
    
    if isinstance(data, dict):
        data["entries"] = entries
    else:
        data = entries
    
    with open(ledger_path, "w") as f:
        json.dump(data, f, indent=2)
    
    log(f"Added {added} new DeFi platforms to ledger")

def main():
    log("=== DeFi Bounty Scanner Cycle Start ===")
    
    cfg = load_config()
    scan_results = []
    
    for name, info in DEFI_PLATFORMS.items():
        result = scan_platform(name, info)
        scan_results.append(result)
    
    cfg["last_scan"] = datetime.now(timezone.utc).isoformat()
    cfg["scan_results"] = scan_results
    save_config(cfg)
    
    update_ledger_with_platforms()
    
    autonomous_count = sum(1 for r in scan_results if r["autonomous_friendly"])
    log(f"Scan complete: {len(scan_results)} platforms, {autonomous_count} autonomous-friendly")
    log("=== DeFi Bounty Scanner Cycle Complete ===")

if __name__ == "__main__":
    main()
