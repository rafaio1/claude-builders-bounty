 #!/usr/bin/env python3
 """Neon Postgres Reseller Scaffold - Zero-Capital Lab v23"""
 import json, os, datetime, re, subprocess, sys
 
 PILOT_DIR = os.path.dirname(os.path.abspath(__file__))
 OUTPUT_DIR = os.path.join(PILOT_DIR, "output")
 OUTPUT_FILE = os.path.join(OUTPUT_DIR, "reseller_scaffold_index.json")
 
 FREE_TIER_LIMITS = {
     "storage_gb": 0.5,
     "compute_hours_month": 190,
     "branches": 10,
     "projects": 1,
     "concurrent_connections": None,
     "data_transfer_gb": None,
     "commercial_allowed": True,
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
     "multi_tenancy_strategy": "1 projeto Neon -> multiplos schemas/roles por cliente",
 }
 
 def validate_free_tier_docs():
     result = {
         "doc_verified": False,
         "source_url": "https://neon.tech/pricing",
         "notes": [],
         "commercial_allowed": FREE_TIER_LIMITS["commercial_allowed"],
     }
     try:
         proc = subprocess.run(
             ["curl", "-sL", "--max-time", "15", result["source_url"]],
             capture_output=True, text=True, timeout=20
         )
         html = proc.stdout.lower()
         storage_match = re.search(r'(\d+)\s*(?:gb|mb)\s*(?:of\s+)?storage', html)
         if storage_match:
             val = int(storage_match.group(1))
             unit = "gb" if "gb" in html[max(0, storage_match.start()-20):storage_match.end()+5] else "mb"
             actual_gb = val if unit == "gb" else val / 1024
             if abs(actual_gb - FREE_TIER_LIMITS["storage_gb"]) < 0.1:
                 result["doc_verified"] = True
                 result["notes"].append(f"Storage confirmado: {val}{unit}")
             else:
                 result["notes"].append(f"Discrepancia storage: docs={val}{unit}, esperado={FREE_TIER_LIMITS['storage_gb']}GB")
         if "commercial" in html and ("allowed" in html or "permitted" in html):
             result["notes"].append("Uso comercial explicitamente permitido nos docs")
         elif "non-commercial" in html or "personal only" in html:
             result["commercial_allowed"] = False
             result["notes"].append("Uso comercial PROIBIDO no free tier")
     except Exception as e:
         result["notes"].append(f"Falha na extracao automatica: {str(e)[:100]}")
         result["notes"].append("Requer validacao manual via playwright-cli")
     return result
 
 def estimate_unit_economics(doc_status):
     fx_rate = 5.80
     cost_per_client_usd = PAID_PLAN_BASELINE["launch_price_usd"] / 10
     revenue_brl = RESELLING_MODEL["managed_service_price_brl"]
     cost_brl = cost_per_client_usd * fx_rate
     margin_brl = revenue_brl - cost_brl
     margin_pct = (margin_brl / revenue_brl * 100) if revenue_brl > 0 else 0
     return {
         "revenue_per_client_brl": revenue_brl,
         "cost_per_client_brl": round(cost_brl, 2),
         "gross_margin_brl": round(margin_brl, 2),
         "gross_margin_pct": round(margin_pct, 1),
         "break_even_clients_per_project": max(1, int(PAID_PLAN_BASELINE["launch_price_usd"] * fx_rate / revenue_brl) + 1),
         "ceiling_warning": "Free tier limita a 1 projeto; escala requer upgrade para Launch ($19/mo)" if not doc_status.get("commercial_allowed") else "Multi-tenancy em unico projeto free e viavel ate ~10 micro-DBs",
     }
 
 def main():
     os.makedirs(OUTPUT_DIR, exist_ok=True)
     print("[neon-postgres-reseller] Validando free tier...")
     doc_status = validate_free_tier_docs()
     print("[neon-postgres-reseller] Estimando unit economics...")
     economics = estimate_unit_economics(doc_status)
     report = {
         "pilot": "neon-postgres-reseller-scaffold",
         "category": "infrastructure_reselling",
         "status": "SCAFFOLD_OK",
         "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
         "free_tier_limits": FREE_TIER_LIMITS,
         "paid_plan_baseline": PAID_PLAN_BASELINE,
         "reselling_model": RESELLING_MODEL,
         "doc_verification": doc_status,
         "unit_economics": economics,
         "risks": [
             "Neon free tier tem apenas 1 projeto - multi-tenancy via schema isolation e mandatorio",
             "Compute hours limitadas a 190h/mes; idle timeout ajuda mas picos podem esgotar",
             "Sem programa de affiliate publico confirmado - receita puramente service-based",
             "Egress de dados nao tem cap explicito mas fair-use policy pode aplicar",
         ],
         "next_steps": [
             "Validar storage real via playwright-cli open https://neon.tech/pricing",
             "Testar criacao de schema isolado por tenant em projeto free",
             "Pesquisar programa partner/affiliate nao listado publicamente",
             "Comparar com Supabase scaffold (#38) para decisao de foco",
         ],
     }
     with open(OUTPUT_FILE, "w") as f:
         json.dump(report, f, indent=2, ensure_ascii=False)
     print(f"[neon-postgres-reseller] Output escrito: {OUTPUT_FILE}")
     print(f"[neon-postgres-reseller] Doc verified: {doc_status['doc_verified']}")
     print(f"[neon-postgres-reseller] Commercial allowed: {doc_status['commercial_allowed']}")
     print(f"[neon-postgres-reseller] Margin: R${economics['gross_margin_brl']}/cliente ({economics['gross_margin_pct']}%)")
     return 0
 
 if __name__ == "__main__":
     sys.exit(main())
