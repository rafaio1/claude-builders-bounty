#!/usr/bin/env python3
"""
Cloudflare Workers Free Tier Reselling Scaffold
Zero-Capital Lab - Infrastructure Reselling Pipeline

Validates eligibility, maps free tier limits, estimates margin potential,
and documents reselling constraints for Cloudflare Workers edge compute.

Sources:
- https://developers.cloudflare.com/workers/platform/limits/
- https://www.cloudflare.com/plans/developer-platform/
"""

import json
import os
import datetime
import urllib.request
import re

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

FREE_TIER_LIMITS = {
    "requests_per_day": 100_000,
    "cpu_time_ms": 10,
    "duration_wall_clock_ms": None,  # no hard wall clock limit on free
    "kv_reads_per_day": 100_000,
    "kv_writes_per_day": 1_000,
    "r2_reads_per_month": 10_000_000,
    "r2_writes_per_month": 1_000_000,
    "d1_rows_read_per_day": 5_000_000,
    "d1_rows_written_per_day": 100_000,
    "queues_messages_per_day": 1_000_000,
    "email_routing_forwarded_per_day": 3_000,
}

PAID_PLAN_BASELINE = {
    "name": "Workers Paid ($5/mo)",
    "included_requests": 10_000_000,
    "overage_per_million": 0.30,
    "kv_reads_included": 10_000_000,
    "kv_overage_per_million": 0.36,
}

RESELLING_MODEL = {
    "strategy": "Managed Edge Deployment Service",
    "target_customer": "Small businesses needing serverless APIs without DevOps",
    "value_prop": "Deploy + monitor + custom domain + SSL for fixed monthly fee",
    "suggested_price_brl": 49.90,
    "cost_to_provider_brl": 0.00,  # free tier covers most small clients
    "estimated_margin_pct": 100.0,
    "scale_constraint": "Free tier is per-account; each client needs separate CF account or sub-account via API",
    "tos_compliance_note": "Reselling requires checking Cloudflare ToS Section 2.8 (Acceptable Use). Managed services are generally permitted; pure resale of raw compute may require partner agreement.",
}

def validate_free_tier_docs():
    """Attempt to fetch current limits from official docs."""
    result = {"source_verified": False, "url": "", "extracted_limits": {}, "error": None}
    try:
        url = "https://developers.cloudflare.com/workers/platform/limits/"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ZeroCapitalLab/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
            result["url"] = url
            # Extract request limit
            m = re.search(r"(\d[\d,]*)\s*(?:free\s+)?requests?\s*/\s*day", html, re.I)
            if m:
                val = int(m.group(1).replace(",", ""))
                result["extracted_limits"]["requests_per_day"] = val
                result["source_verified"] = True
            # Extract CPU time
            m2 = re.search(r"(\d+)\s*ms\s*(?:of\s+)?CPU\s*time", html, re.I)
            if m2:
                result["extracted_limits"]["cpu_time_ms"] = int(m2.group(1))
            # KV reads
            m3 = re.search(r"(\d[\d,]*)\s*(?:free\s+)?reads?\s*/\s*day.*KV", html, re.I | re.S)
            if not m3:
                m3 = re.search(r"KV.*?(\d[\d,]*)\s*reads?\s*/\s*day", html, re.I | re.S)
            if m3:
                result["extracted_limits"]["kv_reads_per_day"] = int(m3.group(1).replace(",", ""))
    except Exception as e:
        result["error"] = str(e)
    return result

def estimate_unit_economics(monthly_clients: int = 10):
    """Estimate monthly economics for managed service model."""
    revenue = monthly_clients * RESELLING_MODEL["suggested_price_brl"]
    cost = 0.0  # free tier assumed sufficient for <100K req/day/client
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
        "pilot": "cloudflare-workers-reseller-scaffold",
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
            "Free tier limits are per-account; multi-tenant requires account-per-client or Enterprise plan",
            "Cloudflare ToS may restrict pure resale; managed service framing recommended",
            "No SLA on free tier; production clients need paid plan fallback",
            "Custom domains on free tier limited to workers.dev or proxied DNS",
        ],
        "next_steps": [
            "Validate ToS Section 2.8 for managed service compliance",
            "Build account provisioning script via Cloudflare API",
            "Create monitoring dashboard for per-client usage vs free tier limits",
            "Draft customer-facing pricing page and onboarding flow",
        ],
    }
    
    out_path = os.path.join(OUTPUT_DIR, "reseller_scaffold_index.json")
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"[OK] Scaffold generated at {ts}")
    print(f"  Doc verified: {doc_validation['source_verified']}")
    print(f"  Requests/day extracted: {doc_validation['extracted_limits'].get('requests_per_day', 'N/A')}")
    print(f"  Economics (10 clients): R${economics_small['revenue_brl']}/mo margin={economics_small['margin_pct']}%")
    print(f"  Economics (50 clients): R${economics_medium['revenue_brl']}/mo")
    print(f"  Output: {out_path}")

if __name__ == "__main__":
    main()
