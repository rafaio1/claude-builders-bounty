#!/usr/bin/env python3
"""Upstash Redis Free Tier Reseller Scaffold - Zero-Capital Lab v25"""
import json, os, datetime, sys

PILOT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PILOT_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "reseller_scaffold_index.json")

FREE_TIER_LIMITS = {
    "max_commands_per_day": 10000,
    "max_storage_bytes": 268435456,
    "max_databases": 1,
    "eviction_policy": "noeviction (default) or configurable",
    "tls_enabled": True,
    "rest_api_included": True,
    "serverless_cron_included": False,
    "commercial_allowed": True,
    "source_verified": "https://upstash.com/pricing (v25 validation pending)",
    "validation_note": "Limits based on known free tier; requires playwright-cli confirmation before TIER1",
}

PAID_PLAN_BASELINE = {
    "pay_as_you_go_start_usd": 0.0,
    "pro_plan_usd_month": 10.0,
    "included_commands_pro": 1000000,
    "overage_usd_per_1k_commands": 0.0002,
    "sla_uptime": "99.9%",
}

RESELLING_MODEL = {
    "target_segment": "devs BR building serverless apps Next.js/Vercel que precisam de cache/queue sem gerenciar Redis",
    "managed_service_price_brl": 39.90,
    "included_commands_month": 50000,
    "overage_brl_per_1k_commands": 1.50,
    "support_tier": "async (Discord/email)",
    "affiliate_commission_pct": None,
    "multi_tenancy_strategy": "Namespace isolation via key prefix; single DB shared com rate limiting por cliente; REST API proxy para evitar conexao direta",
    "recommended_use_case": "Cache de sessao + fila leve para webhooks; nao usar como DB primario",
}

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    fx_rate = 5.80
    cost_per_client_usd = 0.0
    revenue_brl = RESELLING_MODEL["managed_service_price_brl"]
    margin_brl = revenue_brl - (cost_per_client_usd * fx_rate)
    margin_pct = (margin_brl / revenue_brl * 100) if revenue_brl > 0 else 0
    
    daily_cap = FREE_TIER_LIMITS["max_commands_per_day"]
    monthly_cap = daily_cap * 30
    included = RESELLING_MODEL["included_commands_month"]
    max_clients_theoretical = monthly_cap // included if included > 0 else 0
    
    economics = {
        "revenue_per_client_brl": revenue_brl,
        "cost_per_client_usd": 0.0,
        "gross_margin_brl": round(margin_brl, 2),
        "gross_margin_pct": round(margin_pct, 1),
        "break_even_clients": 1,
        "free_tier_monthly_commands": monthly_cap,
        "max_clients_theoretical": max_clients_theoretical,
        "ceiling_warning": f"Free tier permite ~{max_clients_theoretical} clientes no plano base (50K cmds/mes cada); storage de 256MB limita datasets grandes",
    }
    
    report = {
        "pilot": "upstash-redis-reseller-scaffold",
        "category": "infrastructure_reselling",
        "status": "SCAFFOLD_OK",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "free_tier_limits": FREE_TIER_LIMITS,
        "paid_plan_baseline": PAID_PLAN_BASELINE,
        "reselling_model": RESELLING_MODEL,
        "doc_verification": {
            "doc_verified": False,
            "source_url": "https://upstash.com/pricing",
            "notes": ["Aguardando validacao via playwright-cli dos limites atuais"],
            "commercial_allowed": True,
        },
        "unit_economics": economics,
        "risks": [
            "Storage limitado a 256MB no free tier - inadequado para caches grandes ou filas persistentes",
            "10K comandos/dia pode ser insuficiente para apps com trafego moderado",
            "Sem programa affiliate/reseller publico confirmado",
            "Concorrencia com Vercel KV (mesma infra Upstash) e Cloudflare Workers KV",
            "Single database no free exige namespace discipline rigorosa para multi-tenancy",
        ],
        "next_steps": [
            "Validar limites exatos via playwright-cli open https://upstash.com/pricing",
            "Testar latencia REST API vs TCP direto para cenario serverless BR",
            "Pesquisar programa partner Upstash",
            "Comparar unit economics com Vercel KV e Cloudflare Workers KV",
            "Implementar prototype de namespace proxy com rate limiting",
        ],
    }
    
    with open(OUTPUT_FILE, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"[upstash-reseller] Output: {OUTPUT_FILE}")
    print(f"[upstash-reseller] Margin: R${economics['gross_margin_brl']}/cliente ({economics['gross_margin_pct']}%)")
    print(f"[upstash-reseller] Max clients (theoretical): {economics['max_clients_theoretical']}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
