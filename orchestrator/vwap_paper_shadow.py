#!/usr/bin/env python3
"""
VWAP Mean-Reversion Paper Shadow Executor (Multi-Coin + Safety Controls)
Strategy: Enter when price < VWAP - 2*std, exit when price > VWAP - 0.5*std or max hold
Symbols: 11 liquid spot pairs on Bybit
Timeframe: 5m
Execution: PAPER ONLY - no real orders
Safety: Kill switch, daily loss limit, min balance, consecutive error halt
"""

import ccxt
import json
import os
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv('/root/.automaton/bybit-murre.env')

# === CONFIGURATION ===
SYMBOLS = [
    'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT',
    'DOGE/USDT', 'LINK/USDT', 'SUI/USDT', 'WLD/USDT',
    'AAVE/USDT', 'AVAX/USDT', 'BCH/USDT'
]
TIMEFRAME = '5m'
VWAP_PERIOD = 20
ENTRY_BAND = 2.0       # DO NOT REDUCE BELOW 2.0 sigma - backtest validated
EXIT_BAND = 0.5
MAX_HOLD_CANDLES = 48
MAKER_FEE = 0.0002

# === SAFETY PARAMETERS ===
MIN_BALANCE_USDT = 3.0
DAILY_LOSS_LIMIT_PCT = -1.0
MAX_CONSECUTIVE_ERRORS = 3

# === FILE PATHS ===
STATE_FILE = '/Agentic/orchestrator/vwap_shadow_state.json'
LEDGER_FILE = '/Agentic/orchestrator/vwap_shadow_ledger.jsonl'
RECONCILIATION_FILE = '/Agentic/orchestrator/reconciliation_state.json'


# === SAFETY CONTROLS ===
def check_kill_switch():
    kill = os.getenv('AGENTIC_LIVE_TRADE', '1')
    if str(kill).strip() == '0':
        print('[KILL_SWITCH] AGENTIC_LIVE_TRADE=0 detected. Halting shadow executor.', flush=True)
        return False
    return True


def check_daily_loss_limit(state):
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    daily_key = f'daily_pnl_{today}'
    daily_pnl = state.get(daily_key, 0.0)
    if daily_pnl < DAILY_LOSS_LIMIT_PCT:
        print(f'[RISK_GUARD] Daily loss limit breached: {daily_pnl:.4f}% < {DAILY_LOSS_LIMIT_PCT}%. Blocking new entries.', flush=True)
        return False
    return True


def record_trade_pnl(state, net_pnl_pct):
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    daily_key = f'daily_pnl_{today}'
    state[daily_key] = state.get(daily_key, 0.0) + net_pnl_pct
    return state


def check_balance(exchange):
    try:
        balance = exchange.fetch_balance()
        usdt_free = float(balance.get('USDT', {}).get('free', 0))
        if usdt_free < MIN_BALANCE_USDT:
            print(f'[BALANCE_GUARD] USDT balance {usdt_free:.2f} < {MIN_BALANCE_USDT}. Blocking new entries.', flush=True)
            return False
        return True
    except Exception as e:
        print(f'[BALANCE_GUARD] Failed to fetch balance: {e}', flush=True)
        return False


# === STATE MANAGEMENT ===
def load_state():
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {'positions': {}, 'last_run': None, 'trades_count': 0}


def save_state(state):
    state['last_run'] = datetime.now(timezone.utc).isoformat()
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def log_trade(trade):
    trade['timestamp'] = datetime.now(timezone.utc).isoformat()
    with open(LEDGER_FILE, 'a') as f:
     f.write(json.dumps(trade) + '\n')


# === STRATEGY LOGIC ===
def calculate_vwap_bands(ohlcv, period):
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

    return vwap, std_dev, ohlcv[-1][4]


def run_shadow_cycle():
    if not check_kill_switch():
        return [{'action': 'HALTED', 'reason': 'kill_switch'}]

    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_REAL_API_KEY'),
        'secret': os.getenv('BYBIT_REAL_API_SECRET'),
        'options': {'defaultType': 'spot'},
        'enableRateLimit': True
    })

    state = load_state()
    cycle_results = []

    balance_ok = check_balance(exchange)
    loss_limit_ok = check_daily_loss_limit(state)
    can_enter = balance_ok and loss_limit_ok

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
                if z_score < -ENTRY_BAND and can_enter:
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
                elif z_score < -ENTRY_BAND and not can_enter:
                    cycle_results.append({
                        'symbol': symbol,
                        'action': 'ENTRY_BLOCKED',
                        'reason': 'balance_or_loss_limit',
                        'z_score': round(z_score, 4)
                    })
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
                    state = record_trade_pnl(state, net_pnl_pct * 100)
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


# === MAIN LOOP ===
if __name__ == '__main__':
    if not check_kill_switch():
        print('[FATAL] Kill switch active at startup. Exiting.', flush=True)
        exit(0)

    print(f'[VWAP_SHADOW] Starting continuous loop | Symbols: {len(SYMBOLS)} coins | TF: {TIMEFRAME}', flush=True)
    print(f'[VWAP_SHADOW] Entry band: {ENTRY_BAND}sigma | Exit band: {EXIT_BAND}sigma | Max hold: {MAX_HOLD_CANDLES} candles', flush=True)
    print(f'[VWAP_SHADOW] Safety: KillSwitch=ON | DailyLossLimit={DAILY_LOSS_LIMIT_PCT}% | MinBalance={MIN_BALANCE_USDT} USDT | MaxErrors={MAX_CONSECUTIVE_ERRORS}', flush=True)

    consecutive_errors = 0

    while True:
        try:
            if not check_kill_switch():
                print('[KILL_SWITCH] Detected mid-loop. Graceful shutdown.', flush=True)
                break

            results = run_shadow_cycle()
            consecutive_errors = 0

            output = {
                'cycle_time': datetime.now(timezone.utc).isoformat(),
                'results': results,
                'state_file': STATE_FILE,
                'ledger_file': LEDGER_FILE
            }
            print(json.dumps(output, indent=2), flush=True)

            entries = sum(1 for r in results if r.get('action') == 'ENTRY_SIGNAL')
            exits = sum(1 for r in results if r.get('action') == 'EXIT')
            holds = sum(1 for r in results if r.get('action') == 'HOLD')
            blocked = sum(1 for r in results if r.get('action') == 'ENTRY_BLOCKED')
            errors = sum(1 for r in results if 'error' in r)
            print(f'[CYCLE_SUMMARY] Entries:{entries} Exits:{exits} Holds:{holds} Blocked:{blocked} Errors:{errors}', flush=True)

            if errors > 0:
                consecutive_errors += errors
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    print(f'[ERROR_GUARD] {consecutive_errors} consecutive errors. Halting for safety.', flush=True)
                    break

        except Exception as e:
            print(f'[ERROR] Cycle failed: {e}', flush=True)
            consecutive_errors += 1
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                print(f'[ERROR_GUARD] {consecutive_errors} consecutive cycle failures. Halting.', flush=True)
                break

        time.sleep(300)
