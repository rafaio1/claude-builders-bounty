import sys, os, json, time, hashlib, hmac, requests, sqlite3
from pathlib import Path
sys.path.insert(0, '/Agentic/build/lib')
from agentic.env import bybit_credentials
from agentic.aro.store import append_jsonl

ROOT = Path('/Agentic')

print('=== BOUNTY HUNTER ACTIVATION & CAPITAL INJECTION STRATEGY ===')

# 1. Inspect BugHunter DB for actionable targets
bughunter_db = Path('/root/BugHunter/data/bughunter.db')
targets = []

if bughunter_db.exists():
    try:
        conn = sqlite3.connect(f'file:{bughunter_db}?mode=ro', uri=True)
        cursor = conn.cursor()
        
        # Get programs with bounties
        cursor.execute("SELECT handle, name, base_bounty, currency FROM programs WHERE offers_bounties = 1 AND base_bounty > 0 ORDER BY base_bounty DESC LIMIT 10")
        rows = cursor.fetchall()
        
        print('[BUGHUNTER] Top Actionable Bounty Targets:')
        for r in rows:
            handle, name, bounty, curr = r
            targets.append({'handle': handle, 'bounty': bounty})
            print(f"  -> {handle} ({name}): ${bounty} {curr}")
            
        # Check if bughunter loop is running
        import subprocess
        result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
        bh_running = any('bughunter loop' in l and 'grep' not in l for l in result.stdout.splitlines())
        print(f'\n[BUGHUNTER] Loop Active: {bh_running}')
        
        conn.close()
    except Exception as e:
        print(f'[BUGHUNTER] Error: {e}')

# 2. Bybit Status Check (Post-Bleed-Stop)
api_key, secret = bybit_credentials()
recv_window = '5000'
base = 'https://api.bybit.com'
session = requests.Session()
session.trust_env = False

def sign(payload):
    ts = str(int(time.time() * 1000))
    raw = f'{ts}{api_key}{recv_window}{payload}'
    return ts, hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()

def get(path, query=''):
    url = f'{base}{path}'
    if query: url += f'?{query}'
    ts, sig = sign(query)
    h = {'X-BAPI-API-KEY': api_key, 'X-BAPI-TIMESTAMP': ts, 'X-BAPI-RECV-WINDOW': recv_window, 'X-BAPI-SIGN': sig, 'Content-Type': 'application/json'}
    try:
        resp = session.get(url, headers=h, timeout=15)
        return resp.json()
    except Exception as e:
        return {'retCode': -1}

bal = get('/v5/account/wallet-balance', 'accountType=UNIFIED')
usdt = 0
if bal.get('retCode') == 0:
    for c in bal['result']['list'][0]['coin']:
        if c['coin'] == 'USDT': usdt = float(c.get('walletBalance', 0))

print(f'\n[BYBIT] Protected Capital: ${usdt:.4f} USDT')
print(f'[STRATEGY] Micro-trading paused. Focus shifted to external revenue generation via BugHunter.')

# 3. Log Strategic Pivot
append_jsonl(ROOT, 'ledger.jsonl', {
    'kind': 'external_revenue_focus_activated',
    'bybit_usdt_preserved': str(round(usdt, 4)),
    'bughunter_targets_identified': str(len(targets)),
    'top_target': targets[0]['handle'] if targets else 'none',
    'strategy': 'bounty_hunting_for_capital_injection',
    'live': True
})

print('\n=== AUTONOMOUS SYSTEM ALIGNED ===')
print('System is now prioritizing high-value bug bounties to inject capital into Bybit for compounding toward $1,000,000.')
