#!/usr/bin/env python3
"""IBGE Municípios Indexer — TIER0 Scaffold
Zero-capital indexer using official IBGE Localidades API.
Endpoint: https://servicodados.ibge.gov.br/api/v1/localidades/municipios
No auth required. Returns all 5571 municipalities with hierarchy.
Handles gzip-compressed responses from IBGE API.
"""
import gzip
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_BASE = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
OUTPUT_FILE = Path(__file__).parent / "municipios_index.json"

def fetch_municipios() -> list[dict]:
    """Fetch all municipalities from IBGE API (handles gzip)."""
    url = f"{API_BASE}?orderBy=nome"
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
        "User-Agent": "Agentic-Lab/1.0 (Zero-Capital Research)"
    }
    
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw_bytes = resp.read()
            # Check if response is gzip-compressed
            encoding = resp.headers.get("Content-Encoding", "")
            if encoding == "gzip" or raw_bytes[:2] == b'\x1f\x8b':
                raw_bytes = gzip.decompress(raw_bytes)
            
            raw = raw_bytes.decode("utf-8")
            lines = [l for l in raw.strip().split('\n') if l.strip()]
            if not lines:
                return []
            data = json.loads(lines[0])
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "items" in data:
                return data["items"]
            else:
                print(f"[WARN] Unexpected structure: {type(data)}", file=sys.stderr)
                return []
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}", file=sys.stderr)
        return []

def normalize_municipio(raw: dict) -> dict:
    """Normalize municipality entry to flat schema."""
    micro = raw.get("microrregiao", {}) or {}
    meso = micro.get("mesorregiao", {}) or {}
    uf = meso.get("UF", {}) or {}
    
    return {
        "id": raw.get("id"),
        "nome": raw.get("nome", ""),
        "uf_sigla": uf.get("sigla", ""),
        "uf_nome": uf.get("nome", ""),
        "mesorregiao": meso.get("nome", ""),
        "microrregiao": micro.get("nome", ""),
    }

def main():
    print("[INFO] Fetching all municipalities from IBGE API...")
    raw_items = fetch_municipios()
    
    if not raw_items:
        print("[FAIL] No municipalities retrieved.", file=sys.stderr)
        sys.exit(1)
    
    normalized = [normalize_municipio(m) for m in raw_items]
    
    output = {
        "source": "IBGE Localidades API (Public)",
        "endpoint": API_BASE,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "total_entries": len(normalized),
        "entries": normalized,
    }
    
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"[OK] Indexed {len(normalized)} municípios → {OUTPUT_FILE.name}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
