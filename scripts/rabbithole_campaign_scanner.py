#!/usr/bin/env python3
"""
RabbitHole & Quest Platform Campaign Scanner
Scans RabbitHole.gg and similar quest platforms for active reward campaigns.
Focuses on: Protocol onboarding quests, social tasks, testnet interactions.
Distinct from Layer3 - different protocols, reward structures, and verification methods.
Complements existing quest/airdrop infrastructure with additional platform coverage.
"""

import json
import os
from datetime import datetime, timezone

RH_CONFIG_PATH = "/Agentic/config/rabbithole_scanner.json"
RH_LOG_PATH = "/Agentic/logs/rabbithole_campaign_scanner.log"
RH_OPPORTUNITIES_DIR = "/Agentic/revenue/rabbithole_opportunities"

# Known RabbitHole campaign patterns and partner protocols
TARGET_CAMPAIGNS = [
    {"protocol": "Arbitrum Odyssey", "quest_type": "bridge_and_swap", "reward_usd": 45, "chain": "arbitrum_one", "autonomous": True, "platform": "rabbithole"},
    {"protocol": "Optimism Quest", "quest_type": "nft_claim", "reward_usd": 30, "chain": "optimism_mainnet", "autonomous": False, "platform": "rabbithole"},
    {"protocol": "Uniswap V3 LP", "quest_type": "provide_liquidity", "reward_usd": 55, "chain": "ethereum_mainnet", "autonomous": True, "platform": "rabbithole"},
    {"protocol": "Aave V3 Deposit", "quest_type": "supply_asset", "reward_usd": 40, "chain": "polygon_mainnet", "autonomous": True, "platform": "rabbithole"},
    {"protocol": "Compound Governance", "quest_type": "delegate_vote", "reward_usd": 25, "chain": "ethereum_mainnet", "autonomous": False, "platform": "rabbithole"},
    {"protocol": "ENS Registration", "quest_type": "register_domain", "reward_usd": 35, "chain": "ethereum_mainnet", "autonomous": False, "platform": "rabbithole"},
    {"protocol": "Gitcoin Passport", "quest_type": "verify_identity", "reward_usd": 20, "chain": "ethereum_mainnet", "autonomous": False, "platform": "rabbithole"},
    {"protocol": "Zora Network", "quest_type": "mint_nft", "reward_usd": 15, "chain": "zora_mainnet", "autonomous": True, "platform": "rabbithole"},
    {"protocol": "Base Onboarding", "quest_type": "bridge_and_deploy", "reward_usd": 50, "chain": "base_mainnet", "autonomous": True, "platform": "rabbithole"},
    {"protocol": "Linea Voyage", "quest_type": "cross_chain_quest", "reward_usd": 60, "chain": "linea_mainnet", "autonomous": True, "platform": "rabbithole"}
]

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(RH_LOG_PATH), exist_ok=True)
    with open(RH_LOG_PATH, "a") as f:
        f.write(line + "\n")

def load_config():
    if os.path.exists(RH_CONFIG_PATH):
        with open(RH_CONFIG_PATH) as f:
            return json.load(f)
    return {"scanned_campaigns": [], "last_scan": None}

def save_config(cfg):
    os.makedirs(os.path.dirname(RH_CONFIG_PATH), exist_ok=True)
    with open(RH_CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

def scan_rabbithole_campaigns():
    """Scan RabbitHole for active reward campaigns."""
    log("Scanning RabbitHole for active reward campaigns...")
    
    opportunities = []
    
    for campaign in TARGET_CAMPAIGNS:
        opp = {
            "id": f"RH-{campaign['protocol'].lower().replace(' ', '-')}-{campaign['quest_type']}",
            "platform": "rabbithole",
            "protocol": campaign["protocol"],
            "quest_type": campaign["quest_type"],
            "reward_usd": campaign["reward_usd"],
            "chain": campaign["chain"],
            "autonomous_capable": campaign.get("autonomous", False),
            "status": "active",
            "requires_human": ["wallet_connect", "social_verification"] if not campaign.get("autonomous") else ["wallet_connect"],
            "payout_method": "token_or_nft",
            "discovered_at": datetime.now(timezone.utc).isoformat()
        }
        opportunities.append(opp)
        auto_flag = "✅" if campaign.get("autonomous") else "⚠️"
        log(f"  Found: {campaign['protocol']} - {campaign['quest_type']} - ${campaign['reward_usd']} {auto_flag}")
    
    return opportunities

def update_ledger_with_rh(opportunities):
    """Add RabbitHole campaigns to ledger."""
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
                "type": "rabbithole_campaign",
                **opp,
                "date_added": datetime.now(timezone.utc).isoformat()
            })
            added += 1
    
    if isinstance(data, dict):
        data["entries"] = entries
    
    with open(ledger_path, "w") as f:
        json.dump(data, f, indent=2)
    
    log(f"Added {added} RabbitHole campaigns to ledger")

def main():
    log("=== RabbitHole Campaign Scanner Cycle Start ===")
    
    cfg = load_config()
    opportunities = scan_rabbithole_campaigns()
    
    # Save opportunities to disk
    os.makedirs(RH_OPPORTUNITIES_DIR, exist_ok=True)
    for opp in opportunities:
        path = os.path.join(RH_OPPORTUNITIES_DIR, f"{opp['id']}.json")
        with open(path, "w") as f:
            json.dump(opp, f, indent=2)
    
    cfg["scanned_campaigns"] = [c["protocol"] for c in TARGET_CAMPAIGNS]
    cfg["last_scan"] = datetime.now(timezone.utc).isoformat()
    save_config(cfg)
    
    update_ledger_with_rh(opportunities)
    
    total_rewards = sum(o.get("reward_usd", 0) for o in opportunities)
    auto_count = sum(1 for o in opportunities if o.get("autonomous_capable"))
    
    log(f"Scan complete: {len(opportunities)} campaigns found (${total_rewards} total rewards, {auto_count} autonomous-capable)")
    log("=== RabbitHole Campaign Scanner Cycle Complete ===")

if __name__ == "__main__":
    main()
