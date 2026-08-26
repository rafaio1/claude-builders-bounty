#!/usr/bin/env python3
"""
Render Free Static Site Hosting Reselling Scaffold
Zero-Capital Lab - Infrastructure Reselling Pipeline

Validates eligibility, maps free tier limits, estimates margin potential,
and documents reselling constraints for Render static site hosting.

Sources:
- https://render.com/pricing
- https://render.com/docs/free
"""

import json
import os
import datetime
import urllib.request
import re

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

FREE_TIER_LIMITS = {
    "static_sites": "unlimited",
    "bandwidth_gb_month": 100,
    "build_minutes_month": None,  # not explicitly limited for static sites
    "custom_domains": True,
    "ssl_certificates": True,
    "auto_deploy_from_git": True,
    "preview_environments": False,  # paid feature
    "commercial_usage_allowed": True,
}

PAID_PLAN_BASELINE = {
    "name": "Pro ($19/mo per user)",
    "bandwidth_gb_month": 1_000,
    "preview_environments": True,
    "priority_support": True,
    "sso_saml": True,
}

RESELLING_MODEL = {
    "strategy": "Managed Static Site Hosting for SMBs",
    "target_customer": "Small businesses needing landing pages + blogs without WordPress complexity",
    "value_prop": "Deploy + custom domain + SSL + CDN + form integration + analytics setup",
    "suggested_price_brl": 39.90,
    "cost_to_provider_brl": 0.00,
    "estimated_margin_pct": 100.0,
    "scale_constraint": "Free tier is generous for static sites; main limit is bandwidth (100GB/mo). Heavy media sites may exceed.",
    "tos_compliance_note": "Render permits commercial usage on free tier. Managed hosting services are allowed. No partner program required.",
}

def validate_free_tier_docs():
    """Attempt to fetch current limits from official docs."""
    result = {"source_verified": False, "url": "", "extracted_limits": {}, "error": None}
    try:
        url = "https://render.com/pricing"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ZeroCapitalLab/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
            result["url"] = url
            m = re.search(r"(\d+)\s*(?:GB|gb)\s*(?:of\s+)?bandwidth", html, re.I)
            if m:
                result["extracted_limits"]["bandwidth_gb_month"] = int(m.group(1))
                result["source_verified"] = True
            m2 = re.search(r"unlimited.*?static\s*sites?", html, re.I)
            if m2:
                result["extracted_limits"]["static_sites"] = "unlimited"
            m3 = re.search(r"commercial.*?allowed|free.*?commercial", html, re.I)
            if m3:
                result["extracted_limits"]["commercial_usage_allowed"] = True
    except Exception as e:
        result["error"] = str(e)
    return result

def estimate_unit_economics(monthly_clients: int = 10):
    """Estimate monthly economics for managed static hosting model."""
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
        "pilot": "render-static-reseller-scaffold",
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
            "Bandwidth limit (100GB/mo) shared across all sites on free account; heavy traffic clients may exceed",
            "No preview environments on free tier; client approval workflow requires manual staging",
            "Build times may be slower on free tier during peak hours; no priority queue",
            "Custom domains require DNS configuration per client; no bulk provisioning API",
            "No native form handling; requires external service (Formspree, Netlify Forms alternative)",
        ],
        "next_steps": [
            "Build site provisioning script via Render API",
            "Create automated deploy pipeline for client repos (GitHub/GitLab integration)",
            "Design form handling integration with free-tier compatible services",
            "Test bandwidth monitoring and alerting for multi-client accounts",
            "Draft migration playbook from free to Pro for growing clients",
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
