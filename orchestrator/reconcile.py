import ccxt, json

# Bybit
env = {}
with open('/root/.automaton/bybit-murre.env') as f:
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip()

bybit = ccxt.bybit({
    'apiKey': env.get('BYBIT_REAL_API_KEY', ''),
    'secret': env.get('BYBIT_REAL_API_SECRET', ''),
    'options': {'defaultType': 'spot'}
})
bybit.load_markets()
bal = bybit.fetch_balance()
bybit_usdt = float(bal.get('USDT', {}).get('free', 0))
print(f'Bybit USDT free: {bybit_usdt:.4f}')
bybit_coins = []
for coin, info in bal.get('total', {}).items():
    if coin != 'USDT' and float(info) > 0:
        bybit_coins.append((coin, float(info)))
        print(f'  Bybit {coin}: {info}')

# Check open orders
bybit_orders = bybit.fetch_open_orders()
print(f'Bybit open orders: {len(bybit_orders)}')

# Binance
env2 = {}
with open('/Agentic/.env') as f:
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            env2[k.strip()] = v.strip()

binance = ccxt.binance({
    'apiKey': env2.get('BINANCE_API_KEY', ''),
    'secret': env2.get('BINANCE_API_SECRET', '')
})
binance.load_markets()
bal2 = binance.fetch_balance()
binance_usdt = float(bal2.get('USDT', {}).get('free', 0))
print(f'Binance USDT free: {binance_usdt:.4f}')
binance_coins = []
for coin, info in bal2.get('total', {}).items():
    if coin != 'USDT' and float(info) > 0:
        binance_coins.append((coin, float(info)))
        print(f'  Binance {coin}: {info}')

binance_orders = binance.fetch_open_orders()
print(f'Binance open orders: {len(binance_orders)}')

total = bybit_usdt + binance_usdt
print(f'\n=== RECONCILIATION SUMMARY ===')
print(f'Bybit USDT: {bybit_usdt:.4f}')
print(f'Binance USDT: {binance_usdt:.4f}')
print(f'Total USDT: {total:.4f}')
print(f'Bybit non-USDT coins: {len(bybit_coins)}')
print(f'Binance non-USDT coins: {len(binance_coins)}')
print(f'Open orders: Bybit={len(bybit_orders)} Binance={len(binance_orders)}')
