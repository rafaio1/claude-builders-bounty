#!/usr/bin/env python3
"""
Opportunity Scaler Agent: Identifies and prioritizes high-value opportunities
to scale revenue from micro-gigs to $1M USD target.

Analyzes:
- contracts.json for conversion rates
- micro_gigs_found.json for volume/patterns
- External opportunity feeds (when available)

Outputs prioritized opportunity list with expected value and action items.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path("/Agentic/data/aro")
CONTRACTS_PATH = DATA_DIR / "contracts.json"
GIGS_PATH = DATA_DIR / "micro_gigs_found.json"
OPPORTUNITIES_PATH = DATA_DIR / "opportunities.json"
REPORT_PATH = DATA_DIR / "reports/opportunity-pipeline-2026-08-20.json"

def load_json(path: Path) -> dict | list:
    if not path.exists():
        return {} if path.suffix == '.json' and 'contract' in str(path) else []
    try:
        return json.loads(path.read_text())
    except:
        return {}

def analyze_contracts(contracts: dict) -> dict:
    """Analyze contract conversion and revenue patterns."""
    items = contracts.get("items", []) if isinstance(contracts, dict) else []
    
    stats = {
        "total": len(items),
        "by_status": defaultdict(int),
        "by_amount": {"micro_lt50": 0, "mid_50_250": 0, "premium_gt250": 0},
        "total_value_brl": 0.0,
        "converted_value_brl": 0.0,
        "conversion_rate": 0.0
    }
    
    for c in items:
        status = c.get("status", "unknown")
        amount = float(c.get("amount_brl", 0))
        stats["by_status"][status] += 1
        stats["total_value_brl"] += amount
        
        if amount < 50:
            stats["by_amount"]["micro_lt50"] += 1
        elif amount <= 250:
            stats["by_amount"]["mid_50_250"] += 1
        else:
            stats["by_amount"]["premium_gt250"] += 1
            
        if status in ("paid", "completed", "delivered"):
            stats["converted_value_brl"] += amount
    
    if stats["total"] > 0:
        paid = stats["by_status"].get("paid", 0) + stats["by_status"].get("completed", 0)
        stats["conversion_rate"] = round(paid / stats["total"] * 100, 1)
    
    stats["by_status"] = dict(stats["by_status"])
    return stats

def analyze_gigs(gigs: list) -> dict:
    """Analyze micro-gig patterns for scaling signals."""
    if not gigs:
        return {"count": 0, "sources": {}, "avg_budget": 0}
    
    sources = defaultdict(int)
    budgets = []
    
    for g in gigs:
        src = g.get("source", g.get("platform", "unknown"))
        sources[src] += 1
        budget = g.get("budget", g.get("amount", 0))
        if isinstance(budget, (int, float)):
            budgets.append(float(budget))
    
    return {
        "count": len(gigs),
        "sources": dict(sources),
        "avg_budget": round(sum(budgets) / len(budgets), 2) if budgets else 0,
        "high_value_count": sum(1 for b in budgets if b >= 100)
    }

def generate_scaling_recommendations(contract_stats: dict, gig_stats: dict) -> list:
    """Generate actionable recommendations based on data."""
    recs = []
    
    # Check conversion rate
    if contract_stats["conversion_rate"] < 20:
        recs.append({
            "priority": "CRITICAL",
            "action": "Improve proposal quality or targeting",
            "reason": f"Conversion rate is {contract_stats['conversion_rate']}% (target: >30%)",
            "expected_impact": "2-3x revenue increase"
        })
    
    # Check ticket size distribution
    if contract_stats["by_amount"]["premium_gt250"] < contract_stats["total"] * 0.3:
        recs.append({
            "priority": "HIGH",
            "action": "Shift focus to premium contracts (>$250 BRL)",
            "reason": f"Only {contract_stats['by_amount']['premium_gt250']}/{contract_stats['total']} contracts are premium tier",
            "expected_impact": "Higher margin, lower volume needed for $1M"
        })
    
    # Check gig source diversity
    if len(gig_stats.get("sources", {})) < 3:
        recs.append({
            "priority": "MEDIUM",
            "action": "Diversify opportunity sources beyond current platforms",
            "reason": "Over-reliance on single channel increases risk",
            "expected_impact": "Stable pipeline during platform downturns"
        })
    
    # Scaling math
    current_monthly_est = contract_stats["converted_value_brl"] / max(1, contract_stats["total"]) * 30
    gap_to_1m_usd_brl = 5000000 - contract_stats["converted_value_brl"]
    
    recs.append({
        "priority": "STRATEGIC",
        "action": "Build recurring revenue stream (B2B retainers)",
        "reason": f"One-off sales require {gap_to_1m_usd_brl/max(current_monthly_est, 1):.0f} months at current pace; retainers compress timeline",
        "expected_impact": "Path to $1M in 18-24 months vs 10+ years"
    })
    
    return recs

def main():
    contracts = load_json(CONTRACTS_PATH)
    gigs = load_json(GIGS_PATH)
    
    contract_stats = analyze_contracts(contracts)
    gig_stats = analyze_gigs(gigs)
    recommendations = generate_scaling_recommendations(contract_stats, gig_stats)
    
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_analysis": contract_stats,
        "gig_pipeline_analysis": gig_stats,
        "scaling_recommendations": recommendations,
        "target": {
            "usd": 1000000,
            "brl_approx": 5000000,
            "current_validated_brl": 0.0,  # From reality-gate audit
            "gap_multiplier": "INFINITE"
        },
        "next_steps": [
            "Filter MQL5/Freelancer for budget >= $100 only",
            "Create B2B retainer proposal template",
            "Activate email_triage.py to capture client replies faster",
            "Weekly review of opportunity pipeline metrics"
        ]
    }
    
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
