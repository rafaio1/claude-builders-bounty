import ccxt, os, json, time
from dotenv import load_dotenv

# === BYBIT ===
load_dotenv('/root/.automaton/bybit-murre.env')
bybit = ccxt.bybit({
    'apiKey': os.getenv('BYBIT_API_KEY'),
    'secret': os.getenv('BYBIT_API_SECRET'),
    'options': {'defaultType': 'spot'}
})

print("=== BYBIT BALANCE ===")
bal = bybit.fetch_balance()
for coin in ['USDT', 'XRP', 'DOGE', 'SOL']:
    f = float(bal.get(coin, {}).get('free', 0) or 0)
    u = float(bal.get(coin, {}).get('used', 0) or 0)
    t = float(bal.get(coin, {}).get('total', 0) or 0)
    print(f"  {coin}: free={f} used={u} total={t}")

print("\n=== BYBIT OPEN ORDERS ===")
all_orders = bybit.fetch_open_orders()
print(f"  Total open orders: {len(all_orders)}")
for o in all_orders:
    print(f"    {o['symbol']} {o['side']} {o['type']} {o['amount']} @ {o['price']} id={o['id']}")

print("\n=== BYBIT RECENT TRADES ===")
for sym in ['XRP/USDT', 'DOGE/USDT', 'SOL/USDT']:
    try:
        trades = bybit.fetch_my_trades(sym, limit=5)
        print(f"  {sym}: {len(trades)} recent trades")
        for t in trades:
            print(f"    {t['side']} {t['amount']} @ {t['price']} fee={t.get('fee',{}).get('cost','?')} {t.get('fee',{}).get('currency','?')} ts={t['timestamp']}")
    except Exception as e:
        print(f"  {sym} trades: ERROR {e}")

# === BINANCE ===
load_dotenv('/Agentic/.env', override=True)
binance = ccxt.binance({
    'apiKey': os.getenv('BINANCE_API_KEY'),
    'secret': os.getenv('BINANCE_API_SECRET'),
    'options': {'defaultType': 'spot'}
})

print("\n=== BINANCE BALANCE ===")
bal = binance.fetch_balance()
for coin in ['USDT', 'XRP', 'DOGE']:
    f = float(bal.get(coin, {}).get('free', 0) or 0)
    u = float(bal.get(coin, {}).get('used', 0) or 0)
    t = float(bal.get(coin, {}).get('total', 0) or 0)
    print(f"  {coin}: free={f} used={u} total={t}")

print("\n=== BINANCE OPEN ORDERS ===")
all_orders = binance.fetch_open_orders()
print(f"  Total open orders: {len(all_orders)}")
for o in all_orders:
    print(f"    {o['symbol']} {o['side']} {o['type']} {o['amount']} @ {o['price']} id={o['id']}")

print("\n=== RECONCILIATION COMPLETE ===")
