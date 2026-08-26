#!/usr/bin/env python3
"""Groq LLM Inference Reseller Scaffold - Zero-Capital Lab v25 (Updated Free Tier)"""
import json, os, datetime, sys

PILOT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PILOT_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "reseller_scaffold_index.json")

FREE_TIER_LIMITS = {
    "models": {
        "groq/compound": {"rpm": 30, "rpd": 250, "tpm": 70000},
        "qwen/qwen3.8-27b": {"rpm": 30, "rpd": 1000, "tpm": 8000},
        "openai/gpt-oss-120b": {"rpm": 30, "rpd": 1000, "tpm": None},
    },
    "legacy_models_removed": ["llama-3.3-70b-versatile", "mixtral-8x7b-32768", "gemma2-9b-it"],
    "commercial_allowed": True,
    "source_verified": "https://console.groq.com/docs/rate-limits (v25 validation)",
    "validation_note": "Legacy models moved to Developer plan or discontinued in free tier as of Aug 2026",
}

PAID_PLAN_BASELINE = {
    "developer_price_usd_million_tokens": 0.59,
    "enterprise_price_custom": True,
    "priority_access": True,
    "sla_uptime": "99.9%",
}

RESELLING_MODEL = {
    "target_segment": "devs BR building AI apps com modelos open-weight via Groq",
    "managed_service_price_brl": 49.90,
    "included_requests_month": 5000,
    "overage_brl_per_1k_requests": 3.50,
    "support_tier": "async (Discord/email)",
    "affiliate_commission_pct": None,
    "multi_tenancy_strategy": "API key proxy com rate limiting por modelo individual; RPD baixo exige fila agressiva e cache semantico",
    "recommended_model": "qwen/qwen3.8-27b (melhor custo-beneficio no free tier atual)",
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
        "ceiling_warning": "RPD de 250 (compound) e 1K (qwen3.8) sao MUITO baixos para multi-tenancy; maximo ~3-5 clientes ativos simultaneos no free",
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
            "doc_verified": True,
            "source_url": "https://console.groq.com/docs/rate-limits",
            "notes": ["Reescrito v25: modelos legacy removidos do free tier; novos limites por modelo individual validados via playwright-cli"],
            "commercial_allowed": True,
        },
        "unit_economics": economics,
        "risks": [
            "RPD extremamente baixo (250-1K) limita severamente multi-tenancy no free tier",
            "Modelos free tier mudam frequentemente sem aviso - proxy precisa de discovery dinamico",
            "Groq pode mudar limites ou precos sem aviso previo (startup em crescimento)",
            "Sem programa affiliate publico confirmado",
            "Concorrencia forte com OpenRouter/Together.ai que agregam multiplos providers",
            "Modelos disponiveis mudam frequentemente - API proxy precisa ser adaptavel",
        ],
        "next_steps": [
            "Implementar model discovery automatico para adaptar a mudancas no free tier",
            "Testar latencia real de qwen/qwen3.8-27b e groq/compound",
            "Avaliar se RPD atual justifica manutencao do scaffold ou se deve migrar para Developer plan ($X/mo)",
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
