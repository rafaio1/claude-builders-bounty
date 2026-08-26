#!/usr/bin/env python3
"""Fly.io MicroVM Reseller Scaffold - Zero-Capital Lab v25 (TRIAL ONLY - NOT VIABLE)"""
import json, os, datetime, sys

PILOT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PILOT_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "reseller_scaffold_index.json")

FREE_TIER_LIMITS = {
    "type": "TIME_LIMITED_TRIAL_ONLY",
    "trial_duration_days": 7,
    "trial_vm_hours_total": 2,
    "trial_max_machines": 10,
    "trial_max_vcpu_per_machine": 2,
    "trial_volume_storage_gb": 20,
    "permanent_free_tier": False,
    "auto_stop_after_5min_idle": True,
    "dedicated_ipv4_in_trial": False,
    "performance_cpu_in_trial": False,
    "commercial_allowed": False,
    "source_verified": "https://fly.io/docs/about/free-trial/ (v25 validated via playwright-cli)",
    "validation_note": "CRITICAL: Fly.io has NO permanent free tier. Only 7-day/2-hour trial. Apps stop when trial ends or payment method added. NOT VIABLE for zero-capital reselling.",
}

PAID_PLAN_BASELINE = {
    "shared_cpu_1x_usd_month": 1.94,
    "shared_cpu_2x_usd_month": 3.88,
    "performance_cpu_1x_usd_month": 7.00,
    "persistent_storage_usd_gb_month": 0.15,
    "outbound_bandwidth_usd_gb": 0.02,
    "sla_uptime": "99.9% (paid plans)",
}

RESELLING_MODEL = {
    "target_segment": "INVIÁVEL - Fly.io não possui free tier permanente",
    "managed_service_price_brl": 0.0,
    "included_vms": 0,
    "included_storage_gb": 0,
    "overage_brl_per_vm": 0.0,
    "support_tier": "N/A",
    "affiliate_commission_pct": None,
    "multi_tenancy_strategy": "INVIÁVEL - Trial de 7 dias/2 horas não suporta multi-tenancy ou operação contínua",
    "recommended_use_case": "N/A - Migrar para Railway ($5 trial credit + paid), Render (free static + paid dynos), ou Koyeb (free tier permanente)",
    "disposition": "REJECT_TIER0",
}

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    economics = {
        "revenue_per_client_brl": 0.0,
        "cost_per_client_usd": 0.0,
        "gross_margin_brl": 0.0,
        "gross_margin_pct": 0.0,
        "break_even_clients": 0,
        "max_clients_free_tier": 0,
        "storage_per_client_gb": 0,
        "ceiling_warning": "INVIÁVEL: Fly.io não tem free tier permanente. Trial de 7 dias/2 horas não permite operação contínua zero-capital.",
    }
    
    report = {
        "pilot": "fly-io-reseller-scaffold",
        "category": "infrastructure_reselling",
        "status": "SCAFFOLD_REJECTED",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "free_tier_limits": FREE_TIER_LIMITS,
        "paid_plan_baseline": PAID_PLAN_BASELINE,
        "reselling_model": RESELLING_MODEL,
        "doc_verification": {
            "doc_verified": True,
            "source_url": "https://fly.io/docs/about/free-trial/",
            "notes": ["Validado v25: NÃO há free tier permanente. Apenas trial 7 dias/2 horas. Scaffold REJEITADO para TIER0."],
            "commercial_allowed": False,
        },
        "unit_economics": economics,
        "risks": [
            "NÃO HÁ FREE TIER PERMANENTE - apenas trial de 7 dias/2 horas",
            "Apps param automaticamente após trial expirar ou ao adicionar cartão",
            "Zero-capital impossível sem método de pagamento vinculado",
            "Modelo de reselling inviável sem permanência garantida",
        ],
        "next_steps": [
            "Migrar esforço para alternativas com free tier permanente: Koyeb, Render, Railway (com créditos)",
            "Remover fly-io-reseller-scaffold do pipeline TIER0 ativo",
            "Documentar lição aprendida: verificar existência de free tier ANTES de criar scaffold",
        ],
    }
    
    with open(OUTPUT_FILE, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"[flyio-reseller] Output: {OUTPUT_FILE}")
    print(f"[flyio-reseller] Status: SCAFFOLD_REJECTED (no permanent free tier)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
