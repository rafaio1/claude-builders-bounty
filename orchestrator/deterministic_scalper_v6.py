#!/usr/bin/env python3
"""
Bot de scalping deterministico v6 - Bybit e Binance.
V5 falhou: RSI<25 nunca ocorre, TP 0.4% nunca atingido em 120s.
V6: sinal de dip de preco, TP menor, MaxHold curto.
"""
import ccxt
import os
import sys
import json
import time
import signal as sigmod
import traceback
import math
from datetime import datetime, timezone

EXCHANGE_NAME = sys.argv[1] if len(sys.argv) > 1 else 'bybit'
SESSION_START = datetime.now(timezone.utc)

if EXCHANGE_NAME == 'bybit':
    env = {}
    with open('/root/.automaton/bybit-murre.env') as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    API_KEY = env.get('BYBIT_REAL_API_KEY', '')
    API_SECRET = env.get('BYBIT_REAL_API_SECRET', '')
    BUDGET_USDT = 18.0
    RESERVE_USDT = 1.0
    TARGET_PROFIT = 10.0
    TP_PCT = 0.0015
    SL_PCT = 0.003
    MAX_HOLD_SEC = 20
    FEE_PCT = 0.0
elif EXCHANGE_NAME == 'binance':
    env = {}
    with open('/Agentic/.env') as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    API_KEY = env.get('BINANCE_API_KEY', '')
    API_SECRET = env.get('BINANCE_API_SECRET', '')
    BUDGET_USDT = 12.0
    RESERVE_USDT = 1.0
    TARGET_PROFIT = 20.0
    TP_PCT = 0.0045
    SL_PCT = 0.003
    MAX_HOLD_SEC = 40
    FEE_PCT = 0.001
else:
    print(f"Exchange desconhecida: {EXCHANGE_NAME}")
    sys.exit(1)

COOLDOWN_SEC = 3
SCAN_INTERVAL = 2
LEDGER_PATH = '/Agentic/ledger.jsonl'
MAX_PRICE = 1.50
MAX_SPREAD_PCT = 0.20
MIN_VOLUME_24H = 20e6
DIP_THRESHOLD_PCT = 0.25
DIP_LOOKBACK_SEC = 60

SCAN_SYMBOLS = [
    'DOGE/USDT', 'TRX/USDT', 'XRP/USDT', 'ADA/USDT',
    'PEPE/USDT', 'SUI/USDT', 'APT/USDT', 'ARB/USDT',
    'OP/USDT', 'ENA/USDT', 'SEI/USDT', 'GRT/USDT',
    'LDO/USDT', 'NEAR/USDT', 'FET/USDT', 'DYDX/USDT',
    'GALA/USDT', 'FTM/USDT', 'ALGO/USDT', 'ONE/USDT',
    'ANKR/USDT', 'CHZ/USDT', 'MANA/USDT', 'SAND/USDT',
    'AXS/USDT', 'ICP/USDT', 'FIL/USDT', 'THETA/USDT',
    'WLD/USDT', 'STX/USDT', 'CKB/USDT', 'CFX/USDT',
    'GAS/USDT', 'ORDI/USDT', 'WAVES/USDT', 'CRV/USDT',
    'LUNC/USDT', 'RVN/USDT', 'ZIL/USDT', 'GMT/USDT',
    'IMX/USDT', 'BAT/USDT', 'ZRX/USDT', 'INJ/USDT',
]

running = True

def handle_signal(signum, frame):
    global running
    running = False
    print(f"\n[SIGNAL] Parando...", flush=True)

sigmod.signal(sigmod.SIGINT, handle_signal)
sigmod.signal(sigmod.SIGTERM, handle_signal)

exchange_cls = ccxt.bybit if EXCHANGE_NAME == 'bybit' else ccxt.binance
exchange = exchange_cls({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'},
})

available_symbols = []

def load_markets():
    global available_symbols
    exchange.load_markets()
    available_symbols = []
    for sym in SCAN_SYMBOLS:
        if sym in exchange.markets:
            m = exchange.markets[sym]
            if m.get('active', True) and m.get('spot', True):
                available_symbols.append(sym)
    print(f"  Simbolos disponiveis: {len(available_symbols)}", flush=True)

def get_trade_size():
    try:
        bal = exchange.fetch_balance()
        usdt_free = float(bal.get('USDT', {}).get('free', 0))
        trade_cap = BUDGET_USDT - RESERVE_USDT
        return min(usdt_free - RESERVE_USDT, trade_cap)
    except Exception:
        return 0

def get_realized_pnl():
    total = 0.0
    try:
        with open(LEDGER_PATH, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    if d.get('exchange') == EXCHANGE_NAME and 'net_pnl' in d:
                        total += float(d['net_pnl'])
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    return total

def adjust_qty(symbol, raw_qty):
    try:
        m = exchange.markets[symbol]
        amt_prec = m.get('precision', {}).get('amount', 0.01)
        min_amt = m.get('limits', {}).get('amount', {}).get('min', 0.01)
        if amt_prec and amt_prec >= 1:
            q = math.floor(raw_qty / amt_prec) * amt_prec
        elif amt_prec and 0 < amt_prec < 1:
            q = math.floor(raw_qty / amt_prec) * amt_prec
            decimals = int(-math.log10(amt_prec)) + 2 if amt_prec < 1 else 6
            q = round(q, decimals)
        else:
            q = round(raw_qty, 6)
        if q < min_amt:
            q = math.ceil(raw_qty / amt_prec) * amt_prec if amt_prec else raw_qty
            q = round(q, 6)
        if q < 0.000001:
            return 0, False
        return q, True
    except Exception:
        return round(raw_qty, 6), True

def scan_for_dip(symbol):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, '1m', limit=5)
        if len(ohlcv) < 3:
            return False, 0, {}
        closes = [c[4] for c in ohlcv]
        current_price = closes[-1]
        ref_price = closes[-3] if len(closes) >= 3 else closes[0]
        if ref_price <= 0:
            return False, 0, {}
        drop_pct = (ref_price - current_price) / ref_price * 100
        ticker = exchange.fetch_ticker(symbol)
        bid = float(ticker.get('bid', 0))
        ask = float(ticker.get('ask', 0))
        if bid > 0 and ask > 0:
            spread_pct = (ask - bid) / bid * 100
        else:
            spread_pct = 999
        if spread_pct > MAX_SPREAD_PCT:
            return False, 0, {}
        quote_vol = float(ticker.get('quoteVolume', 0))
        if quote_vol < MIN_VOLUME_24H:
            return False, 0, {}
        if current_price > MAX_PRICE:
            return False, 0, {}
        if drop_pct >= DIP_THRESHOLD_PCT:
            last_low = ohlcv[-1][3]
            recovering = current_price > last_low * 1.0001
            return True, current_price, {
                'drop_pct': round(drop_pct, 3),
                'spread': round(spread_pct, 3),
                'vol24h': round(quote_vol / 1e6, 1),
                'recovering': recovering,
            }
        return False, 0, {}
    except Exception:
        return False, 0, {}

def execute_trade(symbol, entry_ref_price):
    coin = symbol.split('/')[0]
    trade_size = get_trade_size()
    if trade_size < 2:
        print(f"  Saldo insuficiente para trade", flush=True)
        return None
    m = exchange.markets[symbol]
    amt_prec = m.get('precision', {}).get('amount', 0.01)
    min_amt = m.get('limits', {}).get('amount', {}).get('min', 0.01)
    min_cost = m.get('limits', {}).get('cost', {}).get('min', 1.0)
    raw_qty = trade_size / entry_ref_price
    buy_qty, ok = adjust_qty(symbol, raw_qty)
    if not ok or buy_qty <= 0:
        print(f"  Qty invalida: {buy_qty}", flush=True)
        return None
    if buy_qty < min_amt or buy_qty * entry_ref_price < min_cost:
        print(f"  Qty/cost baixo: qty={buy_qty} cost={buy_qty*entry_ref_price:.4f}", flush=True)
        return None
    tp_price = entry_ref_price * (1 + TP_PCT)
    sl_price = entry_ref_price * (1 - SL_PCT)
    print(f"  [{EXCHANGE_NAME}] BUY {symbol} qty={buy_qty} @ ~{entry_ref_price:.6f} | TP={tp_price:.6f} SL={sl_price:.6f}", flush=True)
    try:
        buy_order = exchange.create_order(symbol, 'market', 'buy', buy_qty)
        fill_price = float(buy_order.get('average') or buy_order.get('price') or entry_ref_price)
        filled_qty = float(buy_order.get('amount') or buy_qty)
        buy_fee = float(buy_order.get('fee', {}).get('cost', 0) or 0)
        buy_fee_curr = buy_order.get('fee', {}).get('currency', 'USDT')
        print(f"  BUY filled: qty={filled_qty} @ {fill_price} fee={buy_fee} {buy_fee_curr}", flush=True)
    except Exception as e:
        print(f"  BUY error: {e}", flush=True)
        traceback.print_exc()
        return None
    tp_price = fill_price * (1 + TP_PCT)
    sl_price = fill_price * (1 - SL_PCT)
    time.sleep(0.3)
    try:
        bal = exchange.fetch_balance()
        actual_balance = float(bal.get(coin, {}).get('free', 0))
    except Exception:
        actual_balance = filled_qty
    sell_qty, ok_sell = adjust_qty(symbol, actual_balance)
    if not ok_sell or sell_qty <= 0:
        sell_qty = filled_qty
        print(f"  Usando qty original: {sell_qty}", flush=True)
    else:
        print(f"  Saldo real de {coin}: {actual_balance} -> sell_qty={sell_qty}", flush=True)
    entry_time = time.time()
    exit_price = fill_price
    exit_reason = 'NONE'
    check_count = 0
    while running and (time.time() - entry_time) < MAX_HOLD_SEC:
        try:
            ticker = exchange.fetch_ticker(symbol)
            current = float(ticker['last'])
            elapsed = time.time() - entry_time
            pnl_pct = (current - fill_price) / fill_price * 100
            check_count += 1
            if current >= tp_price:
                exit_price = current
                exit_reason = 'TP'
                print(f"  [{elapsed:.1f}s] {symbol} price={current} pnl={pnl_pct:.3f}% TP HIT!", flush=True)
                break
            if current <= sl_price:
                exit_price = current
                exit_reason = 'SL'
                print(f"  [{elapsed:.1f}s] {symbol} price={current} pnl={pnl_pct:.3f}% SL HIT", flush=True)
                break
            if check_count % 20 == 0:
                print(f"  [{elapsed:.1f}s] {symbol} price={current} pnl={pnl_pct:.3f}%", flush=True)
            time.sleep(0.5)
        except Exception as e:
            print(f"  Monitor error: {e}", flush=True)
            time.sleep(1)
    if exit_reason == 'NONE':
        try:
            ticker = exchange.fetch_ticker(symbol)
            exit_price = float(ticker['last'])
            exit_reason = 'TIMEOUT'
            print(f"  [{time.time()-entry_time:.1f}s] {symbol} TIMEOUT @ {exit_price}", flush=True)
        except Exception:
            exit_price = fill_price
            exit_reason = 'TIMEOUT'
    sell_fill = exit_price
    sell_fee = 0
    sell_fee_curr = 'USDT'
    try:
        sell_order = exchange.create_order(symbol, 'market', 'sell', sell_qty)
        sell_fill = float(sell_order.get('average') or sell_order.get('price') or exit_price)
        sell_fee = float(sell_order.get('fee', {}).get('cost', 0) or 0)
        sell_fee_curr = sell_order.get('fee', {}).get('currency', 'USDT')
        print(f"  SELL filled: qty={sell_qty} @ {sell_fill} reason={exit_reason} fee={sell_fee} {sell_fee_curr}", flush=True)
    except Exception as e:
        print(f"  SELL error: {e}", flush=True)
        try:
            time.sleep(1)
            bal2 = exchange.fetch_balance()
            real_amt = float(bal2.get(coin, {}).get('free', 0))
            adj_qty, _ = adjust_qty(symbol, real_amt)
            if adj_qty > 0:
                sell_order = exchange.create_order(symbol, 'market', 'sell', adj_qty)
                sell_fill = float(sell_order.get('average') or sell_order.get('price') or exit_price)
                sell_fee = float(sell_order.get('fee', {}).get('cost', 0) or 0)
                sell_fee_curr = sell_order.get('fee', {}).get('currency', 'USDT')
                sell_qty = adj_qty
                print(f"  SELL retry OK: qty={adj_qty} @ {sell_fill}", flush=True)
            else:
                print(f"  SELL retry falhou: saldo zero", flush=True)
        except Exception as e2:
            print(f"  SELL retry error: {e2}", flush=True)
            traceback.print_exc()
    buy_fee_usdt = buy_fee if buy_fee_curr == 'USDT' else buy_fee * fill_price
    sell_fee_usdt = sell_fee if sell_fee_curr == 'USDT' else sell_fee * sell_fill
    total_fees = buy_fee_usdt + sell_fee_usdt
    gross_pnl = (sell_fill - fill_price) * sell_qty
    net_pnl = gross_pnl - total_fees
    win = net_pnl > 0
    print(f"  RESULT: gross={gross_pnl:.6f} fees={total_fees:.6f} net={net_pnl:.6f} {'WIN' if win else 'LOSS'}", flush=True)
    entry_ts = datetime.now(timezone.utc).isoformat()
    record = {
        'ts': entry_ts,
        'exchange': EXCHANGE_NAME,
        'symbol': symbol,
        'entry_price': fill_price,
        'exit_price': sell_fill,
        'qty': sell_qty,
        'exit_reason': exit_reason,
        'gross_pnl': round(gross_pnl, 6),
        'fees_usdt': round(total_fees, 6),
        'net_pnl': round(net_pnl, 6),
        'win': win,
    }
    try:
        with open(LEDGER_PATH, 'a') as f:
            f.write(json.dumps(record) + '\n')
    except Exception:
        pass
    return net_pnl

def cleanup_open_orders():
    try:
        exchange.cancel_all_orders()
        print(f"  Ordens canceladas", flush=True)
    except Exception as e:
        print(f"  Cleanup ordens error: {e}", flush=True)

def cleanup_residual_balances():
    try:
        bal = exchange.fetch_balance()
        for coin, info in bal.get('total', {}).items():
            if coin == 'USDT':
                continue
            if isinstance(info, dict):
                amt = float(info.get('total', 0))
            else:
                try:
                    amt = float(info)
                except (TypeError, ValueError):
                    continue
            if amt <= 0:
                continue
            sym = f"{coin}/USDT"
            if sym not in exchange.markets:
                continue
            m = exchange.markets[sym]
            min_cost = m.get('limits', {}).get('cost', {}).get('min', 1.0)
            price_est = 0.001
            try:
                ticker = exchange.fetch_ticker(sym)
                price_est = float(ticker.get('last', 0.001))
            except Exception:
                pass
            if amt * price_est < min_cost:
                continue
            adj_qty, ok = adjust_qty(sym, amt)
            if not ok or adj_qty <= 0:
                continue
            try:
                exchange.create_order(sym, 'market', 'sell', adj_qty)
                print(f"  Vendido residual: {coin} qty={adj_qty}", flush=True)
                time.sleep(0.5)
            except Exception:
                pass
    except Exception as e:
        print(f"  Cleanup saldos error: {e}", flush=True)

def main_loop():
    print(f"[{EXCHANGE_NAME.upper()}] Bot v6 iniciado em {SESSION_START.isoformat()}", flush=True)
    print(f"  Budget: {BUDGET_USDT} USDT | Reserva: {RESERVE_USDT} | Meta: +{TARGET_PROFIT}", flush=True)
    print(f"  TP={TP_PCT*100}% SL={SL_PCT*100}% MaxHold={MAX_HOLD_SEC}s", flush=True)
    print(f"  Dip: {DIP_THRESHOLD_PCT}% | MaxPreco={MAX_PRICE} | MaxSpread={MAX_SPREAD_PCT}%", flush=True)
    load_markets()
    cleanup_open_orders()
    cleanup_residual_balances()
    cycle = 0
    last_trade_time = 0
    symbols_to_scan = list(available_symbols)
    while running:
        cycle += 1
        realized = get_realized_pnl()
        progress = (realized / TARGET_PROFIT * 100) if TARGET_PROFIT > 0 else 0
        print(f"[Cycle {cycle}] PnL: {realized:.6f} | Meta: {TARGET_PROFIT} | Progress: {progress:.1f}%", flush=True)
        if realized >= TARGET_PROFIT:
            print(f"  META ATINGIDA! {realized:.6f} >= {TARGET_PROFIT}", flush=True)
            break
        since_trade = time.time() - last_trade_time
        if since_trade < COOLDOWN_SEC:
            time.sleep(COOLDOWN_SEC - since_trade)
        found_signal = False
        for sym in symbols_to_scan:
            if not running:
                break
            try:
                has_signal, signal_price, signal_info = scan_for_dip(sym)
                if has_signal:
                    print(f"  SIGNAL: {sym} drop={signal_info.get('drop_pct')}% price={signal_price} info={signal_info}", flush=True)
                    result = execute_trade(sym, signal_price)
                    last_trade_time = time.time()
                    found_signal = True
                    break
            except Exception:
                pass
        if not found_signal:
            print(f"  Nenhum sinal", flush=True)
        time.sleep(SCAN_INTERVAL)
    print(f"\n[{EXCHANGE_NAME.upper()}] Bot parado. PnL: {get_realized_pnl():.6f}", flush=True)
    cleanup_open_orders()

if __name__ == '__main__':
    main_loop()
