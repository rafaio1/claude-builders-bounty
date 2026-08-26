#!/usr/bin/env python3
"""V23d-v5 XRP Mean Reversion - PAPER + REAL HYBRID MODE
Paper trading active while RSI > 30 to validate edge in real-time.
Auto-switches to REAL orders when signal triggers AND paper WR > 40%.
Strategy: RSI<30 + BB(20,2) Lower + Vol>SMA*0.8 | Exit: SMA20 or Stop -0.2% | Hold 2h
"""
import ccxt, os, json, time, math, requests
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv('/root/.automaton/bybit-murre.env', override=True)
load_dotenv('/Agentic/.env', override=False)

LOG_FILE = '/Agentic/orchestrator/v23d_xrp.log'
LEDGER_FILE = '/Agentic/ledger.jsonl'
STATE_FILE = '/Agentic/orchestrator/v23d_state.json'
SYMBOL = 'XRP/USDT'
FEE_RATE = 0.0004
CHECK_INTERVAL = 30
TG_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TG_CHAT = '8309124582'

RSI_MAX = 30
BB_PERIOD = 20
BB_MULT = 2.0
VOL_SMA_MULT = 0.8
STOP_PCT = 0.002
MAX_HOLD_CANDLES = 24
PAPER_MIN_WR_FOR_LIVE = 40.0
PAPER_MIN_TRADES_FOR_LIVE = 3

state = {
    "version": "v23d_v5",
    "start_time": time.time(),
    "trades": 0,
    "wins": 0,
    "pnl": 0.0,
    "running": True,
    "last_signal": None,
    "errors": 0,
    "max_drawdown": 0.0,
    "peak_pnl": 0.0,
    "streak": 0,
    "gross_profit": 0.0,
    "gross_loss": 0.0,
    "paper_trades": 0,
    "paper_wins": 0,
    "paper_pnl": 0.0,
    "mode": "PAPER"
}

def log(msg):
    ts = datetime.now(timezone.utc).strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, 'a') as f:
        f.write(line + '\n')

def save_state():
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def append_ledger(entry):
    with open(LEDGER_FILE, 'a') as f:
        f.write(json.dumps(entry) + '\n')

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

def get_equity_curve(n=20):
    try:
        entries = []
        with open(LEDGER_FILE) as f:
            for line in f:
                try:
                    e = json.loads(line.strip())
                    if e.get('exchange') == 'bybit':
                        entries.append(e.get('net_pnl', 0))
                except: pass
        recent = entries[-n:]
        if not recent: return "No data"
        cumulative = []
        running = 0
        for p in recent:
            running += p
            cumulative.append(running)
        mn, mx = min(cumulative), max(cumulative)
        rng = mx - mn if mx != mn else 0.001
        height = 6
        lines = []
        for row in range(height, -1, -1):
            threshold = mn + (rng * row / height)
            chars = []
            for v in cumulative:
                chars.append('█' if v >= threshold else ' ')
            lines.append(''.join(chars))
        return '\n'.join(lines)
    except Exception:
        return "Error"

def send_tg_report(ex, position, rsi, bb_lower, sma20, current_price, paper_pos):
    if not TG_TOKEN: return
    try:
        bal = ex.fetch_balance()
        usdt_free = float(bal.get('USDT', {}).get('free', 0))
        
        trades = state['trades']
        wins = state['wins']
        wr = (wins/trades*100) if trades > 0 else 0
        
        pt = state['paper_trades']
        pw = state['paper_wins']
        pwr = (pw/pt*100) if pt > 0 else 0
        
        pf = state['gross_profit'] / abs(state['gross_loss']) if state['gross_loss'] != 0 else float('inf')
        pf_str = f"{pf:.2f}" if pf != float('inf') else "∞"
        
        mode_emoji = "🟢 LIVE" if state['mode'] == 'LIVE' else "📝 PAPER"
        pos_status = f"🟢 EM POSIÇÃO @ {position['entry']:.4f}" if position else ("📝 PAPER POS @ " + str(round(paper_pos['entry'],4)) if paper_pos else "⏳ AGUARDANDO")
        dist_pct = ((current_price - bb_lower) / bb_lower * 100) if bb_lower else 0
        
        equity_ascii = get_equity_curve(20)
        
        msg = f"""<b>📊 RELATÓRIO V23d-v5 ({mode_emoji})</b>
━━━━━━━━━━━━━━━━━━━━━━━
<b>🎯 ESTRATÉGIA</b>
Mean Rev: BB(20,2)+RSI&lt;30+Vol&gt;SMA*0.8
Exit: SMA20 | Stop -0.2% | Hold 2h

<b>📈 PERFORMANCE REAL</b>
Trades: {trades} | Wins: {wins} | WR: <b>{wr:.1f}%</b>
PnL: <b>{state['pnl']:+.6f} USDT</b> | PF: {pf_str}

<b>📝 PERFORMANCE PAPER</b>
Trades: {pt} | Wins: {pw} | WR: <b>{pwr:.1f}%</b>
PnL Paper: {state['paper_pnl']:+.6f} USDT
Gate Live: WR&gt;{PAPER_MIN_WR_FOR_LIVE}% &amp; Trades&gt;{PAPER_MIN_TRADES_FOR_LIVE}

<b>💰 MERCADO</b>
USDT: {usdt_free:.4f} | Mode: {mode_emoji}
RSI: {rsi:.1f} | BB_L: {str(round(bb_lower,4)) if bb_lower else 'N/A'}
Preço: {current_price:.4f} | Dist: {dist_pct:+.2f}%
Status: {pos_status}

<b>📉 EQUITY CURVE</b>
<pre>{equity_ascii}</pre>
━━━━━━━━━━━━━━━━━━━━━━━
<i>{datetime.now(timezone.utc).strftime('%H:%M UTC')}</i>"""
        
        requests.post(f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage', json={
            'chat_id': TG_CHAT, 'text': msg, 'parse_mode': 'HTML'
        }, timeout=10)
    except Exception as e:
        log(f"TG REPORT ERROR: {str(e)[:100]}")

def main():
    log("=== V23d-v5 HYBRID PAPER/LIVE STARTING ===")
    log(f"Mode: PAPER until WR>{PAPER_MIN_WR_FOR_LIVE}% & {PAPER_MIN_TRADES_FOR_LIVE}+ trades")
    
    ex = ccxt.bybit({
        'apiKey': os.getenv('BYBIT_REAL_API_KEY'),
        'secret': os.getenv('BYBIT_REAL_API_SECRET'),
        'options': {'defaultType': 'spot'},
        'enableRateLimit': True
    })
    ex.load_markets()
    
    position = None       # Real position
    paper_pos = None      # Virtual position for training
    last_report_time = 0
    
    while state['running']:
        try:
            candles = ex.fetch_ohlcv(SYMBOL, timeframe='5m', limit=100)
            closes = [c[4] for c in candles]
            highs = [c[2] for c in candles]
            lows = [c[3] for c in candles]
            volumes = [c[5] for c in candles]
            
            current_price = closes[-1]
            rsi = calc_rsi(closes)
            sma20, lower_bb, _ = calc_bb(closes, BB_PERIOD, BB_MULT)
            vol_sma = calc_vol_sma(volumes)
            current_vol = volumes[-1]
            
            # Check if we should switch from PAPER to LIVE
            if state['mode'] == 'PAPER':
                pwr = (state['paper_wins']/state['paper_trades']*100) if state['paper_trades'] > 0 else 0
                if state['paper_trades'] >= PAPER_MIN_TRADES_FOR_LIVE and pwr >= PAPER_MIN_WR_FOR_LIVE:
                    state['mode'] = 'LIVE'
                    log(f"🟢 MODE SWITCH: PAPER → LIVE (WR={pwr:.1f}% after {state['paper_trades']} paper trades)")
                    send_tg_report(ex, position, rsi, lower_bb, sma20, current_price, paper_pos)
            
            is_live = state['mode'] == 'LIVE'
            
            # === HANDLE REAL POSITION EXIT ===
            if position:
                elapsed_min = (time.time() - position['ts']) / 60
                current_sma20 = sma20 if sma20 else position['entry']
                hit_target = current_price >= current_sma20
                hit_stop = current_price <= position['entry'] * (1 - STOP_PCT)
                timeout = elapsed_min > (MAX_HOLD_CANDLES * 5)
                
                exit_reason = None
                if hit_target: exit_reason = "TARGET_SMA20"
                elif hit_stop: exit_reason = "STOP_LOSS"
                elif timeout: exit_reason = "TIMEOUT_2H"
                
                if exit_reason:
                    try:
                        bal = ex.fetch_balance()
                        xrp_free = float(bal.get('XRP', {}).get('free', 0))
                        m = ex.market(SYMBOL)
                        amt_step = m.get('precision', {}).get('amount', 1)
                        if isinstance(amt_step, int): amt_step = 10**(-amt_step) if amt_step<0 else amt_step
                        sell_qty = math.floor(xrp_free * 0.998 / amt_step) * amt_step
                        
                        if sell_qty >= m['limits']['amount']['min']:
                            order = ex.create_market_sell_order(SYMBOL, sell_qty)
                            fill_px = float(order.get('average') or current_price)
                            gross = (fill_px - position['entry']) * sell_qty
                            fees = (fill_px + position['entry']) * sell_qty * FEE_RATE
                            net = gross - fees
                            
                            append_ledger({
                                "ts": datetime.now(timezone.utc).isoformat(),
                                "exchange": "bybit", "symbol": SYMBOL,
                                "strategy": "v23d_mean_rev_v5",
                                "entry_price": round(position['entry'], 6),
                                "exit_price": round(fill_px, 6),
                                "qty": sell_qty,
                                "gross_pnl": round(gross, 6),
                                "fees_usdt": round(fees, 6),
                                "net_pnl": round(net, 6),
                                "win": net > 0, "exit_reason": exit_reason,
                                "mode": "LIVE"
                            })
                            state['trades'] += 1
                            if net > 0:
                                state['wins'] += 1
                                state['gross_profit'] += net
                                state['streak'] = max(1, state['streak'] + 1)
                            else:
                                state['gross_loss'] += net
                                state['streak'] = min(-1, state['streak'] - 1)
                            state['pnl'] += net
                            if state['pnl'] > state['peak_pnl']: state['peak_pnl'] = state['pnl']
                            dd = state['peak_pnl'] - state['pnl']
                            if dd > state['max_drawdown']: state['max_drawdown'] = dd
                            
                            emoji = "✅" if net > 0 else "❌"
                            log(f"{emoji} LIVE EXIT {exit_reason}: entry={position['entry']:.4f} exit={fill_px:.4f} net={net:+.6f}")
                            position = None
                            send_tg_report(ex, position, rsi, lower_bb, sma20, current_price, paper_pos)
                    except Exception as e:
                        log(f"LIVE EXIT ERROR: {str(e)[:120]}")
            
            # === HANDLE PAPER POSITION EXIT ===
            elif paper_pos:
                elapsed_min = (time.time() - paper_pos['ts']) / 60
                current_sma20 = sma20 if sma20 else paper_pos['entry']
                hit_target = current_price >= current_sma20
                hit_stop = current_price <= paper_pos['entry'] * (1 - STOP_PCT)
                timeout = elapsed_min > (MAX_HOLD_CANDLES * 5)
                
                exit_reason = None
                if hit_target: exit_reason = "TARGET_SMA20"
                elif hit_stop: exit_reason = "STOP_LOSS"
                elif timeout: exit_reason = "TIMEOUT_2H"
                
                if exit_reason:
                    exit_px = current_price
                    gross = (exit_px - paper_pos['entry']) * paper_pos['qty']
                    fees = (exit_px + paper_pos['entry']) * paper_pos['qty'] * FEE_RATE
                    net = gross - fees
                    
                    append_ledger({
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "exchange": "bybit", "symbol": SYMBOL,
                        "strategy": "v23d_mean_rev_v5_paper",
                        "entry_price": round(paper_pos['entry'], 6),
                        "exit_price": round(exit_px, 6),
                        "qty": paper_pos['qty'],
                        "gross_pnl": round(gross, 6),
                        "fees_usdt": round(fees, 6),
                        "net_pnl": round(net, 6),
                        "win": net > 0, "exit_reason": exit_reason,
                        "mode": "PAPER"
                    })
                    state['paper_trades'] += 1
                    if net > 0: state['paper_wins'] += 1
                    state['paper_pnl'] += net
                    
                    emoji = "✅" if net > 0 else "❌"
                    log(f"{emoji} PAPER EXIT {exit_reason}: entry={paper_pos['entry']:.4f} exit={exit_px:.4f} net={net:+.6f}")
                    paper_pos = None
                    send_tg_report(ex, position, rsi, lower_bb, sma20, current_price, paper_pos)
            
            # === CHECK ENTRY SIGNAL ===
            entry_signal = (lower_bb and current_price < lower_bb and 
                           rsi < RSI_MAX and current_vol > vol_sma * VOL_SMA_MULT)
            
            if entry_signal and not position and not paper_pos:
                bal = ex.fetch_balance()
                usdt_free = float(bal.get('USDT', {}).get('free', 0))
                
                if usdt_free >= 5.0:
                    m = ex.market(SYMBOL)
                    buy_price = round(current_price, 6)
                    qty_raw = (usdt_free * 0.99) / buy_price
                    amt_step = m.get('precision', {}).get('amount', 1)
                    if isinstance(amt_step, int): amt_step = 10**(-amt_step) if amt_step<0 else amt_step
                    buy_qty = math.floor(qty_raw / amt_step) * amt_step
                    
                    if buy_qty >= m['limits']['amount']['min']:
                        if is_live:
                            # REAL ORDER
                            try:
                                order = ex.create_limit_buy_order(SYMBOL, buy_qty, buy_price)
                                log(f"🟢 LIVE ENTRY: RSI={rsi:.1f} Px={buy_price:.4f}<BB_L={lower_bb:.4f}")
                                log(f"   BUY: qty={buy_qty} @ {buy_price}")
                                position = {'entry': buy_price, 'qty': buy_qty, 'ts': time.time()}
                                state['last_signal'] = datetime.now(timezone.utc).isoformat()
                                send_tg_report(ex, position, rsi, lower_bb, sma20, current_price, paper_pos)
                            except Exception as e:
                                log(f"LIVE ENTRY ERROR: {str(e)[:120]}")
                        else:
                            # PAPER TRADE
                            log(f"📝 PAPER ENTRY: RSI={rsi:.1f} Px={buy_price:.4f}<BB_L={lower_bb:.4f}")
                            log(f"   VIRTUAL BUY: qty={buy_qty} @ {buy_price}")
                            paper_pos = {'entry': buy_price, 'qty': buy_qty, 'ts': time.time()}
                            state['last_signal'] = datetime.now(timezone.utc).isoformat()
                            send_tg_report(ex, position, rsi, lower_bb, sma20, current_price, paper_pos)
            
            # PERIODIC REPORT
            if time.time() - last_report_time > 900:
                pos_str = f"LIVE@{position['entry']:.4f}" if position else (f"PAPER@{paper_pos['entry']:.4f}" if paper_pos else "FLAT")
                bb_str = str(round(lower_bb, 4)) if lower_bb else "N/A"
                pwr = (state['paper_wins']/max(state['paper_trades'],1)*100)
                wr = (state['wins']/max(state['trades'],1)*100)
                log(f"[STATUS] {state['mode']} {pos_str} | Real:{state['trades']}T/{wr:.0f}%WR Paper:{state['paper_trades']}T/{pwr:.0f}%WR | RSI:{rsi:.1f} BB_L:{bb_str}")
                send_tg_report(ex, position, rsi, lower_bb, sma20, current_price, paper_pos)
                last_report_time = time.time()
            
            save_state()
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            state['errors'] += 1
            log(f"MAIN ERROR: {str(e)[:150]}")
            time.sleep(30)
    
    state['running'] = False
    save_state()
    log(f"=== V23d-v5 STOPPED: real={state['trades']} paper={state['paper_trades']} pnl={state['pnl']:+.6f} ===")

if __name__ == '__main__':
    main()
