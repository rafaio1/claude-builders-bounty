#!/usr/bin/env python3
"""HodlHodl P2P scanner - busca ofertas BRL/PIX e calcula arb potencial."""
import json, os, sys, time, urllib.request, urllib.parse, hmac, hashlib

def load_env(path="/Agentic/.env"):
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env

def signed_request(env, endpoint, extra_params=None):
    api_key = env.get("HODLHODL_API_KEY", "")
    api_secret = env.get("HODLHODL_API_SECRET", "")
    ts = str(int(time.time()))
    params = {"api_key": api_key}
    if extra_params:
        params.update(extra_params)
    qs = urllib.parse.urlencode(params)
    msg = ts + qs
    sig = hmac.new(api_secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    url = f"https://hodlhodl.com/api/v1/{endpoint}?{qs}&timestamp={ts}&signature={sig}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json"
    })
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read())

env = load_env()
print("=== HODLHODL BRL OFFERS ===")

try:
    data = signed_request(env, "offers", {
        "filters[currency_code]": "BRL",
        "limit": "50"
    })
    offers = data.get("offers", [])
    sell_offers = [o for o in offers if o.get("side") == "sell"]
    buy_offers = [o for o in offers if o.get("side") == "buy"]
    print(f"Total: {len(offers)} | Sell BTC (we buy): {len(sell_offers)} | Buy BTC (we sell): {len(buy_offers)}")
    
    print("\n=== CHEAPEST SELL OFFERS (we buy BTC with BRL) ===")
    for o in sorted(sell_offers, key=lambda x: float(x.get("price", "999999")))[:8]:
        price = float(o.get("price", 0))
        min_a = o.get("min_amount", "?")
        max_a = o.get("max_amount", "?")
        oid = o.get("id", "?")
        payment = o.get("payment_method_names", "?")
        btc_for_100 = 100 / price if price > 0 else 0
        print(f"  ID={oid} | R${price:,.2f} | min={min_a} max={max_a} | R$100-> {btc_for_100:.8f} BTC | {payment}")
    
    print("\n=== HIGHEST BUY OFFERS (we sell BTC for BRL) ===")
    for o in sorted(buy_offers, key=lambda x: float(x.get("price", "0")), reverse=True)[:8]:
        price = float(o.get("price", 0))
        min_a = o.get("min_amount", "?")
        max_a = o.get("max_amount", "?")
        oid = o.get("id", "?")
        payment = o.get("payment_method_names", "?")
        brl_for_001 = 0.001 * price if price > 0 else 0
        print(f"  ID={oid} | R${price:,.2f} | min={min_a} max={max_a} | 0.001 BTC-> R${brl_for_001:.2f} | {payment}")
    
    if sell_offers and buy_offers:
        best_buy = min(float(o.get("price", "999999")) for o in sell_offers)
        best_sell = max(float(o.get("price", "0")) for o in buy_offers)
        spread_pct = ((best_sell - best_buy) / best_buy) * 100
        print(f"\n=== ARB ANALYSIS (same platform) ===")
        print(f"Best buy:  R${best_buy:,.2f}")
        print(f"Best sell: R${best_sell:,.2f}")
        print(f"Spread: {spread_pct:.2f}%")
        if spread_pct > 0:
            gross = 100 / best_buy * best_sell - 100
            fee = (100 + 100 / best_buy * best_sell) * 0.01
            print(f"Gross: R${gross:.2f} | Fees(~1%): R${fee:.2f} | NET: R${gross - fee:.2f}")
        else:
            print("NEGATIVE spread - same-platform arb NOT viable")
            print("Need cross-platform: buy HodlHodl, sell elsewhere (or vice versa)")

except Exception as e:
    print(f"Error: {e}")

# Also check USD offers for comparison
print("\n=== HODLHODL USD OFFERS ===")
try:
    data_usd = signed_request(env, "offers", {
        "filters[currency_code]": "USD",
        "limit": "30"
    })
    offers_usd = data_usd.get("offers", [])
    sell_usd = [o for o in offers_usd if o.get("side") == "sell"]
    buy_usd = [o for o in offers_usd if o.get("side") == "buy"]
    print(f"USD: {len(offers_usd)} total | Sell: {len(sell_usd)} | Buy: {len(buy_usd)}")
    if sell_usd:
        cheapest = min(float(o.get("price", "999999")) for o in sell_usd)
        print(f"Cheapest sell (buy BTC): ${cheapest:,.2f}")
    if buy_usd:
        highest = max(float(o.get("price", "0")) for o in buy_usd)
        print(f"Highest buy (sell BTC): ${highest:,.2f}")
    if sell_usd and buy_usd:
        best_buy = min(float(o.get("price", "999999")) for o in sell_usd)
        best_sell = max(float(o.get("price", "0")) for o in buy_usd)
        spread = ((best_sell - best_buy) / best_buy) * 100
        print(f"USD spread: {spread:.2f}%")
except Exception as e:
    print(f"USD error: {e}")

# Cross-currency arb: buy BTC with BRL, sell BTC for USD
print("\n=== CROSS-CURRENCY ARB (BRL buy -> USD sell) ===")
try:
    if sell_offers and buy_usd:
        brl_buy_price = min(float(o.get("price", "999999")) for o in sell_offers)
        usd_sell_price = max(float(o.get("price", "0")) for o in buy_usd)
        # Convert BRL to USD at ~5.16 rate
        usd_brl_rate = 5.16
        brl_in_usd = brl_buy_price / usd_brl_rate
        print(f"Buy BTC at R${brl_buy_price:,.2f} (~${brl_in_usd:,.2f})")
        print(f"Sell BTC at ${usd_sell_price:,.2f}")
        if usd_sell_price > brl_in_usd:
            profit_pct = ((usd_sell_price - brl_in_usd) / brl_in_usd) * 100
            print(f"Potential profit: {profit_pct:.2f}% (before fees)")
            print(f"  With R$100 (~$19.38): buy BTC, sell for ${19.38 * (1 + profit_pct/100):.2f}")
        else:
            print(f"  No profit: buy ${brl_in_usd:.2f} > sell ${usd_sell_price:.2f}")
except Exception as e:
    print(f"Cross-currency error: {e}")
