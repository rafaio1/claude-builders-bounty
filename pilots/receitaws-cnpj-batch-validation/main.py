#!/usr/bin/env python3
"""
receitaws-cnpj-batch-validation (method_1457)
Scaffolding TIER0: Validação batch de CNPJs via ReceitaWS.
Zero-capital. Stdlib only. Sem auth. Rate limit 3/min respeitado.
Fila assíncrona simulada com sleep entre requisições.
"""

import datetime as dt
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = OUT_DIR / "cnpj_batch_validation_index.json"

UA = "Mozilla/5.0 (compatible; CNPJBatchBot/1.0; +https://ghostcli.dev)"
TIMEOUT = 15
RATE_LIMIT_DELAY = 20  # 3 req/min = 1 a cada 20s para segurança


def validate_cnpj(cnpj: str) -> dict:
    """Consulta um CNPJ na API pública ReceitaWS."""
    cnpj_clean = "".join(filter(str.isdigit, cnpj))
    if len(cnpj_clean) != 14:
        return {"cnpj": cnpj, "status": "invalid_format", "error": "CNPJ deve ter 14 dígitos"}
    
    url = f"https://receitaws.com.br/v1/cnpj/{cnpj_clean}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "cnpj": cnpj_clean,
                "status": "valid" if data.get("status") == "OK" else "inactive",
                "razao_social": data.get("nome", ""),
                "situacao": data.get("situacao", ""),
                "cnae_principal": data.get("atividade_principal", [{}])[0].get("code", ""),
                "municipio": data.get("municipio", ""),
                "uf": data.get("uf", ""),
                "source": "receitaws"
            }
    except urllib.error.HTTPError as e:
        if e.code == 429:
            return {"cnpj": cnpj_clean, "status": "rate_limited", "error": "429 Too Many Requests"}
        return {"cnpj": cnpj_clean, "status": "error", "error": f"HTTP {e.code}"}
    except Exception as e:
        return {"cnpj": cnpj_clean, "status": "error", "error": str(e)}


def main():
    now = dt.datetime.now(dt.timezone.utc)
    
    # CNPJs de exemplo para scaffolding (empresas públicas/conhecidas)
    test_cnpjs = [
        "00.000.000/0001-91",  # Banco do Brasil (exemplo clássico)
        "19.131.243/0001-97",  # OpenAI Brasil (LTDA)
        "33.683.111/0001-07",  # Petrobras
    ]
    
    results = []
    print(f"[INFO] Iniciando validação batch de {len(test_cnpjs)} CNPJs...")
    print(f"[INFO] Rate limit: 3/min (delay {RATE_LIMIT_DELAY}s entre requisições)")
    
    for i, cnpj in enumerate(test_cnpjs):
        print(f"[{i+1}/{len(test_cnpjs)}] Validando {cnpj}...")
        result = validate_cnpj(cnpj)
        results.append(result)
        
        if i < len(test_cnpjs) - 1:
            print(f"[WAIT] Aguardando {RATE_LIMIT_DELAY}s (rate limit)...")
            time.sleep(RATE_LIMIT_DELAY)
    
    output = {
        "pipeline": "receitaws-cnpj-batch-validation",
        "method_id": "method_1457",
        "generated_at_utc": now.isoformat(),
        "total_consultados": len(results),
        "validos": len([r for r in results if r.get("status") == "valid"]),
        "inativos": len([r for r in results if r.get("status") == "inactive"]),
        "erros": len([r for r in results if r.get("status") in ("error", "rate_limited", "invalid_format")]),
        "rate_limit_delay_sec": RATE_LIMIT_DELAY,
        "zero_capital": True,
        "auth_required": False,
        "scaffold_status": "OK",
        "resultados": results
    }
    
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"\n[OK] Output escrito em {OUTPUT_FILE}")
    print(f"[OK] Válidos: {output['validos']} | Inativos: {output['inativos']} | Erros: {output['erros']}")
    return output


if __name__ == "__main__":
    main()
