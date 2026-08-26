import sys, os, json, time, hashlib, hmac, requests, math, sqlite3
from pathlib import Path
sys.path.insert(0, '/Agentic/build/lib')
from agentic.env import bybit_credentials
from agentic.aro.store import append_jsonl

ROOT = Path('/Agentic')
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

def post(path, body):
    url = f'{base}{path}'
    payload = json.dumps(body, separators=(',', ':'), ensure_ascii=False)
    ts, sig = sign(payload)
    h = {'X-BAPI-API-KEY': api_key, 'X-BAPI-TIMESTAMP': ts, 'X-BAPI-RECV-WINDOW': recv_window, 'X-BAPI-SIGN': sig, 'Content-Type': 'application/json'}
    try:
        resp = session.post(url, headers=h, data=payload, timeout=15)
        return resp.json()
    except Exception as e:
        return {'retCode': -1}

print('=== UNIFIED AUTONOMOUS CAPITAL ENGINE: BYBIT + BUGHUNTER ===')

# 1. BYBIT: Check recent fills to confirm TRIA profit
history = get('/v5/execution/list', 'category=spot&limit=20')
recent_profit = 0.0
fills_24h = 0
if history.get('retCode') == 0:
    now_ms = int(time.time() * 1000)
    for t in history['result']['list']:
        age_hrs = (now_ms - int(t.get('execTime', 0))) / 3600000
        if age_hrs < 24:
            fills_24h += 1
            pnl = float(t.get('closedPnl', 0))
            fee = float(t.get('execFee', 0))
            net = pnl - fee
            recent_profit += net
            if abs(net) > 0.001:
                print(f'[BYBIT FILL] {t["symbol"]} {t["side"]} {t["execQty"]} @ {t["execPrice"]} | Net PnL: {net:.4f} USDT')

bal = get('/v5/account/wallet-balance', 'accountType=UNIFIED')
usdt, tria, xrp = 0, 0, 0
if bal.get('retCode') == 0:
    for c in bal['result']['list'][0]['coin']:
        if c['coin'] == 'USDT': usdt = float(c.get('walletBalance', 0))
        if c['coin'] == 'TRIA': tria = float(c.get('walletBalance', 0))
        if c['coin'] == 'XRP': xrp = float(c.get('walletBalance', 0))

bybit_total = usdt + (tria * 0.008) + (xrp * 1.0)
print(f'\n[BYBIT PORTFOLIO] USDT: {usdt:.4f} | TRIA: {tria:.2f} | XRP: {xrp:.2f}')
print(f'[BYBIT STATUS] 24h Fills: {fills_24h} | Net PnL: {recent_profit:.4f} USDT | Total Value: ${bybit_total:.2f}')

# 2. BUGHUNTER: Query highest bounty targets
bughunter_db = Path('/root/BugHunter/data/bughunter.db')
bh_top_bounties = []
bh_submissions = 0
bh_payout_potential = 0.0

if bughunter_db.exists():
    try:
        conn = sqlite3.connect(f'file:{bughunter_db}?mode=ro', uri=True)
        cursor = conn.cursor()
        
        # Get top bounty programs
        cursor.execute("""
            SELECT p.handle, p.name, MAX(b.high) as max_bounty, b.currency 
            FROM programs p 
            LEFT JOIN bounty_rows b ON p.handle = b.program_handle 
            WHERE b.high > 0 
            GROUP BY p.handle 
            ORDER BY max_bounty DESC 
            LIMIT 10
        """)
        rows = cursor.fetchall()
        print(f'\n[BUGHUNTER] Top 10 High-Value Bounty Targets:')
        for r in rows:
            handle, name, max_b, curr = r
            bh_top_bounties.append({'handle': handle, 'name': name, 'max_bounty': max_b, 'currency': curr})
            print(f'  -> {handle} ({name}): up to {max_b} {curr}')
        
        # Check submissions for potential payouts
        cursor.execute("SELECT COUNT(*), SUM(CASE WHEN status IN ('accepted', 'triaged', 'resolved') THEN 1 ELSE 0 END) FROM submissions")
        res = cursor.fetchone()
        bh_submissions = res[0] if res[0] else 0
        accepted_subs = res[1] if res[1] else 0
        print(f'[BUGHUNTER] Total Submissions: {bh_submissions} | Accepted/Triaged: {accepted_subs}')
        
        conn.close()
    except Exception as e:
        print(f'[BUGHUNTER] DB Error: {e}')

# 3. UNIFIED ROADMAP TO $1,000,000
progress_to_1m = (bybit_total / 1000000) * 100
print(f'\n=== $1,000,000 AUTONOMOUS ROADMAP ===')
print(f'Current Liquid Capital (Bybit): ${bybit_total:.4f}')
print(f'Progress to $1M: {progress_to_1m:.8f}%')
print(f'Active Engines: Bybit Spot Trading + BugHunter Bounty Pipeline')
print(f'Next Autonomous Actions: Compound Bybit fills, monitor BugHunter submissions for payouts.')

append_jsonl(ROOT, 'ledger.jsonl', {
    'kind': 'unified_capital_engine_status',
    'bybit_usdt': str(round(usdt, 4)),
    'bybit_total_value': str(round(bybit_total, 4)),
    'bybit_net_pnl_24h': str(round(recent_profit, 4)),
    'bughunter_submissions': str(bh_submissions),
    'bughunter_top_target': bh_top_bounties[0]['handle'] if bh_top_bounties else 'none',
    'progress_to_1m_pct': str(round(progress_to_1m, 8)),
    'strategy': 'dual_engine_trading_and_bounties',
    'live': True
})
