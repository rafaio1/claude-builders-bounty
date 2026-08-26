#!/usr/bin/env python3
"""IBGE News/Releases Indexer — TIER0 Scaffold
Zero-capital indexer using official IBGE public API.
Endpoint: https://servicodados.ibge.gov.br/api/v3/noticias
No auth required. Public data.
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_BASE = "https://servicodados.ibge.gov.br/api/v3/noticias"
OUTPUT_FILE = Path(__file__).parent / "news_index.json"
QUANTITY = 50  # Max per request for scaffold validation

def fetch_news(quantity: int = QUANTITY) -> list[dict]:
    """Fetch news/releases from IBGE public API."""
    url = f"{API_BASE}?tipo=release&quantidade={quantity}"
    headers = {"Accept": "application/json", "User-Agent": "Agentic-Lab/1.0 (Zero-Capital Research)"}
    
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            # Handle potential NDJSON or wrapped response
            lines = [l for l in raw.strip().split('\n') if l.strip()]
            if not lines:
                return []
            data = json.loads(lines[0])
            # API returns {"items": [...], "count": N, ...}
            if isinstance(data, dict) and "items" in data:
                return data["items"]
            elif isinstance(data, list):
                return data
            else:
                print(f"[WARN] Unexpected structure: {type(data)}", file=sys.stderr)
                return []
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}", file=sys.stderr)
        return []

def normalize_item(raw: dict) -> dict:
    """Normalize news item to standard schema."""
    return {
        "id": raw.get("id") or raw.get("news_id") or "",
        "title": raw.get("titulo") or raw.get("title") or "",
        "summary": raw.get("introducao") or raw.get("resumo") or raw.get("summary") or "",
        "date": raw.get("data_publicacao") or raw.get("publication_date") or raw.get("date") or "",
        "category": raw.get("categoria") or raw.get("category") or "",
        "url": raw.get("link") or raw.get("url") or f"https://agenciadenoticias.ibge.gov.br/{raw.get('id', '')}",
        "tags": raw.get("tags", []) if isinstance(raw.get("tags"), list) else [],
    }

def main():
    print(f"[INFO] Fetching up to {QUANTITY} releases from IBGE API...")
    raw_items = fetch_news(QUANTITY)
    
    if not raw_items:
        print("[FAIL] No items retrieved. API may be down.", file=sys.stderr)
        sys.exit(1)
    
    normalized = [normalize_item(item) for item in raw_items]
    
    output = {
        "source": "IBGE Serviço de Dados (Public API)",
        "endpoint": API_BASE,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "total_entries": len(normalized),
        "entries": normalized,
    }
    
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"[OK] Indexed {len(normalized)} releases → {OUTPUT_FILE.name}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
