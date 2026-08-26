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

print('=== FIXING VOLATILITY GRIDS: BASEPRECISION FORMATTING ===')

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
            if low > 0 and high > 0 and vol > 1000000 and last > 0:
                spread_pct = ((high - low) / low) * 100
                volatile_pairs.append({
                    'symbol': symbol,
                    'last': last,
                    'spread_pct': spread_pct,
                    'vol_usd': vol
                })

volatile_pairs.sort(key=lambda x: x['spread_pct'], reverse=True)
top_volatile = volatile_pairs[:15]

inst_info = get('/v5/market/instruments-info', 'category=spot&limit=1000')
inst_map = {}
if inst_info.get('retCode') == 0:
    for i in inst_info['result']['list']:
        inst_map[i['symbol']] = {
            'qs': float(i.get('lotSizeFilter', {}).get('qtyStep', 0.0001)),
            'ts': float(i.get('priceFilter', {}).get('tickSize', 0.0001)),
            'mq': float(i.get('lotSizeFilter', {}).get('minOrderQty', 0)),
            'ma': float(i.get('lotSizeFilter', {}).get('minOrderAmt', 1)),
            'bp': int(i.get('lotSizeFilter', {}).get('basePrecision', 2)),
            'qp': int(i.get('priceFilter', {}).get('quotePrecision', 4))
        }

bal = get('/v5/account/wallet-balance', 'accountType=UNIFIED')
usdt = 0
if bal.get('retCode') == 0:
    for c in bal['result']['list'][0]['coin']:
        if c['coin'] == 'USDT': usdt = float(c.get('walletBalance', 0))

print(f'Available USDT: {usdt:.4f}')

deployed = 0
capital_per_trade = 10.0

for p in top_volatile:
    sym = p['symbol']
    if sym == 'XRPUSDT': continue
    
    inst = inst_map.get(sym)
    if not inst: continue
    
    orders = get('/v5/order/realtime', f'category=spot&symbol={sym}')
    has_orders = False
    if orders.get('retCode') == 0:
        for o in orders['result']['list']:
            if o['orderStatus'] in ['New', 'PartiallyFilled']:
                has_orders = True
                break
    if has_orders:
        continue

    buy_p = math.floor((p['last'] * 0.995) / inst['ts']) * inst['ts']
    if buy_p <= 0: continue
    
    raw_qty = capital_per_trade / buy_p
    qty = math.floor(raw_qty / inst['qs']) * inst['qs']
    
    if qty < inst['mq']:
        continue
        
    if (qty * buy_p) < inst['ma']:
        continue
        
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
        print(f'SUCCESS {sym}: {qty_s} @ {price_s}')
        append_jsonl(ROOT, 'ledger.jsonl', {
            'kind': 'volatility_grid_deployed', 'pair': sym,
            'qty': qty_s, 'price': price_s,
            'spread_24h_pct': str(round(p['spread_pct'], 2)),
            'strategy': 'multi_asset_volatility_capture_fixed', 'live': True
        })
        deployed += 1
        usdt -= capital_per_trade
        if usdt < 10:
            break
    else:
        print(f'FAIL {sym}: {res.get("retMsg", "unknown")}')
        
    time.sleep(0.3)

print(f'\nDeployed: {deployed}')
