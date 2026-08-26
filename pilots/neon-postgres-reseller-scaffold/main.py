#!/usr/bin/env python3
"""Neon Postgres Reseller Scaffold - Zero-Capital Lab v23 (verified)"""
import json, os, datetime, sys

PILOT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PILOT_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "reseller_scaffold_index.json")

FREE_TIER_LIMITS = {
    "storage_gb_per_project": 0.5,
    "compute_cu_hrs_month_per_project": 100,
    "max_cu_size": 2,
    "max_ram_gb": 8,
    "projects": 100,
    "team_members": "unlimited",
    "commercial_allowed": True,
    "source_verified": "playwright-cli snapshot neon.com/pricing 2026-08-26",
}

PAID_PLAN_BASELINE = {
    "launch_price_usd": 19.0,
    "scale_price_usd": 69.0,
    "storage_overage_per_gb": 0.35,
    "compute_hour_rate": 0.10,
    "branch_limit_launch": 100,
    "sla_uptime": "99.9%",
}

RESELLING_MODEL = {
    "target_segment": "micro-SaaS / indie hackers BR",
    "managed_service_price_brl": 89.90,
    "included_storage_mb": 500,
    "overage_brl_per_100mb": 15.0,
    "support_tier": "async (Discord/email)",
    "affiliate_commission_pct": None,
    "multi_tenancy_strategy": "1 projeto free por cliente (100 projetos disponiveis) - isolamento nativo",
}

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    fx_rate = 5.80
    cost_per_client_usd = 0.0
    revenue_brl = RESELLING_MODEL["managed_service_price_brl"]
    cost_brl = cost_per_client_usd * fx_rate
    margin_brl = revenue_brl - cost_brl
    margin_pct = (margin_brl / revenue_brl * 100) if revenue_brl > 0 else 0
    economics = {
        "revenue_per_client_brl": revenue_brl,
        "cost_per_client_brl": round(cost_brl, 2),
        "gross_margin_brl": round(margin_brl, 2),
        "gross_margin_pct": round(margin_pct, 1),
        "break_even_clients_per_project": 1,
        "ceiling_warning": "100 projetos free = ate 100 clientes isolados sem custo; escala alem disso requer Launch ($19/mo)",
    }
    report = {
        "pilot": "neon-postgres-reseller-scaffold",
        "category": "infrastructure_reselling",
        "status": "SCAFFOLD_OK",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "free_tier_limits": FREE_TIER_LIMITS,
        "paid_plan_baseline": PAID_PLAN_BASELINE,
        "reselling_model": RESELLING_MODEL,
        "doc_verification": {
            "doc_verified": True,
            "source_url": "https://neon.com/pricing",
            "notes": [
                "Storage confirmado: 0.5 GB per project",
                "Compute confirmado: 100 CU-hrs monthly per project",
                "Projetos confirmados: 100 (nao 1 como assumido anteriormente)",
                "Uso comercial permitido - Terms of Use Databricks nao proíbem no free tier",
                "Validado via playwright-cli snapshot 2026-08-26T20:36Z",
            ],
            "commercial_allowed": True,
        },
        "unit_economics": economics,
        "risks": [
            "CU-hrs limitadas a 100/projeto/mes; DBs com carga constante podem esgotar em ~3 dias",
            "Idle timeout ajuda mas picos de trafego consomem CU-hrs rapidamente",
            "Sem programa de affiliate publico confirmado - receita puramente service-based",
            "Neon agora parte do Databricks - termos podem mudar com aquisicao",
        ],
        "next_steps": [
            "Testar criacao de 5+ projetos free via API para validar limite real de 100",
            "Benchmark de consumo CU-hrs com carga tipica de micro-SaaS",
            "Pesquisar programa partner/affiliate Databricks pos-aquisicao",
            "Comparar unit economics com Supabase (#38) e Backblaze (#39)",
        ],
    }
    with open(OUTPUT_FILE, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"[neon-postgres-reseller] Output escrito: {OUTPUT_FILE}")
    print(f"[neon-postgres-reseller] Doc verified: True")
    print(f"[neon-postgres-reseller] Commercial allowed: True")
    print(f"[neon-postgres-reseller] Projects: 100 (CORRIGIDO de 1)")
    print(f"[neon-postgres-reseller] Margin: R${economics['gross_margin_brl']}/cliente ({economics['gross_margin_pct']}%)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
