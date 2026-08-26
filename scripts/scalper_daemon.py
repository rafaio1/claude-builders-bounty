#!/usr/bin/env python3
"""
Autonomous Bybit Scalper Daemon - Compounder to $1M
Uses Decimal for precise math and respects Bybit's instrument precision rules.
"""
import sys, os, json, time, hmac, hashlib, requests, logging
from decimal import Decimal, ROUND_DOWN
from pathlib import Path

sys.path.insert(0, '/Agentic/build/lib')
from agentic.env import bybit_credentials

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('/Agentic/data/aro/scalper_daemon.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger('scalper_daemon')

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
        log.error(f'GET {path} failed: {e}')
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
        log.error(f'POST {path} failed: {e}')
        return {'retCode': -1}

def get_decimals(step_str):
    s = str(step_str).rstrip('0')
    if '.' in s:
        return len(s.split('.')[-1])
    return 0

def format_val(val, step_str):
    step = Decimal(str(step_str))
    dec = get_decimals(step_str)
    quantize_str = '0.' + '0' * dec if dec > 0 else '1'
    d_val = Decimal(str(val)).quantize(Decimal(quantize_str), rounding=ROUND_DOWN)
    return str(d_val)

def run_cycle():
    # Cancel stale open orders to free up capital
    open_orders = get('/v5/order/realtime', 'category=spot&limit=50')
    if open_orders.get('retCode') == 0 and open_orders['result']['list']:
        for o in open_orders['result']['list']:
            if o['orderStatus'] in ['New', 'PartiallyFilled']:
                # Cancel if older than 10 minutes (600000 ms)
                created = int(o.get('createdTime', 0))
                if time.time() * 1000 - created > 600000:
                    log.info(f"Canceling stale order {o['orderId']} for {o['symbol']}")
                    post('/v5/order/cancel', {'category': 'spot', 'orderId': o['orderId']})
                    time.sleep(0.5)

    bal = get('/v5/account/wallet-balance', 'accountType=UNIFIED')
    if bal.get('retCode') != 0: return
    
    usdt = 0.0
    coins = {}
    for c in bal['result']['list'][0]['coin']:
        eq = float(c.get('equity', 0))
        locked = float(c.get('locked', 0))
        if c['coin'] == 'USDT':
            usdt = eq - locked
        elif eq > 0 and c['coin'] not in ['USDC', 'BTC', 'ETH', 'EUR', 'USD', 'BRL']:
            coins[c['coin']] = eq - locked
            
    open_orders = get('/v5/order/realtime', 'category=spot&limit=50')
    pending_buys = set()
    pending_sells = set()
    if open_orders.get('retCode') == 0:
        for o in open_orders['result']['list']:
            if o['orderStatus'] in ['New', 'PartiallyFilled']:
                if o['side'] == 'Buy':
                    pending_buys.add(o['symbol'])
                else:
                    pending_sells.add(o['symbol'])
                    
    log.info(f"USDT: {usdt:.2f} | Coins: {len(coins)} | Open Buys: {len(pending_buys)} | Open Sells: {len(pending_sells)}")
    
    tickers = get('/v5/market/tickers', 'category=spot')
    if tickers.get('retCode') != 0: return
    ticker_map = {t['symbol']: t for t in tickers['result']['list']}
    
    # 1. Sell held coins
    for coin, amt in coins.items():
        if amt <= 0: continue
        symbol = f"{coin}USDT"
        if symbol in pending_sells or symbol in pending_buys: continue
        if symbol not in ticker_map: continue
        
        t = ticker_map[symbol]
        last = Decimal(t['lastPrice'])
        high = Decimal(t['highPrice24h'])
        
        target_sell = last * Decimal('1.01')
        if high > last * Decimal('1.005') and high < last * Decimal('1.05'):
            target_sell = high * Decimal('0.998')
            
        info_res = get('/v5/market/instruments-info', f'category=spot&symbol={symbol}')
        if info_res.get('retCode') != 0 or not info_res['result']['list']: continue
        info = info_res['result']['list'][0]
        
        min_amt = Decimal(info['lotSizeFilter']['minOrderAmt'])
        base_prec = info['lotSizeFilter']['basePrecision']
        tick_sz = info['priceFilter']['tickSize']
        
        qty_str = format_val(amt, base_prec)
        price_str = format_val(target_sell, tick_sz)
        
        if Decimal(qty_str) * Decimal(price_str) < min_amt: continue
        
        order = {
            'category': 'spot', 'symbol': symbol, 'side': 'Sell',
            'orderType': 'Limit', 'qty': qty_str, 'price': price_str, 'timeInForce': 'GTC'
        }
        log.info(f"SELL {coin}: {qty_str} @ {price_str}")
        res = post('/v5/order/create', order)
        if res.get('retCode') != 0:
            log.warning(f"Sell failed {symbol}: {res.get('retMsg')}")
            
    # 2. Buy volatile dips (lowered threshold to 5.5 USDT)
    if usdt > 5.5 and len(pending_buys) == 0:
        usdt_pairs = [t for t in tickers['result']['list'] if t['symbol'].endswith('USDT') and float(t.get('turnover24h', 0)) > 10000000]
        for t in usdt_pairs:
            high = float(t['highPrice24h'])
            low = float(t['lowPrice24h'])
            t['vol'] = (high - low) / low if low > 0 else 0
        usdt_pairs.sort(key=lambda x: x['vol'], reverse=True)
        
        for target in usdt_pairs[:15]:
            symbol = target['symbol']
            if symbol in pending_buys or symbol in pending_sells: continue
            
            info_res = get('/v5/market/instruments-info', f'category=spot&symbol={symbol}')
            if info_res.get('retCode') != 0 or not info_res['result']['list']: continue
            info = info_res['result']['list'][0]
            
            min_amt = Decimal(info['lotSizeFilter']['minOrderAmt'])
            base_prec = info['lotSizeFilter']['basePrecision']
            tick_sz = info['priceFilter']['tickSize']
            
            # Skip if our USDT is less than min_amt + small buffer
            if usdt < float(min_amt) + 0.5: continue
            
            last = Decimal(target['lastPrice'])
            buy_price = last * Decimal('0.995')
            
            target_usdt = min(Decimal(str(usdt)) * Decimal('0.95'), Decimal('50.0'))
            qty_raw = target_usdt / buy_price
            
            qty_str = format_val(qty_raw, base_prec)
            price_str = format_val(buy_price, tick_sz)
            
            if Decimal(qty_str) * Decimal(price_str) < min_amt: continue
            
            order = {
                'category': 'spot', 'symbol': symbol, 'side': 'Buy',
                'orderType': 'Limit', 'qty': qty_str, 'price': price_str, 'timeInForce': 'GTC'
            }
            log.info(f"BUY {symbol}: {qty_str} @ {price_str}")
            res = post('/v5/order/create', order)
            if res.get('retCode') == 0:
                log.info(f"✅ BUY ORDER PLACED: {res['result']['orderId']}")
                break
            else:
                log.warning(f"Buy failed {symbol}: {res.get('retMsg')}")

if __name__ == '__main__':
    log.info("Starting Bybit Autonomous Scalper Daemon (v6 - Low Balance & Stale Cancel)...")
    while True:
        try:
            run_cycle()
        except Exception as e:
            log.error(f"Cycle error: {e}")
        time.sleep(30)
