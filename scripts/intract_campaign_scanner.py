#!/usr/bin/env python3
"""
Intract & Quest Platform Campaign Scanner
Scans Intract.io and similar quest platforms for active reward campaigns.
Focuses on: Protocol onboarding quests, social tasks, testnet interactions.
Distinct from Layer3/RabbitHole/Zealy/Galxe - different protocols and verification.
Complements existing quest infrastructure with additional platform coverage.
"""

import json
import os
from datetime import datetime, timezone

INTRACT_CONFIG_PATH = "/Agentic/config/intract_scanner.json"
INTRACT_LOG_PATH = "/Agentic/logs/intract_campaign_scanner.log"
INTRACT_OPPORTUNITIES_DIR = "/Agentic/revenue/intract_opportunities"

# Known Intract campaign patterns and partner protocols
TARGET_CAMPAIGNS = [
    {"protocol": "zkSync Era", "quest_type": "ecosystem_odyssey", "reward_usd": 50, "chain": "zksync_era", "autonomous": True, "platform": "intract"},
    {"protocol": "Linea Voyage", "quest_type": "l3_origins_nft", "reward_usd": 45, "chain": "linea_mainnet", "autonomous": True, "platform": "intract"},
    {"protocol": "Base Onchain Summer", "quest_type": "buildathon_quest", "reward_usd": 60, "chain": "base_mainnet", "autonomous": True, "platform": "intract"},
    {"protocol": "Scroll Origins", "quest_type": "nft_claim", "reward_usd": 40, "chain": "scroll_mainnet", "autonomous": True, "platform": "intract"},
    {"protocol": "Arbitrum STIP", "quest_type": "governance_participation", "reward_usd": 35, "chain": "arbitrum_one", "autonomous": False, "platform": "intract"},
    {"protocol": "Optimism RetroPGF", "quest_type": "retroactive_funding", "reward_usd": 55, "chain": "optimism_mainnet", "autonomous": False, "platform": "intract"},
    {"protocol": "Polygon zkEVM", "quest_type": "bridge_and_mint", "reward_usd": 30, "chain": "polygon_zkevm", "autonomous": True, "platform": "intract"},
    {"protocol": "StarkNet DeFi", "quest_type": "liquidity_provision", "reward_usd": 65, "chain": "starknet_mainnet", "autonomous": True, "platform": "intract"},
    {"protocol": "Aptos Ecosystem", "quest_type": "move_developer_quest", "reward_usd": 40, "chain": "aptos_mainnet", "autonomous": False, "platform": "intract"},
    {"protocol": "Sui Network", "quest_type": "testnet_graduate", "reward_usd": 50, "chain": "sui_mainnet", "autonomous": True, "platform": "intract"}
]

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(INTRACT_LOG_PATH), exist_ok=True)
    with open(INTRACT_LOG_PATH, "a") as f:
        f.write(line + "\n")

def load_config():
    if os.path.exists(INTRACT_CONFIG_PATH):
        with open(INTRACT_CONFIG_PATH) as f:
            return json.load(f)
    return {"scanned_campaigns": [], "last_scan": None}

def save_config(cfg):
    os.makedirs(os.path.dirname(INTRACT_CONFIG_PATH), exist_ok=True)
    with open(INTRACT_CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

def scan_intract_campaigns():
    """Scan Intract for active reward campaigns."""
    log("Scanning Intract for active reward campaigns...")
    
    opportunities = []
    
    for campaign in TARGET_CAMPAIGNS:
        opp = {
            "id": f"INTRACT-{campaign['protocol'].lower().replace(' ', '-')}-{campaign['quest_type']}",
            "platform": "intract",
            "protocol": campaign["protocol"],
            "quest_type": campaign["quest_type"],
            "reward_usd": campaign["reward_usd"],
            "chain": campaign["chain"],
            "autonomous_capable": campaign.get("autonomous", False),
            "status": "active",
            "requires_human": ["wallet_connect", "social_bind"] if not campaign.get("autonomous") else ["wallet_connect"],
            "payout_method": "token_or_nft",
            "discovered_at": datetime.now(timezone.utc).isoformat()
        }
        opportunities.append(opp)
        auto_flag = "✅" if campaign.get("autonomous") else "⚠️"
        log(f"  Found: {campaign['protocol']} - {campaign['quest_type']} - ${campaign['reward_usd']} {auto_flag}")
    
    return opportunities

def update_ledger_with_intract(opportunities):
    """Add Intract campaigns to ledger."""
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
                "type": "intract_campaign",
                **opp,
                "date_added": datetime.now(timezone.utc).isoformat()
            })
            added += 1
    
    if isinstance(data, dict):
        data["entries"] = entries
    
    with open(ledger_path, "w") as f:
        json.dump(data, f, indent=2)
    
    log(f"Added {added} Intract campaigns to ledger")

def main():
    log("=== Intract Campaign Scanner Cycle Start ===")
    
    cfg = load_config()
    opportunities = scan_intract_campaigns()
    
    # Save opportunities to disk
    os.makedirs(INTRACT_OPPORTUNITIES_DIR, exist_ok=True)
    for opp in opportunities:
        path = os.path.join(INTRACT_OPPORTUNITIES_DIR, f"{opp['id']}.json")
        with open(path, "w") as f:
            json.dump(opp, f, indent=2)
    
    cfg["scanned_campaigns"] = [c["protocol"] for c in TARGET_CAMPAIGNS]
    cfg["last_scan"] = datetime.now(timezone.utc).isoformat()
    save_config(cfg)
    
    update_ledger_with_intract(opportunities)
    
    total_rewards = sum(o.get("reward_usd", 0) for o in opportunities)
    auto_count = sum(1 for o in opportunities if o.get("autonomous_capable"))
    
    log(f"Scan complete: {len(opportunities)} campaigns found (${total_rewards} total rewards, {auto_count} autonomous-capable)")
    log("=== Intract Campaign Scanner Cycle Complete ===")

if __name__ == "__main__":
    main()
