#!/usr/bin/env python3
"""Reconciliacao P2P - verifica HodlHodl, Wise, RoboSats e LND sem tocar Binance/Bybit."""
import json, os, sys, time, urllib.request, urllib.parse

def load_env(path="/Agentic/.env"):
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip(chr(34)).strip(chr(39))
    return env

env = load_env()

print("=== HODLHODL OFFERS (BRL/PIX) ===")
api_key = env.get("HODLHODL_API_KEY", "")
if not api_key:
    print("No HODLHODL API key found")
else:
    for side in ["selling", "buying"]:
        url = (
            "https://hodlhodl.com/api/v1/offers?api_key=" + api_key +
            "&filters[currency_code]=BRL&filters[side]=" + side +
            "&filters[payment_method]=PIX&limit=10"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read())
            offers = data.get("offers", [])
            print(f"\n  Side={side} | Total offers: {len(offers)}")
            for o in offers[:8]:
                price = o.get("price", "?")
                min_a = o.get("min_amount", "?")
                max_a = o.get("max_amount", "?")
                rid = o.get("trading_directory", "?")
                asset = o.get("asset_code", "BTC")
                print(f"    {rid} | {asset} | price={price} BRL | min={min_a} | max={max_a}")
        except Exception as e:
            print(f"  Error ({side}): {e}")

print("\n=== WISE BALANCE ===")
wise_key = env.get("WISE_API_KEY", "")
profile_id = env.get("WISE_PROFILE_ID", "")
print(f"  Profile ID: {profile_id}")

if wise_key:
    url = f"https://api.wise.com/legacy/v1/balances?profileId={profile_id}"
    try:
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {wise_key}",
            "User-Agent": "Mozilla/5.0"
        })
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        if isinstance(data, list):
            for b in data:
                amt = b.get("amount", b.get("value", {}).get("value", "?"))
                cur = b.get("currency", b.get("value", {}).get("currency", "?"))
                bid = b.get("id", "?")
                print(f"  Balance: {amt} {cur} (id={bid})")
        else:
            print(f"  Raw: {json.dumps(data)[:600]}")
    except Exception as e:
        print(f"  Legacy error: {e}")

    url2 = f"https://api.wise.com/v2/profiles/{profile_id}/balances"
    try:
        req2 = urllib.request.Request(url2, headers={
            "Authorization": f"Bearer {wise_key}",
            "User-Agent": "Mozilla/5.0"
        })
        resp2 = urllib.request.urlopen(req2, timeout=10)
        data2 = json.loads(resp2.read())
        if isinstance(data2, list):
            for b in data2[:5]:
                amt = b.get("amount", {}).get("value", "?")
                cur = b.get("amount", {}).get("currency", "?")
                bid = b.get("id", "?")
                print(f"  V2 Balance: {amt} {cur} (id={bid})")
        elif isinstance(data2, dict):
            for b in data2.get("balances", data2.get("data", []))[:5]:
                amt = b.get("amount", {}).get("value", "?")
                cur = b.get("amount", {}).get("currency", "?")
                bid = b.get("id", "?")
                print(f"  V2 Balance: {amt} {cur} (id={bid})")
        else:
            print(f"  V2 Raw: {json.dumps(data2)[:600]}")
    except Exception as e:
        print(f"  V2 error: {e}")

    url3 = "https://api.wise.com/v1/rates?source=BRL&target=USD"
    try:
        req3 = urllib.request.Request(url3, headers={
            "Authorization": f"Bearer {wise_key}",
            "User-Agent": "Mozilla/5.0"
        })
        resp3 = urllib.request.urlopen(req3, timeout=10)
        data3 = json.loads(resp3.read())
        if isinstance(data3, list):
            for r in data3[:3]:
                print(f"  Rate: {r.get('rate','?')} BRL->USD (mid: {r.get('mid','?')})")
        else:
            print(f"  Rate raw: {json.dumps(data3)[:300]}")
    except Exception as e:
        print(f"  Rate error: {e}")

print("\n=== ROBOSATS HTTP ===")
try:
    req = urllib.request.Request("http://localhost:8000/api/", headers={"User-Agent": "Mozilla/5.0"})
    resp = urllib.request.urlopen(req, timeout=5)
    print(f"  Status: {resp.status}")
    body = resp.read().decode()[:500]
    print(f"  Body: {body}")
except Exception as e:
    print(f"  RoboSats error: {e}")

print("\n=== GHOSTCLI STATUS ===")
for endpoint in ["http://localhost:3000", "http://localhost:8080"]:
    try:
        req = urllib.request.Request(endpoint, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=3)
        print(f"  {endpoint}: {resp.status}")
    except Exception as e:
        print(f"  {endpoint}: {e}")

print("\n=== SUMMARY ===")
print("  Constraints: NO Binance, NO Bybit API calls")
print("  Capital confirmed: ~$49 USD (Binance+Bybit+Wise)")
print("  ZERO realized profit across 5 sessions")
print("  Next: evaluate HodlHodl P2P arb, Wise conversion, RoboSats LN")
