#!/usr/bin/env python3
"""BACKTEST TRAILING SCALPER - Simula micro-oscilações com dados reais ByBit"""
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

# Configurações de trailing para testar
CONFIGS = [
    {'name': 'conservative', 'activation': 0.3, 'distance': 0.2, 'be': 0.15, 'max_hold': 60},
    {'name': 'balanced',     'activation': 0.25, 'distance': 0.15, 'be': 0.12, 'max_hold': 45},
    {'name': 'aggressive',   'activation': 0.15, 'distance': 0.10, 'be': 0.08, 'max_hold': 30},
    {'name': 'micro_scalp',  'activation': 0.10, 'distance': 0.07, 'be': 0.05, 'max_hold': 20},
]

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def fetch_ohlcv(symbol, timeframe='1m', limit=500):
    """Busca candles recentes para simulação"""
    try:
        candles = bybit.fetch_ohlcv(symbol, timeframe, limit=limit)
        return candles  # [[ts, open, high, low, close, volume], ...]
    except Exception as e:
        log(f"OHLCV ERR {symbol}: {e}")
        return []

def simulate_trailing(candles, config, entry_price, fee_rate=0.001):
    """Simula trailing stop em candles históricos"""
    hwm = entry_price
    trail_on = False
    be_on = False
    
    for i, candle in enumerate(candles):
        ts, o, h, l, c, v = candle
        
        # Simula movimento intra-candle: high primeiro (melhor caso)
        if h > hwm:
            hwm = h
            pnl_pct = ((hwm - entry_price) / entry_price) * 100
            
            if pnl_pct >= config['be'] and not be_on:
                be_on = True
            if pnl_pct >= config['activation'] and not trail_on:
                trail_on = True
        
        # Verifica condições de saída usando low do candle
        if trail_on:
            stop = hwm * (1 - config['distance'] / 100)
            if l <= stop:
                exit_price = max(stop, l)  # Executa no stop ou no low
                cost = entry_price * (1 + fee_rate)
                proceeds = exit_price * (1 - fee_rate)
                pnl_pct = ((proceeds - cost) / cost) * 100
                return {'exit': exit_price, 'pnl_pct': pnl_pct, 'reason': 'trail', 'candles_held': i+1}
        
        elif be_on and l <= entry_price:
            cost = entry_price * (1 + fee_rate)
            proceeds = entry_price * (1 - fee_rate)
            pnl_pct = ((proceeds - cost) / cost) * 100
            return {'exit': entry_price, 'pnl_pct': pnl_pct, 'reason': 'breakeven', 'candles_held': i+1}
        
        # Max hold time (cada candle = 1 min)
        if (i + 1) >= config['max_hold']:
            cost = entry_price * (1 + fee_rate)
            proceeds = c * (1 - fee_rate)
            pnl_pct = ((proceeds - cost) / cost) * 100
            return {'exit': c, 'pnl_pct': pnl_pct, 'reason': 'timeout', 'candles_held': i+1}
    
    # Se chegou ao fim sem sair
    cost = entry_price * (1 + fee_rate)
    proceeds = candles[-1][4] * (1 - fee_rate)
    pnl_pct = ((proceeds - cost) / cost) * 100
    return {'exit': candles[-1][4], 'pnl_pct': pnl_pct, 'reason': 'end', 'candles_held': len(candles)}

def find_top_pairs():
    """Encontra pares mais voláteis com alta liquidez"""
    tickers = bybit.fetch_tickers()
    candidates = []
    for sym, t in tickers.items():
        if not sym.endswith('/USDT'):
            continue
        high = t.get('high') or 0
        low = t.get('low') or 0
        vol = t.get('quoteVolume') or 0
        last = t.get('last') or 0
        if low > 0 and vol > 5000000 and last > 0.01:
            rng = (high - low) / low * 100
            score = rng * (vol ** 0.25)
            candidates.append((sym, rng, last, vol, score))
    candidates.sort(key=lambda x: x[4], reverse=True)
    return candidates[:10]

log("🔬 BACKTEST TRAILING SCALPER INICIADO")
log("Analisando micro-oscilações em top 10 pares voláteis...")

pairs = find_top_pairs()
log(f"\nTop 10 pares selecionados:")
for sym, rng, price, vol, score in pairs:
    log(f"  {sym}: vol={rng:.1f}% | ${price} | liq=${vol/1e6:.1f}M")

results = {cfg['name']: {'trades': [], 'wins': 0, 'losses': 0, 'total_pnl': 0, 'avg_pnl': 0} for cfg in CONFIGS}

for sym, rng, price, vol, score in pairs:
    log(f"\n📊 Backtesting {sym} ({rng:.1f}% vol)...")
    candles = fetch_ohlcv(sym, '1m', 500)
    if len(candles) < 100:
        log(f"  Dados insuficientes ({len(candles)} candles)")
        continue
    
    # Testa cada configuração em múltiplos pontos de entrada
    entry_points = [candles[i][4] for i in range(0, len(candles)-60, 30)]  # A cada 30 min
    
    for cfg in CONFIGS:
        trades = []
        for ep in entry_points:
            # Usa próximos 60 candles após ponto de entrada
            idx = next((j for j, c in enumerate(candles) if c[4] == ep), None)
            if idx is None or idx + 60 > len(candles):
                continue
            subset = candles[idx:idx+60]
            result = simulate_trailing(subset, cfg, ep)
            trades.append(result)
        
        wins = sum(1 for t in trades if t['pnl_pct'] > 0)
        losses = len(trades) - wins
        total_pnl = sum(t['pnl_pct'] for t in trades)
        avg_pnl = total_pnl / len(trades) if trades else 0
        
        results[cfg['name']]['trades'].extend(trades)
        results[cfg['name']]['wins'] += wins
        results[cfg['name']]['losses'] += losses
        results[cfg['name']]['total_pnl'] += total_pnl
        
        log(f"  [{cfg['name']:12s}] {len(trades):3d} trades | Win: {wins}/{len(trades)} ({wins/len(trades)*100:.0f}%) | Avg: {avg_pnl:+.3f}% | Total: {total_pnl:+.2f}%")

# Ranking final
log("\n" + "="*70)
log("🏆 RANKING DE ESTRATÉGIAS (MICRO-OSCILAÇÕES)")
log("="*70)

ranking = []
for name, data in results.items():
    total_trades = data['wins'] + data['losses']
    win_rate = data['wins'] / total_trades * 100 if total_trades > 0 else 0
    avg = data['total_pnl'] / total_trades if total_trades > 0 else 0
    ranking.append((name, total_trades, win_rate, avg, data['total_pnl']))

ranking.sort(key=lambda x: x[3], reverse=True)  # Sort by avg pnl

for i, (name, trades, wr, avg, total) in enumerate(ranking):
    medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "  "
    log(f"{medal} {name:12s} | {trades:4d} trades | WR: {wr:5.1f}% | Avg: {avg:+.4f}% | Total: {total:+.2f}%")

best = ranking[0]
log(f"\n✅ MELHOR ESTRATÉGIA: {best[0]}")
log(f"   Win Rate: {best[2]:.1f}% | Avg PnL: {best[3]:+.4f}% por trade")

# Salvar resultados no state.json
with open(STATE_PATH, 'r') as f:
    state = json.load(f)

state['subagents']['bybit_spot']['backtest_results'] = {
    'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    'pairs_tested': len(pairs),
    'best_strategy': best[0],
    'best_win_rate': round(best[2], 1),
    'best_avg_pnl_pct': round(best[3], 4),
    'ranking': [{'name': r[0], 'trades': r[1], 'win_rate': round(r[2],1), 'avg_pnl': round(r[3],4)} for r in ranking],
    'recommendation': f'Usar estratégia "{best[0]}" com trailing activation={next(c["activation"] for c in CONFIGS if c["name"]==best[0])}%, distance={next(c["distance"] for c in CONFIGS if c["name"]==best[0])}%'
}

with open(STATE_PATH, 'w') as f:
    json.dump(state, f, indent=2)

log("\n💾 Resultados salvos em state.json")
log("🔬 BACKTEST CONCLUÍDO")
