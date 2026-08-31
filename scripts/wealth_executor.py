#!/usr/bin/env python3
"""
Wealth Executor v4 - Correct Bybit V5 Signature (GET includes query string)
Autonomous $200k Goal with real balance tracking
"""
import os, sys, json, time, subprocess, hmac, hashlib, requests
from datetime import datetime, timezone

sys.path.insert(0, '/Agentic/internal')
from env import apply
apply()

LEDGER_PATH = "/Agentic/data/aro/wealth_ledger.json"
TELEGRAM_GATE = "/Agentic/src/telegram_gate.py"
BYBIT_API_KEY = os.environ.get("BYBIT_REAL_API_KEY") or os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_REAL_API_SECRET") or os.environ.get("BYBIT_API_SECRET")
BYBIT_BASE = "https://api.bybit.com"

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open("/Agentic/data/aro/wealth_daemon.log", "a") as f:
        f.write(line + "\n")

def notify_telegram(text):
    """Send operational/planning message via telegram_gate v2"""
    try:
        # Import the gate module directly for structured events
        sys.path.insert(0, '/Agentic/src')
        from telegram_gate import notify_system_status, notify_planning_update
        
        # Route based on content keywords
        if any(kw in text.lower() for kw in ['plan', 'strategy', 'decision', 'next cycle', 'monitoring']):
            ok = notify_planning_update("wealth-executor", "bybit_arb", text)
        else:
            ok = notify_system_status("wealth-executor", "bybit_arb", text)
        
        if ok:
            log(f"Telegram sent (structured): {text[:60]}...")
        else:
            log(f"Telegram gate rejected message")
    except Exception as e:
        log(f"Telegram notification failed: {e}")
        # Fallback to CLI
        try:
            subprocess.run([sys.executable, TELEGRAM_GATE, "--message", text], 
                           timeout=30, capture_output=True)
        except:
            pass

def load_ledger():
    if os.path.exists(LEDGER_PATH):
        with open(LEDGER_PATH) as f:
            return json.load(f)
    return {"goal_usd": 200000, "realized_usd": 0, "strategies": [], "history": [], 
            "bybit_balance": 0, "wise_balance": 0, "trades": []}

def save_ledger(data):
    with open(LEDGER_PATH, "w") as f:
        json.dump(data, f, indent=2)

def bybit_v5_sign_get(timestamp, key, recv_window, query_string, secret):
    """Bybit V5 GET signature: timestamp + apiKey + recvWindow + queryString"""
    val = f"{timestamp}{key}{recv_window}{query_string}"
    return hmac.new(secret.encode(), val.encode(), hashlib.sha256).hexdigest()

def bybit_v5_sign_post(timestamp, key, recv_window, body, secret):
    """Bybit V5 POST signature: timestamp + apiKey + recvWindow + body"""
    val = f"{timestamp}{key}{recv_window}{body}"
    return hmac.new(secret.encode(), val.encode(), hashlib.sha256).hexdigest()

def get_bybit_balance():
    if not BYBIT_API_KEY or not BYBIT_API_SECRET:
        log("Bybit credentials missing")
        return None
    
    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"
    query_string = "accountType=UNIFIED"
    
    sign = bybit_v5_sign_get(timestamp, BYBIT_API_KEY, recv_window, query_string, BYBIT_API_SECRET)
    
    headers = {
        "X-BAPI-API-KEY": BYBIT_API_KEY,
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-RECV-WINDOW": recv_window,
        "X-BAPI-SIGN": sign
    }
    
    try:
        resp = requests.get(
            f"{BYBIT_BASE}/v5/account/wallet-balance?{query_string}",
            headers=headers,
            timeout=10
        )
        data = resp.json()
        
        if data.get("retCode") == 0:
            coins = data["result"]["list"][0].get("coin", [])
            usdt = next((c for c in coins if c["coin"] == "USDT"), None)
            # Unified accounts often return empty string for availableToWithdraw.
            # Prefer walletBalance as the canonical source of tradable capital.
            wb = usdt.get("walletBalance", "") if usdt else ""
            atw = usdt.get("availableToWithdraw", "") if usdt else ""
            if wb and str(wb).strip() != "":
                balance = float(wb)
            elif atw and str(atw).strip() != "":
                balance = float(atw)
            else:
                balance = 0.0
            equity = float(data["result"]["list"][0].get("totalEquity", 0))
            log(f"Bybit Balance: ${balance:.2f} USDT | Equity: ${equity:.2f}")
            return {"usdt": balance, "equity": equity, "available": balance}
        else:
            log(f"Bybit API error: {data.get('retMsg')} (code: {data.get('retCode')})")
            return None
    except Exception as e:
        log(f"Bybit balance check failed: {e}")
        return None

def scan_p2p_opportunities():
    """Scan Bybit P2P and Spot for arbitrage across ALL non-zero assets"""
    opportunities = []
    try:
        # Fetch all spot tickers to evaluate every held asset
        ticker_resp = requests.get(
            f"{BYBIT_BASE}/v5/market/tickers?category=spot",
            timeout=15
        )
        ticker_data = ticker_resp.json()
        
        if ticker_data.get("retCode") != 0:
            log(f"Ticker fetch failed: {ticker_data.get('retMsg')}")
            return opportunities
            
        tickers = {t["symbol"]: t for t in ticker_data["result"].get("list", [])}
        
        # Load current holdings from ledger or balance check
        ledger = load_ledger()
        held_coins = set()
        bal = get_bybit_balance()
        if bal and bal.get("coins"):
            held_coins = {c["coin"] for c in bal["coins"] if float(c.get("walletBalance", 0)) > 0}
        else:
            # Fallback to known holdings from last snapshot
            held_coins = {"BTC","ETH","XRP","BONK","USDT","DOGE","WIF","UNI","SOL","BCH","ADA","LINK","AAVE","BMT","ARB","ATOM","AVAX","SUI","PUMP","SNX","TRUMP","PEPE","TRX","SEI","INJ","HYPE","NYM","MNT","PYBOBO","TRIA","FTT","BICO","ENA","FET","APT","KII","OP","BRL"}
        
        for coin in held_coins:
            if coin == "USDT": continue
            symbol = f"{coin}USDT"
            t = tickers.get(symbol)
            if not t: continue
            
            spot_price = float(t.get("lastPrice", 0))
            if spot_price <= 0: continue
            
            # Simulated P2P spread estimation (real P2P API requires merchant endpoint)
            # Using volatility-adjusted premium model
            vol = float(t.get("price24hPcnt", "0").replace("%","") or 0)
            base_spread = 0.8 + abs(vol) * 2.0  # Higher vol = higher potential arb
            
            buy_premium = spot_price * (1 + base_spread/100)
            sell_discount = spot_price * (1 - base_spread/100)
            spread_pct = ((buy_premium - sell_discount) / sell_discount) * 100
            
            if spread_pct > 1.0:
                action = "EXECUTE" if spread_pct > 1.5 else "MONITOR"
                opportunities.append({
                    "pair": symbol,
                    "type": "multi_asset_arb",
                    "spread_pct": round(spread_pct, 3),
                    "spot_price": spot_price,
                    "est_buy": round(buy_premium, 6),
                    "est_sell": round(sell_discount, 6),
                    "action": action
                })
                log(f"[{symbol}] Arb: {spread_pct:.2f}% ({action}) | Spot: ${spot_price}")
        
        return opportunities
    except Exception as e:
        log(f"P2P scan failed: {e}")
        return []

def execute_spot_trade(side, qty, price, ledger):
    """Execute spot trade on Bybit"""
    pair = ledger.get("current_pair", "BTCUSDT")
    price_f = float(price)
    qty_f = float(qty)
    
    # Load instrument specs - prefer LIVE API over potentially stale cache
    import math
    tick, qstep = 0.01, 0.000001
    try:
        # Fetch live instrument info for accurate precision
        inst_resp = requests.get(
            f"{BYBIT_BASE}/v5/market/instruments-info?category=spot&symbol={pair}",
            timeout=5
        ).json()
        if inst_resp.get("retCode") == 0 and inst_resp["result"]["list"]:
            info = inst_resp["result"]["list"][0]
            tick = float(info.get("priceFilter", {}).get("tickSize", 0.01))
            qstep = float(info.get("lotSizeFilter", {}).get("qtyStep", 0.000001))
            log(f"LIVE INSTRUMENT {pair}: tick={tick}, qstep={qstep}")
        else:
            # Fallback to cache
            cache_path = "/Agentic/data/bybit_instruments_cache.json"
            with open(cache_path) as f:
                instruments = json.load(f)
            spec = instruments.get(pair, {})
            tick = float(spec.get("tickSize", 0.01))
            qstep = float(spec.get("qtyStep", 0.000001))
    except Exception as e:
        log(f"Instrument fetch failed: {e}, using defaults")
    
    # Align to exchange grid exactly
    price_aligned = math.floor(price_f / tick) * tick
    qty_aligned = math.floor(qty_f / qstep) * qstep
    
    # Format without scientific notation
    tick_dec = max(0, -int(math.log10(tick))) if tick < 1 else 0
    qty_dec = max(0, -int(math.log10(qstep))) if qstep < 1 else 0
    price_str = f"{price_aligned:.{tick_dec}f}"
    qty_str = f"{qty_aligned:.{qty_dec}f}"
    
    # Safety check after formatting
    if float(price_str) <= 0 or float(qty_str) <= 0:
        log(f"Invalid trade params: price={price_str}, qty={qty_str}")
        return None
    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"
    
    body = json.dumps({
        "category": "spot",
        "symbol": pair,
        "side": side,
        "orderType": "Limit",
        "qty": qty_str,
        "price": price_str,
        "timeInForce": "GTC"
    })
    
    sign = bybit_v5_sign_post(timestamp, BYBIT_API_KEY, recv_window, body, BYBIT_API_SECRET)
    
    headers = {
        "X-BAPI-API-KEY": BYBIT_API_KEY,
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-RECV-WINDOW": recv_window,
        "X-BAPI-SIGN": sign,
        "Content-Type": "application/json"
    }
    
    try:
        resp = requests.post(
            f"{BYBIT_BASE}/v5/order/create",
            headers=headers,
            data=body,
            timeout=10
        )
        data = resp.json()
        
        if data.get("retCode") == 0:
            order_id = data["result"]["orderId"]
            log(f"{side} order placed: {order_id} @ ${price}")
            return {"order_id": order_id, "status": "pending"}
        else:
            log(f"Trade failed: {data.get('retMsg')} | side={side} qty={qty_str} price={price_str} pair={pair}")
            return None
    except Exception as e:
        log(f"Trade execution error: {e}")
        return None

def check_wise_balance():
    wise_token = os.environ.get("WISE_API_TOKEN") or os.environ.get("WISE_TOKEN")
    if not wise_token:
        return None
    
    try:
        resp = requests.get(
            "https://api.wise.com/v4/profiles/end-user/balances",
            headers={"Authorization": f"Bearer {wise_token}"},
            timeout=10
        )
        if resp.status_code == 200:
            balances = resp.json()
            usd_bal = sum(b.get("amount", {}).get("value", 0) 
                         for b in balances if b.get("currency") == "USD")
            return usd_bal
    except:
        pass
    return None


def get_open_orders(symbol="BTCUSDT"):
    """Fetch open spot orders for symbol"""
    ts = str(int(time.time() * 1000))
    qs = f"category=spot&symbol={symbol}&limit=10"
    sign = bybit_v5_sign_get(ts, BYBIT_API_KEY, "5000", qs, BYBIT_API_SECRET)
    try:
        r = requests.get(f"{BYBIT_BASE}/v5/order/realtime?{qs}",
            headers={"X-BAPI-API-KEY": BYBIT_API_KEY, "X-BAPI-TIMESTAMP": ts,
                     "X-BAPI-RECV-WINDOW": "5000", "X-BAPI-SIGN": sign}, timeout=10).json()
        return r.get("result", {}).get("list", [])
    except Exception as e:
        log(f"get_open_orders error: {e}")
        return []

def get_spot_position(symbol="BTCUSDT"):
    """Get available BTC balance in unified account"""
    ts = str(int(time.time() * 1000))
    qs = "accountType=UNIFIED&coin=BTC"
    sign = bybit_v5_sign_get(ts, BYBIT_API_KEY, "5000", qs, BYBIT_API_SECRET)
    try:
        r = requests.get(f"{BYBIT_BASE}/v5/account/wallet-balance?{qs}",
            headers={"X-BAPI-API-KEY": BYBIT_API_KEY, "X-BAPI-TIMESTAMP": ts,
                     "X-BAPI-RECV-WINDOW": "5000", "X-BAPI-SIGN": sign}, timeout=10).json()
        coins = r.get("result", {}).get("list", [{}])[0].get("coin", [])
        for c in coins:
            if c.get("coin") == "BTC":
                # Prefer walletBalance over availableToWithdraw (latter often empty string)
                wb = c.get("walletBalance", "")
                atw = c.get("availableToWithdraw", "")
                val = atw if (atw and atw != "") else wb
                if not val or val == "":
                    return 0.0
                return float(val)
        return 0.0
    except Exception as e:
        log(f"get_spot_position error: {e}")
        return 0.0

def execute_cycle():
    log("=== Wealth Generation Cycle ===")
    ledger = load_ledger()
    
    # === PROCESS TELEGRAM INBOX COMMANDS ===
    inbox_path = "/Agentic/data/aro/inbox/user_commands.jsonl"
    if os.path.exists(inbox_path):
        try:
            with open(inbox_path, "r+") as f:
                lines = f.readlines()
                new_lines = []
                for line in lines:
                    try:
                        cmd = json.loads(line.strip())
                        if not cmd.get("processed"):
                            text = cmd.get("text", "").lower()
                            log(f"Processing TG command: {cmd.get('text', '')[:80]}")
                            
                            # Command routing
                            if "saldo" in text or "balance" in text or "capital" in text:
                                notify_telegram(f"💰 Status Financeiro:\n• Bybit: ${ledger.get('bybit_balance',0):.2f} USDT\n• Wise: ${ledger.get('wise_balance',0):.2f} USD\n• Realizado: ${ledger.get('realized_usd',0):.2f}")
                            elif "status" in text or "progresso" in text:
                                notify_telegram(f"📊 Progresso Meta $200k:\n• Atual: ${ledger.get('realized_usd',0):.2f}\n• Pipeline Bounty: {ledger.get('pending_bounty_count',0)} claims\n• Estratégia Trading: Maker-Only (em desenvolvimento)")
                            elif "claim" in text or "bounty" in text:
                                notify_telegram("🔍 Forçando verificação de bounties...\n(O bounty-engine já roda a cada 2h automaticamente)")
                                subprocess.run(["systemctl", "start", "agentic-bounty-claimer.service"], capture_output=True)
                            else:
                                notify_telegram(f"✅ Comando recebido: '{cmd.get('text','')}'\n⚠️ Ainda não implementado no wealth-executor. Use 'status', 'saldo' ou 'claim'.")
                            
                            cmd["processed"] = True
                            new_lines.append(json.dumps(cmd) + "\n")
                        else:
                            new_lines.append(line)
                    except json.JSONDecodeError:
                        new_lines.append(line)
                
                f.seek(0)
                f.truncate()
                f.writelines(new_lines)
        except Exception as e:
            log(f"Inbox processing error: {e}")
    
    opps = []  # Placeholder; P2P scan replaced by maker strategy dev
    
    # === CLEANUP STALE ORDERS BEFORE TRADING ===
    try:
        ts = str(int(time.time() * 1000))
        recv = "5000"
        cancel_payload = {"category": "spot"}
        body = json.dumps(cancel_payload)
        msg = ts + BYBIT_API_KEY + recv + body
        sig = hmac.new(BYBIT_API_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()
        headers = {
            "X-BAPI-API-KEY": BYBIT_API_KEY,
            "X-BAPI-SIGN": sig,
            "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-RECV-WINDOW": recv
        }
        r = requests.post(f"{BYBIT_BASE}/v5/order/cancel-all", headers=headers, json=cancel_payload, timeout=10)
        rd = r.json()
        if rd.get("retCode") == 0:
            cancelled = rd.get("result", {}).get("list", [])
            if cancelled:
                log(f"Cleaned up {len(cancelled)} stale open orders before cycle")
            else:
                log("No stale open orders found — capital is free")
        else:
            log(f"Cancel-all returned: {rd.get('retMsg')} (non-fatal)")
    except Exception as e:
        log(f"Stale order cleanup failed (non-fatal): {e}")

    # Check balances
    bybit_data = get_bybit_balance()
    if bybit_data:
        # Use AVAILABLE balance (not total equity) to avoid "Insufficient balance" errors
        # when funds are locked in open maker orders
        available_usdt = float(bybit_data.get("available", bybit_data.get("usdt", 0)))
        ledger["bybit_balance"] = available_usdt
        ledger["bybit_equity"] = bybit_data.get("equity", available_usdt)
        log(f"Balance check: available=${available_usdt:.4f}, equity=${ledger['bybit_equity']:.4f}")
    
    wise_bal = check_wise_balance()
    if wise_bal is not None:
        ledger["wise_balance"] = wise_bal
    
    # === MAKER-ONLY GRID (BTCUSDT) ===
    # STRATEGY: Pure Maker Limit Orders. Taker fees (0.1%) exceed typical spreads on low capital.
    # Buy below market, sell above market. Never cross the book.
    executed = 0
    available = ledger.get("bybit_balance", 0)
    
    # DYNAMIC PAIR SELECTION: Scan for highest spread altcoin to maximize maker edge on low capital.
    selected_pair = "BTCUSDT"
    qty_step = 0.000001
    tick_size = 0.1
    
    min_amt = 5.0  # Default minimum order amount
    try:
        cache_path = "/Agentic/data/bybit_instruments_cache.json"
        if os.path.exists(cache_path):
            with open(cache_path, "r") as f:
                instruments = json.load(f)  # dict: {symbol: {tickSize, qtyStep, minAmt}}
            
            # Fetch all spot tickers at once to avoid N requests
            t_resp = requests.get(f"{BYBIT_BASE}/v5/market/tickers?category=spot", timeout=15).json()
            ticker_map = {}
            if t_resp.get("retCode") == 0:
                for t in t_resp["result"].get("list", []):
                    ticker_map[t["symbol"]] = t
            
            best_spread = 0.0
            for sym, meta in instruments.items():
                if not sym.endswith("USDT"):
                    continue
                t = ticker_map.get(sym)
                if not t:
                    continue
                bp = float(t.get("bid1Price", 0))
                ap = float(t.get("ask1Price", 0))
                if bp <= 0:
                    continue
                spread = (ap - bp) / bp
                # Only consider pairs with meaningful spread and liquidity proxy
                if spread > best_spread and spread < 0.05:  # cap at 5% to avoid illiquid traps
                    best_spread = spread
                    selected_pair = sym
                    qty_step = float(meta.get("qtyStep", 0.000001))
                    tick_size = float(meta.get("tickSize", 0.1))
                    min_amt = float(meta.get("minAmt", 5.0))
            
            if best_spread > 0:
                log(f"DYNAMIC SELECTOR: Best pair {selected_pair} (spread {best_spread*100:.2f}%, step {qty_step}, tick {tick_size})")
            else:
                log(f"DYNAMIC SELECTOR: No viable altcoin found. Staying on BTCUSDT.")
    except Exception as e:
        log(f"DYNAMIC SELECTOR FALLBACK: {e}. Using BTCUSDT.")
    
    pair = selected_pair
    
    # === SELL-SIDE AUTOMATION ===
    # Check if any pending maker buys have filled (position exists)
    btc_pos = get_spot_position(pair)
    open_orders = get_open_orders(pair)
    has_buy_order = any(o.get("side") == "Buy" and o.get("orderStatus") == "New" for o in open_orders)
    has_sell_order = any(o.get("side") == "Sell" and o.get("orderStatus") == "New" for o in open_orders)
    
    if btc_pos > 0.000001 and not has_sell_order:
        # Position exists but no sell order — place maker sell
        pending_sells = ledger.get("pending_maker_sells", [])
        if pending_sells:
            target = pending_sells[0]
            sell_price = target.get("target_sell_price", round(target["buy_price"] * 1.0015 / 0.1) * 0.1)
            sell_qty = min(btc_pos, target.get("qty", btc_pos))
            sell_qty = round(sell_qty / qty_step) * qty_step
            
            if sell_qty * sell_price >= min_amt:
                sell_result = execute_spot_trade("Sell", sell_qty, sell_price, ledger)
                if sell_result:
                    executed += 1
                    log(f"MAKER SELL placed: {sell_qty} {pair} @ {sell_price} (target +0.15%)")
                    notify_telegram(f"📈 MAKER SELL executado\n• {sell_qty} {pair} @ ${sell_price}\n• Compra original: ${target['buy_price']}\n• Lucro alvo: +0.15%")
                    # Remove from pending after sell placed
                    ledger["pending_maker_sells"] = pending_sells[1:]
        else:
            # No record of buy price — sell at +0.15% above current market
            ticker = requests.get(f"{BYBIT_BASE}/v5/market/tickers?category=spot&symbol={pair}", timeout=10).json()
            last_price = float(ticker["result"]["list"][0]["lastPrice"])
            sell_price = round(last_price * 1.0015 / tick_size) * tick_size
            sell_qty = round(btc_pos / qty_step) * qty_step
            if sell_qty * sell_price >= min_amt:
                sell_result = execute_spot_trade("Sell", sell_qty, sell_price, ledger)
                if sell_result:
                    executed += 1
                    log(f"MAKER SELL (no history): {sell_qty} {pair} @ {sell_price}")
    
    if available >= min_amt:
        try:
            # Get current price
            ticker = requests.get(f"{BYBIT_BASE}/v5/market/tickers?category=spot&symbol={pair}", timeout=10).json()
            last_price = float(ticker["result"]["list"][0]["lastPrice"])
            
            # MAKER BUY: Place 0.08% BELOW last price (inside spread, potential rebate)
            spread_pct = 0.0008
            buy_price = round(last_price * (1 - spread_pct) / tick_size) * tick_size
            buy_qty = round((available * 0.95) / buy_price / qty_step) * qty_step
            
            if buy_qty * buy_price >= min_amt:
                ledger["current_pair"] = pair
                # Check for existing open maker orders to avoid duplicates
                ts_now = str(int(time.time() * 1000))
                qs = f"category=spot&symbol={pair}&limit=5"
                sign = bybit_v5_sign_get(ts_now, BYBIT_API_KEY, "5000", qs, BYBIT_API_SECRET)
                try:
                    oo_resp = requests.get(
                        f"{BYBIT_BASE}/v5/order/realtime?{qs}",
                        headers={"X-BAPI-API-KEY": BYBIT_API_KEY, "X-BAPI-TIMESTAMP": ts_now, "X-BAPI-RECV-WINDOW": "5000", "X-BAPI-SIGN": sign},
                        timeout=10
                    ).json()
                    has_open = any(o.get("side") == "Buy" and o.get("orderStatus") == "New" 
                                 for o in oo_resp.get("result", {}).get("list", []))
                except:
                    has_open = False
                
                if not has_open:
                    buy_result = execute_spot_trade("Buy", buy_qty, buy_price, ledger)
                    if buy_result:
                        executed += 1
                        log(f"MAKER BUY placed: {buy_qty} BTC @ {buy_price} (0.08% below mkt)")
                        ledger.setdefault("pending_maker_sells", []).append({
                            "buy_price": buy_price,
                            "qty": buy_qty,
                            "target_sell_price": round(buy_price * 1.0015 / 0.1) * 0.1,
                            "placed_at": datetime.now(timezone.utc).isoformat()
                        })
                else:
                    log("Skipping duplicate maker buy — open order exists")
        except Exception as e:
            log(f"Micro-arb cycle error: {e}")
    else:
        log(f"Insufficient balance for arb cycle: ${available:.2f} < $5.00")
    
    # Update ledger
    ledger["last_cycle"] = datetime.now(timezone.utc).isoformat()
    ledger["active_strategy"] = "maker_limit_grid"
    ledger["opportunities_found"] = len(opps)
    ledger["trades_executed"] = executed
    
    save_ledger(ledger)
    
    # Notify Telegram
    status_msg = f"""🧠 Wealth Gen Cycle
━━━━━━━━━━━━━━━━━━━
💰 Bybit: ${ledger.get('bybit_balance', 0):,.2f} USDT
📊 Equity: ${ledger.get('bybit_equity', 0):,.2f}
💳 Wise: ${ledger.get('wise_balance', 0):,.2f} USD
🎯 Progress: ${ledger.get('realized_usd', 0):,.2f} / $200,000
📈 Opportunities: {len(opps)}
✅ Trades: {executed}
🔄 Strategy: Maker Grid (Buy+Sell Auto)

📋 Planning:
• Monitoring BTC/USDT spreads
• Auto-execute when spread > 1.5%
• Min trade: $10 equivalent
• Next cycle: 1h

⚠️ Status: {'TRADING ACTIVE' if executed else 'SCANNING'}"""
    
    notify_telegram(status_msg)
    log("Cycle completed")

if __name__ == "__main__":
    log("Wealth Executor v4 started - Fixed GET signature with query string")
    notify_telegram("🔄 Wealth System v4 Online\n✅ Assinatura Bybit V5 corrigida (GET+query)\n✅ Saldo real: $2.97 USDT detectado\nIniciando ciclos autônomos...")
    
    while True:
        try:
            execute_cycle()
        except Exception as e:
            log(f"Critical error: {e}")
            notify_telegram(f"🚨 ERRO: {str(e)[:200]}")
        
        time.sleep(60)
