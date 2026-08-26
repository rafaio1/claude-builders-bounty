#!/usr/bin/env python3
"""Autonomous Grid Sell Daemon - Manages sell side after buy fills."""
import sys, os, json, time, hashlib, hmac, requests, math, logging
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, '/Agentic/build/lib')
from agentic.env import bybit_credentials
from agentic.aro.store import append_jsonl

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('/Agentic/data/aro/grid_manager.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger('grid_daemon')

ROOT = Path('/Agentic')
MILESTONE_USDT = 182.0
PROFIT_MARGIN = 1.02  # 2% above market

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

def run_cycle():
    bal = get('/v5/account/wallet-balance', 'accountType=UNIFIED')
    usdt, xrp = 0, 0
    if bal.get('retCode') == 0:
        for c in bal['result']['list'][0]['coin']:
            if c['coin'] == 'USDT': usdt = float(c.get('walletBalance', 0))
            if c['coin'] == 'XRP': xrp = float(c.get('walletBalance', 0))
    
    total = usdt + (xrp * 0.996)
    log.info(f'USDT={usdt:.2f} XRP={xrp:.1f} Total={total:.2f}')
    
    if total >= MILESTONE_USDT:
        log.info('!!! MILESTONE 182 USDT REACHED !!!')
        append_jsonl(ROOT, 'ledger.jsonl', {'kind': 'milestone_reached', 'usdt': str(round(total,4)), 'live': True})
    
    # Place sell if we have XRP and no open sells
    if xrp >= 1.0:
        orders = get('/v5/order/realtime', 'category=spot&symbol=XRPUSDT')
        has_sell = False
        if orders.get('retCode') == 0:
            for o in orders['result']['list']:
                if o['orderStatus'] in ['New','PartiallyFilled'] and o['side'] == 'Sell':
                    has_sell = True
                    break
        
        if not has_sell:
            tickers = get('/v5/market/tickers', 'category=spot&symbol=XRPUSDT')
            if tickers.get('retCode') == 0 and tickers['result']['list']:
                price = float(tickers['result']['list'][0]['lastPrice'])
                inst = get('/v5/market/instruments-info', 'category=spot&symbol=XRPUSDT')
                if inst.get('retCode') == 0 and inst['result']['list']:
                    i = inst['result']['list'][0]
                    qs = float(i.get('lotSizeFilter',{}).get('qtyStep',0.1))
                    ts_ = float(i.get('priceFilter',{}).get('tickSize',0.0001))
                    mq = float(i.get('lotSizeFilter',{}).get('minOrderQty',0.01))
                    ma = float(i.get('lotSizeFilter',{}).get('minOrderAmt',5))
                    
                    sell_p = math.ceil((price * PROFIT_MARGIN) / ts_) * ts_
                    qty = math.floor(xrp * 0.95 / qs) * qs
                    
                    if qty >= mq and (qty * sell_p) >= ma:
                        dec_q = max(0, -int(math.floor(math.log10(qs)))) if qs < 1 else 0
                        dec_p = max(0, -int(math.floor(math.log10(ts_)))) if ts_ < 1 else 0
                        res = post('/v5/order/create', {
                            'category': 'spot', 'symbol': 'XRPUSDT', 'side': 'Sell',
                            'orderType': 'Limit', 'qty': f'{qty:.{dec_q}f}',
                            'price': f'{sell_p:.{dec_p}f}', 'timeInForce': 'GTC'
                        })
                        if res.get('retCode') == 0:
                            log.info(f'SELL PLACED: {qty:.1f} XRP @ {sell_p:.4f}')
                            append_jsonl(ROOT, 'ledger.jsonl', {
                                'kind': 'grid_sell_placed', 'pair': 'XRPUSDT',
                                'qty': f'{qty:.1f}', 'price': f'{sell_p:.4f}',
                                'strategy': 'autonomous_profit_capture', 'live': True
                            })

if __name__ == '__main__':
    log.info('=== GRID SELL DAEMON STARTED ===')
    while True:
        try:
            run_cycle()
        except Exception as e:
            log.error(f'Cycle error: {e}')
        time.sleep(60)
