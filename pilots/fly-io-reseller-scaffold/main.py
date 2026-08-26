#!/usr/bin/env python3
"""Fly.io MicroVM Free Tier Reseller Scaffold - Zero-Capital Lab v25"""
import json, os, datetime, sys

PILOT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PILOT_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "reseller_scaffold_index.json")

FREE_TIER_LIMITS = {
    "shared_cpu_vms": 3,
    "ram_per_vm_mb": 256,
    "persistent_storage_gb": 3,
    "outbound_bandwidth_gb_month": 100,
    "inbound_bandwidth_gb_month": None,
    "ipv4_shared": True,
    "ipv6_dedicated": True,
    "regions_available": "global (30+ regions)",
    "commercial_allowed": True,
    "source_verified": "https://fly.io/docs/about/pricing/ (v25 validation pending)",
    "validation_note": "Free tier limits based on known allowances; requires playwright-cli confirmation",
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
    "target_segment": "devs BR deployando apps globais com baixa latencia sem gerenciar k8s/VPS",
    "managed_service_price_brl": 29.90,
    "included_vms": 1,
    "included_storage_gb": 1,
    "overage_brl_per_vm": 15.00,
    "support_tier": "async (Discord/email)",
    "affiliate_commission_pct": None,
    "multi_tenancy_strategy": "Cada cliente em VM isolada no free tier (ate 3 clientes); storage compartilhado via volumes nomeados",
    "recommended_use_case": "APIs leves, workers background, bots Discord/Telegram com persistencia minima",
}

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    fx_rate = 5.80
    cost_per_client_usd = 0.0
    revenue_brl = RESELLING_MODEL["managed_service_price_brl"]
    margin_brl = revenue_brl - (cost_per_client_usd * fx_rate)
    margin_pct = (margin_brl / revenue_brl * 100) if revenue_brl > 0 else 0
    
    max_clients = FREE_TIER_LIMITS["shared_cpu_vms"]
    storage_per_client = FREE_TIER_LIMITS["persistent_storage_gb"] // max_clients if max_clients > 0 else 0
    
    economics = {
        "revenue_per_client_brl": revenue_brl,
        "cost_per_client_usd": 0.0,
        "gross_margin_brl": round(margin_brl, 2),
        "gross_margin_pct": round(margin_pct, 1),
        "break_even_clients": 1,
        "max_clients_free_tier": max_clients,
        "storage_per_client_gb": storage_per_client,
        "ceiling_warning": f"Free tier permite exatamente {max_clients} VMs; storage de {FREE_TIER_LIMITS['persistent_storage_gb']}GB total limita a {storage_per_client}GB/cliente",
    }
    
    report = {
        "pilot": "fly-io-reseller-scaffold",
        "category": "infrastructure_reselling",
        "status": "SCAFFOLD_OK",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "free_tier_limits": FREE_TIER_LIMITS,
        "paid_plan_baseline": PAID_PLAN_BASELINE,
        "reselling_model": RESELLING_MODEL,
        "doc_verification": {
            "doc_verified": False,
            "source_url": "https://fly.io/docs/about/pricing/",
            "notes": ["Aguardando validacao via playwright-cli dos limites atuais"],
            "commercial_allowed": True,
        },
        "unit_economics": economics,
        "risks": [
            "Apenas 3 VMs no free tier - teto absoluto de 3 clientes simultaneos",
            "256MB RAM por VM limita severamente apps Node.js/Python pesados",
            "Storage persistente de 3GB total inadequado para DBs ou uploads",
            "Fly.io removeu free trial credits em 2024 - free tier agora e permanente mas limitado",
            "Sem programa reseller oficial; multi-tenancy depende de organizacao unica",
            "Concorrencia direta com Railway, Render e Render free tiers similares",
        ],
        "next_steps": [
            "Validar limites exatos via playwright-cli open https://fly.io/docs/about/pricing/",
            "Testar deploy real de app Docker minimo para confirmar 256MB RAM funcional",
            "Verificar se organizacoes separadas podem ser criadas no free (isolamento real)",
            "Comparar unit economics com Railway ($5 trial credit) e Render (free static + paid dynos)",
            "Pesquisar demanda BR por edge computing/global deployment vs VPS tradicional",
        ],
    }
    
    with open(OUTPUT_FILE, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"[flyio-reseller] Output: {OUTPUT_FILE}")
    print(f"[flyio-reseller] Margin: R${economics['gross_margin_brl']}/cliente ({economics['gross_margin_pct']}%)")
    print(f"[flyio-reseller] Max clients: {economics['max_clients_free_tier']}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
