#!/usr/bin/env python3
"""
Netlify Edge Functions Free Tier Reselling Scaffold
Zero-Capital Lab - Infrastructure Reselling Pipeline

Validates eligibility, maps free tier limits, estimates margin potential,
and documents reselling constraints for Netlify Starter plan edge functions.

Sources:
- https://www.netlify.com/pricing/
- https://docs.netlify.com/platform/limits/
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
    "build_minutes_month": 300,
    "serverless_function_invocations_month": 125_000,
    "edge_function_invocations_month": None,  # included in serverless count on starter
    "max_execution_duration_seconds": 10,
    "max_payload_size_mb": 6,
    "concurrent_builds": 1,
    "team_members": 1,
    "commercial_usage_allowed": True,  # Netlify Starter allows commercial use unlike Vercel Hobby
}

PAID_PLAN_BASELINE = {
    "name": "Pro ($19/mo per member)",
    "bandwidth_gb_month": 400,
    "build_minutes_month": 24_000,
    "serverless_function_invocations_month": 1_000_000,
    "max_execution_duration_seconds": 26,
    "analytics_included": True,
    "password_protection": True,
}

RESELLING_MODEL = {
    "strategy": "Managed Jamstack Hosting for SMBs",
    "target_customer": "Small businesses needing static sites + edge APIs without DevOps",
    "value_prop": "Deploy + custom domain + SSL + form handling + monitoring",
    "suggested_price_brl": 49.90,
    "cost_to_provider_brl": 0.00,
    "estimated_margin_pct": 100.0,
    "scale_constraint": "Starter plan allows commercial use but limited to 125K function invocations/mo; heavy clients need Pro upgrade",
    "tos_compliance_note": "Netlify Starter explicitly permits commercial usage. Reselling as managed service is allowed. No partner program required for basic resale.",
}

def validate_free_tier_docs():
    """Attempt to fetch current limits from official docs."""
    result = {"source_verified": False, "url": "", "extracted_limits": {}, "error": None}
    try:
        url = "https://www.netlify.com/pricing/"
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
                result["extracted_limits"]["serverless_function_invocations_month"] = val
            m3 = re.search(r"(\d+)\s*(?:minutes?)\s*(?:of\s+)?build", html, re.I)
            if m3:
                result["extracted_limits"]["build_minutes_month"] = int(m3.group(1))
    except Exception as e:
        result["error"] = str(e)
    return result

def estimate_unit_economics(monthly_clients: int = 10):
    """Estimate monthly economics for managed Jamstack model."""
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
        "pilot": "netlify-edge-reseller-scaffold",
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
            "Build minutes limit (300/mo) tight for active development; exceeded builds queue or fail",
            "Function invocation limit (125K/mo) lower than Vercel Hobby (100K exec + unlimited edge)",
            "No native database; requires external Supabase/PlanetScale/Fauna integration",
            "Form submissions limited to 100/mo on Starter; client forms may exceed quickly",
            "Custom domains require DNS configuration per client; no bulk provisioning API on Starter",
        ],
        "next_steps": [
            "Build site provisioning script via Netlify API v1",
            "Create automated deploy pipeline for client repos",
            "Design form handling upsell path (Netlify Forms paid or alternative)",
            "Test edge function performance vs Cloudflare Workers for same workload",
            "Draft migration playbook from Starter to Pro for growing clients",
        ],
    }
    
    out_path = os.path.join(OUTPUT_DIR, "reseller_scaffold_index.json")
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"[OK] Scaffold generated at {ts}")
    print(f"  Doc verified: {doc_validation['source_verified']}")
    print(f"  Bandwidth extracted: {doc_validation['extracted_limits'].get('bandwidth_gb_month', 'N/A')} GB")
    print(f"  Commercial allowed: {FREE_TIER_LIMITS['commercial_usage_allowed']}")
    print(f"  Economics (10 clients): R${economics_small['revenue_brl']}/mo margin={economics_small['margin_pct']}%")
    print(f"  Output: {out_path}")

if __name__ == "__main__":
    main()
