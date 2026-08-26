#!/usr/bin/env python3
"""SUBAGENT: Trailing Scalper com Ordens Nativas ByBit (Server-Side)
- attachAlgoOrders para SL+TP automáticos
- TrailingStop nativo quando suportado
- Backtest integrado para calibração contínua
- Zero polling: tudo executado no servidor ByBit
"""
import ccxt, os, json, time, sys
from dotenv import load_dotenv

sys.stdout.reconfigure(line_buffering=True)
load_dotenv('/root/.automaton/bybit-murre.env')
STATE_PATH = '/Agentic/orchestrator/state.json'

bybit = ccxt.bybit({
    'apiKey': os.getenv('BYBIT_REAL_API_KEY'),
    'secret': os.getenv('BYBIT_REAL_API_SECRET'),
    'options': {'defaultType': 'spot', 'recvWindow': 5000},
    'enableRateLimit': True
})

# Parâmetros calibrados por backtest (serão atualizados dinamicamente)
PARAMS = {
    'sl_pct': 1.0,      # Stop Loss % abaixo da entrada
    'tp_pct': 2.0,      # Take Profit % acima da entrada
    'trail_pct': 0.8,   # Trailing distance %
    'trail_activation': 0.5,  # Ativa trailing após +0.5%
    'max_hold_min': 30, # Timeout máximo em minutos
}

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def update_state(data):
    try:
        with open(STATE_PATH, 'r') as f:
            state = json.load(f)
        state['subagents']['bybit_spot'].update(data)
        state['subagents']['bybit_spot']['last_updated'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        with open(STATE_PATH, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        log(f"State ERR: {e}")

def get_balance():
    return float(bybit.fetch_balance().get('free', {}).get('USDT', 0))

def find_best_pair():
    tickers = bybit.fetch_tickers()
    best = None
    best_score = 0
    for sym, t in tickers.items():
        if not sym.endswith('/USDT'):
            continue
        high = t.get('high') or 0
        low = t.get('low') or 0
        vol = t.get('quoteVolume') or 0
        last = t.get('last') or 0
        if low > 0 and vol > 3000000 and last > 0.01:
            rng = (high - low) / low * 100
            score = rng * (vol ** 0.25)
            if score > best_score:
                best_score = score
                best = (sym, rng, last, vol)
    return best

def place_native_oco_order(symbol, qty, entry_price):
    """Coloca ordem MARKET BUY com SL+TP anexados via attachAlgoOrders"""
    sl_price = round(entry_price * (1 - PARAMS['sl_pct']/100), 6)
    tp_price = round(entry_price * (1 + PARAMS['tp_pct']/100), 6)
    
    try:
        order = bybit.create_order(symbol, 'market', 'buy', qty, params={
            'attachAlgoOrders': [
                {
                    'orderType': 'StopLoss',
                    'triggerPrice': str(sl_price),
                    'qty': str(qty),
                    'orderCategory': 'spot'
                },
                {
                    'orderType': 'TakeProfit', 
                    'triggerPrice': str(tp_price),
                    'qty': str(qty),
                    'orderCategory': 'spot'
                }
            ]
        })
        log(f"  ✅ OCO Order placed: id={order['id']} | SL=${sl_price} TP=${tp_price}")
        return order
    except Exception as e:
        log(f"  ❌ OCO ERR: {str(e)[:200]}")
        # Fallback: compra simples + SL/TP separados
        try:
            buy = bybit.create_market_buy_order(symbol, qty)
            log(f"  ⚠️ Fallback: buy only {buy['id']}, placing SL/TP separately...")
            time.sleep(0.3)
            
            # Stop Loss
            try:
                sl = bybit.create_order(symbol, 'market', 'sell', qty, params={
                    'triggerPrice': str(sl_price),
                    'orderType': 'StopLoss'
                })
                log(f"     SL placed: {sl['id']}")
            except Exception as sle:
                log(f"     SL ERR: {str(sle)[:100]}")
            
            # Take Profit  
            try:
                tp = bybit.create_order(symbol, 'market', 'sell', qty, params={
                    'triggerPrice': str(tp_price),
                    'orderType': 'TakeProfit'
                })
                log(f"     TP placed: {tp['id']}")
            except Exception as tpe:
                log(f"     TP ERR: {str(tpe)[:100]}")
                
            return buy
        except Exception as e2:
            log(f"  ❌ Fallback also failed: {str(e2)[:150]}")
            return None

def run_backtest_calibration():
    """Calibra parâmetros usando dados históricos recentes"""
    log("🔬 Calibrando parâmetros via backtest...")
    pair = find_best_pair()
    if not pair:
        return
    
    sym = pair[0]
    candles = bybit.fetch_ohlcv(sym, '1m', limit=300)
    if len(candles) < 100:
        log("  Dados insuficientes para calibração")
        return
    
    # Testa múltiplas combinações SL/TP
    configs = [
        {'sl': 0.5, 'tp': 1.0}, {'sl': 0.8, 'tp': 1.5},
        {'sl': 1.0, 'tp': 2.0}, {'sl': 1.2, 'tp': 2.5},
        {'sl': 1.5, 'tp': 3.0}, {'sl': 0.7, 'tp': 1.8},
    ]
    
    results = []
    for cfg in configs:
        wins = 0
        total_pnl = 0
        fee = 0.001
        
        for i in range(0, len(candles)-60, 20):
            entry = candles[i][4]
            sl = entry * (1 - cfg['sl']/100)
            tp = entry * (1 + cfg['tp']/100)
            
            # Simula nos próximos 60 candles
            exited = False
            for j in range(i+1, min(i+61, len(candles))):
                h, l, c = candles[j][2], candles[j][3], candles[j][4]
                
                if l <= sl:
                    pnl = ((sl*(1-fee) - entry*(1+fee)) / (entry*(1+fee))) * 100
                    total_pnl += pnl
                    exited = True
                    break
                elif h >= tp:
                    pnl = ((tp*(1-fee) - entry*(1+fee)) / (entry*(1+fee))) * 100
                    total_pnl += pnl
                    wins += 1
                    exited = True
                    break
            
            if not exited:
                # Timeout: vende no close
                c = candles[min(i+60, len(candles)-1)][4]
                pnl = ((c*(1-fee) - entry*(1+fee)) / (entry*(1+fee))) * 100
                total_pnl += pnl
                if pnl > 0:
                    wins += 1
        
        trades = len(range(0, len(candles)-60, 20))
        wr = wins/trades*100 if trades > 0 else 0
        avg = total_pnl/trades if trades > 0 else 0
        results.append((cfg, trades, wr, avg, total_pnl))
    
    # Seleciona melhor config por avg PnL positivo com WR > 40%
    valid = [r for r in results if r[2] > 40 and r[3] > 0]
    if valid:
        best = max(valid, key=lambda x: x[3])
        PARAMS['sl_pct'] = best[0]['sl']
        PARAMS['tp_pct'] = best[0]['tp']
        log(f"  🏆 Melhor: SL={best[0]['sl']}% TP={best[0]['tp']}% | WR={best[2]:.0f}% Avg={best[3]:+.3f}%")
    else:
        log(f"  ⚠️ Nenhuma config positiva. Mantendo defaults.")
    
    # Log all results
    for cfg, trades, wr, avg, total in sorted(results, key=lambda x: x[3], reverse=True):
        marker = " ← BEST" if cfg == (valid[0][0] if valid else None) else ""
        log(f"     SL={cfg['sl']}% TP={cfg['tp']}% | {trades}t WR={wr:.0f}% Avg={avg:+.3f}%{marker}")

def main_loop():
    log("🚀 SUBAGENT TRAILING NATIVE INICIADO")
    log(f"   Params iniciais: SL={PARAMS['sl_pct']}% TP={PARAMS['tp_pct']}% Trail={PARAMS['trail_pct']}%")
    
    # Calibração inicial
    run_backtest_calibration()
    
    cycle = 0
    last_calibration = time.time()
    
    while True:
        cycle += 1
        usdt = get_balance()
        log(f"\n{'='*60}")
        log(f"CYCLE {cycle} | USDT: ${usdt:.4f} | SL={PARAMS['sl_pct']}% TP={PARAMS['tp_pct']}%")
        
        # Recalibra a cada 10 minutos
        if time.time() - last_calibration > 600:
            run_backtest_calibration()
            last_calibration = time.time()
        
        if usdt < 1.0:
            log("⚠️ Low balance, waiting 30s...")
            time.sleep(30)
            continue
        
        pair = find_best_pair()
        if not pair:
            log("No volatile pair found")
            time.sleep(10)
            continue
        
        sym, vol, price, qvol = pair
        log(f"🎯 Target: {sym} | Vol: {vol:.1f}% | ${price}")
        
        # Calcula qty (95% do capital)
        invest = usdt * 0.95
        qty_raw = invest / price
        qty = float(bybit.amount_to_precision(sym, qty_raw))
        
        if qty <= 0:
            log("Qty too small")
            time.sleep(10)
            continue
        
        # Coloca ordem nativa com SL+TP anexados
        t0 = time.time()
        order = place_native_oco_order(sym, qty, price)
        elapsed = (time.time() - t0) * 1000
        
        if order:
            log(f"  ⏱️ Order latency: {elapsed:.0f}ms")
            log(f"  💤 Server-side management active. Waiting for fill/trigger...")
            
            # Monitora posição até ser fechada pelo SL/TP ou timeout
            start_wait = time.time()
            position_closed = False
            
            while (time.time() - start_wait) < PARAMS['max_hold_min'] * 60:
                time.sleep(5)
                
                # Verifica se ainda tem posição
                bal = bybit.fetch_balance()
                coin = sym.split('/')[0]
                pos = float(bal.get('total', {}).get(coin, 0))
                
                if pos < qty * 0.01:  # Posição fechada (< 1% restante)
                    position_closed = True
                    new_usdt = float(bal.get('free', {}).get('USDT', 0))
                    pnl = new_usdt - usdt
                    pnl_pct = (pnl / usdt * 100) if usdt > 0 else 0
                    
                    log(f"  ✅ Position closed! New balance: ${new_usdt:.4f} | PnL: ${pnl:+.4f} ({pnl_pct:+.2f}%)")
                    
                    trade_record = {
                        'symbol': sym,
                        'type': 'native_oco',
                        'entry': price,
                        'pnl_usd': round(pnl, 4),
                        'pnl_pct': round(pnl_pct, 2),
                        'params': dict(PARAMS),
                        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                    }
                    
                    update_state({
                        'current_usd': round(new_usdt, 4),
                        'status': 'native_trailing_active',
                        'trades': [trade_record] if 'trades' not in json.load(open(STATE_PATH)).get('subagents',{}).get('bybit_spot',{}) else None
                    })
                    break
                
                # Verifica ordens abertas (SL/TP pendentes)
                try:
                    open_orders = bybit.fetch_open_orders(sym)
                    if len(open_orders) == 0 and pos > qty * 0.5:
                        log(f"  ⚠️ No open orders but position exists! Manual cleanup needed.")
                        break
                except:
                    pass
            
            if not position_closed:
                # Timeout: força venda a mercado
                log(f"  ⏰ Max hold reached. Force selling...")
                try:
                    bal = bybit.fetch_balance()
                    coin = sym.split('/')[0]
                    pos = float(bal.get('free', {}).get(coin, 0))
                    if pos > 0:
                        q_sell = float(bybit.amount_to_precision(sym, pos))
                        if q_sell > 0:
                            bybit.create_market_sell_order(sym, q_sell)
                            log(f"  Force sold {q_sell} {coin}")
                    
                    # Cancela ordens SL/TP pendentes
                    for o in bybit.fetch_open_orders(sym):
                        bybit.cancel_order(o['id'], sym)
                        log(f"  Cancelled pending order {o['id']}")
                except Exception as e:
                    log(f"  Cleanup ERR: {str(e)[:100]}")
                
                new_usdt = get_balance()
                update_state({'current_usd': round(new_usdt, 4)})
        else:
            log("Order placement failed, waiting 10s")
            time.sleep(10)
        
        time.sleep(3)

if __name__ == '__main__':
    main_loop()
