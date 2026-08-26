#!/usr/bin/env python3
"""
Binance Margin Trader v9 - Fixed MIN_NOTIONAL + BUY-first strategy
Target: 1,000,000 USDT via cross-margin trading cycles
Key fixes: Proper minNotional filter, BUY preference, robust qty rounding
"""
import sys, os, json, time, hmac, hashlib, requests, math, logging
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, "/Agentic/build/lib")
from agentic.aro.store import append_jsonl

ROOT = Path("/Agentic")
LOG_FILE = ROOT / "logs" / "binance_margin_trader.log"
TRADES_LOG = ROOT / "data" / "aro" / "trades" / "binance_margin.jsonl"
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
logger = logging.getLogger("BinanceMarginTrader")

env_path = ROOT / ".env"
env_vars = {}
for line in env_path.read_text().splitlines():
    if '=' in line and not line.startswith('#'):
        k, v = line.split('=', 1)
        env_vars[k.strip()] = v.strip()

API_KEY = env_vars.get('BINANCE_API_KEY', '')
SECRET = env_vars.get('BINANCE_API_SECRET', '')
BASE = "https://api.binance.com"
RECV_WINDOW = "10000"

TARGET_USDT = 1_000_000
RISK_PER_TRADE_PCT = 80.0  # Very aggressive with small balance
MIN_VOLUME_24H = 5_000_000
CHANGE_THRESHOLD = 0.3
CYCLE_INTERVAL = 90
MIN_TRADE_BALANCE = 5.0
DEFAULT_MIN_NOTIONAL = 10.0  # Safe default for most pairs

_server_time_offset = 0
_symbol_filters = {}

def sign(params):
    return hmac.new(SECRET.encode(), params.encode(), hashlib.sha256).hexdigest()

def sync_server_time():
    global _server_time_offset
    try:
        resp = requests.get(f"{BASE}/api/v3/time", timeout=5)
        if resp.status_code == 200:
            server_ts = resp.json()["serverTime"]
            local_ts = int(time.time() * 1000)
            _server_time_offset = server_ts - local_ts
            logger.info(f"Server time synced: offset={_server_time_offset}ms")
    except Exception as e:
        logger.warning(f"Server time sync failed: {e}")

def get_timestamp():
    return str(int(time.time() * 1000) + _server_time_offset)

def api_get(path, extra_params=""):
    s = requests.Session()
    s.trust_env = False
    ts = get_timestamp()
    parts = []
    if extra_params:
        parts.append(extra_params)
    parts.append(f"recvWindow={RECV_WINDOW}")
    parts.append(f"timestamp={ts}")
    query = "&".join(parts)
    sig = sign(query)
    url = f"{BASE}{path}?{query}&signature={sig}"
    h = {"X-MBX-APIKEY": API_KEY}
    try:
        resp = s.get(url, headers=h, timeout=15)
        data = resp.json()
        if isinstance(data, dict) and "code" in data and data["code"] != 0:
            logger.error(f"API error on {path}: code={data['code']} msg={data.get('msg','')}")
            return None
        return data
    except Exception as e:
        logger.error(f"GET {path} failed: {e}")
        return None
    finally:
        s.close()

def api_post(path, body_params):
    s = requests.Session()
    s.trust_env = False
    ts = get_timestamp()
    parts = [f"{k}={v}" for k, v in body_params.items()]
    parts.append(f"recvWindow={RECV_WINDOW}")
    parts.append(f"timestamp={ts}")
    query = "&".join(parts)
    sig = sign(query)
    url = f"{BASE}{path}?{query}&signature={sig}"
    h = {"X-MBX-APIKEY": API_KEY}
    try:
        resp = s.post(url, headers=h, timeout=15)
        data = resp.json()
        if isinstance(data, dict) and "code" in data and data["code"] != 0:
            return data
        return data
    except Exception as e:
        logger.error(f"POST {path} failed: {e}")
        return None
    finally:
        s.close()

def get_symbol_filters(symbol):
    if symbol in _symbol_filters:
        return _symbol_filters[symbol]
    try:
        s = requests.Session()
        s.trust_env = False
        resp = s.get(f"{BASE}/api/v3/exchangeInfo", params={"symbol": symbol}, timeout=10)
        s.close()
        if resp.status_code == 200:
            info = resp.json()
            symbols = info.get("symbols", [])
            if symbols:
                sym_info = symbols[0]
                filters = {}
                for f in sym_info.get("filters", []):
                    ft = f.get("filterType", "")
                    if ft == "LOT_SIZE":
                        filters["minQty"] = float(f.get("minQty", 0))
                        filters["maxQty"] = float(f.get("maxQty", 999999))
                        filters["stepSize"] = float(f.get("stepSize", 0.00001))
                    elif ft in ("MIN_NOTIONAL", "NOTIONAL"):
                        filters["minNotional"] = float(f.get("minNotional", DEFAULT_MIN_NOTIONAL))
                _symbol_filters[symbol] = filters
                return filters
    except Exception as e:
        logger.warning(f"Failed to get filters for {symbol}: {e}")
    return {"minQty": 0.00001, "maxQty": 999999, "stepSize": 0.00001, "minNotional": DEFAULT_MIN_NOTIONAL}

def round_step(qty, step):
    if step <= 0 or qty <= 0:
        return qty
    precision = max(0, -int(math.floor(math.log10(step)))) if step < 1 else 0
    rounded = math.floor(qty / step) * step
    result = round(rounded, precision)
    if result <= 0 and qty > 0:
        result = round(step, precision)
    return result

def get_margin_balance():
    res = api_get("/sapi/v1/margin/account", "type=CROSS")
    if res is None or not isinstance(res, dict) or "userAssets" not in res:
        return 0.0
    for a in res["userAssets"]:
        if a.get("asset") == "USDT":
            for field in ["netAsset", "free"]:
                try:
                    val = float(a.get(field, 0))
                    if val > 0:
                        return val
                except (ValueError, TypeError):
                    continue
    return 0.0

def get_open_margin_positions():
    """Fetch open margin positions (assets with debt or positive net asset)"""
    res = api_get("/sapi/v1/margin/account", "type=CROSS")
    positions = []
    if res and isinstance(res, dict) and "userAssets" in res:
        for a in res["userAssets"]:
            asset = a.get("asset", "")
            if asset == "USDT":
                continue
            try:
                net = float(a.get("netAsset", 0))
                free = float(a.get("free", 0))
                borrowed = float(a.get("borrowed", 0))
                if abs(net) > 0.00001 or borrowed > 0:
                    positions.append({
                        "asset": asset,
                        "symbol": asset + "USDT",
                        "net": net,
                        "free": free,
                        "borrowed": borrowed
                    })
            except (ValueError, TypeError):
                continue
    return positions

def close_position_if_needed(pos, usdt_price=None):
    """Close a margin position based on TP/SL or repayment needs"""
    symbol = pos["symbol"]
    net = pos["net"]
    borrowed = pos["borrowed"]
    
    # Skip if no meaningful position
    if abs(net) < 0.00001:
        return False
    
    # Get current price
    try:
        s = requests.Session()
        s.trust_env = False
        resp = s.get(f"{BASE}/api/v3/ticker/price", params={"symbol": symbol}, timeout=5)
        s.close()
        if resp.status_code != 200:
            return False
        price = float(resp.json().get("price", 0))
        if price <= 0:
            return False
    except Exception as e:
        logger.warning(f"Price fetch failed for {symbol}: {e}")
        return False
    
    notional = abs(net) * price
    filters = get_symbol_filters(symbol)
    min_notional = filters.get("minNotional", DEFAULT_MIN_NOTIONAL)
    
    if notional < min_notional:
        logger.info(f"Position {symbol} notional ${notional:.2f} < min ${min_notional:.0f}, holding dust")
        return False
    
    # Determine side: SELL if we hold asset (net > 0), BUY to repay if we owe (net < 0 / borrowed > 0)
    side = None
    qty = abs(net)
    
    if net > 0:
        # We own the asset -> SELL back to USDT
        side = "SELL"
        # Simple momentum exit: if RSI > 65 or price up > 2% since entry approximation
        klines = get_klines(symbol, interval="1h", limit=14)
        rsi = calc_rsi(klines) if klines else 50.0
        if rsi < 55:
            logger.info(f"Holding {symbol}: RSI={rsi:.1f} not overbought yet")
            return False
    elif borrowed > 0:
        # We owe the asset -> BUY to repay
        side = "BUY"
    else:
        return False
    
    logger.info(f"CLOSING {symbol}: {side} qty={qty:.8f} @ ~${price:.4f} (net={net:.8f}, borrowed={borrowed:.8f})")
    result = place_margin_order(symbol, side, qty)
    
    if result and isinstance(result, dict) and result.get("orderId"):
        append_jsonl(ROOT, "trades/binance_margin.jsonl", {
            "action": "close",
            "symbol": symbol,
            "side": side,
            "qty": f"{qty:.10f}".rstrip('0').rstrip('.'),
            "orderId": str(result.get("orderId")),
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        return True
    
    return False

def manage_open_positions(usdt_bal):
    """Check all open margin positions and close/repay as needed"""
    positions = get_open_margin_positions()
    if not positions:
        logger.info("No open margin positions to manage")
        return False
    
    logger.info(f"Managing {len(positions)} open position(s): {[p['symbol'] for p in positions]}")
    closed_any = False
    for pos in positions:
        try:
            if close_position_if_needed(pos):
                closed_any = True
                time.sleep(2)
        except Exception as e:
            logger.error(f"Error managing position {pos['symbol']}: {e}", exc_info=True)
    
    return closed_any

def get_spot_balance():
    res = api_get("/api/v3/account")
    if res and isinstance(res, dict) and "balances" in res:
        for b in res["balances"]:
            if b.get("asset") == "USDT":
                try:
                    return float(b.get("free", 0))
                except (ValueError, TypeError):
                    return 0.0
    return 0.0

def transfer_to_margin(amount):
    res = api_post("/sapi/v1/asset/transfer", {
        "type": "MAIN_MARGIN",
        "asset": "USDT",
        "amount": str(round(amount, 2))
    })
    if res and isinstance(res, dict) and res.get("tranId"):
        logger.info(f"Transferred {amount:.2f} USDT to margin (tranId={res['tranId']})")
        return True
    logger.warning(f"Transfer failed: {res}")
    return False

def get_klines(symbol, interval="1h", limit=24):
    try:
        s = requests.Session()
        s.trust_env = False
        resp = s.get(f"{BASE}/api/v3/klines", params={
            "symbol": symbol, "interval": interval, "limit": limit
        }, timeout=10)
        s.close()
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return []

def calc_rsi(klines, period=14):
    if len(klines) < period + 1:
        return 50.0
    closes = [float(k[4]) for k in klines]
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def place_margin_order(symbol, side, qty):
    filters = get_symbol_filters(symbol)
    step = filters.get("stepSize", 0.00001)
    min_qty = filters.get("minQty", 0.00001)
    min_notional = filters.get("minNotional", DEFAULT_MIN_NOTIONAL)
    
    valid_qty = round_step(qty, step)
    if valid_qty < min_qty:
        valid_qty = min_qty
    
    qty_str = f"{valid_qty:.10f}".rstrip('0').rstrip('.')
    
    res = api_post("/sapi/v1/margin/order", {
        "symbol": symbol,
        "side": side,
        "type": "MARKET",
        "quantity": qty_str,
        "isIsolated": "FALSE",
        "sideEffectType": "AUTO_BORROW_REPAY"
    })
    
    if res is None:
        logger.error(f"Order FAILED for {symbol}: No response")
        return None
    
    if isinstance(res, dict) and "code" in res:
        err_code = res["code"]
        err_msg = res.get("msg", "")
        if err_code == -3045:
            logger.warning(f"Borrow unavailable for {symbol} (-3045). Skipping.")
            return {"skip": True, "reason": "borrow_unavailable"}
        elif err_code == -1013:
            logger.warning(f"Filter fail for {symbol}: qty={qty_str} step={step} minQty={min_qty} minNotional={min_notional}. Skipping.")
            return {"skip": True, "reason": "filter_fail"}
        elif err_code == -2010:
            logger.warning(f"Insufficient balance for {symbol} (-2010). Skipping.")
            return {"skip": True, "reason": "insufficient_balance"}
        else:
            logger.error(f"Order FAILED for {symbol}: code={err_code} msg={err_msg}")
            return None
    
    if res.get("orderId"):
        logger.info(f"ORDER PLACED: {side} {qty_str} {symbol} @ MARKET (orderId={res['orderId']})")
        append_jsonl(ROOT, "trades/binance_margin.jsonl", {
            "action": "open",
            "symbol": symbol,
            "side": side,
            "qty": qty_str,
            "orderId": str(res.get("orderId")),
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        return res
    
    logger.error(f"Order FAILED for {symbol}: unexpected response {res}")
    return None

def check_and_trade(usdt_bal):
    try:
        s = requests.Session()
        s.trust_env = False
        tickers_resp = s.get(f"{BASE}/api/v3/ticker/24hr", timeout=15)
        s.close()
        tickers = tickers_resp.json() if tickers_resp.status_code == 200 else []
    except Exception as e:
        logger.error(f"Ticker fetch failed: {e}")
        return False
    
    margin_res = api_get("/sapi/v1/margin/allPairs")
    margin_symbols = set()
    if isinstance(margin_res, list):
        margin_symbols = {p["base"] + p["quote"] for p in margin_res if p.get("isMarginTrade")}
    logger.info(f"Margin-eligible pairs: {len(margin_symbols)}")
    
    candidates = []
    for t in tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT") or sym not in margin_symbols:
            continue
        try:
            vol = float(t.get("quoteVolume", 0))
            last = float(t.get("lastPrice", 0))
            high = float(t.get("highPrice", 0))
            low = float(t.get("lowPrice", 0))
            change_pct = float(t.get("priceChangePercent", 0))
        except (ValueError, TypeError):
            continue
        if vol < MIN_VOLUME_24H or last <= 0:
            continue
        volatility = (high - low) / last if last > 0 else 0
        score = abs(change_pct) * (1 + volatility * 10)
        candidates.append({
            "symbol": sym, "price": last, "change_pct": change_pct,
            "volatility": volatility, "score": score, "vol": vol
        })
    
    candidates.sort(key=lambda x: x["score"], reverse=True)
    logger.info(f"Candidates: {len(candidates)} from {len(tickers)} tickers")
    
    traded = False
    for i, c in enumerate(candidates[:25]):
        sym = c["symbol"]
        price = c["price"]
        change = c["change_pct"]
        
        rsi = 50.0
        klines = get_klines(sym)
        if klines:
            rsi = calc_rsi(klines)
        
        # BUY-first strategy to avoid borrow issues
        side = None
        if change < -CHANGE_THRESHOLD and rsi < 45:
            side = "BUY"
        elif change < -1.0:
            side = "BUY"
        elif rsi < 35:
            side = "BUY"
        elif change > CHANGE_THRESHOLD and rsi > 70:
            side = "SELL"
        elif abs(change) > 2.0 and rsi > 65:
            side = "SELL"
        
        risk_amt = usdt_bal * (RISK_PER_TRADE_PCT / 100)
        qty = risk_amt / price
        
        # Get filters BEFORE checking notional to use correct minNotional
        filters = get_symbol_filters(sym)
        min_notional = filters.get("minNotional", DEFAULT_MIN_NOTIONAL)
        notional = qty * price
        
        if not side:
            logger.info(f"  [{i+1}] {sym}: chg={change:+.2f}% rsi={rsi:.1f} -> NO SIGNAL")
            continue
        if notional < min_notional:
            logger.info(f"  [{i+1}] {sym}: {side} notional ${notional:.2f} < ${min_notional:.0f} (min) -> SKIP")
            continue
        
        logger.info(f"  [{i+1}] {sym}: {side} chg={change:+.2f}% rsi={rsi:.1f} vol=${c['vol']/1e6:.1f}M qty={qty:.6f} notional=${notional:.2f}")
        result = place_margin_order(sym, side, qty)
        
        if result and isinstance(result, dict):
            if result.get("skip"):
                logger.info(f"    Skipping {sym} ({result['reason']}), trying next...")
                continue
            if result.get("orderId"):
                traded = True
                time.sleep(3)
                break
        elif result is None:
            logger.info(f"    Order failed for {sym}, trying next...")
            continue
    
    return traded

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("BINANCE MARGIN TRADER v9 STARTED")
    logger.info(f"Target: ${TARGET_USDT:,} | Risk: {RISK_PER_TRADE_PCT}% | Threshold: {CHANGE_THRESHOLD}%")
    logger.info(f"Cycle: {CYCLE_INTERVAL}s | MinVol: ${MIN_VOLUME_24H/1e6:.0f}M | MinBal: ${MIN_TRADE_BALANCE}")
    logger.info(f"Strategy: BUY-first + proper MIN_NOTIONAL filtering")
    logger.info("=" * 60)
    
    sync_server_time()
    
    cycle = 0
    while True:
        try:
            cycle += 1
            if cycle % 10 == 1:
                sync_server_time()
            
            margin_bal = get_margin_balance()
            spot_bal = get_spot_balance()
            total = margin_bal + spot_bal
            
            logger.info(f"\n--- CYCLE {cycle} --- Margin=${margin_bal:.4f} Spot=${spot_bal:.4f} Total=${total:.4f}")
            
            if total >= TARGET_USDT:
                logger.info(f"TARGET REACHED: ${total:,.2f} USDT!")
                append_jsonl(ROOT, "ledger.jsonl", {
                    "kind": "goal_achieved", "platform": "binance",
                    "balance_usdt": str(total), "target_usdt": str(TARGET_USDT),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                break
            
            if spot_bal > 2 and margin_bal < spot_bal:
                transfer_to_margin(spot_bal - 0.5)
                time.sleep(2)
                margin_bal = get_margin_balance()
                logger.info(f"After transfer: Margin=${margin_bal:.4f}")
            
            if margin_bal >= MIN_TRADE_BALANCE:
                manage_open_positions(margin_bal)
                check_and_trade(margin_bal)
            else:
                logger.warning(f"Insufficient margin (${margin_bal:.2f}). Need ${MIN_TRADE_BALANCE}+ to trade.")
            
            time.sleep(CYCLE_INTERVAL)
            
        except KeyboardInterrupt:
            logger.info("Stopped by user")
            break
        except Exception as e:
            logger.error(f"Cycle error: {e}", exc_info=True)
            time.sleep(30)
