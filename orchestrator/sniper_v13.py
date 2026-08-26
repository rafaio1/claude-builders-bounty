#!/usr/bin/env python3
"""
V13 SNIPER - Patient Limit Maker
================================
Correcoes vs V12:
1. SELL AMOUNT = saldo real da moeda (resolve Insufficient balance)
2. Spread 0.50% Bybit / 0.60% Binance (cobre 0.2% fee + lucro)
3. Sem SL: espera o preco voltar (evita realizar prejuizo)
4. Timeout sell 900s (paciente) - fallback reposiciona
5. Buffer 0.2% no sell amount para fees
6. Size: 10 USDT Bybit / 7 USDT Binance
7. Uma posicao por exchange por vez
8. Cooldown 10s entre trades
9. Max prejuizo total 2.0 USDT
10. Runtime 7200s (2h)
"""

import ccxt
import os
import sys
import json
import time
import math
from datetime import datetime, timezone
from dotenv import load_dotenv

BYBIT_ENV = '/root/.automaton/bybit-murre.env'
BINANCE_ENV = '/Agentic/.env'
LEDGER = '/Agentic/ledger.jsonl'
STATE_FILE = '/Agentic/orchestrator/v13_state.json'
LOG_FILE = '/Agentic/orchestrator/v13_output.log'

ORDER_SIZE_BYBIT = 10.0
ORDER_SIZE_BINANCE = 7.0
SPREAD_BYBIT = 0.0050
SPREAD_BINANCE = 0.0060
SELL_BUFFER = 0.002
BUY_TIMEOUT = 300
SELL_TIMEOUT = 900
SELL_REPOSITION_INTERVAL = 300
COOLDOWN = 10
MAX_TOTAL_LOSS = 2.0
RUNTIME = 7200
MAX_TRADES_PER_SYMBOL = 30
SYMBOLS_BYBIT = ['XRP/USDT', 'DOGE/USDT']
SYMBOLS_BINANCE = ['XRP/USDT', 'DOGE/USDT']


def log(msg):
    ts = datetime.now(timezone.utc).strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, 'a') as f:
            f.write(line + '\n')
    except:
        pass


def write_ledger(entry):
    try:
        with open(LEDGER, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    except:
        pass


def save_state(state):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
    except:
        pass


def fmt_price(ex, sym, val):
    return float(ex.price_to_precision(sym, str(val)))


def fmt_amount(ex, sym, val):
    return float(ex.amount_to_precision(sym, str(val)))


def init_exchanges():
    load_dotenv(BYBIT_ENV)
    bybit = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_REAL_API_KEY'),
        'secret': os.getenv('BYBIT_REAL_API_SECRET'),
        'options': {'defaultType': 'spot'}
    })
    bybit.options.setdefault('fetchOpenOrders', {})['warnWithoutSymbol'] = False

    load_dotenv(BINANCE_ENV, override=True)
    binance = ccxt.binance({
        'apiKey': os.getenv('BINANCE_API_KEY'),
        'secret': os.getenv('BINANCE_API_SECRET'),
        'options': {'defaultType': 'spot'}
    })
    binance.options.setdefault('fetchOpenOrders', {})['warnWithoutSymbol'] = False

    return bybit, binance


def load_market_params(ex, symbols):
    ex.load_markets()
    params = {}
    for sym in symbols:
        m = ex.market(sym)
        params[sym] = {
            'price_precision': m.get('precision', {}).get('price', 0.0001),
            'amount_precision': m.get('precision', {}).get('amount', 0.01),
            'min_cost': float(m.get('limits', {}).get('cost', {}).get('min', 5.0)),
            'min_amount': float(m.get('limits', {}).get('amount', {}).get('min', 0.0)),
            'tick_size': float(m.get('info', {}).get('tickSize', 0.01)),
        }
        pp = params[sym]
        log(f"  {sym}: pp={pp['price_precision']} ap={pp['amount_precision']} mc={pp['min_cost']} ma={pp['min_amount']}")
    return params


def reconcile(bybit, binance):
    log("=== RECONCILIACAO ===")

    bal = bybit.fetch_balance()
    bybit_usdt = float(bal.get('USDT', {}).get('free', 0) or 0)
    log(f"bybit: USDT free={bybit_usdt}")

    for coin in ['XRP', 'DOGE', 'SOL']:
        f = float(bal.get(coin, {}).get('free', 0) or 0)
        if f > 0:
            log(f"bybit: {coin} free={f} (dust)")

    for sym in SYMBOLS_BYBIT:
        try:
            orders = bybit.fetch_open_orders(sym)
            log(f"bybit {sym}: {len(orders)} ordens abertas")
            for o in orders:
                log(f"  CANCELING: {o['side']} {o['amount']} @ {o['price']} id={o['id']}")
                bybit.cancel_order(o['id'], sym)
                time.sleep(0.3)
        except Exception as e:
            log(f"bybit {sym}: erro ordens {e}")

    bal = binance.fetch_balance()
    binance_usdt = float(bal.get('USDT', {}).get('free', 0) or 0)
    log(f"binance: USDT free={binance_usdt}")

    for coin in ['XRP', 'DOGE']:
        f = float(bal.get(coin, {}).get('free', 0) or 0)
        if f > 0:
            log(f"binance: {coin} free={f} (dust)")

    for sym in SYMBOLS_BINANCE:
        try:
            orders = binance.fetch_open_orders(sym)
            log(f"binance {sym}: {len(orders)} ordens abertas")
            for o in orders:
                log(f"  CANCELING: {o['side']} {o['amount']} @ {o['price']} id={o['id']}")
                binance.cancel_order(o['id'], sym)
                time.sleep(0.3)
        except Exception as e:
            log(f"binance {sym}: erro ordens {e}")

    log("=== FIM RECONCILIACAO ===")
    return bybit_usdt, binance_usdt


def get_quote(ex, sym):
    try:
        t = ex.fetch_ticker(sym)
        bid = float(t.get('bid', 0))
        ask = float(t.get('ask', 0))
        last = float(t.get('last', 0))
        return bid, ask, last
    except Exception as e:
        log(f"  {sym} ticker erro: {e}")
        return None, None, None


def check_fill(ex, sym, order_id, since_ts):
    try:
        trades = ex.fetch_my_trades(sym, since=since_ts - 5000, limit=10)
        for t in trades:
            if str(t.get('order', '')) == str(order_id):
                return True, float(t['price']), float(t['amount']), t
        if trades:
            latest = trades[-1]
            if int(latest.get('timestamp', 0)) >= since_ts - 10000:
                return True, float(latest['price']), float(latest['amount']), latest
        return False, 0, 0, None
    except Exception as e:
        log(f"  check_fill erro: {e}")
        return False, 0, 0, None


def get_coin_balance(ex, coin):
    try:
        bal = ex.fetch_balance()
        return float(bal.get(coin, {}).get('free', 0) or 0)
    except:
        return 0.0


def execute_trade(ex, ex_name, sym, params, order_size, spread, state):
    start_time = time.time()

    bid, ask, last = get_quote(ex, sym)
    if not bid or not ask or bid <= 0 or ask <= 0:
        return 0.0, False, "NO_QUOTE"

    buy_price = fmt_price(ex, sym, bid)
    buy_cost = order_size
    buy_amount_raw = buy_cost / buy_price
    buy_amount = fmt_amount(ex, sym, buy_amount_raw)

    actual_cost = buy_amount * buy_price
    if actual_cost < params[sym]['min_cost']:
        log(f"  {ex_name} {sym}: cost {actual_cost:.4f} < min_cost {params[sym]['min_cost']}, skip")
        return 0.0, False, "MIN_COST"

    try:
        order = ex.create_limit_buy_order(sym, buy_amount, buy_price)
        order_id = order.get('id', '')
        log(f"  {ex_name} {sym} BUY LIMIT @ {buy_price} qty={buy_amount} id={order_id}")
    except Exception as e:
        log(f"  {ex_name} {sym} buy erro: {e}")
        return 0.0, False, "BUY_ERROR"

    buy_filled = False
    fill_price = 0
    fill_amount = 0
    buy_since = int(time.time() * 1000)

    while time.time() - start_time < BUY_TIMEOUT:
        time.sleep(5)
        try:
            o = ex.fetch_order(order_id, sym)
            if o.get('status') == 'closed':
                fill_price = float(o.get('average', o.get('price', buy_price)))
                fill_amount = float(o.get('filled', buy_amount))
                buy_filled = True
                break
        except:
            pass

        filled, fp, fa, trade_info = check_fill(ex, sym, order_id, buy_since)
        if filled:
            fill_price = fp
            fill_amount = fa
            buy_filled = True
            break

    if not buy_filled:
        try:
            ex.cancel_order(order_id, sym)
            log(f"  {ex_name} {sym} buy timeout, cancelado")
        except:
            pass
        return 0.0, False, "BUY_TIMEOUT"

    log(f"  {ex_name} {sym} BUY FILLED! @ {fill_price} qty={fill_amount}")

    time.sleep(1)
    coin = sym.split('/')[0]
    actual_balance = get_coin_balance(ex, coin)

    if actual_balance <= 0:
        sell_amount_raw = fill_amount * (1 - SELL_BUFFER - 0.005)
        log(f"  {ex_name} {sym} saldo moeda=0, usando fill_amount * 0.993 = {sell_amount_raw}")
    else:
        sell_amount_raw = actual_balance * (1 - SELL_BUFFER)

    sell_amount = fmt_amount(ex, sym, sell_amount_raw)

    if sell_amount <= 0:
        log(f"  {ex_name} {sym} sell_amount=0 apos precision, skip")
        return 0.0, False, "ZERO_SELL_AMOUNT"

    sell_price_raw = fill_price * (1 + spread)
    sell_price = fmt_price(ex, sym, sell_price_raw)

    sell_cost = sell_amount * sell_price
    if sell_cost < params[sym]['min_cost']:
        log(f"  {ex_name} {sym} sell cost {sell_cost:.4f} < min_cost, ajustando amount")
        sell_amount = fmt_amount(ex, sym, actual_balance if actual_balance > 0 else fill_amount * 0.99)

    log(f"  {ex_name} {sym} SELL LIMIT @ {sell_price} qty={sell_amount} (saldo real={actual_balance})")

    sell_order_id = None
    try:
        sell_order = ex.create_limit_sell_order(sym, sell_amount, sell_price)
        sell_order_id = sell_order.get('id', '')
        log(f"  {ex_name} {sym} sell order placed id={sell_order_id}")
    except Exception as e:
        log(f"  {ex_name} {sym} sell limit erro: {e}")
        sell_amount = fmt_amount(ex, sym, sell_amount * 0.995)
        try:
            sell_order = ex.create_limit_sell_order(sym, sell_amount, sell_price)
            sell_order_id = sell_order.get('id', '')
            log(f"  {ex_name} {sym} sell retry OK id={sell_order_id}")
        except Exception as e2:
            log(f"  {ex_name} {sym} sell retry2 erro: {e2}")
            try:
                sell_order = ex.create_market_sell_order(sym, sell_amount)
                sell_order_id = sell_order.get('id', '')
                log(f"  {ex_name} {sym} market sell fallback id={sell_order_id}")
            except Exception as e3:
                log(f"  {ex_name} {sym} CRITICAL: todas sells falharam: {e3}")
                return 0.0, False, "SELL_ALL_FAILED"

    sell_start = time.time()
    sell_filled = False
    exit_price = 0
    exit_amount = 0
    last_reposition = time.time()

    while time.time() - sell_start < SELL_TIMEOUT:
        time.sleep(5)

        try:
            o = ex.fetch_order(sell_order_id, sym)
            if o.get('status') == 'closed':
                exit_price = float(o.get('average', o.get('price', sell_price)))
                exit_amount = float(o.get('filled', sell_amount))
                sell_filled = True
                break
        except:
            pass

        sell_since = int(sell_start * 1000)
        filled, ep, ea, trade_info = check_fill(ex, sym, sell_order_id, sell_since)
        if filled:
            exit_price = ep
            exit_amount = ea
            sell_filled = True
            break

        if time.time() - last_reposition > SELL_REPOSITION_INTERVAL:
            last_reposition = time.time()
            try:
                ex.cancel_order(sell_order_id, sym)
                time.sleep(0.5)
                bid2, ask2, last2 = get_quote(ex, sym)
                if ask2 and ask2 > fill_price:
                    new_sell_price = fmt_price(ex, sym, ask2)
                else:
                    new_sell_price = fmt_price(ex, sym, fill_price * 1.001)

                actual_balance = get_coin_balance(ex, coin)
                if actual_balance > 0:
                    sell_amount = fmt_amount(ex, sym, actual_balance * (1 - SELL_BUFFER))

                sell_order = ex.create_limit_sell_order(sym, sell_amount, new_sell_price)
                sell_order_id = sell_order.get('id', '')
                log(f"  {ex_name} {sym} sell reposicionado @ {new_sell_price} qty={sell_amount}")
            except Exception as e:
                log(f"  {ex_name} {sym} reposiciona erro: {e}")

    if not sell_filled:
        try:
            ex.cancel_order(sell_order_id, sym)
            time.sleep(0.5)
            actual_balance = get_coin_balance(ex, coin)
            if actual_balance > 0:
                sell_amount = fmt_amount(ex, sym, actual_balance * (1 - SELL_BUFFER))
            market_sell = ex.create_market_sell_order(sym, sell_amount)
            exit_price = float(market_sell.get('average', market_sell.get('price', 0)))
            exit_amount = float(market_sell.get('filled', sell_amount))
            sell_filled = True
            log(f"  {ex_name} {sym} market sell final: @ {exit_price} qty={exit_amount}")
        except Exception as e:
            log(f"  {ex_name} {sym} market sell final erro: {e}")
            return 0.0, False, "SELL_TIMEOUT_MARKET_FAILED"

    if not sell_filled or exit_price <= 0:
        return 0.0, False, "SELL_NO_FILL"

    buy_cost_total = fill_amount * fill_price
    sell_revenue = exit_amount * exit_price

    buy_fee = buy_cost_total * 0.001
    sell_fee = sell_revenue * 0.001

    gross_pnl = sell_revenue - buy_cost_total
    net_pnl = gross_pnl - buy_fee - sell_fee
    win = net_pnl > 0

    reason = "TP_FILLED" if win else "LOSS_SELL"

    entry = {
        'ts': datetime.now(timezone.utc).isoformat(),
        'exchange': ex_name,
        'symbol': sym,
        'entry_price': fill_price,
        'exit_price': exit_price,
        'qty': fill_amount,
        'exit_qty': exit_amount,
        'gross_pnl': round(gross_pnl, 8),
        'fees_usdt': round(buy_fee + sell_fee, 8),
        'net_pnl': round(net_pnl, 8),
        'win': win,
        'exit_reason': reason,
        'sell_spread_pct': round((exit_price - fill_price) / fill_price * 100, 4),
    }
    write_ledger(entry)

    log(f"  {ex_name} {sym} TRADE CLOSED: entry={fill_price} exit={exit_price} "
        f"net_pnl={net_pnl:.6f} win={win}")

    return net_pnl, win, reason


def main():
    log("=== V13 SNIPER PATIENT LIMIT INICIANDO ===")
    log("Estrategia: buy no bid -> wait fill -> sell acima 0.50-0.60% -> PACIENTE 900s")
    log("Sem SL: espera o preco voltar. Buffer 0.2% no sell amount.")

    bybit, binance = init_exchanges()

    log("Carregando market params...")
    bybit_params = load_market_params(bybit, SYMBOLS_BYBIT)
    binance_params = load_market_params(binance, SYMBOLS_BINANCE)

    bybit_usdt, binance_usdt = reconcile(bybit, binance)

    state = {
        'version': 'v13',
        'start_time': time.time(),
        'trades': {'bybit': 0, 'binance': 0},
        'wins': {'bybit': 0, 'binance': 0},
        'pnl': {'bybit': 0.0, 'binance': 0.0},
        'total_loss': 0.0,
        'running': True,
    }
    save_state(state)

    start_time = time.time()
    bybit_idx = 0
    binance_idx = 0
    last_trade_time = {'bybit': 0, 'binance': 0}

    log(f"Start: bybit_usdt={bybit_usdt} binance_usdt={binance_usdt}")
    log(f"Trade sizes: bybit={ORDER_SIZE_BYBIT} binance={ORDER_SIZE_BINANCE}")

    while time.time() - start_time < RUNTIME:
        if state['total_loss'] >= MAX_TOTAL_LOSS:
            log("STOP GLOBAL: max loss atingido")
            break

        elapsed = int(time.time() - start_time)

        if time.time() - last_trade_time['bybit'] > COOLDOWN:
            sym = SYMBOLS_BYBIT[bybit_idx % len(SYMBOLS_BYBIT)]
            bybit_idx += 1

            usdt_free = get_coin_balance(bybit, 'USDT')
            if usdt_free >= ORDER_SIZE_BYBIT + 1:
                log(f"--- Bybit ciclo ({elapsed}s) {sym} ---")
                pnl, win, reason = execute_trade(
                    bybit, 'bybit', sym, bybit_params,
                    ORDER_SIZE_BYBIT, SPREAD_BYBIT, state
                )

                state['trades']['bybit'] += 1
                state['pnl']['bybit'] += pnl
                if win:
                    state['wins']['bybit'] += 1
                if pnl < 0:
                    state['total_loss'] += abs(pnl)

                save_state(state)
                last_trade_time['bybit'] = time.time()
                log(f"  Bybit state: trades={state['trades']['bybit']} "
                    f"wins={state['wins']['bybit']} pnl={state['pnl']['bybit']:.6f} "
                    f"total_loss={state['total_loss']:.6f}")
            else:
                log(f"  Bybit skip: USDT free={usdt_free:.4f} < {ORDER_SIZE_BYBIT + 1}")
                time.sleep(5)

        time.sleep(2)

        if time.time() - last_trade_time['binance'] > COOLDOWN:
            sym = SYMBOLS_BINANCE[binance_idx % len(SYMBOLS_BINANCE)]
            binance_idx += 1

            usdt_free = get_coin_balance(binance, 'USDT')
            if usdt_free >= ORDER_SIZE_BINANCE + 1:
                log(f"--- Binance ciclo ({elapsed}s) {sym} ---")
                pnl, win, reason = execute_trade(
                    binance, 'binance', sym, binance_params,
                    ORDER_SIZE_BINANCE, SPREAD_BINANCE, state
                )

                state['trades']['binance'] += 1
                state['pnl']['binance'] += pnl
                if win:
                    state['wins']['binance'] += 1
                if pnl < 0:
                    state['total_loss'] += abs(pnl)

                save_state(state)
                last_trade_time['binance'] = time.time()
                log(f"  Binance state: trades={state['trades']['binance']} "
                    f"wins={state['wins']['binance']} pnl={state['pnl']['binance']:.6f} "
                    f"total_loss={state['total_loss']:.6f}")
            else:
                log(f"  Binance skip: USDT free={usdt_free:.4f} < {ORDER_SIZE_BINANCE + 1}")
                time.sleep(5)

        time.sleep(2)

    log("=== V13 FINAL REPORT ===")
    log(f"Bybit:   trades={state['trades']['bybit']} wins={state['wins']['bybit']} pnl={state['pnl']['bybit']:.6f}")
    log(f"Binance: trades={state['trades']['binance']} wins={state['wins']['binance']} pnl={state['pnl']['binance']:.6f}")
    log(f"Total loss: {state['total_loss']:.6f}")
    save_state(state)


if __name__ == '__main__':
    main()
