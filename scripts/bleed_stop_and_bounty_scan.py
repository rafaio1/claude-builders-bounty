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

print('=== STRATEGIC PIVOT: STOP FEE BLEED & SCAN BOUNTIES ===')

# 1. BYBIT: Cancel all open orders to stop fee drag on micro-capital
orders = get('/v5/order/realtime', 'category=spot&limit=50')
cancelled = 0
if orders.get('retCode') == 0:
    for o in orders['result']['list']:
        if o['orderStatus'] in ['New', 'PartiallyFilled']:
            res = post('/v5/order/cancel', {'category': 'spot', 'symbol': o['symbol'], 'orderId': o['orderId']})
            if res.get('retCode') == 0:
                print(f"[BYBIT] Cancelled stale order: {o['symbol']} {o['side']}")
                cancelled += 1
print(f"[BYBIT] Cancelled {cancelled} orders. Holding USDT to preserve capital.")

# 2. BUGHUNTER: Inspect bounty_rows schema and find top targets
bughunter_db = Path('/root/BugHunter/data/bughunter.db')
bh_top_bounties = []

if bughunter_db.exists():
    try:
        conn = sqlite3.connect(f'file:{bughunter_db}?mode=ro', uri=True)
        cursor = conn.cursor()
        
        # Get bounty_rows columns
        cursor.execute("PRAGMA table_info(bounty_rows);")
        bounty_cols = [row[1] for row in cursor.fetchall()]
        print(f'\n[BUGHUNTER] bounty_rows columns: {bounty_cols}')
        
        # Find the column that holds the max bounty amount
        max_col = None
        for c in bounty_cols:
            if 'high' in c.lower() or 'max' in c.lower() or 'upper' in c.lower():
                max_col = c
                break
        if not max_col and 'amount' in bounty_cols: max_col = 'amount'
        if not max_col and 'value' in bounty_cols: max_col = 'value'
        
        if max_col:
            print(f"[BUGHUNTER] Using '{max_col}' as max bounty column.")
            cursor.execute(f"""
                SELECT p.handle, p.name, MAX(b.{max_col}) as top_bounty, b.currency 
                FROM programs p 
                LEFT JOIN bounty_rows b ON p.handle = b.program_handle 
                WHERE b.{max_col} > 0 
                GROUP BY p.handle 
                ORDER BY top_bounty DESC 
                LIMIT 5
            """)
            rows = cursor.fetchall()
            print(f'[BUGHUNTER] Top 5 High-Value Bounty Targets:')
            for r in rows:
                handle, name, max_b, curr = r
                bh_top_bounties.append({'handle': handle, 'name': name, 'max_bounty': max_b, 'currency': curr})
                print(f'  -> {handle} ({name}): up to {max_b} {curr}')
        else:
            print("[BUGHUNTER] Could not identify max bounty column. Falling back to base_bounty in programs.")
            cursor.execute("""
                SELECT handle, name, base_bounty, currency 
                FROM programs 
                WHERE base_bounty > 0 
                ORDER BY base_bounty DESC 
                LIMIT 5
            """)
            rows = cursor.fetchall()
            for r in rows:
                handle, name, max_b, curr = r
                bh_top_bounties.append({'handle': handle, 'name': name, 'max_bounty': max_b, 'currency': curr})
                print(f'  -> {handle} ({name}): base {max_b} {curr}')
                
        conn.close()
    except Exception as e:
        print(f'[BUGHUNTER] DB Error: {e}')

# 3. Final Status
bal = get('/v5/account/wallet-balance', 'accountType=UNIFIED')
usdt = 0
if bal.get('retCode') == 0:
    for c in bal['result']['list'][0]['coin']:
        if c['coin'] == 'USDT': usdt = float(c.get('walletBalance', 0))

print(f'\n=== $1M ROADMAP STATUS ===')
print(f'Protected Bybit Capital: ${usdt:.4f} USDT')
print(f'Strategy: Paused micro-trading to stop fee bleed. Awaiting BugHunter bounty payouts or larger capital injection for swing trading.')

append_jsonl(ROOT, 'ledger.jsonl', {
    'kind': 'strategic_pivot_fee_protection',
    'usdt_preserved': str(round(usdt, 4)),
    'orders_cancelled': str(cancelled),
    'bughunter_top_target': bh_top_bounties[0]['handle'] if bh_top_bounties else 'none',
    'top_bounty_value': str(bh_top_bounties[0]['max_bounty']) if bh_top_bounties else '0',
    'strategy': 'fee_protection_and_external_revenue_focus',
    'live': True
})
