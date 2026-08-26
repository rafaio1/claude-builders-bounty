#!/usr/bin/env python3
"""V16 - Bybit Futures Scalper: low-leverage long/short with tight controls.
Fees: maker=0.02%, taker=0.055%. With 3x leverage, 0.10% move = 0.30% PnL.
Strategy: buy limit at bid, sell limit at entry+0.15%. If no fill in 120s, cancel.
Max position: 10 USDT margin. Max loss: 1.5 USDT total.
Only BYBIT futures (Binance futures API not authorized).
"""
import ccxt, os, sys, json, time, math
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv('/root/.automaton/bybit-murre.env', override=True)

LOG_FILE = '/Agentic/orchestrator/v16_output.log'
STATE_FILE = '/Agentic/orchestrator/v16_state.json'
LEDGER_FILE = '/Agentic/ledger.jsonl'

SYMBOLS = ['DOGE/USDT:USDT', 'XRP/USDT:USDT']
MARGIN_SIZE = 10.0  # USDT margin per trade
LEVERAGE = 3
SPREAD_TARGET = 0.0015  # 0.15% above entry
BUY_TIMEOUT = 120
SELL_TIMEOUT = 180
MAX_RUNTIME = 7200
MAX_LOSS = 1.5
CYCLE_COOLDOWN = 12
MIN_SPREAD_TO_ENTER = 0.0008  # only enter if bid-ask >= 0.08%

state = {
    "version": "v16",
    "start_time": time.time(),
    "trades": 0,
    "wins": 0,
    "pnl": 0.0,
    "total_loss": 0.0,
    "running": True,
    "skipped": 0
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
        'options': {'defaultType': 'swap'}
    })

def truncate_qty(value, step):
    if step >= 1:
        return int(value / step) * step
    decimals = max(0, int(round(-math.log10(step))))
    factor = 10 ** decimals
    return math.floor(value * factor) / factor

def reconcile(ex):
    log("=== RECONCILIACAO V16 FUTURES ===")
    bal = ex.fetch_balance({'type': 'swap'})
    usdt = float(bal.get('USDT', {}).get('free', 0))
    log(f"  Bybit swap USDT free={usdt:.4f}")
    
    for sym in SYMBOLS:
        try:
            orders = ex.fetch_open_orders(sym)
            if orders:
                log(f"  WARNING: {sym} has {len(orders)} open!")
                for o in orders:
                    ex.cancel_order(o['id'], sym)
                    log(f"    Cancelled {o['id']}")
            else:
                log(f"  {sym}: 0 open orders")
        except Exception as e:
            log(f"  {sym} open orders error: {e}")
        
        # Check and close any open positions
        try:
            positions = ex.fetch_positions([sym])
            for pos in positions:
                amt = float(pos.get('contracts', 0) or 0)
                if abs(amt) > 0:
                    side = pos.get('side', '?')
                    log(f"  WARNING: {sym} open position side={side} contracts={amt}, closing...")
                    close_side = 'sell' if side == 'long' else 'buy'
                    ex.create_market_order(sym, close_side, abs(amt), params={'reduceOnly': True})
                    log(f"    Closed {sym} position")
        except Exception as e:
            log(f"  {sym} position check error: {e}")
    
    log("=== FIM RECONCILIACAO ===")
    return usdt

def set_leverage_safe(ex, symbol, leverage):
    try:
        ex.set_leverage(leverage, symbol)
        log(f"  {symbol} leverage set to {leverage}x")
    except Exception as e:
        log(f"  {symbol} set_leverage error (may already be set): {e}")

def execute_futures_scalp(ex, symbol, margin_usdt):
    try:
        ticker = ex.fetch_ticker(symbol)
        bid = float(ticker['bid'])
        ask = float(ticker['ask'])
        current_spread = (ask - bid) / bid
        
        if current_spread < MIN_SPREAD_TO_ENTER:
            state['skipped'] += 1
            log(f"  {symbol} spread={current_spread*100:.3f}% < {MIN_SPREAD_TO_ENTER*100:.2f}%, SKIP")
            return None
        
        log(f"  {symbol} SPREAD OK: {current_spread*100:.3f}%")
        
        market_info = ex.market(symbol)
        amt_step = market_info.get('precision', {}).get('amount', 1)
        if isinstance(amt_step, int):
            amt_step = 10 ** (-amt_step) if amt_step < 0 else amt_step
        price_prec = market_info.get('precision', {}).get('price', 0.0001)
        if isinstance(price_prec, int):
            price_step = 10 ** (-price_prec) if price_prec < 0 else price_prec
        else:
            price_step = price_prec
        min_amt = market_info.get('limits', {}).get('amount', {}).get('min', 1)
        
        # Calculate qty from margin * leverage / price
        notional = margin_usdt * LEVERAGE
        qty_raw = notional / bid
        qty = truncate_qty(qty_raw, amt_step)
        
        if qty < min_amt:
            log(f"  {symbol} qty {qty} below min {min_amt}, skip")
            return None
        
        buy_price = round(bid, len(str(price_step).rstrip('0').rstrip('.')) if price_step < 1 else 0)
        log(f"  {symbol} BUY LIMIT @ {buy_price} qty={qty} ({LEVERAGE}x, margin~{margin_usdt} USDT)")
        
        buy_order = ex.create_limit_buy_order(symbol, qty, buy_price)
        
        start_wait = time.time()
        entry_price = None
        filled_qty = 0
        while time.time() - start_wait < BUY_TIMEOUT:
            time.sleep(3)
            try:
                status = ex.fetch_order(buy_order['id'], symbol, params={'acknowledged': True})
                if status['status'] == 'closed':
                    entry_price = float(status.get('average') or buy_price)
                    filled_qty = float(status.get('filled') or qty)
                    log(f"  {symbol} BUY FILLED @ {entry_price} qty={filled_qty}")
                    break
                elif status['status'] == 'canceled':
                    log(f"  {symbol} buy cancelled")
                    return None
            except Exception as e:
                pass
        
        if entry_price is None:
            try:
                ex.cancel_order(buy_order['id'], symbol)
            except:
                pass
            log(f"  {symbol} BUY TIMEOUT, cancelled")
            return None
        
        # Place sell limit at entry + spread target
        sell_price = round(entry_price * (1 + SPREAD_TARGET),
                          len(str(price_step).rstrip('0').rstrip('.')) if price_step < 1 else 0)
        if sell_price <= entry_price:
            sell_price = round(entry_price + price_step,
                              len(str(price_step).rstrip('0').rstrip('.')) if price_step < 1 else 0)
        
        sell_qty = truncate_qty(filled_qty * 0.999, amt_step)
        if sell_qty < min_amt:
            sell_qty = filled_qty
        
        log(f"  {symbol} SELL LIMIT @ {sell_price} qty={sell_qty} (+{SPREAD_TARGET*100:.2f}%)")
        sell_order = ex.create_limit_sell_order(symbol, sell_qty, sell_price, params={'reduceOnly': True})
        
        start_wait = time.time()
        exit_price = None
        exit_reason = "LIMIT_FILL"
        while time.time() - start_wait < SELL_TIMEOUT:
            time.sleep(5)
            try:
                status = ex.fetch_order(sell_order['id'], symbol, params={'acknowledged': True})
                if status['status'] == 'closed':
                    exit_price = float(status.get('average') or sell_price)
                    log(f"  {symbol} SELL FILLED @ {exit_price}")
                    break
                elif status['status'] == 'canceled':
                    log(f"  {symbol} sell cancelled")
                    break
            except:
                pass
        
        if exit_price is None:
            try:
                ex.cancel_order(sell_order['id'], symbol)
            except:
                pass
            time.sleep(1)
            # Market close remaining position
            try:
                positions = ex.fetch_positions([symbol])
                for pos in positions:
                    amt = float(pos.get('contracts', 0) or 0)
                    if abs(amt) > 0:
                        ms = ex.create_market_order(symbol, 'sell', abs(amt), params={'reduceOnly': True})
                        exit_price = float(ms.get('average') or entry_price)
                        exit_reason = "TIMEOUT_MARKET"
                        log(f"  {symbol} TIMEOUT market close @ {exit_price}")
                        break
                if exit_price is None:
                    exit_price = entry_price
                    exit_reason = "TIMEOUT_NO_POS"
            except Exception as e:
                log(f"  {symbol} emergency close error: {e}")
                exit_price = entry_price
                exit_reason = "ERROR_CLOSE"
        
        # PnL calculation (leveraged)
        gross_pnl = (exit_price - entry_price) * filled_qty
        buy_fee = entry_price * filled_qty * 0.00055  # taker fee
        sell_fee = exit_price * sell_qty * 0.0002     # maker fee (limit)
        net_pnl = gross_pnl - buy_fee - sell_fee
        win = net_pnl > 0
        
        trade_entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "exchange": "bybit_futures",
            "symbol": symbol,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "qty": filled_qty,
            "leverage": LEVERAGE,
            "gross_pnl": round(gross_pnl, 6),
            "fees_usdt": round(buy_fee + sell_fee, 6),
            "net_pnl": round(net_pnl, 6),
            "win": win,
            "exit_reason": exit_reason,
            "spread_at_entry_pct": round(current_spread * 100, 4)
        }
        append_ledger(trade_entry)
        
        state['trades'] += 1
        if win:
            state['wins'] += 1
        state['pnl'] += net_pnl
        if net_pnl < 0:
            state['total_loss'] += abs(net_pnl)
        save_state()
        
        result_str = f"{'WIN' if win else 'LOSS'} pnl={net_pnl:+.4f} reason={exit_reason}"
        log(f"  {symbol} TRADE CLOSED: entry={entry_price} exit={exit_price} {result_str}")
        log(f"  Cumulative: trades={state['trades']} wins={state['wins']} pnl={state['pnl']:.4f}")
        
        return net_pnl
        
    except Exception as e:
        log(f"  {symbol} ERROR: {e}")
        import traceback
        log(f"  TRACEBACK: {traceback.format_exc()}")
        return None

def main():
    log("=== V16 BYBIT FUTURES SCALPER INICIANDO ===")
    log(f"Estrategia: futures {LEVERAGE}x, buy limit @ bid, sell @ entry+{SPREAD_TARGET*100:.2f}%")
    log(f"Fees: maker=0.02% taker=0.055%. Min spread={MIN_SPREAD_TO_ENTER*100:.2f}%")
    log(f"Margin={MARGIN_SIZE} USDT/trade. Max loss={MAX_LOSS} Runtime={MAX_RUNTIME}s")
    
    ex = get_exchange()
    ex.load_markets()
    
    usdt_free = reconcile(ex)
    log(f"Start: bybit_swap_usdt={usdt_free:.4f}")
    
    for sym in SYMBOLS:
        set_leverage_safe(ex, sym, LEVERAGE)
    
    start_time = time.time()
    cycle = 0
    
    while time.time() - start_time < MAX_RUNTIME and state['running']:
        if state['total_loss'] >= MAX_LOSS:
            log(f"MAX LOSS {MAX_LOSS} reached, stopping")
            break
        
        cycle += 1
        elapsed = int(time.time() - start_time)
        
        bal = ex.fetch_balance({'type': 'swap'})
        usdt_free = float(bal.get('USDT', {}).get('free', 0))
        
        if usdt_free < MARGIN_SIZE * 0.5:
            log(f"  Insufficient margin ({usdt_free:.2f}), waiting...")
            time.sleep(30)
            continue
        
        symbol = SYMBOLS[cycle % len(SYMBOLS)]
        log(f"--- Ciclo {cycle} ({elapsed}s) {symbol} ---")
        
        execute_futures_scalp(ex, symbol, MARGIN_SIZE)
        time.sleep(CYCLE_COOLDOWN)
        
        save_state()
    
    state['running'] = False
    save_state()
    log(f"=== V16 FINALIZADO: trades={state['trades']} wins={state['wins']} pnl={state['pnl']:.4f} total_loss={state['total_loss']:.4f} skipped={state['skipped']} ===")

if __name__ == '__main__':
    main()
