#!/usr/bin/env python3
"""V22 - Multi-Pair Grid Trading LIVE on Bybit Spot.
Parameters from backtest optimizer: 8 grids, 1.0% spacing, 120-bar lookback.
Maker fees: 0.02% each side. Runs on XRP, DOGE, BTC, ETH, SOL simultaneously.
Capital allocation: proportional to available USDT.
"""
import ccxt, os, sys, json, time, math
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv('/root/.automaton/bybit-murre.env', override=True)

LOG_FILE = '/Agentic/orchestrator/v22_output.log'
STATE_FILE = '/Agentic/orchestrator/v22_state.json'
LEDGER_FILE = '/Agentic/ledger.jsonl'

SYMBOLS = ['XRP/USDT', 'DOGE/USDT', 'BTC/USDT', 'ETH/USDT', 'SOL/USDT']
NUM_GRIDS = 8
GRID_SPACING = 0.01  # 1.0%
LOOKBACK_BARS = 120
MAX_RUNTIME = 7200  # 2 hours
SCAN_INTERVAL = 10  # seconds between grid rebalance checks
FEE_MAKER = 0.0002  # 0.02%

state = {
    "version": "v22",
    "start_time": time.time(),
    "trades": {},
    "wins": {},
    "pnl": {},
    "total_pnl": 0.0,
    "total_fees": 0.0,
    "running": True,
    "active_buys": {},   # symbol -> {price_str: qty}
    "active_sells": {},  # symbol -> {price_str: qty}
}

for sym in SYMBOLS:
    state['trades'][sym] = 0
    state['wins'][sym] = 0
    state['pnl'][sym] = 0.0
    state['active_buys'][sym] = {}
    state['active_sells'][sym] = {}

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

def reconcile(ex):
    log("=== RECONCILIACAO V22 GRID ===")
    bal = ex.fetch_balance()
    usdt = float(bal['USDT']['free'])
    log(f"  Bybit USDT free={usdt:.4f}")
    
    # Cancel ALL open orders across all symbols
    for sym in SYMBOLS:
        try:
            orders = ex.fetch_open_orders(sym)
            if orders:
                log(f"  WARNING: {sym} has {len(orders)} open orders, cancelling...")
                for o in orders:
                    ex.cancel_order(o['id'], sym)
                    log(f"    Cancelled {o['id']} {o['side']} @ {o.get('price','?')}")
            else:
                log(f"  {sym}: 0 open orders")
        except Exception as e:
            log(f"  {sym} cancel error: {e}")
        
        # Clear tracked orders since we cancelled everything
        state['active_buys'][sym] = {}
        state['active_sells'][sym] = {}
    
    # Sell any dust positions
    for sym in SYMBOLS:
        coin = sym.split('/')[0]
        try:
            coin_free = float(bal.get(coin, {}).get('free', 0))
            if coin_free > 0:
                m = ex.market(sym)
                amt_step = m.get('precision', {}).get('amount', 1)
                if isinstance(amt_step, int):
                    amt_step = 10 ** (-amt_step) if amt_step < 0 else amt_step
                qty = truncate_qty(coin_free, amt_step)
                min_amt = m.get('limits', {}).get('amount', {}).get('min', 0)
                min_notional = m.get('limits', {}).get('cost', {}).get('min', 0)
                if qty >= min_amt and qty * float(ex.fetch_ticker(sym)['last'] or 0) >= min_notional:
                    order = ex.create_market_sell_order(sym, qty)
                    log(f"  Sold {coin} dust: qty={qty} id={order['id']}")
                    time.sleep(1)
        except Exception as e:
            log(f"  {sym} dust sell error: {e}")
    
    log("=== FIM RECONCILIACAO ===")
    return usdt

def place_grid_orders(ex, symbol, current_price, usdt_available, klines_recent):
    """Place grid buy and sell limit orders around current price."""
    try:
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
        min_notional = market_info.get('limits', {}).get('cost', {}).get('min', 1)
        
        per_grid = usdt_available / (NUM_GRIDS * len(SYMBOLS))
        
        placed_buys = 0
        placed_sells = 0
        
        for g in range(1, NUM_GRIDS // 2 + 1):
            # Buy levels below current price
            buy_price = round(current_price * (1 - g * GRID_SPACING),
                            len(str(price_step).rstrip('0').rstrip('.')) if price_step < 1 else 0)
            buy_qty = truncate_qty(per_grid / buy_price, amt_step)
            
            if buy_qty >= min_amt and buy_qty * buy_price >= min_notional:
                price_key = str(buy_price)
                if price_key not in state['active_buys'][symbol]:
                    try:
                        order = ex.create_limit_buy_order(symbol, buy_qty, buy_price)
                        state['active_buys'][symbol][price_key] = buy_qty
                        placed_buys += 1
                    except Exception as e:
                        log(f"  {symbol} buy @ {buy_price} error: {e}")
            
            # Sell levels above current price
            sell_price = round(current_price * (1 + g * GRID_SPACING),
                             len(str(price_step).rstrip('0').rstrip('.')) if price_step < 1 else 0)
            sell_qty = truncate_qty(per_grid / sell_price, amt_step)
            
            if sell_qty >= min_amt and sell_qty * sell_price >= min_notional:
                price_key = str(sell_price)
                if price_key not in state['active_sells'][symbol]:
                    try:
                        order = ex.create_limit_sell_order(symbol, sell_qty, sell_price)
                        state['active_sells'][symbol][price_key] = sell_qty
                        placed_sells += 1
                    except Exception as e:
                        log(f"  {symbol} sell @ {sell_price} error: {e}")
        
        if placed_buys > 0 or placed_sells > 0:
            log(f"  {symbol} grid placed: {placed_buys} buys + {placed_sells} sells @ {current_price:.6f}")
        
    except Exception as e:
        log(f"  {symbol} grid placement error: {e}")

def check_fills(ex, symbol):
    """Check which grid orders filled and place counter-orders."""
    try:
        orders = ex.fetch_open_orders(symbol)
        open_ids = {o['id'] for o in orders}
        
        # Check buy fills
        filled_buys = []
        remaining_buys = {}
        for price_str, qty in state['active_buys'][symbol].items():
            price = float(price_str)
            # Check if this order is still open
            still_open = False
            for o in orders:
                if o['side'] == 'buy' and abs(float(o['price']) - price) / price < 0.0001:
                    still_open = True
                    break
            
            if not still_open:
                # Buy filled - place corresponding sell
                sell_price = round(price * (1 + GRID_SPACING), 8)
                m = ex.market(symbol)
                amt_step = m.get('precision', {}).get('amount', 1)
                if isinstance(amt_step, int):
                    amt_step = 10 ** (-amt_step) if amt_step < 0 else amt_step
                sell_qty = truncate_qty(qty * 0.998, amt_step)  # buffer for fees
                min_amt = m.get('limits', {}).get('amount', {}).get('min', 1)
                
                if sell_qty >= min_amt:
                    try:
                        ex.create_limit_sell_order(symbol, sell_qty, sell_price)
                        state['active_sells'][symbol][str(sell_price)] = sell_qty
                        filled_buys.append((price, qty))
                        log(f"  {symbol} BUY FILLED @ {price} -> sell placed @ {sell_price}")
                    except Exception as e:
                        log(f"  {symbol} counter-sell error: {e}")
            else:
                remaining_buys[price_str] = qty
        
        state['active_buys'][symbol] = remaining_buys
        
        # Check sell fills
        filled_sells = []
        remaining_sells = {}
        for price_str, qty in state['active_sells'][symbol].items():
            price = float(price_str)
            still_open = False
            for o in orders:
                if o['side'] == 'sell' and abs(float(o['price']) - price) / price < 0.0001:
                    still_open = True
                    break
            
            if not still_open:
                # Sell filled - completed round trip!
                buy_price = price / (1 + GRID_SPACING)
                gross = (price - buy_price) * qty
                fees = (buy_price * qty + price * qty) * FEE_MAKER
                net = gross - fees
                
                trade_entry = {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "exchange": "bybit",
                    "symbol": symbol,
                    "strategy": "grid_v22",
                    "entry_price": round(buy_price, 8),
                    "exit_price": round(price, 8),
                    "qty": qty,
                    "gross_pnl": round(gross, 6),
                    "fees_usdt": round(fees, 6),
                    "net_pnl": round(net, 6),
                    "win": net > 0,
                    "exit_reason": "GRID_COMPLETE"
                }
                append_ledger(trade_entry)
                
                state['trades'][symbol] += 1
                if net > 0:
                    state['wins'][symbol] += 1
                state['pnl'][symbol] += net
                state['total_pnl'] += net
                state['total_fees'] += fees
                
                filled_sells.append((price, qty, net))
                log(f"  {symbol} GRID COMPLETE: buy@{buy_price:.6f} sell@{price:.6f} net={net:+.6f}")
            else:
                remaining_sells[price_str] = qty
        
        state['active_sells'][symbol] = remaining_sells
        
        if filled_sells:
            total_net = sum(f[2] for f in filled_sells)
            log(f"  {symbol} session: trades={state['trades'][symbol]} wins={state['wins'][symbol]} pnl={state['pnl'][symbol]:+.4f}")
        
    except Exception as e:
        log(f"  {symbol} fill check error: {e}")

def main():
    log("=" * 60)
    log("V22 MULTI-PAIR GRID TRADING - BYBIT SPOT LIVE")
    log(f"Pairs: {', '.join(SYMBOLS)}")
    log(f"Grids: {NUM_GRIDS} | Spacing: {GRID_SPACING*100:.1f}% | Lookback: {LOOKBACK_BARS}")
    log(f"Fees: {FEE_MAKER*100:.2f}% maker | Runtime: {MAX_RUNTIME}s")
    log("=" * 60)
    
    ex = get_exchange()
    ex.load_markets()
    
    usdt_free = reconcile(ex)
    log(f"Start capital: {usdt_free:.4f} USDT")
    
    if usdt_free < 5.0:
        log("ERROR: Insufficient capital (<5 USDT). Stopping.")
        state['running'] = False
        save_state()
        return
    
    start_time = time.time()
    cycle = 0
    
    while time.time() - start_time < MAX_RUNTIME and state['running']:
        elapsed = int(time.time() - start_time)
        cycle += 1
        
        # Refresh balance
        try:
            bal = ex.fetch_balance()
            usdt_free = float(bal['USDT']['free'])
        except:
            usdt_free = 0
        
        for sym in SYMBOLS:
            try:
                ticker = ex.fetch_ticker(sym)
                current_price = float(ticker['last'] or ticker['close'] or 0)
                
                if current_price <= 0:
                    continue
                
                # Check fills first
                check_fills(ex, sym)
                
                # Rebalance grid periodically
                if cycle % 6 == 0:  # Every ~60s
                    place_grid_orders(ex, sym, current_price, usdt_free, None)
                
            except Exception as e:
                if cycle % 30 == 0:
                    log(f"  {sym} cycle error: {e}")
        
        # Progress update every 30 cycles (~5 min)
        if cycle % 30 == 0:
            total_trades = sum(state['trades'].values())
            total_wins = sum(state['wins'].values())
            log(f"[{elapsed}s] cycle={cycle} trades={total_trades} wins={total_wins} "
                f"pnl={state['total_pnl']:+.4f} fees={state['total_fees']:.4f} usdt={usdt_free:.2f}")
            save_state()
        
        time.sleep(SCAN_INTERVAL)
    
    # Final reconciliation
    log("\n=== FINAL RECONCILIATION ===")
    final_bal = ex.fetch_balance()
    final_usdt = float(final_bal['USDT']['free'])
    
    # Cancel remaining orders
    for sym in SYMBOLS:
        try:
            orders = ex.fetch_open_orders(sym)
            for o in orders:
                ex.cancel_order(o['id'], sym)
            if orders:
                log(f"  Cancelled {len(orders)} remaining orders on {sym}")
        except:
            pass
    
    state['running'] = False
    save_state()
    
    total_trades = sum(state['trades'].values())
    total_wins = sum(state['wins'].values())
    wr = (total_wins / total_trades * 100) if total_trades > 0 else 0
    
    log(f"\n{'='*60}")
    log(f"V22 FINAL RESULTS")
    log(f"{'='*60}")
    log(f"Runtime: {int(time.time()-start_time)}s | Cycles: {cycle}")
    log(f"Total trades: {total_trades} | Wins: {total_wins} | WR: {wr:.1f}%")
    log(f"Total PnL: {state['total_pnl']:+.6f} USDT")
    log(f"Total Fees: {state['total_fees']:.6f} USDT")
    log(f"Start USDT: {usdt_free:.4f} | End USDT: {final_usdt:.4f}")
    log(f"Per-symbol breakdown:")
    for sym in SYMBOLS:
        t = state['trades'][sym]
        w = state['wins'][sym]
        p = state['pnl'][sym]
        if t > 0:
            log(f"  {sym}: {t}t {w}w pnl={p:+.6f}")
    log(f"{'='*60}")

if __name__ == '__main__':
    main()
