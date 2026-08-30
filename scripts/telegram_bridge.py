#!/usr/bin/env python3
"""
Telegram Bridge: Bidirectional Communication
- Polls for user messages
- Forwards them as context/instructions to the agent loop
- Sends autonomous status updates and decision logs
"""
import json, os, sys, time, urllib.request, subprocess
from datetime import datetime, timezone

sys.path.insert(0, '/Agentic/internal')
from env import apply
apply()

TG_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TG_CHAT = os.environ.get('TELEGRAM_CHAT_ID', '')
STATE_FILE = '/tmp/tg_bridge_offset.json'
INBOX_FILE = '/Agentic/data/aro/inbox/user_commands.jsonl'

def log(msg): print(f"[{datetime.now(timezone.utc).isoformat()}] {msg}")

def tg_request(method, data=None):
    url = f'https://api.telegram.org/bot{TG_TOKEN}/{method}'
    if data is None:
        return urllib.request.urlopen(url, timeout=15)
    req = urllib.request.Request(url, json.dumps(data).encode(), {'Content-Type': 'application/json'})
    return urllib.request.urlopen(req, timeout=15)

def get_offset():
    try:
        with open(STATE_FILE) as f: return json.load(f).get('offset', 0)
    except: return 0

def save_offset(offset):
    with open(STATE_FILE, 'w') as f: json.dump({'offset': offset}, f)

def forward_to_agent(text, sender):
    """Append user message to inbox for agent consumption"""
    entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'sender': sender,
        'text': text,
        'processed': False
    }
    with open(INBOX_FILE, 'a') as f:
        f.write(json.dumps(entry) + '\n')
    log(f"FORWARDED from {sender}: {text[:100]}")

def poll_updates():
    if not TG_TOKEN or not TG_CHAT:
        log("MISSING_CREDS"); return
    
    offset = get_offset()
    try:
        resp = tg_request('getUpdates', {'offset': offset, 'timeout': 10, 'allowed_updates': ['message']})
        data = json.loads(resp.read())
        
        for update in data.get('result', []):
            msg = update.get('message', {})
            chat_id = str(msg.get('chat', {}).get('id', ''))
            text = msg.get('text', '').strip()
            sender = msg.get('from', {}).get('username', 'unknown')
            update_id = update['update_id']
            
            # Only process messages from authorized chat
            if chat_id == str(TG_CHAT) and text:
                forward_to_agent(text, sender)
                
                # Acknowledge receipt immediately
                ack = f"✅ Recebido: _{text[:50]}..._\n\n🤖 Processando como instrução direta."
                tg_request('sendMessage', {'chat_id': TG_CHAT, 'text': ack, 'parse_mode': 'Markdown'})
            
            save_offset(update_id + 1)
            
    except Exception as e:
        log(f"POLL_ERROR: {e}")

if __name__ == '__main__':
    log("Starting Telegram Bridge Poll Cycle")
    poll_updates()
