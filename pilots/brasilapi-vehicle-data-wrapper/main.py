"""
BrasilAPI Vehicle Data Wrapper MVP
Zero-capital: uses public BrasilAPI FIPE endpoint (free, no key).
Demonstrates wrapper pattern for future premium tier.
"""
import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

FIPE_BRANDS_URL = "https://brasilapi.com.br/api/fipe/marcas/v1/{vehicle_type}"
FIPE_PRICE_URL = "https://brasilapi.com.br/api/fipe/preco/v1/{fipe_code}"


def fetch_json(url: str) -> dict | list | None:
    req = urllib.request.Request(url, headers={"User-Agent": "BrasilAPI-Vehicle-Wrapper/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"[ERROR] HTTP {e.code} for {url}")
        return None
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        return None


def get_brands(vehicle_type: str = "carros") -> list[dict]:
    """Fetch available brands for a vehicle type."""
    data = fetch_json(FIPE_BRANDS_URL.format(vehicle_type=vehicle_type))
    if isinstance(data, list):
        return data
    return []


def get_vehicle_price(fipe_code: str) -> dict | None:
    """Fetch price info for a specific FIPE code."""
    data = fetch_json(FIPE_PRICE_URL.format(fipe_code=fipe_code))
    if isinstance(data, list) and len(data) > 0:
        return data[0]  # Most recent reference
    if isinstance(data, dict):
        return data
    return None


def main():
    print(f"[{datetime.now(timezone.utc).isoformat()}] BrasilAPI Vehicle Wrapper MVP")
    print("=" * 60)

    # Demo 1: List car brands (first 5)
    print("\n[1] Fetching car brands...")
    brands = get_brands("carros")
    if brands:
        print(f"    Found {len(brands)} brands. Top 5:")
        for b in brands[:5]:
            print(f"      - {b.get('nome', 'N/A')} (código: {b.get('codigo', '?')})")
    else:
        print("    No brands returned.")

    # Demo 2: Price lookup for a known FIPE code (VW Gol example)
    sample_fipe = "001004-9"  # VW Gol 1.0
    print(f"\n[2] Price lookup for FIPE {sample_fipe}...")
    price_info = get_vehicle_price(sample_fipe)
    if price_info:
        valor = price_info.get("valor", "N/A")
        mes = price_info.get("mesReferencia", "N/A")
        modelo = price_info.get("modelo", "N/A")
        print(f"    Modelo: {modelo}")
        print(f"    Valor: {valor}")
        print(f"    Referência: {mes}")
    else:
        print("    Price data unavailable.")

    # Save demo output
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "brasilapi.com.br/api/fipe",
        "demo_brands_count": len(brands),
        "demo_price_lookup": price_info,
        "wrapper_status": "FUNCTIONAL_MVP",
    }
    out_file = "wrapper_demo_output.json"
    with open(out_file, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n[OK] Demo output saved to {out_file}")


if __name__ == "__main__":
    main()
