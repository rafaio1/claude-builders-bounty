import sys, os, json, time, hashlib, hmac, requests, math
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

print('=== AUTONOMOUS CAPITAL ROTATION & PRECISION FIX ===')

# 1. Free up locked capital by cancelling stale buy orders
orders = get('/v5/order/realtime', 'category=spot&limit=50')
cancelled = 0
if orders.get('retCode') == 0:
    for o in orders['result']['list']:
        if o['orderStatus'] in ['New', 'PartiallyFilled'] and o['side'] == 'Buy':
            res = post('/v5/order/cancel', {'category': 'spot', 'symbol': o['symbol'], 'orderId': o['orderId']})
            if res.get('retCode') == 0:
                print(f"Cancelled stale buy: {o['symbol']} @ {o['price']}")
                cancelled += 1
print(f"Cancelled {cancelled} stale orders to free USDT.")
time.sleep(1)

# 2. Consolidate any leftover XRP via Market Sell
bal = get('/v5/account/wallet-balance', 'accountType=UNIFIED')
usdt = 0
xrp = 0
if bal.get('retCode') == 0:
    for c in bal['result']['list'][0]['coin']:
        if c['coin'] == 'USDT': usdt = float(c.get('walletBalance', 0))
        if c['coin'] == 'XRP': xrp = float(c.get('walletBalance', 0))

if xrp > 1.0:
    print(f"Market selling {xrp} XRP to consolidate...")
    res = post('/v5/order/create', {
        'category': 'spot', 'symbol': 'XRPUSDT', 'side': 'Sell',
        'orderType': 'Market', 'qty': str(math.floor(xrp * 0.99)),
        'timeInForce': 'IOC'
    })
    print(f"XRP Market Sell: {res.get('retMsg')}")
    time.sleep(2)
    bal = get('/v5/account/wallet-balance', 'accountType=UNIFIED')
    if bal.get('retCode') == 0:
        for c in bal['result']['list'][0]['coin']:
            if c['coin'] == 'USDT': usdt = float(c.get('walletBalance', 0))

print(f"Free USDT for deployment: {usdt:.4f}")

# 3. Fetch volatile pairs and instrument precision rules
tickers = get('/v5/market/tickers', 'category=spot')
volatile_pairs = []
if tickers.get('retCode') == 0:
    for t in tickers['result']['list']:
        symbol = t['symbol']
        if symbol.endswith('USDT'):
            high = float(t.get('highPrice24h', 0))
            low = float(t.get('lowPrice24h', 0))
            last = float(t.get('lastPrice', 0))
            vol = float(t.get('turnover24h', 0))
            if low > 0 and high > 0 and vol > 5000000 and last > 0:
                spread_pct = ((high - low) / low) * 100
                volatile_pairs.append({'symbol': symbol, 'last': last, 'spread_pct': spread_pct})

volatile_pairs.sort(key=lambda x: x['spread_pct'], reverse=True)

inst_info = get('/v5/market/instruments-info', 'category=spot&limit=1000')
inst_map = {}
if inst_info.get('retCode') == 0:
    for i in inst_info['result']['list']:
        bp = i.get('lotSizeFilter', {}).get('basePrecision', 2)
        try: bp_int = int(bp)
        except: bp_int = 2
        qp = i.get('priceFilter', {}).get('quotePrecision', 4)
        try: qp_int = int(qp)
        except: qp_int = 4
        
        inst_map[i['symbol']] = {
            'qs': float(i.get('lotSizeFilter', {}).get('qtyStep', 0.0001)),
            'ts': float(i.get('priceFilter', {}).get('tickSize', 0.0001)),
            'mq': float(i.get('lotSizeFilter', {}).get('minOrderQty', 0)),
            'ma': float(i.get('lotSizeFilter', {}).get('minOrderAmt', 1)),
            'bp': bp_int,
            'qp': qp_int
        }

# 4. Deploy precision-formatted grids
deployed = 0
capital_per_trade = min(usdt * 0.3, 15.0)
if capital_per_trade < 5: capital_per_trade = usdt * 0.9 # If low balance, use most of it

for p in volatile_pairs[:15]:
    sym = p['symbol']
    inst = inst_map.get(sym)
    if not inst: continue
    
    buy_p = math.floor((p['last'] * 0.995) / inst['ts']) * inst['ts']
    if buy_p <= 0: continue
    
    raw_qty = capital_per_trade / buy_p
    qty = math.floor(raw_qty / inst['qs']) * inst['qs']
    
    if qty < inst['mq'] or (qty * buy_p) < inst['ma']: continue
        
    bp = inst['bp']
    qp = inst['qp']
    
    qty_s = f"{qty:.{bp}f}"
    price_s = f"{buy_p:.{qp}f}"
    
    res = post('/v5/order/create', {
        'category': 'spot', 'symbol': sym, 'side': 'Buy',
        'orderType': 'Limit', 'qty': qty_s,
        'price': price_s, 'timeInForce': 'GTC'
    })
    
    if res.get('retCode') == 0:
        print(f'SUCCESS {sym}: {qty_s} @ {price_s} (BP={bp}, QP={qp})')
        append_jsonl(ROOT, 'ledger.jsonl', {
            'kind': 'precision_grid_deployed', 'pair': sym,
            'qty': qty_s, 'price': price_s, 'bp': str(bp), 'qp': str(qp),
            'strategy': 'autonomous_precision_rotation_to_1m', 'live': True
        })
        deployed += 1
        usdt -= capital_per_trade
        if usdt < 5: break
    else:
        print(f'FAIL {sym}: {res.get("retMsg", "unknown")} (BP={bp}, QP={qp})')
    time.sleep(0.3)

print(f"\n=== ROTATION COMPLETE: Deployed {deployed} precision grids ===")
