import os, requests, time, hmac, hashlib, json
from dotenv import load_dotenv
load_dotenv("/Agentic/.env")

KEY = os.getenv("BINANCE_API_KEY")
SECRET = os.getenv("BINANCE_API_SECRET")
BASE = "https://fapi.binance.com"

def sign(params):
    params["timestamp"] = int(time.time() * 1000)
    qs = "&".join(f"{k}={v}" for k,v in params.items())
    sig = hmac.new(SECRET.encode(), qs.encode(), hashlib.sha256).hexdigest()
    return f"{qs}&signature={sig}"

def get(path, params=None):
    headers = {"X-MBX-APIKEY": KEY}
    url = BASE + path
    if params:
        url += "?" + sign(params)
    r = requests.get(url, headers=headers, timeout=10)
    try:
        return r.json()
    except:
        print(f"[BINANCE-MARGIN] RAW RESPONSE: {r.text[:500]}")
        return None

try:
    bal = get("/fapi/v2/balance")
    if isinstance(bal, list):
        usdt = next((b for b in bal if b.get("asset")=="USDT"), None)
        print(f"[BINANCE-MARGIN] USDT Balance: {usdt.get('balance','N/A') if usdt else 'N/A'}")
        print(f"[BINANCE-MARGIN] Available: {usdt.get('availableBalance','N/A') if usdt else 'N/A'}")
    else:
        print(f"[BINANCE-MARGIN] Balance response unexpected: {bal}")

    pos = get("/fapi/v2/positionRisk")
    if isinstance(pos, list):
        active = [p for p in pos if float(p.get("positionAmt",0))!=0]
        print(f"[BINANCE-MARGIN] Active Positions: {len(active)}")
        for p in active[:5]:
            print(f"  {p.get('symbol')} | Amt:{p.get('positionAmt')} | Lev:{p.get('leverage')}x | PnL:{p.get('unRealizedProfit')}")
    else:
        print(f"[BINANCE-MARGIN] Position response unexpected: {pos}")
except Exception as e:
    print(f"[BINANCE-MARGIN] ERROR: {e}")
