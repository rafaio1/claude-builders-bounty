import ccxt
import numpy as np
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv('/root/.automaton/bybit-murre.env', override=True)
bybit = ccxt.bybit({
    'apiKey': os.getenv('BYBIT_API_KEY') or os.getenv('BYBIT_REAL_API_KEY'),
    'secret': os.getenv('BYBIT_API_SECRET') or os.getenv('BYBIT_REAL_API_SECRET'),
    'options': {'defaultType': 'spot'}
})
bybit.load_markets()

# V8 MOMENTUM SCALPING PARAMETERS
PARAMS = {
    'rsi_period': 14,
    'rsi_entry': 30,        # Oversold but not extreme
    'rsi_exit': 65,         # Exit before overbought
    'bb_period': 20,
    'bb_std': 2.0,
    'vol_ma_period': 20,    # Volume moving average
    'vol_mult': 1.5,        # Volume must be 1.5x above average
    'sl_pct': 1.5,          # Tight stop for scalping
    'tp_pct': 2.5,          # Quick profit target
    'trail_activate': 1.2,  # Trail after 1.2% gain
    'trail_offset': 0.5,    # Tight trail to lock profits
    'fee_rate': 0.001,      # 0.1% taker
    'min_hold_candles': 3,  # Min 15min hold
    'max_hold_candles': 36, # Max 3h hold (scalp timeout)
}

CANDIDATES = ['INJ/USDT', 'FET/USDT', 'SUI/USDT', 'DOGE/USDT', 'ADA/USDT', 
              'NEAR/USDT', 'AVAX/USDT', 'LINK/USDT', 'SOL/USDT', 'UNI/USDT']

def calc_rsi(closes, period):
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.convolve(gains, np.ones(period)/period, mode='valid')
    avg_loss = np.convolve(losses, np.ones(period)/period, mode='valid')
    rs = avg_gain / (avg_loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calc_bb(closes, period, std_mult):
    sma = np.convolve(closes, np.ones(period)/period, mode='valid')
    std = np.array([np.std(closes[i:i+period]) for i in range(len(closes)-period+1)])
    upper = sma + std_mult * std
    lower = sma - std_mult * std
    return sma, upper, lower

def calc_vol_ma(volumes, period):
    return np.convolve(volumes, np.ones(period)/period, mode='valid')

def run_backtest(symbol, timeframe='5m', limit=1000):
    print(f"\n=== V8 BACKTEST: {symbol} ({limit} candles) ===")
    
    ohlcv = bybit.fetch_ohlcv(symbol, timeframe, limit=limit)
    timestamps = [c[0] for c in ohlcv]
    opens = np.array([c[1] for c in ohlcv])
    highs = np.array([c[2] for c in ohlcv])
    lows = np.array([c[3] for c in ohlcv])
    closes = np.array([c[4] for c in ohlcv])
    volumes = np.array([c[5] for c in ohlcv])
    
    # Calculate indicators
    rsi = calc_rsi(closes, PARAMS['rsi_period'])
    bb_mid, bb_upper, bb_lower = calc_bb(closes, PARAMS['bb_period'], PARAMS['bb_std'])
    vol_ma = calc_vol_ma(volumes, PARAMS['vol_ma_period'])
    
    # Align arrays (indicators start later due to rolling windows)
    offset = max(PARAMS['rsi_period'], PARAMS['bb_period'], PARAMS['vol_ma_period'])
    rsi = rsi[offset-1:]
    bb_mid = bb_mid[:len(rsi)]
    bb_upper = bb_upper[:len(rsi)]
    bb_lower = bb_lower[:len(rsi)]
    vol_ma = vol_ma[-len(rsi):]
    closes_aligned = closes[-len(rsi):]
    highs_aligned = highs[-len(rsi):]
    timestamps_aligned = timestamps[-len(rsi):]
    volumes_aligned = volumes[-len(rsi):]
    
    # Simulation
    capital = 100.0
    initial_capital = 100.0
    position = None
    trades = []
    wins = 0
    losses = 0
    
    for i in range(len(rsi)):
        price = closes_aligned[i]
        curr_rsi = rsi[i]
        curr_bb_lower = bb_lower[i]
        curr_vol = volumes_aligned[i]
        curr_vol_ma = vol_ma[i]
        
        if position:
            hold_duration = i - position['entry_idx']
            pnl_pct = (price - position['entry_price']) / position['entry_price']
            
            exit_reason = None
            
            if pnl_pct <= -PARAMS['sl_pct'] / 100:
                exit_reason = 'SL'
            elif pnl_pct >= PARAMS['tp_pct'] / 100:
                exit_reason = 'TP'
            elif pnl_pct >= PARAMS['trail_activate'] / 100:
                peak = max(highs_aligned[position['entry_idx']:i+1])
                trail_stop = peak * (1 - PARAMS['trail_offset'] / 100)
                if price <= trail_stop:
                    exit_reason = 'TRAIL'
            elif hold_duration >= PARAMS['min_hold_candles'] and curr_rsi > PARAMS['rsi_exit'] and pnl_pct > 0:
                exit_reason = 'RSI'
            elif hold_duration >= PARAMS['max_hold_candles']:
                exit_reason = 'TIMEOUT'
            
            if exit_reason:
                sell_fee = position['qty'] * price * PARAMS['fee_rate']
                proceeds = position['qty'] * price - sell_fee
                pnl = proceeds - position['cost']
                capital += proceeds
                
                trades.append({
                    'entry_time': datetime.utcfromtimestamp(timestamps_aligned[position['entry_idx']]/1000),
                    'exit_time': datetime.utcfromtimestamp(timestamps_aligned[i]/1000),
                    'entry_price': position['entry_price'],
                    'exit_price': price,
                    'pnl': pnl,
                    'pnl_pct': pnl / position['cost'] * 100,
                    'reason': exit_reason,
                    'hold': hold_duration
                })
                
                if pnl > 0: wins += 1
                else: losses += 1
                position = None
        
        else:
            # Entry: RSI oversold + price at/below BB lower + volume spike
            vol_spike = curr_vol > curr_vol_ma * PARAMS['vol_mult']
            at_bb = price <= curr_bb_lower * 1.002
            
            if curr_rsi < PARAMS['rsi_entry'] and at_bb and vol_spike:
                invest = capital * 0.98
                buy_fee = invest * PARAMS['fee_rate']
                qty = (invest - buy_fee) / price
                position = {
                    'entry_idx': i,
                    'entry_price': price,
                    'qty': qty,
                    'cost': invest
                }
                capital -= invest
    
    total_trades = wins + losses
    win_rate = wins / total_trades * 100 if total_trades > 0 else 0
    net_pnl = capital - initial_capital
    avg_win = sum(t['pnl'] for t in trades if t['pnl'] > 0) / wins if wins > 0 else 0
    avg_loss = sum(t['pnl'] for t in trades if t['pnl'] <= 0) / losses if losses > 0 else 0
    
    print(f"Capital: ${initial_capital:.2f} -> ${capital:.2f} | PnL: ${net_pnl:+.2f} ({net_pnl/initial_capital*100:+.2f}%)")
    print(f"Trades: {total_trades} | W:{wins} L:{losses} | WR: {win_rate:.1f}%")
    print(f"Avg Win: ${avg_win:+.2f} | Avg Loss: ${avg_loss:+.2f}")
    if losses > 0 and avg_loss != 0:
        print(f"Profit Factor: {abs(avg_win * wins / (avg_loss * losses)):.2f}")
    
    for t in trades[-5:]:
        e = "✅" if t['pnl'] > 0 else "❌"
        print(f"  {e} {t['entry_time'].strftime('%m-%d %H:%M')} -> {t['exit_time'].strftime('%H:%M')} | {t['reason']:7s} | ${t['pnl']:+.4f} ({t['pnl_pct']:+.2f}%)")
    
    return {'symbol': symbol, 'net_pnl': net_pnl, 'win_rate': win_rate, 'trades': total_trades, 'final': capital}

results = []
for sym in CANDIDATES:
    try:
        r = run_backtest(sym, '5m', 1000)
        results.append(r)
    except Exception as e:
        print(f"ERR {sym}: {e}")

print("\n" + "="*70)
print("V8 MOMENTUM SCALPING SUMMARY")
print("="*70)
for r in sorted(results, key=lambda x: x['net_pnl'], reverse=True):
    print(f"{r['symbol']:12s} | PnL: ${r['net_pnl']:+7.2f} | WR: {r['win_rate']:5.1f}% | Trades: {r['trades']}")

best = max(results, key=lambda x: x['net_pnl'])
print(f"\n🏆 Best: {best['symbol']} with ${best['net_pnl']:+.2f} PnL")
