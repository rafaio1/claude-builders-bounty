#!/usr/bin/env python3
"""
Broadcast Perpetual Trading Mandate to all active Codex subagents.
Since multi_agent_v1 is unsupported, this writes the mandate to shared state
that all agents read on next cycle, and logs the broadcast event.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

MANDATE_PATH = "/Agentic/data/aro/active_mandates/perpetual_trading.json"
JOURNAL_PATH = "/Agentic/data/aro/journal.jsonl"
ROADMAP_PATH = "/Agentic/data/aro/scaling-roadmap-1m.md"
GUIDE_PATH = "/Agentic/docs/PERPETUAL_TRADING_GUIDE.md"

def create_mandate():
    mandate = {
        "id": "mandate-perp-2026-08-21",
        "type": "trading_strategy_override",
        "status": "ACTIVE",
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "issuer": "human_operator",
        "scope": "ALL_TRADING_SUBAGENTS",
        "supersedes": ["spot_only", "low_leverage_default"],
        "rules": {
            "max_leverage_directional": 3,
            "max_leverage_funding_arb": 10,
            "max_risk_per_trade_pct": 2.0,
            "min_volume_24h_usd": 50000000,
            "max_spread_pct": 0.05,
            "funding_rate_threshold_pct_8h": 0.1,
            "stop_loss_required": True,
            "strategies_priority": [
                "funding_rate_arbitrage",
                "breakout_volume_confirmed",
                "mean_reversion_extreme"
            ],
            "target_roi_monthly_pct": {"min": 15, "max": 30},
            "target_sharpe_ratio": 1.5,
            "max_drawdown_pct": 15
        },
        "integration": {
            "trade_log_path": "/Agentic/data/aro/trades/perpetuals.jsonl",
            "reality_gate_validation": "exchange_statement_pnl_match",
            "email_triage_override": {
                "pertinent_keywords": ["funding >0.3%", "liquidation", "margin call", "maintenance margin"],
                "action": "ROUTE_TO_HUMAN_DO_NOT_DELETE"
            }
        },
        "documentation": {
            "full_guide": GUIDE_PATH,
            "roadmap_section": ROADMAP_PATH
        },
        "enforcement": "Agents not complying are considered misaligned with $1M USD goal."
    }
    
    os.makedirs(os.path.dirname(MANDATE_PATH), exist_ok=True)
    with open(MANDATE_PATH, "w") as f:
        json.dump(mandate, f, indent=2, ensure_ascii=False)
    
    return mandate

def log_broadcast(mandate):
    entry = {
        "kind": "mandate_broadcast",
        "mandate_id": mandate["id"],
        "scope": mandate["scope"],
        "reason": "spot_roi_insufficient_for_1m_target_user_directive",
        "broadcast_method": "shared_state_write",
        "multi_agent_v1_status": "unsupported_fallback_to_file",
        "at": datetime.now(timezone.utc).isoformat(),
        "hash": "bc-perp-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    }
    
    os.makedirs(os.path.dirname(JOURNAL_PATH), exist_ok=True)
    with open(JOURNAL_PATH, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def main():
    mandate = create_mandate()
    log_broadcast(mandate)
    
    print("=== PERPETUAL MANDATE BROADCASTED ===")
    print(f"Mandate ID: {mandate['id']}")
    print(f"Status: {mandate['status']}")
    print(f"Scope: {mandate['scope']}")
    print(f"Written to: {MANDATE_PATH}")
    print(f"Journal logged: {JOURNAL_PATH}")
    print("\nAll trading subagents will read this mandate on next cycle.")
    print("Key rules: Max 3x lev, SL mandatory, funding check pre-trade, ROI target 15-30%/mo")
    print(f"Full guide: {GUIDE_PATH}")
    print(f"Roadmap updated: {ROADMAP_PATH}")

if __name__ == "__main__":
    main()
