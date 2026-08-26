#!/usr/bin/env python3
"""
V9 - Grid Ping-Pong Market Maker
Estrategia: comprar no bid com LIMIT, vender acima com LIMIT.
Captura spread e oscilacoes sem precisar prever direcao.
Bybit: 0% fee => grid = lucro puro.
Binance: 0.1% fee => grid mais largo para cobrir fees.
"""
import ccxt
import os
import sys
import json
import time
import math
import traceback
from datetime import datetime, timezone
import signal as sigmod

EXCHANGE_NAME = sys.argv[1] if len(sys.argv) > 1 else 'bybit'
SESSION_START = datetime.now(timezone.utc)

# ─── Config por exchange ───
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
    GRID_PCT = 0.0008
    BUY_MAX_WAIT = 30
    SELL_MAX_HOLD = 90
    REPOSITION_SEC = 3
    STOP_LOSS_PCT = 0.003
    FEE_PCT = 0.0
    DAILY_LOSS_LIMIT = 0.50
    MAX_CONSEC_LOSSES = 4
    LOSS_PAUSE_SEC = 30
    MIN_NOTIONAL = 0.0
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
    GRID_PCT = 0.0030
    BUY_MAX_WAIT = 45
    SELL_MAX_HOLD = 120
    REPOSITION_SEC = 3
    STOP_LOSS_PCT = 0.005
    FEE_PCT = 0.001
    DAILY_LOSS_LIMIT = 0.50
    MAX_CONSEC_LOSSES = 4
    LOSS_PAUSE_SEC = 30
    MIN_NOTIONAL = 5.0
else:
    print(f"Exchange desconhecida: {EXCHANGE_NAME}")
    sys.exit(1)

LEDGER_PATH = '/Agentic/ledger.jsonl'
COOLDOWN_SEC = 1

SCAN_SYMBOLS = [
    'DOGE/USDT', 'TRX/USDT', 'XRP/USDT', 'ADA/USDT',
    'SUI/USDT', 'APT/USDT', 'ARB/USDT', 'OP/USDT',
    'ENA/USDT', 'SEI/USDT', 'GRT/USDT', 'LDO/USDT',
    'NEAR/USDT', 'FET/USDT', 'INJ/USDT', 'JASMY/USDT',
    'GALA/USDT', 'FTM/USDT', 'ALGO/USDT', 'ONE/USDT',
    'ANKR/USDT', 'CHZ/USDT', 'MANA/USDT', 'SAND/USDT',
    'AXS/USDT', 'FIL/USDT', 'WLD/USDT', 'STX/USDT',
    'IMX/USDT', 'BAT/USDT', 'ZRX/USDT', 'CRV/USDT',
    'PEPE/USDT', 'ORDI/USDT', 'CFX/USDT', 'GAS/USDT',
]

running = True

def handle_signal(signum, frame):
    global running
    running = False

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
session_pnl = 0.0
session_trades = 0
session_wins = 0
consec_losses = 0


def ts():
    return datetime.now(timezone.utc).isoformat()


def log(msg):
    line = f"[{ts()}] [{EXCHANGE_NAME}] {msg}"
    print(line, flush=True)


def log_ledger(entry):
    try:
        with open(LEDGER_PATH, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    except Exception:
        pass


def load_markets():
    global available_symbols
    exchange.load_markets()
    available_symbols = []
    for s in SCAN_SYMBOLS:
        if s in exchange.markets:
            m = exchange.markets[s]
            if m.get('active', True) and m.get('spot', True):
                available_symbols.append(s)
    log(f"V9 Grid iniciado. Symbols={len(available_symbols)} Budget={BUDGET_USDT} Target={TARGET_PROFIT}")
    log(f"Grid={GRID_PCT*100:.2f}% SL={STOP_LOSS_PCT*100:.2f}% BuyWait={BUY_MAX_WAIT}s SellHold={SELL_MAX_HOLD}s Fee={FEE_PCT*100:.1f}%")


def get_usdt_free():
    try:
        bal = exchange.fetch_balance()
        return float(bal.get('USDT', {}).get('free', 0))
    except Exception:
        return 0


def get_base_free(sym):
    try:
        base = sym.split('/')[0]
        bal = exchange.fetch_balance()
        return float(bal.get(base, {}).get('free', 0))
    except Exception:
        return 0


def select_best_pair():
    """Seleciona par com melhor volume e spread apertado."""
    try:
        tickers = exchange.fetch_tickers(available_symbols)
    except Exception as e:
        log(f"fetchTickers erro: {e}")
        return None

    best = None
    best_score = 0

    for sym in available_symbols:
        t = tickers.get(sym)
        if not t:
            continue
        bid = float(t.get('bid', 0) or 0)
        ask = float(t.get('ask', 0) or 0)
        last = float(t.get('last', 0) or 0)
        vol = float(t.get('quoteVolume', 0) or 0)

        if bid <= 0 or ask <= 0 or last <= 0:
            continue
        if vol < 5e6:
            continue

        spread_pct = (ask - bid) / bid
        if spread_pct > 0.005:
            continue

        score = vol / 1e8
        if score > best_score:
            best_score = score
            best = (sym, bid, ask, last, vol)

    return best


def calc_qty(sym, price, trade_usdt):
    """Calcula qty respeitando min_qty, min_cost, precision, NOTIONAL."""
    m = exchange.markets.get(sym, {})
    min_qty = float(m.get('limits', {}).get('amount', {}).get('min', 0) or 0)
    min_cost = float(m.get('limits', {}).get('cost', {}).get('min', 0) or 0)
    qty_precision = int(m.get('precision', {}).get('amount', 8))
    price_precision = int(m.get('precision', {}).get('price', 8))

    min_notional = max(min_cost, MIN_NOTIONAL)
    raw_qty = trade_usdt / price
    qty = max(raw_qty, min_qty)

    if min_notional > 0 and qty * price < min_notional:
        qty = (min_notional / price) * 1.03

    qty = float(f"{qty:.{qty_precision}f}")

    if min_notional > 0 and qty * price < min_notional:
        return None, None, None

    return qty, qty_precision, price_precision


def buy_phase(sym, trade_usdt):
    """Coloca buy LIMIT no bid. Reprica se precisar. Retorna (qty, entry_price)."""
    order_id = None
    entry_price = 0.0
    start = time.time()
    last_reprice = 0

    while running:
        elapsed = time.time() - start
        if elapsed > BUY_MAX_WAIT:
            if order_id:
                try:
                    exchange.cancel_order(order_id, sym)
                except Exception:
                    pass
            log(f"BUY {sym} nao preencheu em {BUY_MAX_WAIT}s.")
            return 0, 0

        try:
            ticker = exchange.fetch_ticker(sym)
            bid = float(ticker.get('bid', 0) or 0)
            ask = float(ticker.get('ask', 0) or 0)
        except Exception:
            time.sleep(1)
            continue

        if bid <= 0:
            time.sleep(1)
            continue

        params = calc_qty(sym, bid, trade_usdt)
        if not params[0]:
            log(f"BUY {sym}: notional insuficiente para bid={bid}")
            time.sleep(2)
            continue
        qty, qty_prec, price_prec = params
        bid_rounded = float(f"{bid:.{price_prec}f}")

        need_reprice = False
        if order_id is None:
            need_reprice = True
        elif time.time() - last_reprice > REPOSITION_SEC:
            need_reprice = True

        if need_reprice:
            if order_id:
                try:
                    exchange.cancel_order(order_id, sym)
                    order_id = None
                except Exception:
                    pass

            try:
                order = exchange.create_order(sym, 'limit', 'buy', qty, bid_rounded)
                order_id = order.get('id')
                entry_price = bid_rounded
                last_reprice = time.time()
                log(f"BUY LIMIT {sym} qty={qty} @ {bid_rounded}")
            except Exception as e:
                log(f"BUY LIMIT erro: {e}")
                time.sleep(1)
                continue

        if order_id:
            try:
                status = exchange.fetch_order(order_id, sym)
                filled = float(status.get('filled', 0) or 0)
                st = status.get('status', '')
                if st == 'closed' or st == 'filled' or filled > 0:
                    avg = float(status.get('average', 0) or entry_price)
                    if filled > 0:
                        if st not in ('closed', 'filled'):
                            try:
                                exchange.cancel_order(order_id, sym)
                            except Exception:
                                pass
                        log(f"BUY FILLED {sym} qty={filled} @ {avg}")
                        return filled, avg
            except Exception as e:
                log(f"fetch_order buy erro: {e}")

        time.sleep(0.5)

    if order_id:
        try:
            exchange.cancel_order(order_id, sym)
        except Exception:
            pass
    return 0, 0


def sell_phase(sym, qty_bought, entry_price):
    """Coloca sell LIMIT acima do entry. Stop loss se cair. Retorna (exit_price, reason)."""
    target = entry_price * (1 + GRID_PCT)
    stop = entry_price * (1 - STOP_LOSS_PCT)

    m = exchange.markets.get(sym, {})
    qty_prec = int(m.get('precision', {}).get('amount', 8))
    price_prec = int(m.get('precision', {}).get('price', 8))

    target_rounded = float(f"{target:.{price_prec}f}")

    # Verifica saldo real do base asset
    base_free = get_base_free(sym)
    sell_qty = min(qty_bought, base_free)
    sell_qty = float(f"{(sell_qty * 0.9999):.{qty_prec}f}")

    if sell_qty <= 0:
        log(f"SELL {sym}: saldo base insuficiente (base_free={base_free})")
        return entry_price, "NO_BALANCE"

    order_id = None
    start = time.time()

    while running:
        elapsed = time.time() - start
        if elapsed > SELL_MAX_HOLD:
            if order_id:
                try:
                    exchange.cancel_order(order_id, sym)
                except Exception:
                    pass
            log(f"SELL {sym} TIMEOUT apos {SELL_MAX_HOLD}s. Market sell.")
            return _market_sell(sym, sell_qty, "TIMEOUT")

        try:
            ticker = exchange.fetch_ticker(sym)
            current = float(ticker.get('last', 0) or 0)
        except Exception:
            time.sleep(0.5)
            continue

        if current <= 0:
            time.sleep(0.5)
            continue

        # Stop loss
        if current <= stop:
            if order_id:
                try:
                    exchange.cancel_order(order_id, sym)
                except Exception:
                    pass
            log(f"SELL {sym} STOP LOSS @ {current} (entry={entry_price})")
            return _market_sell(sym, sell_qty, "SL")

        # Coloca sell limit
        if order_id is None:
            try:
                order = exchange.create_order(sym, 'limit', 'sell', sell_qty, target_rounded)
                order_id = order.get('id')
                log(f"SELL LIMIT {sym} qty={sell_qty} @ {target_rounded} (entry={entry_price})")
            except Exception as e:
                log(f"SELL LIMIT erro: {e} -- market sell")
                return _market_sell(sym, sell_qty, "MARKET_SELL")

        # Verifica fill
        if order_id:
            try:
                status = exchange.fetch_order(order_id, sym)
                filled = float(status.get('filled', 0) or 0)
                st = status.get('status', '')
                if st == 'closed' or st == 'filled' or filled >= sell_qty * 0.99:
                    avg = float(status.get('average', 0) or target_rounded)
                    log(f"SELL FILLED {sym} @ {avg}")
                    return avg, "TP"
            except Exception as e:
                log(f"fetch_order sell erro: {e}")

        time.sleep(0.5)

    if order_id:
        try:
            exchange.cancel_order(order_id, sym)
        except Exception:
            pass
    return entry_price, "SIGNAL_STOP"


def _market_sell(sym, qty, reason):
    """Venda a mercado com retry. Retorna (price, reason)."""
    for attempt in range(3):
        try:
            order = exchange.create_order(sym, 'market', 'sell', qty)
            fill = float(order.get('average', 0) or 0)
            if fill > 0:
                return fill, reason
        except Exception as e:
            log(f"SELL market tentativa {attempt+1} erro: {e}")
            if attempt < 2:
                time.sleep(0.5)
    log(f"SELL market FALHOU apos 3 tentativas.")
    return 0, f"{reason}_FAILED"


def main_loop():
    global session_pnl, session_trades, session_wins, consec_losses, running

    while running:
        if session_pnl >= TARGET_PROFIT:
            log(f"TARGET REACHED: {session_pnl:.4f} USDT")
            log_ledger({'kind': 'target_reached', 'exchange': EXCHANGE_NAME,
                        'session_pnl': round(session_pnl, 8), 'ts': ts()})
            break

        if session_pnl <= -DAILY_LOSS_LIMIT:
            log(f"DAILY LOSS LIMIT: {session_pnl:.4f}. PARANDO.")
            log_ledger({'kind': 'daily_loss_limit', 'exchange': EXCHANGE_NAME,
                        'session_pnl': round(session_pnl, 8), 'ts': ts()})
            break

        # Seleciona par
        pair = select_best_pair()
        if not pair:
            time.sleep(3)
            continue

        sym, bid, ask, last, vol = pair

        # Calcula trade size
        usdt_free = get_usdt_free()
        trade_size = min(usdt_free - RESERVE_USDT, BUDGET_USDT - RESERVE_USDT)
        if trade_size < 2.0:
            log(f"Trade size baixo: {trade_size:.4f} USDT free={usdt_free:.4f}")
            time.sleep(5)
            continue

        # NOTIONAL check: se trade_size < MIN_NOTIONAL, pula
        if MIN_NOTIONAL > 0 and trade_size < MIN_NOTIONAL * 1.1:
            log(f"Trade size {trade_size:.2f} < MIN_NOTIONAL {MIN_NOTIONAL}. Pulando {sym}.")
            time.sleep(3)
            continue

        log(f"Par: {sym} bid={bid} ask={ask} spread={((ask-bid)/bid*100):.3f}% vol={vol/1e6:.1f}M size={trade_size:.2f}")

        # Fase 1: Buy limit no bid
        filled_qty, entry_price = buy_phase(sym, trade_size)
        if filled_qty <= 0:
            time.sleep(COOLDOWN_SEC)
            continue

        # Fase 2: Sell limit acima do entry
        exit_price, exit_reason = sell_phase(sym, filled_qty, entry_price)

        # Calcula PnL
        if exit_price <= 0:
            exit_price = entry_price
            exit_reason = "NO_EXIT_PRICE"

        gross_pnl = (exit_price - entry_price) * filled_qty
        fees = entry_price * filled_qty * FEE_PCT + exit_price * filled_qty * FEE_PCT
        net_pnl = gross_pnl - fees
        win = net_pnl > 0

        session_trades += 1
        session_pnl += net_pnl
        if win:
            session_wins += 1
            consec_losses = 0
        else:
            consec_losses += 1

        entry_dict = {
            'ts': ts(),
            'exchange': EXCHANGE_NAME,
            'symbol': sym,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'qty': filled_qty,
            'exit_reason': exit_reason,
            'gross_pnl': round(gross_pnl, 8),
            'fees_usdt': round(fees, 8),
            'net_pnl': round(net_pnl, 8),
            'win': win,
            'session_pnl': round(session_pnl, 8),
            'session_trades': session_trades,
            'session_wins': session_wins,
            'version': 'V9',
        }
        log_ledger(entry_dict)

        wr = session_wins / session_trades * 100 if session_trades > 0 else 0
        log(f"EXIT {sym} {exit_reason} pnl={net_pnl:.6f} | sessao={session_pnl:.6f} trades={session_trades} wins={session_wins} ({wr:.0f}%)")

        if consec_losses >= MAX_CONSEC_LOSSES:
            log(f"{MAX_CONSEC_LOSSES} losses seguidas. Pausa {LOSS_PAUSE_SEC}s.")
            time.sleep(LOSS_PAUSE_SEC)
            consec_losses = 0

        time.sleep(COOLDOWN_SEC)

    log(f"V9 finalizado. PnL={session_pnl:.6f} Trades={session_trades} Wins={session_wins}")
    log_ledger({
        'kind': 'session_end',
        'exchange': EXCHANGE_NAME,
        'version': 'V9',
        'session_pnl': round(session_pnl, 8),
        'session_trades': session_trades,
        'session_wins': session_wins,
        'ts': ts(),
    })


if __name__ == '__main__':
    load_markets()
    main_loop()
