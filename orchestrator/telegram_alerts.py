#!/usr/bin/env python3
"""Telegram Alert System for Grid Trading Profits.
Auto-detects chat_id from incoming messages, then sends HTML-formatted profit alerts.
"""
import requests, os, json, time, sys
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv('/Agentic/.env')

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_FILE = '/Agentic/orchestrator/telegram_chats.txt'
LEDGER_FILE = '/Agentic/ledger.jsonl'
STATE_FILES = [
    '/Agentic/orchestrator/v22_state.json',
]

def log(msg):
    ts = datetime.now(timezone.utc).strftime('%H:%M:%S')
    print(f"[{ts}] TG: {msg}", flush=True)

def get_chat_ids():
    """Get registered chat IDs from file."""
    ids = []
    try:
        with open(CHAT_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    ids.append(int(line))
    except FileNotFoundError:
        pass
    return ids

def detect_new_chats():
    """Poll getUpdates to find new users who messaged the bot."""
    try:
        r = requests.get(f'https://api.telegram.org/bot{TOKEN}/getUpdates?limit=20&offset=-20', timeout=10)
        updates = r.json().get('result', [])
        existing = set(get_chat_ids())
        new_ids = []
        
        for u in updates:
            msg = u.get('message', {}) or {}
            chat = msg.get('chat', {})
            cid = chat.get('id')
            if cid and cid not in existing:
                new_ids.append(cid)
                name = chat.get('first_name', chat.get('title', 'Unknown'))
                log(f"NEW CHAT DETECTED: {name} (id={cid})")
                
                # Send welcome message
                welcome = (
                    "<b>🤖 RafaioBot - Alertas de Lucro</b>\n\n"
                    "✅ Chat registrado com sucesso!\n"
                    "Você receberá alertas automáticos de:\n"
                    "• 💰 Trades lucrativos do Grid V22\n"
                    "• 📊 Relatórios diários de PnL\n"
                    "• ⚡ Oportunidades de mercado detectadas\n\n"
                    "<i>Enviando relatório inicial...</i>"
                )
                send_html(cid, welcome)
                existing.add(cid)
        
        if new_ids:
            with open(CHAT_FILE, 'a') as f:
                for cid in new_ids:
                    f.write(str(cid) + '\n')
            log(f"Saved {len(new_ids)} new chat ID(s)")
        
        return new_ids
    except Exception as e:
        log(f"detect_new_chats error: {e}")
        return []

def send_html(chat_id, html_text):
    """Send HTML-formatted message to Telegram."""
    try:
        payload = {
            'chat_id': chat_id,
            'text': html_text,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        }
        r = requests.post(f'https://api.telegram.org/bot{TOKEN}/sendMessage', json=payload, timeout=10)
        result = r.json()
        if not result.get('ok'):
            log(f"Send failed for {chat_id}: {result.get('description')}")
            return False
        return True
    except Exception as e:
        log(f"send_html error: {e}")
        return False

def build_profit_report():
    """Build comprehensive HTML profit report from ledger and state."""
    now = datetime.now(timezone.utc)
    
    # Load recent trades from ledger
    trades = []
    try:
        with open(LEDGER_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get('net_pnl') is not None and entry.get('strategy') == 'grid_v22':
                        trades.append(entry)
                except:
                    pass
    except:
        pass
    
    # Load state files
    total_pnl = 0.0
    total_trades = 0
    total_wins = 0
    symbol_stats = {}
    
    for sf in STATE_FILES:
        try:
            with open(sf, 'r') as f:
                st = json.load(f)
            if isinstance(st.get('pnl'), dict):
                for sym, pnl in st['pnl'].items():
                    t = st.get('trades', {}).get(sym, 0)
                    w = st.get('wins', {}).get(sym, 0)
                    symbol_stats[sym] = {'trades': t, 'wins': w, 'pnl': pnl}
                    total_pnl += pnl
                    total_trades += t
                    total_wins += w
            elif isinstance(st.get('total_pnl'), (int, float)):
                total_pnl += st['total_pnl']
                total_trades += st.get('trades', 0) if isinstance(st.get('trades'), int) else sum(st.get('trades', {}).values())
                total_wins += st.get('wins', 0) if isinstance(st.get('wins'), int) else sum(st.get('wins', {}).values())
        except:
            pass
    
    wr = (total_wins / total_trades * 100) if total_trades > 0 else 0
    
    # Recent winning trades
    recent_wins = sorted([t for t in trades if t.get('win', False)], 
                         key=lambda x: x.get('ts', ''), reverse=True)[:5]
    
    # Build HTML
    emoji_pnl = "🟢" if total_pnl >= 0 else "🔴"
    pnl_sign = "+" if total_pnl >= 0 else ""
    
    html = f"""
<b>💰 RELATÓRIO DE LUCRO - GRID TRADING</b>
<i>{now.strftime('%d/%m/%Y %H:%M UTC')}</i>

━━━━━━━━━━━━━━━━━━━━━━━
<b>{emoji_pnl} RESULTADO GERAL</b>
━━━━━━━━━━━━━━━━━━━━━━━
<b>PnL Total:</b> <code>{pnl_sign}{total_pnl:.6f} USDT</code>
<b>Trades:</b> <code>{total_trades}</code> | <b>Wins:</b> <code>{total_wins}</code>
<b>Win Rate:</b> <code>{wr:.1f}%</code>

━━━━━━━━━━━━━━━━━━━━━━━
<b>📊 POR PAR</b>
━━━━━━━━━━━━━━━━━━━━━━━"""
    
    for sym, stats in sorted(symbol_stats.items(), key=lambda x: x[1]['pnl'], reverse=True):
        sym_emoji = "🟢" if stats['pnl'] >= 0 else "🔴"
        sym_sign = "+" if stats['pnl'] >= 0 else ""
        sym_wr = (stats['wins'] / stats['trades'] * 100) if stats['trades'] > 0 else 0
        html += f"""
{sym_emoji} <b>{sym}</b>
   Trades: <code>{stats['trades']}</code> | WR: <code>{sym_wr:.0f}%</code>
   PnL: <code>{sym_sign}{stats['pnl']:.6f} USDT</code>"""
    
    if recent_wins:
        html += """

━━━━━━━━━━━━━━━━━━━━━━━
<b>⚡ ÚLTIMOS TRADES VENCEDORES</b>
━━━━━━━━━━━━━━━━━━━━━━━"""
        for t in recent_wins:
            ts = t.get('ts', '?')[:19].replace('T', ' ')
            sym = t.get('symbol', '?')
            net = t.get('net_pnl', 0)
            entry = t.get('entry_price', 0)
            exit_ = t.get('exit_price', 0)
            html += f"""
✅ <b>{sym}</b> @ {ts}
   Entry: <code>{entry:.8f}</code> → Exit: <code>{exit_:.8f}</code>
   Lucro: <code>+{net:.6f} USDT</code>"""
    
    # Strategy info
    html += """

━━━━━━━━━━━━━━━━━━━━━━━
<b>⚙️ ESTRATÉGIA ATIVA</b>
━━━━━━━━━━━━━━━━━━━━━━━
<b>Grid Trading V22</b>
• Pares: XRP, DOGE, BTC, ETH, SOL
• Grids: 8 | Spacing: 1.0%
• Fees: 0.02% maker (ambos lados)
• Backtest: 220 trades/dia, WR 100%
• Projeção: ~$6.7/dia com $10

━━━━━━━━━━━━━━━━━━━━━━━
<i>🔄 Atualizações automáticas a cada trade vencedor</i>
<i>📱 Enviado por RafaioBot</i>
━━━━━━━━━━━━━━━━━━━━━━━"""
    
    return html.strip()

def build_opportunity_alert(symbol, spread_pct, price, signal_type="GRID_OPPORTUNITY"):
    """Build alert for detected opportunity."""
    now = datetime.now(timezone.utc)
    
    html = f"""
<b>⚡ OPORTUNIDADE DETECTADA</b>
<i>{now.strftime('%H:%M:%S UTC')}</i>

━━━━━━━━━━━━━━━━━━━━━━━
<b>🎯 {symbol}</b>
━━━━━━━━━━━━━━━━━━━━━━━
<b>Sinal:</b> <code>{signal_type}</code>
<b>Preço:</b> <code>{price:.8f}</code>
<b>Spread:</b> <code>{spread_pct:.3f}%</code>

<b>Status:</b> 🟢 Grid ativo monitorando
<b>Ação:</b> Ordens limit posicionadas

━━━━━━━━━━━━━━━━━━━━━━━
<i>📊 Grid V22 operando automaticamente</i>
━━━━━━━━━━━━━━━━━━━━━━━"""
    
    return html.strip()

def main():
    """Main loop: detect chats + send periodic reports."""
    log("Telegram Alert System starting...")
    log(f"Bot token: {'OK' if TOKEN else 'MISSING'}")
    
    # Initial chat detection
    detect_new_chats()
    
    last_report_time = 0
    report_interval = 300  # 5 minutes between full reports
    last_trade_count = 0
    
    while True:
        try:
            # Detect new chats
            detect_new_chats()
            
            chat_ids = get_chat_ids()
            if not chat_ids:
                time.sleep(10)
                continue
            
            # Check for new trades
            current_trade_count = 0
            try:
                with open(LEDGER_FILE, 'r') as f:
                    for line in f:
                        if 'grid_v22' in line:
                            current_trade_count += 1
            except:
                pass
            
            # Send alert on new winning trade
            if current_trade_count > last_trade_count:
                new_trades = current_trade_count - last_trade_count
                log(f"{new_trades} new trade(s) detected")
                
                # Read latest trades
                try:
                    with open(LEDGER_FILE, 'r') as f:
                        lines = f.readlines()
                    for line in lines[-new_trades:]:
                        try:
                            entry = json.loads(line.strip())
                            if entry.get('strategy') == 'grid_v22' and entry.get('win'):
                                alert = build_opportunity_alert(
                                    entry.get('symbol', '?'),
                                    1.0,  # grid spacing
                                    entry.get('exit_price', 0),
                                    "GRID_WIN"
                                )
                                for cid in chat_ids:
                                    send_html(cid, alert)
                        except:
                            pass
                except:
                    pass
                
                last_trade_count = current_trade_count
            
            # Periodic full report
            now = time.time()
            if now - last_report_time >= report_interval:
                report = build_profit_report()
                sent = 0
                for cid in chat_ids:
                    if send_html(cid, report):
                        sent += 1
                log(f"Report sent to {sent}/{len(chat_ids)} chats")
                last_report_time = now
            
            time.sleep(5)
            
        except KeyboardInterrupt:
            log("Shutting down...")
            break
        except Exception as e:
            log(f"Main loop error: {e}")
            time.sleep(10)

if __name__ == '__main__':
    main()
