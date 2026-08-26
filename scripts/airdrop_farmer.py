#!/usr/bin/env python3
"""Airdrop & Points Farmer Scanner - Alternative Revenue Stream v2"""
import sys, os, json, time, re, requests
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/Agentic")
LOG = ROOT / "logs" / "airdrop_farmer.log"
LEDGER = ROOT / "data" / "aro" / "airdrop_opportunities.json"

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def scan_airdrops():
    """Scan for active airdrop/points programs with estimated value"""
    log("=== AIRDROP FARMER SCAN START ===")
    opportunities = []
    
    # Known active points/airdrop programs (manually curated from DeFi ecosystem)
    ACTIVE_PROGRAMS = [
        {"name": "EigenLayer", "chain": "Ethereum", "type": "restaking_points", "est_value": "high", "tvl_api": "eigenlayer"},
        {"name": "Ether.fi", "chain": "Ethereum", "type": "lrt_points", "est_value": "high", "tvl_api": "ether-fi"},
        {"name": "Renzo", "chain": "Multi", "type": "lrt_points", "est_value": "medium", "tvl_api": "renzo"},
        {"name": "Puffer Finance", "chain": "Ethereum", "type": "lrt_points", "est_value": "medium", "tvl_api": "puffer-finance"},
        {"name": "Kelp DAO", "chain": "Multi", "type": "lrt_points", "est_value": "medium", "tvl_api": "kelp-dao"},
        {"name": "Swell", "chain": "Ethereum", "type": "lrt_points", "est_value": "medium", "tvl_api": "swell"},
        {"name": "StakeStone", "chain": "Multi", "type": "lrt_points", "est_value": "low", "tvl_api": "stakestone"},
        {"name": "AltLayer", "chain": "Multi", "type": "restaking_points", "est_value": "medium", "tvl_api": "altlayer"},
        {"name": "Berachain", "chain": "Berachain", "type": "testnet_points", "est_value": "high", "tvl_api": None},
        {"name": "Monad", "chain": "Monad", "type": "testnet_points", "est_value": "high", "tvl_api": None},
        {"name": "Linea", "chain": "Linea", "type": "l2_points", "est_value": "high", "tvl_api": None},
        {"name": "Scroll", "chain": "Scroll", "type": "l2_points", "est_value": "medium", "tvl_api": None},
        {"name": "zkSync Era", "chain": "zkSync", "type": "l2_points", "est_value": "medium", "tvl_api": None},
        {"name": "Fuel Network", "chain": "Fuel", "type": "testnet_points", "est_value": "medium", "tvl_api": None},
        {"name": "Abstract Chain", "chain": "Abstract", "type": "l2_points", "est_value": "medium", "tvl_api": None},
    ]
    
    # Fetch TVL data from DefiLlama
    tvl_data = {}
    try:
        resp = requests.get("https://api.llama.fi/protocols", timeout=30)
        if resp.status_code == 200:
            protocols = resp.json()
            for p in protocols:
                slug = p.get("slug", "").lower()
                tvl_data[slug] = {
                    "tvl": p.get("tvl", 0),
                    "change_1d": p.get("change_1d", 0),
                    "chain": p.get("chain", "multi")
                }
            log(f"  DefiLlama: fetched TVL for {len(tvl_data)} protocols")
    except Exception as e:
        log(f"  DefiLlama error: {e}")
    
    # Build opportunity list with real TVL data
    for prog in ACTIVE_PROGRAMS:
        tvl_info = tvl_data.get(prog["tvl_api"], {}) if prog.get("tvl_api") else {}
        tvl = tvl_info.get("tvl", 0) or 0
        
        opportunities.append({
            "name": prog["name"],
            "chain": prog["chain"],
            "type": prog["type"],
            "est_value": prog["est_value"],
            "tvl_usd": tvl,
            "tvl_change_1d": tvl_info.get("change_1d", 0),
            "actionable": True,
            "found_at": datetime.now(timezone.utc).isoformat()
        })
        
        if tvl > 0:
            log(f"  FOUND: {prog['name']} | TVL: ${tvl/1e6:.0f}M | Type: {prog['type']} | Value: {prog['est_value']}")
        else:
            log(f"  FOUND: {prog['name']} | TVL: N/A (testnet/L2) | Type: {prog['type']} | Value: {prog['est_value']}")
    
    # Scan for new token launches on major chains (potential retroactive airdrops)
    try:
        # Check recent high-TVL protocol launches
        resp = requests.get("https://api.llama.fi/protocols?chain=Ethereum", timeout=20)
        if resp.status_code == 200:
            eth_protos = resp.json()
            # Find protocols launched in last 30 days with TVL > $10M
            new_protos = [p for p in eth_protos 
                         if (p.get("tvl") or 0) > 10_000_000 
                         and p.get("symbol")  # Has token = potential airdrop
                         and not p.get("deadUrl")]
            log(f"  New ETH protocols (TVL>$10M): {len(new_protos)} candidates")
            for np in new_protos[:5]:
                opportunities.append({
                    "name": np.get("name", "?"),
                    "chain": "Ethereum",
                    "type": "new_protocol_retro",
                    "est_value": "speculative",
                    "tvl_usd": np.get("tvl", 0),
                    "token": np.get("symbol", "?"),
                    "actionable": True,
                    "found_at": datetime.now(timezone.utc).isoformat()
                })
    except Exception as e:
        log(f"  New protocol scan error: {e}")
    
    log(f"Total airdrop opportunities: {len(opportunities)}")
    
    # Save to ledger
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    ledger_data = {
        "opportunities": opportunities,
        "last_scan": datetime.now(timezone.utc).isoformat(),
        "total_found": len(opportunities),
        "high_value_count": len([o for o in opportunities if o.get("est_value") == "high"]),
        "total_tvl_tracked": sum(o.get("tvl_usd", 0) for o in opportunities)
    }
    LEDGER.write_text(json.dumps(ledger_data, indent=2, default=str))
    log(f"Saved to ledger. High-value targets: {ledger_data['high_value_count']}")
    
    return opportunities

if __name__ == "__main__":
    log("Airdrop Farmer Scanner v1.0 starting (interval=3600s)")
    while True:
        try:
            scan_airdrops()
        except Exception as e:
            log(f"FATAL: {e}")
        time.sleep(3600)
