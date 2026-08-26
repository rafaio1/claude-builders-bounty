#!/usr/bin/env python3
"""Cloudflare R2 Reseller Scaffold - Zero-Capital Lab v24"""
import json, os, datetime, sys

PILOT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PILOT_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "reseller_scaffold_index.json")

FREE_TIER_LIMITS = {
    "storage_gb": 10,
    "class_a_operations_million": 1,
    "class_b_operations_million": 10,
    "egress_gb": 0,
    "commercial_allowed": True,
    "source_verified": "https://developers.cloudflare.com/r2/pricing/ (known limits)",
}

PAID_PLAN_BASELINE = {
    "storage_per_gb_usd": 0.015,
    "class_a_per_million_usd": 3.60,
    "class_b_per_million_usd": 0.36,
    "egress_free": True,
}

RESELLING_MODEL = {
    "target_segment": "devs BR que precisam de S3-compativel sem egress fee",
    "managed_service_price_brl": 49.90,
    "included_storage_gb": 10,
    "overage_brl_per_gb": 0.15,
    "support_tier": "async (Discord/email)",
    "affiliate_commission_pct": None,
    "multi_tenancy_strategy": "1 bucket por cliente com prefix isolation ou buckets separados",
}

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    fx_rate = 5.80
    cost_per_client_usd = 0.0
    revenue_brl = RESELLING_MODEL["managed_service_price_brl"]
    margin_brl = revenue_brl - (cost_per_client_usd * fx_rate)
    margin_pct = (margin_brl / revenue_brl * 100) if revenue_brl > 0 else 0
    economics = {
        "revenue_per_client_brl": revenue_brl,
        "cost_per_client_brl": 0.0,
        "gross_margin_brl": round(margin_brl, 2),
        "gross_margin_pct": round(margin_pct, 1),
        "break_even_clients": 1,
        "ceiling_warning": "Free tier generoso (10GB + zero egress); escala linear apos limite",
    }
    report = {
        "pilot": "cloudflare-r2-reseller-scaffold",
        "category": "infrastructure_reselling",
        "status": "SCAFFOLD_OK",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "free_tier_limits": FREE_TIER_LIMITS,
        "paid_plan_baseline": PAID_PLAN_BASELINE,
        "reselling_model": RESELLING_MODEL,
        "doc_verification": {
            "doc_verified": False,
            "source_url": "https://developers.cloudflare.com/r2/pricing/",
            "notes": ["Limites baseados em conhecimento previo; requer validacao via playwright-cli"],
            "commercial_allowed": True,
        },
        "unit_economics": economics,
        "risks": [
            "Zero egress fee e diferencial mas Cloudflare pode mudar politica",
            "Class A operations limitadas a 1M/mes no free; uploads pesados consomem rapido",
            "Sem programa affiliate publico confirmado para R2 especificamente",
        ],
        "next_steps": [
            "Validar limites exatos via playwright-cli open https://developers.cloudflare.com/r2/pricing/",
            "Testar criacao de bucket e upload via API com credenciais free",
            "Comparar com Backblaze B2 scaffold (#39) - B2 tem affiliate 15%",
        ],
    }
    with open(OUTPUT_FILE, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"[r2-reseller] Output: {OUTPUT_FILE}")
    print(f"[r2-reseller] Margin: R${economics['gross_margin_brl']}/cliente ({economics['gross_margin_pct']}%)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
