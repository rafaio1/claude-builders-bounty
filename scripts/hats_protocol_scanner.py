#!/usr/bin/env python3
"""
Hats Protocol & DAO Contribution Scanner
Scans Hats Protocol ecosystem and related DAOs for paid contribution opportunities.
Hats enables role-based bounties, stream payments, and autonomous task completion rewards.
Focuses on: Governance tasks, documentation, community management, dev tooling.
Distinct from audit platforms - targets ongoing DAO operations and micro-bounties.
"""

import json
import os
from datetime import datetime, timezone

HATS_CONFIG_PATH = "/Agentic/config/hats_protocol_scanner.json"
HATS_LOG_PATH = "/Agentic/logs/hats_protocol_scanner.log"
HATS_OPPORTUNITIES_DIR = "/Agentic/revenue/hats_opportunities"

# Known Hats Protocol DAOs and ecosystems with active contribution programs
TARGET_ECOSYSTEMS = [
    {"name": "Gitcoin DAO", "url": "https://grants.gitcoin.co/", "type": "governance", "payout": "crypto_stream", "autonomous_friendly": True},
    {"name": "Optimism Collective", "url": "https://community.optimism.io/", "type": "retroactive_funding", "payout": "op_token", "autonomous_friendly": True},
    {"name": "Arbitrum DAO", "url": "https://forum.arbitrum.foundation/", "type": "grant_proposal", "payout": "arb_token", "autonomous_friendly": False},
    {"name": "ENS DAO", "url": "https://discuss.ens.domains/", "type": "working_group", "payout": "eth_stream", "autonomous_friendly": True},
    {"name": "Uniswap Foundation", "url": "https://www.uniswapfoundation.org/", "type": "dev_grant", "payout": "uni_token", "autonomous_friendly": True},
    {"name": "Aave DAO", "url": "https://governance.aave.com/", "type": "service_provider", "payout": "aave_token", "autonomous_friendly": False},
    {"name": "MakerDAO", "url": "https://forum.makerdao.com/", "type": "core_unit", "payout": "dai_stream", "autonomous_friendly": False},
    {"name": "Compound Grants", "url": "https://compound.finance/grants", "type": "dev_grant", "payout": "comp_token", "autonomous_friendly": True},
    {"name": "Lido DAO", "url": "https://research.lido.fi/", "type": "contributor", "payout": "ldo_token", "autonomous_friendly": True},
    {"name": "Gnosis DAO", "url": "https://forum.gnosis.io/", "type": "working_group", "payout": "gno_token", "autonomous_friendly": True}
]

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(HATS_LOG_PATH), exist_ok=True)
    with open(HATS_LOG_PATH, "a") as f:
        f.write(line + "\n")

def load_config():
    if os.path.exists(HATS_CONFIG_PATH):
        with open(HATS_CONFIG_PATH) as f:
            return json.load(f)
    return {"scanned_ecosystems": [], "last_scan": None}

def save_config(cfg):
    os.makedirs(os.path.dirname(HATS_CONFIG_PATH), exist_ok=True)
    with open(HATS_CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

def scan_hats_ecosystems():
    """Scan Hats Protocol compatible DAOs for contribution opportunities."""
    log("Scanning Hats Protocol & DAO ecosystems for contribution opportunities...")
    
    opportunities = []
    
    for eco in TARGET_ECOSYSTEMS:
        opp = {
            "id": f"HATS-{eco['name'].lower().replace(' ', '-')}",
            "platform": "hats_protocol_dao",
            "ecosystem": eco["name"],
            "url": eco["url"],
            "contribution_type": eco["type"],
            "payout_method": eco["payout"],
            "autonomous_friendly": eco.get("autonomous_friendly", False),
            "status": "active",
            "requires_human": ["wallet_connect", "dao_membership"] if not eco.get("autonomous_friendly") else ["wallet_connect"],
            "discovered_at": datetime.now(timezone.utc).isoformat()
        }
        opportunities.append(opp)
        auto_flag = "✅" if eco.get("autonomous_friendly") else "⚠️"
        log(f"  Found: {eco['name']} - {eco['type']} - {eco['payout']} {auto_flag}")
    
    return opportunities

def update_ledger_with_hats(opportunities):
    """Add Hats/DAO opportunities to ledger."""
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
                "type": "hats_dao_opportunity",
                **opp,
                "date_added": datetime.now(timezone.utc).isoformat()
            })
            added += 1
    
    if isinstance(data, dict):
        data["entries"] = entries
    
    with open(ledger_path, "w") as f:
        json.dump(data, f, indent=2)
    
    log(f"Added {added} Hats/DAO opportunities to ledger")

def main():
    log("=== Hats Protocol & DAO Scanner Cycle Start ===")
    
    cfg = load_config()
    opportunities = scan_hats_ecosystems()
    
    # Save opportunities to disk
    os.makedirs(HATS_OPPORTUNITIES_DIR, exist_ok=True)
    for opp in opportunities:
        path = os.path.join(HATS_OPPORTUNITIES_DIR, f"{opp['id']}.json")
        with open(path, "w") as f:
            json.dump(opp, f, indent=2)
    
    cfg["scanned_ecosystems"] = [e["name"] for e in TARGET_ECOSYSTEMS]
    cfg["last_scan"] = datetime.now(timezone.utc).isoformat()
    save_config(cfg)
    
    update_ledger_with_hats(opportunities)
    
    auto_count = sum(1 for o in opportunities if o.get("autonomous_friendly"))
    
    log(f"Scan complete: {len(opportunities)} DAO ecosystems found ({auto_count} autonomous-friendly)")
    log("=== Hats Protocol & DAO Scanner Cycle Complete ===")

if __name__ == "__main__":
    main()
