import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

# Load credentials
load_dotenv('/root/.automaton/bybit-murre.env', override=True)
bybit = ccxt.bybit({
    'apiKey': os.getenv('BYBIT_API_KEY') or os.getenv('BYBIT_REAL_API_KEY'),
    'secret': os.getenv('BYBIT_API_SECRET') or os.getenv('BYBIT_REAL_API_SECRET'),
    'options': {'defaultType': 'spot'}
})
bybit.load_markets()

# V7 CONSERVATIVE PARAMETERS
PARAMS = {
    'rsi_period': 14,
    'rsi_entry': 25,        # Very strict oversold
    'rsi_exit': 70,         # Conservative exit
    'bb_period': 20,
    'bb_std': 2.0,
    'bb_entry_mult': 0.995, # Must be BELOW lower band
    'sl_pct': 2.5,          # Wider stop to avoid noise
    'tp_pct': 4.0,          # Higher target for better R:R
    'trail_activate': 2.0,  # Trail only after meaningful gain
    'trail_offset': 1.0,    # Wider trail
    'fee_rate': 0.001,      # 0.1% taker fee per side
    'min_hold_candles': 6,  # Hold at least 6 candles (30min on 5m)
}

CANDIDATES = ['INJ/USDT', 'FET/USDT', 'SUI/USDT', 'DOGE/USDT', 'ADA/USDT', 
              'NEAR/USDT', 'AVAX/USDT', 'LINK/USDT', 'SOL/USDT', 'UNI/USDT']

def calc_indicators(df):
    closes = df['close']
    delta = closes.diff()
    gain = delta.where(delta > 0, 0).rolling(window=PARAMS['rsi_period']).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=PARAMS['rsi_period']).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    sma = closes.rolling(window=PARAMS['bb_period']).mean()
    std = closes.rolling(window=PARAMS['bb_period']).std()
    df['bb_upper'] = sma + (std * PARAMS['bb_std'])
    df['bb_mid'] = sma
    df['bb_lower'] = sma - (std * PARAMS['bb_std'])
    return df

def run_backtest(symbol, timeframe='5m', limit=1000):
    print(f"\n=== BACKTESTING {symbol} ({limit} candles, {timeframe}) ===")
    
    ohlcv = bybit.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = calc_indicators(df)
    df = df.dropna().reset_index(drop=True)
    
    # Simulation state
    capital = 100.0  # Start with $100 for percentage calculation
    initial_capital = capital
    position = None
    trades = []
    wins = 0
    losses = 0
    
    for i in range(len(df)):
        row = df.iloc[i]
        price = row['close']
        rsi = row['rsi']
        bb_lower = row['bb_lower']
        bb_mid = row['bb_mid']
        bb_upper = row['bb_upper']
        
        if position:
            # Check exit conditions
            hold_duration = i - position['entry_idx']
            pnl_pct = (price - position['entry_price']) / position['entry_price']
            
            exit_reason = None
            
            # Stop Loss
            if pnl_pct <= -PARAMS['sl_pct'] / 100:
                exit_reason = 'SL'
            # Take Profit
            elif pnl_pct >= PARAMS['tp_pct'] / 100:
                exit_reason = 'TP'
            # Trailing Stop (simplified: if was up > trail_activate and now dropped by trail_offset from peak)
            elif pnl_pct >= PARAMS['trail_activate'] / 100:
                # Find peak since entry
                peak = df.iloc[position['entry_idx']:i+1]['high'].max()
                trail_stop = peak * (1 - PARAMS['trail_offset'] / 100)
                if price <= trail_stop:
                    exit_reason = 'TRAIL'
            # RSI Exit (only if profitable and holding long enough)
            elif hold_duration >= PARAMS['min_hold_candles'] and pnl_pct > 0 and rsi > PARAMS['rsi_exit']:
                exit_reason = 'RSI'
            # Timeout (stale position)
            elif hold_duration >= 48 and pnl_pct < 0.005:  # 4h with <0.5% gain
                exit_reason = 'TIMEOUT'
            
            if exit_reason:
                # Execute sell
                sell_fee = position['qty'] * price * PARAMS['fee_rate']
                proceeds = position['qty'] * price - sell_fee
                pnl = proceeds - position['cost']
                capital += proceeds
                
                trade = {
                    'entry_time': df.iloc[position['entry_idx']]['datetime'],
                    'exit_time': row['datetime'],
                    'entry_price': position['entry_price'],
                    'exit_price': price,
                    'pnl': pnl,
                    'pnl_pct': pnl / position['cost'] * 100,
                    'reason': exit_reason,
                    'hold_candles': hold_duration
                }
                trades.append(trade)
                
                if pnl > 0:
                    wins += 1
                else:
                    losses += 1
                
                position = None
        
        else:
            # Check entry conditions
            if (rsi < PARAMS['rsi_entry'] and 
                price <= bb_lower * PARAMS['bb_entry_mult']):
                
                # Calculate position size (98% of capital)
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
    
    # Results
    total_trades = wins + losses
    win_rate = wins / total_trades * 100 if total_trades > 0 else 0
    total_pnl = capital - initial_capital
    avg_win = sum(t['pnl'] for t in trades if t['pnl'] > 0) / wins if wins > 0 else 0
    avg_loss = sum(t['pnl'] for t in trades if t['pnl'] <= 0) / losses if losses > 0 else 0
    
    print(f"Initial Capital: ${initial_capital:.2f}")
    print(f"Final Capital: ${capital:.2f}")
    print(f"Net PnL: ${total_pnl:+.2f} ({total_pnl/initial_capital*100:+.2f}%)")
    print(f"Total Trades: {total_trades} | Wins: {wins} | Losses: {losses}")
    print(f"Win Rate: {win_rate:.1f}%")
    print(f"Avg Win: ${avg_win:+.2f} | Avg Loss: ${avg_loss:+.2f}")
    print(f"Profit Factor: {abs(avg_win * wins / (avg_loss * losses)):.2f}" if losses > 0 and avg_loss != 0 else "Profit Factor: N/A")
    
    # Show last 5 trades
    print(f"\nLast 5 trades:")
    for t in trades[-5:]:
        emoji = "✅" if t['pnl'] > 0 else "❌"
        print(f"  {emoji} {t['entry_time']} -> {t['exit_time']} | {t['reason']:7s} | PnL: ${t['pnl']:+.4f} ({t['pnl_pct']:+.2f}%) | Hold: {t['hold_candles']}c")
    
    return {
        'symbol': symbol,
        'final_capital': capital,
        'net_pnl': total_pnl,
        'win_rate': win_rate,
        'total_trades': total_trades,
        'trades': trades
    }

# Run backtest on top candidates
results = []
for sym in CANDIDATES[:5]:  # Test top 5
    try:
        res = run_backtest(sym, '5m', 1000)
        results.append(res)
    except Exception as e:
        print(f"Error backtesting {sym}: {e}")

# Summary
print("\n" + "="*60)
print("BACKTEST SUMMARY (V7 CONSERVATIVE)")
print("="*60)
for r in results:
    print(f"{r['symbol']:12s} | PnL: ${r['net_pnl']:+7.2f} | WR: {r['win_rate']:5.1f}% | Trades: {r['total_trades']}")

best = max(results, key=lambda x: x['net_pnl'])
print(f"\nBest performer: {best['symbol']} with ${best['net_pnl']:+.2f} PnL")
