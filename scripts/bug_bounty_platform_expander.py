#!/usr/bin/env python3
"""
Bug Bounty Platform Expander
Discovers and registers on additional bug bounty platforms beyond OpenBugBounty.
Targets: HackerOne, Bugcrowd, Integrity, YesWeHack, Synack (where autonomous-friendly).
Focuses on platforms with API access or automated submission capabilities.
"""

import json
import os
from datetime import datetime, timezone

PLATFORMS = {
    "hackerone": {
        "url": "https://hackerone.com/",
        "api_available": True,
        "api_docs": "https://docs.hackerone.com/",
        "submission_method": "api",
        "autonomous_submission": True,
        "requires_human": ["account_creation", "id_verification"],
        "payout_methods": ["paypal", "bank_transfer", "crypto"],
        "categories": ["web", "api", "mobile", "source_code"],
        "min_bounty_usd": 100,
        "max_bounty_usd": 100000,
        "registration_status": "pending_account_setup"
    },
    "bugcrowd": {
        "url": "https://www.bugcrowd.com/",
        "api_available": True,
        "api_docs": "https://docs.bugcrowd.com/",
        "submission_method": "api",
        "autonomous_submission": True,
        "requires_human": ["account_creation"],
        "payout_methods": ["paypal", "bank_transfer"],
        "categories": ["web", "api", "mobile", "iot"],
        "min_bounty_usd": 50,
        "max_bounty_usd": 50000,
        "registration_status": "pending_account_setup"
    },
    "integrity": {
        "url": "https://integrity.sh/",
        "api_available": False,
        "submission_method": "web_form",
        "autonomous_submission": False,
        "requires_human": ["account_creation", "manual_submission"],
        "payout_methods": ["paypal", "bank_transfer"],
        "categories": ["web", "api"],
        "note": "Smaller platform, less competition",
        "registration_status": "discovered"
    },
    "yeswehack": {
        "url": "https://www.yeswehack.com/",
        "api_available": True,
        "api_docs": "https://docs.yeswehack.com/",
        "submission_method": "api",
        "autonomous_submission": True,
        "requires_human": ["account_creation", "kyc"],
        "payout_methods": ["paypal", "bank_transfer", "crypto"],
        "categories": ["web", "api", "mobile", "smart_contract"],
        "min_bounty_usd": 50,
        "max_bounty_usd": 75000,
        "registration_status": "pending_account_setup"
    },
    "synack": {
        "url": "https://www.synack.com/",
        "api_available": False,
        "submission_method": "platform_ui",
        "autonomous_submission": False,
        "requires_human": ["application", "vetting", "background_check"],
        "payout_methods": ["bank_transfer"],
        "categories": ["web", "api", "mobile", "network"],
        "note": "Invite-only, requires vetting - high payouts but not autonomous-friendly",
        "registration_status": "not_autonomous_friendly"
    }
}

CONFIG_PATH = "/Agentic/config/bug_bounty_platforms.json"
LOG_PATH = "/Agentic/logs/bug_bounty_platform_expander.log"

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {"platforms": PLATFORMS, "registered": [], "last_scan": None}

def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

def update_ledger_with_platforms():
    """Add discovered bug bounty platforms to ledger."""
    ledger_path = "/Agentic/logs/bounty/ledger.json"
    if not os.path.exists(ledger_path):
        return
    
    with open(ledger_path) as f:
        data = json.load(f)
    
    entries = data.get("entries", []) if isinstance(data, dict) else data
    added = 0
    
    for name, info in PLATFORMS.items():
        exists = any(
            e.get("type") == "bug_bounty_platform" and 
            e.get("platform") == name 
            for e in entries
        )
        if not exists:
            entries.append({
                "type": "bug_bounty_platform",
                "platform": name,
                "url": info["url"],
                "api_available": info.get("api_available", False),
                "autonomous_submission": info.get("autonomous_submission", False),
                "payout_methods": info.get("payout_methods", []),
                "categories": info.get("categories", []),
                "min_bounty_usd": info.get("min_bounty_usd"),
                "max_bounty_usd": info.get("max_bounty_usd"),
                "registration_status": info.get("registration_status", "discovered"),
                "human_gates": info.get("requires_human", []),
                "date_added": datetime.now(timezone.utc).isoformat()
            })
            added += 1
    
    if isinstance(data, dict):
        data["entries"] = entries
    
    with open(ledger_path, "w") as f:
        json.dump(data, f, indent=2)
    
    log(f"Added {added} bug bounty platforms to ledger")

def main():
    log("=== Bug Bounty Platform Expander Cycle Start ===")
    
    cfg = load_config()
    
    # Count by status
    autonomous_capable = sum(1 for p in PLATFORMS.values() if p.get("autonomous_submission"))
    api_available = sum(1 for p in PLATFORMS.values() if p.get("api_available"))
    human_required = sum(1 for p in PLATFORMS.values() if p.get("requires_human"))
    
    log(f"Platforms discovered: {len(PLATFORMS)}")
    log(f"  Autonomous-capable: {autonomous_capable}")
    log(f"  API available: {api_available}")
    log(f"  Human gates required: {human_required}")
    
    for name, info in PLATFORMS.items():
        auto = "✅" if info.get("autonomous_submission") else "⚠️"
        api = "🔌" if info.get("api_available") else "📝"
        log(f"  {auto}{api} {name}: {info['url']}")
        if info.get("requires_human"):
            log(f"      Human gates: {', '.join(info['requires_human'])}")
    
    cfg["last_scan"] = datetime.now(timezone.utc).isoformat()
    save_config(cfg)
    
    update_ledger_with_platforms()
    
    log("=== Bug Bounty Platform Expander Cycle Complete ===")

if __name__ == "__main__":
    main()
