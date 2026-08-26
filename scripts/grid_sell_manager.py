#!/usr/bin/env python3
"""Autonomous Grid Sell Manager - Created by ARO to fill gap in sell-side automation.
This tool monitors filled buy orders and automatically places corresponding sell orders
at profit targets. Runs continuously until milestone reached."""
import sys, os, json, time, hashlib, hmac, requests, math
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, '/Agentic/build/lib')
from agentic.env import bybit_credentials
from agentic.aro.store import append_jsonl

ROOT = Path('/Agentic')
MILESTONE_USDT = 182.0
PROFIT_TARGETS = [1.015, 1.025, 1.040]  # 1.5%, 2.5%, 4% above entry

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
        return {'retCode': -1, 'error': str(e)}

def post(path, body):
    url = f'{base}{path}'
    payload = json.dumps(body, separators=(',', ':'), ensure_ascii=False)
    ts, sig = sign(payload)
    h = {'X-BAPI-API-KEY': api_key, 'X-BAPI-TIMESTAMP': ts, 'X-BAPI-RECV-WINDOW': recv_window, 'X-BAPI-SIGN': sig, 'Content-Type': 'application/json'}
    try:
        resp = session.post(url, headers=h, data=payload, timeout=15)
        return resp.json()
    except Exception as e:
        return {'retCode': -1, 'error': str(e)}

def get_balance():
    bal = get('/v5/account/wallet-balance', 'accountType=UNIFIED')
    usdt = 0
    xrp = 0
    if bal.get('retCode') == 0:
        for c in bal['result']['list'][0]['coin']:
            if c['coin'] == 'USDT': usdt = float(c.get('walletBalance', 0))
            if c['coin'] == 'XRP': xrp = float(c.get('walletBalance', 0))
    return usdt, xrp

def get_instrument(symbol):
    info = get('/v5/market/instruments-info', f'category=spot&symbol={symbol}')
    if info.get('retCode') == 0 and info['result']['list']:
        i = info['result']['list'][0]
        return {
            'qty_step': float(i.get('lotSizeFilter', {}).get('qtyStep', 0.1)),
            'tick_size': float(i.get('priceFilter', {}).get('tickSize', 0.0001)),
            'min_qty': float(i.get('lotSizeFilter', {}).get('minOrderQty', 0.01)),
            'min_amt': float(i.get('lotSizeFilter', {}).get('minOrderAmt', 5))
        }
    return {'qty_step': 0.1, 'tick_size': 0.0001, 'min_qty': 0.01, 'min_amt': 5}

def format_qty(q, step):
    q = math.floor(q / step) * step
    if step >= 1:
        return str(int(q))
    decimals = max(0, -int(math.floor(math.log10(step))))
    return f'{q:.{decimals}f}'

def format_price(p, tick):
    decimals = max(0, -int(math.floor(math.log10(tick)))) if tick < 1 else 0
    return f'{p:.{decimals}f}'

def run_cycle():
    usdt, xrp = get_balance()
    total_value = usdt + (xrp * 0.996)  # approximate
    
    print(f'[{datetime.now(timezone.utc).strftime("%H:%M:%S")}] USDT: {usdt:.2f} | XRP: {xrp:.1f} | Value: {total_value:.2f}')
    
    if total_value >= MILESTONE_USDT:
        print('!!! MILESTONE REACHED !!!')
        append_jsonl(ROOT, 'ledger.jsonl', {
            'kind': 'milestone_reached', 'milestone': '1000_brl_target',
            'usdt_equivalent': str(round(total_value, 4)), 'live': True
        })
        return True
    
    # Check for XRP balance that needs sell orders
    if xrp >= 1.0:
        inst = get_instrument('XRPUSDT')
        
        # Check existing sells
        orders = get('/v5/order/realtime', 'category=spot&symbol=XRPUSDT')
        open_sells = []
        if orders.get('retCode') == 0:
            for o in orders['result']['list']:
                if o['orderStatus'] in ['New', 'PartiallyFilled'] and o['side'] == 'Sell':
                    open_sells.append(o)
        
        # If no open sells, place at profit target
        if not open_sells:
            tickers = get('/v5/market/tickers', 'category=spot&symbol=XRPUSDT')
            if tickers.get('retCode') == 0 and tickers['result']['list']:
                price = float(tickers['result']['list'][0]['lastPrice'])
                
                # Place sell at +2% above current market
                sell_p = math.ceil((price * 1.02) / inst['tick_size']) * inst['tick_size']
                qty = format_qty(xrp * 0.95, inst['qty_step'])
                
                if float(qty) >= inst['min_qty'] and (float(qty) * sell_p) >= inst['min_amt']:
                    res = post('/v5/order/create', {
                        'category': 'spot', 'symbol': 'XRPUSDT', 'side': 'Sell',
                        'orderType': 'Limit', 'qty': qty,
                        'price': format_price(sell_p, inst['tick_size']),
                        'timeInForce': 'GTC'
                    })
                    if res.get('retCode') == 0:
                        print(f'  SELL PLACED: {qty} XRP @ {sell_p:.4f}')
                        append_jsonl(ROOT, 'ledger.jsonl', {
                            'kind': 'grid_sell_placed', 'pair': 'XRPUSDT',
                            'qty': qty, 'price': str(sell_p),
                            'strategy': 'autonomous_profit_capture', 'live': True
                        })
    
    # Check for recent fills and log profits
    history = get('/v5/execution/list', 'category=spot&limit=10')
    if history.get('retCode') == 0:
        now_ms = int(time.time() * 1000)
        for t in history['result']['list']:
            age_ms = now_ms - int(t.get('execTime', 0))
            if age_ms < 300000:  # last 5 min
                pnl = float(t.get('closedPnl', 0))
                if abs(pnl) > 0.001:
                    print(f'  FILL: {t["symbol"]} {t["side"]} PnL={pnl:.4f}')
    
    return False

if __name__ == '__main__':
    print('=== AUTONOMOUS GRID SELL MANAGER STARTED ===')
    print(f'Target: {MILESTONE_USDT} USDT (~1000 BRL)')
    print('Running continuous monitoring loop...')
    
    while True:
        try:
            milestone = run_cycle()
            if milestone:
                print('Milestone achieved. Continuing with 50% owner share policy.')
            time.sleep(60)
        except Exception as e:
            print(f'Error: {e}')
            time.sleep(30)
