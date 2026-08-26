import subprocess, sqlite3, json, sys, os, time, hashlib, hmac, requests
from pathlib import Path
sys.path.insert(0, '/Agentic/build/lib')
from agentic.env import bybit_credentials
from agentic.aro.store import append_jsonl

ROOT = Path('/Agentic')
BH_VENV = '/root/BugHunter/.venv/bin/python'

print('=== ADVANCING BUGHUNTER PIPELINE & CHECKING BYBIT ===')

# 1. Advance BugHunter Pipeline
print('[BUGHUNTER] Running settle...')
res_settle = subprocess.run([BH_VENV, '-m', 'bughunter', 'settle', '--limit', '20'], capture_output=True, text=True, timeout=120)
print(f"Settle output: {res_settle.stdout[:500]}")

print('[BUGHUNTER] Running review --submit...')
res_review = subprocess.run([BH_VENV, '-m', 'bughunter', 'review', '--submit', '--limit', '10'], capture_output=True, text=True, timeout=120)
print(f"Review output: {res_review.stdout[:500]}")

# 2. Check BugHunter DB for submission status
bughunter_db = Path('/root/BugHunter/data/bughunter.sqlite3')
if not bughunter_db.exists():
    bughunter_db = Path('/root/BugHunter/data/bughunter.db')

submitted_count = 0
potential_payout = 0.0
if bughunter_db.exists():
    conn = sqlite3.connect(f'file:{bughunter_db}?mode=ro', uri=True)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM submissions WHERE status IN ('submitted', 'advanced', 'triaged', 'accepted')")
    submitted_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT p.base_bounty FROM programs p JOIN submissions s ON p.handle = s.handle WHERE s.status IN ('submitted', 'advanced', 'triaged', 'accepted')")
    for row in cursor.fetchall():
        potential_payout += float(row[0] or 0)
    conn.close()

print(f'\n[BUGHUNTER] Active Submissions: {submitted_count} | Est. Pipeline: ${potential_payout:,.2f}')

# 3. Check Bybit Balance
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

print(f'[BYBIT] Current USDT: ${usdt:.4f}')
print(f'[TARGET] $1,000,000 USD | Progress: {(usdt / 1000000) * 100:.8f}%')

append_jsonl(ROOT, 'ledger.jsonl', {
    'kind': 'pipeline_advancement',
    'submissions_active': str(submitted_count),
    'est_pipeline_usd': str(round(potential_payout, 2)),
    'bybit_usdt': str(round(usdt, 4)),
    'strategy': 'advancing_bughunter_submissions_for_capital_injection',
    'live': True
})
