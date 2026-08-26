#!/usr/bin/env python3
"""
CEX-to-CEX Arbitrage Scanner com foco em Maker/Limit Orders.

Filosofia:
- Binance maker fee: 0.075% (com BNB discount) ou 0.1% (sem)
- Bybit maker fee: 0.02% (VIP0 spot)
- Total maker fee: ~0.095% (vs 0.2% taker+taker)
- Withdrawal fee USDT TRC20: ~$1

Com saldo em ambas exchanges: break-even = 0.095% spread
"""
import ccxt, os, sys, json, time, traceback
from datetime import datetime, timezone

LEDGER_PATH = '/Agentic/ledger.jsonl'


def load_creds():
    binance_env = {}
    with open('/Agentic/.env') as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                binance_env[k.strip()] = v.strip()

    bybit_env = {}
    with open('/root/.automaton/bybit-murre.env') as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                bybit_env[k.strip()] = v.strip()

    return binance_env, bybit_env


def init_exchanges():
    benv, yenv = load_creds()
    ex_b = ccxt.binance({
        'apiKey': benv.get('BINANCE_API_KEY', ''),
        'secret': benv.get('BINANCE_API_SECRET', ''),
        'enableRateLimit': True,
        'timeout': 15000,
    })
    ex_y = ccxt.bybit({
        'apiKey': yenv.get('BYBIT_REAL_API_KEY', ''),
        'secret': yenv.get('BYBIT_REAL_API_SECRET', ''),
        'enableRateLimit': True,
        'timeout': 15000,
        'options': {'defaultType': 'spot'}
    })
    ex_b.load_markets()
    ex_y.load_markets()
    return ex_b, ex_y


def log_ledger(entry):
    with open(LEDGER_PATH, 'a') as f:
        f.write(json.dumps(entry) + '\n')
    print(f"[LEDGER] {json.dumps(entry)}", flush=True)


def scan_arb(ex_b, ex_y, min_spread_pct=0.05):
    b_symbols = set(ex_b.symbols)
    y_symbols = set(ex_y.symbols)
    common = sorted(b_symbols & y_symbols)
    usdt_pairs = [s for s in common if s.endswith('/USDT') and not s.startswith('LD')]

    print(f"Scanning {len(usdt_pairs)} common USDT pairs...", flush=True)

    results = []
    batch_size = 50

    for i in range(0, len(usdt_pairs), batch_size):
        batch = usdt_pairs[i:i + batch_size]
        try:
            b_tick = ex_b.fetch_tickers(batch)
        except Exception as e:
            print(f"  Binance tickers batch {i}: {e}", flush=True)
            b_tick = {}
        try:
            y_tick = ex_y.fetch_tickers(batch)
        except Exception as e:
            print(f"  Bybit tickers batch {i}: {e}", flush=True)
            y_tick = {}

        for sym in batch:
            b = b_tick.get(sym)
            y = y_tick.get(sym)
            if not b or not y:
                continue
            b_ask = b.get('ask')
            b_bid = b.get('bid')
            y_ask = y.get('ask')
            y_bid = y.get('bid')
            if not b_ask or not b_bid or not y_ask or not y_bid:
                continue
            if b_ask <= 0 or y_ask <= 0:
                continue

            # Direction 1: Buy Binance (ask), Sell Bybit (bid)
            spread1 = (y_bid - b_ask) / b_ask * 100
            # Direction 2: Buy Bybit (ask), Sell Binance (bid)
            spread2 = (b_bid - y_ask) / y_ask * 100

            best_spread = max(spread1, spread2)
            if abs(best_spread) > min_spread_pct:
                direction = "B->Y" if spread1 > spread2 else "Y->B"
                results.append({
                    'symbol': sym,
                    'spread_pct': round(best_spread, 4),
                    'direction': direction,
                    'b_ask': b_ask,
                    'b_bid': b_bid,
                    'y_ask': y_ask,
                    'y_bid': y_bid,
                })

        time.sleep(0.3)

    results.sort(key=lambda x: -abs(x['spread_pct']))
    return results, len(usdt_pairs)


def calculate_net_profit(spread_pct, capital_usdt, maker_fee_pct=0.095, withdrawal_fee=0.0):
    gross_profit = capital_usdt * (spread_pct / 100)
    total_fees = capital_usdt * (maker_fee_pct / 100) + withdrawal_fee
    net = gross_profit - total_fees
    return net


def main():
    print(f"[ARB SCANNER] Iniciado em {datetime.now(timezone.utc).isoformat()}", flush=True)
    ex_b, ex_y = init_exchanges()

    b_bal = ex_b.fetch_balance()
    y_bal = ex_y.fetch_balance()
    b_usdt = float(b_bal.get('USDT', {}).get('free', 0))
    y_usdt = float(y_bal.get('USDT', {}).get('free', 0))
    print(f"  Binance USDT: {b_usdt:.2f} | Bybit USDT: {y_usdt:.2f}", flush=True)

    has_both = b_usdt > 5 and y_usdt > 5
    withdrawal_fee = 0.0 if has_both else 1.0
    capital = min(b_usdt, y_usdt) if has_both else min(b_usdt, y_usdt)

    print(f"  Capital disponivel: ${capital:.2f} | Withdrawal fee: ${withdrawal_fee}", flush=True)
    print(f"  Maker fee total: 0.095% (Binance 0.075% + Bybit 0.02%)", flush=True)

    if capital > 0:
        min_break_even = 0.095 + (withdrawal_fee / capital * 100)
    else:
        min_break_even = 999
    print(f"  Break-even spread: {min_break_even:.4f}%", flush=True)
    print(flush=True)

    results, total_scanned = scan_arb(ex_b, ex_y, min_spread_pct=0.05)

    print(f"\n=== TOP 30 ARB SPREADS ===", flush=True)
    print(f"Total pairs scanned: {total_scanned}", flush=True)
    print(f"Pairs with spread > 0.05%: {len(results)}", flush=True)
    print(f"Break-even: {min_break_even:.4f}%", flush=True)
    print(flush=True)

    viable = []
    for r in results[:30]:
        net = calculate_net_profit(r['spread_pct'], capital, 0.095, withdrawal_fee)
        is_viable = net > 0
        status = "VIABLE" if is_viable else "skip"
        print(f"  {r['symbol']:15s} {r['direction']} spread={r['spread_pct']:+.4f}% "
              f"net=${net:.4f} {status}", flush=True)
        if is_viable:
            viable.append({**r, 'net_profit': net})

    print(f"\nViable opportunities: {len(viable)}", flush=True)

    if viable:
        log_ledger({
            'kind': 'arb_scan_result',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'total_pairs': total_scanned,
            'viable_count': len(viable),
            'top_opportunities': viable[:5],
            'capital_usd': capital,
            'maker_fee_pct': 0.095,
            'withdrawal_fee': withdrawal_fee,
        })

    return viable


if __name__ == '__main__':
    try:
        viable = main()
        if viable:
            print(f"\n[VIABLE] {len(viable)} oportunidades viaveis encontradas!", flush=True)
        else:
            print(f"\n[SKIP] Nenhuma oportunidade viavel. Spreads insuficientes para superar fees.", flush=True)
    except Exception as e:
        print(f"[ERROR] {e}", flush=True)
        traceback.print_exc()
