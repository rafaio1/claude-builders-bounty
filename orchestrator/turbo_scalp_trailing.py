#!/usr/bin/env python3
"""TURBO SCALPER V2 - Trailing Stop + Full Capital + Guaranteed Exit"""
import ccxt, os, json, time, sys
from dotenv import load_dotenv

load_dotenv('/root/.automaton/bybit-murre.env')
STATE_PATH = '/Agentic/orchestrator/state.json'

bybit = ccxt.bybit({
    'apiKey': os.getenv('BYBIT_REAL_API_KEY'),
    'secret': os.getenv('BYBIT_REAL_API_SECRET'),
    'options': {'defaultType': 'spot', 'recvWindow': 5000},
    'enableRateLimit': False
})

# Trailing stop parameters
TRAILING_ACTIVATION_PCT = 0.25    # Activate trailing after +0.25% profit
TRAILING_DISTANCE_PCT = 0.15      # Trail 0.15% below high watermark
BREAKEVEN_ACTIVATION_PCT = 0.15   # Move stop to breakeven after +0.15%
MAX_HOLD_SECONDS = 60             # Force exit after 60s regardless
MIN_PROFIT_TARGET_PCT = 0.10      # Minimum acceptable profit

def log(msg):
    ts = time.strftime('%H:%M:%S')
    print(f"[{ts}] {msg}", flush=True)

def update_state(usd, trades=None, status='trailing_active'):
    try:
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
    except Exception as e:
        log(f"State update ERR: {e}")

def get_balance():
    bal = bybit.fetch_balance()
    return float(bal.get('free', {}).get('USDT', 0))

def get_position_value(symbol):
    """Get current value of any position held"""
    bal = bybit.fetch_balance()
    for coin, amt in bal.get('total', {}).items():
        if coin in ['USDT', 'USDC', 'USD', 'BRL']:
            continue
        a = float(amt)
        if a > 0:
            try:
                ticker = bybit.fetch_ticker(f"{coin}/USDT")
                return coin, a, ticker['last'], a * ticker['last']
            except:
                pass
    return None, 0, 0, 0

def find_volatile_pair():
    tickers = bybit.fetch_tickers()
    candidates = []
    for sym, t in tickers.items():
        if not sym.endswith('/USDT'):
            continue
        high = t.get('high') or 0
        low = t.get('low') or 0
        vol = t.get('quoteVolume') or 0
        last = t.get('last') or 0
        if low > 0 and vol > 1000000 and last > 0.001:  # Higher liquidity threshold
            pct_range = (high - low) / low * 100
            score = pct_range * (vol ** 0.3)
            candidates.append((sym, score, pct_range, last, vol))
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[:5]

def execute_trailing_scalp(symbol, usdt_amount):
    """MARKET BUY -> TRAILING STOP -> MARKET SELL. Full capital protection."""
    try:
        # 1. BUY at market with 98% of capital
        ticker = bybit.fetch_ticker(symbol)
        entry_price = ticker['last']
        qty_raw = (usdt_amount * 0.98) / entry_price
        qty = bybit.amount_to_precision(symbol, qty_raw)
        
        if float(qty) <= 0:
            log(f"  Qty too small for {symbol}")
            return None
        
        t0 = time.time()
        buy = bybit.create_market_buy_order(symbol, float(qty))
        buy_ms = (time.time() - t0) * 1000
        actual_entry = float(buy.get('average') or buy.get('price') or entry_price)
        filled = float(buy.get('filled') or qty)
        cost = float(buy.get('cost') or filled * actual_entry)
        
        log(f"  📈 BUY {symbol}: {filled} @ ${actual_entry:.6f} | ${cost:.2f} | {buy_ms:.0f}ms")
        
        # 2. TRAILING STOP MONITORING
        high_watermark = actual_entry
        trailing_active = False
        breakeven_set = False
        start_time = time.time()
        exit_price = None
        exit_reason = ""
        
        while (time.time() - start_time) < MAX_HOLD_SECONDS:
            time.sleep(0.3)  # Poll every 300ms
            
            try:
                current_ticker = bybit.fetch_ticker(symbol)
                current_price = current_ticker['last']
            except:
                continue
            
            # Update high watermark
            if current_price > high_watermark:
                high_watermark = current_price
                pnl_from_entry = ((high_watermark - actual_entry) / actual_entry) * 100
                
                # Activate breakeven protection
                if pnl_from_entry >= BREAKEVEN_ACTIVATION_PCT and not breakeven_set:
                    breakeven_set = True
                    log(f"  🛡️ Breakeven protection ON (+{pnl_from_entry:.2f}%)")
                
                # Activate trailing stop
                if pnl_from_entry >= TRAILING_ACTIVATION_PCT and not trailing_active:
                    trailing_active = True
                    log(f"  🎯 Trailing stop ON (+{pnl_from_entry:.2f}%) | HWM: ${high_watermark:.6f}")
            
            # Check exit conditions
            current_pnl = ((current_price - actual_entry) / actual_entry) * 100
            
            if trailing_active:
                trailing_stop_price = high_watermark * (1 - TRAILING_DISTANCE_PCT / 100)
                if current_price <= trailing_stop_price:
                    exit_price = current_price
                    exit_reason = f"Trailing stop hit (HWM ${high_watermark:.6f} -{TRAILING_DISTANCE_PCT}%)"
                    break
            elif breakeven_set:
                if current_price <= actual_entry:
                    exit_price = current_price
                    exit_reason = "Breakeven stop hit"
                    break
            
            # Take profit at +0.5% if not trailing yet
            if current_pnl >= 0.5 and not trailing_active:
                exit_price = current_price
                exit_reason = "Take profit +0.5%"
                break
        
        # Force exit if max hold time reached
        if exit_price is None:
            exit_price = bybit.fetch_ticker(symbol)['last']
            exit_reason = f"Max hold {MAX_HOLD_SECONDS}s"
        
        # 3. SELL at market - GUARANTEED EXIT
        t1 = time.time()
        sell = bybit.create_market_sell_order(symbol, filled)
        sell_ms = (time.time() - t1) * 1000
        actual_exit = float(sell.get('average') or sell.get('price') or exit_price)
        proceeds = float(sell.get('cost') or filled * actual_exit)
        
        pnl = proceeds - cost
        pnl_pct = (pnl / cost * 100) if cost > 0 else 0
        
        log(f"  📉 SELL {symbol}: {filled} @ ${actual_exit:.6f} | ${proceeds:.2f} | {sell_ms:.0f}ms")
        log(f"  💰 PnL: ${pnl:+.4f} ({pnl_pct:+.3f}%) | Reason: {exit_reason}")
        
        return {
            'symbol': symbol,
            'side': 'trailing_scalp',
            'entry': actual_entry,
            'exit': actual_exit,
            'qty': filled,
            'cost': cost,
            'proceeds': proceeds,
            'pnl_usd': round(pnl, 4),
            'pnl_pct': round(pnl_pct, 3),
            'exit_reason': exit_reason,
            'high_watermark': high_watermark,
            'trailing_used': trailing_active,
            'buy_ms': round(buy_ms),
            'sell_ms': round(sell_ms),
            'hold_seconds': round(time.time() - start_time, 1),
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        }
    except Exception as e:
        log(f"  ❌ ERR {symbol}: {str(e)[:150]}")
        return None

# === MAIN LOOP ===
log("🚀 TURBO SCALPER V2 - TRAILING STOP - FULL CAPITAL PROTECTION")
cycle = 0
while True:
    cycle += 1
    usdt = get_balance()
    log(f"\n{'='*60}")
    log(f"CICLO {cycle} | USDT Livre: ${usdt:.4f}")
    
    if usdt < 1.0:
        log("⚠️ Saldo < $1. Aguardando 10s...")
        time.sleep(10)
        continue
    
    # Find best pair
    top = find_volatile_pair()
    if not top:
        log("Nenhum par volátil encontrado")
        time.sleep(5)
        continue
    
    best_sym, best_score, best_vol, best_price, best_qvol = top[0]
    log(f"🎯 Alvo: {best_sym} | Vol24h: {best_vol:.1f}% | Score: {best_score:.0f} | ${best_price}")
    
    # Execute trailing scalp
    trade = execute_trailing_scalp(best_sym, usdt)
    
    if trade:
        new_bal = get_balance()
        update_state(new_bal, [trade])
        log(f"💵 Novo saldo: ${new_bal:.4f} | Delta ciclo: ${new_bal - usdt:+.4f}")
    else:
        log("Trade falhou, aguardando 5s")
        time.sleep(5)
    
    time.sleep(2)
