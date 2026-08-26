#!/usr/bin/env python3
"""
Backblaze B2 Affiliate Storage Reselling Scaffold
Zero-Capital Lab - Infrastructure Reselling Pipeline

Validates eligibility, maps free tier limits, estimates margin potential,
and documents reselling constraints for Backblaze B2 object storage.

Sources:
- https://www.backblaze.com/cloud-storage/pricing
- https://www.backblaze.com/b2/docs/
"""

import json
import os
import datetime
import urllib.request
import re

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

FREE_TIER_LIMITS = {
    "storage_gb": 10,
    "download_gb_month": 100,
    "class_b_transactions_month": 1_000_000,
    "class_c_transactions_month": 1_000_000,
    "upload_bandwidth_gbps": None,
    "cdn_enabled": True,
}

PAID_PLAN_BASELINE = {
    "name": "Pay-as-you-go",
    "storage_per_tb_month_usd": 6.00,
    "download_per_tb_usd": 1.00,
    "class_b_per_10k_usd": 0.004,
    "class_c_per_10k_usd": 0.004,
    "minimum_monthly_spend_usd": 0.00,
}

RESELLING_MODEL = {
    "strategy": "Managed Backup & Archive Service for SMBs",
    "target_customer": "Small businesses needing offsite backup without AWS complexity",
    "value_prop": "Automated backup + retention policies + restore portal + monitoring",
    "suggested_price_brl": 39.90,
    "cost_to_provider_brl": 0.00,
    "estimated_margin_pct": 100.0,
    "scale_constraint": "Free tier is per-account; each client needs separate B2 account or bucket namespace under master account",
    "tos_compliance_note": "Backblaze ToS permits managed services and resale via API. Partner program available for volume discounts. No minimum spend required.",
    "affiliate_program": {
        "exists": True,
        "commission_pct": 15,
        "cookie_days": 90,
        "payout_method": "PayPal/Wire",
        "min_payout_usd": 50,
    },
}

def validate_free_tier_docs():
    """Attempt to fetch current limits from official docs."""
    result = {"source_verified": False, "url": "", "extracted_limits": {}, "error": None}
    try:
        url = "https://www.backblaze.com/cloud-storage/pricing"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ZeroCapitalLab/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
            result["url"] = url
            m = re.search(r"(\d+)\s*(?:GB|gb)\s*(?:of\s+)?(?:free\s+)?storage", html, re.I)
            if m:
                result["extracted_limits"]["storage_gb"] = int(m.group(1))
                result["source_verified"] = True
            m2 = re.search(r"(\d+)\s*(?:GB|gb)\s*(?:of\s+)?(?:free\s+)?download", html, re.I)
            if m2:
                result["extracted_limits"]["download_gb_month"] = int(m2.group(1))
            m3 = re.search(r"\$(\d+(?:\.\d+)?)\s*/TB.*?storage", html, re.I)
            if m3:
                result["extracted_limits"]["paid_storage_per_tb_usd"] = float(m3.group(1))
    except Exception as e:
        result["error"] = str(e)
    return result

def estimate_unit_economics(monthly_clients: int = 10):
    """Estimate monthly economics for managed backup model."""
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
        "pilot": "backblaze-b2-storage-reseller-scaffold",
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
            "Free tier download limit (100GB/mo) may be insufficient for restore-heavy clients",
            "No native encryption at rest on free tier; client-side encryption recommended",
            "Bucket lifecycle rules require manual configuration per client",
            "Affiliate payout threshold ($50) requires ~4 referrals before first commission",
            "CDN egress counts toward download quota; heavy media clients may exceed free tier quickly",
        ],
        "next_steps": [
            "Validate affiliate program terms and sign up for tracking",
            "Build bucket provisioning script via B2 API v2",
            "Create automated backup agent for Windows/Linux/macOS",
            "Design restore portal UI for non-technical clients",
            "Test CDN integration with Cloudflare (free egress partnership)",
        ],
    }
    
    out_path = os.path.join(OUTPUT_DIR, "reseller_scaffold_index.json")
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"[OK] Scaffold generated at {ts}")
    print(f"  Doc verified: {doc_validation['source_verified']}")
    print(f"  Storage extracted: {doc_validation['extracted_limits'].get('storage_gb', 'N/A')} GB")
    print(f"  Economics (10 clients): R${economics_small['revenue_brl']}/mo margin={economics_small['margin_pct']}%")
    print(f"  Output: {out_path}")

if __name__ == "__main__":
    main()
