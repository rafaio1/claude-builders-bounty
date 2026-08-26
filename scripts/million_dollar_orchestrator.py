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

print('=== $1,000,000 ORCHESTRATOR: TRADING + EXTERNAL REVENUE ===')

# 1. Trading Engine: Monitor TRIAUSDT and prepare auto-sell
bal = get('/v5/account/wallet-balance', 'accountType=UNIFIED')
usdt, tria = 0, 0
if bal.get('retCode') == 0:
    for c in bal['result']['list'][0]['coin']:
        if c['coin'] == 'USDT': usdt = float(c.get('walletBalance', 0))
        if c['coin'] == 'TRIA': tria = float(c.get('walletBalance', 0))

orders = get('/v5/order/realtime', 'category=spot&symbol=TRIAUSDT')
open_buys, open_sells = 0, 0
if orders.get('retCode') == 0:
    for o in orders['result']['list']:
        if o['orderStatus'] in ['New', 'PartiallyFilled']:
            if o['side'] == 'Buy': open_buys += 1
            else: open_sells += 1

print(f'[TRADING] USDT: {usdt:.4f} | TRIA: {tria:.4f} | Buys: {open_buys} | Sells: {open_sells}')

# If TRIA balance > 0 and no open sells, place a +2% sell order
if tria >= 10.0 and open_sells == 0:
    tickers = get('/v5/market/tickers', 'category=spot&symbol=TRIAUSDT')
    if tickers.get('retCode') == 0 and tickers['result']['list']:
        price = float(tickers['result']['list'][0]['lastPrice'])
        inst_info = get('/v5/market/instruments-info', 'category=spot&symbol=TRIAUSDT')
        if inst_info.get('retCode') == 0 and inst_info['result']['list']:
            i = inst_info['result']['list'][0]
            qs = float(i.get('lotSizeFilter', {}).get('qtyStep', 0.1))
            ts_ = float(i.get('priceFilter', {}).get('tickSize', 0.0001))
            mq = float(i.get('lotSizeFilter', {}).get('minOrderQty', 0.1))
            ma = float(i.get('lotSizeFilter', {}).get('minOrderAmt', 1))
            bp = int(i.get('lotSizeFilter', {}).get('basePrecision', 2))
            qp = int(i.get('priceFilter', {}).get('quotePrecision', 4))
            
            sell_p = math.ceil((price * 1.02) / ts_) * ts_
            qty = math.floor(tria * 0.98 / qs) * qs
            
            if qty >= mq and (qty * sell_p) >= ma:
                qty_s = f"{qty:.{bp}f}"
                price_s = f"{sell_p:.{qp}f}"
                res = post('/v5/order/create', {
                    'category': 'spot', 'symbol': 'TRIAUSDT', 'side': 'Sell',
                    'orderType': 'Limit', 'qty': qty_s,
                    'price': price_s, 'timeInForce': 'GTC'
                })
                if res.get('retCode') == 0:
                    print(f'[TRADING] AUTO-SELL PLACED: {qty_s} TRIA @ {price_s}')
                    append_jsonl(ROOT, 'ledger.jsonl', {
                        'kind': 'tria_auto_sell', 'qty': qty_s, 'price': price_s, 'live': True
                    })

# 2. External Revenue Engine: Check BugHunter Bounties
bughunter_db = Path('/Agentic/data/aro/bughunter_findings.db')
bounty_potential = 0
high_value_targets = 0
if bughunter_db.exists():
    try:
        conn = sqlite3.connect(f'file:{bughunter_db}?mode=ro', uri=True)
        cursor = conn.cursor()
        # Look for programs with high bounties or active reports
        cursor.execute("SELECT handle, name FROM programs WHERE bounty_max_usd > 1000 ORDER BY bounty_max_usd DESC LIMIT 5")
        rows = cursor.fetchall()
        for r in rows:
            high_value_targets += 1
            print(f'[EXTERNAL] High-Value Target: {r[0]} ({r[1]})')
        
        # Check for submitted reports awaiting payout
        cursor.execute("SELECT COUNT(*) FROM reports WHERE status IN ('submitted', 'triaged', 'accepted')")
        pending_payouts = cursor.fetchone()[0]
        print(f'[EXTERNAL] Pending Payouts: {pending_payouts} reports')
        conn.close()
    except Exception as e:
        print(f'[EXTERNAL] BugHunter DB read error: {e}')

# 3. Strategic Roadmap Logging
total_est_value = usdt + (tria * 0.008)
progress_to_1m = (total_est_value / 1000000) * 100

print(f'\n=== $1M ROADMAP STATUS ===')
print(f'Current Liquid + Crypto: ${total_est_value:.4f}')
print(f'Progress to $1,000,000: {progress_to_1m:.8f}%')
print(f'Strategy: Compounding micro-grids + BugHunter high-value bounties')

append_jsonl(ROOT, 'ledger.jsonl', {
    'kind': 'million_dollar_orchestration',
    'usdt': str(round(usdt, 4)),
    'tria': str(round(tria, 4)),
    'bughunter_targets': str(high_value_targets),
    'progress_to_1m_pct': str(round(progress_to_1m, 8)),
    'strategy': 'trading_compounding_plus_external_bounties',
    'live': True
})
