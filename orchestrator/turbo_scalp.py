#!/usr/bin/env python3
"""TURBO SCALPER - Market-Only, Zero-Latency, Aggressive Compound"""
import ccxt, os, json, time, sys
from dotenv import load_dotenv

load_dotenv('/root/.automaton/bybit-murre.env')
STATE_PATH = '/Agentic/orchestrator/state.json'

bybit = ccxt.bybit({
    'apiKey': os.getenv('BYBIT_REAL_API_KEY'),
    'secret': os.getenv('BYBIT_REAL_API_SECRET'),
    'options': {'defaultType': 'spot', 'recvWindow': 5000},
    'enableRateLimit': False  # MAX SPEED - no rate limit delay
})

def log(msg):
    ts = time.strftime('%H:%M:%S')
    print(f"[{ts}] {msg}", flush=True)

def update_state(usd, trades=None, status='turbo_active'):
    with open(STATE_PATH, 'r') as f:
        state = json.load(f)
    state['subagents']['bybit_spot']['current_usd'] = round(usd, 4)
    state['subagents']['bybit_spot']['status'] = status
    state['subagents']['bybit_spot']['last_updated'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    if trades:
        if 'trades' not in state['subagents']['bybit_spot']:
            state['subagents']['bybit_spot']['trades'] = []
        state['subagents']['bybit_spot']['trades'].extend(trades)
    with open(STATE_PATH, 'w') as f:
        json.dump(state, f, indent=2)

def get_balance():
    bal = bybit.fetch_balance()
    return float(bal.get('free', {}).get('USDT', 0))

def find_volatile_pair():
    """Find highest volatility pair with sufficient liquidity in <1s"""
    tickers = bybit.fetch_tickers()
    candidates = []
    for sym, t in tickers.items():
        if not sym.endswith('/USDT'):
            continue
        high = t.get('high') or 0
        low = t.get('low') or 0
        vol = t.get('quoteVolume') or 0
        last = t.get('last') or 0
        if low > 0 and vol > 500000 and last > 0.001:
            pct_range = (high - low) / low * 100
            # Weight: volatility * sqrt(volume) for liquid volatile pairs
            score = pct_range * (vol ** 0.3)
            candidates.append((sym, score, pct_range, last, vol))
    
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[:5]

def execute_scalp(symbol, usdt_amount):
    """MARKET BUY -> immediate MARKET SELL at +0.3% target. No limits."""
    try:
        # BUY at market
        qty_raw = usdt_amount / bybit.fetch_ticker(symbol)['last']
        qty = bybit.amount_to_precision(symbol, qty_raw)
        if float(qty) <= 0:
            return None
        
        t0 = time.time()
        buy = bybit.create_market_buy_order(symbol, float(qty))
        buy_ms = (time.time() - t0) * 1000
        entry = float(buy.get('average') or buy.get('price') or 0)
        filled = float(buy.get('filled') or qty)
        cost = float(buy.get('cost') or filled * entry)
        
        log(f"  BUY {symbol}: {filled} @ ${entry:.6f} | ${cost:.2f} | {buy_ms:.0f}ms")
        
        # Immediate SELL at market with +0.3% target (aggressive scalp)
        target_price = entry * 1.003
        # Wait max 2s for price movement, then sell at market regardless
        time.sleep(0.5)
        
        t1 = time.time()
        sell = bybit.create_market_sell_order(symbol, filled)
        sell_ms = (time.time() - t1) * 1000
        exit_price = float(sell.get('average') or sell.get('price') or 0)
        proceeds = float(sell.get('cost') or filled * exit_price)
        pnl = proceeds - cost
        pnl_pct = (pnl / cost * 100) if cost > 0 else 0
        
        log(f"  SELL {symbol}: {filled} @ ${exit_price:.6f} | ${proceeds:.2f} | {sell_ms:.0f}ms | PnL: ${pnl:+.4f} ({pnl_pct:+.3f}%)")
        
        return {
            'symbol': symbol,
            'side': 'scalp_market',
            'entry': entry,
            'exit': exit_price,
            'qty': filled,
            'cost': cost,
            'proceeds': proceeds,
            'pnl_usd': round(pnl, 4),
            'pnl_pct': round(pnl_pct, 3),
            'buy_ms': round(buy_ms),
            'sell_ms': round(sell_ms),
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        }
    except Exception as e:
        log(f"  ERR {symbol}: {str(e)[:100]}")
        return None

# === MAIN LOOP ===
log("🚀 TURBO SCALPER INICIADO - MARKET ONLY - ZERO LIMITS")
cycle = 0
while True:
    cycle += 1
    usdt = get_balance()
    log(f"\n=== CICLO {cycle} | USDT: ${usdt:.4f} ===")
    
    if usdt < 1.0:
        log("⚠️ Saldo < $1. Aguardando...")
        time.sleep(10)
        continue
    
    # Find best pair
    top = find_volatile_pair()
    if not top:
        log("Nenhum par volátil encontrado")
        time.sleep(5)
        continue
    
    best_sym, best_score, best_vol, best_price, best_qvol = top[0]
    log(f"🎯 Alvo: {best_sym} | Vol: {best_vol:.1f}% | Score: {best_score:.0f} | ${best_price}")
    
    # Use 95% of balance (aggressive compound)
    invest = usdt * 0.95
    trade = execute_scalp(best_sym, invest)
    
    if trade:
        new_bal = get_balance()
        update_state(new_bal, [trade])
        log(f"💰 Novo saldo: ${new_bal:.4f} | Delta: ${new_bal - usdt:+.4f}")
    else:
        log("Trade falhou, aguardando 5s")
        time.sleep(5)
    
    # Minimal delay between cycles
    time.sleep(2)
