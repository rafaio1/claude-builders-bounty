#!/usr/bin/env python3
"""Resend Email API Reseller Scaffold - Zero-Capital Lab v24"""
import json, os, datetime, sys

PILOT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PILOT_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "reseller_scaffold_index.json")

FREE_TIER_LIMITS = {
    "emails_month": 3000,
    "emails_day": 100,
    "attachments_mb": 50,
    "domains": 1,
    "commercial_allowed": True,
    "source_verified": "https://resend.com/pricing (known limits)",
}

PAID_PLAN_BASELINE = {
    "pro_price_usd": 20.0,
    "pro_emails_month": 50000,
    "extra_per_1k_usd": 0.50,
    "sla_uptime": "99.9%",
}

RESELLING_MODEL = {
    "target_segment": "micro-SaaS BR que precisam de email transacional",
    "managed_service_price_brl": 39.90,
    "included_emails_month": 3000,
    "overage_brl_per_1k": 5.0,
    "support_tier": "async (Discord/email)",
    "affiliate_commission_pct": None,
    "multi_tenancy_strategy": "API key isolada por cliente; dominio compartilhado ou custom",
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
        "ceiling_warning": "Free tier limitado a 100 emails/dia e 3K/mes; clientes com volume maior exigem Pro ($20/mo)",
    }
    report = {
        "pilot": "resend-email-reseller-scaffold",
        "category": "infrastructure_reselling",
        "status": "SCAFFOLD_OK",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "free_tier_limits": FREE_TIER_LIMITS,
        "paid_plan_baseline": PAID_PLAN_BASELINE,
        "reselling_model": RESELLING_MODEL,
        "doc_verification": {
            "doc_verified": False,
            "source_url": "https://resend.com/pricing",
            "notes": ["Limites baseados em conhecimento previo; requer validacao via playwright-cli"],
            "commercial_allowed": True,
        },
        "unit_economics": economics,
        "risks": [
            "100 emails/dia e teto baixo para apps com notificacoes frequentes",
            "Sem programa affiliate publico confirmado",
            "Concorrencia forte com SendGrid/Mailgun/Amazon SES",
            "Dominio compartilhado no free tier pode afetar deliverability",
        ],
        "next_steps": [
            "Validar limites exatos via playwright-cli open https://resend.com/pricing",
            "Testar envio de email via API com credenciais free",
            "Comparar unit economics com alternativas (SendGrid free tier = 100/dia tambem)",
        ],
    }
    with open(OUTPUT_FILE, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"[resend-reseller] Output: {OUTPUT_FILE}")
    print(f"[resend-reseller] Margin: R${economics['gross_margin_brl']}/cliente ({economics['gross_margin_pct']}%)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
