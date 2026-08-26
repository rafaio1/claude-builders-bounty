#!/usr/bin/env python3
"""V19 - Binance Spot with BNB Fee Discount (25% off).
Effective fees: 0.075% each side = 0.15% round-trip.
Min profitable spread: >0.15%. Entry threshold: 0.18%.
Target sell spread: 0.25%. Primary: PNUT/USDT.
"""
import ccxt, os, sys, json, time, math
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv('/Agentic/.env')

LOG_FILE = '/Agentic/orchestrator/v19_output.log'
STATE_FILE = '/Agentic/orchestrator/v19_state.json'
LEDGER_FILE = '/Agentic/ledger.jsonl'

PRIMARY = 'PNUT/USDT'
FALLBACKS = ['ACT/USDT', 'BANANAS31/USDT', 'WIF/USDT']
TRADE_SIZE = 7.0
SPREAD_TARGET = 0.0025
MIN_SPREAD_ENTRY = 0.0018
SELL_TIMEOUT = 90
MAX_RUNTIME = 7200
MAX_LOSS = 1.5
SCAN_INTERVAL = 3
COOLDOWN = 10
FEE_RATE = 0.00075  # 0.075% with BNB discount

state = {
    "version": "v19",
    "start_time": time.time(),
    "trades": 0,
    "wins": 0,
    "pnl": 0.0,
    "total_loss": 0.0,
    "running": True,
    "scans": 0,
    "max_spread": 0.0
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

def reconcile(ex):
    log("=== RECONCILIACAO V19 ===")
    bal = ex.fetch_balance()
    usdt = float(bal['USDT']['free'])
    bnb = float(bal.get('BNB', {}).get('free', 0))
    log(f"  Binance USDT={usdt:.4f} BNB={bnb:.6f}")
    all_syms = [PRIMARY] + FALLBACKS
    for sym in all_syms:
        try:
            orders = ex.fetch_open_orders(sym)
            if orders:
                log(f"  WARNING: {sym} has {len(orders)} open!")
                for o in orders:
                    ex.cancel_order(o['id'], sym)
                    log(f"    Cancelled {o['id']}")
        except Exception as e:
            log(f"  {sym} check error: {e}")
    log("=== FIM RECONCILIACAO ===")
    return usdt

def execute_trade(ex, symbol, size_usdt, current_spread):
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

        qty_raw = size_usdt / ask
        qty = truncate_qty(qty_raw, amt_step)
        if qty < min_amt:
            log(f"  {symbol} qty {qty} below min {min_amt}, skip")
            return None

        log(f"  {symbol} MARKET BUY qty={qty} @ ~{ask} (spread={current_spread*100:.3f}%)")
        buy_order = ex.create_market_buy_order(symbol, qty)
        entry_price = float(buy_order.get('average') or ask)
        filled_qty = float(buy_order.get('filled') or qty)
        log(f"  {symbol} BUY FILLED @ {entry_price} qty={filled_qty}")

        coin = symbol.split('/')[0]
        time.sleep(1)
        bal = ex.fetch_balance()
        coin_free = float(bal[coin]['free'])
        sell_qty = truncate_qty(coin_free * 0.998, amt_step)

        sell_price = round(entry_price * (1 + SPREAD_TARGET),
                          len(str(price_step).rstrip('0').rstrip('.')) if price_step < 1 else 0)
        if sell_price <= entry_price:
            sell_price = round(entry_price + price_step,
                              len(str(price_step).rstrip('0').rstrip('.')) if price_step < 1 else 0)

        if sell_qty < min_amt:
            log(f"  {symbol} sell qty too small, market exit")
            ms = ex.create_market_sell_order(symbol, truncate_qty(coin_free, amt_step))
            exit_price = float(ms.get('average') or entry_price)
            exit_reason = "DUST_EXIT"
        else:
            log(f"  {symbol} SELL LIMIT @ {sell_price} qty={sell_qty} (+{SPREAD_TARGET*100:.2f}%)")
            sell_order = ex.create_limit_sell_order(symbol, sell_qty, sell_price)
            start_wait = time.time()
            exit_price = None
            exit_reason = "LIMIT_FILL"
            while time.time() - start_wait < SELL_TIMEOUT:
                time.sleep(3)
                try:
                    status = ex.fetch_order(sell_order['id'], symbol)
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
                bal2 = ex.fetch_balance()
                remaining = float(bal2[coin]['free'])
                if remaining > min_amt:
                    ms = ex.create_market_sell_order(symbol, truncate_qty(remaining, amt_step))
                    exit_price = float(ms.get('average') or entry_price)
                    exit_reason = "TIMEOUT_MARKET"
                    log(f"  {symbol} TIMEOUT market sell @ {exit_price}")
                else:
                    exit_price = sell_price
                    exit_reason = "TIMEOUT_DUST"

        gross_pnl = (exit_price - entry_price) * filled_qty
        buy_fee = entry_price * filled_qty * FEE_RATE
        sell_fee = exit_price * (sell_qty if sell_qty >= min_amt else filled_qty) * FEE_RATE
        net_pnl = gross_pnl - buy_fee - sell_fee
        win = net_pnl > 0

        trade_entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "exchange": "binance",
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
            "spread_at_entry_pct": round(current_spread * 100, 4),
            "fee_rate": FEE_RATE
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
    log("=== V19 BINANCE SPOT + BNB DISCOUNT INICIANDO ===")
    log(f"Fees efetivas: {FEE_RATE*100:.3f}% por lado (BNB -25%)")
    log(f"Primary: {PRIMARY}. Min spread={MIN_SPREAD_ENTRY*100:.2f}% Target={SPREAD_TARGET*100:.2f}%")
    log(f"Size={TRADE_SIZE} USDT. MaxLoss={MAX_LOSS}")

    ex = get_exchange()
    ex.load_markets()
    usdt_free = reconcile(ex)
    log(f"Start: binance_usdt={usdt_free:.4f}")

    start_time = time.time()
    last_trade_time = 0

    while time.time() - start_time < MAX_RUNTIME and state['running']:
        if state['total_loss'] >= MAX_LOSS:
            log(f"MAX LOSS {MAX_LOSS} reached, stopping")
            break

        elapsed = int(time.time() - start_time)
        state['scans'] += 1

        targets = [PRIMARY] + FALLBACKS
        best_sym = None
        best_spread = 0

        for sym in targets:
            if sym not in ex.symbols:
                continue
            try:
                t = ex.fetch_ticker(sym)
                bid = float(t['bid'] or 0)
                ask = float(t['ask'] or 0)
                if bid > 0 and ask > bid:
                    spread = (ask - bid) / bid
                    if spread > best_spread:
                        best_spread = spread
                        best_sym = sym
            except:
                pass

        if best_spread > state['max_spread']:
            state['max_spread'] = best_spread

        if state['scans'] % 20 == 0:
            log(f"  [{elapsed}s] scan#{state['scans']} best={best_sym} spread={best_spread*100:.3f}% max={state['max_spread']*100:.3f}%")

        if best_sym and best_spread >= MIN_SPREAD_ENTRY and (time.time() - last_trade_time) > COOLDOWN:
            bal = ex.fetch_balance()
            usdt_free = float(bal['USDT']['free'])
            if usdt_free >= TRADE_SIZE * 0.5:
                log(f"  OPPORTUNITY! {best_sym} spread={best_spread*100:.3f}%")
                result = execute_trade(ex, best_sym, TRADE_SIZE, best_spread)
                if result is not None:
                    last_trade_time = time.time()
            else:
                log(f"  Spread OK but low balance ({usdt_free:.2f})")

        time.sleep(SCAN_INTERVAL)
        save_state()

    state['running'] = False
    save_state()
    log(f"=== V19 FINALIZADO: trades={state['trades']} wins={state['wins']} pnl={state['pnl']:.4f} loss={state['total_loss']:.4f} scans={state['scans']} maxSpread={state['max_spread']*100:.3f}% ===")

if __name__ == '__main__':
    main()
