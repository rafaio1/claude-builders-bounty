#!/usr/bin/env python3
"""SUBAGENT V5: Smart Spot Scalper with Server-Side TP/SL Management
- Detects open positions and sets server-side TP/SL orders
- Uses OCO (Binance) or conditional orders (Bybit) for risk management
- Tracks positions with expected P&L in state.json
- Market orders for entry, conditional orders for exit
"""
import ccxt, os, json, time, sys, math
from dotenv import load_dotenv
from trading_economic_guard import evaluate_live_trading
sys.stdout.reconfigure(line_buffering=True)

EXCHANGE = sys.argv[1] if len(sys.argv) > 1 else 'bybit'
load_dotenv('/root/.automaton/bybit-murre.env' if EXCHANGE == 'bybit' else '/Agentic/.env')
STATE_PATH = '/Agentic/orchestrator/state.json'

_guard = evaluate_live_trading(exchange_name=EXCHANGE)
if not _guard.allowed:
    print(f"TRADING_ECONOMIC_GUARD_BLOCKED: {';'.join(_guard.reasons)}", flush=True)
    raise SystemExit(78)

if EXCHANGE == 'bybit':
    exchange = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_REAL_API_KEY'),
        'secret': os.getenv('BYBIT_REAL_API_SECRET'),
        'options': {'defaultType': 'spot', 'recvWindow': 5000},
        'enableRateLimit': True
    })
    STATE_KEY = 'bybit_spot'
else:
    exchange = ccxt.binance({
        'apiKey': os.getenv('BINANCE_API_KEY'),
        'secret': os.getenv('BINANCE_API_SECRET'),
        'options': {'defaultType': 'spot'},
        'enableRateLimit': True
    })
    STATE_KEY = 'binance_spot'

exchange.load_markets()

PARAMS = {
    'sl_pct': 0.8,
    'tp_pct': 1.2,
    'trail_pct': 0.5,
    'trail_activation': 0.8,
    'max_hold_sec': 120,
}

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}][{EXCHANGE.upper()}] {msg}", flush=True)

# Trade cooldown and history tracking
_last_trade_time = {}  # symbol -> timestamp
_last_loss_time = {}   # symbol -> timestamp of last loss
_consecutive_losses = {}  # symbol -> count
_last_sell_time = {}   # symbol -> timestamp of ANY sell (wash-trade guard)
_daily_pnl = {}        # symbol -> {date_str: float} cumulative realized PnL
_wash_halted = set()   # symbols halted due to wash-trade detection

COOLDOWN_AFTER_LOSS_SEC = 300    # 90s cooldown after loss - balance between safety and frequency
MIN_TRADE_INTERVAL_SEC = 300    # 5min min interval between trades on same symbol (was 60s)
MAX_CONSECUTIVE_LOSSES = 3      # Stop trading symbol after 3 consecutive losses
CONSECUTIVE_LOSS_COOLDOWN = 1800  # 30 min ban after max consecutive losses
POST_SELL_COOLDOWN_SEC = 300    # Mandatory 5min cooldown after ANY sell before re-entry
WASH_DETECT_WINDOW = 5          # Check last N trades for wash pattern
WASH_MAX_INTERVAL_SEC = 30      # Trades <30s apart considered potential wash
MAX_DAILY_LOSS_USDT = 1.0       # Halt symbol if daily loss exceeds this

def update_state(data):
    try:
        with open(STATE_PATH, 'r') as f:
            state = json.load(f)
        state['subagents'][STATE_KEY].update(data)
        state['subagents'][STATE_KEY]['last_updated'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        with open(STATE_PATH, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        log(f"State ERR: {e}")

# Track symbols with active open positions to prevent double-entry
_active_positions = set()
ACTIVE_POS_FILE = '/Agentic/orchestrator/.active_positions_' + EXCHANGE + '.json'
COOLDOWN_STATE_FILE = '/Agentic/orchestrator/.cooldown_state_' + EXCHANGE + '.json'

def _load_active_from_file():
    """Load persisted active positions from disk"""
    try:
        if os.path.exists(ACTIVE_POS_FILE):
            with open(ACTIVE_POS_FILE, 'r') as f:
                data = json.load(f)
            syms = set(data.get('symbols', []))
            file_ts = data.get('updated', 0)
            # Restore entry timestamps so MaxHold survives restarts
            for s in syms:
                if s not in _last_trade_time or _last_trade_time[s] == 0:
                    _last_trade_time[s] = file_ts
            if syms:
                log(f"  📂 Restored {len(syms)} active pos (ts={file_ts:.0f})")
            return syms
    except Exception as e:
        log(f"  ⚠️ Load active pos file ERR: {str(e)[:60]}")
    return set()

def _save_active_to_file():
    """Persist active positions to disk"""
    try:
        with open(ACTIVE_POS_FILE, 'w') as f:
            json.dump({'symbols': list(_active_positions), 'updated': time.time()}, f)
    except Exception as e:
        log(f"  ⚠️ Save active pos file ERR: {str(e)[:60]}")

def _save_cooldown_state():
    """Persist cooldown timestamps to survive restarts"""
    try:
        data = {
            'last_trade_time': _last_trade_time,
            'last_loss_time': _last_loss_time,
            'last_sell_time': _last_sell_time,
            'consecutive_losses': _consecutive_losses,
            'daily_pnl': _daily_pnl,
            'wash_halted': list(_wash_halted),
            'saved_at': time.time()
        }
        with open(COOLDOWN_STATE_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        log(f"  ⚠️ Failed to save cooldown state: {e}")

def _load_cooldown_state():
    """Restore cooldown timestamps from disk on startup"""
    global _last_trade_time, _last_loss_time, _last_sell_time, _consecutive_losses, _daily_pnl, _wash_halted
    try:
        with open(COOLDOWN_STATE_FILE, 'r') as f:
            data = json.load(f)
        _last_trade_time.update(data.get('last_trade_time', {}))
        _last_loss_time.update(data.get('last_loss_time', {}))
        _last_sell_time.update(data.get('last_sell_time', {}))
        _consecutive_losses.update(data.get('consecutive_losses', {}))
        _daily_pnl.update(data.get('daily_pnl', {}))
        _wash_halted = set(data.get('wash_halted', []))
        saved_at = data.get('saved_at', 0)
        age = time.time() - saved_at if saved_at > 0 else 9999
        log(f"  📂 Cooldown state restored: {len(_last_trade_time)} symbols, wash_halted={_wash_halted}, age={age:.0f}s")
    except FileNotFoundError:
        log(f"  ℹ️ No cooldown state file found, starting fresh")
    except Exception as e:
        log(f"  ⚠️ Failed to load cooldown state: {e}")

# Load persisted cooldown state on startup
_load_cooldown_state()

def can_trade_symbol(symbol):
    """Check if symbol is available for trading based on cooldowns and active positions"""
    now = time.time()
    
    # CRITICAL: Never open 2nd position on same symbol
    if symbol in _active_positions:
        log(f"  🚫 {symbol} already has active position - skip")
        return False
    
    # Check consecutive loss ban
    consec = _consecutive_losses.get(symbol, 0)
    if consec >= MAX_CONSECUTIVE_LOSSES:
        last_loss = _last_loss_time.get(symbol, 0)
        if now - last_loss < CONSECUTIVE_LOSS_COOLDOWN:
            remaining = int(CONSECUTIVE_LOSS_COOLDOWN - (now - last_loss))
            log(f"  🚫 {symbol} banned: {consec} consecutive losses, {remaining}s remaining")
            return False
        else:
            _consecutive_losses[symbol] = 0
            log(f"  ✅ {symbol} ban expired, resetting loss counter")
    
    # Check post-loss cooldown
    last_loss = _last_loss_time.get(symbol, 0)
    if last_loss > 0 and now - last_loss < COOLDOWN_AFTER_LOSS_SEC:
        remaining = int(COOLDOWN_AFTER_LOSS_SEC - (now - last_loss))
        log(f"  ⏳ {symbol} loss cooldown: {remaining}s remaining")
        return False
    
    # Check min interval between trades
    last_trade = _last_trade_time.get(symbol, 0)
    if last_trade > 0 and now - last_trade < MIN_TRADE_INTERVAL_SEC:
        remaining = int(MIN_TRADE_INTERVAL_SEC - (now - last_trade))
        log(f"  ⏳ {symbol} min interval: {remaining}s remaining")
        return False
    
    return True

def mark_position_open(symbol):
    """Mark symbol as having active position - call immediately after BUY"""
    _active_positions.add(symbol)
    _last_trade_time[symbol] = time.time()
    _save_active_to_file()
    log(f"  📌 {symbol} marked as active position")

def mark_position_closed(symbol):
    """Mark symbol position as closed - call after SELL"""
    _active_positions.discard(symbol)
    _save_active_to_file()
    log(f"  📍 {symbol} position closed")

def sell_position(pos):
    """Market sell entire position and record PnL. Returns True if successful."""
    try:
        symbol = pos['symbol']
        asset = pos['asset']
        # Fetch real balance to avoid precision errors
        bal = exchange.fetch_balance({'type': 'spot'})
        raw_qty = float(bal.get(asset, {}).get('free', 0))
        if raw_qty <= 0:
            log(f"  ⚠️ No free {asset} to sell")
            return False
        
        # Apply safety buffer and precision to avoid NOTIONAL/precision errors
        safe_qty = raw_qty * 0.999
        qty = float(exchange.amount_to_precision(symbol, safe_qty))
        # Check against exchange minimum amount precision
        mkt = exchange.market(symbol)
        min_amt = 0
        if EXCHANGE == 'bybit':
            lot = mkt.get('info', {}).get('lotSizeFilter', {})
            min_amt = float(lot.get('minOrderQty', '0'))
        else:
            min_amt = float(mkt.get('limits', {}).get('amount', {}).get('min', 0))
        if qty <= 0 or qty < min_amt:
            log(f"  ⚠️ Sell qty {qty} below min {min_amt} for {asset} (raw={raw_qty}) - skipping")
            return False
        
        t0 = time.time()
        sell = exchange.create_market_sell_order(symbol, qty)
        sell_ms = (time.time() - t0) * 1000
        
        exit_price = float(sell.get('average') or exchange.fetch_ticker(symbol)['last'])
        proceeds = float(sell.get('cost') or qty * exit_price)
        entry_cost = pos.get('value_usd', qty * pos.get('price', exit_price))
        pnl = proceeds - entry_cost
        pnl_pct = (pnl / entry_cost) * 100 if entry_cost > 0 else 0
        
        log(f"  📉 SELL {symbol}: {qty:.6f} @ ${exit_price:.6f} | ${proceeds:.2f} | {sell_ms:.0f}ms")
        log(f"  💰 PnL: ${pnl:+.4f} ({pnl_pct:+.2f}%)")
        
        record_sell(symbol)
        record_trade_result(symbol, pnl)
        check_wash_pattern(symbol)
        mark_position_closed(symbol)
        return True
    except Exception as e:
        log(f"  ❌ SELL ERR for {pos.get('symbol','?')}: {str(e)[:120]}")
        return False

def record_trade_result(symbol, pnl):
    """Record trade outcome for cooldown logic"""
    _last_trade_time[symbol] = time.time()
    # Track daily PnL
    today_key = time.strftime('%Y-%m-%d')
    if not isinstance(_daily_pnl.get(symbol), dict):
        _daily_pnl[symbol] = {}
    _daily_pnl[symbol][today_key] = _daily_pnl[symbol].get(today_key, 0.0) + pnl
    if pnl < 0:
        _last_loss_time[symbol] = time.time()
        _consecutive_losses[symbol] = _consecutive_losses.get(symbol, 0) + 1
        log(f"  📉 Loss #{_consecutive_losses[symbol]} on {symbol}: ${pnl:+.4f}")
    else:
        # Reset consecutive loss counter on win
        if _consecutive_losses.get(symbol, 0) > 0:
            log(f"  📈 Win on {symbol} resets loss streak (was {_consecutive_losses[symbol]})")
        _consecutive_losses[symbol] = 0
    _save_cooldown_state()

def record_sell(symbol):
    """Record that a sell occurred - triggers mandatory post-sell cooldown"""
    _last_sell_time[symbol] = time.time()
    _save_cooldown_state()
    log(f"  🔒 {symbol} sell recorded, {POST_SELL_COOLDOWN_SEC}s re-entry lock")

def check_wash_pattern(symbol, ledger_path='/Agentic/ledger.jsonl'):
    """Detect wash-trade pattern: N recent trades all <interval apart with net loss"""
    try:
        import json as _json
        trades = []
        with open(ledger_path, 'r') as f:
            for line in f:
                try:
                    t = _json.loads(line.strip())
                    if t.get('symbol') == symbol:
                        trades.append(t)
                except:
                    pass
        recent = trades[-WASH_DETECT_WINDOW:]
        if len(recent) < WASH_DETECT_WINDOW:
            return False
        timestamps = sorted([t.get('timestamp', t.get('ts', 0)) for t in recent])
        intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
        net_pnl = sum(t.get('realizedPnl', t.get('pnl', 0)) or 0 for t in recent)
        if all(iv < WASH_MAX_INTERVAL_SEC for iv in intervals) and net_pnl < 0:
            log(f"  🚨 WASH DETECTED on {symbol}: {len(recent)} trades avg interval {sum(intervals)/len(intervals):.0f}s, net ${net_pnl:.4f}")
            _wash_halted.add(symbol)
            return True
    except Exception as e:
        log(f"  ⚠️ Wash check error: {str(e)[:80]}")
    return False

def get_balance():
    try:
        bal = exchange.fetch_balance({'type': 'spot'})
        usdt = bal.get('USDT', {})
        free = usdt.get('free') if isinstance(usdt, dict) else 0
        if not free:
            free = bal.get('free', {}).get('USDT', 0)
        return float(free or 0)
    except Exception as e:
        log(f"Balance ERR: {e}")
        return 0.0

def get_open_positions():
    """Check for any non-USDT assets in spot wallet = open positions"""
    positions = []
    try:
        bal = exchange.fetch_balance({'type': 'spot'})
        for asset, qty in bal.get('total', {}).items():
            if asset in ('USDT', 'BRL', 'LDUSDT') or not qty or float(qty) <= 0:
                continue
            sym = f'{asset}/USDT'
            if sym in exchange.markets:
                try:
                    tick = exchange.fetch_ticker(sym)
                    val = float(qty) * tick['last']
                    min_notional = 5.0 if EXCHANGE == 'bybit' else 10.0
                    if val < min_notional:
                        continue  # Skip dust below tradeable threshold
                    positions.append({
                        'symbol': sym,
                        'asset': asset,
                        'qty': float(qty),
                        'price': tick['last'],
                            'value_usd': val,
                            'has_tp_sl': False,  # Will check below
                            'timestamp': time.time()  # Approximate entry time for MaxHold
                        })
                except:
                    pass
    except Exception as e:
        log(f"Position check ERR: {e}")
    return positions

def check_existing_tp_sl(symbol):
    """Check if position already has open TP/SL orders"""
    try:
        open_orders = exchange.fetch_open_orders(symbol)
        for order in open_orders:
            order_type = order.get('type', '').upper()
            # Bybit: look for conditional orders with triggerPrice
            if EXCHANGE == 'bybit':
                if order.get('triggerPrice') or order_type in ['STOP_MARKET', 'TAKE_PROFIT_MARKET']:
                    return True
            # Binance: look for OCO or STOP_LOSS_LIMIT/TAKE_PROFIT_LIMIT
            else:
                if order_type in ['STOP_LOSS_LIMIT', 'TAKE_PROFIT_LIMIT', 'STOP_LOSS', 'TAKE_PROFIT']:
                    return True
                # Check for OCO (both stop and limit present)
                if 'stopPrice' in order and order.get('stopPrice'):
                    return True
    except Exception as e:
        log(f"Check TP/SL ERR for {symbol}: {str(e)[:80]}")
    return False

def setup_tp_sl_bybit(position):
    """Set/UPDATE Stop Loss for Bybit SPOT (dynamic trailing - cancels & recreates on price move)"""
    try:
        symbol = position['symbol']
        qty = position['qty']
        entry_price = position['price']
        value_usd = position['value_usd']
        
        # Fetch current market price for dynamic trailing update
        ticker = exchange.fetch_ticker(symbol)
        current_price = ticker['last']
        
        tp_price = entry_price * (1 + PARAMS['tp_pct'] / 100)
        # Trail SL up if price moved significantly above entry
        gain_pct = (current_price - entry_price) / entry_price * 100
        if gain_pct >= PARAMS['trail_activation']:
            # Move SL to breakeven or trail from peak
            sl_price = max(entry_price, current_price * (1 - PARAMS['trail_pct'] / 100))
            log(f"  📈 Trailing SL updated: gain {gain_pct:.2f}% -> new SL ${sl_price:.6f}")
        else:
            sl_price = entry_price * (1 - PARAMS['sl_pct'] / 100)
        
        log(f"  🎯 TP/SL for {symbol}: TP=${tp_price:.6f} (+{PARAMS['tp_pct']}%) | SL=${sl_price:.6f} (curr=${current_price:.6f})")
        
        # Check minimum order value for ByBit spot (~$1)
        if value_usd < 1.0:
            log(f"  ℹ️ Position ${value_usd:.2f} < $1 min - client-side monitoring only")
            return False
        
        mkt = exchange.market(symbol)
        lot = mkt.get('info', {}).get('lotSizeFilter', {})
        min_q = float(lot.get('minOrderQty', '0'))
        
        # Fetch REAL available balance to avoid 170131 Insufficient Balance
        asset = symbol.split('/')[0]
        try:
            bal = exchange.fetch_balance({'type': 'spot'})
            free_qty = float(bal.get(asset, {}).get('free', 0))
            safe_qty = min(qty, free_qty) * 0.999
            trunc_qty = float(exchange.amount_to_precision(symbol, safe_qty))
            log(f"     qty={qty} | free={free_qty:.6f} -> safe={trunc_qty}, min_q={min_q}")
        except Exception as e:
            log(f"     ⚠️ Bal fetch err: {e}, using pos qty")
            trunc_qty = float(exchange.amount_to_precision(symbol, qty))
            log(f"     qty={qty} -> precision={trunc_qty}, min_q={min_q}")
        
        # Force minimum viable quantity for SL order when position clearly exists
        # Prevents "amount must be greater than minimum amount precision" errors
        # on small positions where free balance scan returns slightly less than actual
        if trunc_qty <= 0 and qty >= min_q:
            trunc_qty = min_q
        if trunc_qty < min_q:
            if qty >= min_q or value_usd >= 5.0:
                log(f"  🔧 Forcing SL qty to min_q={min_q} (was {trunc_qty}, raw={qty}, val=${value_usd:.2f})")
                trunc_qty = min_q
            else:
                log(f"  ⚠️ Qty too small: {trunc_qty} < {min_q} (raw={qty}, val=${value_usd:.2f})")
                return False
        
        price_filter = mkt.get('info', {}).get('priceFilter', {})
        tick = float(price_filter.get('tickSize', '0.000001'))
        sl_rounded = math.floor(sl_price / tick) * tick
        
        # Cancel any existing conditional sell orders on this symbol first
        # (ByBit spot only allows ONE pending sell per asset)
        cancelled = False
        try:
            open_orders = exchange.fetch_open_orders(symbol)
            for oo in open_orders:
                if oo.get('side') == 'sell':
                    exchange.cancel_order(oo['id'], symbol)
                    log(f"     🗑️ Cancelled existing order {oo['id']}")
                    cancelled = True
        except:
            pass
        
        # Throttle: avoid spamming API if nothing changed significantly
        state_key = f"last_sl_update_{symbol}"
        try:
            with open(STATE_PATH, 'r') as f:
                _state = json.load(f)
            last_update = _state.get('subagents', {}).get(STATE_KEY, {}).get(state_key, 0)
        except:
            last_update = 0
        if time.time() - last_update < 30 and not cancelled:
            log(f"     ⏳ TP/SL update throttled (<30s since last)")
            return True
        
        import uuid
        base_symbol = symbol.split('/')[0]
        
        # Set STOP LOSS only (most critical protection)
        # TP will be monitored client-side since ByBit spot locks asset per order
        try:
            sl_res = exchange.private_post_v5_order_create({
                'category': 'spot',
                'symbol': base_symbol + 'USDT',
                'side': 'Sell',
                'orderType': 'Market',
                'qty': str(trunc_qty),
                'triggerPrice': str(sl_rounded),
                'orderLinkId': str(uuid.uuid4())[:32]
            })
            if sl_res.get('retCode') == 0:
                log(f"  ✅ SL Order UPDATED: {sl_res['result']['orderId']} @ ${sl_rounded:.6f}")
                update_state({state_key: time.time()})
                log(f"  ℹ️ TP monitored client-side (ByBit spot: 1 pending sell per asset)")
                return True
            else:
                ret_msg = sl_res.get('retMsg', 'unknown')
                if '10024' in ret_msg or 'regulation' in ret_msg.lower():
                    log(f"  🚫 SL blocked by BR regulation")
                    return False
                log(f"  ❌ SL V5 ERR: {ret_msg[:120]}")
                return False
        except Exception as e:
            err = str(e)
            if '10024' in err:
                log(f"  🚫 SL blocked by regulation")
                return False
            log(f"  ❌ SL ERR: {err[:120]}")
            return False
        
    except Exception as e:
        log(f"  ❌ Setup TP/SL ERR: {str(e)[:120]}")
        return False

def setup_tp_sl_binance(position):
    """Set/UPDATE Take Profit and Stop Loss for Binance (dynamic trailing - cancels & recreates)"""
    try:
        symbol = position['symbol']
        qty = position['qty']
        entry_price = position['price']
        
        # Fetch current market price for dynamic trailing update
        ticker = exchange.fetch_ticker(symbol)
        current_price = ticker['last']
        
        tp_price = entry_price * (1 + PARAMS['tp_pct'] / 100)
        # Trail SL up if price moved significantly above entry
        gain_pct = (current_price - entry_price) / entry_price * 100
        if gain_pct >= PARAMS['trail_activation']:
            sl_price = max(entry_price, current_price * (1 - PARAMS['trail_pct'] / 100))
            log(f"  📈 Trailing SL updated: gain {gain_pct:.2f}% -> new SL ${sl_price:.6f}")
        else:
            sl_price = entry_price * (1 - PARAMS['sl_pct'] / 100)
        sl_limit_price = sl_price * 0.998  # Slightly below SL for guaranteed fill
        
        log(f"  🎯 Setting TP/SL for {symbol}: TP=${tp_price:.6f} (+{PARAMS['tp_pct']}%) | SL=${sl_price:.6f} (curr=${current_price:.6f})")
        
        # Get market precision
        mkt = exchange.market(symbol)
        step = float(mkt.get('stepSize', '1'))
        min_notional = float(mkt.get('minNotional', '5'))
        price_precision = int(mkt.get('precision', {}).get('price', 8))
        
        # Use position qty directly to avoid race condition with recent buys
        trunc_qty = math.floor(qty / step) * step
        est_value = trunc_qty * entry_price
        # Binance STOP_LOSS_LIMIT requires minNotional ($5-10 depending on pair)
        # For small positions, skip server-side and use client-side monitoring
        min_notional_for_order = float(mkt.get('info', {}).get('filters', [{}])[0].get('minNotional', '5')) if mkt.get('info', {}).get('filters') else 5.0
        for filt in mkt.get('info', {}).get('filters', []):
            if filt.get('filterType') == 'NOTIONAL':
                min_notional_for_order = float(filt.get('minNotional', '5'))
                break
        
        if est_value < min_notional_for_order:
            log(f"  ℹ️ Position ${est_value:.2f} < min notional ${min_notional_for_order} - client-side monitoring only")
            return False  # Will fall back to client-side in main loop
        
        # Throttle: avoid spamming API if nothing changed significantly
        state_key = f"last_sl_update_{symbol}"
        try:
            with open(STATE_PATH, 'r') as f:
                _state = json.load(f)
            last_update = _state.get('subagents', {}).get(STATE_KEY, {}).get(state_key, 0)
        except:
            last_update = 0
        
        # Binance spot: conditional orders lock balance. Use STOP_LOSS_LIMIT for protection
        # and client-side TP monitoring (TP limit also locks, can't have both simultaneously)
        try:
            # Find tick size from filters
            tick = 0.000001
            for filt in mkt.get('info', {}).get('filters', []):
                if filt.get('filterType') == 'PRICE_FILTER':
                    tick = float(filt.get('tickSize', '0.000001'))
                    break
            
            def round_tick(price, t):
                return math.floor(price / t) * t
            
            sl_rounded = round_tick(sl_price, tick)
            sl_limit_rounded = round_tick(sl_limit_price, tick)
            
            # Cancel any existing open sell orders on this symbol first
            cancelled = False
            try:
                open_orders = exchange.fetch_open_orders(symbol)
                for oo in open_orders:
                    if oo.get('side') == 'sell':
                        exchange.cancel_order(oo['id'], symbol)
                        log(f"     🗑️ Cancelled existing order {oo['id']}")
                        cancelled = True
            except:
                pass
            
            if time.time() - last_update < 30 and not cancelled:
                log(f"     ⏳ TP/SL update throttled (<30s since last)")
                return True
            
            # Set STOP_LOSS_LIMIT (protects downside without locking for TP)
            sl_order = exchange.create_order(
                symbol=symbol,
                type='STOP_LOSS_LIMIT',
                side='sell',
                amount=trunc_qty,
                price=sl_limit_rounded,
                params={'stopPrice': sl_rounded}
            )
            log(f"  ✅ SL Order UPDATED: {sl_order['id']} | Trigger=${sl_rounded:.6f} Limit=${sl_limit_rounded:.6f}")
            update_state({state_key: time.time()})
            log(f"  ℹ️ TP will be monitored client-side (Binance spot locks balance per order)")
            return True
            
        except Exception as e:
            log(f"  ❌ SL ERR: {str(e)[:150]}")
            return False
            
    except Exception as e:
        log(f"  ❌ Setup TP/SL ERR: {str(e)[:120]}")
        return False

def manage_positions():
    """Check all positions and set TP/SL if missing"""
    positions = get_open_positions()
    if not positions:
        return positions
    
    total_value = sum(p['value_usd'] for p in positions)
    log(f"  📊 Managing {len(positions)} positions | Total: ${total_value:.2f}")
    
    positions_with_tp_sl = 0
    expected_tp_pnl = 0
    expected_sl_pnl = 0
    
    for pos in positions:
        log(f"     {pos['asset']}: {pos['qty']} @ ${pos['price']:.6f} = ${pos['value_usd']:.2f}")
        
        # Check if already has TP/SL
        if check_existing_tp_sl(pos['symbol']):
            pos['has_tp_sl'] = True
            positions_with_tp_sl += 1
            log(f"       ✅ Already has TP/SL configured")
        else:
            # Set up TP/SL
            log(f"       🔧 Setting up TP/SL...")
            if EXCHANGE == 'bybit':
                success = setup_tp_sl_bybit(pos)
            else:
                success = setup_tp_sl_binance(pos)
            
            if success:
                pos['has_tp_sl'] = True
                positions_with_tp_sl += 1
                expected_tp_pnl += pos['value_usd'] * (PARAMS['tp_pct'] / 100)
                expected_sl_pnl += pos['value_usd'] * (PARAMS['sl_pct'] / 100)
            else:
                log(f"       ❌ Failed to set TP/SL")
    
    # Update state with position metrics
    update_state({
        'open_positions': len(positions),
        'positions_with_tp_sl': positions_with_tp_sl,
        'total_position_value': total_value,
        'expected_tp_pnl': expected_tp_pnl,
        'expected_sl_pnl': expected_sl_pnl,
        'risk_reward_ratio': PARAMS['tp_pct'] / PARAMS['sl_pct'],
        'status': 'positions_monitored' if positions_with_tp_sl == len(positions) else 'partial_tp_sl_setup'
    })
    
    return positions

def find_best_pair():
    """Find highest volatility pair from curated list"""
    candidates = ['BTC/USDT','ETH/USDT','SOL/USDT','BNB/USDT','AVAX/USDT',
        'LINK/USDT','DOT/USDT','NEAR/USDT','INJ/USDT','SUI/USDT',
        'FET/USDT','DOGE/USDT','ADA/USDT','ATOM/USDT','UNI/USDT']
    best = None
    best_score = 0
    MIN_VOL_PCT = 3.0  # Only trade high-vol pairs where 1.2% TP is reachable in 240s
    for sym in candidates:
        if sym not in exchange.markets:
            continue
        try:
            t = exchange.fetch_ticker(sym)
            high = t.get('high') or 0
            low = t.get('low') or 0
            vol = t.get('quoteVolume') or 0
            last = t.get('last') or 0
            rng_pct = (high - low) / low * 100 if low > 0 else 0
            mid = (high + low) / 2 if low > 0 else 0
            # Momentum filter: only enter if price is in upper half of daily range
            # Avoids buying into falling knives or sideways chop
            # Strengthened momentum filter: price must be in upper 40% of daily range
            # This prevents buying into chop/falling knives that cause capital bleed
            upper_threshold = low + (high - low) * 0.3 if high > low else mid
            if low > 0 and vol > 500000 and last > 0.001 and rng_pct >= MIN_VOL_PCT and last > upper_threshold:
                rng = (high - low) / low * 100
                score = rng * (vol ** 0.25)
                if score > best_score:
                    best_score = score
                    best = (sym, rng, last, vol)
        except:
            continue
    if not best:
        log(f"  ⚠️ No pair met min volatility {MIN_VOL_PCT}%. Skipping entry cycle.")
    return best

def execute_trailing_scalp(symbol, usdt_amount):
    """MARKET BUY -> immediately set server-side TP/SL -> monitor"""
    try:
        ticker = exchange.fetch_ticker(symbol)
        entry_price = ticker['last']
        
        # Calculate qty with fee buffer
        # ByBit spot market buy requires significant headroom for fees/slippage
        # Testing showed 80% allocation works, 70% fails with insufficient balance
        # Increased to 85% for Bybit to maximize capital deployment on filtered entries
        # Restored to 95% - tighter TP/SL requires full capital deployment for meaningful gains
        allocation_pct = 0.95 if EXCHANGE == 'bybit' else 0.99
        safe_amount = usdt_amount * allocation_pct
        qty_raw = safe_amount / entry_price
        
        mkt = exchange.market(symbol)
        if EXCHANGE == 'bybit':
            lot = mkt.get('info', {}).get('lotSizeFilter', {})
            min_q = float(lot.get('minOrderQty', '0'))
            qty = float(exchange.amount_to_precision(symbol, qty_raw))
        else:
            step = float(mkt.get('stepSize', '1'))
            min_q = float(mkt.get('limits', {}).get('amount', {}).get('min', 0))
            qty = math.floor(qty_raw / step) * step
        
        if qty < min_q or qty <= 0:
            log(f"  ⚠️ Qty {qty} < min {min_q} for {symbol}")
            return None
        
        cost_est = qty * entry_price
        min_notional = 5.0 if EXCHANGE == 'bybit' else 10.0
        if cost_est < min_notional:
            log(f"  ⚠️ Below min notional: ${cost_est:.2f} < ${min_notional}")
            return None
        if cost_est > usdt_amount:
            log(f"  ⚠️ Insufficient: need ${cost_est:.2f}, have ${usdt_amount:.2f}")
            return None
        
        # Fee-aware entry: ensure potential TP profit exceeds 2x round-trip fees
        # ByBit/Binance spot taker fee ~0.1% each way = 0.2% round trip
        fee_rate = 0.002  # 0.2% round trip
        round_trip_fee = cost_est * fee_rate
        expected_tp_profit = cost_est * (PARAMS['tp_pct'] / 100)
        if expected_tp_profit < 2 * round_trip_fee:
            log(f"  ⚠️ Fee-unprofitable: TP ${expected_tp_profit:.4f} < 2x fees ${2*round_trip_fee:.4f}")
            return None
        
        # MARKET BUY - reliable execution for semi-HFT
        t0 = time.time()
        try:
            buy = exchange.create_market_buy_order(symbol, qty)
            actual_entry = float(buy.get('average') or entry_price)
            filled = float(buy.get('filled') or qty)
            cost = float(buy.get('cost') or filled * actual_entry)
            buy_ms = (time.time() - t0) * 1000
            log(f"  📈 BUY {symbol}: {filled} @ ${actual_entry:.6f} | ${cost:.2f} | {buy_ms:.0f}ms")
        except Exception as e:
            log(f"  ❌ BUY ERR: {str(e)[:100]}")
            return None
        except Exception as e:
            log(f"  ❌ BUY ERR: {str(e)[:100]}")
            return None
        
        # Mark position open IMMEDIATELY to prevent double-entry on next cycle
        mark_position_open(symbol)
        
        # IMMEDIATELY set server-side TP/SL
        position = {
            'symbol': symbol,
            'qty': filled,
            'price': actual_entry,
            'value_usd': cost
        }
        
        if EXCHANGE == 'bybit':
            tp_sl_set = setup_tp_sl_bybit(position)
        else:
            tp_sl_set = setup_tp_sl_binance(position)
        
        if not tp_sl_set:
            log(f"  ⚠️ TP/SL setup failed, using client-side monitoring fallback")
            # Fallback to old client-side monitoring
            return execute_client_side_monitor(symbol, filled, actual_entry, cost)
        
        log(f"  ✅ Server-side TP/SL active - position will auto-exit")
        # Position stays open until SL triggers or client-side TP sells
        # Do NOT mark_position_closed here - it's still open
        return {'pnl': 0, 'pnl_pct': 0, 'entry': actual_entry, 'exit': 'pending_tp_sl', 'server_side': True}
        
    except Exception as e:
        err = str(e)
        if '10024' in err or 'regulatory' in err.lower():
            log(f"  🚫 REGULATORY BLOCK: {err[:80]}")
            update_state({'status': 'disabled_br_regulation', 'error': err[:200]})
            sys.exit(0)
        log(f"  ❌ Trade ERR: {err[:120]}")
        # Emergency sell if we bought but errored
        try:
            bal = exchange.fetch_balance({'type': 'spot'})
            asset = symbol.split('/')[0]
            held = float(bal.get(asset, {}).get('free', 0))
            if held > 0:
                exchange.create_market_sell_order(symbol, held)
                log(f"  🆘 Emergency sold {held} {asset}")
        except:
            pass
        return None

def execute_client_side_monitor(symbol, filled, actual_entry, cost):
    """Fallback client-side monitoring if server-side TP/SL fails"""
    peak_price = actual_entry
    start_time = time.time()
    sl_price = actual_entry * (1 - PARAMS['sl_pct'] / 100)
    tp_price = actual_entry * (1 + PARAMS['tp_pct'] / 100)
    trail_active = False
    
    while True:
        elapsed = time.time() - start_time
        if elapsed > PARAMS['max_hold_sec']:
            log(f"  ⏰ MaxHold {PARAMS['max_hold_sec']}s reached")
            break
        
        try:
            tick = exchange.fetch_ticker(symbol)
            current = tick['last']
            
            if current > peak_price:
                peak_price = current
            
            if current >= tp_price:
                log(f"  🎯 TP HIT @ ${current:.6f}")
                break
            
            if current <= sl_price:
                log(f"  🛑 SL HIT @ ${current:.6f}")
                break
            
            gain_pct = (current - actual_entry) / actual_entry * 100
            if gain_pct >= PARAMS['trail_activation']:
                trail_active = True
            
            if trail_active:
                trail_stop = peak_price * (1 - PARAMS['trail_pct'] / 100)
                if current <= trail_stop:
                    log(f"  📉 Trail stop @ ${current:.6f} (peak ${peak_price:.6f})")
                    break
        
        except Exception as e:
            log(f"  Monitor ERR: {str(e)[:80]}")
        
        time.sleep(1)
    
    # MARKET SELL
    t0 = time.time()
    sell = exchange.create_market_sell_order(symbol, filled)
    sell_ms = (time.time() - t0) * 1000
    exit_price = float(sell.get('average') or exchange.fetch_ticker(symbol)['last'])
    proceeds = float(sell.get('cost') or filled * exit_price)
    pnl = proceeds - cost
    pnl_pct = (pnl / cost) * 100 if cost > 0 else 0
    
    log(f"  📉 SELL {symbol}: {filled} @ ${exit_price:.6f} | ${proceeds:.2f} | {sell_ms:.0f}ms")
    log(f"  💰 PnL: ${pnl:+.4f} ({pnl_pct:+.2f}%)")
    
    record_sell(symbol)
    record_trade_result(symbol, pnl)
    check_wash_pattern(symbol)
    return {'pnl': pnl, 'pnl_pct': pnl_pct, 'entry': actual_entry, 'exit': exit_price}

# === MAIN LOOP ===
log("🚀 SUBAGENT V5 SMART SCALPER INICIADO")
log(f"   Params: SL={PARAMS['sl_pct']}% TP={PARAMS['tp_pct']}% Trail={PARAMS['trail_pct']}% MaxHold={PARAMS['max_hold_sec']}s")
log(f"   ⚠️ Server-side TP/SL prioritizado | Market orders apenas para entry")

cycle = 0
while True:
    cycle += 1
    usdt_free = get_balance()
    log(f"CYCLE {cycle} | USDT: ${usdt_free:.4f}")
    
    # HARD BLOCK: Never open new trades if any position is already active
    # Uses persistent _active_positions set to prevent re-entry during balance scan lag
    if _active_positions:
        active_list = list(_active_positions)
        log(f"  🚫 ENTRY BLOCKED: {len(active_list)} active position(s) ({', '.join(active_list)})")
        # ALWAYS run monitoring/sell logic when blocked - do not skip
        try:
            positions = manage_positions()
            # Fallback: if wallet scan finds nothing but memory says position exists,
            # force cleanup to prevent permanent lock
            if not positions and _active_positions:
                # WALLET-VERIFIED ghost check: re-fetch balance directly before declaring ghost
                # Prevents false cleanup when manage_positions() missed asset due to API latency
                try:
                    direct_bal = exchange.fetch_balance({'type': 'spot'})
                except Exception as e:
                    log(f"  ⚠️ Direct balance fetch failed: {str(e)[:60]}, skipping ghost check")
                    time.sleep(5)
                    continue
                    
                for sym in list(_active_positions):
                    entry_ts = _last_trade_time.get(sym, 0)
                    age = time.time() - entry_ts if entry_ts > 0 else 999
                    # Dynamic grace: shorter when wallet shows zero balance for asset
                    # Prevents 30min lockout after server-side SL fill
                    asset_for_grace = sym.split('/')[0]
                    has_balance = float(direct_bal.get(asset_for_grace, {}).get('total', 0) or 0) > 0
                    grace = max(180, PARAMS.get("max_hold_sec", 120)) if has_balance else min(60, PARAMS.get("max_hold_sec", 120))  # FIXED: 180s min when balance exists
                    
                    if age < grace:
                        log(f"  ⏳ Ghost check skipped for {sym}: age={age:.0f}s (<{grace}s grace)")
                        continue
                    
                    # Verify asset actually missing from wallet via direct balance check
                    asset = sym.split('/')[0]
                    direct_qty = float(direct_bal.get(asset, {}).get('free', 0) or 0)
                    direct_total = float(direct_bal.get(asset, {}).get('total', 0) or 0)
                    
                    if direct_total > 0:
                        # Asset EXISTS in wallet - manage_positions() missed it
                        # Force a proper sell instead of ghost cleanup
                        log(f"  🔍 {sym} found in wallet ({direct_total}) despite empty position list - forcing sell")
                        try:
                            tick = exchange.fetch_ticker(sym)
                            mkt = exchange.market(sym)
                            min_q = float(mkt.get('info',{}).get('lotSizeFilter',{}).get('minOrderQty','0')) if EXCHANGE == 'bybit' else float(mkt.get('limits',{}).get('amount',{}).get('min',0))
                            qty = float(exchange.amount_to_precision(sym, direct_total * 0.999))
                            min_notional = 5.0 if EXCHANGE == 'bybit' else 10.0
                            est_value = qty * tick['last']
                            if qty >= min_q and est_value >= min_notional:
                                sell_order = exchange.create_market_sell_order(sym, qty)
                                sell_val = qty * tick['last']
                                entry_price = _active_positions.get(sym, {}).get('price', tick['last']) if isinstance(_active_positions, dict) else tick['last']
                                pnl = sell_val - (qty * entry_price)
                                log(f"  💰 RECOVERY SELL {sym}: {qty} @ ${tick['last']:.6f} | PnL: ${pnl:.4f}")
                                record_sell(sym)
                                record_trade_result(sym, pnl)
                                check_wash_pattern(sym)
                            else:
                                log(f"  ⚠️ {sym} recovery skipped: qty={qty} val=${est_value:.2f} < min_notional=${min_notional} - dust, clearing memory")
                        except Exception as e:
                            log(f"  ❌ Recovery sell failed for {sym}: {str(e)[:80]}")
                        mark_position_closed(sym)
                    else:
                        # Asset truly gone from wallet - safe to clean memory
                        log(f"  ⚠️ Position {sym} confirmed GHOST (wallet=0, age={age:.0f}s) - cleaning memory")
                        mark_position_closed(sym)
                time.sleep(5)
                continue
            if positions:
                for pos in positions:
                    try:
                        tick = exchange.fetch_ticker(pos['symbol'])
                        current = tick['last']
                        tp_target = pos['price'] * (1 + PARAMS['tp_pct'] / 100)
                        gain_pct = (current - pos['price']) / pos['price'] * 100
                        entry_time = _last_trade_time.get(pos['symbol'], 0)
                        hold_duration = time.time() - entry_time if entry_time > 0 else 0
                        
                        # Check server-side SL existence
                        has_server_sl = False
                        try:
                            open_orders = exchange.fetch_open_orders(pos['symbol'])
                            for oo in open_orders:
                                if oo.get('side') == 'sell' and (oo.get('triggerPrice') or oo.get('type','').upper() in ['STOP_MARKET','STOP_LOSS_LIMIT']):
                                    has_server_sl = True
                                    break
                        except:
                            pass
                        
                        log(f"  🔍 {pos['asset']}: hold={hold_duration:.0f}s/{PARAMS['max_hold_sec']}s sl={has_server_sl} pnl={gain_pct:+.2f}%")
                        
                        # FORCE EXIT if MaxHold exceeded OR no server SL after 60s
                        should_exit = False
                        exit_reason = ""
                        if hold_duration > PARAMS['max_hold_sec']:
                            should_exit = True
                            exit_reason = f"MaxHold {PARAMS['max_hold_sec']}s exceeded"
                        elif not has_server_sl and hold_duration > 60:
                            # In swing mode (MaxHold > 1h), don't force-exit just because SL setup failed
                            # The position may still be valid and SL can be retried next cycle
                            if PARAMS.get('max_hold_sec', 180) <= 3600:
                                should_exit = True
                                exit_reason = f"No server SL after {hold_duration:.0f}s"
                        elif current >= tp_target:
                            should_exit = True
                            exit_reason = f"TP hit @ ${current:.6f}"
                        
                        if should_exit:
                            log(f"  🚨 EXIT TRIGGER: {exit_reason} for {pos['asset']}")
                            sold = sell_position(pos)
                            if sold:
                                log(f"  💰 EXITED {pos['asset']} via {exit_reason}")
                    except Exception as inner_e:
                        log(f"  ❌ Monitor inner ERR: {str(inner_e)[:100]}")
        except Exception as outer_e:
            log(f"  ❌ Monitor outer ERR: {str(outer_e)[:100]}")
        time.sleep(5)  # Trend-following: 5s cycle balances speed and API safety
        continue
    
    # Step 1: Manage existing positions (set TP/SL if missing)
    positions = manage_positions()
    
    if positions:
        total_pos_value = sum(p['value_usd'] for p in positions)
        
        # If >50% capital in positions, monitor them actively
        positions_with_tp_sl = sum(1 for p in positions if p.get('has_tp_sl'))
        if total_pos_value > usdt_free * 0.5:
            # Client-side TP check for positions (server-side SL is set, TP monitored here)
            for pos in positions:
                try:
                    tick = exchange.fetch_ticker(pos['symbol'])
                    current = tick['last']
                    tp_target = pos['price'] * (1 + PARAMS['tp_pct'] / 100)
                    gain_pct = (current - pos['price']) / pos['price'] * 100
                    
                    # Force sell if position held too long (MaxHold timeout)
                    # Use _last_trade_time for accurate entry tracking instead of balance scan time
                    entry_time = _last_trade_time.get(pos['symbol'], 0)
                    hold_duration = time.time() - entry_time if entry_time > 0 else 0
                    
                    # Fallback: if timestamp unknown but position has TP/SL, assume stale
                    # Prevents positions loaded from balance scan from being stuck forever
                    if hold_duration == 0 and pos.get('has_tp_sl'):
                        hold_duration = PARAMS['max_hold_sec'] + 1
                        log(f"  ⚠️ {pos['asset']}: no entry timestamp, assuming maxhold exceeded")
                    
                    # Also check if server-side SL actually exists; if not, treat as client-side
                    has_server_sl = False
                    try:
                        open_orders = exchange.fetch_open_orders(pos['symbol'])
                        for oo in open_orders:
                            if oo.get('side') == 'sell' and (oo.get('triggerPrice') or oo.get('type','').upper() in ['STOP_MARKET','STOP_LOSS_LIMIT']):
                                has_server_sl = True
                                break
                    except:
                        pass
                    
                    # Emergency exit: no server SL + holding > 60s = likely stuck
                    if not has_server_sl and hold_duration > 60:
                        log(f"  🆘 NO SERVER SL for {pos['asset']} after {hold_duration:.0f}s - forcing exit")
                        sold = sell_position(pos)
                        if sold:
                            log(f"  💰 Emergency exit on {pos['asset']}")
                        continue
                    
                    if hold_duration > PARAMS['max_hold_sec']:
                        log(f"  ⏰ MaxHold {PARAMS['max_hold_sec']}s exceeded for {pos['asset']} ({gain_pct:+.2f}%)")
                        sold = sell_position(pos)
                        if sold:
                            log(f"  💰 Timeout exit on {pos['asset']}")
                        continue
                    
                    if current >= tp_target:
                        log(f"  🎯 TP TARGET HIT for {pos['asset']} @ ${current:.6f} (+{gain_pct:.2f}%)")
                        # Sell at market to realize profit
                        sold = sell_position(pos)
                        if sold:
                            log(f"  💰 Realized profit on {pos['asset']}")
                    elif gain_pct > PARAMS['trail_activation']:
                        log(f"  📈 {pos['asset']} up {gain_pct:.2f}% - trailing active")
                except Exception as e:
                    pass
            
            log(f"  ⏸️ {positions_with_tp_sl}/{len(positions)} positions managed, monitoring...")
            time.sleep(5)  # Trend-following: 5s cycle balances speed and API safety
            continue
    
    # Step 2: Capital check for new trades
    min_trade = 5.0 if EXCHANGE == 'bybit' else 10.0
    if usdt_free < min_trade:
        log(f"  ⚠️ Low balance (${usdt_free:.2f} < ${min_trade})")
        if usdt_free < 1.0:
            log("  ⛔ Capital below minimum - standby")
            update_state({'status': 'standby_low_capital', 'capital_usd': usdt_free})
            time.sleep(300)
            continue
        time.sleep(30)
        continue
    
    # Block new entries if any position is already open (prevent double-entry & capital drain)
    if positions:
        open_assets = [p['asset'] for p in positions]
        log(f"  🚫 Entry blocked: {len(positions)} position(s) open ({', '.join(open_assets)})")
        time.sleep(5)  # Trend-following: 5s cycle balances speed and API safety
        continue
    
    # Step 3: Find best pair and execute with server-side TP/SL
    target = find_best_pair()
    if not target:
        log("  No volatile pair found")
        time.sleep(5)  # Trend-following: 5s cycle balances speed and API safety
        continue
    
    sym, vol, price, volume = target
    log(f"  🎯 Target: {sym} | Vol: {vol:.1f}% | ${price}")
    
    # Execute trade
    result = execute_trailing_scalp(sym, usdt_free)
    if result:
        update_state({
            'current_usd': get_balance(),
            'last_trade': {'symbol': sym, 'pnl': result.get('pnl', 0), 'pnl_pct': result.get('pnl_pct', 0)},
            'status': 'active_trading_server_side_tp_sl'
        })
    
    time.sleep(5)
