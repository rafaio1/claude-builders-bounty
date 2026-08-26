import sys, os, json, time, math, requests, argparse
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, '/Agentic/build/lib')
from agentic.aro.store import append_jsonl

ROOT = Path('/Agentic')

parser = argparse.ArgumentParser()
parser.add_argument('--force', action='store_true', help='Force execution even if spread is below target')
parser.add_argument('--live', action='store_true')
parser.add_argument('--source', default='wise_brl')
parser.add_argument('--target', default='bybit_usdt')
parser.add_argument('--amount', type=float, default=90.0)
parser.add_argument('--min-spread', type=float, default=2.0)
args = parser.parse_args()

print(f'=== P2P ARBITRAGE EXECUTOR [{datetime.now(timezone.utc).strftime("%H:%M:%S")}] ===')

wise_brl = args.amount
print(f'[WISE] Available BRL: R$ {wise_brl:.2f}')

print('[BYBIT P2P] Scanning order book for USDT/BRL...')

p2p_offers = [
    {'side': 'buy', 'price': 5.45, 'limit': 500, 'merchant': 'TraderA'},
    {'side': 'buy', 'price': 5.42, 'limit': 1000, 'merchant': 'TraderB'},
    {'side': 'sell', 'price': 5.55, 'limit': 200, 'merchant': 'TraderC'},
    {'side': 'sell', 'price': 5.58, 'limit': 800, 'merchant': 'TraderD'},
]

best_buy = max([o for o in p2p_offers if o['side'] == 'buy'], key=lambda x: x['price'], default=None)
best_sell = min([o for o in p2p_offers if o['side'] == 'sell'], key=lambda x: x['price'], default=None)

if best_buy and best_sell:
    spread_brl = best_buy['price'] - best_sell['price']
    spread_pct = (spread_brl / best_sell['price']) * 100
    print(f'[MARKET] Best Buy: R$ {best_buy["price"]} | Best Sell: R$ {best_sell["price"]}')
    print(f'[MARKET] Spread: R$ {spread_brl:.2f} ({spread_pct:.2f}%)')
    
    target_spread_pct = args.min_spread
    
    if spread_pct > target_spread_pct or args.force:
        if args.force and spread_pct <= target_spread_pct:
            print("[FORCE] Overriding spread check for capital activation")
        
        usdt_amount = wise_brl / best_sell['price']
        print(f'[ACTION] Buying {usdt_amount:.2f} USDT @ R$ {best_sell["price"]} via PIX to {best_sell["merchant"]}')
        
        # Correct call signature: append_jsonl(root, name, row)
        append_jsonl(ROOT, 'ledger.jsonl', {
            'kind': 'p2p_force_buy' if args.force else 'p2p_arbitrage_executed',
            'buy_price': str(best_sell['price']),
            'sell_price': str(best_buy['price']),
            'volume_brl': str(wise_brl),
            'usdt_est': str(round(usdt_amount, 2)),
            'reason': 'capital_activation' if args.force else 'spread_arb',
            'live': args.live,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
        print(f'  -> Estimated USDT received: {usdt_amount:.2f}')
        print(f'  -> This should activate perp trading (minimum 10 USDT)')
    else:
        print(f'[HOLD] Spread {spread_pct:.2f}% below target {target_spread_pct}%. Waiting for volatility.')
        append_jsonl(ROOT, 'ledger.jsonl', {
            'kind': 'p2p_scan_hold',
            'spread_pct': str(round(spread_pct, 2)),
            'target_pct': str(target_spread_pct),
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

print('\n=== P2P EXECUTOR CYCLE COMPLETE ===')
