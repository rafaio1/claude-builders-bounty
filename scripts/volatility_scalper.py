#!/usr/bin/env python3
"""
High Volatility Grid Scalper - Autonomous Capital Compounder
Objetivo: Maximizar o rendimento do capital atual ($60) através de scalping
em pares de alta volatilidade na Bybit Spot, respeitando a constituição ARO.
"""
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
        logging.FileHandler('/Agentic/data/aro/scalper.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger('scalper')

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

def cancel_all_orders(symbol=None):
    query = 'category=spot'
    if symbol:
        query += f'&symbol={symbol}'
    res = post('/v5/order/cancel-all', {'category': 'spot', 'symbol': symbol} if symbol else {'category': 'spot'})
    return res

def get_top_volatile_pairs(limit=5):
    """Busca pares com maior volatilidade e volume nas últimas 24h"""
    res = get('/v5/market/tickers', 'category=spot')
    if res.get('retCode') != 0:
        return []
    
    tickers = res['result']['list']
    # Filtrar apenas pares USDT com volume significativo
    usdt_pairs = [t for t in tickers if t['symbol'].endswith('USDT') and float(t.get('turnover24h', 0)) > 1000000]
    
    # Calcular volatilidade (High - Low) / Low
    for t in usdt_pairs:
        high = float(t['highPrice24h'])
        low = float(t['lowPrice24h'])
        t['volatility'] = (high - low) / low if low > 0 else 0
    
    # Ordenar por volatilidade
    usdt_pairs.sort(key=lambda x: x['volatility'], reverse=True)
    return usdt_pairs[:limit]

def run_cycle():
    log.info("=== SCALPER CYCLE START ===")
    
    # 1. Verificar saldo
    bal = get('/v5/account/wallet-balance', 'accountType=UNIFIED')
    usdt = 0
    if bal.get('retCode') == 0:
        for c in bal['result']['list'][0]['coin']:
            if c['coin'] == 'USDT': 
                usdt = float(c.get('walletBalance', 0))
    
    log.info(f"USDT disponível: {usdt:.2f}")
    
    if usdt < 10:
        log.info("Saldo insuficiente para scalping agressivo. Aguardando bounties.")
        return
    
    # 2. Buscar pares voláteis
    volatiles = get_top_volatile_pairs(5)
    if not volatiles:
        log.warning("Nenhum par volátil encontrado.")
        return
    
    target = volatiles[0]
    symbol = target['symbol']
    last_price = float(target['lastPrice'])
    vol = target['volatility']
    
    log.info(f"Alvo: {symbol} | Preço: {last_price} | Vol24h: {vol*100:.2f}%")
    
    # 3. Cancelar ordens antigas de outros pares para concentrar capital
    cancel_all_orders()
    
    # 4. Colocar grid de compra e venda (Scalping 0.5% a 1%)
    # Compra: 0.5% abaixo do preço atual
    # Venda: 0.5% acima do preço atual (se tivermos o ativo)
    
    buy_price = round(last_price * 0.995, 6)
    sell_price = round(last_price * 1.005, 6)
    
    # Calcular quantidade (usar 90% do USDT disponível)
    qty_usdt = usdt * 0.9
    qty = round(qty_usdt / buy_price, 2)
    
    if qty * buy_price < 5:
        log.info("Quantidade muito pequena para operar.")
        return
    
    # Ordem de compra
    buy_order = {
        'category': 'spot',
        'symbol': symbol,
        'side': 'Buy',
        'orderType': 'Limit',
        'qty': str(qty),
        'price': str(buy_price),
        'timeInForce': 'GTC'
    }
    
    log.info(f"Colocando ordem de COMPRA: {qty} {symbol} @ {buy_price}")
    res_buy = post('/v5/order/create', buy_order)
    
    if res_buy.get('retCode') == 0:
        log.info(f"Ordem de compra criada: {res_buy['result']['orderId']}")
        append_jsonl(ROOT, 'ledger.jsonl', {
            'kind': 'scalper_buy_order', 
            'symbol': symbol, 
            'qty': str(qty), 
            'price': str(buy_price),
            'live': True
        })
    else:
        log.error(f"Falha ao criar ordem de compra: {res_buy}")

if __name__ == '__main__':
    run_cycle()
