#!/usr/bin/env python3
"""
Geração de Amostras Reais — Data Products (ReceitaWS, IBGE, GitHub)
TIER0 Scaffolding: Valida fontes oficiais BR sem publicação externa.
Zero-capital: apenas stdlib + APIs públicas abertas.
"""
import json
import datetime
import os
import urllib.request
import urllib.error

def fetch_json(url, timeout=10):
    """Fetch JSON from public API with error handling."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AgenticLab/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e), "url": url}

def sample_receitaws():
    """Method 709: ReceitaWS CNPJ sample (public data)."""
    # Use known valid test CNPJ format (not real company to avoid privacy issues in scaffold)
    # In production TIER1, would use real validated CNPJs from public registry
    test_cnpj = "00000000000191"  # Placeholder - replace with real public CNPJ in TIER1
    url = f"https://receitaws.com.br/v1/cnpj/{test_cnpj}"
    data = fetch_json(url)
    
    return {
        "method_id": 709,
        "source": "ReceitaWS",
        "endpoint": url,
        "sample_type": "CNPJ Public Registry",
        "data_fields_available": list(data.keys()) if isinstance(data, dict) and "error" not in data else ["error"],
        "raw_sample": data if isinstance(data, dict) else None,
        "compliance_note": "Dados públicos via API aberta. Uso comercial requer verificação de ToS.",
        "zero_capital_viable": True
    }

def sample_ibge():
    """Method 715: IBGE Municipalities API sample."""
    url = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios?orderBy=nome&limit=5"
    data = fetch_json(url)
    
    return {
        "method_id": 715,
        "source": "IBGE API",
        "endpoint": url,
        "sample_type": "Municipalities Reference Data",
        "records_returned": len(data) if isinstance(data, list) else 0,
        "data_structure": data[0] if isinstance(data, list) and len(data) > 0 else None,
        "compliance_note": "API pública oficial do governo federal. Dados abertos por lei.",
        "zero_capital_viable": True
    }

def sample_github_proxy():
    """Method 721: GitHub Search API for BR tech ecosystem signals."""
    query = "language:python+topic:brasil+stars:>100"
    url = f"https://api.github.com/search/repositories?q={query}&per_page=3"
    data = fetch_json(url)
    
    items = data.get("items", []) if isinstance(data, dict) else []
    
    return {
        "method_id": 721,
        "source": "GitHub Search API",
        "endpoint": url,
        "sample_type": "BR Tech Ecosystem Repos",
        "total_count": data.get("total_count", 0) if isinstance(data, dict) else 0,
        "sample_repos": [
            {
                "name": r.get("full_name"),
                "stars": r.get("stargazers_count"),
                "description": r.get("description", "")[:100]
            }
            for r in items[:3]
        ],
        "compliance_note": "GitHub API rate-limited (60/h unauthenticated). Sufficient for sampling.",
        "zero_capital_viable": True
    }

def scaffold():
    output = {
        "proposal_id": "exp-20260826-data-products-sample-generation",
        "title": "Geração de Amostras Reais — Data Products (ReceitaWS, IBGE, GitHub)",
        "status": "SCAFFOLD_OK",
        "scaffolded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "methods_validated": [],
        "sources_status": {},
        "compliance": {
            "zero_capital": True,
            "no_external_signup": True,
            "no_public_publish": True,
            "data_license_respected": True,
            "kill_switch_active": os.environ.get("AGENTIC_LIVE_TRADE", "0") == "0"
        },
        "next_steps_tier1": [
            "Conselho valida qualidade das amostras",
            "Definir formato de entrega (CSV/API/ZIP) e precificação",
            "Verificar ToS de cada fonte para uso comercial",
            "Implementar cache/rate-limiting para produção",
            "Submeter proposta TIER1 apenas com comprador/plataforma confirmada"
        ]
    }
    
    # Execute samples
    print("[1/3] Fetching ReceitaWS sample...")
    rws = sample_receitaws()
    output["methods_validated"].append(rws)
    output["sources_status"]["receitaws"] = "OK" if "error" not in rws.get("raw_sample", {}) else "ERROR"
    
    print("[2/3] Fetching IBGE sample...")
    ibge = sample_ibge()
    output["methods_validated"].append(ibge)
    output["sources_status"]["ibge"] = "OK" if ibge["records_returned"] > 0 else "ERROR"
    
    print("[3/3] Fetching GitHub BR ecosystem sample...")
    gh = sample_github_proxy()
    output["methods_validated"].append(gh)
    output["sources_status"]["github"] = "OK" if gh["total_count"] > 0 else "ERROR"
    
    # Summary
    ok_count = sum(1 for v in output["sources_status"].values() if v == "OK")
    output["validation_summary"] = {
        "total_methods": 3,
        "successful": ok_count,
        "failed": 3 - ok_count,
        "all_sources_viable": ok_count == 3
    }
    
    out_path = os.path.join(os.path.dirname(__file__), "output.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Scaffold gerado: {out_path}")
    print(f"[OK] Fontes validadas: {ok_count}/3")
    for m in output["methods_validated"]:
        status = "✅" if output["sources_status"].get(m["source"].lower().split()[0], "") == "OK" else "❌"
        print(f"  {status} {m['source']} (Method {m['method_id']})")
    
    return output

if __name__ == "__main__":
    scaffold()
