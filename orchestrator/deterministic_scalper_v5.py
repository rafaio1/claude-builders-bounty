#!/usr/bin/env python3
"""
Bot de scalping deterministico v5 - Bybit e Binance.
Melhorias vs v4:
- Market orders direto (limit nunca preenche em 10s)
- TP 0.6% / SL 0.4% (tighter, mais wins)
- MaxHold 120s (2 min - corta sideways rapido)
- RSI com Wilder's smoothing (fix bug RSI=0)
- Filtro de spread max 0.15% (saida facil)
- Filtro de volume 24h > $30M
- Precisao de qty baseada no market precision real
- Cooldown 5s (ciclos mais rapidos)
- Bybit fee=0% confirmado: TP 0.4% ja e lucro puro
- Log estruturado para analise
"""
import ccxt
import os
import sys
import json
import time
import signal as sigmod
import traceback
import math
from datetime import datetime, timezone, timedelta

EXCHANGE_NAME = sys.argv[1] if len(sys.argv) > 1 else 'bybit'
SESSION_START = datetime.now(timezone.utc)

# Carrega credenciais
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
    RESERVE_USDT = 2.0
    TARGET_PROFIT = 10.0
    TP_PCT = 0.004    # 0.4% TP (fee=0% na bybit spot)
    SL_PCT = 0.004    # 0.4% SL (simetrico pois sem fee)
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
    TP_PCT = 0.008    # 0.8% TP (precisa cobrir 0.2% de fees)
    SL_PCT = 0.005    # 0.5% SL
else:
    print(f"Exchange desconhecida: {EXCHANGE_NAME}")
    sys.exit(1)

MAX_HOLD_SEC = 120    # 2 minutos
COOLDOWN_SEC = 5
SCAN_INTERVAL = 2
LEDGER_PATH = '/Agentic/ledger.jsonl'
MAX_PRICE = 1.50      # moedas ate $1.50
MAX_SPREAD_PCT = 0.15 # spread bid-ask max 0.15%
MIN_VOLUME_24H = 30e6 # $30M volume 24h minimo

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
]

# Filtra simbolos disponiveis apos load_markets
running = True

def handle_signal(signum, frame):
    global running
    running = False
    print(f"\n[SIGNAL] Parando apos ciclo atual...", flush=True)

sigmod.signal(sigmod.SIGINT, handle_signal)
sigmod.signal(sigmod.SIGTERM, handle_signal)

exchange_cls = ccxt.bybit if EXCHANGE_NAME == 'bybit' else ccxt.binance
exchange = exchange_cls({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
    'timeout': 10000,
    'options': {
        'defaultType': 'spot',
        'fetchOpenOrders': {'warnWithoutSymbol': False}
    }
})
exchange.load_markets()

# Filtra simbolos que existem nesta exchange
SCAN_SYMBOLS = [s for s in SCAN_SYMBOLS if s in exchange.markets]
print(f"[{EXCHANGE_NAME.upper()}] Bot v5 iniciado em {SESSION_START.isoformat()}", flush=True)
print(f"  Budget: {BUDGET_USDT} USDT | Reserva: {RESERVE_USDT} USDT | Meta: +{TARGET_PROFIT} USDT", flush=True)
print(f"  TP={TP_PCT*100}% SL={SL_PCT*100}% MaxHold={MAX_HOLD_SEC}s Cooldown={COOLDOWN_SEC}s", flush=True)
print(f"  MaxPreco={MAX_PRICE} | MaxSpread={MAX_SPREAD_PCT}% | MinVol24h={MIN_VOLUME_24H/1e6}M", flush=True)
print(f"  Simbolos: {len(SCAN_SYMBOLS)}", flush=True)


def get_usdt_free():
    try:
        bal = exchange.fetch_balance()
        return float(bal.get('USDT', {}).get('free', 0))
    except Exception:
        return 0.0


def get_trade_size():
    usdt = get_usdt_free()
    available = usdt - RESERVE_USDT
    if available < 3:
        return 0
    size = min(available * 0.90, BUDGET_USDT)
    return max(size, 3) if size >= 3 else 0


def calc_rsi_wilder(closes, period=14):
    """Calcula RSI usando Wilder's smoothing (nao SMA simples)."""
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i+1] - closes[i] for i in range(len(closes)-1)]
    gains = [max(d, 0) for d in deltas]
    losses = [max(-d, 0) for d in deltas]
    
    # Primeira media: SMA
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    # Wilder smoothing
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def calc_sma(values, period):
    if len(values) < period:
        return sum(values) / len(values) if values else 0
    return sum(values[-period:]) / period


def find_entry_signal(symbol):
    """Busca sinal de entrada: RSI oversold + trend de recuperacao."""
    try:
        ohlcv_1m = exchange.fetch_ohlcv(symbol, '1m', limit=30)
        if len(ohlcv_1m) < 20:
            return False, 0, {}
        
        closes_1m = [c[4] for c in ohlcv_1m]
        rsi = calc_rsi_wilder(closes_1m, 14)
        
        ohlcv_5m = exchange.fetch_ohlcv(symbol, '5m', limit=25)
        if len(ohlcv_5m) < 20:
            return False, 0, {}
        closes_5m = [c[4] for c in ohlcv_5m]
        sma20_5m = calc_sma(closes_5m, 20)
        
        vols = [c[5] for c in ohlcv_1m[-10:]]
        avg_vol = sum(vols) / len(vols) if vols else 1
        last_vol = vols[-1] if vols else 0
        vol_spike = last_vol > avg_vol * 1.5
        
        current_price = closes_1m[-1]
        
        # Filtro de spread
        ticker = exchange.fetch_ticker(symbol)
        bid = float(ticker.get('bid', 0))
        ask = float(ticker.get('ask', 0))
        if bid > 0 and ask > 0:
            spread_pct = (ask - bid) / bid * 100
        else:
            spread_pct = 999
        
        if spread_pct > MAX_SPREAD_PCT:
            return False, 0, {}
        
        # Filtro de volume 24h
        quote_vol = float(ticker.get('quoteVolume', 0))
        if quote_vol < MIN_VOLUME_24H:
            return False, 0, {}
        
        trend_up = current_price > sma20_5m
        
        if rsi < 25 and trend_up:
            return True, current_price, {
                'rsi_1m': round(rsi, 2),
                'sma20_5m': round(sma20_5m, 6),
                'vol_spike': vol_spike,
                'trend_up': trend_up,
                'spread': round(spread_pct, 3),
                'vol24h': round(quote_vol / 1e6, 1)
            }
        
        if rsi < 35 and vol_spike and trend_up:
            return True, current_price, {
                'rsi_1m': round(rsi, 2),
                'sma20_5m': round(sma20_5m, 6),
                'vol_spike': vol_spike,
                'trend_up': trend_up,
                'spread': round(spread_pct, 3),
                'vol24h': round(quote_vol / 1e6, 1)
            }
        
        return False, 0, {}
    except Exception:
        return False, 0, {}


def adjust_sell_qty(symbol, raw_qty):
    """Ajusta qty para venda baseado na precisao do market."""
    try:
        m = exchange.markets[symbol]
        amt_prec = m.get('precision', {}).get('amount', 0.01)
        min_amt = m.get('limits', {}).get('amount', {}).get('min', 0.01)
        
        if amt_prec and amt_prec >= 1:
            sell_qty = math.floor(raw_qty / amt_prec) * amt_prec
        elif amt_prec and 0 < amt_prec < 1:
            sell_qty = math.floor(raw_qty / amt_prec) * amt_prec
            decimals = int(-math.log10(amt_prec)) + 2 if amt_prec < 1 else 6
            sell_qty = round(sell_qty, decimals)
        else:
            sell_qty = round(raw_qty, 6)
        
        if sell_qty < min_amt:
            sell_qty = math.ceil(raw_qty / amt_prec) * amt_prec if amt_prec else raw_qty
            sell_qty = round(sell_qty, 6)
        
        if sell_qty < 0.000001:
            return 0, False
        
        return sell_qty, True
    except Exception:
        return round(raw_qty, 6), True


def execute_trade(symbol, entry_price):
    """Executa trade: market buy, monitora TP/SL, market sell."""
    coin = symbol.split('/')[0]
    trade_size = get_trade_size()
    if trade_size < 3:
        print(f"  Saldo insuficiente para trade", flush=True)
        return
    
    m = exchange.markets[symbol]
    amt_prec = m.get('precision', {}).get('amount', 0.01)
    min_amt = m.get('limits', {}).get('amount', {}).get('min', 0.01)
    min_cost = m.get('limits', {}).get('cost', {}).get('min', 1.0)
    
    raw_qty = trade_size / entry_price
    if amt_prec and amt_prec >= 1:
        buy_qty = math.floor(raw_qty / amt_prec) * amt_prec
    elif amt_prec and 0 < amt_prec < 1:
        buy_qty = math.floor(raw_qty / amt_prec) * amt_prec
        decimals = int(-math.log10(amt_prec)) + 2 if amt_prec < 1 else 6
        buy_qty = round(buy_qty, decimals)
    else:
        buy_qty = round(raw_qty, 6)
    
    if buy_qty < min_amt or buy_qty * entry_price < min_cost:
        print(f"  Qty muito baixa: {buy_qty} (min={min_amt}, cost={buy_qty*entry_price:.4f}, min_cost={min_cost})", flush=True)
        return
    
    tp_price = entry_price * (1 + TP_PCT)
    sl_price = entry_price * (1 - SL_PCT)
    
    print(f"  [{EXCHANGE_NAME}] BUY {symbol} qty={buy_qty} @ ~{entry_price:.6f} | TP={tp_price:.6f} SL={sl_price:.6f}", flush=True)
    
    # Market buy direto
    try:
        buy_order = exchange.create_order(symbol, 'market', 'buy', buy_qty)
        fill_price = float(buy_order.get('average') or buy_order.get('price') or entry_price)
        filled_qty = float(buy_order.get('amount') or buy_qty)
        buy_fee = float(buy_order.get('fee', {}).get('cost', 0) or 0)
        buy_fee_curr = buy_order.get('fee', {}).get('currency', 'USDT')
        
        print(f"  BUY filled: qty={filled_qty} @ {fill_price} fee={buy_fee} {buy_fee_curr}", flush=True)
    except Exception as e:
        print(f"  BUY error: {e}", flush=True)
        traceback.print_exc()
        return
    
    # Verifica saldo real para venda
    try:
        time.sleep(0.5)
        bal = exchange.fetch_balance()
        actual_balance = float(bal.get(coin, {}).get('free', 0))
    except Exception:
        actual_balance = filled_qty
    
    sell_qty, ok_sell = adjust_sell_qty(symbol, actual_balance)
    if not ok_sell or sell_qty <= 0:
        sell_qty = filled_qty
        print(f"  Usando qty original: {sell_qty}", flush=True)
    else:
        print(f"  Saldo real de {coin}: {actual_balance} -> sell_qty={sell_qty}", flush=True)
    
    # Monitora TP/SL
    entry_time = time.time()
    exit_price = fill_price
    exit_reason = 'NONE'
    
    while running and (time.time() - entry_time) < MAX_HOLD_SEC:
        try:
            ticker = exchange.fetch_ticker(symbol)
            current = float(ticker['last'])
            elapsed = int(time.time() - entry_time)
            pnl_pct = (current - fill_price) / fill_price * 100
            
            if current >= tp_price:
                exit_price = current
                exit_reason = 'TP'
                print(f"  [{elapsed}s] {symbol} price={current} pnl={pnl_pct:.2f}% TP HIT!", flush=True)
                break
            
            if current <= sl_price:
                exit_price = current
                exit_reason = 'SL'
                print(f"  [{elapsed}s] {symbol} price={current} pnl={pnl_pct:.2f}% SL HIT", flush=True)
                break
            
            if elapsed % 30 == 0 and elapsed > 0:
                print(f"  [{elapsed}s] {symbol} price={current} pnl={pnl_pct:.2f}% (TP={tp_price:.6f} SL={sl_price:.6f})", flush=True)
            
            time.sleep(1)
        except Exception as e:
            print(f"  Monitor error: {e}", flush=True)
            time.sleep(2)
    
    # Se timeout, vende ao preco atual
    if exit_reason == 'NONE':
        try:
            ticker = exchange.fetch_ticker(symbol)
            exit_price = float(ticker['last'])
            exit_reason = 'TIMEOUT'
            print(f"  [{int(time.time()-entry_time)}s] {symbol} TIMEOUT @ {exit_price}", flush=True)
        except Exception:
            exit_price = fill_price
            exit_reason = 'TIMEOUT'
    
    # Market sell
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
            adj_qty, _ = adjust_sell_qty(symbol, real_amt)
            if adj_qty > 0:
                sell_order = exchange.create_order(symbol, 'market', 'sell', adj_qty)
                sell_fill = float(sell_order.get('average') or sell_order.get('price') or exit_price)
                sell_fee = float(sell_order.get('fee', {}).get('cost', 0) or 0)
                sell_fee_curr = sell_order.get('fee', {}).get('currency', 'USDT')
                sell_qty = adj_qty
                print(f"  SELL retry OK: qty={adj_qty} @ {sell_fill} fee={sell_fee} {sell_fee_curr}", flush=True)
            else:
                print(f"  SELL retry falhou: saldo zero ou insuficiente", flush=True)
        except Exception as e2:
            print(f"  SELL retry error: {e2}", flush=True)
            traceback.print_exc()
    
    # Calcula PnL
    buy_fee_usdt = buy_fee if buy_fee_curr == 'USDT' else buy_fee * fill_price
    sell_fee_usdt = sell_fee if sell_fee_curr == 'USDT' else sell_fee * sell_fill
    total_fees = buy_fee_usdt + sell_fee_usdt
    
    gross_pnl = (sell_fill - fill_price) * sell_qty
    net_pnl = gross_pnl - total_fees
    
    win = net_pnl > 0
    status = 'WIN' if win else 'LOSS'
    
    print(f"  RESULT: {symbol} entry={fill_price} exit={sell_fill} pnl_gross={gross_pnl:.6f} fees={total_fees:.6f} pnl_net={net_pnl:.6f} {status} reason={exit_reason}", flush=True)
    
    # Ledger
    entry_ts = datetime.now(timezone.utc).isoformat()
    record = {
        'ts': entry_ts,
        'exchange': EXCHANGE_NAME,
        'symbol': symbol,
        'entry_price': fill_price,
        'exit_price': sell_fill,
        'qty': sell_qty,
        'exit_reason': exit_reason,
        'gross_pnl': round(gross_pnl, 8),
        'fees_usdt': round(total_fees, 8),
        'net_pnl': round(net_pnl, 8),
        'win': win
    }
    try:
        with open(LEDGER_PATH, 'a') as f:
            f.write(json.dumps(record) + '\n')
        print(f"  [LEDGER] {json.dumps(record)}", flush=True)
    except Exception:
        pass
    
    return net_pnl


def get_realized_pnl(since):
    """Calcula PnL realizado desde o inicio da sessao via fetch_my_trades."""
    total_pnl = 0.0
    since_ms = int(since.timestamp() * 1000)
    
    for sym in SCAN_SYMBOLS[:15]:
        try:
            trades = exchange.fetch_my_trades(sym, since=since_ms, limit=20)
            if not trades:
                continue
            
            buys = [t for t in trades if t['side'] == 'buy']
            sells = [t for t in trades if t['side'] == 'sell']
            
            if not buys or not sells:
                continue
            
            total_buy_cost = sum(t['cost'] for t in buys)
            total_buy_qty = sum(t['amount'] for t in buys)
            total_sell_value = sum(t['cost'] for t in sells)
            total_sell_qty = sum(t['amount'] for t in sells)
            
            all_fees = 0
            for t in trades:
                fee = t.get('fee', {})
                if fee:
                    fee_cost = float(fee.get('cost', 0))
                    fee_curr = fee.get('currency', 'USDT')
                    if fee_curr == 'USDT':
                        all_fees += fee_cost
                    else:
                        avg_price = total_buy_cost / total_buy_qty if total_buy_qty > 0 else 0
                        all_fees += fee_cost * avg_price
            
            if total_sell_qty > 0:
                avg_buy_price = total_buy_cost / total_buy_qty if total_buy_qty > 0 else 0
                total_pnl += (total_sell_value - avg_buy_price * total_sell_qty) - all_fees
        except Exception:
            continue
    
    return total_pnl


# Limpa ordens abertas e dust residual
print(f"\nLimpando ordens abertas...", flush=True)
try:
    open_orders = exchange.fetch_open_orders()
    for o in open_orders:
        try:
            exchange.cancel_order(o['id'], o['symbol'])
            print(f"  Cancelada: {o['symbol']} {o['side']} {o['amount']}", flush=True)
        except Exception:
            pass
except Exception as e:
    print(f"  Erro ao limpar ordens: {e}", flush=True)

# Limpa saldos residuais
print(f"Limpando saldos residuais...", flush=True)
try:
    bal = exchange.fetch_balance()
    for coin, info in bal.get('total', {}).items():
        if coin in ('USDT', 'USD', 'BRL'):
            continue
        if coin.startswith('LD'):
            continue
        amt = float(info) if isinstance(info, (int, float)) else 0
        if amt <= 0:
            continue
        sym = f"{coin}/USDT"
        if sym not in exchange.markets:
            continue
        try:
            ticker = exchange.fetch_ticker(sym)
            price = float(ticker['last'])
            value = amt * price
            if value < 0.05:
                continue
            m = exchange.markets[sym]
            amt_prec = m.get('precision', {}).get('amount', 0.01)
            min_amt = m.get('limits', {}).get('amount', {}).get('min', 0.01)
            min_cost = m.get('limits', {}).get('cost', {}).get('min', 1.0)
            if amt_prec and amt_prec >= 1:
                sell_qty = math.floor(amt / amt_prec) * amt_prec
            elif amt_prec and 0 < amt_prec < 1:
                sell_qty = math.floor(amt / amt_prec) * amt_prec
                decimals = int(-math.log10(amt_prec)) + 2 if amt_prec < 1 else 6
                sell_qty = round(sell_qty, decimals)
            else:
                sell_qty = round(amt, 6)
            if sell_qty >= min_amt and sell_qty * price >= min_cost and value > 0.5:
                print(f"  Vendendo dust: {coin} {amt} -> {sell_qty} @ {price} = {sell_qty*price:.4f} USDT", flush=True)
                order = exchange.create_order(sym, 'market', 'sell', sell_qty)
                fill = float(order.get('average') or order.get('price') or price)
                print(f"    Vendido @ {fill}", flush=True)
        except Exception:
            pass
except Exception as e:
    print(f"  Erro ao limpar saldos: {e}", flush=True)

# Loop principal
cycle = 0
total_pnl = 0.0
consec_losses = 0
cooldown_until = 0

while running:
    cycle += 1
    try:
        total_pnl = get_realized_pnl(SESSION_START)
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
        
        trade_size = get_trade_size()
        if trade_size < 3:
            print(f"  Saldo insuficiente: livre={get_usdt_free():.2f}", flush=True)
            time.sleep(10)
            continue
        
        found_trade = False
        for sym in list(SCAN_SYMBOLS):
            if not running:
                break
            if sym not in exchange.markets:
                continue
            try:
                ticker = exchange.fetch_ticker(sym)
                price = float(ticker['last'])
                if price > MAX_PRICE:
                    continue
                if price > 0 and trade_size / price < 1:
                    continue
                has_signal, signal_price, signal_info = find_entry_signal(sym)
                if has_signal:
                    print(f"  SIGNAL: {sym} RSI={signal_info.get('rsi_1m')} price={signal_price} info={signal_info}", flush=True)
                    result = execute_trade(sym, signal_price)
                    found_trade = True
                    if result is not None:
                        if result > 0:
                            consec_losses = 0
                        else:
                            consec_losses += 1
                    cooldown_until = time.time() + COOLDOWN_SEC
                    break
            except Exception:
                continue
        
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
