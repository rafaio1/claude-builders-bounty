#!/usr/bin/env python3
"""Grid Trading Optimizer - Find parameters that maximize PnL/day with >100 TPD.
Tests multiple grid configs across multiple pairs simultaneously.
Capital: $10 starting, compound profits.
"""
import ccxt, os, json, time, math, csv
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from itertools import product

load_dotenv('/root/.automaton/bybit-murre.env', override=True)

DATA_DIR = '/Agentic/orchestrator/backtest_data'
RESULTS_DIR = '/Agentic/orchestrator/backtest_results'
FEE_TAKER = 0.001   # 0.1%
FEE_MAKER = 0.0002  # 0.02% (limit orders = maker)

def log(msg):
    ts = datetime.now(timezone.utc).strftime('%H:%M:%S')
    print(f"[{ts}] {msg}", flush=True)

def get_exchange():
    return ccxt.bybit({
        'apiKey': os.getenv('BYBIT_REAL_API_KEY'),
        'secret': os.getenv('BYBIT_REAL_API_SECRET'),
        'options': {'defaultType': 'spot'}
    })

def download_klines(symbol, timeframe='1m', days_back=7):
    ex = get_exchange()
    ex.load_markets()
    all_klines = []
    since = int((datetime.now(timezone.utc) - timedelta(days=days_back)).timestamp() * 1000)
    log(f"Downloading {symbol} {timeframe} ({days_back}d)...")
    while True:
        try:
            klines = ex.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
            if not klines: break
            all_klines.extend(klines)
            since = klines[-1][0] + 1
            if len(klines) < 1000: break
            time.sleep(0.15)
        except Exception as e:
            log(f"  Error: {e}")
            break
    filename = f"{DATA_DIR}/{symbol.replace('/', '_')}_{timeframe}_7d.csv"
    with open(filename, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['ts','o','h','l','c','v'])
        for k in all_klines: w.writerow(k)
    log(f"  Saved {len(all_klines)} candles")
    return all_klines

def load_klines(symbol, timeframe='1m', days='7d'):
    filename = f"{DATA_DIR}/{symbol.replace('/', '_')}_{timeframe}_{days}.csv"
    try:
        klines = []
        with open(filename, 'r') as f:
            r = csv.reader(f); next(r)
            for row in r: klines.append([float(x) for x in row])
        return klines
    except: return []

def simulate_grid(klines, capital, num_grids, grid_spacing_pct, lookback_bars, 
                  fee_rate=FEE_MAKER, use_compound=True):
    """
    Simulate grid trading with configurable parameters.
    Grid places buy orders below current price and sell orders above.
    Each completed round-trip captures grid_spacing minus fees.
    """
    trades = []
    equity = capital
    total_fees = 0.0
    
    # Track active grid levels
    active_buys = {}   # price -> qty
    active_sells = {}  # price -> qty
    
    for i in range(lookback_bars, len(klines)):
        ts = klines[i][0]
        o, h, l, c, v = klines[i][1], klines[i][2], klines[i][3], klines[i][4], klines[i][5]
        
        # Calculate dynamic range from lookback
        highs = [k[2] for k in klines[i-lookback_bars:i]]
        lows = [k[3] for k in klines[i-lookback_bars:i]]
        range_high = max(highs)
        range_low = min(lows)
        mid = (range_high + range_low) / 2
        
        if range_high <= range_low or mid <= 0:
            continue
        
        # Check fills this bar
        # Buy fills: price dropped to or below buy level
        filled_buys = []
        for price, qty in list(active_buys.items()):
            if l <= price:
                filled_buys.append((price, qty))
                del active_buys[price]
        
        # Sell fills: price rose to or above sell level  
        filled_sells = []
        for price, qty in list(active_sells.items()):
            if h >= price:
                filled_sells.append((price, qty))
                del active_sells[price]
        
        # Process buy fills -> place corresponding sells
        for buy_price, qty in filled_buys:
            sell_price = buy_price * (1 + grid_spacing_pct)
            active_sells[sell_price] = qty
        
        # Process sell fills -> record completed round trips
        for sell_price, qty in filled_sells:
            buy_price = sell_price / (1 + grid_spacing_pct)
            gross = (sell_price - buy_price) * qty
            fees = (buy_price * qty + sell_price * qty) * fee_rate
            net = gross - fees
            
            trades.append({
                'ts_in': ts, 'ts_out': ts,
                'entry': buy_price, 'exit': sell_price,
                'qty': qty, 'gross': gross, 'fees': fees, 'net': net
            })
            total_fees += fees
            
            if use_compound:
                equity += net
        
        # Rebalance grid every N bars or if no active orders
        if i % 10 == 0 or (not active_buys and not active_sells):
            # Clear stale orders far from current price
            stale_threshold = grid_spacing_pct * 3
            active_buys = {p: q for p, q in active_buys.items() 
                          if abs(p - c) / c < stale_threshold}
            active_sells = {p: q for p, q in active_sells.items()
                           if abs(p - c) / c < stale_threshold}
            
            # Place new grid orders around current price
            available_capital = equity if use_compound else capital
            per_grid = available_capital / max(num_grids, 1)
            
            for g in range(1, num_grids // 2 + 1):
                buy_level = c * (1 - g * grid_spacing_pct)
                sell_level = c * (1 + g * grid_spacing_pct)
                
                if buy_level > range_low * 0.99:
                    qty = per_grid / buy_level
                    if buy_level not in active_buys:
                        active_buys[buy_level] = qty
                
                if sell_level < range_high * 1.01:
                    qty = per_grid / sell_level
                    if sell_level not in active_sells:
                        active_sells[sell_level] = qty
    
    # Calculate metrics
    n = len(trades)
    wins = sum(1 for t in trades if t['net'] > 0)
    total_pnl = sum(t['net'] for t in trades)
    
    if n > 0:
        first_ts = trades[0]['ts_in']
        last_ts = trades[-1]['ts_out']
        days = max(0.01, (last_ts - first_ts) / 86400000)
        tpd = n / days
        ppd = total_pnl / days
    else:
        days, tpd, ppd = 1, 0, 0
    
    wr = (wins / n * 100) if n > 0 else 0
    avg_net = total_pnl / n if n > 0 else 0
    
    return {
        'trades': n, 'wins': wins, 'wr': round(wr, 1),
        'pnl': round(total_pnl, 4), 'fees': round(total_fees, 4),
        'tpd': round(tpd, 1), 'ppd': round(ppd, 4),
        'avg_net': round(avg_net, 6),
        'final_equity': round(equity, 4),
        'roi_pct': round((equity - capital) / capital * 100, 2)
    }

def main():
    log("=" * 80)
    log("GRID TRADING OPTIMIZER - Multi-Parameter Search")
    log("Target: >100 TPD, >$50/day PnL, $10 capital")
    log("=" * 80)
    
    symbols = ['XRP/USDT', 'DOGE/USDT', 'BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    
    # Download 7 days of data for each symbol
    for sym in symbols:
        kl = load_klines(sym, '1m', '7d')
        if len(kl) < 1000:
            download_klines(sym, '1m', days_back=7)
    
    # Parameter grid search
    param_grid = {
        'num_grids': [8, 12, 16, 20, 30],
        'grid_spacing': [0.002, 0.003, 0.004, 0.005, 0.008, 0.01],
        'lookback': [30, 60, 120],
    }
    
    combos = list(product(param_grid['num_grids'], param_grid['grid_spacing'], param_grid['lookback']))
    log(f"\nTesting {len(combos)} parameter combinations x {len(symbols)} symbols = {len(combos)*len(symbols)} backtests")
    
    all_results = []
    best_overall = None
    best_score = -999
    
    for sym in symbols:
        klines = load_klines(sym, '1m', '7d')
        if len(klines) < 200:
            log(f"  {sym}: insufficient data, skipping")
            continue
        
        log(f"\n--- {sym} ({len(klines)} candles) ---")
        
        for ng, gs, lb in combos:
            r = simulate_grid(klines, capital=10.0, num_grids=ng, 
                            grid_spacing_pct=gs, lookback_bars=lb,
                            fee_rate=FEE_MAKER, use_compound=True)
            
            r['symbol'] = sym
            r['params'] = {'grids': ng, 'spacing': gs, 'lookback': lb}
            all_results.append(r)
            
            # Score: weighted combination of TPD and PnL/day
            # Must meet minimum TPD threshold
            if r['tpd'] >= 50:  # Minimum viable TPD
                score = r['ppd'] * (r['tpd'] / 100) * (r['wr'] / 100)
            else:
                score = r['ppd'] * 0.1  # Penalize low TPD
            
            if score > best_score:
                best_score = score
                best_overall = r
        
        # Show top 3 for this symbol
        sym_results = [r for r in all_results if r['symbol'] == sym]
        sym_results.sort(key=lambda x: x['ppd'], reverse=True)
        for r in sym_results[:3]:
            p = r['params']
            log(f"  grids={p['grids']:>2} spacing={p['spacing']*100:.1f}% lb={p['lookback']:>3} | "
                f"{r['trades']:>5}t WR={r['wr']:>5.1f}% PnL=${r['pnl']:>8.4f} "
                f"TPD={r['tpd']:>6.1f} $/d=${r['ppd']:>8.4f} ROI={r['roi_pct']:>6.1f}%")
    
    # Global ranking
    log(f"\n{'='*100}")
    log(f"TOP 20 CONFIGURATIONS (sorted by PnL/day)")
    log(f"{'='*100}")
    log(f"{'Rank':>4} {'Symbol':<12} {'Grids':>5} {'Space%':>7} {'LB':>4} | "
        f"{'Trades':>6} {'WR%':>6} {'PnL':>10} {'TPD':>7} {'$/day':>10} {'ROI%':>7}")
    log("-" * 100)
    
    all_results.sort(key=lambda x: x['ppd'], reverse=True)
    
    for i, r in enumerate(all_results[:20]):
        p = r['params']
        marker = " ★" if r == best_overall else ""
        log(f"{i+1:>4} {r['symbol']:<12} {p['grids']:>5} {p['spacing']*100:>7.1f} {p['lookback']:>4} | "
            f"{r['trades']:>6} {r['wr']:>6.1f} {r['pnl']:>10.4f} {r['tpd']:>7.1f} {r['ppd']:>10.4f} {r['roi_pct']:>7.1f}{marker}")
    
    # Viability assessment
    log(f"\n{'='*80}")
    log("VIABILITY ASSESSMENT")
    log(f"{'='*80}")
    
    viable = [r for r in all_results if r['tpd'] >= 100 and r['ppd'] >= 50]
    near_viable = [r for r in all_results if r['tpd'] >= 100 and r['ppd'] >= 1.0]
    
    if viable:
        log(f"✓ FOUND {len(viable)} configurations meeting target (>100 TPD, >$50/day)")
        for r in viable[:5]:
            p = r['params']
            log(f"  {r['symbol']} grids={p['grids']} spacing={p['spacing']*100:.1f}% | "
                f"TPD={r['tpd']:.0f} $/d=${r['ppd']:.2f}")
    elif near_viable:
        best_nv = near_viable[0]
        p = best_nv['params']
        log(f"✗ NO config meets $50/day target")
        log(f"  BEST VIABLE: {best_nv['symbol']} grids={p['grids']} spacing={p['spacing']*100:.1f}%")
        log(f"  TPD={best_nv['tpd']:.0f} ✓ | $/day=${best_nv['ppd']:.4f} (need $50 = {50/max(best_nv['ppd'],0.001):.0f}x gap)")
        log(f"  With $10 capital, max theoretical daily profit at 0.5% edge/trade:")
        log(f"    100 trades × $10 × 0.5% = $5.00/day (BEFORE fees)")
        log(f"    To reach $50/day need either:")
        log(f"      a) $100 capital (10x) → ${best_nv['ppd']*10:.2f}/day")
        log(f"      b) 5% edge/trade (unrealistic in spot)")
        log(f"      c) Leverage/futures (blocked on this account)")
    else:
        log(f"✗ NO configuration achieves >100 TPD with positive PnL")
        log(f"  Best overall: {best_overall['symbol'] if best_overall else 'N/A'}")
        if best_overall:
            log(f"  TPD={best_overall['tpd']:.0f} $/d=${best_overall['ppd']:.4f}")
    
    # Capital scaling analysis
    log(f"\n--- CAPITAL SCALING PROJECTION ---")
    if best_overall and best_overall['ppd'] > 0:
        base_ppd = best_overall['ppd']
        for cap in [10, 50, 100, 500, 1000]:
            projected = base_ppd * (cap / 10)
            meets_target = "✓" if projected >= 50 else "✗"
            log(f"  ${cap:>5} capital → ${projected:>8.2f}/day {meets_target}")
    
    # Save results
    out = f"{RESULTS_DIR}/grid_optimizer_{int(time.time())}.json"
    with open(out, 'w') as f:
        json.dump({
            'best': best_overall,
            'top20': all_results[:20],
            'total_tested': len(all_results),
            'viable_count': len(viable),
            'near_viable_count': len(near_viable)
        }, f, indent=2)
    log(f"\nResults saved: {out}")

if __name__ == '__main__':
    main()
