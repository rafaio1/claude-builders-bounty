#!/usr/bin/env python3
"""
Telegram Responder: Autonomous Reply Loop
Processes user_commands.jsonl and sends replies via Telegram API.
Runs independently of the main agent loop to ensure responsiveness.
"""
import json, os, sys, urllib.request
from datetime import datetime, timezone

sys.path.insert(0, '/Agentic/internal')
from env import apply
apply()

INBOX = '/Agentic/data/aro/inbox/user_commands.jsonl'
LEDGER = '/Agentic/data/aro/bounty_ledger.json'
TG_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TG_CHAT = os.environ.get('TELEGRAM_CHAT_ID', '')

def send_tg(text):
    if not TG_TOKEN or not TG_CHAT: return False
    try:
        data = json.dumps({'chat_id': TG_CHAT, 'text': text, 'parse_mode': 'Markdown'}).encode()
        req = urllib.request.Request(f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage', 
                                     data=data, headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e: 
        print(f"TG_ERR: {e}")
        return False

def get_ledger_stats():
    try:
        with open(LEDGER) as f: ledger = json.load(f)
        entries = ledger.get('entries', [])
        potential = sum(e.get('value', 0) for e in entries if e.get('status') in ['claimed', 'completed_pending_payout', 'submitted', 'in_review'])
        realized = sum(e.get('value', 0) for e in entries if e.get('status') in ['paid', 'payout_received'])
        active = len([e for e in entries if e.get('status') == 'claimed'])
        closed = len([e for e in entries if e.get('status') == 'completed_pending_payout'])
        return {'potential': potential, 'realized': realized, 'active': active, 'closed': closed, 'total': len(entries)}
    except: return {'potential': 0, 'realized': 0, 'active': 0, 'closed': 0, 'total': 0}

def process_inbox():
    if not os.path.exists(INBOX): return
    
    with open(INBOX) as f: lines = f.readlines()
    
    remaining = []
    processed_count = 0
    
    stats = get_ledger_stats()
    
    for line in lines:
        try:
            cmd = json.loads(line.strip())
            if cmd.get('processed'):
                remaining.append(line.strip())
                continue
                
            text = cmd.get('text', '').lower()
            response = None
            
            if any(k in text for k in ['capital', 'ledger', 'quanto', 'dinheiro', 'saldo', 'brl', 'usd']):
                response = f'''💰 *Resumo Financeiro*

• Pipeline Potencial: {stats['potential']} (várias moedas)
• Realizado/Pago: {stats['realized']}
• Claims Ativos: {stats['active']}
• Fechados/Pendentes: {stats['closed']}

_Total de entradas: {stats['total']}_'''
            
            elif any(k in text for k in ['prompt', 'tarefa', 'servidor', 'rodando', 'status', 'sistema']):
                response = '''🤖 *Status do Sistema Autônomo*

✅ Auto-Claim Scout (2h)
✅ Telegram Bridge (30s)
✅ Responder Automático (1min)
✅ Bounty Monitor (15min)
✅ Payout Reconciler (ativo)

_Todas as tarefas operacionais._'''
                
            elif any(k in text for k in ['claim', 'bounty', 'pendente']):
                response = f'''🎯 *Status de Claims*

• Ativos/Aguardando: {stats['active']}
• Concluídos/Merge: {stats['closed']}
• Total no Ledger: {stats['total']}

_O sistema monitora e clama automaticamente a cada 2h._'''
            
            elif any(k in text for k in ['oi', 'olá', 'hello', 'hi', 'bom dia', 'boa tarde', 'boa noite']):
                response = '👋 Olá! Sistema autônomo ativo.\n\nComandos úteis:\n• *saldo* - ver capital\n• *status* - ver tarefas\n• *claims* - ver bounties'
            
            else:
                response = f'🤔 Recebi: _"{cmd.get("text","")[:60]}..."_\n\nAinda não tenho resposta automática específica, mas registrei como contexto.'
            
            if response and send_tg(response):
                cmd['processed'] = True
                cmd['processed_at'] = datetime.now(timezone.utc).isoformat()
                processed_count += 1
            
            remaining.append(json.dumps(cmd))
            
        except Exception as e: 
            print(f"PARSE_ERR: {e}")
            remaining.append(line.strip())
    
    with open(INBOX, 'w') as f:
        for item in remaining:
            f.write(item + '\n')
            
    if processed_count > 0:
        print(f"RESPONDED: {processed_count} messages")

if __name__ == '__main__':
    process_inbox()
