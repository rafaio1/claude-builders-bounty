#!/usr/bin/env python3
"""DadosGovBR Catalog Indexer — TIER0 Scaffold
Zero-capital indexer using official GitHub static source.
Source: dadosgovbr/catalogos-dados-brasil (catalogos.csv)
Fallback for DadosGovBR API (401 Unauthorized without bearer token).
"""
import csv
import io
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SOURCE_URL = "https://raw.githubusercontent.com/dadosgovbr/catalogos-dados-brasil/master/dados/catalogos.csv"
OUTPUT_FILE = Path(__file__).parent / "catalogs_index.json"

def fetch_catalogs() -> list[dict]:
    """Fetch catalog CSV from GitHub static source."""
    headers = {"User-Agent": "Agentic-Lab/1.0 (Zero-Capital Research)"}
    req = urllib.request.Request(SOURCE_URL, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode("utf-8")
            reader = csv.DictReader(io.StringIO(content))
            return [row for row in reader]
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}", file=sys.stderr)
        return []

def normalize_catalog(raw: dict) -> dict:
    """Normalize catalog entry to standard schema."""
    return {
        "title": raw.get("Título", "").strip(),
        "url": raw.get("URL", "").strip(),
        "municipio": raw.get("Município", "").strip(),
        "uf": raw.get("UF", "").strip(),
        "esfera": raw.get("Esfera", "").strip(),
        "poder": raw.get("Poder", "").strip(),
        "solucao": raw.get("Solução", "").strip(),
    }

def main():
    print("[INFO] Fetching catalogs from DadosGovBR GitHub source...")
    raw_catalogs = fetch_catalogs()

    if not raw_catalogs:
        print("[FAIL] No catalogs retrieved. Source may be unavailable.", file=sys.stderr)
        sys.exit(1)

    normalized = [normalize_catalog(c) for c in raw_catalogs]

    output = {
        "source": "DadosGovBR Catalogos (GitHub Static)",
        "source_url": SOURCE_URL,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "total_entries": len(normalized),
        "entries": normalized,
    }

    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"[OK] Indexed {len(normalized)} catalogs → {OUTPUT_FILE.name}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
