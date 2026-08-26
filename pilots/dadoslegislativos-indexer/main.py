#!/usr/bin/env python3
"""
dadoslegislativos-indexer — Scaffolding TIER0
Indexa proposições recentes da Câmara dos Deputados via API Aberta (zero-capital).
Fonte: https://dadosabertos.camara.leg.br/api/v2/proposicoes?ordem=DESC&ordenarPor=id
"""
import json
import urllib.request
import datetime
import sys
from pathlib import Path

API_URL = "https://dadosabertos.camara.leg.br/api/v2/proposicoes?ordem=DESC&ordenarPor=id&itens=20"
OUTPUT_FILE = Path(__file__).parent / "proposicoes_index.json"

def fetch_proposicoes():
    req = urllib.request.Request(API_URL, headers={"Accept": "application/json", "User-Agent": "AgenticLab/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            # Handle potential gzip
            if raw[:2] == b'\x1f\x8b':
                import gzip
                raw = gzip.decompress(raw)
            data = json.loads(raw.decode("utf-8"))
            return data.get("dados", [])
    except Exception as e:
        print(f"[ERRO] Falha ao buscar proposições: {e}", file=sys.stderr)
        return []

def main():
    itens = fetch_proposicoes()
    index = []
    for item in itens:
        index.append({
            "id": item.get("id"),
            "siglaTipo": item.get("siglaTipo"),
            "numero": item.get("numero"),
            "ano": item.get("ano"),
            "ementa": item.get("ementa", "")[:200],
            "dataApresentacao": item.get("dataApresentacao"),
            "uri": item.get("uri")
        })
    
    result = {
        "source": "Camara dos Deputados API v2",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "count": len(index),
        "items": index
    }
    
    OUTPUT_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"[OK] Indexadas {len(index)} proposições em {OUTPUT_FILE}")
    return 0 if len(index) > 0 else 1

if __name__ == "__main__":
    sys.exit(main())
