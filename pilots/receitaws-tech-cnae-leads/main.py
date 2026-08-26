#!/usr/bin/env python3
"""
Method 716: Lead Generation Lists for Startups (ReceitaWS Tech CNAE)
TIER0 Scaffolding: Valida extração de leads B2B tech via ReceitaWS.
Zero-capital: stdlib + API pública. Sem publicação externa.
"""
import json
import datetime
import os
import urllib.request
import urllib.error

# CNAEs de tecnologia/startup comuns
TECH_CNAES = [
    "6201501",  # Desenvolvimento de programas de computador sob encomenda
    "6202300",  # Desenvolvimento e licenciamento de programas de computador customizáveis
    "6203100",  # Desenvolvimento e licenciamento de programas de computador não-customizáveis
    "6204000",  # Consultoria em tecnologia da informação
    "6311900",  # Tratamento de dados, provedores de serviços de aplicação e serviços de hospedagem
]

def fetch_receitaws(cnpj):
    """Fetch CNPJ data from ReceitaWS."""
    url = f"https://receitaws.com.br/v1/cnpj/{cnpj}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AgenticLab/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}

def validate_cnae_filter():
    """Validate that we can filter companies by tech CNAE."""
    # Use sample CNPJs (publicly known test/example CNPJs or previously validated ones)
    # In production, this would iterate over a seed list or search API
    sample_results = []
    
    # Test with a known public institution CNPJ to verify API structure
    test_cnpj = "00000000000191"  # Placeholder
    data = fetch_receitaws(test_cnpj)
    
    has_cnae_field = False
    cnae_structure = None
    
    if isinstance(data, dict) and "error" not in data:
        # Check primary and secondary CNAE fields
        if "atividade_principal" in data or "atividades_secundarias" in data:
            has_cnae_field = True
            cnae_structure = {
                "primary": data.get("atividade_principal"),
                "secondary_count": len(data.get("atividades_secundarias", []))
            }
    
    return {
        "api_responds": "error" not in data if isinstance(data, dict) else False,
        "has_cnae_fields": has_cnae_field,
        "cnae_structure_sample": cnae_structure,
        "tech_cnaes_defined": len(TECH_CNAES),
        "filter_viable": has_cnae_field and len(TECH_CNAES) > 0
    }

def scaffold():
    output = {
        "proposal_id": "exp-20260826-data-products-method-716-leads",
        "title": "Method 716: Lead Generation Lists for Startups (ReceitaWS Tech CNAE)",
        "status": "SCAFFOLD_OK",
        "scaffolded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "method_validated": validate_cnae_filter(),
        "tech_cnaes": TECH_CNAES,
        "compliance": {
            "zero_capital": True,
            "no_external_signup": True,
            "no_public_publish": True,
            "data_source": "ReceitaWS (public API)",
            "kill_switch_active": os.environ.get("AGENTIC_LIVE_TRADE", "0") == "0"
        },
        "monetization_path": {
            "product": "Lista de empresas tech por CNAE/região/porte",
            "target_buyer": "Vendas B2B, recrutadores tech, investidores",
            "pricing_model": "Por lista filtrada ou assinatura mensal",
            "estimated_ticket": "R$200-2000/lista dependendo do filtro"
        },
        "next_steps_tier1": [
            "Construir seed list de CNPJs via busca web/LinkedIn/diretórios públicos",
            "Implementar batch fetch com rate limiting (ReceitaWS: ~3 req/min safe)",
            "Normalizar e enriquecer dados (porte, capital social, endereço)",
            "Criar filtros exportáveis (CSV/JSON) por CNAE+UF+porte",
            "Validar ToS ReceitaWS para uso comercial de dados agregados"
        ]
    }
    
    out_path = os.path.join(os.path.dirname(__file__), "output.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    v = output["method_validated"]
    print(f"[OK] Scaffold gerado: {out_path}")
    print(f"[OK] API responde: {v['api_responds']}")
    print(f"[OK] Campos CNAE presentes: {v['has_cnae_fields']}")
    print(f"[OK] Filtro viável: {v['filter_viable']} ({v['tech_cnaes_defined']} CNAEs tech definidos)")
    
    return output

if __name__ == "__main__":
    scaffold()
