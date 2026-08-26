import sys, os, json, time, hashlib, hmac, requests, math, logging
sys.path.insert(0, '/Agentic/src')
from agentic.env import bybit_credentials
from agentic.aro.store import append_jsonl
from pathlib import Path

ROOT = Path("/Agentic")
LOG_FILE = ROOT / "data" / "aro" / "compounder.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)

api_key, secret = bybit_credentials()
recv_window = "5000"
base = "https://api.bybit.com"
session = requests.Session()
session.trust_env = False

TARGET_USDT = 182.0  # ~1000 BRL

def sign(payload):
    ts = str(int(time.time() * 1000))
    raw = f"{ts}{api_key}{recv_window}{payload}"
    return ts, hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()

def get(path, query=""):
    url = f"{base}{path}"
    if query: url += f"?{query}"
    ts, sig = sign(query)
    h = {"X-BAPI-API-KEY": api_key, "X-BAPI-TIMESTAMP": ts, "X-BAPI-RECV-WINDOW": recv_window, "X-BAPI-SIGN": sig, "Content-Type": "application/json"}
    try:
        resp = session.get(url, headers=h, timeout=15)
        return resp.json()
    except Exception as e:
        logging.error(f"GET {path} failed: {e}")
        return {"retCode": -1}

def post(path, body):
    url = f"{base}{path}"
    payload = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    ts, sig = sign(payload)
    h = {"X-BAPI-API-KEY": api_key, "X-BAPI-TIMESTAMP": ts, "X-BAPI-RECV-WINDOW": recv_window, "X-BAPI-SIGN": sig, "Content-Type": "application/json"}
    try:
        resp = session.post(url, headers=h, data=payload, timeout=15)
        return resp.json()
    except Exception as e:
        logging.error(f"POST {path} failed: {e}")
        return {"retCode": -1}

def get_market_price(sym):
    t = get("/v5/market/tickers", f"category=spot&symbol={sym}")
    if t.get("retCode") == 0 and t.get("result", {}).get("list"):
        return float(t["result"]["list"][0]["lastPrice"])
    return None

def get_instruments():
    info = get("/v5/market/instruments-info", "category=spot&limit=1000")
    insts = {}
    if info.get("retCode") == 0:
        for i in info["result"]["list"]:
            insts[i["symbol"]] = {
                "qtyStep": float(i.get("lotSizeFilter", {}).get("qtyStep", 1)),
                "tickSize": float(i.get("priceFilter", {}).get("tickSize", 0.000001)),
                "minQty": float(i.get("lotSizeFilter", {}).get("minOrderQty", 0)),
                "minAmt": float(i.get("lotSizeFilter", {}).get("minOrderAmt", 0))
            }
    return insts

def format_qty(q, step):
    q = math.floor(q / step) * step
    s = f"{q:.8f}".rstrip('0').rstrip('.')
    return s if s and s != "." else "0"

def format_price(p, tick):
    dec = max(0, -int(math.floor(math.log10(tick)))) if tick < 1 else 0
    return f"{p:.{dec}f}"

logging.info("=== AUTONOMOUS COMPOUNDER DAEMON STARTED ===")
insts = get_instruments()

# Track placed orders to avoid spamming
active_buys = {}
active_sells = {}

while True:
    try:
        bal_res = get("/v5/account/wallet-balance", "accountType=UNIFIED")
        usdt_bal = 0
        coins = {}
        if bal_res.get("retCode") == 0:
            for c in bal_res["result"]["list"][0]["coin"]:
                b = float(c.get("walletBalance", 0))
                if b > 0:
                    coins[c["coin"]] = b
                    if c["coin"] == "USDT": usdt_bal = b
        
        logging.info(f"USDT: {usdt_bal:.4f} | Other coins: {len(coins)-1}")
        
        if usdt_bal >= TARGET_USDT:
            logging.info("!!! TARGET 1000 BRL (182 USDT) ACHIEVED !!!")
            append_jsonl(ROOT, "ledger.jsonl", {"kind": "milestone_reached", "milestone": "1000_brl_target", "usdt": str(usdt_bal), "live": True})
            break

        # Manage XRPUSDT Grid
        sym = "XRPUSDT"
        if sym in insts:
            price = get_market_price(sym)
            if price:
                inst = insts[sym]
                # Check open orders for XRP
                orders = get("/v5/order/realtime", f"category=spot&symbol={sym}")
                open_buys = []
                open_sells = []
                if orders.get("retCode") == 0:
                    for o in orders["result"]["list"]:
                        if o["orderStatus"] in ["New", "PartiallyFilled"]:
                            if o["side"] == "Buy": open_buys.append(o)
                            else: open_sells.append(o)
                
                # If no open buys and we have USDT, place a tight buy
                if not open_buys and usdt_bal >= 5.0:
                    buy_p = math.floor((price * 0.998) / inst["tickSize"]) * inst["tickSize"]
                    qty = (usdt_bal * 0.5) / buy_p
                    qty_s = format_qty(qty, inst["qtyStep"])
                    if float(qty_s) >= inst["minQty"] and (float(qty_s) * buy_p) >= inst["minAmt"]:
                        res = post("/v5/order/create", {"category": "spot", "symbol": sym, "side": "Buy", "orderType": "Limit", "qty": qty_s, "price": format_price(buy_p, inst["tickSize"]), "timeInForce": "GTC"})
                        if res.get("retCode") == 0: logging.info(f"XRP BUY placed @ {buy_p}")
                
                # If no open sells and we have XRP, place a tight sell
                xrp_bal = coins.get("XRP", 0)
                if not open_sells and xrp_bal >= inst["minQty"]:
                    sell_p = math.ceil((price * 1.002) / inst["tickSize"]) * inst["tickSize"]
                    qty_s = format_qty(xrp_bal * 0.95, inst["qtyStep"])
                    if float(qty_s) >= inst["minQty"] and (float(qty_s) * sell_p) >= inst["minAmt"]:
                        res = post("/v5/order/create", {"category": "spot", "symbol": sym, "side": "Sell", "orderType": "Limit", "qty": qty_s, "price": format_price(sell_p, inst["tickSize"]), "timeInForce": "GTC"})
                        if res.get("retCode") == 0: logging.info(f"XRP SELL placed @ {sell_p}")

        # Manage DOGEUSDT Grid
        sym = "DOGEUSDT"
        if sym in insts:
            price = get_market_price(sym)
            if price:
                inst = insts[sym]
                orders = get("/v5/order/realtime", f"category=spot&symbol={sym}")
                open_buys = []
                if orders.get("retCode") == 0:
                    for o in orders["result"]["list"]:
                        if o["orderStatus"] in ["New", "PartiallyFilled"] and o["side"] == "Buy":
                            open_buys.append(o)
                
                if not open_buys and usdt_bal >= 5.0:
                    buy_p = math.floor((price * 0.998) / inst["tickSize"]) * inst["tickSize"]
                    qty = (usdt_bal * 0.3) / buy_p
                    qty_s = format_qty(qty, inst["qtyStep"])
                    if float(qty_s) >= inst["minQty"] and (float(qty_s) * buy_p) >= inst["minAmt"]:
                        res = post("/v5/order/create", {"category": "spot", "symbol": sym, "side": "Buy", "orderType": "Limit", "qty": qty_s, "price": format_price(buy_p, inst["tickSize"]), "timeInForce": "GTC"})
                        if res.get("retCode") == 0: logging.info(f"DOGE BUY placed @ {buy_p}")

        time.sleep(15)
    except Exception as e:
        logging.error(f"Loop error: {e}")
        time.sleep(30)
