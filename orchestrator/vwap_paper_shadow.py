#!/usr/bin/env python3
"""
VWAP Mean-Reversion Paper Shadow Executor
Strategy: Enter when price < VWAP - 2*std, exit when price > VWAP - 0.5*std or max hold
Symbols: XRP/USDT, AVAX/USDT, BCH/USDT
Timeframe: 5m
Execution: PAPER ONLY - no real orders
"""

import ccxt
import json
import os
import time
import statistics
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv('/root/.automaton/bybit-murre.env')

SYMBOLS = ['XRP/USDT', 'AVAX/USDT', 'BCH/USDT']
TIMEFRAME = '5m'
VWAP_PERIOD = 20
ENTRY_BAND = 2.0
EXIT_BAND = 0.5
MAX_HOLD_CANDLES = 48
MAKER_FEE = 0.0002
STATE_FILE = '/Agentic/orchestrator/vwap_shadow_state.json'
LEDGER_FILE = '/Agentic/orchestrator/vwap_shadow_ledger.jsonl'
RECONCILIATION_FILE = '/Agentic/orchestrator/reconciliation_state.json'

def load_state():
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except:
        return {'positions': {}, 'last_run': None, 'trades_count': 0}

def save_state(state):
    state['last_run'] = datetime.now(timezone.utc).isoformat()
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def log_trade(trade):
    trade['timestamp'] = datetime.now(timezone.utc).isoformat()
    with open(LEDGER_FILE, 'a') as f:
        f.write(json.dumps(trade) + '\n')

def calculate_vwap_bands(ohlcv, period):
    """Calculate VWAP and std dev bands for latest candle"""
    if len(ohlcv) < period:
        return None, None, None
    
    window = ohlcv[-period:]
    typical_prices = [(c[2] + c[3] + c[4]) / 3 for c in window]
    volumes = [c[5] for c in window]
    
    sum_tp_vol = sum(tp * v for tp, v in zip(typical_prices, volumes))
    sum_vol = sum(volumes)
    
    if sum_vol == 0:
        return None, None, None
    
    vwap = sum_tp_vol / sum_vol
    deviations = [(c[4] - vwap) ** 2 for c in window]
    std_dev = (sum(deviations) / len(deviations)) ** 0.5
    
    return vwap, std_dev, ohlcv[-1][4]  # Return current close

def run_shadow_cycle():
    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_REAL_API_KEY'),
        'secret': os.getenv('BYBIT_REAL_API_SECRET'),
        'options': {'defaultType': 'spot'},
        'enableRateLimit': True
    })
    
    state = load_state()
    cycle_results = []
    
    for symbol in SYMBOLS:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=VWAP_PERIOD + 10)
            vwap, std_dev, close = calculate_vwap_bands(ohlcv, VWAP_PERIOD)
            
            if vwap is None or std_dev == 0:
                continue
            
            z_score = (close - vwap) / std_dev
            ts = ohlcv[-1][0]
            
            pos_key = symbol.replace('/', '_')
            position = state['positions'].get(pos_key)
            
            if position is None:
                # Check entry condition
                if z_score < -ENTRY_BAND:
                    state['positions'][pos_key] = {
                        'entry_price': close,
                        'entry_ts': ts,
                        'hold_count': 0,
                        'entry_z': round(z_score, 4)
                    }
                    cycle_results.append({
                        'symbol': symbol,
                        'action': 'ENTRY_SIGNAL',
                        'price': close,
                        'z_score': round(z_score, 4),
                        'vwap': round(vwap, 6)
                    })
            else:
                # Update hold count
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
                    
                    trade = {
                        'symbol': symbol,
                        'side': 'sell',
                        'entry_price': position['entry_price'],
                        'exit_price': close,
                        'gross_pnl_pct': round(gross_pnl_pct * 100, 4),
                        'net_pnl_pct': round(net_pnl_pct * 100, 4),
                        'hold_candles': position['hold_count'],
                        'exit_reason': exit_reason,
                        'entry_z': position.get('entry_z', 0),
                        'exit_z': round(z_score, 4)
                    }
                    
                    log_trade(trade)
                    del state['positions'][pos_key]
                    state['trades_count'] = state.get('trades_count', 0) + 1
                    
                    cycle_results.append({
                        'symbol': symbol,
                        'action': 'EXIT',
                        'reason': exit_reason,
                        'net_pnl_pct': trade['net_pnl_pct'],
                        'hold_candles': position['hold_count']
                    })
                else:
                    cycle_results.append({
                        'symbol': symbol,
                        'action': 'HOLD',
                        'hold_count': position['hold_count'],
                        'current_z': round(z_score, 4)
                    })
        
        except Exception as e:
            cycle_results.append({'symbol': symbol, 'error': str(e)})
    
    save_state(state)
    return cycle_results

if __name__ == '__main__':
    results = run_shadow_cycle()
    print(json.dumps({
        'cycle_time': datetime.now(timezone.utc).isoformat(),
        'results': results,
        'state_file': STATE_FILE,
        'ledger_file': LEDGER_FILE
    }, indent=2))
