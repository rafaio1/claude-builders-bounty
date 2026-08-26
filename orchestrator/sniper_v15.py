#!/usr/bin/env python3
"""V15 - Patient Maker-Maker: only enter when spread >= 0.30%.
Buy limit at bid, sell limit at bid+0.30%. Both sides patient.
Fees are 0.1% each side = 0.20% total. Need >0.20% spread to profit.
Min spread target: 0.30% (0.10% net after fees).
"""
import ccxt, os, sys, json, time, math
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv('/Agentic/.env')
load_dotenv('/root/.automaton/bybit-murre.env', override=True)

LOG_FILE = '/Agentic/orchestrator/v15_output.log'
STATE_FILE = '/Agentic/orchestrator/v15_state.json'
LEDGER_FILE = '/Agentic/ledger.jsonl'

SYMBOLS = ['XRP/USDT', 'DOGE/USDT']
BYBIT_SIZE = 10.0
BINANCE_SIZE = 7.0
MIN_SPREAD_PCT = 0.0030  # 0.30% minimum to enter
SELL_SPREAD_PCT = 0.0030  # sell at entry + 0.30%
BUY_TIMEOUT = 180   # wait 3min for buy fill
SELL_TIMEOUT = 300  # wait 5min for sell fill
MAX_RUNTIME = 7200
MAX_LOSS = 2.0
CYCLE_COOLDOWN = 10
SCAN_INTERVAL = 5   # seconds between spread scans

state = {
    "version": "v15",
    "start_time": time.time(),
    "trades": {"bybit": 0, "binance": 0},
    "wins": {"bybit": 0, "binance": 0},
    "pnl": {"bybit": 0.0, "binance": 0.0},
    "total_loss": 0.0,
    "running": True,
    "skipped_no_spread": 0
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
    log("=== RECONCILIACAO V15 ===")
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
        return None

def execute_trade(ex_name, ex, symbol, size_usdt):
    """Only enter if current spread >= MIN_SPREAD_PCT. Buy at bid, sell at bid+SELL_SPREAD."""
    try:
        ticker = ex.fetch_ticker(symbol)
        bid = float(ticker['bid'])
        ask = float(ticker['ask'])
        current_spread = (ask - bid) / bid

        if current_spread < MIN_SPREAD_PCT:
            state['skipped_no_spread'] += 1
            log(f"  {ex_name} {symbol} spread={current_spread*100:.3f}% < {MIN_SPREAD_PCT*100:.1f}%, SKIP")
            return None

        log(f"  {ex_name} {symbol} SPREAD OK: {current_spread*100:.3f}% >= {MIN_SPREAD_PCT*100:.1f}%")

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

        qty_raw = size_usdt / bid
        qty = truncate_qty(qty_raw, amt_step)
        if qty <= min_amt:
            log(f"  {ex_name} {symbol} qty {qty} below min {min_amt}, skip")
            return None

        buy_price = round(bid, len(str(price_step).rstrip('0').rstrip('.')) if price_step < 1 else 0)
        log(f"  {ex_name} {symbol} BUY LIMIT @ {buy_price} qty={qty}")
        buy_order = ex.create_limit_buy_order(symbol, qty, buy_price)

        start_wait = time.time()
        entry_price = None
        filled_qty = 0
        while time.time() - start_wait < BUY_TIMEOUT:
            time.sleep(3)
            status = fetch_order_safe(ex, buy_order['id'], symbol, ex_name)
            if status is None:
                continue
            if status['status'] == 'closed':
                entry_price = float(status.get('average') or buy_price)
                filled_qty = float(status.get('filled') or qty)
                log(f"  {ex_name} {symbol} BUY FILLED @ {entry_price} qty={filled_qty}")
                break
            elif status['status'] == 'canceled':
                log(f"  {ex_name} {symbol} buy cancelled")
                return None

        if entry_price is None:
            try:
                ex.cancel_order(buy_order['id'], symbol)
            except:
                pass
            log(f"  {ex_name} {symbol} BUY TIMEOUT, cancelled")
            return None

        coin = symbol.split('/')[0]
        time.sleep(1)
        bal = ex.fetch_balance()
        coin_free = float(bal[coin]['free'])
        sell_qty = truncate_qty(coin_free * 0.998, amt_step)

        sell_price = round(entry_price * (1 + SELL_SPREAD_PCT),
                          len(str(price_step).rstrip('0').rstrip('.')) if price_step < 1 else 0)
        if sell_price <= entry_price:
            sell_price = round(entry_price + price_step,
                              len(str(price_step).rstrip('0').rstrip('.')) if price_step < 1 else 0)

        if sell_qty <= min_amt:
            log(f"  {ex_name} {symbol} sell qty too small, market exit")
            ms = ex.create_market_sell_order(symbol, truncate_qty(coin_free, amt_step))
            exit_price = float(ms.get('average') or entry_price)
            exit_reason = "DUST_EXIT"
        else:
            log(f"  {ex_name} {symbol} SELL LIMIT @ {sell_price} qty={sell_qty} (target +{SELL_SPREAD_PCT*100:.1f}%)")
            sell_order = ex.create_limit_sell_order(symbol, sell_qty, sell_price)

            start_wait = time.time()
            exit_price = None
            exit_reason = "LIMIT_FILL"
            while time.time() - start_wait < SELL_TIMEOUT:
                time.sleep(5)
                status = fetch_order_safe(ex, sell_order['id'], symbol, ex_name)
                if status is None:
                    continue
                if status['status'] == 'closed':
                    exit_price = float(status.get('average') or sell_price)
                    log(f"  {ex_name} {symbol} SELL FILLED @ {exit_price}")
                    break
                elif status['status'] == 'canceled':
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
            "spread_at_entry_pct": round(current_spread * 100, 4),
            "target_spread_pct": SELL_SPREAD_PCT * 100
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
    log("=== V15 PATIENT MAKER-MAKER INICIANDO ===")
    log(f"Estrategia: so entra se spread >= {MIN_SPREAD_PCT*100:.1f}%")
    log(f"Buy limit @ bid -> Sell limit @ entry+{SELL_SPREAD_PCT*100:.1f}%")
    log(f"Fees=0.1%+0.1%=0.2%. Min spread={MIN_SPREAD_PCT*100:.1f}% = lucro minimo {(MIN_SPREAD_PCT-0.002)*100:.1f}%")
    log(f"Max loss={MAX_LOSS} Runtime={MAX_RUNTIME}s")

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

            execute_trade(ex_name, ex, symbol, sizes[ex_name])
            time.sleep(CYCLE_COOLDOWN)

        save_state()

    state['running'] = False
    save_state()
    log(f"=== V15 FINALIZADO: trades={state['trades']} wins={state['wins']} pnl={state['pnl']} total_loss={state['total_loss']:.4f} skipped={state['skipped_no_spread']} ===")

if __name__ == '__main__':
    main()
