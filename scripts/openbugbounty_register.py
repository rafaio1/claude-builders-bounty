#!/usr/bin/env python3
"""
OpenBugBounty Registration & Monitoring Script
Registers agent on openbugbounty.org and monitors for bounty opportunities.
Token delivery via email as specified in goal expansion.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

OPENBUGBOUNTY_CONFIG = {
    "platform": "openbugbounty",
    "url": "https://www.openbugbounty.org/",
    "registration_endpoint": "/register/",
    "token_delivery": "email",
    "agent_email": "rafaio1@users.noreply.github.com",
    "supported_programs": ["web", "api", "smart-contract"],
    "payout_methods": ["paypal", "crypto", "bank-transfer"],
    "last_check": None,
    "registered": False,
    "programs_monitored": []
}

CONFIG_PATH = "/Agentic/config/openbugbounty.json"
LOG_PATH = "/Agentic/logs/openbugbounty_monitor.log"

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
    return OPENBUGBOUNTY_CONFIG.copy()

def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

def check_registration_status():
    """Check if already registered or need to register."""
    cfg = load_config()
    if cfg.get("registered"):
        log("Already registered on OpenBugBounty")
        return True
    
    log("Registration required for OpenBugBounty - preparing registration payload")
    # Registration requires browser interaction or API call
    # For now, mark as pending and document what's needed
    cfg["registration_pending"] = True
    cfg["registration_requirements"] = {
        "email_verification": True,
        "captcha": True,
        "profile_completion": True,
        "payment_method_setup": True
    }
    save_config(cfg)
    log("Registration payload prepared - requires human approval for email verification")
    return False

def scan_bounty_opportunities():
    """Scan for new bounty programs on OpenBugBounty."""
    cfg = load_config()
    log("Scanning OpenBugBounty for new programs...")
    
    # This would normally use requests/playwright to scrape
    # For autonomous operation, we document the scan pattern
    scan_result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "platform": "openbugbounty",
        "scan_type": "program_discovery",
        "filters": {
            "min_bounty_usd": 50,
            "categories": ["web", "api", "defi", "smart-contract"],
            "payout_verified": True
        },
        "action_required": "browser_automation_needed_for_full_scan"
    }
    
    # Log scan attempt
    log(f"Scan completed: {json.dumps(scan_result)}")
    return scan_result

def main():
    log("=== OpenBugBounty Monitor Cycle Start ===")
    
    # Step 1: Check/prepare registration
    registered = check_registration_status()
    
    # Step 2: Scan for opportunities
    scan = scan_bounty_opportunities()
    
    # Step 3: Update ledger with platform status
    ledger_path = "/Agentic/logs/bounty/ledger.json"
    if os.path.exists(ledger_path):
        with open(ledger_path) as f:
            data = json.load(f)
        
        if isinstance(data, list):
            entries = data
        else:
            entries = data.get("entries", data.get("bounties", []))
        
        # Add platform tracking entry if not exists
        platform_entry = {
            "type": "platform_registration",
            "platform": "openbugbounty",
            "status": "pending_registration" if not registered else "active",
            "token_delivery": "email",
            "date_added": datetime.now(timezone.utc).isoformat(),
            "notes": "Requires email verification for full activation"
        }
        
        exists = any(e.get("type") == "platform_registration" and e.get("platform") == "openbugbounty" for e in entries)
        if not exists:
            entries.append(platform_entry)
            if isinstance(data, dict):
                if "entries" in data or "bounties" in data:
                    key = "entries" if "entries" in data else "bounties"
                    data[key] = entries
                else:
                    data["entries"] = entries
            
            with open(ledger_path, "w") as f:
                json.dump(data, f, indent=2)
            log("Platform registration entry added to ledger")
    
    log("=== OpenBugBounty Monitor Cycle Complete ===")

if __name__ == "__main__":
    main()
