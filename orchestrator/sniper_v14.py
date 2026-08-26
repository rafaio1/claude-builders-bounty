#!/usr/bin/env python3
"""V14 - Micro Scalp Taker: buy market, sell limit at ask+spread immediately.
Goal: capture tiny spreads repeatedly with deterministic controls.
Spread target: 0.25% (covers ~0.20% fees + 0.05% min profit).
No SL - if sell doesn't fill in 120s, market sell to exit.
"""
import ccxt, os, sys, json, time, math
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv('/Agentic/.env')
load_dotenv('/root/.automaton/bybit-murre.env', override=True)

LOG_FILE = '/Agentic/orchestrator/v14_output.log'
STATE_FILE = '/Agentic/orchestrator/v14_state.json'
LEDGER_FILE = '/Agentic/ledger.jsonl'

SYMBOLS = ['XRP/USDT', 'DOGE/USDT']
BYBIT_SIZE = 10.0
BINANCE_SIZE = 7.0
SPREAD_PCT = 0.0025  # 0.25%
SELL_TIMEOUT = 120   # seconds before market exit
MAX_RUNTIME = 7200   # 2 hours
MAX_LOSS = 3.0       # stop if total loss exceeds this
CYCLE_COOLDOWN = 15  # seconds between cycles

state = {
    "version": "v14",
    "start_time": time.time(),
    "trades": {"bybit": 0, "binance": 0},
    "wins": {"bybit": 0, "binance": 0},
    "pnl": {"bybit": 0.0, "binance": 0.0},
    "total_loss": 0.0,
    "running": True
}

def log(msg):
    ts = datetime.now(timezone.utc).strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, 'a') as f:
        f.write(line + '\n')

def save_state():
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def append_ledger(entry):
    with open(LEDGER_FILE, 'a') as f:
        f.write(json.dumps(entry) + '\n')

def get_exchange(name):
    if name == 'bybit':
        return ccxt.bybit({
            'apiKey': os.getenv('BYBIT_REAL_API_KEY'),
            'secret': os.getenv('BYBIT_REAL_API_SECRET'),
            'options': {'defaultType': 'spot'}
        })
    else:
        return ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_API_SECRET'),
            'options': {'warnOnFetchOpenOrdersWithoutSymbol': False}
        })

def truncate(value, precision):
    if precision >= 1:
        return math.floor(value * precision) / precision
    decimals = max(0, int(-math.log10(precision)))
    factor = 10 ** decimals
    return math.floor(value * factor) / factor

def reconcile(exchanges):
    log("=== RECONCILIACAO V14 ===")
    for name, ex in exchanges.items():
        bal = ex.fetch_balance()
        usdt = float(bal['USDT']['free'])
        log(f"  {name}: USDT free={usdt:.4f}")
        for sym in SYMBOLS:
            try:
                orders = ex.fetch_open_orders(sym)
                if orders:
                    log(f"  WARNING: {name} {sym} has {len(orders)} open orders!")
                    for o in orders:
                        ex.cancel_order(o['id'], sym)
                        log(f"    Cancelled {o['id']} {o['side']} {o['type']}")
            except Exception as e:
                log(f"  {name} {sym} open orders check error: {e}")
    log("=== FIM RECONCILIACAO ===")

def execute_scalp(ex_name, ex, symbol, size_usdt):
    """Buy market, immediately place sell limit at entry*(1+spread)."""
    try:
        ticker = ex.fetch_ticker(symbol)
        ask = float(ticker['ask'])
        
        # Buy at market (taker)
        qty_raw = size_usdt / ask
        market_info = ex.market(symbol)
        qty_precision = market_info.get('precision', {}).get('amount', 1)
        if isinstance(qty_precision, int):
            qty = truncate(qty_raw, 10**qty_precision) if qty_precision < 0 else truncate(qty_raw, qty_precision)
        else:
            qty = truncate(qty_raw, qty_precision)
        
        min_amount = market_info.get('limits', {}).get('amount', {}).get('min', 0)
        if qty <= min_amount:
            log(f"  {ex_name} {symbol} qty {qty} below min {min_amount}, skip")
            return None
        
        log(f"  {ex_name} {symbol} BUY MARKET qty={qty} @ ~{ask}")
        buy_order = ex.create_market_buy_order(symbol, qty)
        entry_price = float(buy_order.get('average') or ask)
        filled_qty = float(buy_order.get('filled') or qty)
        log(f"  {ex_name} {symbol} BUY FILLED @ {entry_price} qty={filled_qty}")
        
        # Get actual coin balance after buy
        coin = symbol.split('/')[0]
        time.sleep(1)
        bal = ex.fetch_balance()
        coin_free = float(bal[coin]['free'])
        
        # Sell limit at entry * (1 + spread), using actual balance minus buffer
        sell_qty = truncate(coin_free * 0.998, qty_precision if isinstance(qty_precision, (int,float)) else 0.1)
        sell_price = round(entry_price * (1 + SPREAD_PCT), 
                          len(str(market_info.get('precision',{}).get('price',0.0001)).rstrip('0').rstrip('.') or 4))
        
        if sell_qty <= min_amount:
            log(f"  {ex_name} {symbol} sell qty {sell_qty} too small, market sell")
            sell_order = ex.create_market_sell_order(symbol, truncate(coin_free, qty_precision if isinstance(qty_precision,(int,float)) else 0.1))
            exit_price = float(sell_order.get('average') or entry_price)
        else:
            log(f"  {ex_name} {symbol} SELL LIMIT @ {sell_price} qty={sell_qty}")
            sell_order = ex.create_limit_sell_order(symbol, sell_qty, sell_price)
            
            # Wait for fill with timeout
            start_wait = time.time()
            exit_price = None
            while time.time() - start_wait < SELL_TIMEOUT:
                time.sleep(5)
                try:
                    order_status = ex.fetch_order(sell_order['id'], symbol)
                    if order_status['status'] == 'closed':
                        exit_price = float(order_status.get('average') or sell_price)
                        log(f"  {ex_name} {symbol} SELL FILLED @ {exit_price}")
                        break
                    elif order_status['status'] == 'canceled':
                        log(f"  {ex_name} {symbol} sell cancelled unexpectedly")
                        break
                except Exception as e:
                    log(f"  {ex_name} {symbol} sell status check error: {e}")
            
            if exit_price is None:
                # Timeout - cancel and market sell
                try:
                    ex.cancel_order(sell_order['id'], symbol)
                except:
                    pass
                time.sleep(1)
                bal2 = ex.fetch_balance()
                remaining = float(bal2[coin]['free'])
                if remaining > min_amount:
                    ms = ex.create_market_sell_order(symbol, truncate(remaining, qty_precision if isinstance(qty_precision,(int,float)) else 0.1))
                    exit_price = float(ms.get('average') or entry_price)
                    log(f"  {ex_name} {symbol} TIMEOUT market sell @ {exit_price}")
                else:
                    exit_price = sell_price  # assume filled partially
                    log(f"  {ex_name} {symbol} TIMEOUT but dust remaining")
        
        # Calculate PnL
        gross_pnl = (exit_price - entry_price) * filled_qty
        buy_fee = entry_price * filled_qty * 0.001  # 0.1% taker
        sell_fee = exit_price * sell_qty * 0.001     # 0.1% taker/maker
        net_pnl = gross_pnl - buy_fee - sell_fee
        win = net_pnl > 0
        
        trade_entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "exchange": ex_name,
            "symbol": symbol,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "qty": filled_qty,
            "exit_qty": sell_qty,
            "gross_pnl": round(gross_pnl, 6),
            "fees_usdt": round(buy_fee + sell_fee, 6),
            "net_pnl": round(net_pnl, 6),
            "win": win,
            "exit_reason": "WIN" if win else ("TIMEOUT_SELL" if exit_price != sell_price else "LOSS_SELL"),
            "spread_pct": round((exit_price/entry_price - 1)*100, 4)
        }
        append_ledger(trade_entry)
        
        state['trades'][ex_name] += 1
        if win:
            state['wins'][ex_name] += 1
        state['pnl'][ex_name] += net_pnl
        if net_pnl < 0:
            state['total_loss'] += abs(net_pnl)
        save_state()
        
        result_str = f"{'WIN' if win else 'LOSS'} pnl={net_pnl:+.4f}"
        log(f"  {ex_name} {symbol} TRADE CLOSED: entry={entry_price} exit={exit_price} {result_str}")
        log(f"  {ex_name.capitalize()} state: trades={state['trades'][ex_name]} wins={state['wins'][ex_name]} pnl={state['pnl'][ex_name]:.4f}")
        
        return net_pnl
        
    except Exception as e:
        log(f"  {ex_name} {symbol} ERROR: {e}")
        return None

def main():
    log("=== V14 MICRO SCALP TAKER INICIANDO ===")
    log(f"Estrategia: buy MARKET -> sell LIMIT @ entry+{SPREAD_PCT*100}% -> timeout {SELL_TIMEOUT}s market exit")
    log(f"Sem SL. Max loss={MAX_LOSS} USDT. Runtime={MAX_RUNTIME}s")
    
    bybit = get_exchange('bybit')
    binance = get_exchange('binance')
    bybit.load_markets()
    binance.load_markets()
    
    exchanges = {'bybit': bybit, 'binance': binance}
    sizes = {'bybit': BYBIT_SIZE, 'binance': BINANCE_SIZE}
    
    reconcile(exchanges)
    
    start_bal_bybit = float(bybit.fetch_balance()['USDT']['free'])
    start_bal_binance = float(binance.fetch_balance()['USDT']['free'])
    log(f"Start: bybit_usdt={start_bal_bybit:.4f} binance_usdt={start_bal_binance:.4f}")
    
    start_time = time.time()
    cycle = 0
    
    while time.time() - start_time < MAX_RUNTIME and state['running']:
        if state['total_loss'] >= MAX_LOSS:
            log(f"MAX LOSS {MAX_LOSS} reached, stopping")
            break
        
        cycle += 1
        elapsed = int(time.time() - start_time)
        
        # Alternate exchanges each cycle
        for ex_name in ['bybit', 'binance']:
            if not state['running'] or state['total_loss'] >= MAX_LOSS:
                break
            
            ex = exchanges[ex_name]
            bal = ex.fetch_balance()
            usdt_free = float(bal['USDT']['free'])
            
            if usdt_free < sizes[ex_name] * 0.5:
                log(f"  {ex_name} insufficient USDT ({usdt_free:.2f}), skip")
                continue
            
            # Pick symbol with best liquidity
            symbol = SYMBOLS[cycle % len(SYMBOLS)]
            log(f"--- {ex_name} ciclo {cycle} ({elapsed}s) {symbol} ---")
            
            execute_scalp(ex_name, ex, symbol, sizes[ex_name])
            time.sleep(CYCLE_COOLDOWN)
    
    state['running'] = False
    save_state()
    log(f"=== V14 FINALIZADO: trades={state['trades']} wins={state['wins']} pnl={state['pnl']} total_loss={state['total_loss']:.4f} ===")

if __name__ == '__main__':
    main()
