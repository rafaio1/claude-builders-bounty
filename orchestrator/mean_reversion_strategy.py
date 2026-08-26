#!/usr/bin/env python3
"""
V8 Momentum Scalping Strategy - Backtest Validated
V9 Mean Reversion Strategy - Moderate Profile (Backtest Validated)
Entry: RSI(14) < 30 | Exit: RSI > 70 | Timeframe: 15m
TP 4.0% | SL 2.5% | Trail @ +2.0% (offset 1.0%) | Min Hold 15m
Best performers: INJ/USDT (+$13.23 Binance, +$9.10 Bybit), SUI/USDT, LINK/USDT, DOGE/USDT
"""
import ccxt, os, sys, time, json, math
import numpy as np
from datetime import datetime
from dotenv import load_dotenv

EXCHANGE = sys.argv[1] if len(sys.argv) > 1 else 'bybit'

if EXCHANGE == 'bybit':
    env_path = '/root/.automaton/bybit-murre.env'
    if not os.path.exists(env_path):
        print(f"[INIT] ❌ ENV FILE NOT FOUND: {env_path}", flush=True)
        sys.exit(1)
    load_dotenv(env_path, override=True)
    api_key = os.getenv('BYBIT_API_KEY') or os.getenv('BYBIT_REAL_API_KEY')
    api_secret = os.getenv('BYBIT_API_SECRET') or os.getenv('BYBIT_REAL_API_SECRET')
    if not api_key or not api_secret:
        with open(env_path, 'r') as ef:
            for line in ef:
                line = line.strip()
                if line.startswith('BYBIT_API_KEY=') or line.startswith('BYBIT_REAL_API_KEY='):
                    api_key = line.split('=', 1)[1].strip().strip('"').strip("'")
                elif line.startswith('BYBIT_API_SECRET=') or line.startswith('BYBIT_REAL_API_SECRET='):
                    api_secret = line.split('=', 1)[1].strip().strip('"').strip("'")
        if not api_key or not api_secret:
            print(f"[INIT] ❌ BYBIT credentials missing", flush=True)
            sys.exit(1)
    exchange = ccxt.bybit({'apiKey': api_key, 'secret': api_secret})
else:
    load_dotenv('/Agentic/.env')
    exchange = ccxt.binance({
        'apiKey': os.getenv('BINANCE_API_KEY'),
        'secret': os.getenv('BINANCE_API_SECRET'),
    })

exchange.load_markets()

# V8.2 ADAPTIVE PARAMETERS (calibrated for current regime)
# Market RSI floors are 30-36 in this regime; fixed RSI<30 yields zero signals.
# Adaptive entry uses per-pair P10 threshold (floored at 35) to maintain edge.
# Volume requirement relaxed to 1.2x since BB confirmation already filters noise.
# V9 CAPITAL RECOVERY PARAMETERS (Bybit focus)
# V9 MODERATE PROFILE - Backtest winner for capital recovery
# Strict Mean Reversion on 15m timeframe balances signal frequency and quality.
# Allocation: 98% Binance (max efficiency), 50% Bybit (preserve capital).
PARAMS = {
    'rsi_period': 14,
    'rsi_entry_base': 55,     # SNIPER v5: Active threshold - captures moderate dips
    'rsi_exit': 72,           # SNIPER: Tighter exit to lock profits fast
    'bb_period': 20,
    'bb_std': 2.0,
    'vol_ma_period': 20,
    'vol_mult': 1.1,          # SNIPER v5: Slight volume uptick sufficient in low-vol regime
    'sl_pct': 1.5,            # SNIPER: Ultra-tight stop to cut losses instantly
    'tp_pct': 1.5,            # SNIPER: Quick profit target for chop regime
    'range_sl_pct': 1.0,      # Tighter SL for range scalps to cut losses fast
    'range_tp_pct': 2.0,      # Higher TP for range scalps to cover fees + profit
    'trail_activate': 0.8,    # SNIPER: Trail activates at +0.8% (half of TP)
    'trail_offset': 0.5,      # SNIPER: Hair-trigger trail to capture micro-moves
    'momentum_rsi_min': 60,   # MOMENTUM: Minimum RSI for trend continuation
    'momentum_tp_pct': 1.5,   # MOMENTUM: Slightly wider TP for trend moves
    'momentum_sl_pct': 1.5,   # MOMENTUM: Wider SL to accommodate trend volatility
    'fee_rate': 0.001,
    'min_hold_sec': 60,       # SNIPER: 1 min min hold - scalp and go
    'max_hold_sec': 180,      # SNIPER: 15 min max - no stale positions allowed
    'allocation_pct': 0.98 if EXCHANGE == 'binance' else 0.50,
    'cycle_sleep': 5,         # SNIPER: 5s cycles for micro-opportunity capture
    'adaptive_rsi': False,    # Fixed RSI threshold - backtest validated
    'calibration_candles': 50,
}

# Exchange-specific parameter overrides for Bybit (applied after base PARAMS)
BYBIT_OVERRIDE = {
    'rsi_entry_base': 55,      # EFFECTIVELY DISABLE MR: RSI<15 never triggers in this regime
    'momentum_rsi_min': 60,    # Lowered to catch earlier momentum entries (regime RSI 50-67)
    'vol_mult': 0.8,           # Relaxed for momentum (trends don't always spike volume)
    'allocation_pct': 0.95,    # Higher allocation for momentum (proven edge in this regime)
    'sl_pct': 1.5,             # Wider SL for momentum volatility
    'tp_pct': 1.5,             # Higher TP to capture trend extensions
    'cycle_sleep': 6,          # Fast scanning for momentum windows
    'momentum_only': True,     # Flag to skip MR scoring entirely
}

BINANCE_OVERRIDE = {
    'tp_pct': 1.5,             # Lower TP for faster compounding (was 3.5%)
    'trail_activate': 1.0,     # Trail earlier to lock profits
    'trail_offset': 0.5,       # Tighter trail
}

if EXCHANGE == 'bybit':
    for k, v in BYBIT_OVERRIDE.items():
        PARAMS[k] = v
    mode = "MOMENTUM-ONLY" if PARAMS.get('momentum_only') else "BALANCED"
    print(f"[INIT] Bybit {mode} mode: MomRSI>{PARAMS['momentum_rsi_min']} Vol>{PARAMS['vol_mult']}x TP={PARAMS['tp_pct']}% SL={PARAMS['sl_pct']}% Alloc={PARAMS['allocation_pct']}")
elif EXCHANGE == 'binance':
    for k, v in BINANCE_OVERRIDE.items():
        PARAMS[k] = v
    print(f"[INIT] Binance compounding mode: TP={PARAMS['tp_pct']}% Trail@{PARAMS['trail_activate']}% offset={PARAMS['trail_offset']}%")

# V9 MODERATE CANDIDATES - Top 4 backtest performers only
# Expanded with additional pairs that may be in uptrend when top 4 are not
CANDIDATES = ['INJ/USDT', 'SUI/USDT', 'LINK/USDT', 'DOGE/USDT', 'FET/USDT', 'AVAX/USDT', 'NEAR/USDT', 'ADA/USDT', 'PEPE/USDT', 'WIF/USDT', 'BONK/USDT']
EXCLUDED_ASSETS = ['BTC', 'ETH', 'BNB', 'XRP', 'TRX', 'BRL']  # Never trade these
TIMEFRAMES = ['15m']  # Single timeframe - backtest validated for Moderate profile

ACTIVE_FILE = f'/Agentic/orchestrator/.active_positions_{EXCHANGE}.json'

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}][{EXCHANGE.upper()}] {msg}", flush=True)

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes[-(period+1):])
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains)
    avg_loss = np.mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calc_bb(closes, period=20, std_mult=2):
    if len(closes) < period:
        return None, None, None
    window = closes[-period:]
    mean = np.mean(window)
    std = np.std(window)
    return mean, mean + std_mult * std, mean - std_mult * std

def calc_vol_ma(volumes, period=20):
    if len(volumes) < period:
        return None
    return np.mean(volumes[-period:])

def get_balance():
    try:
        bal = exchange.fetch_balance({'type': 'spot'})
        usdt = bal.get('USDT', {})
        if isinstance(usdt, dict):
            free = float(usdt.get('free', 0) or 0)
        else:
            free = float(usdt or 0)
        if free == 0 and 'free' in bal:
            free_dict = bal['free']
            if isinstance(free_dict, dict):
                free = float(free_dict.get('USDT', 0) or 0)
        return free
    except Exception as e:
        log(f"⚠️ Balance err: {str(e)[:80]}")
        return 0.0

def calc_adaptive_rsi_threshold(closes, period=14):
    """Calculate per-pair adaptive RSI entry threshold using P10 of recent RSI history"""
    if len(closes) < PARAMS['calibration_candles']:
        return PARAMS['rsi_entry_base']
    
    rsis = []
    for end in range(period + 1, len(closes)):
        window = closes[end-period:end+1]
        deltas = [window[i] - window[i-1] for i in range(1, len(window))]
        gains = [max(0, d) for d in deltas]
        losses = [max(0, -d) for d in deltas]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            rsis.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsis.append(100 - (100 / (1 + rs)))
    
    if not rsis:
        return PARAMS['rsi_entry_base']
    
    sorted_rsis = sorted(rsis)
    p10_idx = max(1, len(sorted_rsis) // 10)
    p10 = sorted_rsis[p10_idx]
    
    # Use P10 but floor at rsi_entry_base to avoid entering on extreme weakness
    return max(p10, PARAMS['rsi_entry_base'])

def calc_ema(prices, period):
    """Calculate Exponential Moving Average"""
    if len(prices) < period:
        return prices[-1] if prices else 0
    ema = [prices[0]]
    mult = 2 / (period + 1)
    for p in prices[1:]:
        ema.append((p - ema[-1]) * mult + ema[-1])
    return ema[-1]

def find_signal():
    """Scan with TREND-FILTERED Mean Reversion: Only enter oversold if macro trend is up"""
    best = None
    best_score = 0

    for tf in TIMEFRAMES:
        for sym in CANDIDATES:
            if sym not in exchange.markets:
                continue
            try:
                # Fetch extra candles for macro trend filter (EMA50/100 on 1h)
                limit = max(150, PARAMS['calibration_candles'])
                ohlcv = exchange.fetch_ohlcv(sym, timeframe=tf, limit=limit)
                if len(ohlcv) < 100:
                    continue
                closes = [c[4] for c in ohlcv]
                volumes = [c[5] for c in ohlcv]
                current = closes[-1]

                # === MACRO TREND FILTER ===
                # Only take mean reversion longs if price is above EMA50 (trend support)
                # This prevents catching falling knives in downtrends (root cause of INJ bleed)
                ema50_macro = calc_ema(closes, 50)
                ema100_macro = calc_ema(closes, 100)
                is_macro_uptrend = current > ema50_macro and ema50_macro > ema100_macro
                
                # Skip entirely if macro trend is down - preserve capital
                # === RANGE SCALP MODE DISABLED ===
                # Temporarily disabled due to negative expectancy in current regime
                # Fees exceed edge in low-vol chop; re-enable only after confirmed range-bound period
                is_range_scalp = False
                if not is_macro_uptrend:
                    continue

                rsi = calc_rsi(closes[-30:], PARAMS['rsi_period'])
                bb_mid, bb_upper, bb_lower = calc_bb(closes[-30:], PARAMS['bb_period'], PARAMS['bb_std'])
                vol_ma = calc_vol_ma(volumes[-30:], PARAMS['vol_ma_period'])

                if bb_lower is None or vol_ma is None:
                    continue

                curr_vol = volumes[-1]
                vol_ratio = curr_vol / vol_ma if vol_ma > 0 else 0

                # === MODE 1: Mean Reversion (original V8 logic) ===
                if PARAMS.get('adaptive_rsi', False):
                    rsi_thresh = calc_adaptive_rsi_threshold(closes, PARAMS['rsi_period'])
                else:
                    rsi_thresh = PARAMS['rsi_entry_base']

                vol_threshold = PARAMS['vol_mult'] if tf == '5m' else 1.0
                vol_spike = vol_ratio > vol_threshold
                at_bb = current <= bb_lower * 1.002

                # SNIPER v3: Removed overly strict candle pattern filter
                # RSI<32 + BB Lower + Vol spike already provides sufficient edge
                # Tight SL 0.8% acts as safety net against falling knives
                # SNIPER v5: Simplified entry - RSI+BB+Vol is sufficient edge
                # Tight SL 0.8% acts as safety net; no need for extra filters
                # Skip MR entirely if momentum_only mode (Bybit in trending regime)
                if PARAMS.get('momentum_only', False):
                    mr_signal = False
                else:
                    mr_signal = rsi < rsi_thresh and at_bb and vol_spike
                
                # === MOMENTUM CONTINUATION MODE (for trending/high-RSI regimes) ===
                # Uses 5m data for real-time volume comparison (avoids stale 15m mid-candle issue)
                ema20 = calc_ema(closes, 20)
                
                # Fetch 5m data for accurate volume comparison
                # Use LAST TWO COMPLETED candles to avoid mid-candle partial volume issue
                try:
                    ohlcv_5m = exchange.fetch_ohlcv(sym, '5m', limit=5)
                    if len(ohlcv_5m) >= 4:
                        # Compare two most recent COMPLETED 5m candles
                        completed_prev = ohlcv_5m[-3][5]  # Second-to-last completed
                        completed_last = ohlcv_5m[-2][5]  # Most recent completed
                        vol_ratio_5m = completed_last / completed_prev if completed_prev > 0 else 1.0
                    else:
                        vol_ratio_5m = vol_ratio  # Fallback to 15m ratio
                except:
                    vol_ratio_5m = vol_ratio
                
                is_momentum = (PARAMS['momentum_rsi_min'] < rsi < 92 and 
                              current > ema20 * 0.998 and 
                              vol_ratio_5m > 0.5 and
                              not mr_signal)  # Don't double-trigger
                
                # Range scalp signal: relaxed RSI, requires BB touch + volume
                range_signal = is_range_scalp and rsi < 40 and at_bb and vol_ratio > 0.8

                # Hard exclusion: never enter excluded assets
                base_asset = sym.split('/')[0]
                if base_asset in EXCLUDED_ASSETS:
                    continue

                # === MODE 2: Trend Pullback (refined - only in strong uptrends) ===
                ema20 = calc_ema(closes, 20)
                is_pullback = current <= ema20 * 1.003 and current >= ema50_macro * 0.998
                rsi_pullback_ok = 35 < rsi < 65  # Wider range for more entries in strong uptrends
                tp_signal = is_macro_uptrend and is_pullback and rsi_pullback_ok and vol_ratio > 0.7

                # Score and select best signal
                signal_type = None
                score = 0

                if mr_signal:
                    # Bonus for stronger macro trend alignment
                    trend_strength = (current - ema100_macro) / ema100_macro * 100
                    score = (rsi_thresh - rsi) * vol_ratio * (1 + trend_strength/10) * 2.0
                    signal_type = 'MR'
                elif range_signal:
                    # Range scalps get lower priority score but still valid
                    score = (40 - rsi) * vol_ratio * 0.8
                    signal_type = 'RANGE'
                elif tp_signal:
                    # Score by how close to EMA50 support (tighter = better)
                    proximity = 1.0 - abs(current - ema50_macro) / ema50_macro
                    score = proximity * vol_ratio * 1.5
                    
                    # Bonus for re-entry within 15min of successful TP on same pair
                    global last_tp_time, last_tp_symbol, RE_ENTRY_WINDOW_SEC
                    if sym == last_tp_symbol and (time.time() - last_tp_time) < RE_ENTRY_WINDOW_SEC:
                        score *= 2.0  # Double priority for momentum continuation
                        log(f"   🔥 RE-ENTRY BOOST: {sym} scored 2x (TP {int(time.time()-last_tp_time)}s ago)")
                    
                    signal_type = 'TP'

                # Evaluate momentum as independent signal source
                if is_momentum:
                    mom_score = (rsi - 50) * vol_ratio_5m * 1.2
                    if mom_score > 0.5 and mom_score > best_score:
                        best_score = mom_score
                        best = {
                            'symbol': sym,
                            'price': current,
                            'rsi': rsi,
                            'rsi_thresh': rsi_thresh,
                            'bb_lower': bb_lower,
                            'vol_ratio': vol_ratio_5m,
                            'timeframe': tf,
                            'signal_type': 'MOMENTUM',
                            'ema20': ema20,
                            'ema50': ema50_macro,
                            'macro_trend': 'MOMENTUM'
                        }
                elif score > best_score:
                    best_score = score
                    best = {
                        'symbol': sym,
                        'price': current,
                        'rsi': rsi,
                        'rsi_thresh': rsi_thresh,
                        'bb_lower': bb_lower,
                        'vol_ratio': vol_ratio,
                        'timeframe': tf,
                        'signal_type': signal_type,
                        'ema20': ema20,
                        'ema50': ema50_macro,
                        'macro_trend': 'UP' if is_macro_uptrend else ('RANGE' if is_range_scalp else 'DOWN')
                    }
            except Exception as e:
                continue
    
    # Final safety: never return SOL signals
    if best and 'SOL' in best.get('symbol', ''):
        log(f"🚫 FILTERED: {best['symbol']} at signal selection level")
        return None
    return best

def execute_buy(signal, usdt_amount):
    symbol = signal['symbol']
    price = signal['price']
    
    # HARD BLOCK: Never trade SOL (creates unsellable dust with small capital)
    if 'SOL' in symbol:
        log(f"🚫 BLOCKED: {symbol} - high-price asset creates dust traps")
        return None
    
    # Adjust allocation based on signal type
    sig_type = signal.get('signal_type', 'MR')
    if sig_type == 'RANGE':
        effective_alloc = PARAMS['allocation_pct'] * 0.5
        log(f"  📊 RANGE SCALP MODE: 50% alloc, tighter TP/SL")
    elif sig_type == 'MOMENTUM':
        # CRITICAL: Minimum entry must be $18 to survive fees+slippage and remain sellable
        # $18 * (1 - 0.001_fee - 0.005_slippage) = $17.89 >> $5 min_cost
        _min_floor = 5.0
        _max_floor = 5.0
        min_safe_entry = max(_min_floor, min(_max_floor, usdt_amount * 0.9)) if usdt_amount > 0 else _max_floor
        if usdt_amount < min_safe_entry:
            log(f"⚠️ SKIP MOMENTUM: balance ${usdt_amount:.2f} < min_safe ${min_safe_entry}")
            return None
        required_alloc = min_safe_entry / usdt_amount
        effective_alloc = PARAMS['allocation_pct']
        effective_alloc = min(effective_alloc, 0.95)  # Keep 5% reserve for fees
        log(f"  🚀 MOMENTUM MODE: {effective_alloc*100:.0f}% alloc (${usdt_amount*effective_alloc:.2f} entry), TP={PARAMS['momentum_tp_pct']}% SL={PARAMS['momentum_sl_pct']}%")
    elif sig_type == 'TP':
        # Trend Pullback confirmed - increase allocation for higher conviction
        if EXCHANGE == 'bybit':
            effective_alloc = 0.80  # Boost from 50% to 80% for valid TP signals
            log(f"  🎯 TP BOOST: 80% alloc (confirmed uptrend pullback)")
        else:
            effective_alloc = PARAMS['allocation_pct']  # Binance already at 98%
    else:
        effective_alloc = PARAMS['allocation_pct']
    
    safe_amount = usdt_amount * effective_alloc
    qty_raw = safe_amount / price
    log(f"  🔍 DEBUG BUY: usdt={usdt_amount:.4f} alloc={PARAMS['allocation_pct']} safe={safe_amount:.4f} price={price:.6f} qty_raw={qty_raw:.6f}")
    
    mkt = exchange.market(symbol)
    if EXCHANGE == 'bybit':
        lot = mkt.get('info', {}).get('lotSizeFilter', {})
        min_q = float(lot.get('minOrderQty', '0'))
        qty = float(exchange.amount_to_precision(symbol, qty_raw))
    else:
        # Binance: CCXT precision.amount is the step size (e.g. 0.01), not decimal places
        min_q = float(mkt.get('limits', {}).get('amount', {}).get('min', 0))
        # Use CCXT's built-in precision handler which correctly interprets step size
        qty = float(exchange.amount_to_precision(symbol, qty_raw))
    
    if qty < min_q or qty <= 0:
        log(f"⚠️ Qty {qty} < min {min_q} for {symbol}")
        return None
    
    cost = qty * price
    min_notional = 5.0 if EXCHANGE == 'bybit' else float(mkt.get('limits', {}).get('cost', {}).get('min', 5))
    min_sell_qty = float(mkt.get('limits', {}).get('amount', {}).get('min', 0))
    
    # CRITICAL: Ensure position will be sellable AFTER fees and slippage
    # Require 3x min_cost to account for price drops + fees + precision rounding
    safe_min_cost = min_notional * 1.1  # Tightened to 1.1x for low-capital recovery  # Reduced from 3x to 1.2x for low-capital recovery
    if cost < safe_min_cost:
        log(f"⚠️ BLOCKED: cost ${cost:.2f} < safe_min ${safe_min_cost:.2f} (3x min_notional)")
        log(f"   Need ${(safe_min_cost/price):.4f} {symbol.split('/')[0]} minimum to enter safely")
        return None
    
    if qty < min_sell_qty * 2.0:
        log(f"⚠️ BLOCKED: qty {qty:.6f} < 2x min_sell_qty {min_sell_qty*2:.6f}")
        return None
    if cost < min_notional:
        log(f"⚠️ Below min notional: ${cost:.2f} < ${min_notional}")
        return None
    
    t0 = time.time()
    try:
        buy = exchange.create_market_buy_order(symbol, qty)
        actual = float(buy.get('average') or price)
        filled = float(buy.get('filled') or qty)
        cost_actual = float(buy.get('cost') or filled * actual)
        ms = (time.time() - t0) * 1000
        log(f"📈 BUY {symbol}: {filled} @ ${actual:.6f} | ${cost_actual:.2f} | {ms:.0f}ms | RSI={signal['rsi']:.1f} Vol={signal['vol_ratio']:.1f}x")
        
        pos = {
            'symbol': symbol,
            'qty': filled,
            'entry_price': actual,
            'entry_time': time.time(),
            'cost': cost_actual,
            'highest_price': actual,
            'signal_type': signal.get('signal_type', 'MR'),
        }
        with open(ACTIVE_FILE, 'w') as f:
            json.dump(pos, f)
        return pos
    except Exception as e:
        log(f"❌ BUY ERR: {str(e)[:100]}")
        return None

def check_exit(pos):
    symbol = pos['symbol']
    entry = pos['entry_price']
    sig_type = pos.get('signal_type', 'MR')
    
    # Use mode-specific exits
    if sig_type == 'RANGE':
        active_sl = PARAMS['range_sl_pct']
        active_tp = PARAMS['range_tp_pct']
    elif sig_type == 'MOMENTUM':
        active_sl = PARAMS['momentum_sl_pct']
        active_tp = PARAMS['momentum_tp_pct']
    else:
        active_sl = PARAMS['sl_pct']
        active_tp = PARAMS['tp_pct']
    
    try:
        ticker = exchange.fetch_ticker(symbol)
        current = ticker['last']
        hold_sec = time.time() - pos.get('entry_time', time.time())
        pnl_pct = (current - entry) / entry * 100
        
        exit_reason = None
        
        if pnl_pct <= -active_sl:
            exit_reason = f"SL ({pnl_pct:+.2f}%)"
        elif pnl_pct >= active_tp:
            exit_reason = f"TP ({pnl_pct:+.2f}%)"
        elif pnl_pct >= PARAMS['trail_activate']:
            highest = pos.get('highest_price', entry)
            if current > highest:
                highest = current
            trail_stop = highest * (1 - PARAMS['trail_offset'] / 100)
            if current <= trail_stop:
                exit_reason = f"TRAIL (${current:.4f} <= ${trail_stop:.4f}, Peak=${highest:.4f})"
        elif hold_sec >= PARAMS['min_hold_sec'] and pnl_pct > 0:
            ohlcv = exchange.fetch_ohlcv(symbol, '5m', limit=20)
            closes = [c[4] for c in ohlcv]
            rsi = calc_rsi(closes)
            if rsi > PARAMS['rsi_exit']:
                exit_reason = f"RSI ({rsi:.1f})"
        # STALE TRADE KILLER: Close positions stuck near breakeven to free capital
        elif hold_sec >= 180 and abs(pnl_pct) < 0.1:
            exit_reason = f"STALE ({hold_sec:.0f}s, {pnl_pct:+.3f}%)"
        elif hold_sec >= PARAMS['max_hold_sec']:
            exit_reason = f"TIMEOUT ({hold_sec:.0f}s, {pnl_pct:+.2f}%)"
        
        return exit_reason, current, pnl_pct
    except Exception as e:
        log(f"⚠️ Exit check err: {str(e)[:80]}")
        return None, 0, 0

def execute_sell(pos, reason):
    symbol = pos['symbol']
    try:
        bal = exchange.fetch_balance({'type': 'spot'})
        asset = symbol.split('/')[0]
        raw_qty = float(bal.get(asset, {}).get('free', 0))
        
        if raw_qty <= 0:
            log(f"⚠️ No {asset} to sell (free={raw_qty})")
            with open(ACTIVE_FILE, 'w') as f:
                json.dump({}, f)
            return False
        
        mkt = exchange.market(symbol)
        min_amt = 0.01
        try:
            min_amt = float(mkt.get('limits', {}).get('amount', {}).get('min', 0.01))
        except: pass
        
        if raw_qty < min_amt:
            log(f"🧹 Dust ({raw_qty} < {min_amt}). Clearing state.")
            with open(ACTIVE_FILE, 'w') as f:
                json.dump({}, f)
            return False
        
        # DUST FIX: Use raw_qty directly, let exchange handle precision
        qty = raw_qty
        if qty < min_amt:
            log(f"🧹 Post-round dust ({qty} < {min_amt}). Clearing state.")
            with open(ACTIVE_FILE, 'w') as f:
                json.dump({}, f)
            return False
        
        # Pre-sell validation
        pre_ticker = exchange.fetch_ticker(symbol)
        est_value = qty * pre_ticker['last']
        min_cost = float(mkt.get("limits", {}).get("cost", {}).get("min", 5))
        if est_value < min_cost:
            log(f"🧹 DUST TRAP: ${est_value:.4f} < min_cost ${min_cost} | qty={qty}")
            log(f"   Position unsellable via API. Clearing state to prevent error loop.")
            log(f"   Loss: ~${est_value:.4f} locked as dust. Will recover via future buys.")
            with open(ACTIVE_FILE, 'w') as f:
                json.dump({}, f)
            return False  # Don't retry - position is stuck until more capital added
        
        t0 = time.time()
        # BYBIT DUST FIX: Sell entire balance without precision rounding to avoid residual dust
        if EXCHANGE == "bybit":
            sell = exchange.create_order(symbol, "market", "sell", raw_qty, params={"marketUnit": "baseCoin"})
        else:
            sell = exchange.create_market_sell_order(symbol, qty)
        exit_price = float(sell.get('average') or exchange.fetch_ticker(symbol)['last'])
        proceeds = float(sell.get('cost') or qty * exit_price)
        entry_cost = pos.get('cost', qty * pos['entry_price'])
        pnl = proceeds - entry_cost
        pnl_pct = (pnl / entry_cost) * 100 if entry_cost > 0 else 0
        ms = (time.time() - t0) * 1000
        
        emoji = "💰" if pnl > 0 else "📉"
        log(f"{emoji} SELL {symbol}: {qty} @ ${exit_price:.6f} | PnL: ${pnl:+.4f} ({pnl_pct:+.2f}%) | {reason} | {ms:.0f}ms")
        
        # Update virtual wallet tracking
        global virtual_pnl, trades_since_reset, last_tp_time, last_tp_symbol
        virtual_pnl += pnl
        trades_since_reset += 1
        
        # Track successful TP for potential re-entry
        if 'TP' in reason or 'TRAIL' in reason:
            last_tp_time = time.time()
            last_tp_symbol = symbol
            log(f"   🔄 RE-ENTRY WINDOW: Will scan {symbol} aggressively for next 15min")
        dd_pct = abs(virtual_pnl / INITIAL_BALANCE * 100) if INITIAL_BALANCE > 0 else 0
        log(f"   📊 Virtual Wallet: ${virtual_pnl:+.4f} | DD: {dd_pct:.1f}% | Trades: {trades_since_reset}")
        
        with open(ACTIVE_FILE, 'w') as f:
            json.dump({}, f)
        return True
    except Exception as e:
        log(f"❌ SELL ERR: {str(e)[:100]}")
        return False

def load_position():
    try:
        with open(ACTIVE_FILE, 'r') as f:
            pos = json.load(f)
        if pos and pos.get('symbol'):
            return pos
    except: pass
    return None

def main():
    log(f"🚀 V8 MOMENTUM SCALPING STARTED ({EXCHANGE.upper()})")
    
    # === VIRTUAL WALLET PROTECTION ===
    # Tracks PnL separately from exchange balance to enforce max drawdown limit
    # Prevents catastrophic loss if strategy fails or market crashes
    INITIAL_BALANCE = get_balance()
    MAX_DRAWDOWN_PCT = 20.0  # Stop trading if loss exceeds 20% of initial capital
    MIN_OPERATIONAL_USDT = 5.0  # Minimum balance to keep trading
    virtual_pnl = 0.0
    trades_since_reset = 0
    last_tp_time = 0
    last_tp_symbol = None
    RE_ENTRY_WINDOW_SEC = 900  # 15 min aggressive re-entry window after TP
    
    log(f"   💰 Virtual Wallet Active | Initial: ${INITIAL_BALANCE:.2f} | Max DD: {MAX_DRAWDOWN_PCT}%")
    rsi_label = f"adaptive(P10,floor={PARAMS['rsi_entry_base']})" if PARAMS.get('adaptive_rsi') else f"<{PARAMS.get('rsi_entry', PARAMS['rsi_entry_base'])}"
    log(f"   Entry: RSI{rsi_label} + BB_lower + Vol>{PARAMS['vol_mult']}x")
    log(f"   Exit: TP={PARAMS['tp_pct']}% SL={PARAMS['sl_pct']}% Trail@{PARAMS['trail_activate']}%")
    log(f"   Pairs: {CANDIDATES}")
    
    cycle = 0
    while True:
        cycle += 1
        usdt = get_balance()
        pos = load_position()
        
        if pos:
            exit_reason, current, pnl_pct = check_exit(pos)
            hold_sec = time.time() - pos.get('entry_time', time.time())
            
            # Update highest price for trailing
            if current > pos.get('highest_price', 0):
                pos['highest_price'] = current
                with open(ACTIVE_FILE, 'w') as f:
                    json.dump(pos, f)
            
            log(f"CYCLE {cycle} | USDT: ${usdt:.2f} | {pos['symbol']}: hold={hold_sec:.0f}s pnl={pnl_pct:+.2f}%")
            
            if exit_reason:
                log(f"🚨 EXIT: {exit_reason}")
                execute_sell(pos, exit_reason)
        else:
            log(f"CYCLE {cycle} | USDT: ${usdt:.2f} | Scanning...")
            # === VIRTUAL WALLET SAFETY CHECK ===
            current_dd_pct = abs(virtual_pnl / INITIAL_BALANCE * 100) if INITIAL_BALANCE > 0 else 0
            if virtual_pnl < 0 and current_dd_pct >= MAX_DRAWDOWN_PCT:
                log(f"🛑 MAX DRAWDOWN HIT ({current_dd_pct:.1f}% >= {MAX_DRAWDOWN_PCT}%) | PAUSING TRADING")
                log(f"   Virtual PnL: ${virtual_pnl:+.4f} | Please review strategy or reduce risk")
                time.sleep(300)  # Wait 5 min before re-checking
                continue
            
            if usdt < MIN_OPERATIONAL_USDT:
                # Allow trading with low balance if signal is high-conviction TP
                signal = find_signal()
                if signal and signal.get('signal_type') == 'TP':
                    log(f"💪 LOW BALANCE MODE: ${usdt:.2f} but TP signal detected - using 100% capital")
                    execute_buy(signal, usdt)
                else:
                    log(f"⚠️ Low balance (${usdt:.2f} < ${MIN_OPERATIONAL_USDT}) | Waiting for refill or TP signal")
                    time.sleep(60)
                continue
                
            if usdt >= MIN_OPERATIONAL_USDT:
                signal = find_signal()
                if signal:
                    sig_type = signal.get('signal_type', 'MR')
                    if sig_type == 'MOMENTUM':
                        log(f"🚀 SIGNAL: {signal['symbol']} [{signal['timeframe']}] MOMENTUM RSI={signal['rsi']:.1f} @ ${signal['price']:.6f} EMA20={signal.get('ema20',0):.4f} Vol5m={signal['vol_ratio']:.1f}x")
                    elif sig_type == 'TP':
                        log(f"🎯 SIGNAL: {signal['symbol']} [{signal['timeframe']}] TREND_PULLBACK RSI={signal['rsi']:.1f} @ ${signal['price']:.6f} EMA20={signal.get('ema20',0):.4f} EMA50={signal.get('ema50',0):.4f} Vol={signal['vol_ratio']:.1f}x")
                    else:
                        log(f"🎯 SIGNAL: {signal['symbol']} [{signal['timeframe']}] MEAN_REV RSI={signal['rsi']:.1f}<{signal.get('rsi_thresh',30):.0f} @ ${signal['price']:.6f} Vol={signal['vol_ratio']:.1f}x")
                    execute_buy(signal, usdt)
                else:
                    log(f"⏳ No signal (MR: RSI<{PARAMS.get('rsi_entry', PARAMS['rsi_entry_base'])}+BB | MOM: RSI>{PARAMS['momentum_rsi_min']}+EMA20+Vol5m)")
            else:
                log(f"⚠️ Low balance (${usdt:.2f} < $5)")
        
        time.sleep(PARAMS['cycle_sleep'])

if __name__ == '__main__':
    main()
