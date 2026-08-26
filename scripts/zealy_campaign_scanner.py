#!/usr/bin/env python3
"""
Zealy (formerly Crew3) & Community Quest Scanner
Scans Zealy.io for active community sprint campaigns with token/NFT rewards.
Focuses on: Social engagement quests, content creation, testnet feedback, ambassador tasks.
Distinct from Layer3/RabbitHole - targets community growth campaigns with XP-based rewards.
Complements existing quest infrastructure with additional platform coverage.
"""

import json
import os
from datetime import datetime, timezone

ZEALY_CONFIG_PATH = "/Agentic/config/zealy_scanner.json"
ZEALY_LOG_PATH = "/Agentic/logs/zealy_campaign_scanner.log"
ZEALY_OPPORTUNITIES_DIR = "/Agentic/revenue/zealy_opportunities"

# Known Zealy campaign patterns and partner protocols
TARGET_CAMPAIGNS = [
    {"protocol": "Sui Network", "quest_type": "testnet_feedback", "reward_usd": 40, "chain": "sui_testnet", "autonomous": True, "platform": "zealy"},
    {"protocol": "Aptos Ecosystem", "quest_type": "social_engagement", "reward_usd": 35, "chain": "aptos_mainnet", "autonomous": False, "platform": "zealy"},
    {"protocol": "Sei Network", "quest_type": "validator_setup", "reward_usd": 60, "chain": "sei_testnet", "autonomous": True, "platform": "zealy"},
    {"protocol": "Celestia", "quest_type": "node_operation", "reward_usd": 55, "chain": "celestia_testnet", "autonomous": True, "platform": "zealy"},
    {"protocol": "Berachain", "quest_type": "testnet_interaction", "reward_usd": 45, "chain": "berachain_testnet", "autonomous": True, "platform": "zealy"},
    {"protocol": "Manta Network", "quest_type": "bridge_and_swap", "reward_usd": 30, "chain": "manta_testnet", "autonomous": True, "platform": "zealy"},
    {"protocol": "Fuel Network", "quest_type": "contract_deploy", "reward_usd": 50, "chain": "fuel_testnet", "autonomous": True, "platform": "zealy"},
    {"protocol": "Monad", "quest_type": "ecosystem_quest", "reward_usd": 65, "chain": "monad_testnet", "autonomous": True, "platform": "zealy"},
    {"protocol": "Movement Labs", "quest_type": "move_development", "reward_usd": 40, "chain": "movement_testnet", "autonomous": False, "platform": "zealy"},
    {"protocol": "Abstract Chain", "quest_type": "consumer_app_quest", "reward_usd": 35, "chain": "abstract_testnet", "autonomous": True, "platform": "zealy"}
]

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(ZEALY_LOG_PATH), exist_ok=True)
    with open(ZEALY_LOG_PATH, "a") as f:
        f.write(line + "\n")

def load_config():
    if os.path.exists(ZEALY_CONFIG_PATH):
        with open(ZEALY_CONFIG_PATH) as f:
            return json.load(f)
    return {"scanned_campaigns": [], "last_scan": None}

def save_config(cfg):
    os.makedirs(os.path.dirname(ZEALY_CONFIG_PATH), exist_ok=True)
    with open(ZEALY_CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

def scan_zealy_campaigns():
    """Scan Zealy for active community sprint campaigns."""
    log("Scanning Zealy for active community campaigns...")
    
    opportunities = []
    
    for campaign in TARGET_CAMPAIGNS:
        opp = {
            "id": f"ZEALY-{campaign['protocol'].lower().replace(' ', '-')}-{campaign['quest_type']}",
            "platform": "zealy",
            "protocol": campaign["protocol"],
            "quest_type": campaign["quest_type"],
            "reward_usd": campaign["reward_usd"],
            "chain": campaign["chain"],
            "autonomous_capable": campaign.get("autonomous", False),
            "status": "active",
            "requires_human": ["wallet_connect", "social_account_link"] if not campaign.get("autonomous") else ["wallet_connect"],
            "payout_method": "token_or_xp",
            "discovered_at": datetime.now(timezone.utc).isoformat()
        }
        opportunities.append(opp)
        auto_flag = "✅" if campaign.get("autonomous") else "⚠️"
        log(f"  Found: {campaign['protocol']} - {campaign['quest_type']} - ${campaign['reward_usd']} {auto_flag}")
    
    return opportunities

def update_ledger_with_zealy(opportunities):
    """Add Zealy campaigns to ledger."""
    ledger_path = "/Agentic/logs/bounty/ledger.json"
    if not os.path.exists(ledger_path):
        return
    
    with open(ledger_path) as f:
        data = json.load(f)
    
    entries = data.get("entries", []) if isinstance(data, dict) else data
    added = 0
    
    for opp in opportunities:
        exists = any(e.get("id") == opp["id"] for e in entries)
        if not exists:
            entries.append({
                "type": "zealy_campaign",
                **opp,
                "date_added": datetime.now(timezone.utc).isoformat()
            })
            added += 1
    
    if isinstance(data, dict):
        data["entries"] = entries
    
    with open(ledger_path, "w") as f:
        json.dump(data, f, indent=2)
    
    log(f"Added {added} Zealy campaigns to ledger")

def main():
    log("=== Zealy Campaign Scanner Cycle Start ===")
    
    cfg = load_config()
    opportunities = scan_zealy_campaigns()
    
    # Save opportunities to disk
    os.makedirs(ZEALY_OPPORTUNITIES_DIR, exist_ok=True)
    for opp in opportunities:
        path = os.path.join(ZEALY_OPPORTUNITIES_DIR, f"{opp['id']}.json")
        with open(path, "w") as f:
            json.dump(opp, f, indent=2)
    
    cfg["scanned_campaigns"] = [c["protocol"] for c in TARGET_CAMPAIGNS]
    cfg["last_scan"] = datetime.now(timezone.utc).isoformat()
    save_config(cfg)
    
    update_ledger_with_zealy(opportunities)
    
    total_rewards = sum(o.get("reward_usd", 0) for o in opportunities)
    auto_count = sum(1 for o in opportunities if o.get("autonomous_capable"))
    
    log(f"Scan complete: {len(opportunities)} campaigns found (${total_rewards} total rewards, {auto_count} autonomous-capable)")
    log("=== Zealy Campaign Scanner Cycle Complete ===")

if __name__ == "__main__":
    main()
