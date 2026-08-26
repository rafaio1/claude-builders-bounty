#!/usr/bin/env python3
"""Advanced Backtest: Market Making + Cross-Pair Arb + Grid Trading.
Tests strategies that can theoretically overcome 0.2% round-trip fees.
"""
import ccxt, os, sys, json, time, math, csv
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv('/root/.automaton/bybit-murre.env', override=True)

DATA_DIR = '/Agentic/orchestrator/backtest_data'
RESULTS_DIR = '/Agentic/orchestrator/backtest_results'
FEE_RATE = 0.001  # 0.1% per side taker; maker would be 0.02% but we test worst case

def log(msg):
    ts = datetime.now(timezone.utc).strftime('%H:%M:%S')
    print(f"[{ts}] {msg}", flush=True)

def load_klines(symbol, timeframe='1m'):
    filename = f"{DATA_DIR}/{symbol.replace('/', '_')}_{timeframe}.csv"
    klines = []
    with open(filename, 'r') as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            klines.append([float(x) for x in row])
    return klines

class Result:
    def __init__(self, name, symbol):
        self.name = name
        self.symbol = symbol
        self.trades = []
        self.wins = 0
        self.losses = 0
        self.total_pnl = 0.0
        self.total_fees = 0.0
        self.peak = 0.0
        self.max_dd = 0.0
    
    def add(self, entry, exit_, qty, ts_in, ts_out, reason):
        gross = (exit_ - entry) * qty
        fees = (entry * qty + exit_ * qty) * FEE_RATE
        net = gross - fees
        self.trades.append({'net': net, 'reason': reason})
        self.total_pnl += net
        self.total_fees += fees
        if net > 0: self.wins += 1
        else: self.losses += 1
        eq = self.total_pnl
        if eq > self.peak: self.peak = eq
        dd = self.peak - eq
        if dd > self.max_dd: self.max_dd = dd
    
    def summary(self):
        n = self.wins + self.losses
        wr = (self.wins / n * 100) if n > 0 else 0
        if self.trades:
            days = max(1, (self.trades[-1].get('ts_out', self.trades[0].get('ts_in', 0)) - self.trades[0].get('ts_in', 0)) / 86400000)
            tpd = n / days
            ppd = self.total_pnl / days
        else:
            days, tpd, ppd = 1, 0, 0
        avg_w = sum(t['net'] for t in self.trades if t['net'] > 0) / max(1, self.wins)
        avg_l = sum(t['net'] for t in self.trades if t['net'] <= 0) / max(1, self.losses)
        pf = abs(avg_w * self.wins / (avg_l * self.losses)) if self.losses > 0 and avg_l != 0 else float('inf')
        return {
            'strategy': self.name, 'symbol': self.symbol,
            'trades': n, 'wins': self.wins, 'wr': round(wr, 1),
            'pnl': round(self.total_pnl, 4), 'fees': round(self.total_fees, 4),
            'tpd': round(tpd, 1), 'ppd': round(ppd, 4),
            'avg_win': round(avg_w, 6), 'avg_loss': round(avg_l, 6),
            'pf': round(pf, 2), 'max_dd': round(self.max_dd, 4),
            'days': round(days, 2)
        }

# Strategy 4: Passive Market Making (simulated)
# Place bid at best_bid and ask at best_ask every bar.
# If both fill in same bar, capture full spread minus fees.
# Realistic fill rate estimated from volume/spread ratio.
def backtest_market_making(klines, symbol, capital=10.0):
    r = Result("Passive_MarketMaking", symbol)
    
    # Simulate: each minute, estimate probability of both sides filling
    # Higher volume + tighter spread = higher fill probability
    position_cost = 0
    position_qty = 0
    
    for i in range(1, len(klines)):
        ts = klines[i][0]
        o, h, l, c, v = klines[i][1], klines[i][2], klines[i][3], klines[i][4], klines[i][5]
        prev_c = klines[i-1][4]
        
        # Estimate spread from high-low range (proxy for tick data)
        bar_range = (h - l) / l if l > 0 else 0
        est_spread = bar_range * 0.3  # Spread is typically ~30% of bar range
        
        # Fill probability based on volume and spread tightness
        # More volume = more fills; tighter spread = easier to get hit
        vol_factor = min(v / 100000, 3.0)  # Normalize volume
        spread_factor = max(0.1, 1.0 - est_spread * 100)  # Tighter = better
        fill_prob = min(0.8, vol_factor * spread_factor * 0.3)
        
        # Simulate fills using deterministic hash for reproducibility
        import hashlib
        seed = int(hashlib.md5(f"{symbol}{ts}".encode()).hexdigest()[:8], 16) % 10000
        bid_fill = (seed % 100) < (fill_prob * 100)
        ask_fill = ((seed // 100) % 100) < (fill_prob * 100)
        
        mid = (h + l) / 2
        bid_price = mid * (1 - est_spread / 2)
        ask_price = mid * (1 + est_spread / 2)
        
        if bid_fill and ask_fill:
            # Both sides filled: capture spread
            qty = capital / mid
            gross = (ask_price - bid_price) * qty
            fees = (bid_price * qty + ask_price * qty) * FEE_RATE
            net = gross - fees
            r.trades.append({'net': net, 'reason': 'BOTH_FILL'})
            r.total_pnl += net
            r.total_fees += fees
            if net > 0: r.wins += 1
            else: r.losses += 1
            eq = r.total_pnl
            if eq > r.peak: r.peak = eq
            dd = r.peak - eq
            if dd > r.max_dd: r.max_dd = dd
        elif bid_fill and not ask_fill:
            # Only buy filled: hold inventory, mark-to-market at close
            qty = capital / bid_price
            unrealized = (c - bid_price) * qty
            # Assume we sell at close (taker fee)
            fees = (bid_price * qty + c * qty) * FEE_RATE
            net = unrealized - fees
            r.add(bid_price, c, qty, ts, ts, "BID_ONLY_CLOSE")
        elif ask_fill and not bid_fill:
            # Only sell filled: short inventory (not possible in spot without borrowing)
            # Skip - can't naked short in spot
            pass
    
    return r

# Strategy 5: Cross-Pair Statistical Arbitrage
# Trade XRP/USDT vs DOGE/USDT ratio mean reversion
def backtest_cross_pair_arb(klines_a, klines_b, sym_a, sym_b, capital=10.0):
    r = Result(f"CrossPair_Arb_{sym_a.split('/')[0]}_{sym_b.split('/')[0]}", f"{sym_a}+{sym_b}")
    
    # Align timestamps
    ts_a = {k[0]: k for k in klines_a}
    ts_b = {k[0]: k for k in klines_b}
    common_ts = sorted(set(ts_a.keys()) & set(ts_b.keys()))
    
    if len(common_ts) < 100:
        log(f"  Insufficient aligned data: {len(common_ts)} bars")
        return r
    
    ratios = []
    for ts in common_ts:
        ca = ts_a[ts][4]
        cb = ts_b[ts][4]
        if cb > 0:
            ratios.append((ts, ca / cb))
    
    # Z-score mean reversion on ratio
    lookback = 60
    entry_z = 2.0
    exit_z = 0.5
    
    position = None
    
    for i in range(lookback, len(ratios)):
        ts = ratios[i][0]
        ratio = ratios[i][1]
        
        window = [r[1] for r in ratios[i-lookback:i]]
        mean_r = sum(window) / len(window)
        std_r = math.sqrt(sum((x - mean_r)**2 for x in window) / len(window))
        
        if std_r == 0:
            continue
        
        z = (ratio - mean_r) / std_r
        
        if position is None:
            if z > entry_z:
                # Ratio too high: sell A, buy B
                qty_a = (capital / 2) / ts_a[ts][4]
                qty_b = (capital / 2) / ts_b[ts][4]
                position = {'ts': ts, 'qty_a': qty_a, 'qty_b': qty_b, 
                           'entry_a': ts_a[ts][4], 'entry_b': ts_b[ts][4], 'side': 'short_ratio'}
            elif z < -entry_z:
                # Ratio too low: buy A, sell B
                qty_a = (capital / 2) / ts_a[ts][4]
                qty_b = (capital / 2) / ts_b[ts][4]
                position = {'ts': ts, 'qty_a': qty_a, 'qty_b': qty_b,
                           'entry_a': ts_a[ts][4], 'entry_b': ts_b[ts][4], 'side': 'long_ratio'}
        else:
            exit_a = ts_a[ts][4]
            exit_b = ts_b[ts][4]
            
            if position['side'] == 'short_ratio':
                pnl_a = (position['entry_a'] - exit_a) * position['qty_a']  # sold A
                pnl_b = (exit_b - position['entry_b']) * position['qty_b']  # bought B
            else:
                pnl_a = (exit_a - position['entry_a']) * position['qty_a']
                pnl_b = (position['entry_b'] - exit_b) * position['qty_b']
            
            gross = pnl_a + pnl_b
            fees = (position['entry_a'] * position['qty_a'] + exit_a * position['qty_a'] +
                   position['entry_b'] * position['qty_b'] + exit_b * position['qty_b']) * FEE_RATE
            net = gross - fees
            
            should_exit = abs(z) < exit_z or abs(z) > 4.0  # Exit on reversion or extreme
            
            if should_exit:
                r.trades.append({'net': net, 'reason': 'Z_REVERSION' if abs(z) < exit_z else 'EXTREME_EXIT'})
                r.total_pnl += net
                r.total_fees += fees
                if net > 0: r.wins += 1
                else: r.losses += 1
                eq = r.total_pnl
                if eq > r.peak: r.peak = eq
                dd = r.peak - eq
                if dd > r.max_dd: r.max_dd = dd
                position = None
    
    return r

# Strategy 6: Grid Trading (buy dips, sell rips in range)
def backtest_grid(klines, symbol, capital=10.0, grid_pct=0.005, num_grids=5):
    """Place grid orders within recent range. Buy at lower grids, sell at upper."""
    r = Result("Grid_Trading", symbol)
    
    lookback = 60
    active_orders = []  # (price, side, qty, ts)
    
    for i in range(lookback, len(klines)):
        ts = klines[i][0]
        c = klines[i][4]
        h = klines[i][2]
        l = klines[i][3]
        
        # Calculate range from lookback
        highs = [k[2] for k in klines[i-lookback:i]]
        lows = [k[3] for k in klines[i-lookback:i]]
        range_high = max(highs)
        range_low = min(lows)
        range_mid = (range_high + range_low) / 2
        range_width = range_high - range_low
        
        if range_width / range_mid < 0.01:  # Range too tight, skip
            continue
        
        # Check if any active orders filled this bar
        remaining = []
        for price, side, qty, order_ts in active_orders:
            filled = False
            if side == 'buy' and l <= price:
                # Buy filled, place corresponding sell
                sell_price = price * (1 + grid_pct)
                remaining.append((sell_price, 'sell', qty, ts))
                filled = True
            elif side == 'sell' and h >= price:
                # Sell filled: record completed round trip
                # Find original buy price (approximate)
                buy_price = price / (1 + grid_pct)
                gross = (price - buy_price) * qty
                fees = (buy_price * qty + price * qty) * FEE_RATE
                net = gross - fees
                r.add(buy_price, price, qty, order_ts, ts, "GRID_COMPLETE")
                filled = True
            
            if not filled:
                remaining.append((price, side, qty, order_ts))
        
        active_orders = remaining
        
        # Place new grid orders if we have capacity
        if len(active_orders) < num_grids * 2:
            grid_step = range_width / num_grids
            for g in range(num_grids):
                buy_level = range_low + g * grid_step
                sell_level = range_low + (g + 1) * grid_step
                
                # Only place if price is near this level
                if abs(c - buy_level) / c < grid_pct / 2:
                    qty = capital / (num_grids * c)
                    active_orders.append((buy_level, 'buy', qty, ts))
                if abs(c - sell_level) / c < grid_pct / 2:
                    qty = capital / (num_grids * c)
                    active_orders.append((sell_level, 'sell', qty, ts))
    
    return r

# Strategy 7: Maker Rebate Scalp (assume 0.02% maker fee instead of 0.1%)
def backtest_maker_rebate(klines, symbol, capital=10.0):
    """Same as mean reversion but with MAKER fees (0.02% each side = 0.04% RT)."""
    MAKER_FEE = 0.0002  # 0.02% maker
    r = Result("Maker_Rebate_Scalp", symbol)
    
    sma_period = 10
    entry_dev = 0.0015  # 0.15% below SMA
    exit_dev = 0.0005   # 0.05% above entry
    
    position = None
    
    for i in range(sma_period, len(klines)):
        ts = klines[i][0]
        c = klines[i][4]
        sma = sum(k[4] for k in klines[i-sma_period:i]) / sma_period
        dev = (c - sma) / sma
        
        if position is None:
            if dev < -entry_dev:
                qty = capital / c
                position = {'entry': c, 'ts': ts, 'qty': qty}
        else:
            pnl_pct = (c - position['entry']) / position['entry']
            if pnl_pct >= exit_dev or dev >= 0:
                gross = (c - position['entry']) * position['qty']
                fees = (position['entry'] * position['qty'] + c * position['qty']) * MAKER_FEE
                net = gross - fees
                r.add(position['entry'], c, position['qty'], position['ts'], ts, "MAKER_TP")
                position = None
            elif pnl_pct <= -0.003:
                gross = (c - position['entry']) * position['qty']
                fees = (position['entry'] * position['qty'] + c * position['qty']) * MAKER_FEE
                net = gross - fees
                r.add(position['entry'], c, position['qty'], position['ts'], ts, "MAKER_SL")
                position = None
    
    if position:
        c = klines[-1][4]
        gross = (c - position['entry']) * position['qty']
        fees = (position['entry'] * position['qty'] + c * position['qty']) * MAKER_FEE
        r.add(position['entry'], c, position['qty'], position['ts'], klines[-1][0], "EOD")
    
    return r

def main():
    log("=" * 70)
    log("ADVANCED BACKTEST: Market Making + Cross-Pair Arb + Grid + Maker Rebate")
    log(f"Fee assumption: 0.1% taker (except Maker Rebate @ 0.02%)")
    log("=" * 70)
    
    results = []
    
    # Load pre-downloaded data
    xrp = load_klines('XRP/USDT')
    doge = load_klines('DOGE/USDT')
    btc = load_klines('BTC/USDT')
    
    log(f"\nData loaded: XRP={len(xrp)}, DOGE={len(doge)}, BTC={len(btc)} candles")
    
    # Test Market Making
    log("\n--- Passive Market Making ---")
    for sym, kl in [('XRP/USDT', xrp), ('DOGE/USDT', doge), ('BTC/USDT', btc)]:
        r = backtest_market_making(kl, sym, 10.0)
        s = r.summary()
        results.append(s)
        log(f"  {sym}: {s['trades']}t WR={s['wr']}% PnL={s['pnl']:.4f} TPD={s['tpd']} PnL/d={s['ppd']:.4f}")
    
    # Test Cross-Pair Arb
    log("\n--- Cross-Pair Statistical Arbitrage ---")
    r_xd = backtest_cross_pair_arb(xrp, doge, 'XRP/USDT', 'DOGE/USDT', 10.0)
    s_xd = r_xd.summary()
    results.append(s_xd)
    log(f"  XRP-DOGE: {s_xd['trades']}t WR={s_xd['wr']}% PnL={s_xd['pnl']:.4f} TPD={s_xd['tpd']} PnL/d={s_xd['ppd']:.4f}")
    
    r_xb = backtest_cross_pair_arb(xrp, btc, 'XRP/USDT', 'BTC/USDT', 10.0)
    s_xb = r_xb.summary()
    results.append(s_xb)
    log(f"  XRP-BTC: {s_xb['trades']}t WR={s_xb['wr']}% PnL={s_xb['pnl']:.4f} TPD={s_xb['tpd']} PnL/d={s_xb['ppd']:.4f}")
    
    # Test Grid Trading
    log("\n--- Grid Trading ---")
    for sym, kl in [('XRP/USDT', xrp), ('DOGE/USDT', doge)]:
        r = backtest_grid(kl, sym, 10.0, grid_pct=0.005, num_grids=5)
        s = r.summary()
        results.append(s)
        log(f"  {sym}: {s['trades']}t WR={s['wr']}% PnL={s['pnl']:.4f} TPD={s['tpd']} PnL/d={s['ppd']:.4f}")
    
    # Test Maker Rebate Scalp
    log("\n--- Maker Rebate Scalp (0.02% fee) ---")
    for sym, kl in [('XRP/USDT', xrp), ('DOGE/USDT', doge), ('BTC/USDT', btc)]:
        r = backtest_maker_rebate(kl, sym, 10.0)
        s = r.summary()
        results.append(s)
        log(f"  {sym}: {s['trades']}t WR={s['wr']}% PnL={s['pnl']:.4f} TPD={s['tpd']} PnL/d={s['ppd']:.4f}")
    
    # Summary table
    log(f"\n{'='*90}")
    log(f"{'Strategy':<30} {'Symbol':<15} {'Trades':>7} {'WR%':>6} {'PnL':>10} {'TPD':>7} {'PnL/d':>10} {'PF':>6}")
    log("-" * 90)
    
    best = None
    best_score = -999
    for s in results:
        score = s['ppd'] * (s['wr'] / 100) * min(s['tpd'] / 100, 1.0)
        marker = ""
        if score > best_score:
            best_score = score
            best = s
            marker = " ★"
        log(f"{s['strategy']:<30} {s['symbol']:<15} {s['trades']:>7} {s['wr']:>6.1f} {s['pnl']:>10.4f} {s['tpd']:>7.1f} {s['ppd']:>10.4f} {s['pf']:>6.2f}{marker}")
    
    log(f"\n{'='*70}")
    if best:
        log(f"BEST: {best['strategy']} on {best['symbol']}")
        log(f"  Trades/day: {best['tpd']:.1f} | PnL/day: ${best['ppd']:.4f} | WR: {best['wr']}% | PF: {best['pf']}")
        
        target_tpd = 100
        target_ppd = 50
        viable = best['tpd'] >= target_tpd and best['ppd'] >= target_ppd
        log(f"\n  TARGET CHECK: >{target_tpd} TPD={'✓' if best['tpd']>=target_tpd else '✗'} | >${target_ppd}/day={'✓' if best['ppd']>=target_ppd else '✗'}")
        log(f"  VIABILITY: {'PASS ✓' if viable else 'FAIL ✗'}")
        
        if not viable:
            log(f"\n  REALITY CHECK:")
            log(f"  With $10 capital and 0.1% fees ($0.01/trade round-trip):")
            log(f"  - Need avg profit >$0.01/trade just to break even")
            log(f"  - For $50/day need {int(50/max(best['ppd'],0.001))}x improvement")
            log(f"  - Maker fees (0.02%) reduce cost to $0.004/trade RT")
            log(f"  - Even with maker fees, need sustained 0.5%+ edge per trade")
    
    # Save
    out = f"{RESULTS_DIR}/advanced_backtest_{int(time.time())}.json"
    with open(out, 'w') as f:
        json.dump(results, f, indent=2)
    log(f"\nSaved to: {out}")

if __name__ == '__main__':
    main()
