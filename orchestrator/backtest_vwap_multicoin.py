#!/usr/bin/env python3
"""
VWAP Mean-Reversion Backtest — Multi-Coin Universe
Walk-forward backtest for expanded 11-symbol VWAP strategy.
Uses 7d of 1m data aggregated to 5m candles.
"""

import ccxt
import os
import json
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv('/root/.automaton/bybit-murre.env')

SYMBOLS = [
    'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT',
    'DOGE/USDT', 'LINK/USDT', 'SUI/USDT', 'WLD/USDT',
    'AAVE/USDT', 'AVAX/USDT', 'BCH/USDT'
]

TIMEFRAME = '5m'
VWAP_PERIOD = 20
ENTRY_BAND = 2.0
EXIT_BAND = 0.5
MAX_HOLD_CANDLES = 48
MAKER_FEE = 0.0002
CANDLE_LIMIT = 2000  # ~7 days of 5m candles

def fetch_ohlcv_safe(exchange, symbol, timeframe, limit):
    """Fetch OHLCV with retry and rate limit handling."""
    for attempt in range(3):
        try:
            data = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            return data
        except Exception as e:
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
            else:
                print(f"  FAIL {symbol}: {e}")
                return None

def run_backtest(ohlcv_data, symbol):
    """Run VWAP mean-reversion backtest on OHLCV data."""
    trades = []
    position = None
    
    for i in range(VWAP_PERIOD, len(ohlcv_data)):
        window = ohlcv_data[i-VWAP_PERIOD:i]
        typical_prices = [(c[2] + c[3] + c[4]) / 3 for c in window]
        volumes = [c[5] for c in window]
        
        sum_tp_vol = sum(tp * v for tp, v in zip(typical_prices, volumes))
        sum_vol = sum(volumes)
        
        if sum_vol == 0:
            continue
        
        vwap = sum_tp_vol / sum_vol
        deviations = [(c[4] - vwap) ** 2 for c in window]
        std_dev = (sum(deviations) / len(deviations)) ** 0.5
        
        if std_dev == 0:
            continue
        
        close = ohlcv_data[i][4]
        z_score = (close - vwap) / std_dev
        ts = ohlcv_data[i][0]
        
        if position is None:
            # Entry condition
            if z_score < -ENTRY_BAND:
                position = {
                    'entry_price': close,
                    'entry_ts': ts,
                    'hold_count': 0,
                    'entry_z': z_score
                }
        else:
            position['hold_count'] += 1
            
            should_exit = False
            exit_reason = ''
            
            if z_score > -EXIT_BAND:
                should_exit = True
                exit_reason = 'vwap_reversion'
            elif position['hold_count'] >= MAX_HOLD_CANDLES:
                should_exit = True
                exit_reason = 'max_hold'
            
            if should_exit:
                gross_pnl_pct = (close - position['entry_price']) / position['entry_price']
                net_pnl_pct = gross_pnl_pct - (2 * MAKER_FEE)
                
                trades.append({
                    'symbol': symbol,
                    'entry_price': position['entry_price'],
                    'exit_price': close,
                    'gross_pnl_pct': round(gross_pnl_pct * 100, 4),
                    'net_pnl_pct': round(net_pnl_pct * 100, 4),
                    'hold_candles': position['hold_count'],
                    'exit_reason': exit_reason,
                    'entry_z': round(position['entry_z'], 4),
                    'exit_z': round(z_score, 4),
                    'entry_ts': position['entry_ts'],
                    'exit_ts': ts
                })
                position = None
    
    return trades

def main():
    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_REAL_API_KEY'),
        'secret': os.getenv('BYBIT_REAL_API_SECRET'),
        'options': {'defaultType': 'spot'},
        'enableRateLimit': True
    })
    
    all_results = {}
    total_trades = 0
    total_net_pnl = 0.0
    
    print(f"[BACKTEST_VWAP] Starting multi-coin backtest | {len(SYMBOLS)} symbols | {CANDLE_LIMIT} candles each")
    print(f"[BACKTEST_VWAP] Params: VWAP={VWAP_PERIOD} | Entry={ENTRY_BAND}σ | Exit={EXIT_BAND}σ | MaxHold={MAX_HOLD_CANDLES} | Fee={MAKER_FEE*100}%")
    print("=" * 80)
    
    for symbol in SYMBOLS:
        print(f"\nFetching {symbol}...", flush=True)
        ohlcv = fetch_ohlcv_safe(exchange, symbol, TIMEFRAME, CANDLE_LIMIT)
        
        if ohlcv is None or len(ohlcv) < VWAP_PERIOD + 10:
            print(f"  SKIP {symbol}: insufficient data")
            continue
        
        print(f"  Got {len(ohlcv)} candles ({ohlcv[0][0]} → {ohlcv[-1][0]})")
        trades = run_backtest(ohlcv, symbol)
        
        n_trades = len(trades)
        wins = sum(1 for t in trades if t['net_pnl_pct'] > 0)
        win_rate = (wins / n_trades * 100) if n_trades > 0 else 0
        avg_net = sum(t['net_pnl_pct'] for t in trades) / n_trades if n_trades > 0 else 0
        total_net = sum(t['net_pnl_pct'] for t in trades)
        
        result = {
            'symbol': symbol,
            'trades': n_trades,
            'wins': wins,
            'win_rate': round(win_rate, 1),
            'avg_net_pnl_pct': round(avg_net, 4),
            'total_net_pnl_pct': round(total_net, 4),
            'candles': len(ohlcv),
            'trade_details': trades
        }
        all_results[symbol] = result
        
        total_trades += n_trades
        total_net_pnl += total_net
        
        status = "✅" if avg_net > 0 else "❌"
        print(f"  {status} {symbol}: {n_trades} trades | WR={win_rate:.1f}% | Avg={avg_net:+.4f}% | Total={total_net:+.4f}%")
    
    print("\n" + "=" * 80)
    print(f"[SUMMARY] Total: {total_trades} trades across {len(all_results)} symbols")
    print(f"[SUMMARY] Aggregate Net PnL: {total_net_pnl:+.4f}%")
    print(f"[SUMMARY] Avg per symbol: {total_net_pnl/len(all_results):+.4f}%")
    
    # Promotion gate check
    positive_symbols = sum(1 for r in all_results.values() if r['avg_net_pnl_pct'] > 0)
    overall_positive = total_net_pnl > 0
    
    print(f"\n[PROMOTION_GATE]")
    print(f"  Symbols with positive expectation: {positive_symbols}/{len(all_results)}")
    print(f"  Overall net PnL positive: {overall_positive}")
    print(f"  Verdict: {'PASS ✅' if overall_positive and positive_symbols >= len(all_results)//2 else 'FAIL ❌'}")
    
    # Save results
    output_file = '/Agentic/orchestrator/backtest_vwap_multicoin_results.json'
    with open(output_file, 'w') as f:
        json.dump({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'params': {
                'vwap_period': VWAP_PERIOD,
                'entry_band': ENTRY_BAND,
                'exit_band': EXIT_BAND,
                'max_hold': MAX_HOLD_CANDLES,
                'maker_fee': MAKER_FEE,
                'timeframe': TIMEFRAME,
                'candle_limit': CANDLE_LIMIT
            },
            'summary': {
                'total_trades': total_trades,
                'total_net_pnl_pct': round(total_net_pnl, 4),
                'symbols_tested': len(all_results),
                'positive_symbols': positive_symbols,
                'promotion_pass': overall_positive and positive_symbols >= len(all_results)//2
            },
            'per_symbol': {k: {kk: vv for kk, vv in v.items() if kk != 'trade_details'} for k, v in all_results.items()},
            'all_trades': [t for r in all_results.values() for t in r['trade_details']]
        }, f, indent=2)
    
    print(f"\nResults saved to {output_file}")

if __name__ == '__main__':
    main()
