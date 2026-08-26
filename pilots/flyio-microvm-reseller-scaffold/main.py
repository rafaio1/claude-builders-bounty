#!/usr/bin/env python3
"""
Fly.io Free Tier MicroVM Reselling Scaffold
Zero-Capital Lab - Infrastructure Reselling Pipeline

Validates eligibility, maps free tier limits, estimates margin potential,
and documents reselling constraints for Fly.io shared-cpu microVMs.

Sources:
- https://fly.io/docs/about/pricing/
- https://fly.io/docs/litefs/
"""

import json
import os
import datetime
import urllib.request
import re

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

FREE_TIER_LIMITS = {
    "shared_cpu_256mb_vms": 3,
    "persistent_storage_gb": 3,
    "outbound_bandwidth_gb_month": 100,
    "inbound_bandwidth_gb_month": None,  # free
    "ipv4_addresses": 1,
    "ipv6_addresses": None,  # unlimited
    "max_app_count": None,  # not explicitly limited but VM count constrained
    "regions_allowed": True,
    "commercial_usage_allowed": True,
}

PAID_PLAN_BASELINE = {
    "name": "Pay-as-you-go",
    "shared_cpu_256mb_per_month_usd": 1.94,
    "persistent_storage_per_gb_month_usd": 0.15,
    "outbound_bandwidth_per_gb_usd": 0.02,
    "ipv4_address_per_month_usd": 2.00,
}

RESELLING_MODEL = {
    "strategy": "Managed Edge App Hosting for SMBs",
    "target_customer": "Small businesses needing always-on APIs/bots without cloud complexity",
    "value_prop": "Deploy + custom domain + SSL + monitoring + regional proximity + persistent storage",
    "suggested_price_brl": 29.90,
    "cost_to_provider_brl": 0.00,
    "estimated_margin_pct": 100.0,
    "scale_constraint": "Free tier allows only 3 VMs total; each client needs dedicated VM or multi-tenant architecture within single VM",
    "tos_compliance_note": "Fly.io permits commercial usage on free tier. Reselling as managed service is allowed. No partner program required for basic resale.",
}

def validate_free_tier_docs():
    """Attempt to fetch current limits from official docs."""
    result = {"source_verified": False, "url": "", "extracted_limits": {}, "error": None}
    try:
        url = "https://fly.io/docs/about/pricing/"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ZeroCapitalLab/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
            result["url"] = url
            m = re.search(r"(\d+)\s*(?:free\s+)?(?:shared|cpu).*?(?:256|512)\s*MB.*?VMs?", html, re.I)
            if m:
                result["extracted_limits"]["shared_cpu_256mb_vms"] = int(m.group(1))
                result["source_verified"] = True
            m2 = re.search(r"(\d+)\s*(?:GB|gb)\s*(?:of\s+)?(?:persistent|volume|storage)", html, re.I)
            if m2:
                result["extracted_limits"]["persistent_storage_gb"] = int(m2.group(1))
            m3 = re.search(r"(\d+)\s*(?:GB|gb)\s*(?:of\s+)?outbound.*?bandwidth", html, re.I)
            if m3:
                result["extracted_limits"]["outbound_bandwidth_gb_month"] = int(m3.group(1))
    except Exception as e:
        result["error"] = str(e)
    return result

def estimate_unit_economics(monthly_clients: int = 3):
    """Estimate monthly economics for managed edge hosting model."""
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
    economics_small = estimate_unit_economics(3)
    economics_medium = estimate_unit_economics(10)
    economics_scale = estimate_unit_economics(50)
    
    report = {
        "pilot": "flyio-microvm-reseller-scaffold",
        "category": "infrastructure_reselling",
        "timestamp": ts,
        "status": "SCAFFOLD_OK",
        "free_tier_limits": FREE_TIER_LIMITS,
        "paid_plan_baseline": PAID_PLAN_BASELINE,
        "reselling_model": RESELLING_MODEL,
        "doc_validation": doc_validation,
        "unit_economics": {
            "small_3_clients": economics_small,
            "medium_10_clients": economics_medium,
            "scale_50_clients": economics_scale,
        },
        "risks": [
            "Only 3 free VMs total; hard ceiling on number of isolated client deployments",
            "Shared CPU performance varies; noisy neighbor effect possible on free tier",
            "Persistent storage (3GB) insufficient for database-heavy apps; requires external DB",
            "Outbound bandwidth (100GB/mo) shared across all VMs; media-heavy clients may exceed",
            "No SLA on free tier; production outages have no recourse or priority support",
            "IPv4 address costs $2/mo after first free one; multi-client IPv4 requires paid upgrade",
        ],
        "next_steps": [
            "Build app provisioning script via flyctl CLI/API",
            "Create multi-tenant architecture template to serve multiple clients per VM",
            "Design monitoring dashboard for per-client resource usage vs free tier limits",
            "Test LiteFS for distributed SQLite across regions on free tier",
            "Draft migration playbook from free to pay-as-you-go for growing clients",
        ],
    }
    
    out_path = os.path.join(OUTPUT_DIR, "reseller_scaffold_index.json")
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"[OK] Scaffold generated at {ts}")
    print(f"  Doc verified: {doc_validation['source_verified']}")
    print(f"  Free VMs extracted: {doc_validation['extracted_limits'].get('shared_cpu_256mb_vms', 'N/A')}")
    print(f"  Economics (3 clients): R${economics_small['revenue_brl']}/mo margin={economics_small['margin_pct']}%")
    print(f"  WARNING: Only 3 free VMs total - hard ceiling on isolated deployments")
    print(f"  Output: {out_path}")

if __name__ == "__main__":
    main()
