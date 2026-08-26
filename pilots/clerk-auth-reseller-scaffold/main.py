#!/usr/bin/env python3
"""Clerk Auth Reseller Scaffold - Zero-Capital Lab v24"""
import json, os, datetime, sys

PILOT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PILOT_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "reseller_scaffold_index.json")

FREE_TIER_LIMITS = {
    "mau": 10000,
    "social_providers": "all",
    "custom_domains": 1,
    "webhooks": True,
    "commercial_allowed": True,
    "source_verified": "https://clerk.com/pricing (known limits)",
}

PAID_PLAN_BASELINE = {
    "pro_price_usd": 25.0,
    "pro_mau": 100000,
    "extra_per_1k_mau_usd": 1.0,
    "sla_uptime": "99.9%",
}

RESELLING_MODEL = {
    "target_segment": "startups BR que precisam de auth sem self-host",
    "managed_service_price_brl": 69.90,
    "included_mau": 10000,
    "overage_brl_per_1k_mau": 8.0,
    "support_tier": "async (Discord/email)",
    "affiliate_commission_pct": None,
    "multi_tenancy_strategy": "1 Clerk instance por app; free tier cobre ate 10K MAU",
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
        "ceiling_warning": "Free tier generoso (10K MAU); escala apos limite requer Pro ($25/mo)",
    }
    report = {
        "pilot": "clerk-auth-reseller-scaffold",
        "category": "infrastructure_reselling",
        "status": "SCAFFOLD_OK",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "free_tier_limits": FREE_TIER_LIMITS,
        "paid_plan_baseline": PAID_PLAN_BASELINE,
        "reselling_model": RESELLING_MODEL,
        "doc_verification": {
            "doc_verified": False,
            "source_url": "https://clerk.com/pricing",
            "notes": ["Limites baseados em conhecimento previo; requer validacao via playwright-cli"],
            "commercial_allowed": True,
        },
        "unit_economics": economics,
        "risks": [
            "10K MAU e teto alto para free tier mas apps virais podem atingir rapido",
            "Sem programa affiliate publico confirmado",
            "Concorrencia com Auth0/Supabase Auth/Firebase Auth que tambem tem free tiers",
            "Clerk foca em Next.js/React - menos flexivel para stacks nao-JS",
        ],
        "next_steps": [
            "Validar limites exatos via playwright-cli open https://clerk.com/pricing",
            "Testar criacao de instancia e integracao via API com credenciais free",
            "Comparar unit economics com Supabase Auth (ja incluso no scaffold #38)",
        ],
    }
    with open(OUTPUT_FILE, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"[clerk-reseller] Output: {OUTPUT_FILE}")
    print(f"[clerk-reseller] Margin: R${economics['gross_margin_brl']}/cliente ({economics['gross_margin_pct']}%)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
