#!/usr/bin/env python3
"""Upstash Redis Free Tier Reseller Scaffold - Zero-Capital Lab v25"""
import json, os, datetime, sys

PILOT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PILOT_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "reseller_scaffold_index.json")

FREE_TIER_LIMITS = {
    "monthly_commands": 500000,
    "max_storage_bytes": 268435456,
    "monthly_bandwidth_gb": 10,
    "max_databases": 1,
    "eviction_policy": "noeviction (default) or configurable",
    "tls_enabled": True,
    "rest_api_included": True,
    "serverless_cron_included": False,
    "commercial_allowed": True,
    "source_verified": "https://upstash.com/pricing/redis (v25 validated via playwright-cli)",
    "validation_note": "Free tier is 500K commands/month (NOT 10K/day), 256MB storage, 10GB bandwidth. Validated Aug 2026.",
}

PAID_PLAN_BASELINE = {
    "pay_as_you_go_usd_per_100k_commands": 0.20,
    "fixed_250mb_usd_month": 10.0,
    "fixed_unlimited_commands": True,
    "prod_pack_addon_usd_month": 200.0,
    "sla_uptime": "99.9% (Prod Pack only)",
}

RESELLING_MODEL = {
    "target_segment": "devs BR building serverless apps Next.js/Vercel que precisam de cache/queue sem gerenciar Redis",
    "managed_service_price_brl": 39.90,
    "included_commands_month": 100000,
    "overage_brl_per_1k_commands": 1.20,
    "support_tier": "async (Discord/email)",
    "affiliate_commission_pct": None,
    "multi_tenancy_strategy": "Namespace isolation via key prefix; single DB shared com rate limiting por cliente; REST API proxy para evitar conexao direta",
    "recommended_use_case": "Cache de sessao + fila leve para webhooks; nao usar como DB primario",
    "free_tier_advantage": "500K cmds/mes permite ate 5 clientes no plano base (100K cada) com margem total",
}

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    fx_rate = 5.80
    cost_per_client_usd = 0.0
    revenue_brl = RESELLING_MODEL["managed_service_price_brl"]
    margin_brl = revenue_brl - (cost_per_client_usd * fx_rate)
    margin_pct = (margin_brl / revenue_brl * 100) if revenue_brl > 0 else 0
    
    monthly_cap = FREE_TIER_LIMITS["monthly_commands"]
    included = RESELLING_MODEL["included_commands_month"]
    max_clients_theoretical = monthly_cap // included if included > 0 else 0
    
    economics = {
        "revenue_per_client_brl": revenue_brl,
        "cost_per_client_usd": 0.0,
        "gross_margin_brl": round(margin_brl, 2),
        "gross_margin_pct": round(margin_pct, 1),
        "break_even_clients": 1,
        "free_tier_monthly_commands": monthly_cap,
        "free_tier_bandwidth_gb": FREE_TIER_LIMITS["monthly_bandwidth_gb"],
        "max_clients_theoretical": max_clients_theoretical,
        "ceiling_warning": f"Free tier permite ~{max_clients_theoretical} clientes no plano base (100K cmds/mes cada); storage 256MB e bandwidth 10GB limitam datasets grandes",
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
            "doc_verified": True,
            "source_url": "https://upstash.com/pricing/redis",
            "notes": ["Validado v25 via playwright-cli: 500K cmds/mes, 256MB storage, 10GB bandwidth, 1 DB free"],
            "commercial_allowed": True,
        },
        "unit_economics": economics,
        "risks": [
            "Storage limitado a 256MB no free tier - inadequado para caches grandes ou filas persistentes",
            "Bandwidth de 10GB/mes pode ser gargalo para apps com payloads grandes",
            "Sem programa affiliate/reseller publico confirmado",
            "Concorrencia com Vercel KV (mesma infra Upstash) e Cloudflare Workers KV",
            "Single database no free exige namespace discipline rigorosa para multi-tenancy",
        ],
        "next_steps": [
            "Testar latencia REST API vs TCP direto para cenario serverless BR",
            "Implementar namespace proxy com rate limiting por cliente (100K cmds/mes cada)",
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
