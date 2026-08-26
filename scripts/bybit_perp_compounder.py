#!/usr/bin/env python3
"""
Bybit Perpetual Compounder - Fixed lotSizeFilter parsing
Mandate: Max 3x leverage, SL mandatory, funding check pre-trade.
"""
import sys, os, json, time, hashlib, hmac, requests, math, logging
sys.path.insert(0, "/Agentic/build/lib")
from agentic.env import bybit_credentials
from agentic.aro.store import append_jsonl
from pathlib import Path

ROOT = Path("/Agentic")
LOG_FILE = ROOT / "data" / "aro" / "perp_compounder.log"
TRADES_LOG = ROOT / "data" / "aro" / "trades" / "perpetuals.jsonl"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
TRADES_LOG.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("PerpCompounder")

api_key, secret = bybit_credentials()
recv_window = "5000"
base = "https://api.bybit.com"
session = requests.Session()
session.trust_env = False

MAX_LEVERAGE = 3
RISK_PER_TRADE_PCT = 2.0
MIN_VOLUME_24H = 50_000_000
MAX_SPREAD_PCT = 0.05
FUNDING_THRESHOLD = 0.001

_instrument_cache = {}

def safe_float(val, default=0.0):
    if val is None or val == '':
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

def sign(payload):
    ts = str(int(time.time() * 1000))
    raw = f"{ts}{api_key}{recv_window}{payload}"
    return ts, hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()

def get(path, query=""):
    url = f"{base}{path}"
    if query: url += f"?{query}"
    ts, sig = sign(query)
    h = {"X-BAPI-API-KEY": api_key, "X-BAPI-TIMESTAMP": ts, "X-BAPI-RECV-WINDOW": recv_window, "X-BAPI-SIGN": sig}
    try:
        resp = session.get(url, headers=h, timeout=15)
        return resp.json()
    except Exception as e:
        logger.error(f"GET {path} failed: {e}")
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
        logger.error(f"POST {path} failed: {e}")
        return {"retCode": -1}

def get_wallet_balance():
    res = get("/v5/account/wallet-balance", "accountType=UNIFIED")
    if res.get("retCode") == 0:
        for coin in res["result"]["list"][0]["coin"]:
            if coin["coin"] == "USDT":
                return safe_float(coin.get("walletBalance"), 0.0)
    return 0.0

def get_instrument_spec(symbol):
    """Get minOrderQty and qtyStep from lotSizeFilter."""
    if symbol in _instrument_cache:
        return _instrument_cache[symbol]
    
    spec = {"minOrderQty": 0.01, "qtyStep": 0.01, "minNotional": 5.0}
    
    res = get("/v5/market/instruments-info", f"category=linear&symbol={symbol}")
    if res.get("retCode") == 0 and res["result"].get("list"):
        i = res["result"]["list"][0]
        lsf = i.get("lotSizeFilter", {})
        if lsf:
            spec["minOrderQty"] = safe_float(lsf.get("minOrderQty"), 0.01)
            spec["qtyStep"] = safe_float(lsf.get("qtyStep"), 0.01)
            spec["minNotional"] = safe_float(lsf.get("minNotionalValue"), 5.0)
    
    _instrument_cache[symbol] = spec
    return spec

def round_qty(qty, step):
    """Round quantity down to nearest valid step."""
    if step <= 0:
        return round(qty, 2)
    return math.floor(qty / step) * step

def format_qty(qty, step):
    """Format qty string respecting step precision."""
    if step >= 1:
        return str(int(round_qty(qty, step)))
    else:
        # Determine decimal places from step
        decimals = max(0, -int(math.floor(math.log10(step)))) if step > 0 else 8
        rounded = round_qty(qty, step)
        return f"{rounded:.{decimals}f}"

def set_leverage(symbol, leverage):
    body = {"category": "linear", "symbol": symbol, "buyLeverage": str(leverage), "sellLeverage": str(leverage)}
    return post("/v5/position/set-leverage", body)

def place_perp_order(symbol, side, qty_str, sl_price=None):
    body = {
        "category": "linear",
        "symbol": symbol,
        "side": side,
        "orderType": "Market",
        "qty": qty_str,
        "timeInForce": "GTC"
    }
    if sl_price:
        body["stopLoss"] = str(sl_price)
    
    res = post("/v5/order/create", body)
    if res.get("retCode") == 0:
        logger.info(f"ORDER PLACED: {side} {qty_str} {symbol} SL={sl_price}")
        append_jsonl(ROOT, "trades/perpetuals.jsonl", {
            "action": "open",
            "symbol": symbol,
            "side": side,
            "qty": qty_str,
            "sl": str(sl_price),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        })
    else:
        logger.error(f"Order failed: {res.get('retMsg')} | qty={qty_str}")
    return res

def check_opportunities(usdt_bal):
    tickers = get("/v5/market/tickers", "category=linear")
    if tickers.get("retCode") != 0: 
        logger.warning("Failed to fetch tickers")
        return
    
    candidates = []
    for t in tickers["result"]["list"]:
        vol = safe_float(t.get("turnover24h"), 0)
        ask = safe_float(t.get("askPrice"), 0)
        bid = safe_float(t.get("bidPrice"), 0)
        last = safe_float(t.get("lastPrice"), 1)
        fr = safe_float(t.get("fundingRate"), 0)
        
        if last <= 0 or vol < MIN_VOLUME_24H:
            continue
            
        spread = abs(ask - bid) / last if last > 0 else 999
        
        if spread <= MAX_SPREAD_PCT:
            candidates.append({
                "symbol": t["symbol"],
                "price": last,
                "funding": fr,
                "vol": vol
            })
    
    candidates.sort(key=lambda x: abs(x["funding"]), reverse=True)
    logger.info(f"Found {len(candidates)} valid candidates from {len(tickers['result']['list'])} tickers")
    
    for c in candidates[:5]:
        sym = c["symbol"]
        fr = c["funding"]
        price = c["price"]
        
        if abs(fr) > FUNDING_THRESHOLD:
            logger.info(f"OPPORTUNITY: {sym} Funding={fr:.6f} Price={price}")
            
            spec = get_instrument_spec(sym)
            logger.info(f"  Spec: minQty={spec['minOrderQty']} step={spec['qtyStep']} minNotional={spec['minNotional']}")
            
            risk_amt = usdt_bal * (RISK_PER_TRADE_PCT / 100)
            sl_dist_pct = 0.02
            raw_qty = risk_amt / (price * sl_dist_pct)
            
            qty = round_qty(raw_qty, spec["qtyStep"])
            
            notional = qty * price
            if notional < spec["minNotional"] or qty < spec["minOrderQty"]:
                qty = spec["minOrderQty"]
                notional = qty * price
                if notional < 5:
                    logger.info(f"Skipping {sym}: min order ${notional:.2f} too small")
                    continue
            
            qty_str = format_qty(qty, spec["qtyStep"])
            logger.info(f"  Computed qty: raw={raw_qty:.8f} -> formatted={qty_str} notional=${notional:.2f}")
            
            side = "Sell" if fr > 0 else "Buy"
            sl = price * (1 + sl_dist_pct) if side == "Sell" else price * (1 - sl_dist_pct)
            
            pos = get("/v5/position/list", f"category=linear&symbol={sym}")
            has_pos = False
            if pos.get("retCode") == 0:
                for p in pos["result"].get("list", []):
                    if safe_float(p.get("size"), 0) > 0:
                        has_pos = True
                        break
            
            if not has_pos:
                set_leverage(sym, MAX_LEVERAGE)
                result = place_perp_order(sym, side, qty_str, sl_price=round(sl, 8))
                
                if result.get("retCode") == 0:
                    logger.info(f"SUCCESS: Opened {side} on {sym}")
                    time.sleep(3)
                    return
                else:
                    logger.warning(f"Failed to open {sym}, trying next candidate")
                    time.sleep(1)
            else:
                logger.info(f"Skipping {sym}: already have position")

if __name__ == "__main__":
    logger.info("=== BYBIT PERPETUAL COMPOUNDER STARTED ===")
    logger.info(f"Mandate: Max Lev={MAX_LEVERAGE}x, Risk={RISK_PER_TRADE_PCT}%, FundThresh={FUNDING_THRESHOLD}")
    
    while True:
        try:
            bal = get_wallet_balance()
            logger.info(f"Wallet USDT: {bal:.4f}")
            
            if bal >= 10:
                check_opportunities(bal)
            else:
                logger.warning(f"Insufficient balance for perp trading (<10 USDT)")
                
            time.sleep(60)
        except Exception as e:
            logger.error(f"Main loop error: {e}", exc_info=True)
            time.sleep(30)
