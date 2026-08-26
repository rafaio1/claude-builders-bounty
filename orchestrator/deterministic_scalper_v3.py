#!/usr/bin/env python3
"""
Bot de scalping deterministico v3 - Bybit e Binance.
Corrigido: busca saldo real apos compra, ajusta qty na venda,
filtra simbolos por preco adequado ao capital.
"""
import ccxt, os, sys, json, time, signal, traceback, math
from datetime import datetime, timezone

EXCHANGE_NAME = sys.argv[1] if len(sys.argv) > 1 else 'bybit'

# Carrega credenciais
if EXCHANGE_NAME == 'bybit':
    from_env = {}
    with open('/root/.automaton/bybit-murre.env') as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                from_env[k.strip()] = v.strip()
    API_KEY = from_env.get('BYBIT_REAL_API_KEY', '')
    API_SECRET = from_env.get('BYBIT_REAL_API_SECRET', '')
    BUDGET_USDT = 16.0
    RESERVE_USDT = 5.0
    TARGET_PROFIT = 10.0
elif EXCHANGE_NAME == 'binance':
    from_env = {}
    with open('/Agentic/.env') as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                from_env[k.strip()] = v.strip()
    API_KEY = from_env.get('BINANCE_API_KEY', '')
    API_SECRET = from_env.get('BINANCE_API_SECRET', '')
    BUDGET_USDT = 14.0
    RESERVE_USDT = 2.0
    TARGET_PROFIT = 20.0
else:
    print(f"Unknown exchange: {EXCHANGE_NAME}")
    sys.exit(1)

TP_PCT = 0.005
SL_PCT = 0.005
MAX_HOLD_SEC = 120
COOLDOWN_SEC = 20
MAX_CONSEC_LOSSES = 3
SCAN_INTERVAL = 5
LEDGER_PATH = '/Agentic/ledger.jsonl'

# Simbolos com preco baixo suficiente para capital pequeno
SCAN_SYMBOLS = [
    'XRP/USDT', 'DOGE/USDT', 'ADA/USDT', 'TRX/USDT',
    'SUI/USDT', 'APT/USDT', 'INJ/USDT', 'OP/USDT', 'ARB/USDT',
    'PEPE/USDT', 'WIF/USDT', 'ENA/USDT', 'TIA/USDT',
    'FET/USDT', 'SEI/USDT', 'DYDX/USDT', 'GRT/USDT', 'LDO/USDT',
    'NEAR/USDT', 'AVAX/USDT', 'LINK/USDT', 'SOL/USDT',
]

exchange_cls = ccxt.bybit if EXCHANGE_NAME == 'bybit' else ccxt.binance
exchange = exchange_cls({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
    'timeout': 15000,
    'options': {'defaultType': 'spot', 'fetchOpenOrders': {'warnWithoutSymbol': False}}
})
exchange.load_markets()

running = True
cooldown_until = 0
consec_losses = {}

def log_ledger(entry):
    with open(LEDGER_PATH, 'a') as f:
        f.write(json.dumps(entry) + '\n')
    print(f"[LEDGER] {json.dumps(entry)}", flush=True)

def get_usdt_free():
    bal = exchange.fetch_balance()
    return float(bal.get('USDT', {}).get('free', 0))

def get_trade_size():
    free = get_usdt_free()
    available = free - RESERVE_USDT
    if available < 5:
        return 0
    size = min(max(available * 0.50, 5.0), 10.0)
    return round(size, 2)

def get_realized_pnl(start_time):
    total_pnl = 0.0
    since = int(start_time.timestamp() * 1000)
    for sym in SCAN_SYMBOLS:
        if sym not in exchange.markets:
            continue
        try:
            trades = exchange.fetch_my_trades(sym, since=since, limit=50)
            if not trades:
                continue
            buys = [t for t in trades if t['side'] == 'buy']
            sells = [t for t in trades if t['side'] == 'sell']
            if not sells:
                continue
            total_sell_value = sum(t['cost'] for t in sells)
            total_sell_qty = sum(t['amount'] for t in sells)
            total_buy_value = sum(t['cost'] for t in buys)
            total_buy_qty = sum(t['amount'] for t in buys)
            if total_buy_qty > 0:
                avg_buy_price = total_buy_value / total_buy_qty
                total_pnl += (total_sell_value - avg_buy_price * total_sell_qty)
                total_fees = sum(float(t.get('fee', {}).get('cost', 0) or 0) for t in trades)
                total_pnl -= total_fees
        except Exception:
            pass
    return total_pnl

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        if diff > 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))
    gains = gains[-period:]
    losses = losses[-period:]
    avg_gain = sum(gains) / period if gains else 0
    avg_loss = sum(losses) / period if losses else 0.0001
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def find_entry_signal(symbol):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, '1m', limit=30)
        if len(ohlcv) < 15:
            return False, 0
        closes = [c[4] for c in ohlcv]
        rsi = calc_rsi(closes, 14)
        last_price = closes[-1]
        sma10 = sum(closes[-10:]) / 10
        if rsi < 50 and last_price < sma10:
            return True, last_price
        if rsi < 35:
            return True, last_price
    except Exception:
        pass
    return False, 0

def adjust_qty(symbol, qty, entry_price):
    market = exchange.markets.get(symbol)
    if not market:
        return 0, False
    amount_prec = market.get('precision', {}).get('amount', None)
    if isinstance(amount_prec, float) and amount_prec > 0:
        qty = math.floor(qty / amount_prec) * amount_prec
    elif isinstance(amount_prec, int):
        qty = round(qty, amount_prec)
    min_amt = market.get('limits', {}).get('amount', {}).get('min', 0)
    if min_amt and qty < min_amt:
        return 0, False
    min_cost = market.get('limits', {}).get('cost', {}).get('min', 0)
    if min_cost and qty * entry_price < min_cost:
        return 0, False
    qty = round(qty, 8)
    return qty, True

def get_coin_balance(coin):
    try:
        bal = exchange.fetch_balance()
        return float(bal.get(coin, {}).get('free', 0))
    except Exception:
        return 0.0

def execute_trade(symbol, entry_price):
    global cooldown_until, consec_losses

    trade_usdt = get_trade_size()
    if trade_usdt < 5:
        print(f"  Saldo insuficiente para trade", flush=True)
        return None

    qty = trade_usdt / entry_price
    qty, ok = adjust_qty(symbol, qty, entry_price)
    if not ok or qty <= 0:
        print(f"  Qty invalida para {symbol} (preco={entry_price}, trade_usdt={trade_usdt})", flush=True)
        return None

    tp_price = entry_price * (1 + TP_PCT)
    sl_price = entry_price * (1 - SL_PCT)
    print(f"  [{EXCHANGE_NAME}] BUY {symbol} qty={qty} @ ~{entry_price} | TP={tp_price} SL={sl_price}", flush=True)

    coin = symbol.split('/')[0]

    try:
        buy_order = exchange.create_order(symbol, 'market', 'buy', qty)
        if not buy_order:
            print(f"  BUY returned None", flush=True)
            return None
        fill_price = float(buy_order.get('average') or buy_order.get('price') or entry_price)
        buy_fee = float((buy_order.get('fee') or {}).get('cost', 0) or 0)
        buy_fee_curr = (buy_order.get('fee') or {}).get('currency', '') or ''
        print(f"  BUY filled: qty={qty} @ {fill_price} fee={buy_fee} {buy_fee_curr}", flush=True)
    except Exception as e:
        print(f"  BUY error: {e}", flush=True)
        traceback.print_exc()
        return None

    time.sleep(1)

    actual_balance = get_coin_balance(coin)
    if actual_balance > 0:
        sell_qty, ok_sell = adjust_qty(symbol, actual_balance, fill_price)
        if not ok_sell or sell_qty <= 0:
            sell_qty = qty
            print(f"  Usando qty original para sell: {sell_qty}", flush=True)
        else:
            print(f"  Saldo real de {coin}: {actual_balance} -> sell_qty={sell_qty}", flush=True)
    else:
        sell_qty = qty
        print(f"  Saldo de {coin} e zero, usando qty do order: {sell_qty}", flush=True)

    tp_price = fill_price * (1 + TP_PCT)
    sl_price = fill_price * (1 - SL_PCT)

    entry_time = time.time()
    exit_reason = None
    exit_price = fill_price
    check_interval = 3

    while running and (time.time() - entry_time) < MAX_HOLD_SEC:
        try:
            ticker = exchange.fetch_ticker(symbol)
            current = float(ticker['last'])
            elapsed = time.time() - entry_time

            if current >= tp_price:
                exit_reason = 'TP'
                exit_price = current
                break
            elif current <= sl_price:
                exit_reason = 'SL'
                exit_price = current
                break

            if int(elapsed) % 15 == 0 and int(elapsed) > 0:
                pnl_pct = (current - fill_price) / fill_price * 100
                print(f"  [{int(elapsed)}s] {symbol} price={current} pnl={pnl_pct:.2f}%", flush=True)

            time.sleep(check_interval)
        except Exception as e:
            print(f"  Monitor error: {e}", flush=True)
            time.sleep(5)
            continue

    if not exit_reason:
        exit_reason = 'TIMEOUT'

    try:
        sell_order = exchange.create_order(symbol, 'market', 'sell', sell_qty)
        if sell_order:
            sell_fill = float(sell_order.get('average') or sell_order.get('price') or exit_price)
            sell_fee = float((sell_order.get('fee') or {}).get('cost', 0) or 0)
            sell_fee_curr = (sell_order.get('fee') or {}).get('currency', '') or ''
            print(f"  SELL filled: qty={sell_qty} @ {sell_fill} reason={exit_reason} fee={sell_fee} {sell_fee_curr}", flush=True)
            exit_price = sell_fill
        else:
            print(f"  SELL returned None, tentando novamente...", flush=True)
            time.sleep(2)
            sell_order = exchange.create_order(symbol, 'market', 'sell', sell_qty)
            sell_fill = float(sell_order.get('average') or sell_order.get('price') or exit_price) if sell_order else exit_price
            exit_price = sell_fill
    except Exception as e:
        print(f"  SELL error: {e}", flush=True)
        traceback.print_exc()
        time.sleep(2)
        try:
            actual_bal = get_coin_balance(coin)
            if actual_bal > 0:
                adj_qty, _ = adjust_qty(symbol, actual_bal, exit_price)
                if adj_qty > 0:
                    sell_order = exchange.create_order(symbol, 'market', 'sell', adj_qty)
                    if sell_order:
                        exit_price = float(sell_order.get('average') or sell_order.get('price') or exit_price)
                        print(f"  SELL retry OK: @ {exit_price}", flush=True)
        except Exception as e2:
            print(f"  SELL retry failed: {e2}", flush=True)

    gross_pnl = (exit_price - fill_price) * sell_qty
    est_fee_usdt = 0
    if buy_fee_curr == 'USDT':
        est_fee_usdt += buy_fee
    if 'sell_fee_curr' in locals() and sell_fee_curr == 'USDT':
        est_fee_usdt += sell_fee
    if buy_fee_curr and buy_fee_curr != 'USDT' and buy_fee > 0:
        est_fee_usdt += buy_fee * fill_price
    if 'sell_fee_curr' in locals() and sell_fee_curr and sell_fee_curr != 'USDT' and sell_fee > 0:
        est_fee_usdt += sell_fee * exit_price

    net_pnl = gross_pnl - est_fee_usdt
    is_win = net_pnl > 0

    print(f"  RESULT: {symbol} pnl_gross={gross_pnl:.6f} fees={est_fee_usdt:.6f} pnl_net={net_pnl:.6f} {'WIN' if is_win else 'LOSS'}", flush=True)

    log_ledger({
        'ts': datetime.now(timezone.utc).isoformat(),
        'exchange': EXCHANGE_NAME,
        'symbol': symbol,
        'entry_price': fill_price,
        'exit_price': exit_price,
        'qty': sell_qty,
        'exit_reason': exit_reason,
        'gross_pnl': round(gross_pnl, 6),
        'fees_usdt': round(est_fee_usdt, 6),
        'net_pnl': round(net_pnl, 6),
        'win': is_win,
    })

    if not is_win:
        consec_losses[symbol] = consec_losses.get(symbol, 0) + 1
        cooldown_until = time.time() + COOLDOWN_SEC
        if consec_losses[symbol] >= MAX_CONSEC_LOSSES:
            print(f"  {symbol} max perdas, removendo do scan", flush=True)
            if symbol in SCAN_SYMBOLS:
                SCAN_SYMBOLS.remove(symbol)
    else:
        consec_losses[symbol] = 0

    return is_win

def signal_handler(sig, frame):
    global running
    print("\n[STOP] Encerrando...", flush=True)
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

session_start = datetime.now(timezone.utc)
print(f"[{EXCHANGE_NAME.upper()}] Bot v3 iniciado em {session_start.isoformat()}", flush=True)
print(f"  Budget: {BUDGET_USDT} USDT | Reserva: {RESERVE_USDT} USDT | Meta: +{TARGET_PROFIT} USDT", flush=True)
print(f"  TP={TP_PCT*100}% SL={SL_PCT*100}% MaxHold={MAX_HOLD_SEC}s Cooldown={COOLDOWN_SEC}s", flush=True)

print("Limpando ordens abertas...", flush=True)
for sym in list(SCAN_SYMBOLS):
    try:
        for o in exchange.fetch_open_orders(sym):
            exchange.cancel_order(o['id'], sym)
            print(f"  Cancelled {o['id']} on {sym}", flush=True)
    except Exception:
        pass

cycle = 0
total_pnl = 0.0

while running:
    cycle += 1
    try:
        total_pnl = get_realized_pnl(session_start)
        pct = total_pnl / TARGET_PROFIT * 100 if TARGET_PROFIT > 0 else 0
        print(f"\n[Cycle {cycle}] PnL realizado: {total_pnl:.6f} USDT | Meta: {TARGET_PROFIT} USDT | Progress: {pct:.1f}%", flush=True)

        if total_pnl >= TARGET_PROFIT:
            print(f"\n*** META ATINGIDA: {total_pnl:.6f} >= {TARGET_PROFIT} USDT ***", flush=True)
            print(f"*** CONFIRMADO via fetch_my_trades ***", flush=True)
            break

        if time.time() < cooldown_until:
            remaining = int(cooldown_until - time.time())
            print(f"  Cooldown ativo, {remaining}s restantes", flush=True)
            time.sleep(SCAN_INTERVAL)
            continue

        usdt_free = get_usdt_free()
        trade_size = get_trade_size()
        if trade_size < 5:
            print(f"  Saldo insuficiente: livre={usdt_free:.2f}", flush=True)
            time.sleep(SCAN_INTERVAL)
            continue

        found_trade = False
        for sym in list(SCAN_SYMBOLS):
            if sym not in exchange.markets:
                continue
            try:
                ticker = exchange.fetch_ticker(sym)
                price = float(ticker['last'])
                # Filtrar: trade_size deve comprar pelo menos 1 unidade
                if price > 0 and trade_size / price < 1:
                    continue
                has_signal, signal_price = find_entry_signal(sym)
                if has_signal:
                    print(f"  SIGNAL: {sym} RSI<50, price={signal_price}", flush=True)
                    result = execute_trade(sym, signal_price)
                    found_trade = True
                    break
            except Exception:
                continue
            if not running:
                break

        if not found_trade:
            print(f"  Nenhum sinal encontrado", flush=True)

        time.sleep(SCAN_INTERVAL)

    except Exception as e:
        print(f"  Erro no ciclo: {e}", flush=True)
        traceback.print_exc()
        time.sleep(5)

print(f"\n{'='*50}", flush=True)
print(f"RELATORIO FINAL - {EXCHANGE_NAME.upper()}", flush=True)
print(f"  PnL realizado: {total_pnl:.6f} USDT", flush=True)
print(f"  Meta: {TARGET_PROFIT} USDT", flush=True)
print(f"  Status: {'ATINGIDO' if total_pnl >= TARGET_PROFIT else 'NAO ATINGIDO'}", flush=True)
print(f"{'='*50}", flush=True)
