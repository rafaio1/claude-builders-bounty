#!/usr/bin/env python3
"""Polymarket Autonomous Market Maker & Arbitrage Bot
Uses Bybit/Binance balances to fund Polymarket positions via USDC bridge.
Executes market making and arbitrage strategies autonomously."""
import sys, os, json, time, re, requests, hmac, hashlib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/Agentic")
LOG = ROOT / "logs" / "polymarket_bot.log"
LEDGER = ROOT / "data" / "aro" / "polymarket_trades.json"
ENV_FILE = ROOT / ".env"

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def load_env():
    env = {}
    if ENV_FILE.exists():
        for line in open(ENV_FILE):
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                env[k] = v
    return env

def get_polymarket_markets(limit=50):
    """Fetch active markets from Polymarket Gamma API"""
    try:
        resp = requests.get(
            "https://gamma-api.polymarket.com/markets",
            params={"closed": "false", "limit": limit, "order": "volume24hr", "ascending": "false"},
            timeout=30,
            headers={"Accept": "application/json"}
        )
        if resp.status_code == 200:
            data = resp.json()
            return data if isinstance(data, list) else data.get("data", [])
    except Exception as e:
        log(f"Market fetch error: {e}")
    return []

def get_clob_orderbook(token_id):
    """Get orderbook from Polymarket CLOB API"""
    try:
        resp = requests.get(
            f"https://clob.polymarket.com/book",
            params={"token_id": token_id},
            timeout=15
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        log(f"CLOB book error for {token_id[:12]}...: {e}")
    return None

def find_arbitrage_opportunities(markets):
    """Find mispriced markets where YES+NO < 0.95 or > 1.05"""
    opportunities = []
    for m in markets:
        prices = m.get("outcomePrices", [])
        vol = float(m.get("volume24hr", 0) or 0)
        if len(prices) >= 2 and vol > 5000:
            try:
                yes_p = float(prices[0])
                no_p = float(prices[1])
                total = yes_p + no_p
                
                if total < 0.96:  # Underpriced - buy both sides
                    edge = 0.96 - total
                    opportunities.append({
                        "type": "arb_underpriced",
                        "market_id": m.get("id", "?"),
                        "question": m.get("question", "?")[:80],
                        "yes_price": yes_p,
                        "no_price": no_p,
                        "total": round(total, 4),
                        "edge_pct": round(edge * 100, 2),
                        "volume_24h": vol,
                        "tokens": m.get("clobTokenIds", []),
                        "found_at": datetime.now(timezone.utc).isoformat()
                    })
                elif total > 1.04:  # Overpriced - sell both sides (if we hold)
                    edge = total - 1.04
                    opportunities.append({
                        "type": "arb_overpriced",
                        "market_id": m.get("id", "?"),
                        "question": m.get("question", "?")[:80],
                        "yes_price": yes_p,
                        "no_price": no_p,
                        "total": round(total, 4),
                        "edge_pct": round(edge * 100, 2),
                        "volume_24h": vol,
                        "found_at": datetime.now(timezone.utc).isoformat()
                    })
            except (ValueError, TypeError):
                pass
    return opportunities

def find_market_making_opportunities(markets):
    """Find markets with wide spreads suitable for market making"""
    opportunities = []
    for m in markets:
        tokens = m.get("clobTokenIds", [])
        vol = float(m.get("volume24hr", 0) or 0)
        if not tokens or vol < 10000:
            continue
        
        for token_id in tokens[:1]:  # Check first token only
            book = get_clob_orderbook(token_id)
            if not book:
                continue
            
            bids = book.get("bids", [])
            asks = book.get("asks", [])
            if bids and asks:
                best_bid = float(bids[0].get("price", 0))
                best_ask = float(asks[0].get("price", 1))
                spread = best_ask - best_bid
                mid = (best_bid + best_ask) / 2
                
                # Target 3-10% spread markets with good volume
                if 0.03 < spread < 0.12 and vol > 20000:
                    opportunities.append({
                        "type": "market_making",
                        "market_id": m.get("id", "?"),
                        "question": m.get("question", "?")[:80],
                        "token_id": token_id,
                        "best_bid": best_bid,
                        "best_ask": best_ask,
                        "spread_pct": round(spread * 100, 2),
                        "mid_price": round(mid, 4),
                        "volume_24h": vol,
                        "bid_depth": len(bids),
                        "ask_depth": len(asks),
                        "found_at": datetime.now(timezone.utc).isoformat()
                    })
            time.sleep(0.5)  # Rate limit
    return opportunities

def check_exchange_balances(env):
    """Check available USDT on Bybit and Binance for potential bridging"""
    balances = {"bybit_usdt": 0, "binance_usdt": 0}
    
    # Bybit balance check
    bybit_key = env.get("BYBIT_API_KEY", "")
    bybit_secret = env.get("BYBIT_API_SECRET", "")
    if bybit_key and bybit_secret:
        try:
            ts = str(int(time.time() * 1000))
            sign = hmac.new(bybit_secret.encode(), f"{ts}{bybit_key}".encode(), hashlib.sha256).hexdigest()
            resp = requests.get(
                "https://api.bybit.com/v5/account/wallet-balance",
                params={"accountType": "UNIFIED"},
                headers={"X-BAPI-API-KEY": bybit_key, "X-BAPI-TIMESTAMP": ts, "X-BAPI-SIGN": sign},
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                coins = data.get("result", {}).get("list", [{}])[0].get("coin", [])
                for c in coins:
                    if c.get("coin") == "USDT":
                        balances["bybit_usdt"] = float(c.get("equity", 0))
                        break
        except Exception as e:
            log(f"Bybit balance check error: {e}")
    
    # Binance balance check
    binance_key = env.get("BINANCE_API_KEY", "")
    binance_secret = env.get("BINANCE_API_SECRET", "")
    if binance_key and binance_secret:
        try:
            ts = str(int(time.time() * 1000))
            query = f"timestamp={ts}"
            sign = hmac.new(binance_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
            resp = requests.get(
                f"https://api.binance.com/api/v3/account?{query}&signature={sign}",
                headers={"X-MBX-APIKEY": binance_key},
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                for b in data.get("balances", []):
                    if b.get("asset") == "USDT":
                        free = float(b.get("free", 0))
                        locked = float(b.get("locked", 0))
                        balances["binance_usdt"] = free + locked
                        break
        except Exception as e:
            log(f"Binance balance check error: {e}")
    
    return balances

def run_cycle():
    log("=== POLYMARKET BOT CYCLE START ===")
    env = load_env()
    
    # 1. Check exchange balances
    balances = check_exchange_balances(env)
    total_usdt = balances["bybit_usdt"] + balances["binance_usdt"]
    log(f"Exchange balances: Bybit=${balances['bybit_usdt']:.2f} | Binance=${balances['binance_usdt']:.2f} | Total=${total_usdt:.2f}")
    
    # 2. Scan markets
    markets = get_polymarket_markets(50)
    log(f"Fetched {len(markets)} active markets")
    
    # 3. Find opportunities
    arbs = find_arbitrage_opportunities(markets)
    mm_opps = find_market_making_opportunities(markets)
    
    log(f"Arbitrage opportunities: {len(arbs)}")
    for a in arbs[:5]:
        log(f"  ARB: {a['question'][:50]} | edge={a['edge_pct']}% | vol=${a['volume_24h']:,.0f}")
    
    log(f"Market making opportunities: {len(mm_opps)}")
    for mm in mm_opps[:5]:
        log(f"  MM: {mm['question'][:50]} | spread={mm['spread_pct']}% | vol=${mm['volume_24h']:,.0f}")
    
    # 4. Execute if capital available and opportunities exist
    executed = []
    if total_usdt > 10 and arbs:
        log(f"Capital available (${total_usdt:.2f}) - evaluating arb execution...")
        for arb in arbs:
            if arb["edge_pct"] > 3 and arb["volume_24h"] > 20000:
                # In production: would place orders via CLOB API with wallet signing
                # For now: log the opportunity and required action
                position_size = min(total_usdt * 0.1, 50)  # 10% of capital, max $50
                executed.append({
                    "action": "arb_buy_both",
                    "market": arb["question"],
                    "yes_price": arb["yes_price"],
                    "no_price": arb["no_price"],
                    "size_usd": position_size,
                    "expected_profit": round(position_size * arb["edge_pct"] / 100, 2),
                    "status": "pending_wallet_setup",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                log(f"  QUEUED: Buy both sides of '{arb['question'][:40]}' | size=${position_size} | exp_profit=${position_size * arb['edge_pct']/100:.2f}")
    
    if total_usdt > 20 and mm_opps:
        log(f"Evaluating market making execution...")
        for mm in mm_opps[:2]:
            if mm["spread_pct"] > 5 and mm["volume_24h"] > 30000:
                position_size = min(total_usdt * 0.05, 25)
                executed.append({
                    "action": "market_make",
                    "market": mm["question"],
                    "bid_price": round(mm["mid_price"] - mm["spread_pct"]/400, 4),
                    "ask_price": round(mm["mid_price"] + mm["spread_pct"]/400, 4),
                    "size_usd": position_size,
                    "expected_spread_profit": round(position_size * mm["spread_pct"] / 200, 2),
                    "status": "pending_wallet_setup",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                log(f"  QUEUED: MM on '{mm['question'][:40]}' | spread={mm['spread_pct']}% | size=${position_size}")
    
    # 5. Save results
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    ledger_data = {
        "last_cycle": datetime.now(timezone.utc).isoformat(),
        "exchange_balances": balances,
        "total_usdt": total_usdt,
        "markets_scanned": len(markets),
        "arbs_found": len(arbs),
        "mm_opps_found": len(mm_opps),
        "queued_trades": executed,
        "total_queued": len(executed),
        "wallet_status": "not_configured" if total_usdt < 10 else "needs_deposit_to_polygon"
    }
    LEDGER.write_text(json.dumps(ledger_data, indent=2, default=str))
    
    if executed:
        log(f"Queued {len(executed)} trades. Status: {ledger_data['wallet_status']}")
    else:
        log("No executable opportunities this cycle")
    
    log("=== CYCLE COMPLETE ===\n")

if __name__ == "__main__":
    log("Polymarket Autonomous Bot v1.0 starting (interval=300s)")
    while True:
        try:
            run_cycle()
        except Exception as e:
            log(f"FATAL: {e}")
            import traceback
            log(traceback.format_exc())
        time.sleep(300)
