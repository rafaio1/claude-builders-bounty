#!/usr/bin/env python3
"""Polymarket Arbitrage & Prediction Market Scanner - Alternative Revenue Stream"""
import sys, os, json, time, re, requests
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/Agentic")
LOG = ROOT / "logs" / "polymarket_arb.log"
LEDGER = ROOT / "data" / "aro" / "polymarket_opportunities.json"
ENV_FILE = ROOT / ".env"

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def scan_polymarket():
    """Scan Polymarket for mispriced markets and arbitrage opportunities"""
    log("=== POLYMARKET SCAN START ===")
    opportunities = []
    
    # 1. Get high-volume markets
    try:
        resp = requests.get(
            "https://gamma-api.polymarket.com/markets",
            params={"closed": "false", "limit": 50, "order": "volume24hr", "ascending": "false"},
            timeout=30,
            headers={"Accept": "application/json"}
        )
        if resp.status_code == 200:
            markets = resp.json() if isinstance(resp.json(), list) else resp.json().get("data", [])
            log(f"  Fetched {len(markets)} high-volume markets")
            
            for m in markets:
                question = m.get("question", "?")
                vol_24h = float(m.get("volume24hr", 0) or 0)
                outcomes = m.get("outcomes", [])
                prices = m.get("outcomePrices", [])
                
                # Look for mispricing: sum of YES+NO should be ~1.0
                # If significantly off, there's an arb opportunity
                if len(prices) >= 2:
                    try:
                        yes_price = float(prices[0])
                        no_price = float(prices[1])
                        total = yes_price + no_price
                        
                        # Arb if total < 0.95 (buy both sides for guaranteed profit)
                        # or total > 1.05 (sell both sides)
                        if total < 0.95 and vol_24h > 10000:
                            edge = 0.95 - total
                            opportunities.append({
                                "type": "arb_underpriced",
                                "market": question[:100],
                                "yes_price": yes_price,
                                "no_price": no_price,
                                "total": total,
                                "edge_pct": round(edge * 100, 2),
                                "volume_24h": vol_24h,
                                "potential_profit_per_100": round(edge * 100, 2),
                                "found_at": datetime.now(timezone.utc).isoformat()
                            })
                            log(f"  ARB FOUND: {question[:60]} | edge={edge*100:.1f}% | vol=${vol_24h:,.0f}")
                        
                        # Also flag high-confidence markets where we could take a position
                        # based on news/sentiment analysis (future enhancement)
                        elif vol_24h > 50000 and (yes_price < 0.15 or yes_price > 0.85):
                            opportunities.append({
                                "type": "high_conviction",
                                "market": question[:100],
                                "yes_price": yes_price,
                                "no_price": no_price,
                                "volume_24h": vol_24h,
                                "signal": "cheap_yes" if yes_price < 0.15 else "expensive_yes",
                                "found_at": datetime.now(timezone.utc).isoformat()
                            })
                            log(f"  SIGNAL: {question[:60]} | yes={yes_price:.2f} | vol=${vol_24h:,.0f}")
                    except (ValueError, TypeError):
                        pass
        else:
            log(f"  Polymarket API error: HTTP {resp.status_code}")
    except Exception as e:
        log(f"  Polymarket scan error: {e}")
    
    # 2. Check CLOB orderbook for spread opportunities
    try:
        clob_resp = requests.get(
            "https://clob.polymarket.com/markets",
            params={"next_cursor": "MA==", "limit": 20},
            timeout=30
        )
        if clob_resp.status_code == 200:
            clob_data = clob_resp.json()
            clob_markets = clob_data.get("data", [])
            log(f"  CLOB: {len(clob_markets)} markets with orderbooks")
            
            for cm in clob_markets:
                tokens = cm.get("tokens", [])
                for token in tokens:
                    bids = token.get("bids", [])
                    asks = token.get("asks", [])
                    if bids and asks:
                        best_bid = float(bids[0].get("price", 0))
                        best_ask = float(asks[0].get("price", 1))
                        spread = best_ask - best_bid
                        if spread > 0.05 and spread < 0.15:  # 5-15% spread = market making opp
                            opportunities.append({
                                "type": "market_making",
                                "token": token.get("token_id", "?")[:20],
                                "best_bid": best_bid,
                                "best_ask": best_ask,
                                "spread_pct": round(spread * 100, 2),
                                "found_at": datetime.now(timezone.utc).isoformat()
                            })
    except Exception as e:
        log(f"  CLOB scan error: {e}")
    
    log(f"Total opportunities found: {len(opportunities)}")
    
    # Save to ledger
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if LEDGER.exists():
        try:
            existing = json.loads(LEDGER.read_text())
        except:
            pass
    
    if "opportunities" not in existing:
        existing["opportunities"] = []
    
    # Deduplicate by market name
    existing_markets = {o.get("market", "") for o in existing["opportunities"]}
    new_opps = [o for o in opportunities if o.get("market", "") not in existing_markets]
    existing["opportunities"].extend(new_opps)
    existing["last_scan"] = datetime.now(timezone.utc).isoformat()
    existing["total_found"] = len(existing["opportunities"])
    
    LEDGER.write_text(json.dumps(existing, indent=2, default=str))
    log(f"Saved {len(new_opps)} new opportunities (total: {existing['total_found']})")
    
    return opportunities

if __name__ == "__main__":
    log("Polymarket Arb Scanner v1.0 starting (interval=300s)")
    while True:
        try:
            scan_polymarket()
        except Exception as e:
            log(f"FATAL: {e}")
        time.sleep(300)
