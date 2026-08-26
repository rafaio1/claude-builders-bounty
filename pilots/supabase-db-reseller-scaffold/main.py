#!/usr/bin/env python3
"""
Supabase Free Tier Database Reselling Scaffold
Zero-Capital Lab - Infrastructure Reselling Pipeline

Validates eligibility, maps free tier limits, estimates margin potential,
and documents reselling constraints for Supabase Postgres + Edge Functions.

Sources:
- https://supabase.com/pricing
- https://supabase.com/docs/guides/platform/limits
"""

import json
import os
import datetime
import urllib.request
import re

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

FREE_TIER_LIMITS = {
    "database_size_mb": 500,
    "bandwidth_gb_month": 5,
    "edge_function_invocations_month": 500_000,
    "realtime_messages_month": 2_000_000,
    "storage_size_gb": 1,
    "storage_bandwidth_gb_month": 2,
    "projects_count": 2,
    "pause_after_inactivity_days": 7,
    "max_connections": None,  # not explicitly limited on free but pool constrained
}

PAID_PLAN_BASELINE = {
    "name": "Pro ($25/mo)",
    "database_size_gb": 8,
    "bandwidth_gb_month": 250,
    "edge_function_invocations_month": None,  # pay per use
    "no_pause": True,
    "daily_backups": True,
}

RESELLING_MODEL = {
    "strategy": "Managed Backend-as-a-Service for SMBs",
    "target_customer": "Small SaaS/apps needing Postgres + Auth + Storage without DevOps",
    "value_prop": "Pre-configured project + schema migrations + monitoring + custom domain",
    "suggested_price_brl": 89.90,
    "cost_to_provider_brl": 0.00,  # free tier covers MVP-stage clients
    "estimated_margin_pct": 100.0,
    "scale_constraint": "Free tier pauses after 7 days inactivity; production clients need Pro plan or keep-alive pings",
    "tos_compliance_note": "Supabase ToS permits managed services. Reselling raw access may require partner program. Each client should have own project under reseller org or separate account.",
}

def validate_free_tier_docs():
    """Attempt to fetch current limits from official docs."""
    result = {"source_verified": False, "url": "", "extracted_limits": {}, "error": None}
    try:
        url = "https://supabase.com/pricing"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ZeroCapitalLab/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
            result["url"] = url
            # Extract database size
            m = re.search(r"(\d+)\s*(?:MB|mb)\s*(?:of\s+)?(?:database|db)\s*(?:size|space)", html, re.I)
            if m:
                result["extracted_limits"]["database_size_mb"] = int(m.group(1))
                result["source_verified"] = True
            # Extract bandwidth
            m2 = re.search(r"(\d+)\s*(?:GB|gb)\s*(?:of\s+)?bandwidth", html, re.I)
            if m2:
                result["extracted_limits"]["bandwidth_gb_month"] = int(m2.group(1))
            # Extract projects
            m3 = re.search(r"(\d+)\s*(?:free\s+)?projects?", html, re.I)
            if m3:
                result["extracted_limits"]["projects_count"] = int(m3.group(1))
    except Exception as e:
        result["error"] = str(e)
    return result

def estimate_unit_economics(monthly_clients: int = 10):
    """Estimate monthly economics for managed BaaS model."""
    revenue = monthly_clients * RESELLING_MODEL["suggested_price_brl"]
    cost = 0.0  # free tier assumed sufficient for small clients
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
        "pilot": "supabase-db-reseller-scaffold",
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
            "Free tier projects pause after 7 days inactivity; requires keep-alive cron or upgrade",
            "Database size limit (500MB) tight for production; migration path to Pro needed",
            "Only 2 free projects per account; multi-client requires multiple accounts or org upgrade",
            "No SLA on free tier; data loss risk if project paused/restored incorrectly",
            "Auth users limited to 50K MAU on free tier; SaaS apps may hit ceiling fast",
        ],
        "next_steps": [
            "Validate ToS for managed service vs resale distinction",
            "Build project provisioning script via Supabase Management API",
            "Create keep-alive mechanism to prevent project pausing",
            "Draft migration playbook for clients exceeding free tier limits",
            "Test restore reliability after 7-day pause cycle",
        ],
    }
    
    out_path = os.path.join(OUTPUT_DIR, "reseller_scaffold_index.json")
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"[OK] Scaffold generated at {ts}")
    print(f"  Doc verified: {doc_validation['source_verified']}")
    print(f"  DB size extracted: {doc_validation['extracted_limits'].get('database_size_mb', 'N/A')} MB")
    print(f"  Economics (10 clients): R${economics_small['revenue_brl']}/mo margin={economics_small['margin_pct']}%")
    print(f"  Economics (50 clients): R${economics_medium['revenue_brl']}/mo")
    print(f"  Output: {out_path}")

if __name__ == "__main__":
    main()
