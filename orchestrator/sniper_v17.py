#!/usr/bin/env python3
"""V17 - Spread Hunter Futures: continuous scan, enter only when spread > 0.10%.
Focus on WIF/USDT:USDT (highest spread observed ~0.05-0.15%).
Market buy + immediate limit sell at entry+0.15%.
Fees: taker 0.055% + maker 0.02% = 0.075% round-trip.
Min profitable spread: >0.075%. Target entry: >0.10%.
"""
import ccxt, os, sys, json, time, math
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv('/root/.automaton/bybit-murre.env', override=True)

LOG_FILE = '/Agentic/orchestrator/v17_output.log'
STATE_FILE = '/Agentic/orchestrator/v17_state.json'
LEDGER_FILE = '/Agentic/ledger.jsonl'

PRIMARY_SYMBOL = 'WIF/USDT:USDT'
FALLBACK_SYMBOLS = ['DOGE/USDT:USDT', 'XRP/USDT:USDT']
MARGIN_SIZE = 10.0
LEVERAGE = 3
SPREAD_TARGET = 0.0015  # sell at entry + 0.15%
MIN_SPREAD_ENTRY = 0.0010  # only enter if spread >= 0.10%
SELL_TIMEOUT = 120
MAX_RUNTIME = 7200
MAX_LOSS = 1.5
SCAN_INTERVAL = 2  # seconds between scans
COOLDOWN_AFTER_TRADE = 15

state = {
    "version": "v17",
    "start_time": time.time(),
    "trades": 0,
    "wins": 0,
    "pnl": 0.0,
    "total_loss": 0.0,
    "running": True,
    "scans": 0,
    "max_spread_seen": 0.0
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
    log("=== RECONCILIACAO V17 ===")
    bal = ex.fetch_balance({'type': 'swap'})
    usdt = float(bal.get('USDT', {}).get('free', 0))
    log(f"  Swap USDT free={usdt:.4f}")
    
    all_syms = [PRIMARY_SYMBOL] + FALLBACK_SYMBOLS
    for sym in all_syms:
        try:
            orders = ex.fetch_open_orders(sym)
            if orders:
                log(f"  WARNING: {sym} has {len(orders)} open!")
                for o in orders:
                    ex.cancel_order(o['id'], sym)
                    log(f"    Cancelled {o['id']}")
            positions = ex.fetch_positions([sym])
            for pos in positions:
                amt = float(pos.get('contracts', 0) or 0)
                if abs(amt) > 0:
                    side = pos.get('side', '?')
                    log(f"  WARNING: {sym} position side={side} contracts={amt}, closing...")
                    close_side = 'sell' if side == 'long' else 'buy'
                    ex.create_market_order(sym, close_side, abs(amt), params={'reduceOnly': True})
                    log(f"    Closed {sym}")
        except Exception as e:
            log(f"  {sym} check error: {e}")
    log("=== FIM RECONCILIACAO ===")
    return usdt

def execute_hunt(ex, symbol, margin_usdt, current_spread):
    try:
        ticker = ex.fetch_ticker(symbol)
        ask = float(ticker['ask'])
        
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
        
        notional = margin_usdt * LEVERAGE
        qty_raw = notional / ask
        qty = truncate_qty(qty_raw, amt_step)
        
        if qty < min_amt:
            log(f"  {symbol} qty {qty} below min {min_amt}, skip")
            return None
        
        log(f"  {symbol} MARKET BUY qty={qty} @ ~{ask} (spread={current_spread*100:.3f}%)")
        buy_order = ex.create_market_buy_order(symbol, qty)
        entry_price = float(buy_order.get('average') or ask)
        filled_qty = float(buy_order.get('filled') or qty)
        log(f"  {symbol} BUY FILLED @ {entry_price} qty={filled_qty}")
        
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
            time.sleep(3)
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
        
        gross_pnl = (exit_price - entry_price) * filled_qty
        buy_fee = entry_price * filled_qty * 0.00055
        sell_fee = exit_price * sell_qty * 0.0002
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
    log("=== V17 SPREAD HUNTER FUTURES INICIANDO ===")
    log(f"Monitoramento continuo scan a cada {SCAN_INTERVAL}s")
    log(f"Entrada apenas se spread >= {MIN_SPREAD_ENTRY*100:.2f}%")
    log(f"Primary: {PRIMARY_SYMBOL}. Fees: 0.055%+0.02%=0.075%")
    log(f"Margin={MARGIN_SIZE} Leverage={LEVERAGE}x MaxLoss={MAX_LOSS}")
    
    ex = get_exchange()
    ex.load_markets()
    
    usdt_free = reconcile(ex)
    log(f"Start: swap_usdt={usdt_free:.4f}")
    
    start_time = time.time()
    last_trade_time = 0
    
    while time.time() - start_time < MAX_RUNTIME and state['running']:
        if state['total_loss'] >= MAX_LOSS:
            log(f"MAX LOSS {MAX_LOSS} reached, stopping")
            break
        
        elapsed = int(time.time() - start_time)
        state['scans'] += 1
        
        # Scan primary symbol
        try:
            ticker = ex.fetch_ticker(PRIMARY_SYMBOL)
            bid = float(ticker['bid'])
            ask = float(ticker['ask'])
            spread = (ask - bid) / bid
            
            if spread > state['max_spread_seen']:
                state['max_spread_seen'] = spread
            
            if state['scans'] % 30 == 0:
                log(f"  [{elapsed}s] scan#{state['scans']} {PRIMARY_SYMBOL} spread={spread*100:.3f}% max={state['max_spread_seen']*100:.3f}%")
            
            if spread >= MIN_SPREAD_ENTRY and (time.time() - last_trade_time) > COOLDOWN_AFTER_TRADE:
                bal = ex.fetch_balance({'type': 'swap'})
                usdt_free = float(bal.get('USDT', {}).get('free', 0))
                
                if usdt_free >= MARGIN_SIZE * 0.5:
                    log(f"  OPPORTUNITY! {PRIMARY_SYMBOL} spread={spread*100:.3f}% >= {MIN_SPREAD_ENTRY*100:.2f}%")
                    result = execute_hunt(ex, PRIMARY_SYMBOL, MARGIN_SIZE, spread)
                    if result is not None:
                        last_trade_time = time.time()
                else:
                    log(f"  Spread OK but insufficient margin ({usdt_free:.2f})")
        
        except Exception as e:
            if state['scans'] % 30 == 0:
                log(f"  Scan error: {e}")
        
        time.sleep(SCAN_INTERVAL)
        save_state()
    
    state['running'] = False
    save_state()
    log(f"=== V17 FINALIZADO: trades={state['trades']} wins={state['wins']} pnl={state['pnl']:.4f} loss={state['total_loss']:.4f} scans={state['scans']} maxSpread={state['max_spread_seen']*100:.3f}% ===")

if __name__ == '__main__':
    main()
