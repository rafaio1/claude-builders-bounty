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

print('=== $1M ACCELERATION: HIGH-VOLATILITY SCANNER & MULTI-GRID DEPLOYMENT ===')

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
            if low > 0 and high > 0 and vol > 1000000:
                spread_pct = ((high - low) / low) * 100
                volatile_pairs.append({
                    'symbol': symbol,
                    'last': last,
                    'spread_pct': spread_pct,
                    'vol_usd': vol
                })

volatile_pairs.sort(key=lambda x: x['spread_pct'], reverse=True)
top_volatile = volatile_pairs[:5]

print('Top 5 most volatile pairs (24h spread %):')
for p in top_volatile:
    print(f"  {p['symbol']}: {p['spread_pct']:.2f}% spread | Vol: ${p['vol_usd']:,.0f} | Price: {p['last']}")

bal = get('/v5/account/wallet-balance', 'accountType=UNIFIED')
usdt = 0
if bal.get('retCode') == 0:
    for c in bal['result']['list'][0]['coin']:
        if c['coin'] == 'USDT': usdt = float(c.get('walletBalance', 0))

print(f'\nAvailable USDT for new grids: {usdt:.4f}')

deployed = 0
if usdt > 15:
    inst_info = get('/v5/market/instruments-info', 'category=spot&limit=1000')
    inst_map = {}
    if inst_info.get('retCode') == 0:
        for i in inst_info['result']['list']:
            inst_map[i['symbol']] = {
                'qs': float(i.get('lotSizeFilter', {}).get('qtyStep', 0.0001)),
                'ts': float(i.get('priceFilter', {}).get('tickSize', 0.0001)),
                'mq': float(i.get('lotSizeFilter', {}).get('minOrderQty', 0)),
                'ma': float(i.get('lotSizeFilter', {}).get('minOrderAmt', 1))
            }

    for p in top_volatile[:3]:
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
            print(f'{sym}: already has active orders, skipping.')
            continue

        buy_p = math.floor((p['last'] * 0.995) / inst['ts']) * inst['ts']
        qty = math.floor((5.0) / buy_p / inst['qs']) * inst['qs']
        
        if qty >= inst['mq'] and (qty * buy_p) >= inst['ma']:
            dec_q = max(0, -int(math.floor(math.log10(inst['qs'])))) if inst['qs'] < 1 else 0
            dec_p = max(0, -int(math.floor(math.log10(inst['ts'])))) if inst['ts'] < 1 else 0
            
            res = post('/v5/order/create', {
                'category': 'spot', 'symbol': sym, 'side': 'Buy',
                'orderType': 'Limit', 'qty': f'{qty:.{dec_q}f}',
                'price': f'{buy_p:.{dec_p}f}', 'timeInForce': 'GTC'
            })
            if res.get('retCode') == 0:
                print(f'DEPLOYED GRID BUY: {sym} {qty:.{dec_q}f} @ {buy_p:.{dec_p}f} (Volatility Capture)')
                append_jsonl(ROOT, 'ledger.jsonl', {
                    'kind': 'volatility_grid_deployed', 'pair': sym,
                    'qty': f'{qty:.{dec_q}f}', 'price': f'{buy_p:.{dec_p}f}',
                    'spread_24h_pct': str(round(p['spread_pct'], 2)),
                    'strategy': 'multi_asset_volatility_capture_to_1m', 'live': True
                })
                deployed += 1
            else:
                print(f'FAILED {sym}: {res.get("retMsg", "unknown")}')
        time.sleep(0.2)

print(f'\nNew volatility grids deployed: {deployed}')
print('System is now multi-asset and aggressively hunting volatility across Bybit spot market.')

append_jsonl(ROOT, 'ledger.jsonl', {
    'kind': 'multi_asset_expansion',
    'new_grids_deployed': str(deployed),
    'total_active_pairs': str(1 + deployed),
    'strategy': 'high_volatility_spot_rotation_to_1m',
    'live': True
})
