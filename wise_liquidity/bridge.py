#!/usr/bin/env python3
"""Wise Liquidity Bridge - Capital flow coordinator for futures subagents"""
import json, os, sys
from datetime import datetime, timezone

STATE_PATH = "/Agentic/orchestrator/state.json"
CONFIG_PATH = "/Agentic/wise_liquidity/config.json"

def load_json(path):
    with open(path) as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    print(f"[{ts}] {msg}", flush=True)

def assess_bridge_needs(state, config):
    """Check which futures subagents need liquidity support"""
    bridge_targets = config.get("bridge_targets", [])
    needs = []
    for target in bridge_targets:
        agent = state.get("subagents", {}).get(target, {})
        goal = agent.get("goal_usd", 0)
        current = agent.get("current_usd", 0)
        deficit = goal - current
        if deficit > 0 and agent.get("status") != "initializing":
            needs.append({
                "target": target,
                "deficit_usd": deficit,
                "priority": "high" if deficit > goal * 0.5 else "medium"
            })
    return needs

def simulate_bridge_transfer(needs, available_usd):
    """Simulate capital allocation (real implementation requires Wise API + exchange APIs)"""
    allocations = []
    remaining = available_usd
    for need in sorted(needs, key=lambda x: x["deficit_usd"], reverse=True):
        alloc = min(need["deficit_usd"], remaining)
        if alloc > 0:
            allocations.append({"target": need["target"], "amount_usd": alloc})
            remaining -= alloc
    return allocations

def main():
    state = load_json(STATE_PATH)
    config = load_json(CONFIG_PATH)
    
    wise_agent = state.get("subagents", {}).get("wise_liquidity", {})
    available = wise_agent.get("current_usd", 0)
    
    log("Bridge coordinator started")
    needs = assess_bridge_needs(state, config)
    
    if not needs:
        log("No active bridge requests from futures subagents")
    else:
        log(f"Identified {len(needs)} subagent(s) needing liquidity")
        for n in needs:
            log(f"  -> {n['target']}: deficit ${n['deficit_usd']:,.0f} ({n['priority']} priority)")
        
        if available > 0:
            allocs = simulate_bridge_transfer(needs, available)
            for a in allocs:
                log(f"  Allocated ${a['amount_usd']:,.0f} to {a['target']}")
        else:
            log("No available liquidity in wise_liquidity to bridge; awaiting fiat inflow or arb profits")
    
    # Update status to reflect bridge readiness
    if "wise_liquidity" in state.get("subagents", {}):
        state["subagents"]["wise_liquidity"]["status"] = "bridge_ready"
        state["subagents"]["wise_liquidity"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        save_json(STATE_PATH, state)
        log("State updated: bridge_ready")

if __name__ == "__main__":
    main()
