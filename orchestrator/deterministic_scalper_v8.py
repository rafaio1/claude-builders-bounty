#!/usr/bin/env python3
"""
Bot de scalping deterministico V8 - Micro-Momentum + Trailing Stop.
V4: limit orders nao preenchem (MORTO)
V5: RSI<25 nunca ocorre (MORTO)
V6: comprar dip = pegar faca caindo (MORTO)
V7: arquivo nunca salvo (MISSING)
V8: Multi-tick momentum + trailing stop + daily loss limit.
Bybit fee=0% => qualquer movimento positivo = lucro puro.
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

# -- Config --
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
    BUDGET_USDT = 19.0
    RESERVE_USDT = 1.0
    TARGET_PROFIT = 10.0
    TP_PCT = 0.0012
    SL_PCT = 0.0006
    TRAIL_ACTIVATE_PCT = 0.0004
    TRAIL_OFFSET_PCT = 0.0002
    MAX_HOLD_SEC = 20
    FEE_PCT = 0.0
    DAILY_LOSS_LIMIT = 0.3
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
    BUDGET_USDT = 13.0
    RESERVE_USDT = 1.0
    TARGET_PROFIT = 20.0
    TP_PCT = 0.0025
    SL_PCT = 0.0012
    TRAIL_ACTIVATE_PCT = 0.0008
    TRAIL_OFFSET_PCT = 0.0004
    MAX_HOLD_SEC = 45
    FEE_PCT = 0.001
    DAILY_LOSS_LIMIT = 0.5
else:
    print(f"Exchange desconhecida: {EXCHANGE_NAME}")
    sys.exit(1)

COOLDOWN_SEC = 2
LEDGER_PATH = '/Agentic/ledger.jsonl'
MAX_PRICE = 1.50
MAX_SPREAD_PCT = 0.15
MIN_VOLUME_24H = 30e6
MAX_CONSEC_LOSSES = 5
LOSS_PAUSE_SEC = 60
MOMENTUM_TICKS = 2
MOMENTUM_INTERVAL = 2
MOMENTUM_MIN_MOVE_PCT = 0.005

SCAN_SYMBOLS = [
    'DOGE/USDT', 'TRX/USDT', 'XRP/USDT', 'ADA/USDT',
    'PEPE/USDT', 'SUI/USDT', 'APT/USDT', 'ARB/USDT',
    'OP/USDT', 'ENA/USDT', 'SEI/USDT', 'GRT/USDT',
    'LDO/USDT', 'NEAR/USDT', 'FET/USDT', 'DYDX/USDT',
    'GALA/USDT', 'FTM/USDT', 'ALGO/USDT', 'ONE/USDT',
    'ANKR/USDT', 'CHZ/USDT', 'MANA/USDT', 'SAND/USDT',
    'AXS/USDT', 'FIL/USDT', 'WLD/USDT', 'STX/USDT',
    'CKB/USDT', 'CFX/USDT', 'GAS/USDT', 'ORDI/USDT',
    'WAVES/USDT', 'CRV/USDT', 'IMX/USDT', 'BAT/USDT',
    'ZRX/USDT', 'INJ/USDT', 'JASMY/USDT', 'LUNC/USDT',
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
if EXCHANGE_NAME == 'binance':
    exchange.options['fetchOpenOrders'] = {'warnWithoutSymbol': False}
    exchange.options['fetchTickers'] = {'warnWithoutSymbol': False}

available_symbols = []
price_history = {}
session_pnl = 0.0
session_trades = 0
session_wins = 0
consec_losses = 0
last_loss_time = 0


def log_ledger(entry):
    try:
        with open(LEDGER_PATH, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    except Exception:
        pass


def ts():
    return datetime.now(timezone.utc).isoformat()


def load_markets():
    global available_symbols
    exchange.load_markets()
    available_symbols = []
    for sym in SCAN_SYMBOLS:
        if sym in exchange.markets:
            m = exchange.markets[sym]
            if m.get('active', True) and m.get('spot', True):
                available_symbols.append(sym)
    print(f"[{ts()}] [{EXCHANGE_NAME}] Simbolos disponiveis: {len(available_symbols)}", flush=True)


def get_trade_size():
    try:
        bal = exchange.fetch_balance()
        usdt_free = float(bal.get('USDT', {}).get('free', 0))
        trade_cap = BUDGET_USDT - RESERVE_USDT
        return min(usdt_free - RESERVE_USDT, trade_cap)
    except Exception:
        return 0


def filter_symbols(tickers):
    candidates = []
    for sym in available_symbols:
        t = tickers.get(sym)
        if not t:
            continue
        last = float(t.get('last', 0) or 0)
        if last <= 0 or last > MAX_PRICE:
            continue
        bid = float(t.get('bid', 0) or 0)
        ask = float(t.get('ask', 0) or 0)
        if bid <= 0 or ask <= 0:
            continue
        spread_pct = (ask - bid) / bid * 100
        if spread_pct > MAX_SPREAD_PCT:
            continue
        vol = float(t.get('quoteVolume', 0) or t.get('baseVolume', 0) or 0)
        if vol < MIN_VOLUME_24H:
            continue
        candidates.append((sym, last, bid, ask, vol))
    return candidates


def detect_momentum(sym, current_price):
    hist = price_history.get(sym, [])
    if len(hist) < MOMENTUM_TICKS:
        return False
    recent = hist[-MOMENTUM_TICKS:]
    for i in range(1, len(recent)):
        if recent[i][1] <= recent[i - 1][1]:
            return False
    total_move_pct = (recent[-1][1] - recent[0][1]) / recent[0][1] * 100
    return total_move_pct >= MOMENTUM_MIN_MOVE_PCT


def update_price_history(tickers):
    now = time.time()
    for sym in available_symbols:
        t = tickers.get(sym)
        if t:
            last = float(t.get('last', 0) or 0)
            if last > 0:
                if sym not in price_history:
                    price_history[sym] = []
                price_history[sym].append((now, last))
                cutoff = now - (MOMENTUM_TICKS * MOMENTUM_INTERVAL + 5)
                price_history[sym] = [(t, p) for t, p in price_history[sym] if t > cutoff]


def execute_trade(sym, trade_size_usdt):
    global session_pnl, session_trades, session_wins, consec_losses, running

    try:
        ticker = exchange.fetch_ticker(sym)
        entry_price = float(ticker.get('last', 0))
        if entry_price <= 0:
            return

        symbol_info = exchange.markets.get(sym, {})
        min_cost = float(symbol_info.get('limits', {}).get('cost', {}).get('min', 0) or 0)
        min_qty = float(symbol_info.get('limits', {}).get('amount', {}).get('min', 0) or 0)
        qty_precision = int(symbol_info.get("precision", {}).get("amount", 8))

        raw_qty = trade_size_usdt / entry_price
        qty = max(raw_qty, min_qty)
        if min_cost > 0 and qty * entry_price < min_cost:
            qty = min_cost / entry_price * 1.01
        qty = float(f"{qty:.{qty_precision}f}")
        if qty <= 0:
            return

        actual_cost = qty * entry_price
        if actual_cost > trade_size_usdt * 1.05:
            qty = float(f"{trade_size_usdt / entry_price:.{qty_precision}f}")
            if qty < min_qty:
                return

        print(f"[{ts()}] [{EXCHANGE_NAME}] BUY {sym} qty={qty} @ ~{entry_price} (cost={actual_cost:.4f})", flush=True)

        order = exchange.create_order(sym, 'market', 'buy', qty)
        fill_price = float(order.get('average', 0) or entry_price)
        entry_price = fill_price if fill_price > 0 else entry_price

        tp_price = entry_price * (1 + TP_PCT)
        sl_price = entry_price * (1 - SL_PCT)
        trail_active = False
        best_price = entry_price
        hold_start = time.time()

        print(f"[{ts()}] [{EXCHANGE_NAME}] Position: entry={entry_price} TP={tp_price} SL={sl_price}", flush=True)

        while running:
            elapsed = time.time() - hold_start
            if elapsed > MAX_HOLD_SEC:
                reason = "TIMEOUT"
                break

            try:
                t = exchange.fetch_ticker(sym)
                current = float(t.get('last', 0))
                bid = float(t.get('bid', 0) or 0)
                ask = float(t.get('ask', 0) or 0)
            except Exception:
                time.sleep(0.3)
                continue

            if current <= 0:
                time.sleep(0.3)
                continue

            if current > best_price:
                best_price = current

            move_pct = (current - entry_price) / entry_price
            if move_pct >= TRAIL_ACTIVATE_PCT and not trail_active:
                trail_active = True
                sl_price = entry_price * (1 + 0.0001)
                print(f"[{ts()}] [{EXCHANGE_NAME}] Trail ativado: SL={sl_price}", flush=True)

            if trail_active:
                new_trail_sl = best_price * (1 - TRAIL_OFFSET_PCT)
                if new_trail_sl > sl_price:
                    sl_price = new_trail_sl

            if current >= tp_price:
                reason = "TP"
                break
            if current <= sl_price:
                reason = "SL"
                break

            time.sleep(0.3)
        else:
            reason = "SIGNAL_STOP"

        sell_price = current
        try:
            sell_order = exchange.create_order(sym, 'market', 'sell', qty)
            sell_fill = float(sell_order.get('average', 0) or sell_price)
            if sell_fill > 0:
                sell_price = sell_fill
        except Exception as e:
            print(f"[{ts()}] [{EXCHANGE_NAME}] ERRO SELL: {e} -- tentando novamente...", flush=True)
            time.sleep(0.5)
            try:
                sell_order = exchange.create_order(sym, 'market', 'sell', qty)
                sell_fill = float(sell_order.get('average', 0) or sell_price)
                if sell_fill > 0:
                    sell_price = sell_fill
            except Exception as e2:
                print(f"[{ts()}] [{EXCHANGE_NAME}] SELL FALHOU: {e2}", flush=True)
                sell_price = current

        gross_pnl = (sell_price - entry_price) * qty
        fees_usdt = entry_price * qty * FEE_PCT + sell_price * qty * FEE_PCT
        net_pnl = gross_pnl - fees_usdt
        win = net_pnl > 0

        session_trades += 1
        session_pnl += net_pnl
        if win:
            session_wins += 1
            consec_losses = 0
        else:
            consec_losses += 1
            last_loss_time = time.time()

        entry_dict = {
            'ts': ts(),
            'exchange': EXCHANGE_NAME,
            'symbol': sym,
            'entry_price': entry_price,
            'exit_price': sell_price,
            'qty': qty,
            'exit_reason': reason,
            'gross_pnl': round(gross_pnl, 8),
            'fees_usdt': round(fees_usdt, 8),
            'net_pnl': round(net_pnl, 8),
            'win': win,
            'session_pnl': round(session_pnl, 8),
            'session_trades': session_trades,
            'session_wins': session_wins,
        }
        log_ledger(entry_dict)

        win_rate = session_wins / session_trades * 100 if session_trades > 0 else 0
        print(f"[{ts()}] [{EXCHANGE_NAME}] EXIT {sym} reason={reason} "
              f"net_pnl={net_pnl:.6f} | session={session_pnl:.6f} "
              f"trades={session_trades} wins={session_wins} ({win_rate:.0f}%)", flush=True)

        if session_pnl <= -DAILY_LOSS_LIMIT:
            print(f"[{ts()}] [{EXCHANGE_NAME}] DAILY LOSS LIMIT HIT ({session_pnl:.4f}). PARANDO.", flush=True)
            log_ledger({'kind': 'daily_loss_limit', 'exchange': EXCHANGE_NAME,
                        'session_pnl': round(session_pnl, 8), 'ts': ts()})
            running = False

        if consec_losses >= MAX_CONSEC_LOSSES:
            print(f"[{ts()}] [{EXCHANGE_NAME}] {MAX_CONSEC_LOSSES} consec losses. Pausa {LOSS_PAUSE_SEC}s.", flush=True)
            time.sleep(LOSS_PAUSE_SEC)
            consec_losses = 0

    except ccxt.InsufficientFunds as e:
        print(f"[{ts()}] [{EXCHANGE_NAME}] InsufficientFunds: {e}", flush=True)
    except ccxt.NetworkError as e:
        print(f"[{ts()}] [{EXCHANGE_NAME}] NetworkError: {e}", flush=True)
    except ccxt.ExchangeError as e:
        print(f"[{ts()}] [{EXCHANGE_NAME}] ExchangeError: {e}", flush=True)
    except Exception as e:
        print(f"[{ts()}] [{EXCHANGE_NAME}] ERRO INESPERADO: {e}", flush=True)
        traceback.print_exc()


def main_loop():
    global running
    last_scan = 0
    last_trade_time = 0

    print(f"[{ts()}] [{EXCHANGE_NAME}] V8 iniciado. Budget={BUDGET_USDT} Target={TARGET_PROFIT}", flush=True)
    print(f"[{ts()}] [{EXCHANGE_NAME}] TP={TP_PCT*100:.2f}% SL={SL_PCT*100:.2f}% "
          f"MaxHold={MAX_HOLD_SEC}s TrailAct={TRAIL_ACTIVATE_PCT*100:.2f}%", flush=True)

    while running:
        now = time.time()

        if session_pnl >= TARGET_PROFIT:
            print(f"[{ts()}] [{EXCHANGE_NAME}] TARGET REACHED: {session_pnl:.4f} USDT", flush=True)
            log_ledger({'kind': 'target_reached', 'exchange': EXCHANGE_NAME,
                        'session_pnl': round(session_pnl, 8), 'ts': ts()})
            break

        if now - last_scan < MOMENTUM_INTERVAL:
            time.sleep(0.2)
            continue

        last_scan = now

        if now - last_trade_time < COOLDOWN_SEC:
            time.sleep(0.2)
            continue

        try:
            tickers = exchange.fetch_tickers(available_symbols)
        except Exception as e:
            print(f"[{ts()}] [{EXCHANGE_NAME}] fetchTickers erro: {e}", flush=True)
            time.sleep(2)
            continue

        update_price_history(tickers)
        candidates = filter_symbols(tickers)

        if not candidates:
            continue

        best_sym = None
        best_score = 0
        for sym, last, bid, ask, vol in candidates:
            if detect_momentum(sym, last):
                hist = price_history.get(sym, [])
                if len(hist) >= 2:
                    recent_move = (hist[-1][1] - hist[0][1]) / hist[0][1] * 100
                    score = recent_move * (vol / 1e8)
                    if score > best_score:
                        best_score = score
                        best_sym = sym

        # Fallback: se nenhum momentum encontrado apos varios scans, pegar o mais volatil
        if not best_sym and candidates:
            if not hasattr(main_loop, 'no_signal_count'):
                main_loop.no_signal_count = 0
            main_loop.no_signal_count += 1
            if main_loop.no_signal_count >= 5:
                best_cand = max(candidates, key=lambda x: x[4])
                best_sym = best_cand[0]
                best_score = -1
                main_loop.no_signal_count = 0
                print(f"[{ts()}] [{EXCHANGE_NAME}] FALLBACK signal: {best_sym} (no momentum for 5 scans)", flush=True)
        else:
            if hasattr(main_loop, 'no_signal_count'):
                main_loop.no_signal_count = 0

        if best_sym:
            trade_size = get_trade_size()
            if trade_size < 1.0:
                print(f"[{ts()}] [{EXCHANGE_NAME}] Trade size muito baixo: {trade_size:.4f}", flush=True)
                time.sleep(5)
                continue

            print(f"[{ts()}] [{EXCHANGE_NAME}] MOMENTUM signal: {best_sym} score={best_score:.4f}", flush=True)
            execute_trade(best_sym, trade_size)
            last_trade_time = time.time()

    print(f"[{ts()}] [{EXCHANGE_NAME}] V8 finalizado. "
          f"PnL={session_pnl:.6f} Trades={session_trades} Wins={session_wins}", flush=True)
    log_ledger({
        'kind': 'session_end',
        'exchange': EXCHANGE_NAME,
        'session_pnl': round(session_pnl, 8),
        'session_trades': session_trades,
        'session_wins': session_wins,
        'ts': ts(),
    })


if __name__ == '__main__':
    load_markets()
    main_loop()
