#!/usr/bin/env python3
"""V21 - Maker-Maker Limit: buy at bid, sell at ask. Both sides patient.
Edge = (ask - bid) - fees. With BNB discount: 0.15% fees.
Only enter when spread >= 0.18% (net +0.03%).
Buy timeout 120s, sell timeout 120s. No market exits unless dust.
"""
import ccxt, os, sys, json, time, math
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv('/Agentic/.env')
load_dotenv('/root/.automaton/bybit-murre.env', override=True)

LOG_FILE = '/Agentic/orchestrator/v21_output.log'
STATE_FILE = '/Agentic/orchestrator/v21_state.json'
LEDGER_FILE = '/Agentic/ledger.jsonl'

BINANCE_SYMBOLS = ['PNUT/USDT', 'ACT/USDT']
BYBIT_SYMBOLS = ['DOGE/USDT', 'XRP/USDT']
MAX_SIZE_BN = 7.0
MAX_SIZE_BB = 10.0
MIN_SIZE = 1.0
MIN_SPREAD_BN = 0.0018
MIN_SPREAD_BB = 0.0022
BUY_TIMEOUT = 120
SELL_TIMEOUT = 120
MAX_RUNTIME = 7200
MAX_LOSS = 2.0
SCAN_INTERVAL = 3
COOLDOWN = 10
FEE_BN = 0.00075
FEE_BB = 0.001

state = {
    "version": "v21",
    "start_time": time.time(),
    "trades": {"binance": 0, "bybit": 0},
    "wins": {"binance": 0, "bybit": 0},
    "pnl": {"binance": 0.0, "bybit": 0.0},
    "total_loss": 0.0,
    "running": True,
    "scans": 0,
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

def get_exchanges():
    bn = ccxt.binance({
        'apiKey': os.getenv('BINANCE_API_KEY'),
        'secret': os.getenv('BINANCE_API_SECRET'),
        'options': {'warnOnFetchOpenOrdersWithoutSymbol': False}
    })
    bb = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_REAL_API_KEY'),
        'secret': os.getenv('BYBIT_REAL_API_SECRET'),
        'options': {'defaultType': 'spot'}
    })
    return bn, bb

def truncate_qty(value, step):
    if step >= 1:
        return int(value / step) * step
    decimals = max(0, int(round(-math.log10(step))))
    factor = 10 ** decimals
    return math.floor(value * factor) / factor

def reconcile(exchanges):
    log("=== RECONCILIACAO V21 ===")
    for name, ex in exchanges.items():
        bal = ex.fetch_balance()
        usdt = float(bal['USDT']['free'])
        log(f"  {name}: USDT={usdt:.4f}")
        syms = BINANCE_SYMBOLS if name == 'binance' else BYBIT_SYMBOLS
        for sym in syms:
            try:
                orders = ex.fetch_open_orders(sym)
                if orders:
                    log(f"  WARNING: {name} {sym} has {len(orders)} open!")
                    for o in orders:
                        ex.cancel_order(o['id'], sym)
                        log(f"    Cancelled {o['id']}")
            except Exception as e:
                log(f"  {name} {sym} check error: {e}")
    log("=== FIM RECONCILIACAO ===")

def execute_maker_trade(ex_name, ex, symbol, size_usdt, bid_price, ask_price, fee_rate):
    """Buy limit at bid, then sell limit at ask. Pure maker both sides."""
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
        min_notional = market_info.get('limits', {}).get('cost', {}).get('min', 0)

        qty_raw = size_usdt / bid_price
        qty = truncate_qty(qty_raw, amt_step)
        notional = qty * bid_price

        if qty < min_amt or notional < min_notional:
            log(f"  {ex_name} {symbol} qty={qty} notional={notional:.2f} below min, skip")
            return None

        buy_price = round(bid_price, len(str(price_step).rstrip('0').rstrip('.')) if price_step < 1 else 0)
        sell_price = round(ask_price, len(str(price_step).rstrip('0').rstrip('.')) if price_step < 1 else 0)

        expected_gross = (sell_price - buy_price) * qty
        expected_fees = (buy_price * qty + sell_price * qty) * fee_rate
        expected_net = expected_gross - expected_fees

        log(f"  {ex_name} {symbol} MAKER BUY @ {buy_price} qty={qty} -> SELL @ {sell_price}")
        log(f"  {ex_name} {symbol} Expected: gross={expected_gross:.4f} fees={expected_fees:.4f} net={expected_net:.4f}")

        # Place buy limit at bid
        buy_order = ex.create_limit_buy_order(symbol, qty, buy_price)
        start_wait = time.time()
        entry_price = None
        filled_qty = 0

        while time.time() - start_wait < BUY_TIMEOUT:
            time.sleep(3)
            try:
                if ex_name == 'bybit':
                    status = ex.fetch_order(buy_order['id'], symbol, params={'acknowledged': True})
                else:
                    status = ex.fetch_order(buy_order['id'], symbol)
                if status['status'] == 'closed':
                    entry_price = float(status.get('average') or buy_price)
                    filled_qty = float(status.get('filled') or qty)
                    log(f"  {ex_name} {symbol} BUY FILLED @ {entry_price} qty={filled_qty}")
                    break
                elif status['status'] == 'canceled':
                    log(f"  {ex_name} {symbol} buy cancelled")
                    return None
            except:
                pass

        if entry_price is None:
            try:
                ex.cancel_order(buy_order['id'], symbol)
            except:
                pass
            log(f"  {ex_name} {symbol} BUY TIMEOUT, cancelled")
            return None

        # Get actual coin balance after buy
        coin = symbol.split('/')[0]
        time.sleep(1)
        bal = ex.fetch_balance()
        coin_free = float(bal[coin]['free'])
        sell_qty = truncate_qty(coin_free * 0.998, amt_step)

        if sell_qty < min_amt:
            log(f"  {ex_name} {symbol} sell qty too small after buy")
            return None

        # Place sell limit at original ask price
        log(f"  {ex_name} {symbol} SELL LIMIT @ {sell_price} qty={sell_qty}")
        sell_order = ex.create_limit_sell_order(symbol, sell_qty, sell_price)
        start_wait = time.time()
        exit_price = None
        exit_reason = "LIMIT_FILL"

        while time.time() - start_wait < SELL_TIMEOUT:
            time.sleep(3)
            try:
                if ex_name == 'bybit':
                    status = ex.fetch_order(sell_order['id'], symbol, params={'acknowledged': True})
                else:
                    status = ex.fetch_order(sell_order['id'], symbol)
                if status['status'] == 'closed':
                    exit_price = float(status.get('average') or sell_price)
                    log(f"  {ex_name} {symbol} SELL FILLED @ {exit_price}")
                    break
                elif status['status'] == 'canceled':
                    log(f"  {ex_name} {symbol} sell cancelled")
                    break
            except:
                pass

        if exit_price is None:
            # Sell didn't fill - cancel and hold position (don't market sell at loss)
            try:
                ex.cancel_order(sell_order['id'], symbol)
            except:
                pass
            log(f"  {ex_name} {symbol} SELL TIMEOUT - holding {coin} position (no forced loss)")
            exit_reason = "HOLD_POSITION"
            # Record as incomplete trade, don't count as loss
            state['skipped'] += 1
            save_state()
            return None

        gross_pnl = (exit_price - entry_price) * filled_qty
        buy_fee = entry_price * filled_qty * fee_rate
        sell_fee = exit_price * sell_qty * fee_rate
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
            "strategy": "maker_maker",
            "fee_rate": fee_rate
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
        log(f"  {ex_name} cumulative: trades={state['trades'][ex_name]} wins={state['wins'][ex_name]} pnl={state['pnl'][ex_name]:.4f}")
        return net_pnl

    except Exception as e:
        log(f"  {ex_name} {symbol} ERROR: {e}")
        import traceback
        log(f"  TRACEBACK: {traceback.format_exc()}")
        return None

def main():
    log("=== V21 MAKER-MAKER LIMIT INICIANDO ===")
    log(f"Binance: fee={FEE_BN*100:.3f}% minSpread={MIN_SPREAD_BN*100:.2f}%")
    log(f"Bybit: fee={FEE_BB*100:.3f}% minSpread={MIN_SPREAD_BB*100:.2f}%")
    log(f"Strategy: buy@bid -> sell@ask. NO market exits on timeout.")
    log(f"MaxLoss={MAX_LOSS} Runtime={MAX_RUNTIME}s")

    bn, bb = get_exchanges()
    bn.load_markets()
    bb.load_markets()
    exchanges = {'binance': bn, 'bybit': bb}

    reconcile(exchanges)

    bal_bn = bn.fetch_balance()
    bal_bb = bb.fetch_balance()
    log(f"Start: binance_usdt={float(bal_bn['USDT']['free']):.4f} bybit_usdt={float(bal_bb['USDT']['free']):.4f}")

    start_time = time.time()
    last_trade_time = {'binance': 0, 'bybit': 0}

    while time.time() - start_time < MAX_RUNTIME and state['running']:
        if state['total_loss'] >= MAX_LOSS:
            log(f"MAX LOSS {MAX_LOSS} reached, stopping")
            break

        elapsed = int(time.time() - start_time)
        state['scans'] += 1

        for ex_name, ex, symbols, min_spread, fee_rate, max_size in [
            ('binance', bn, BINANCE_SYMBOLS, MIN_SPREAD_BN, FEE_BN, MAX_SIZE_BN),
            ('bybit', bb, BYBIT_SYMBOLS, MIN_SPREAD_BB, FEE_BB, MAX_SIZE_BB)
        ]:
            if not state['running'] or state['total_loss'] >= MAX_LOSS:
                break
            if (time.time() - last_trade_time[ex_name]) < COOLDOWN:
                continue

            best_sym = None
            best_bid = 0
            best_ask = 0
            best_spread = 0

            for sym in symbols:
                if sym not in ex.symbols:
                    continue
                try:
                    ob = ex.fetch_order_book(sym, limit=3)
                    bid = float(ob['bids'][0][0]) if ob['bids'] else 0
                    ask = float(ob['asks'][0][0]) if ob['asks'] else 0
                    if bid > 0 and ask > bid:
                        spread = (ask - bid) / bid
                        if spread > best_spread:
                            best_spread = spread
                            best_bid = bid
                            best_ask = ask
                            best_sym = sym
                except:
                    pass

            if best_sym and best_spread >= min_spread:
                bal = ex.fetch_balance()
                usdt_free = float(bal['USDT']['free'])
                trade_size = min(usdt_free * 0.9, max_size)

                if trade_size >= MIN_SIZE:
                    log(f"  OPPORTUNITY! {ex_name} {best_sym} spread={best_spread*100:.3f}% bid={best_bid} ask={best_ask}")
                    result = execute_maker_trade(ex_name, ex, best_sym, trade_size, best_bid, best_ask, fee_rate)
                    if result is not None:
                        last_trade_time[ex_name] = time.time()
                else:
                    if state['scans'] % 30 == 0:
                        log(f"  [{elapsed}s] {ex_name} spread OK but low balance ({usdt_free:.2f})")

        if state['scans'] % 30 == 0:
            total_pnl = state['pnl']['binance'] + state['pnl']['bybit']
            log(f"  [{elapsed}s] scan#{state['scans']} bn={state['trades']['binance']}t bb={state['trades']['bybit']}t pnl={total_pnl:.4f} skipped={state['skipped']}")

        time.sleep(SCAN_INTERVAL)
        save_state()

    state['running'] = False
    save_state()
    total_pnl = state['pnl']['binance'] + state['pnl']['bybit']
    log(f"=== V21 FINALIZADO: bn={state['trades']['binance']}t/{state['wins']['binance']}w bb={state['trades']['bybit']}t/{state['wins']['bybit']}w pnl={total_pnl:.4f} loss={state['total_loss']:.4f} skipped={state['skipped']} ===")

if __name__ == '__main__':
    main()
