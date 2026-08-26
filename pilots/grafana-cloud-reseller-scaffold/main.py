#!/usr/bin/env python3
"""Grafana Cloud Reseller Scaffold - Zero-Capital Lab v24"""
import json, os, datetime, sys

PILOT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PILOT_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "reseller_scaffold_index.json")

FREE_TIER_LIMITS = {
    "metrics_series": 10000,
    "logs_gb_month": 50,
    "traces_gb_month": 50,
    "profiles_cpu_hours": 100,
    "users": 3,
    "retention_days": 30,
    "commercial_allowed": True,
    "source_verified": "https://grafana.com/pricing/ (known limits)",
}

PAID_PLAN_BASELINE = {
    "pro_price_usd_per_user": 8.0,
    "advanced_price_usd_per_user": 29.0,
    "extra_metrics_per_1k_usd": 0.50,
    "extra_logs_per_gb_usd": 0.30,
    "sla_uptime": "99.5%",
}

RESELLING_MODEL = {
    "target_segment": "startups BR que precisam de observabilidade sem self-host",
    "managed_service_price_brl": 79.90,
    "included_users": 3,
    "overage_brl_per_user": 35.0,
    "support_tier": "async (Discord/email)",
    "affiliate_commission_pct": None,
    "multi_tenancy_strategy": "1 org Grafana por cliente; free tier cobre ate 3 usuarios",
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
        "ceiling_warning": "Free tier limitado a 3 usuarios e 10K series; crescimento exige Pro ($8/user/mo)",
    }
    report = {
        "pilot": "grafana-cloud-reseller-scaffold",
        "category": "infrastructure_reselling",
        "status": "SCAFFOLD_OK",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "free_tier_limits": FREE_TIER_LIMITS,
        "paid_plan_baseline": PAID_PLAN_BASELINE,
        "reselling_model": RESELLING_MODEL,
        "doc_verification": {
            "doc_verified": False,
            "source_url": "https://grafana.com/pricing/",
            "notes": ["Limites baseados em conhecimento previo; requer validacao via playwright-cli"],
            "commercial_allowed": True,
        },
        "unit_economics": economics,
        "risks": [
            "Free tier limitado a 3 usuarios - teto baixo para revenda B2B",
            "10K metric series pode ser insuficiente para apps com muitas instancias",
            "Sem programa affiliate publico confirmado para Grafana Cloud",
            "Concorrencia forte com Datadog/New Relic que tem free tiers tambem",
        ],
        "next_steps": [
            "Validar limites exatos via playwright-cli open https://grafana.com/pricing/",
            "Testar criacao de org e convite de usuarios via API",
            "Pesquisar programa partner Grafana Labs",
            "Comparar com alternativas open-source self-hosted (Prometheus/Loki)",
        ],
    }
    with open(OUTPUT_FILE, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"[grafana-reseller] Output: {OUTPUT_FILE}")
    print(f"[grafana-reseller] Margin: R${economics['gross_margin_brl']}/cliente ({economics['gross_margin_pct']}%)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
