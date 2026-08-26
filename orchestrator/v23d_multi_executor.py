#!/usr/bin/env python3
"""V23d-v5 MULTI-COIN REAL EXECUTOR
Approved coins from backtest: AVAX/USDT, BCH/USDT
XRP/USDT continues running in separate process (session 64312)
Strategy: RSI<30 + BB(20,2) Lower + Vol>SMA*0.8 | Exit: SMA20 or Stop -0.2% | Hold 2h
"""
import ccxt, os, json, time, math, requests
from datetime import datetime, timezone
from dotenv import load_dotenv
import sys
from pathlib import Path

# Add src to path for telegram_gate import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

load_dotenv('/root/.automaton/bybit-murre.env', override=True)
load_dotenv('/Agentic/.env', override=False)

LOG_FILE = '/Agentic/orchestrator/v23d_multi.log'
LEDGER_FILE = '/Agentic/ledger.jsonl'
STATE_FILE = '/Agentic/orchestrator/v23d_multi_state.json'
SYMBOLS = ['AVAX/USDT', 'BCH/USDT']  # XRP handled by existing sniper_v23d_xrp.py
FEE_RATE = 0.0004
RSI_MAX = 30
BB_PERIOD = 20
BB_MULT = 2.0
VOL_SMA_MULT = 0.8
STOP_PCT = 0.002
MAX_HOLD_MIN = 120
TG_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TG_CHAT = '8309124582'

# Import central telegram gate - fail-closed
try:
    from telegram_gate import send_financial_event, notify_trade_realized, _log as gate_log
    GATE_AVAILABLE = True
except ImportError as e:
    print(f"[FATAL] Cannot import telegram_gate: {e}", flush=True)
    GATE_AVAILABLE = False

def log(msg):
    ts = datetime.now(timezone.utc).strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, 'a') as f:
        f.write(line + '\n')

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def append_ledger(entry):
    with open(LEDGER_FILE, 'a') as f:
        f.write(json.dumps(entry) + '\n')

def send_tg_blocked(msg):
    """BLOCKED: Direct Telegram sends are disabled. Use telegram_gate only."""
    log(f"[TG_BLOCKED] Direct send_tg call suppressed: {msg[:80]}...")
    return False

def send_trade_realized(sym, net_pnl, gross_pnl, fees, exit_reason, trade_count, win_rate):
    """Send trade realized event through central gate with full schema."""
    if not GATE_AVAILABLE:
        log(f"[TG_GATE_UNAVAILABLE] Trade realized but gate missing: {sym} net={net_pnl}")
        return False
    
    event_id = f"v23d_multi_{sym}_{int(time.time())}_{trade_count}"
    try:
        result = notify_trade_realized(
            process_id="v23d_multi_executor",
            asset=sym.split('/')[0],
            gross=gross_pnl,
            fees=fees,
            net=net_pnl,
            currency="USDT",
            external_reference=f"exit_{exit_reason}_t{trade_count}",
            source="bybit_spot_v23d_multi",
            metadata={
                "symbol": sym,
                "exit_reason": exit_reason,
                "trade_count": trade_count,
                "win_rate": win_rate,
                "mode": "REAL"
            }
        )
        if result:
            log(f"[TG_GATE_OK] Trade realized sent: {sym} net={net_pnl:+.6f}")
        else:
            log(f"[TG_GATE_REJECTED] Trade event rejected by gate: {sym}")
        return result
    except Exception as e:
        log(f"[TG_GATE_ERROR] Failed to send trade realized: {e}")
        return False

def calc_rsi(closes, period=14):
    if len(closes) < period + 1: return 50
    gains, losses = [], []
    for i in range(-period, 0):
        diff = closes[i] - closes[i-1]
        gains.append(max(0, diff))
        losses.append(max(0, -diff))
    avg_gain = sum(gains)/period
    avg_loss = sum(losses)/period
    if avg_loss == 0: return 100
    rs = avg_gain / avg_loss
    return 100 - (100/(1+rs))

def calc_bb(closes, period=20, std_mult=2.0):
    if len(closes) < period: return None, None, None
    window = closes[-period:]
    sma = sum(window)/period
    std = (sum((x-sma)**2 for x in window)/period)**0.5
    return sma, sma - std_mult*std, sma + std_mult*std

def calc_vol_sma(volumes, period=20):
    if len(volumes) < period: return 0
    return sum(volumes[-period:]) / period

state = {
    "version": "v23d_v5_multi_real",
    "start_time": time.time(),
    "symbols": SYMBOLS,
    "trades": 0, "wins": 0, "pnl": 0.0,
    "running": True, "errors": 0,
    "max_drawdown": 0.0, "peak_pnl": 0.0,
    "mode": "REAL",
    "positions": {}
}

log("=== V23d-v5 MULTI-COIN REAL STARTING ===")
log(f"Coins: {', '.join(SYMBOLS)} (XRP handled separately)")
log(f"Params: RSI<{RSI_MAX} BB({BB_PERIOD},{BB_MULT}) Vol>SMA*{VOL_SMA_MULT}")
log(f"Exit: SMA20 | Stop -{STOP_PCT*100}% | Hold {MAX_HOLD_MIN}min")
log("Mode: REAL (backtest validated)")

ex = ccxt.bybit({
    'apiKey': os.getenv('BYBIT_REAL_API_KEY'),
    'secret': os.getenv('BYBIT_REAL_API_SECRET'),
    'options': {'defaultType': 'spot'},
    'enableRateLimit': True
})
ex.load_markets()

last_report = 0
# Startup message is NOT a financial event - blocked by gate policy
log(f"[TG_BLOCKED] Startup message suppressed (not realized capital): V23d-v5 MULTI INICIADO")

while state['running']:
    try:
        for sym in SYMBOLS:
            if sym in state['positions']:
                pos = state['positions'][sym]
                candles = ex.fetch_ohlcv(sym, timeframe='5m', limit=30)
                closes = [c[4] for c in candles]
                current_price = closes[-1]
                elapsed_min = (time.time() - pos['ts']) / 60
                sma20, _, _ = calc_bb(closes, BB_PERIOD, BB_MULT)
                curr_sma = sma20 if sma20 else pos['entry']
                hit_target = current_price >= curr_sma
                hit_stop = current_price <= pos['entry'] * (1 - STOP_PCT)
                timeout = elapsed_min > MAX_HOLD_MIN
                exit_reason = None
                if hit_target: exit_reason = "TARGET_SMA20"
                elif hit_stop: exit_reason = "STOP_LOSS"
                elif timeout: exit_reason = "TIMEOUT_2H"
                if exit_reason:
                    try:
                        bal = ex.fetch_balance()
                        base = sym.split('/')[0]
                        base_free = float(bal.get(base, {}).get('free', 0))
                        m = ex.market(sym)
                        amt_step = m.get('precision', {}).get('amount', 1)
                        if isinstance(amt_step, int): amt_step = 10**(-amt_step) if amt_step<0 else amt_step
                        sell_qty = math.floor(base_free * 0.998 / amt_step) * amt_step
                        if sell_qty >= m['limits']['amount']['min']:
                            order = ex.create_market_sell_order(sym, sell_qty)
                            fill_px = float(order.get('average') or current_price)
                            gross = (fill_px - pos['entry']) * sell_qty
                            fees = (fill_px + pos['entry']) * sell_qty * FEE_RATE
                            net = gross - fees
                            append_ledger({
                                "ts": datetime.now(timezone.utc).isoformat(),
                                "exchange": "bybit", "symbol": sym,
                                "strategy": "v23d_mean_rev_v5_multi_real",
                                "entry_price": round(pos['entry'], 6),
                                "exit_price": round(fill_px, 6),
                                "qty": sell_qty,
                                "gross_pnl": round(gross, 6),
                                "fees_usdt": round(fees, 6),
                                "net_pnl": round(net, 6),
                                "win": net > 0, "exit_reason": exit_reason,
                                "mode": "REAL"
                            })
                            state['trades'] += 1
                            if net > 0: state['wins'] += 1
                            state['pnl'] += net
                            if state['pnl'] > state['peak_pnl']: state['peak_pnl'] = state['pnl']
                            dd = state['peak_pnl'] - state['pnl']
                            if dd > state['max_drawdown']: state['max_drawdown'] = dd
                            emoji = "✅" if net > 0 else "❌"
                            log(f"{emoji} EXIT {sym} {exit_reason}: entry={pos['entry']:.4f} exit={fill_px:.4f} net={net:+.6f}")
                            del state['positions'][sym]
                            wr = (state['wins']/state['trades']*100) if state['trades'] > 0 else 0
                            # Send through central gate - only confirmed realized trades
                            send_trade_realized(
                                sym=sym,
                                net_pnl=net,
                                gross_pnl=gross,
                                fees=fees,
                                exit_reason=exit_reason,
                                trade_count=state['trades'],
                                win_rate=wr
                            )
                    except Exception as e:
                        log(f"EXIT ERROR {sym}: {str(e)[:120]}")
                continue
            try:
                candles = ex.fetch_ohlcv(sym, timeframe='5m', limit=100)
                closes = [c[4] for c in candles]
                volumes = [c[5] for c in candles]
                current_price = closes[-1]
                rsi = calc_rsi(closes)
                sma20, lower_bb, _ = calc_bb(closes, BB_PERIOD, BB_MULT)
                vol_sma = calc_vol_sma(volumes)
                current_vol = volumes[-1]
                if (lower_bb and current_price < lower_bb and
                    rsi < RSI_MAX and current_vol > vol_sma * VOL_SMA_MULT):
                    bal = ex.fetch_balance()
                    usdt_free = float(bal.get('USDT', {}).get('free', 0))
                    max_per_coin = usdt_free * 0.45
                    if max_per_coin >= 5.0:
                        m = ex.market(sym)
                        buy_price = round(current_price, 6)
                        qty_raw = (max_per_coin * 0.99) / buy_price
                        amt_step = m.get('precision', {}).get('amount', 1)
                        if isinstance(amt_step, int): amt_step = 10**(-amt_step) if amt_step<0 else amt_step
                        buy_qty = math.floor(qty_raw / amt_step) * amt_step
                        if buy_qty >= m['limits']['amount']['min']:
                            order = ex.create_limit_buy_order(sym, buy_qty, buy_price)
                            log(f"🟢 ENTRY {sym}: RSI={rsi:.1f} Px={buy_price:.4f}<BB_L={lower_bb:.4f}")
                            state['positions'][sym] = {'entry': buy_price, 'qty': buy_qty, 'ts': time.time()}
                            # ENTRY signals are NOT financial events - blocked by gate policy
                            log(f"[TG_BLOCKED] Entry signal suppressed (not realized capital): {sym}")
            except Exception as e:
                log(f"ENTRY ERROR {sym}: {str(e)[:120]}")
        if time.time() - last_report > 900:
            pos_str = ", ".join([f"{s}@{p['entry']:.4f}" for s,p in state['positions'].items()]) or "FLAT"
            wr = (state['wins']/max(state['trades'],1)*100)
            log(f"[STATUS] {pos_str} | T:{state['trades']} WR:{wr:.0f}% PnL:{state['pnl']:+.6f}")
            last_report = time.time()
        save_state(state)
        time.sleep(30)
    except KeyboardInterrupt:
        break
    except Exception as e:
        state['errors'] += 1
        log(f"MAIN ERROR: {str(e)[:150]}")
        time.sleep(30)

state['running'] = False
save_state(state)
log(f"=== V23d-v5 MULTI STOPPED: trades={state['trades']} pnl={state['pnl']:+.6f} ===")
