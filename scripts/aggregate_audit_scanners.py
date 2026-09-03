#!/usr/bin/env python3
"""Aggregate C4/Sherlock opportunity files into queue-builder-compatible state.

The deterministic bounty_priority_queue.py only ingests sources listed in
ALL_INPUT_ORDER. This adapter reads the individual opportunity JSON files
produced by code4rena_contest_scanner and sherlock_audit_scanner, normalizes
them to the candidate schema expected by _candidate_rows, and writes a single
state file that can be added to ALL_INPUT_ORDER.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

C4_DIR = Path("/Agentic/revenue/code4rena_opportunities")
SHERLOCK_DIR = Path("/Agentic/revenue/sherlock_opportunities")
OUTPUT_PATH = Path("/Agentic/state/audit_contest_candidates.json")

def load_opportunities(directory: Path, platform: str) -> list[dict]:
    candidates = []
    if not directory.exists():
        return candidates
    for f in sorted(directory.glob("*.json")):
        try:
            data = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        # Normalize to candidate shape expected by queue builder
        prize = data.get("prize_pool_usd")
        if prize is None:
            continue
        candidate = {
            "id": data.get("id", f.stem),
            "platform": platform,
            "sponsor": data.get("sponsor", ""),
            "title": f"{data.get('sponsor', '')} Audit Contest",
            "reward": {
                "asset": "USDC",
                "amount": prize,
                "network": "ethereum" if platform == "code4rena" else "arbitrum",
            },
            "payout": {
                "asset": "USDC",
                "network": "ethereum" if platform == "code4rena" else "arbitrum",
                "method": data.get("payout_method", "crypto_wallet"),
            },
            "status": data.get("status", "open"),
            "autonomous_submission": data.get("autonomous_submission", False),
            "requires_human": data.get("requires_human", []),
            "discovered_at": data.get("discovered_at"),
            "source_file": str(f),
        }
        candidates.append(candidate)
    return candidates

def main():
    c4 = load_opportunities(C4_DIR, "code4rena")
    sherlock = load_opportunities(SHERLOCK_DIR, "sherlock")
    all_candidates = c4 + sherlock
    
    output = {
        "schema_version": "1.0",
        "source": "audit_contests",
        "platforms": ["code4rena", "sherlock"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok" if all_candidates else "empty",
        "candidates": all_candidates,
        "candidate_count": len(all_candidates),
        "total_prize_pool_usd": sum(c["reward"]["amount"] for c in all_candidates),
    }
    
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    tmp.rename(OUTPUT_PATH)
    print(f"Wrote {len(all_candidates)} audit contest candidates to {OUTPUT_PATH}")
    print(f"  Code4rena: {len(c4)}, Sherlock: {len(sherlock)}")
    print(f"  Total prize pool: ${output['total_prize_pool_usd']:,.0f}")

if __name__ == "__main__":
    main()
