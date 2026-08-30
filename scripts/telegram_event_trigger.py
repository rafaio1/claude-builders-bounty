#!/usr/bin/env python3
"""
Telegram Event Trigger: Push notifications on ledger state changes.
Replaces polling-based status updates with real-time event-driven alerts.
"""
import json, os, sys, urllib.request, hashlib
from datetime import datetime, timezone

sys.path.insert(0, '/Agentic/internal')
from env import apply
apply()

LEDGER = '/Agentic/data/aro/bounty_ledger.json'
STATE_FILE = '/tmp/tg_event_state.json'
TG_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TG_CHAT = os.environ.get('TELEGRAM_CHAT_ID', '')

def send_tg(text):
    if not TG_TOKEN or not TG_CHAT: return
    try:
        data = json.dumps({'chat_id': TG_CHAT, 'text': text, 'parse_mode': 'Markdown'}).encode()
        req = urllib.request.Request(f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage', 
                                     data=data, headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e: print(f"TG_ERR: {e}")

def get_state_hash(entries):
    """Create a hash of critical fields to detect changes"""
    relevant = []
    for e in entries:
        relevant.append({
            'repo': e.get('repo'),
            'issue': e.get('issue') or e.get('number'),
            'status': e.get('status'),
            'value': e.get('value'),
            'updated': e.get('updated')
        })
    return hashlib.md5(json.dumps(relevant, sort_keys=True).encode()).hexdigest()

def load_previous_state():
    try:
        with open(STATE_FILE) as f: return json.load(f)
    except: return {'hash': '', 'entries': {}}

def save_state(state):
    with open(STATE_FILE, 'w') as f: json.dump(state, f)

def main():
    if not os.path.exists(LEDGER): return
    
    with open(LEDGER) as f: ledger = json.load(f)
    entries = ledger.get('entries', [])
    
    current_hash = get_state_hash(entries)
    prev = load_previous_state()
    
    if current_hash == prev.get('hash'):
        return  # No changes
    
    # Detect specific events
    prev_entries = prev.get('entries', {})
    curr_entries = {f"{e.get('repo')}#{e.get('issue') or e.get('number')}": e for e in entries}
    
    notifications = []
    
    for key, curr in curr_entries.items():
        prev_status = prev_entries.get(key, {}).get('status')
        curr_status = curr.get('status')
        
        if prev_status != curr_status:
            emoji = '🔄'
            if curr_status == 'claimed': emoji = '🎯'
            elif curr_status == 'completed_pending_payout': emoji = '✅'
            elif curr_status == 'paid': emoji = '💰'
            elif curr_status == 'rejected_auto': emoji = '❌'
            
            title = curr.get('title', key)
            val = curr.get('value', '?')
            cur = curr.get('currency', '')
            
            notifications.append(f"{emoji} *{key}*\n_{title[:60]}_\nStatus: `{prev_status}` → `{curr_status}`\nValor: {val} {cur}")
    
    # New entries
    for key in curr_entries:
        if key not in prev_entries:
            e = curr_entries[key]
            notifications.append(f"🆕 *Novo Claim Registrado*\n`{key}`\n_{e.get('title','?')[:60]}_")
    
    if notifications:
        msg = "📡 *Eventos Detectados no Ledger*\n\n" + "\n\n".join(notifications[:5])  # Limit to avoid spam
        if len(notifications) > 5:
            msg += f"\n\n_...e mais {len(notifications)-5} eventos._"
        send_tg(msg)
    
    # Save new state
    new_state = {
        'hash': current_hash,
        'entries': {k: {'status': v.get('status'), 'updated': v.get('updated')} for k,v in curr_entries.items()},
        'last_check': datetime.now(timezone.utc).isoformat()
    }
    save_state(new_state)
    print(f"EVENTS_PROCESSED: {len(notifications)} notifications sent")

if __name__ == '__main__':
    main()
