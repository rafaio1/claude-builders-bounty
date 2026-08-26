#!/usr/bin/env python3
import ccxt, json, time
from datetime import datetime, timezone

def load_bybit():
    env = {}
    with open('/root/.automaton/bybit-murre.env') as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    bx = ccxt.bybit({
        'apiKey': env['BYBIT_REAL_API_KEY'],
        'secret': env['BYBIT_REAL_API_SECRET'],
        'options': {'defaultType': 'spot'}
    })
    bx.load_markets()
    return bx

def load_binance():
    env = {}
    with open('/Agentic/.env') as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    bn = ccxt.binance({
        'apiKey': env['BINANCE_API_KEY'],
        'secret': env['BINANCE_API_SECRET'],
        'options': {'defaultType': 'spot', 'fetchOpenOrders': {'warnWithoutSymbol': False}}
    })
    bn.load_markets()
    return bn

def sell_dust(exchange, name, assets):
    bal = exchange.fetch_balance()
    print(f"=== {name} DUST SELL ===")
    for asset in assets:
        free = float(bal.get(asset, {}).get('free', 0))
        if free <= 0:
            continue
        sym = f"{asset}/USDT"
        if sym not in exchange.markets:
            print(f"  {asset}: {free} - no USDT pair")
            continue
        m = exchange.markets[sym]
        min_cost = float(m.get('limits', {}).get('cost', {}).get('min', 5) or 5)
        min_qty = float(m.get('limits', {}).get('amount', {}).get('min', 0) or 0)
        try:
            t = exchange.fetch_ticker(sym)
            price = float(t['last'])
            val = free * price
            if val >= min_cost and free >= min_qty:
                q = exchange.amount_to_precision(sym, free)
                print(f"  Selling {q} {asset} @ ~{price} (~{val:.4f} USDT)")
                o = exchange.create_order(sym, 'market', 'sell', float(q))
                print(f"    result: id={o.get('id')} status={o.get('status')} filled={o.get('filled')} avg={o.get('average')}")
            else:
                print(f"  {asset}: {free} (~{val:.4f} USDT) - below min_cost={min_cost}")
        except Exception as e:
            print(f"  {asset} sell erro: {e}")

if __name__ == '__main__':
    bx = load_bybit()
    sell_dust(bx, 'BYBIT', ['ADA', 'DOGE', 'XRP', 'TRX', 'SOL', 'ETH', 'BTC'])
    time.sleep(1)
    bal_bybit = bx.fetch_balance()
    bybit_usdt = float(bal_bybit.get('USDT', {}).get('free', 0))
    print(f"\nBYBIT USDT after dust sell: {bybit_usdt}")

    bn = load_binance()
    sell_dust(bn, 'BINANCE', ['MANA', 'DOGE', 'WLD', 'INJ', 'BTC'])
    time.sleep(1)
    bal_binance = bn.fetch_balance()
    binance_usdt = float(bal_binance.get('USDT', {}).get('free', 0))
    print(f"\nBINANCE USDT after dust sell: {binance_usdt}")

    total = bybit_usdt + binance_usdt
    print(f"\n=== TOTAL USDT: {total:.4f} ===")

    entry = {
        'kind': 'reconciliation',
        'ts': datetime.now(timezone.utc).isoformat(),
        'session': 'dust_sell',
        'capital_real': {
            'binance_usdt': binance_usdt,
            'bybit_usdt': bybit_usdt,
            'total_usd': total,
        },
        'realized_profit_usd': 0.0,
        'note': 'Dust vendido para consolidar capital em USDT.',
    }
    with open('/Agentic/ledger.jsonl', 'a') as f:
        f.write(json.dumps(entry) + '\n')
    print("Ledger updated.")
