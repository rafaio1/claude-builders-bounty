#!/usr/bin/env python3
"""Backtest Engine for Bybit Spot - High Frequency Strategies.
Downloads real kline data and simulates trades with exact fees.
"""
import ccxt, os, sys, json, time, math, csv
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv('/root/.automaton/bybit-murre.env', override=True)

DATA_DIR = '/Agentic/orchestrator/backtest_data'
RESULTS_DIR = '/Agentic/orchestrator/backtest_results'
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

FEE_RATE = 0.001  # 0.1% per side (no BNB on Bybit)

def log(msg):
    ts = datetime.now(timezone.utc).strftime('%H:%M:%S')
    print(f"[{ts}] {msg}", flush=True)

def get_exchange():
    return ccxt.bybit({
        'apiKey': os.getenv('BYBIT_REAL_API_KEY'),
        'secret': os.getenv('BYBIT_REAL_API_SECRET'),
        'options': {'defaultType': 'spot'}
    })

def download_klines(symbol, timeframe='1m', limit=1000, days_back=3):
    """Download recent klines from Bybit."""
    ex = get_exchange()
    ex.load_markets()
    
    all_klines = []
    since = int((datetime.now(timezone.utc) - timedelta(days=days_back)).timestamp() * 1000)
    
    log(f"Downloading {symbol} {timeframe} klines ({days_back} days)...")
    
    while True:
        try:
            klines = ex.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)
            if not klines:
                break
            all_klines.extend(klines)
            since = klines[-1][0] + 1
            if len(klines) < limit:
                break
            time.sleep(0.2)  # Rate limit
        except Exception as e:
            log(f"  Download error: {e}")
            break
    
    # Save to CSV
    filename = f"{DATA_DIR}/{symbol.replace('/', '_')}_{timeframe}.csv"
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        for k in all_klines:
            writer.writerow(k)
    
    log(f"  Saved {len(all_klines)} candles to {filename}")
    return all_klines

def load_klines(symbol, timeframe='1m'):
    """Load klines from CSV."""
    filename = f"{DATA_DIR}/{symbol.replace('/', '_')}_{timeframe}.csv"
    klines = []
    with open(filename, 'r') as f:
        reader = csv.reader(f)
        next(reader)  # Skip header
        for row in reader:
            klines.append([float(x) for x in row])
    return klines

class BacktestResult:
    def __init__(self, strategy_name, symbol):
        self.strategy = strategy_name
        self.symbol = symbol
        self.trades = []
        self.wins = 0
        self.losses = 0
        self.total_pnl = 0.0
        self.total_fees = 0.0
        self.max_drawdown = 0.0
        self.peak_equity = 0.0
        
    def add_trade(self, entry_price, exit_price, qty, entry_time, exit_time, reason):
        gross_pnl = (exit_price - entry_price) * qty
        fees = (entry_price * qty + exit_price * qty) * FEE_RATE
        net_pnl = gross_pnl - fees
        
        self.trades.append({
            'entry_time': entry_time,
            'exit_time': exit_time,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'qty': qty,
            'gross_pnl': round(gross_pnl, 6),
            'fees': round(fees, 6),
            'net_pnl': round(net_pnl, 6),
            'reason': reason
        })
        
        self.total_pnl += net_pnl
        self.total_fees += fees
        
        if net_pnl > 0:
            self.wins += 1
        else:
            self.losses += 1
            
        # Track drawdown
        equity = self.total_pnl
        if equity > self.peak_equity:
            self.peak_equity = equity
        dd = self.peak_equity - equity
        if dd > self.max_drawdown:
            self.max_drawdown = dd
    
    def summary(self):
        total_trades = self.wins + self.losses
        win_rate = (self.wins / total_trades * 100) if total_trades > 0 else 0
        
        # Calculate trades per day
        if self.trades:
            first_ts = self.trades[0]['entry_time']
            last_ts = self.trades[-1]['exit_time']
            days = max(1, (last_ts - first_ts) / (24 * 3600 * 1000))
            trades_per_day = total_trades / days
            pnl_per_day = self.total_pnl / days
        else:
            days = 1
            trades_per_day = 0
            pnl_per_day = 0
        
        avg_win = sum(t['net_pnl'] for t in self.trades if t['net_pnl'] > 0) / max(1, self.wins)
        avg_loss = sum(t['net_pnl'] for t in self.trades if t['net_pnl'] <= 0) / max(1, self.losses)
        
        return {
            'strategy': self.strategy,
            'symbol': self.symbol,
            'total_trades': total_trades,
            'wins': self.wins,
            'losses': self.losses,
            'win_rate_pct': round(win_rate, 2),
            'total_pnl_usdt': round(self.total_pnl, 4),
            'total_fees_usdt': round(self.total_fees, 4),
            'net_after_fees_usdt': round(self.total_pnl, 4),
            'avg_win_usdt': round(avg_win, 6),
            'avg_loss_usdt': round(avg_loss, 6),
            'max_drawdown_usdt': round(self.max_drawdown, 4),
            'trades_per_day': round(trades_per_day, 1),
            'pnl_per_day_usdt': round(pnl_per_day, 4),
            'days_tested': round(days, 2),
            'profit_factor': round(abs(sum(t['net_pnl'] for t in self.trades if t['net_pnl'] > 0) / sum(t['net_pnl'] for t in self.trades if t['net_pnl'] <= 0)), 2) if self.losses > 0 else float('inf')
        }

# Strategy 1: Mean Reversion Micro-Scalp
def backtest_mean_reversion(klines, symbol, capital=10.0):
    """Buy when price drops N% below SMA, sell when reverts."""
    result = BacktestResult("MeanReversion_MicroScalp", symbol)
    
    sma_period = 20
    entry_threshold = 0.003  # 0.3% below SMA
    exit_threshold = 0.001   # 0.1% above SMA (or at SMA)
    stop_loss = 0.005        # 0.5% stop
    
    position = None
    
    for i in range(sma_period, len(klines)):
        ts = klines[i][0]
        close = klines[i][4]
        
        # Calculate SMA
        sma = sum(k[4] for k in klines[i-sma_period:i]) / sma_period
        
        deviation = (close - sma) / sma
        
        if position is None:
            # Entry: price significantly below SMA
            if deviation < -entry_threshold:
                qty = capital / close
                position = {'entry_price': close, 'entry_time': ts, 'qty': qty}
        else:
            # Exit conditions
            pnl_pct = (close - position['entry_price']) / position['entry_price']
            
            if pnl_pct >= exit_threshold or deviation >= 0:
                # Take profit
                result.add_trade(position['entry_price'], close, position['qty'], 
                               position['entry_time'], ts, "TP_REVERSION")
                position = None
            elif pnl_pct <= -stop_loss:
                # Stop loss
                result.add_trade(position['entry_price'], close, position['qty'],
                               position['entry_time'], ts, "STOP_LOSS")
                position = None
    
    # Close any open position at end
    if position:
        last_close = klines[-1][4]
        result.add_trade(position['entry_price'], last_close, position['qty'],
                       position['entry_time'], klines[-1][0], "END_OF_DATA")
    
    return result

# Strategy 2: Bollinger Band Squeeze Breakout
def backtest_bb_breakout(klines, symbol, capital=10.0):
    """Enter on BB squeeze breakout, exit on mean reversion or timeout."""
    result = BacktestResult("BB_Squeeze_Breakout", symbol)
    
    bb_period = 20
    bb_std = 2.0
    squeeze_threshold = 0.02  # BB width < 2% = squeeze
    
    position = None
    hold_bars = 0
    max_hold = 30  # Max 30 bars (~30 min on 1m)
    
    for i in range(bb_period, len(klines)):
        ts = klines[i][0]
        close = klines[i][4]
        high = klines[i][2]
        low = klines[i][3]
        
        # Calculate BB
        prices = [k[4] for k in klines[i-bb_period:i]]
        sma = sum(prices) / bb_period
        variance = sum((p - sma) ** 2 for p in prices) / bb_period
        std = math.sqrt(variance)
        upper = sma + bb_std * std
        lower = sma - bb_std * std
        width = (upper - lower) / sma
        
        if position is None:
            # Entry: squeeze detected + breakout above upper band
            if width < squeeze_threshold and close > upper:
                qty = capital / close
                position = {'entry_price': close, 'entry_time': ts, 'qty': qty}
                hold_bars = 0
        else:
            hold_bars += 1
            pnl_pct = (close - position['entry_price']) / position['entry_price']
            
            # Exit: price returns to SMA or timeout or stop
            if close <= sma:
                result.add_trade(position['entry_price'], close, position['qty'],
                               position['entry_time'], ts, "TP_SMA_RETURN")
                position = None
            elif hold_bars >= max_hold:
                result.add_trade(position['entry_price'], close, position['qty'],
                               position['entry_time'], ts, "TIMEOUT")
                position = None
            elif pnl_pct <= -0.008:  # 0.8% stop
                result.add_trade(position['entry_price'], close, position['qty'],
                               position['entry_time'], ts, "STOP_LOSS")
                position = None
    
    if position:
        last_close = klines[-1][4]
        result.add_trade(position['entry_price'], last_close, position['qty'],
                       position['entry_time'], klines[-1][0], "END_OF_DATA")
    
    return result

# Strategy 3: Volume Spike Momentum
def backtest_volume_spike(klines, symbol, capital=10.0):
    """Enter on volume spike + price momentum, quick scalp."""
    result = BacktestResult("Volume_Spike_Momentum", symbol)
    
    vol_period = 20
    vol_multiplier = 2.0  # Volume > 2x average
    price_momentum = 0.002  # Price up 0.2% in last bar
    tp_pct = 0.003  # 0.3% take profit
    sl_pct = 0.004  # 0.4% stop loss
    max_hold = 15
    
    position = None
    hold_bars = 0
    
    for i in range(vol_period, len(klines)):
        ts = klines[i][0]
        close = klines[i][4]
        volume = klines[i][5]
        prev_close = klines[i-1][4]
        
        # Average volume
        avg_vol = sum(k[5] for k in klines[i-vol_period:i]) / vol_period
        
        # Price change
        price_chg = (close - prev_close) / prev_close
        
        if position is None:
            # Entry: volume spike + positive momentum
            if volume > avg_vol * vol_multiplier and price_chg > price_momentum:
                qty = capital / close
                position = {'entry_price': close, 'entry_time': ts, 'qty': qty}
                hold_bars = 0
        else:
            hold_bars += 1
            pnl_pct = (close - position['entry_price']) / position['entry_price']
            
            if pnl_pct >= tp_pct:
                result.add_trade(position['entry_price'], close, position['qty'],
                               position['entry_time'], ts, "TAKE_PROFIT")
                position = None
            elif pnl_pct <= -sl_pct:
                result.add_trade(position['entry_price'], close, position['qty'],
                               position['entry_time'], ts, "STOP_LOSS")
                position = None
            elif hold_bars >= max_hold:
                result.add_trade(position['entry_price'], close, position['qty'],
                               position['entry_time'], ts, "TIMEOUT")
                position = None
    
    if position:
        last_close = klines[-1][4]
        result.add_trade(position['entry_price'], last_close, position['qty'],
                       position['entry_time'], klines[-1][0], "END_OF_DATA")
    
    return result

def main():
    symbols = ['XRP/USDT', 'DOGE/USDT', 'BTC/USDT']
    capital = 10.0
    
    log("=" * 60)
    log("BACKTEST ENGINE - BYBIT SPOT HIGH FREQUENCY")
    log(f"Capital: {capital} USDT | Fee: {FEE_RATE*100}% per side")
    log("=" * 60)
    
    all_results = []
    
    for symbol in symbols:
        log(f"\n--- Testing {symbol} ---")
        
        # Download data
        klines = download_klines(symbol, '1m', limit=1000, days_back=3)
        if len(klines) < 100:
            log(f"  Insufficient data for {symbol}, skipping")
            continue
        
        log(f"  Data: {len(klines)} candles, {klines[0][0]} to {klines[-1][0]}")
        
        # Run strategies
        r1 = backtest_mean_reversion(klines, symbol, capital)
        r2 = backtest_bb_breakout(klines, symbol, capital)
        r3 = backtest_volume_spike(klines, symbol, capital)
        
        for r in [r1, r2, r3]:
            summary = r.summary()
            all_results.append(summary)
            log(f"  {r.strategy}: {summary['total_trades']} trades, WR={summary['win_rate_pct']}%, PnL={summary['total_pnl_usdt']:.4f}, TPD={summary['trades_per_day']:.1f}, PnL/day={summary['pnl_per_day_usdt']:.4f}")
    
    # Save results
    results_file = f"{RESULTS_DIR}/backtest_summary_{int(time.time())}.json"
    with open(results_file, 'w') as f:
        json.dump(all_results, f, indent=2)
    
    log(f"\n{'='*60}")
    log("BACKTEST SUMMARY")
    log(f"{'='*60}")
    log(f"{'Strategy':<30} {'Symbol':<12} {'Trades':>7} {'WR%':>6} {'PnL':>10} {'TPD':>6} {'PnL/d':>10}")
    log("-" * 85)
    
    best_result = None
    best_score = -999
    
    for r in all_results:
        score = r['pnl_per_day_usdt'] * (r['win_rate_pct'] / 100) * min(r['trades_per_day'] / 100, 1.0)
        marker = ""
        if score > best_score:
            best_score = score
            best_result = r
            marker = " <-- BEST"
        
        log(f"{r['strategy']:<30} {r['symbol']:<12} {r['total_trades']:>7} {r['win_rate_pct']:>6.1f} {r['total_pnl_usdt']:>10.4f} {r['trades_per_day']:>6.1f} {r['pnl_per_day_usdt']:>10.4f}{marker}")
    
    log(f"\nResults saved to: {results_file}")
    
    if best_result:
        log(f"\nBEST STRATEGY: {best_result['strategy']} on {best_result['symbol']}")
        log(f"  Trades/day: {best_result['trades_per_day']:.1f} (target: >100)")
        log(f"  PnL/day: {best_result['pnl_per_day_usdt']:.4f} USDT (target: >50)")
        log(f"  Win rate: {best_result['win_rate_pct']:.1f}%")
        log(f"  Profit factor: {best_result['profit_factor']}")
        
        # Viability check
        viable = best_result['trades_per_day'] >= 100 and best_result['pnl_per_day_usdt'] >= 50
        log(f"\n  VIABILITY: {'PASS ✓' if viable else 'FAIL ✗'}")
        if not viable:
            needed_tpd = 100
            needed_pnl = 50
            log(f"  Gap: need {needed_tpd} TPD (have {best_result['trades_per_day']:.1f}), need ${needed_pnl}/day (have ${best_result['pnl_per_day_usdt']:.4f})")
    
    return all_results

if __name__ == '__main__':
    main()
