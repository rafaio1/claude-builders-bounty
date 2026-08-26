#!/usr/bin/env python3
"""
Vercel Hobby Plan Edge Function Reselling Scaffold
Zero-Capital Lab - Infrastructure Reselling Pipeline

Validates eligibility, maps free tier limits, estimates margin potential,
and documents reselling constraints for Vercel Hobby plan edge functions.

Sources:
- https://vercel.com/pricing
- https://vercel.com/docs/platform/limits
"""

import json
import os
import datetime
import urllib.request
import re

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

FREE_TIER_LIMITS = {
    "bandwidth_gb_month": 100,
    "serverless_function_executions_month": 100_000,
    "edge_function_invocations_month": None,  # unlimited on hobby but fair use
    "build_minutes_month": 6_000,
    "max_execution_duration_seconds": 10,
    "max_payload_size_mb": 4.5,
    "commercial_usage_allowed": False,
    "team_members": 1,
}

PAID_PLAN_BASELINE = {
    "name": "Pro ($20/mo per member)",
    "bandwidth_gb_month": 1_000,
    "serverless_function_executions_month": 1_000_000,
    "build_minutes_month": 24_000,
    "max_execution_duration_seconds": 60,
    "commercial_usage_allowed": True,
    "analytics_included": True,
}

RESELLING_MODEL = {
    "strategy": "Managed Frontend Hosting for SMBs",
    "target_customer": "Small businesses needing static sites + serverless APIs without DevOps",
    "value_prop": "Deploy + custom domain + SSL + monitoring + performance optimization",
    "suggested_price_brl": 59.90,
    "cost_to_provider_brl": 0.00,
    "estimated_margin_pct": 100.0,
    "scale_constraint": "Hobby plan prohibits commercial usage; managed service must use Pro plan or frame as personal projects under client accounts",
    "tos_compliance_note": "Vercel Hobby plan explicitly forbids commercial usage (ToS Section 3). Reselling requires Pro plan upgrade or having clients sign up directly with reseller as consultant.",
}

def validate_free_tier_docs():
    """Attempt to fetch current limits from official docs."""
    result = {"source_verified": False, "url": "", "extracted_limits": {}, "error": None}
    try:
        url = "https://vercel.com/pricing"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ZeroCapitalLab/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
            result["url"] = url
            m = re.search(r"(\d+)\s*(?:GB|gb)\s*(?:of\s+)?bandwidth", html, re.I)
            if m:
                result["extracted_limits"]["bandwidth_gb_month"] = int(m.group(1))
                result["source_verified"] = True
            m2 = re.search(r"(\d[\d,]*)\s*(?:free\s+)?(?:serverless\s+)?(?:function\s+)?(?:execution|invocation)s?", html, re.I)
            if m2:
                val = int(m2.group(1).replace(",", ""))
                result["extracted_limits"]["serverless_function_executions_month"] = val
            m3 = re.search(r"commercial.*?(?:not\s+)?allowed|non-commercial", html, re.I)
            if m3:
                result["extracted_limits"]["commercial_usage_allowed"] = False
    except Exception as e:
        result["error"] = str(e)
    return result

def estimate_unit_economics(monthly_clients: int = 10):
    """Estimate monthly economics for managed hosting model."""
    revenue = monthly_clients * RESELLING_MODEL["suggested_price_brl"]
    cost = 0.0
    margin = revenue - cost
    return {
        "monthly_clients": monthly_clients,
        "revenue_brl": round(revenue, 2),
        "cost_brl": round(cost, 2),
        "margin_brl": round(margin, 2),
        "margin_pct": 100.0 if cost == 0 else round((margin / revenue) * 100, 1),
        "annualized_revenue_brl": round(revenue * 12, 2),
    }

def main():
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    doc_validation = validate_free_tier_docs()
    economics_small = estimate_unit_economics(10)
    economics_medium = estimate_unit_economics(50)
    economics_scale = estimate_unit_economics(200)
    
    report = {
        "pilot": "vercel-edge-reseller-scaffold",
        "category": "infrastructure_reselling",
        "timestamp": ts,
        "status": "SCAFFOLD_OK",
        "free_tier_limits": FREE_TIER_LIMITS,
        "paid_plan_baseline": PAID_PLAN_BASELINE,
        "reselling_model": RESELLING_MODEL,
        "doc_validation": doc_validation,
        "unit_economics": {
            "small_10_clients": economics_small,
            "medium_50_clients": economics_medium,
            "scale_200_clients": economics_scale,
        },
        "risks": [
            "Hobby plan explicitly prohibits commercial usage; requires Pro plan ($20/mo) for legitimate resale",
            "Margin collapses if Pro plan required: R$59.90 revenue - ~R$100 cost = negative margin at small scale",
            "Execution duration limit (10s on Hobby) insufficient for complex APIs; Pro offers 60s",
            "No SLA on Hobby plan; production outages have no recourse",
            "Team collaboration limited to 1 member on Hobby; multi-developer projects need Pro",
        ],
        "next_steps": [
            "Re-evaluate economics with Pro plan cost included; target price may need to be R$149+",
            "Explore Vercel Partner Program for volume discounts on Pro plans",
            "Build deployment automation via Vercel CLI/API for rapid client onboarding",
            "Create migration path from Hobby to Pro as client usage grows",
            "Consider alternative providers (Netlify, Cloudflare Pages) with more permissive free tiers",
        ],
    }
    
    out_path = os.path.join(OUTPUT_DIR, "reseller_scaffold_index.json")
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"[OK] Scaffold generated at {ts}")
    print(f"  Doc verified: {doc_validation['source_verified']}")
    print(f"  Bandwidth extracted: {doc_validation['extracted_limits'].get('bandwidth_gb_month', 'N/A')} GB")
    print(f"  Commercial allowed: {doc_validation['extracted_limits'].get('commercial_usage_allowed', 'N/A')}")
    print(f"  Economics (10 clients): R${economics_small['revenue_brl']}/mo margin={economics_small['margin_pct']}%")
    print(f"  WARNING: Hobby plan prohibits commercial usage - see risks")
    print(f"  Output: {out_path}")

if __name__ == "__main__":
    main()
