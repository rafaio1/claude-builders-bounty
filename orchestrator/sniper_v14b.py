#!/usr/bin/env python3
"""V14b - Micro Scalp Taker FIXED: buy market, sell limit at ask+0.15%.
Fixes: bybit fetchOrder acknowledged=True, tighter spread, faster timeout.
"""
import ccxt, os, sys, json, time, math
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv('/Agentic/.env')
load_dotenv('/root/.automaton/bybit-murre.env', override=True)

LOG_FILE = '/Agentic/orchestrator/v14b_output.log'
STATE_FILE = '/Agentic/orchestrator/v14b_state.json'
LEDGER_FILE = '/Agentic/ledger.jsonl'

SYMBOLS = ['XRP/USDT', 'DOGE/USDT']
BYBIT_SIZE = 10.0
BINANCE_SIZE = 7.0
SPREAD_PCT = 0.0015  # 0.15% above ask
SELL_TIMEOUT = 60
MAX_RUNTIME = 7200
MAX_LOSS = 2.5
CYCLE_COOLDOWN = 10

state = {
    "version": "v14b",
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

def truncate_qty(value, step):
    if step >= 1:
        return int(value / step) * step
    decimals = max(0, int(round(-math.log10(step))))
    factor = 10 ** decimals
    return math.floor(value * factor) / factor

def reconcile(exchanges):
    log("=== RECONCILIACAO V14b ===")
    for name, ex in exchanges.items():
        bal = ex.fetch_balance()
        usdt = float(bal['USDT']['free'])
        log(f"  {name}: USDT free={usdt:.4f}")
        for sym in SYMBOLS:
            try:
                orders = ex.fetch_open_orders(sym)
                if orders:
                    log(f"  WARNING: {name} {sym} has {len(orders)} open!")
                    for o in orders:
                        ex.cancel_order(o['id'], sym)
                        log(f"    Cancelled {o['id']}")
            except Exception as e:
                log(f"  {name} {sym} open orders error: {e}")
    log("=== FIM RECONCILIACAO ===")

def fetch_order_safe(ex, order_id, symbol, ex_name):
    try:
        if ex_name == 'bybit':
            return ex.fetch_order(order_id, symbol, params={'acknowledged': True})
        else:
            return ex.fetch_order(order_id, symbol)
    except Exception as e:
        log(f"  {ex_name} {symbol} fetchOrder error: {e}")
        return None

def execute_scalp(ex_name, ex, symbol, size_usdt):
    try:
        ticker = ex.fetch_ticker(symbol)
        ask = float(ticker['ask'])
        bid = float(ticker['bid'])
        spread_now = (ask - bid) / bid * 100
        
        market_info = ex.market(symbol)
        amt_step = market_info.get('precision', {}).get('amount', 0.1)
        if isinstance(amt_step, int):
            amt_step = 10 ** (-amt_step) if amt_step < 0 else amt_step
        price_prec = market_info.get('precision', {}).get('price', 0.0001)
        if isinstance(price_prec, int):
            price_step = 10 ** (-price_prec) if price_prec < 0 else price_prec
        else:
            price_step = price_prec
        min_amt = market_info.get('limits', {}).get('amount', {}).get('min', 0)
        
        qty_raw = size_usdt / ask
        qty = truncate_qty(qty_raw, amt_step)
        
        if qty <= min_amt:
            log(f"  {ex_name} {symbol} qty {qty} below min {min_amt}, skip")
            return None
        
        log(f"  {ex_name} {symbol} BUY MARKET qty={qty} @ ~{ask} (spread={spread_now:.3f}%)")
        buy_order = ex.create_market_buy_order(symbol, qty)
        entry_price = float(buy_order.get('average') or ask)
        filled_qty = float(buy_order.get('filled') or qty)
        log(f"  {ex_name} {symbol} BUY FILLED @ {entry_price} qty={filled_qty}")
        
        coin = symbol.split('/')[0]
        time.sleep(1)
        bal = ex.fetch_balance()
        coin_free = float(bal[coin]['free'])
        
        sell_qty = truncate_qty(coin_free * 0.998, amt_step)
        sell_price = round(ask * (1 + SPREAD_PCT), 
                          len(str(price_step).rstrip('0').rstrip('.')) if price_step < 1 else 0)
        if sell_price <= ask:
            sell_price = round(ask + price_step, 
                              len(str(price_step).rstrip('0').rstrip('.')) if price_step < 1 else 0)
        
        if sell_qty <= min_amt:
            log(f"  {ex_name} {symbol} sell qty too small, market exit")
            ms = ex.create_market_sell_order(symbol, truncate_qty(coin_free, amt_step))
            exit_price = float(ms.get('average') or entry_price)
            exit_reason = "DUST_EXIT"
        else:
            log(f"  {ex_name} {symbol} SELL LIMIT @ {sell_price} qty={sell_qty}")
            sell_order = ex.create_limit_sell_order(symbol, sell_qty, sell_price)
            
            start_wait = time.time()
            exit_price = None
            exit_reason = "LIMIT_FILL"
            while time.time() - start_wait < SELL_TIMEOUT:
                time.sleep(3)
                order_status = fetch_order_safe(ex, sell_order['id'], symbol, ex_name)
                if order_status is None:
                    continue
                if order_status['status'] == 'closed':
                    exit_price = float(order_status.get('average') or sell_price)
                    log(f"  {ex_name} {symbol} SELL FILLED @ {exit_price}")
                    break
                elif order_status['status'] == 'canceled':
                    log(f"  {ex_name} {symbol} sell cancelled")
                    break
            
            if exit_price is None:
                try:
                    ex.cancel_order(sell_order['id'], symbol)
                except:
                    pass
                time.sleep(1)
                bal2 = ex.fetch_balance()
                remaining = float(bal2[coin]['free'])
                if remaining > min_amt:
                    ms = ex.create_market_sell_order(symbol, truncate_qty(remaining, amt_step))
                    exit_price = float(ms.get('average') or entry_price)
                    exit_reason = "TIMEOUT_MARKET"
                    log(f"  {ex_name} {symbol} TIMEOUT market sell @ {exit_price}")
                else:
                    exit_price = sell_price
                    exit_reason = "TIMEOUT_DUST"
                    log(f"  {ex_name} {symbol} TIMEOUT dust remaining")
        
        gross_pnl = (exit_price - entry_price) * filled_qty
        buy_fee = entry_price * filled_qty * 0.001
        sell_fee = exit_price * (sell_qty if sell_qty > min_amt else filled_qty) * 0.001
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
            "exit_reason": exit_reason,
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
        
        result_str = f"{'WIN' if win else 'LOSS'} pnl={net_pnl:+.4f} reason={exit_reason}"
        log(f"  {ex_name} {symbol} TRADE CLOSED: entry={entry_price} exit={exit_price} {result_str}")
        log(f"  {ex_name.capitalize()} cumulative: trades={state['trades'][ex_name]} wins={state['wins'][ex_name]} pnl={state['pnl'][ex_name]:.4f}")
        
        return net_pnl
        
    except Exception as e:
        log(f"  {ex_name} {symbol} ERROR: {e}")
        import traceback
        log(f"  TRACEBACK: {traceback.format_exc()}")
        return None

def main():
    log("=== V14b MICRO SCALP TAKER (FIXED) INICIANDO ===")
    log(f"Estrategia: buy MARKET -> sell LIMIT @ ask+{SPREAD_PCT*100}% -> timeout {SELL_TIMEOUT}s")
    log(f"Bybit fetchOrder fix aplicado. Max loss={MAX_LOSS} Runtime={MAX_RUNTIME}s")
    
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
        
        for ex_name in ['bybit', 'binance']:
            if not state['running'] or state['total_loss'] >= MAX_LOSS:
                break
            
            ex = exchanges[ex_name]
            bal = ex.fetch_balance()
            usdt_free = float(bal['USDT']['free'])
            
            if usdt_free < sizes[ex_name] * 0.5:
                log(f"  {ex_name} insufficient USDT ({usdt_free:.2f}), skip")
                continue
            
            symbol = SYMBOLS[cycle % len(SYMBOLS)]
            log(f"--- {ex_name} ciclo {cycle} ({elapsed}s) {symbol} ---")
            
            execute_scalp(ex_name, ex, symbol, sizes[ex_name])
            time.sleep(CYCLE_COOLDOWN)
    
    state['running'] = False
    save_state()
    log(f"=== V14b FINALIZADO: trades={state['trades']} wins={state['wins']} pnl={state['pnl']} total_loss={state['total_loss']:.4f} ===")

if __name__ == '__main__':
    main()
