import ccxt
import os
import time

def load_env(filepath):
    env = {}
    if os.path.exists(filepath):
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip()
    return env

print("=== BYBIT ===")
bybit_env = load_env('/root/.automaton/bybit-murre.env')
bybit = ccxt.bybit({
    'apiKey': bybit_env.get('BYBIT_REAL_API_KEY'),
    'secret': bybit_env.get('BYBIT_REAL_API_SECRET'),
    'options': {'defaultType': 'spot'}
})
try:
    bybit_bal = bybit.fetch_balance()
    bybit_usdt = bybit_bal.get('USDT', {}).get('free', 0)
    bybit_total = bybit_bal.get('USDT', {}).get('total', 0)
    print(f"Bybit USDT Free: {bybit_usdt}")
    print(f"Bybit USDT Total: {bybit_total}")
    
    # Fetch all assets to see if capital is elsewhere
    for asset, bal in bybit_bal['total'].items():
        if bal > 0:
            print(f"  Asset: {asset} = {bal}")
            
    trades = bybit.fetch_my_trades(limit=20)
    print(f"Recent Bybit Trades ({len(trades)}):")
    pnl = 0
    for t in trades[-10:]:
        print(f"  {t['datetime']} | {t['symbol']} | {t['side']} | {t['amount']} @ {t['price']} | Fee: {t['fee']['cost']} {t['fee']['currency']}")
except Exception as e:
    print(f"Bybit Error: {e}")

print("\n=== BINANCE ===")
binance_env = load_env('/Agentic/.env')
binance = ccxt.binance({
    'apiKey': binance_env.get('BINANCE_API_KEY'),
    'secret': binance_env.get('BINANCE_API_SECRET'),
    'options': {'defaultType': 'spot'}
})
try:
    binance_bal = binance.fetch_balance()
    binance_usdt = binance_bal.get('USDT', {}).get('free', 0)
    binance_total = binance_bal.get('USDT', {}).get('total', 0)
    print(f"Binance USDT Free: {binance_usdt}")
    print(f"Binance USDT Total: {binance_total}")
    
    for asset, bal in binance_bal['total'].items():
        if bal > 0:
            print(f"  Asset: {asset} = {bal}")
            
    trades = binance.fetch_my_trades(limit=20)
    print(f"Recent Binance Trades ({len(trades)}):")
    for t in trades[-10:]:
        print(f"  {t['datetime']} | {t['symbol']} | {t['side']} | {t['amount']} @ {t['price']} | Fee: {t['fee']['cost']} {t['fee']['currency']}")
except Exception as e:
    print(f"Binance Error: {e}")
