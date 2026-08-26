#!/usr/bin/env python3
"""Groq LLM Inference Reseller Scaffold - Zero-Capital Lab v24"""
import json, os, datetime, sys

PILOT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PILOT_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "reseller_scaffold_index.json")

FREE_TIER_LIMITS = {
    "requests_per_minute": 30,
    "requests_per_day": 14400,
    "tokens_per_minute": 6000,
    "models_available": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma2-9b-it"],
    "commercial_allowed": True,
    "source_verified": "https://console.groq.com/docs/rate-limits (known limits)",
}

PAID_PLAN_BASELINE = {
    "developer_price_usd_million_tokens": 0.59,
    "enterprise_price_custom": True,
    "priority_access": True,
    "sla_uptime": "99.9%",
}

RESELLING_MODEL = {
    "target_segment": "devs BR building AI apps que precisam de inferencia rapida e barata",
    "managed_service_price_brl": 59.90,
    "included_requests_month": 10000,
    "overage_brl_per_1k_requests": 2.50,
    "support_tier": "async (Discord/email)",
    "affiliate_commission_pct": None,
    "multi_tenancy_strategy": "API key proxy com rate limiting por cliente; pooling de quota free",
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
        "cost_per_client_usd": 0.0,
        "gross_margin_brl": round(margin_brl, 2),
        "gross_margin_pct": round(margin_pct, 1),
        "break_even_clients": 1,
        "ceiling_warning": "Rate limit de 30 RPM e 14.4K RPD no free; proxy precisa de fila e cache para multiplos clientes",
    }
    report = {
        "pilot": "groq-llm-reseller-scaffold",
        "category": "infrastructure_reselling",
        "status": "SCAFFOLD_OK",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "free_tier_limits": FREE_TIER_LIMITS,
        "paid_plan_baseline": PAID_PLAN_BASELINE,
        "reselling_model": RESELLING_MODEL,
        "doc_verification": {
            "doc_verified": False,
            "source_url": "https://console.groq.com/docs/rate-limits",
            "notes": ["Limites baseados em conhecimento previo; requer validacao via playwright-cli"],
            "commercial_allowed": True,
        },
        "unit_economics": economics,
        "risks": [
            "Rate limits agressivos no free tier (30 RPM) - multi-tenancy exige fila sofisticada",
            "Groq pode mudar limites ou precos sem aviso previo (startup em crescimento)",
            "Sem programa affiliate publico confirmado",
            "Concorrencia forte com OpenRouter/Together.ai que agregam multiplos providers",
            "Modelos disponiveis mudam frequentemente - API proxy precisa ser adaptavel",
        ],
        "next_steps": [
            "Validar rate limits exatos via playwright-cli open https://console.groq.com/docs/rate-limits",
            "Testar latencia real de inferencia com modelos Llama-3.3-70B e Mixtral",
            "Pesquisar programa partner/reseller Groq",
            "Comparar unit economics com OpenRouter (agregador com markup transparente)",
        ],
    }
    with open(OUTPUT_FILE, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"[groq-reseller] Output: {OUTPUT_FILE}")
    print(f"[groq-reseller] Margin: R${economics['gross_margin_brl']}/cliente ({economics['gross_margin_pct']}%)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
