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

print('=== EXTERNAL REVENUE DISCOVERY & TRADING OPTIMIZATION ===')

# 1. Discover BugHunter Database Schema
bughunter_db = Path('/root/BugHunter/data/bughunter.db')
bh_programs = 0
bh_reports = 0
bh_schema_info = []

if bughunter_db.exists():
    try:
        conn = sqlite3.connect(f'file:{bughunter_db}?mode=ro', uri=True)
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        print(f'[BUGHUNTER] Found tables: {tables}')
        
        # Inspect 'programs' table columns
        if 'programs' in tables:
            cursor.execute("PRAGMA table_info(programs);")
            prog_cols = [row[1] for row in cursor.fetchall()]
            print(f'[BUGHUNTER] Programs columns: {prog_cols}')
            bh_schema_info.append(f"programs: {','.join(prog_cols[:5])}...")
            
            # Count programs
            cursor.execute("SELECT COUNT(*) FROM programs")
            bh_programs = cursor.fetchone()[0]
            
            # Try to find high value programs based on actual columns
            # Look for anything related to bounty, reward, payout
            bounty_cols = [c for c in prog_cols if 'bounty' in c.lower() or 'reward' in c.lower() or 'payout' in c.lower()]
            if bounty_cols:
                print(f'[BUGHUNTER] Bounty-related columns: {bounty_cols}')
        
        # Inspect 'reports' table columns
        if 'reports' in tables:
            cursor.execute("PRAGMA table_info(reports);")
            rep_cols = [row[1] for row in cursor.fetchall()]
            print(f'[BUGHUNTER] Reports columns: {rep_cols}')
            bh_schema_info.append(f"reports: {','.join(rep_cols[:5])}...")
            
            # Count reports
            cursor.execute("SELECT COUNT(*) FROM reports")
            bh_reports = cursor.fetchone()[0]
            print(f'[BUGHUNTER] Total reports in DB: {bh_reports}')
            
            # Check for any reports with status indicating potential payout
            status_col = [c for c in rep_cols if 'status' in c.lower()]
            if status_col:
                cursor.execute(f"SELECT {status_col[0]}, COUNT(*) FROM reports GROUP BY {status_col[0]}")
                statuses = cursor.fetchall()
                print(f'[BUGHUNTER] Report statuses: {statuses}')
        
        conn.close()
    except Exception as e:
        print(f'[BUGHUNTER] Error reading DB: {e}')

# 2. Trading Engine: Optimize Open Orders
bal = get('/v5/account/wallet-balance', 'accountType=UNIFIED')
usdt, tria, xrp = 0, 0, 0
if bal.get('retCode') == 0:
    for c in bal['result']['list'][0]['coin']:
        if c['coin'] == 'USDT': usdt = float(c.get('walletBalance', 0))
        if c['coin'] == 'TRIA': tria = float(c.get('walletBalance', 0))
        if c['coin'] == 'XRP': xrp = float(c.get('walletBalance', 0))

total_value = usdt + (tria * 0.008) + (xrp * 1.0)
print(f'\n[TRADING] USDT: {usdt:.4f} | TRIA: {tria:.2f} | XRP: {xrp:.2f} | Total: ${total_value:.2f}')

# Check all open orders and ensure sell side is covered
orders = get('/v5/order/realtime', 'category=spot&limit=50')
open_buys, open_sells = [], []
if orders.get('retCode') == 0:
    for o in orders['result']['list']:
        if o['orderStatus'] in ['New', 'PartiallyFilled']:
            if o['side'] == 'Buy': open_buys.append(o)
            else: open_sells.append(o)

print(f'[TRADING] Open Buys: {len(open_buys)} | Open Sells: {len(open_sells)}')

# If we have assets but no sells, place them
assets_to_sell = []
if tria >= 10: assets_to_sell.append(('TRIAUSDT', tria))
if xrp >= 1: assets_to_sell.append(('XRPUSDT', xrp))

for sym, amt in assets_to_sell:
    has_sell = any(o['symbol'] == sym for o in open_sells)
    if not has_sell:
        tickers = get('/v5/market/tickers', f'category=spot&symbol={sym}')
        if tickers.get('retCode') == 0 and tickers['result']['list']:
            price = float(tickers['result']['list'][0]['lastPrice'])
            inst_info = get('/v5/market/instruments-info', f'category=spot&symbol={sym}')
            if inst_info.get('retCode') == 0 and inst_info['result']['list']:
                i = inst_info['result']['list'][0]
                qs = float(i.get('lotSizeFilter', {}).get('qtyStep', 0.1))
                ts_ = float(i.get('priceFilter', {}).get('tickSize', 0.0001))
                mq = float(i.get('lotSizeFilter', {}).get('minOrderQty', 0.1))
                ma = float(i.get('lotSizeFilter', {}).get('minOrderAmt', 1))
                
                try:
                    bp = int(i.get('lotSizeFilter', {}).get('basePrecision', 2))
                    qp = int(i.get('priceFilter', {}).get('quotePrecision', 4))
                except:
                    bp, qp = 2, 4
                
                sell_p = math.ceil((price * 1.015) / ts_) * ts_
                qty = math.floor(amt * 0.98 / qs) * qs
                
                if qty >= mq and (qty * sell_p) >= ma:
                    qty_s = f"{qty:.{bp}f}"
                    price_s = f"{sell_p:.{qp}f}"
                    res = post('/v5/order/create', {
                        'category': 'spot', 'symbol': sym, 'side': 'Sell',
                        'orderType': 'Limit', 'qty': qty_s,
                        'price': price_s, 'timeInForce': 'GTC'
                    })
                    if res.get('retCode') == 0:
                        print(f'[TRADING] AUTO-SELL PLACED: {sym} {qty_s} @ {price_s}')
                        append_jsonl(ROOT, 'ledger.jsonl', {
                            'kind': 'auto_sell_placed', 'pair': sym,
                            'qty': qty_s, 'price': price_s, 'live': True
                        })

# 3. Log orchestration status
progress_to_1m = (total_value / 1000000) * 100
print(f'\n=== $1M ROADMAP STATUS ===')
print(f'Current Liquid + Crypto: ${total_value:.4f}')
print(f'Progress to $1,000,000: {progress_to_1m:.8f}%')
print(f'BugHunter DB: {bh_programs} programs, {bh_reports} reports')

append_jsonl(ROOT, 'ledger.jsonl', {
    'kind': 'external_revenue_discovery',
    'usdt': str(round(usdt, 4)),
    'tria': str(round(tria, 2)),
    'xrp': str(round(xrp, 2)),
    'total_value_usd': str(round(total_value, 4)),
    'bughunter_programs': str(bh_programs),
    'bughunter_reports': str(bh_reports),
    'schema_discovered': str(bh_schema_info),
    'progress_to_1m_pct': str(round(progress_to_1m, 8)),
    'live': True
})
