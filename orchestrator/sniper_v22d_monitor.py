#!/usr/bin/env python3
"""V22d Monitor v4 - Adaptive sell: +0.5% target, market exit if price < entry.
Fixes: previous +1% target too aggressive, caused losses when price reversed.
New logic: if current_price < entry_price at fill time -> immediate market sell.
If current_price >= entry_price -> limit sell at entry * 1.005 (+0.5%).
"""
import ccxt, os, sys, json, time, math
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv('/root/.automaton/bybit-murre.env', override=True)
LOG_FILE = '/Agentic/orchestrator/v22d_monitor.log'
LEDGER_FILE = '/Agentic/ledger.jsonl'
STATE_FILE = '/Agentic/orchestrator/v22d_state.json'
ACTIVE_FILE = '/Agentic/orchestrator/v22d_active.json'
GRID_SPACING_SELL = 0.005  # 0.5% above entry (reduced from 1.0%)
FEE_MAKER = 0.0002
MAX_RUNTIME = 7200
CHECK_INTERVAL = 5
state = {
    "version": "v22d_v4",
    "start_time": time.time(),
    "trades": 0,
    "wins": 0,
    "pnl": 0.0,
    "total_fees": 0.0,
    "buy_fills": 0,
    "sell_placed": 0,
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
def get_exchange():
    return ccxt.bybit({
        'apiKey': os.getenv('BYBIT_REAL_API_KEY'),
        'secret': os.getenv('BYBIT_REAL_API_SECRET'),
        'options': {'defaultType': 'spot'}
    })
def truncate_qty(value, step):
    if step >= 1:
        return int(value / step) * step
    decimals = max(0, int(round(-math.log10(step))))
    factor = 10 ** decimals
    return math.floor(value * factor) / factor
def main():
    log("=== V22d MONITOR v4 STARTING ===")
    log(f"Adaptive sell: +{GRID_SPACING_SELL*100}% if price>=entry, else market exit")
    ex = get_exchange()
    ex.load_markets()
    try:
        with open(ACTIVE_FILE, 'r') as f:
            active = json.load(f)
        log(f"Loaded active orders state")
    except Exception as e:
        log(f"ERROR loading active orders: {e}")
        return
    processed_buys = set()
    pending_sells = {}
    start_time = time.time()
    while time.time() - start_time < MAX_RUNTIME and state['running']:
        try:
            symbols = list(active.get('active_orders', {}).keys())
            for sym in symbols:
                try:
                    open_orders = ex.fetch_open_orders(sym)
                    open_buy_ids = {o['id'] for o in open_orders if o['side'] == 'buy'}
                    buys = active['active_orders'][sym].get('buys', {})
                    for price_str, info in buys.items():
                        order_id = info['id']
                        buy_key = f"{sym}_{order_id}"
                        if buy_key in processed_buys:
                            continue
                        if order_id not in open_buy_ids:
                            try:
                                order_info = ex.fetch_order(order_id, sym, params={'acknowledged': True})
                                fill_price = float(order_info.get('average') or order_info.get('price') or price_str)
                                fill_qty = float(order_info.get('filled') or info['qty'])
                                if fill_qty > 0 and order_info.get('status') == 'closed':
                                    state['buy_fills'] += 1
                                    log(f"  BUY FILLED: {sym} @ {fill_price} qty={fill_qty}")
                                    coin = sym.split('/')[0]
                                    bal = ex.fetch_balance()
                                    coin_free = float(bal.get(coin, {}).get('free', 0))
                                    log(f"  {coin} actual balance: {coin_free}")
                                    m = ex.market(sym)
                                    amt_step = m.get('precision', {}).get('amount', 1)
                                    if isinstance(amt_step, int):
                                        amt_step = 10 ** (-amt_step) if amt_step < 0 else amt_step
                                    price_prec = m.get('precision', {}).get('price', 0.0001)
                                    if isinstance(price_prec, int):
                                        price_step = 10 ** (-price_prec) if price_prec < 0 else price_prec
                                    else:
                                        price_step = price_prec
                                    min_amt = m.get('limits', {}).get('amount', {}).get('min', 1)
                                    min_cost = m.get('limits', {}).get('cost', {}).get('min', 5.0)
                                    sell_qty = truncate_qty(coin_free * 0.998, amt_step)
                                    # ADAPTIVE SELL LOGIC
                                    ticker = ex.fetch_ticker(sym)
                                    current_price = float(ticker['last'])
                                    if current_price < fill_price:
                                        # Price dropped below entry -> market sell immediately
                                        log(f"  PRICE BELOW ENTRY ({current_price:.6f} < {fill_price:.6f}), market exit")
                                        if sell_qty >= min_amt and sell_qty * current_price >= min_cost:
                                            try:
                                                ms = ex.create_market_sell_order(sym, sell_qty)
                                                exit_price = float(ms.get('average') or current_price)
                                                gross = (exit_price - fill_price) * sell_qty
                                                fees = (fill_price * fill_qty + exit_price * sell_qty) * FEE_MAKER
                                                net = gross - fees
                                                trade_entry = {
                                                    "ts": datetime.now(timezone.utc).isoformat(),
                                                    "exchange": "bybit",
                                                    "symbol": sym,
                                                    "strategy": "grid_v22e",
                                                    "entry_price": round(fill_price, 8),
                                                    "exit_price": round(exit_price, 8),
                                                    "qty": sell_qty,
                                                    "gross_pnl": round(gross, 6),
                                                    "fees_usdt": round(fees, 6),
                                                    "net_pnl": round(net, 6),
                                                    "win": net > 0,
                                                    "exit_reason": "MARKET_EXIT_BELOW_ENTRY"
                                                }
                                                append_ledger(trade_entry)
                                                state['trades'] += 1
                                                if net > 0: state['wins'] += 1
                                                state['pnl'] += net
                                                state['total_fees'] += fees
                                                emoji = "✅" if net > 0 else "❌"
                                                log(f"  {emoji} MARKET EXIT: {sym} buy@{fill_price:.6f} sell@{exit_price:.6f} net={net:+.6f}")
                                            except Exception as e:
                                                log(f"  MARKET EXIT ERROR: {str(e)[:120]}")
                                        processed_buys.add(buy_key)
                                    else:
                                        # Price >= entry -> limit sell at +0.5%
                                        sell_price = round(fill_price * (1 + GRID_SPACING_SELL),
                                            len(str(price_step).rstrip('0').rstrip('.')) if isinstance(price_step, float) and price_step < 1 else 0)
                                        notional = sell_qty * sell_price
                                        if sell_qty >= min_amt and notional >= min_cost:
                                            try:
                                                sell_order = ex.create_limit_sell_order(sym, sell_qty, sell_price)
                                                state['sell_placed'] += 1
                                                if sym not in pending_sells:
                                                    pending_sells[sym] = []
                                                pending_sells[sym].append({
                                                    'id': sell_order['id'],
                                                    'buy_price': fill_price,
                                                    'sell_price': sell_price,
                                                    'qty': sell_qty
                                                })
                                                log(f"  SELL PLACED: {sym} @ {sell_price} qty={sell_qty} notional={notional:.2f} (+{GRID_SPACING_SELL*100}%)")
                                            except Exception as e:
                                                log(f"  SELL ERROR: {str(e)[:120]}")
                                        else:
                                            log(f"  SELL SKIP: qty={sell_qty} notional={notional:.2f}")
                                        processed_buys.add(buy_key)
                            except Exception as e:
                                log(f"  Fill check error {sym} {order_id}: {str(e)[:100]}")
                    # Check pending sells
                    if sym in pending_sells:
                        open_sell_ids = {o['id'] for o in open_orders if o['side'] == 'sell'}
                        remaining_sells = []
                        for sell_info in pending_sells[sym]:
                            if sell_info['id'] not in open_sell_ids:
                                try:
                                    sell_order_info = ex.fetch_order(sell_info['id'], sym, params={'acknowledged': True})
                                    exit_price = float(sell_order_info.get('average') or sell_info['sell_price'])
                                    qty = float(sell_order_info.get('filled') or sell_info['qty'])
                                    entry_price = sell_info['buy_price']
                                    gross = (exit_price - entry_price) * qty
                                    fees = (entry_price * qty + exit_price * qty) * FEE_MAKER
                                    net = gross - fees
                                    trade_entry = {
                                        "ts": datetime.now(timezone.utc).isoformat(),
                                        "exchange": "bybit",
                                        "symbol": sym,
                                        "strategy": "grid_v22e",
                                        "entry_price": round(entry_price, 8),
                                        "exit_price": round(exit_price, 8),
                                        "qty": qty,
                                        "gross_pnl": round(gross, 6),
                                        "fees_usdt": round(fees, 6),
                                        "net_pnl": round(net, 6),
                                        "win": net > 0,
                                        "exit_reason": "GRID_COMPLETE"
                                    }
                                    append_ledger(trade_entry)
                                    state['trades'] += 1
                                    if net > 0: state['wins'] += 1
                                    state['pnl'] += net
                                    state['total_fees'] += fees
                                    emoji = "✅" if net > 0 else "❌"
                                    log(f"  {emoji} GRID COMPLETE: {sym} buy@{entry_price:.6f} sell@{exit_price:.6f} net={net:+.6f}")
                                except Exception as e:
                                    log(f"  Sell fill check error: {str(e)[:100]}")
                            else:
                                remaining_sells.append(sell_info)
                        pending_sells[sym] = remaining_sells
                except Exception as e:
                    log(f"  {sym} cycle error: {str(e)[:100]}")
            elapsed = int(time.time() - start_time)
            if elapsed % 60 < CHECK_INTERVAL:
                log(f"[{elapsed}s] fills={state['buy_fills']} sells={state['sell_placed']} "
                    f"trades={state['trades']} wins={state['wins']} pnl={state['pnl']:+.6f}")
            save_state()
            time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            break
        except Exception as e:
            log(f"Main loop error: {e}")
            time.sleep(10)
    state['running'] = False
    save_state()
    log(f"=== V22d MONITOR STOPPED: trades={state['trades']} wins={state['wins']} pnl={state['pnl']:+.6f} ===")
if __name__ == '__main__':
    main()
