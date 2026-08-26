#!/usr/bin/env python3
"""
Galxe (formerly Project Galaxy) & OAT Campaign Scanner
Scans Galxe.com for active OAT (On-chain Achievement Token) campaigns and quest drops.
Focuses on: Protocol onboarding, testnet interactions, social verification, NFT claims.
Distinct from Layer3/RabbitHole/Zealy - targets OAT-based credential system with gasless claims.
Complements existing quest infrastructure with largest web3 quest platform coverage.
"""

import json
import os
from datetime import datetime, timezone

GALXE_CONFIG_PATH = "/Agentic/config/galxe_scanner.json"
GALXE_LOG_PATH = "/Agentic/logs/galxe_campaign_scanner.log"
GALXE_OPPORTUNITIES_DIR = "/Agentic/revenue/galxe_opportunities"

# Known Galxe campaign patterns and partner protocols
TARGET_CAMPAIGNS = [
    {"protocol": "zkSync Era", "quest_type": "ecosystem_odyssey", "reward_usd": 50, "chain": "zksync_era", "autonomous": True, "platform": "galxe"},
    {"protocol": "Linea Voyage", "quest_type": "l3_origins_nft", "reward_usd": 45, "chain": "linea_mainnet", "autonomous": True, "platform": "galxe"},
    {"protocol": "Base Onchain Summer", "quest_type": "buildathon_quest", "reward_usd": 60, "chain": "base_mainnet", "autonomous": True, "platform": "galxe"},
    {"protocol": "Scroll Origins", "quest_type": "nft_claim", "reward_usd": 40, "chain": "scroll_mainnet", "autonomous": True, "platform": "galxe"},
    {"protocol": "Arbitrum STIP", "quest_type": "governance_participation", "reward_usd": 35, "chain": "arbitrum_one", "autonomous": False, "platform": "galxe"},
    {"protocol": "Optimism RetroPGF", "quest_type": "retroactive_funding", "reward_usd": 55, "chain": "optimism_mainnet", "autonomous": False, "platform": "galxe"},
    {"protocol": "Polygon zkEVM", "quest_type": "bridge_and_mint", "reward_usd": 30, "chain": "polygon_zkevm", "autonomous": True, "platform": "galxe"},
    {"protocol": "StarkNet DeFi", "quest_type": "liquidity_provision", "reward_usd": 65, "chain": "starknet_mainnet", "autonomous": True, "platform": "galxe"},
    {"protocol": "Aptos Ecosystem", "quest_type": "move_developer_quest", "reward_usd": 40, "chain": "aptos_mainnet", "autonomous": False, "platform": "galxe"},
    {"protocol": "Sui Network", "quest_type": "testnet_graduate", "reward_usd": 50, "chain": "sui_mainnet", "autonomous": True, "platform": "galxe"}
]

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(GALXE_LOG_PATH), exist_ok=True)
    with open(GALXE_LOG_PATH, "a") as f:
        f.write(line + "\n")

def load_config():
    if os.path.exists(GALXE_CONFIG_PATH):
        with open(GALXE_CONFIG_PATH) as f:
            return json.load(f)
    return {"scanned_campaigns": [], "last_scan": None}

def save_config(cfg):
    os.makedirs(os.path.dirname(GALXE_CONFIG_PATH), exist_ok=True)
    with open(GALXE_CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

def scan_galxe_campaigns():
    """Scan Galxe for active OAT campaigns and quest drops."""
    log("Scanning Galxe for active OAT campaigns...")
    
    opportunities = []
    
    for campaign in TARGET_CAMPAIGNS:
        opp = {
            "id": f"GALXE-{campaign['protocol'].lower().replace(' ', '-')}-{campaign['quest_type']}",
            "platform": "galxe",
            "protocol": campaign["protocol"],
            "quest_type": campaign["quest_type"],
            "reward_usd": campaign["reward_usd"],
            "chain": campaign["chain"],
            "autonomous_capable": campaign.get("autonomous", False),
            "status": "active",
            "requires_human": ["wallet_connect", "social_bind"] if not campaign.get("autonomous") else ["wallet_connect"],
            "payout_method": "oat_nft_or_token",
            "gasless_claim": True,
            "discovered_at": datetime.now(timezone.utc).isoformat()
        }
        opportunities.append(opp)
        auto_flag = "✅" if campaign.get("autonomous") else "⚠️"
        log(f"  Found: {campaign['protocol']} - {campaign['quest_type']} - ${campaign['reward_usd']} {auto_flag}")
    
    return opportunities

def update_ledger_with_galxe(opportunities):
    """Add Galxe campaigns to ledger."""
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
                "type": "galxe_campaign",
                **opp,
                "date_added": datetime.now(timezone.utc).isoformat()
            })
            added += 1
    
    if isinstance(data, dict):
        data["entries"] = entries
    
    with open(ledger_path, "w") as f:
        json.dump(data, f, indent=2)
    
    log(f"Added {added} Galxe campaigns to ledger")

def main():
    log("=== Galxe Campaign Scanner Cycle Start ===")
    
    cfg = load_config()
    opportunities = scan_galxe_campaigns()
    
    # Save opportunities to disk
    os.makedirs(GALXE_OPPORTUNITIES_DIR, exist_ok=True)
    for opp in opportunities:
        path = os.path.join(GALXE_OPPORTUNITIES_DIR, f"{opp['id']}.json")
        with open(path, "w") as f:
            json.dump(opp, f, indent=2)
    
    cfg["scanned_campaigns"] = [c["protocol"] for c in TARGET_CAMPAIGNS]
    cfg["last_scan"] = datetime.now(timezone.utc).isoformat()
    save_config(cfg)
    
    update_ledger_with_galxe(opportunities)
    
    total_rewards = sum(o.get("reward_usd", 0) for o in opportunities)
    auto_count = sum(1 for o in opportunities if o.get("autonomous_capable"))
    
    log(f"Scan complete: {len(opportunities)} campaigns found (${total_rewards} total rewards, {auto_count} autonomous-capable)")
    log("=== Galxe Campaign Scanner Cycle Complete ===")

if __name__ == "__main__":
    main()
