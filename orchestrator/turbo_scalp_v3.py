#!/usr/bin/env python3
"""TURBO SCALPER V3 - Cached Tickers + Trailing Stop + Immediate Flush"""
import ccxt, os, json, time, sys
from dotenv import load_dotenv

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

load_dotenv('/root/.automaton/bybit-murre.env')
STATE_PATH = '/Agentic/orchestrator/state.json'

bybit = ccxt.bybit({
    'apiKey': os.getenv('BYBIT_REAL_API_KEY'),
    'secret': os.getenv('BYBIT_REAL_API_SECRET'),
    'options': {'defaultType': 'spot', 'recvWindow': 5000},
    'enableRateLimit': False
})

TRAILING_ACTIVATION_PCT = 0.25
TRAILING_DISTANCE_PCT = 0.15
BREAKEVEN_ACTIVATION_PCT = 0.15
MAX_HOLD_SECONDS = 45
TICKER_CACHE_TTL = 10  # Refresh tickers every 10s max

ticker_cache = {'data': None, 'ts': 0}

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def update_state(usd, trades=None, status='trailing_v3'):
    try:
        with open(STATE_PATH, 'r') as f:
            state = json.load(f)
        state['subagents']['bybit_spot']['current_usd'] = round(usd, 4)
        state['subagents']['bybit_spot']['status'] = status
        state['subagents']['bybit_spot']['last_updated'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        if trades:
            state['subagents']['bybit_spot'].setdefault('trades', []).extend(trades)
        with open(STATE_PATH, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        log(f"State ERR: {e}")

def get_balance():
    return float(bybit.fetch_balance().get('free', {}).get('USDT', 0))

def get_tickers_cached():
    now = time.time()
    if ticker_cache['data'] and (now - ticker_cache['ts']) < TICKER_CACHE_TTL:
        return ticker_cache['data']
    ticker_cache['data'] = bybit.fetch_tickers()
    ticker_cache['ts'] = now
    return ticker_cache['data']

def find_best_pair():
    tickers = get_tickers_cached()
    best = None
    best_score = 0
    for sym, t in tickers.items():
        if not sym.endswith('/USDT'):
            continue
        high = t.get('high') or 0
        low = t.get('low') or 0
        vol = t.get('quoteVolume') or 0
        last = t.get('last') or 0
        if low > 0 and vol > 2000000 and last > 0.001:
            rng = (high - low) / low * 100
            score = rng * (vol ** 0.25)
            if score > best_score:
                best_score = score
                best = (sym, rng, last, vol)
    return best

def trailing_scalp(symbol, usdt_amount):
    try:
        ticker = bybit.fetch_ticker(symbol)
        entry_price = ticker['last']
        qty_raw = (usdt_amount * 0.98) / entry_price
        qty = bybit.amount_to_precision(symbol, qty_raw)
        if float(qty) <= 0:
            return None

        t0 = time.time()
        buy = bybit.create_market_buy_order(symbol, float(qty))
        buy_ms = (time.time() - t0) * 1000
        actual_entry = float(buy.get('average') or buy.get('price') or entry_price)
        filled = float(buy.get('filled') or qty)
        cost = float(buy.get('cost') or filled * actual_entry)
        log(f"  BUY {symbol}: {filled} @ ${actual_entry:.6f} | ${cost:.2f} | {buy_ms:.0f}ms")

        hwm = actual_entry
        trail_on = False
        be_on = False
        start = time.time()
        exit_price = None
        reason = ""

        while (time.time() - start) < MAX_HOLD_SECONDS:
            time.sleep(0.25)
            try:
                cp = bybit.fetch_ticker(symbol)['last']
            except:
                continue

            if cp > hwm:
                hwm = cp
                pnl_pct = ((hwm - actual_entry) / actual_entry) * 100
                if pnl_pct >= BREAKEVEN_ACTIVATION_PCT and not be_on:
                    be_on = True
                    log(f"  🛡️ Breakeven ON (+{pnl_pct:.2f}%)")
                if pnl_pct >= TRAILING_ACTIVATION_PCT and not trail_on:
                    trail_on = True
                    log(f"  🎯 Trail ON (+{pnl_pct:.2f}%) HWM=${hwm:.6f}")

            cur_pnl = ((cp - actual_entry) / actual_entry) * 100
            if trail_on:
                stop = hwm * (1 - TRAILING_DISTANCE_PCT / 100)
                if cp <= stop:
                    exit_price = cp
                    reason = f"Trail hit HWM=${hwm:.6f}"
                    break
            elif be_on and cp <= actual_entry:
                exit_price = cp
                reason = "Breakeven hit"
                break
            if cur_pnl >= 0.5 and not trail_on:
                exit_price = cp
                reason = "TP +0.5%"
                break

        if exit_price is None:
            exit_price = bybit.fetch_ticker(symbol)['last']
            reason = f"MaxHold {MAX_HOLD_SECONDS}s"

        t1 = time.time()
        sell = bybit.create_market_sell_order(symbol, filled)
        sell_ms = (time.time() - t1) * 1000
        actual_exit = float(sell.get('average') or sell.get('price') or exit_price)
        proceeds = float(sell.get('cost') or filled * actual_exit)
        pnl = proceeds - cost
        pnl_pct = (pnl / cost * 100) if cost > 0 else 0

        log(f"  SELL {symbol}: {filled} @ ${actual_exit:.6f} | ${proceeds:.2f} | {sell_ms:.0f}ms")
        log(f"  PnL: ${pnl:+.4f} ({pnl_pct:+.3f}%) | {reason}")

        return {
            'symbol': symbol, 'side': 'trailing_v3',
            'entry': actual_entry, 'exit': actual_exit,
            'qty': filled, 'cost': cost, 'proceeds': proceeds,
            'pnl_usd': round(pnl, 4), 'pnl_pct': round(pnl_pct, 3),
            'exit_reason': reason, 'trailing_used': trail_on,
            'hold_seconds': round(time.time() - start, 1),
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        }
    except Exception as e:
        log(f"  ERR: {str(e)[:150]}")
        return None

log("🚀 TURBO V3 STARTED")
cycle = 0
while True:
    cycle += 1
    usdt = get_balance()
    log(f"\n=== CYCLE {cycle} | USDT: ${usdt:.4f} ===")
    if usdt < 1.0:
        log("Low balance, wait 10s")
        time.sleep(10)
        continue
    pair = find_best_pair()
    if not pair:
        log("No pair found")
        time.sleep(5)
        continue
    sym, vol, price, qvol = pair
    log(f"Target: {sym} | Vol: {vol:.1f}% | ${price}")
    trade = trailing_scalp(sym, usdt)
    if trade:
        new_bal = get_balance()
        update_state(new_bal, [trade])
        log(f"New bal: ${new_bal:.4f} | Delta: ${new_bal-usdt:+.4f}")
    time.sleep(2)
