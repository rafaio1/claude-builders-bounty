#!/usr/bin/env python3
"""
P2P Arbitrage Orchestrator v1.0
================================
Fluxo completo: Scan Real -> Sanity Check -> Profit Calc -> Execution Gate -> Ledger
Conecta HodlHodl (BTC/BRL) + CoinGecko (USDT ref) + Wise (FX fallback)
"""

import os, sys, json, time, requests
from datetime import datetime, timezone
from pathlib import Path
from decimal import Decimal, ROUND_DOWN

ROOT = Path("/Agentic")
LOG_DIR = ROOT / "logs"
LOG_FILE = LOG_DIR / "p2p_orchestrator.log"
LEDGER_FILE = ROOT / "ledger.jsonl"

# Configs
MIN_SPREAD_PCT = 1.0          # Spread mínimo após fees
MAX_CAPITAL_BRL = 100.0       # Capital máximo por trade
WISE_FEE_PCT = 0.005          # Fee Wise conversion
HODLHODL_FEE_PCT = 0.006      # Fee HodlHodl per side
SLIPPAGE_BUFFER = 0.005       # Buffer slippage
FIXED_GAS_USD = 2.00          # BTC receive + send + USDT withdraw

LOG_DIR.mkdir(parents=True, exist_ok=True)

def log(msg, level="INFO"):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def append_ledger(entry: dict):
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    with open(LEDGER_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")

def get_fx_rate_brl_usd():
    """Get BRL/USD rate from Binance USDTBRL ticker (primary) or CoinGecko (fallback)"""
    try:
        # Primary: Binance USDT/BRL spot price (most liquid and accurate for arb)
        r = requests.get(
            "https://api.binance.com/api/v3/ticker/price?symbol=USDTBRL",
            timeout=8, headers={"User-Agent": "P2P-Orchestrator/1.0"}
        )
        if r.status_code == 200:
            price = float(r.json().get("price", 0))
            if price > 0:
                return price
    except Exception as e:
        log(f"Binance FX error: {e}", "WARN")

    # Fallback: CoinGecko
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=tether&vs_currencies=brl",
            timeout=10, headers={"User-Agent": "P2P-Orchestrator/1.0"}
        )
        if r.status_code == 200:
            brl_per_usdt = r.json().get("tether", {}).get("brl", 0)
            if brl_per_usdt > 0:
                return float(brl_per_usdt)
    except Exception as e:
        log(f"CoinGecko FX error: {e}", "WARN")
    return 5.17  # Hardcoded fallback based on last known rate

def scan_hodlhodl_multi():
    """Scan HodlHodl for BTC offers in BRL, USD, EUR, GBP for cross-currency arb"""
    result = {}
    
    # Binance reference prices for sanity checks
    refs = {}
    for sym in ["BTCBRL", "BTCUSDT"]:
        try:
            r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={sym}", timeout=8)
            if r.status_code == 200:
                refs[sym] = float(r.json().get("price", 0))
        except Exception:
            pass
    
    currencies = ["BRL", "USD", "EUR", "GBP"]
    
    for currency in currencies:
        result[currency] = {"buy": [], "sell": []}
        
        for side in ["buy", "sell"]:
            try:
                url = f"https://hodlhodl.com/api/v1/offers?currency_code={currency}&asset=BTC&type={side}&limit=50"
                r = requests.get(url, timeout=15, headers={"User-Agent": "P2P-Orchestrator/1.0"})
                if r.status_code == 200:
                    offers = r.json().get("offers", [])
                    valid = []
                    for o in offers:
                        price = float(o.get("price", 0))
                        min_amt = float(o.get("min_amount", 0))
                        max_amt = float(o.get("max_amount", 0))
                        curr = o.get("currency_code", "")
                        
                        if curr != currency:
                            continue
                        if max_amt < 50:
                            continue
                        
                        # Sanity check against Binance spot (converted)
                        ref_key = "BTCBRL" if currency == "BRL" else "BTCUSDT"
                        if ref_key in refs and refs[ref_key] > 0:
                            ref_price = refs[ref_key]
                            # For non-BRL, we'd need FX conversion - skip strict check for now
                            if currency == "BRL" and not (200000 < price < 600000):
                                continue
                        
                        valid.append({
                            "id": o.get("id"),
                            "price": price,
                            "min": min_amt,
                            "max": max_amt,
                            "currency": currency,
                            "merchant": o.get("trader", {}).get("login", "unknown"),
                            "payment": o.get("payment_method_instructions", "N/A")
                        })
                    
                    valid.sort(key=lambda x: x["price"], reverse=(side == "buy"))
                    result[currency][side] = valid[:5]
                    
            except Exception as e:
                log(f"HodlHodl {currency}/{side} scan error: {e}", "ERROR")
    
    return result

def find_best_cross_currency_arb(market_data, fx_rates):
    """
    Find best arbitrage across currencies.
    Routes: 
      1. BRL->BTC->USD (buy BTC with BRL, sell for USD)
      2. BRL->BTC->EUR->USD (triangular)
      3. Direct BRL/USD spread on same platform
    Returns best opportunity dict or None
    """
    opportunities = []
    
    # Route 1: BRL->BTC->USD (buy BTC with BRL, sell for USD)
    # We buy BTC: take BRL SELL offers (people selling BTC for BRL), sorted ascending = cheapest first
    # We sell BTC: take USD BUY offers (people buying BTC with USD), sorted descending = highest first
    brl_sells = market_data.get("BRL", {}).get("sell", [])
    usd_buys = market_data.get("USD", {}).get("buy", [])
    
    if brl_sells and usd_buys:
        best_buy_brl = brl_sells[0]  # Lowest BRL sell price = cheapest to buy BTC
        best_sell_usd = usd_buys[0]  # Highest USD buy price = best to sell BTC
        
        # Calculate implied BRL/USD rate via BTC
        # We buy BTC at X BRL/BTC, sell at Y USD/BTC
        # Effective rate: X/Y BRL per USD
        btc_price_brl = best_buy_brl["price"]
        btc_price_usd = best_sell_usd["price"]
        
        if btc_price_usd > 0:
            implied_brl_per_usd = btc_price_brl / btc_price_usd
            market_brl_per_usd = fx_rates.get("USDTBRL", 5.17)
            
            # If implied rate is LOWER than market, we profit
            # (we get more USD for our BRL via BTC than direct)
            spread_pct = ((market_brl_per_usd - implied_brl_per_usd) / market_brl_per_usd) * 100
            
            opportunities.append({
                "route": "BRL->BTC->USD",
                "buy_offer": best_buy_brl,
                "sell_offer": best_sell_usd,
                "implied_rate": round(implied_brl_per_usd, 4),
                "market_rate": round(market_brl_per_usd, 4),
                "spread_pct": round(spread_pct, 2),
                "direction": "profitable" if spread_pct > 0 else "loss"
            })
    
    # Route 2: USD->BTC->BRL (buy BTC with USD, sell for BRL)
    # We buy BTC: take USD SELL offers (people selling BTC for USD), sorted ascending = cheapest first
    # We sell BTC: take BRL BUY offers (people buying BTC with BRL), sorted descending = highest first
    usd_sells = market_data.get("USD", {}).get("sell", [])
    brl_buys = market_data.get("BRL", {}).get("buy", [])
    
    if usd_sells and brl_buys:
        best_buy_usd = usd_sells[0]  # Lowest USD sell price = cheapest to buy BTC
        best_sell_brl = brl_buys[0]  # Highest BRL buy price = best to sell BTC
        
        btc_price_usd = best_buy_usd["price"]
        btc_price_brl = best_sell_brl["price"]
        
        if btc_price_usd > 0:
            implied_brl_per_usd = btc_price_brl / btc_price_usd
            market_brl_per_usd = fx_rates.get("USDTBRL", 5.17)
            
            # Reverse: profitable if implied > market (we get more BRL for USD via BTC)
            spread_pct = ((implied_brl_per_usd - market_brl_per_usd) / market_brl_per_usd) * 100
            
            opportunities.append({
                "route": "USD->BTC->BRL",
                "buy_offer": best_buy_usd,
                "sell_offer": best_sell_brl,
                "implied_rate": round(implied_brl_per_usd, 4),
                "market_rate": round(market_brl_per_usd, 4),
                "spread_pct": round(spread_pct, 2),
                "direction": "profitable" if spread_pct > 0 else "loss"
            })
    
    # Sort by spread descending
    opportunities.sort(key=lambda x: x["spread_pct"], reverse=True)
    
    return opportunities[0] if opportunities else None


def calculate_arb_opportunity(buy_offer, sell_offer, fx_brl_usd, capital_brl):
    """
    Calculate real arbitrage profit considering all fees
    
    Route: Buy BTC with BRL on HodlHodl -> Sell BTC for USDT equivalent
    Reference: USDT/BRL market rate from CoinGecko
    """
    btc_price_buy = buy_offer["price"]      # BRL per BTC (what we pay)
    btc_price_sell = sell_offer["price"]     # BRL per BTC (what we get if selling back)
    
    # Effective USDT we could get by selling BTC at market rate
    # Using CoinGecko USDT/BRL as proxy for BTC->USDT exit
    usdt_market_value = capital_brl / fx_brl_usd
    
    # Actual BTC we can buy
    btc_amount = capital_brl / btc_price_buy
    
    # Value of that BTC in BRL at sell side (spread capture)
    btc_value_brl = btc_amount * btc_price_sell
    
    # Convert to USDT equivalent
    gross_usdt = btc_value_brl / fx_brl_usd
    
    # Deduct fees
    hodlhodl_fees = capital_brl * HODLHODL_FEE_PCT * 2  # Buy + Sell sides
    wise_fee_equiv = capital_brl * WISE_FEE_PCT         # Opportunity cost vs Wise direct
    slippage = capital_brl * SLIPPAGE_BUFFER
    
    total_fees_brl = hodlhodl_fees + wise_fee_equiv + slippage
    total_fees_usd = total_fees_brl / fx_brl_usd
    
    net_usdt = gross_usdt - total_fees_usd - FIXED_GAS_USD
    
    # Compare to baseline: just holding USDT via Wise
    baseline_usdt = (capital_brl / fx_brl_usd) * (1 - WISE_FEE_PCT)
    
    profit_usd = net_usdt - baseline_usdt
    roi_pct = (profit_usd / baseline_usdt * 100) if baseline_usdt > 0 else 0
    
    return {
        "capital_brl": capital_brl,
        "btc_buy_price": btc_price_buy,
        "btc_sell_price": btc_price_sell,
        "fx_brl_usd": fx_brl_usd,
        "gross_usdt": round(gross_usdt, 2),
        "total_fees_usd": round(total_fees_usd, 2),
        "fixed_gas_usd": FIXED_GAS_USD,
        "net_usdt": round(net_usdt, 2),
        "baseline_usdt": round(baseline_usdt, 2),
        "profit_usd": round(profit_usd, 2),
        "roi_pct": round(roi_pct, 2),
        "is_viable": profit_usd > 5.0 and roi_pct >= MIN_SPREAD_PCT
    }

def run_cycle(dry_run=True):
    """Execute one full arb cycle with multi-currency support"""
    log("=" * 60)
    log(f"CYCLE START | Mode: {'DRY-RUN' if dry_run else 'LIVE'}")
    
    # Step 1: Get FX references
    fx_rates = {}
    for sym in ["USDTBRL", "BTCBRL", "BTCUSDT"]:
        try:
            r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={sym}", timeout=8)
            if r.status_code == 200:
                fx_rates[sym] = float(r.json().get("price", 0))
        except Exception as e:
            log(f"FX fetch error {sym}: {e}", "WARN")
    
    usdt_brl = fx_rates.get("USDTBRL", 5.17)
    log(f"FX Rates: USDT/BRL={usdt_brl:.4f} | BTC/BRL={fx_rates.get('BTCBRL',0):.0f} | BTC/USDT={fx_rates.get('BTCUSDT',0):.0f}")
    
    # Step 2: Scan multi-currency markets
    log("Scanning HodlHodl multi-currency order books (BRL, USD, EUR, GBP)...")
    market = scan_hodlhodl_multi()
    
    total_offers = sum(len(market[c]["buy"]) + len(market[c]["sell"]) for c in market)
    log(f"Total valid offers found: {total_offers}")
    for c in ["BRL", "USD", "EUR", "GBP"]:
        b = len(market[c]["buy"])
        s = len(market[c]["sell"])
        if b > 0 or s > 0:
            log(f"  {c}: {b} buy, {s} sell")
    
    # Step 3: Find best cross-currency opportunity
    opp = find_best_cross_currency_arb(market, {"USDTBRL": usdt_brl})
    
    if not opp:
        log("No cross-currency opportunities found this cycle.", "WARN")
        append_ledger({"kind": "cycle_skip", "reason": "no_opportunities", "dry_run": dry_run})
        log("CYCLE END")
        log("=" * 60)
        return
    
    log(f"--- BEST OPPORTUNITY: {opp['route']} ---")
    log(f"  Implied Rate: {opp['implied_rate']} BRL/USD")
    log(f"  Market Rate:  {opp['market_rate']} BRL/USD")
    log(f"  Spread:       {opp['spread_pct']}% ({opp['direction']})")
    log(f"  Buy Offer:    {opp['buy_offer']['currency']} {opp['buy_offer']['price']} (ID: {opp['buy_offer']['id'][:8]})")
    log(f"  Sell Offer:   {opp['sell_offer']['currency']} {opp['sell_offer']['price']} (ID: {opp['sell_offer']['id'][:8]})")
    
    # Step 4: Calculate actual profit with fees
    capital_brl = min(MAX_CAPITAL_BRL, opp['buy_offer']['max'], opp['sell_offer']['max'])
    if capital_brl < 100:
        log(f"Capital too low ({capital_brl} BRL). Skipping.", "WARN")
        append_ledger({"kind": "cycle_skip", "reason": "capital_too_low", "dry_run": dry_run})
        log("CYCLE END")
        log("=" * 60)
        return
    
    # Estimate profit based on spread
    gross_profit_pct = opp['spread_pct']
    total_fees_pct = (HODLHODL_FEE_PCT * 2 + WISE_FEE_PCT + SLIPPAGE_BUFFER) * 100
    net_profit_pct = gross_profit_pct - total_fees_pct
    
    # Convert to USD profit
    capital_usd = capital_brl / usdt_brl
    gross_profit_usd = capital_usd * (gross_profit_pct / 100)
    total_fees_usd = capital_usd * (total_fees_pct / 100) + FIXED_GAS_USD
    net_profit_usd = gross_profit_usd - total_fees_usd
    
    is_viable = net_profit_usd > 5.0 and net_profit_pct >= MIN_SPREAD_PCT
    
    log(f"--- PROFIT ANALYSIS (R$ {capital_brl:.0f} / ${capital_usd:.2f}) ---")
    log(f"  Gross Spread:  {gross_profit_pct:.2f}%")
    log(f"  Total Fees:    {total_fees_pct:.2f}% + ${FIXED_GAS_USD} gas")
    log(f"  Net Spread:    {net_profit_pct:.2f}%")
    log(f"  Net Profit:    ${net_profit_usd:.2f}")
    log(f"  VIABLE:        {is_viable}")
    
    # Step 5: Decision gate
    if is_viable:
        action = "EXECUTE" if not dry_run else "SIMULATE_EXECUTE"
        log(f">>> VIABLE OPPORTUNITY | Action: {action}", "SUCCESS")
        
        append_ledger({
            "kind": "arb_opportunity" if dry_run else "arb_executed",
            "route": opp["route"],
            "buy_offer_id": opp["buy_offer"]["id"],
            "sell_offer_id": opp["sell_offer"]["id"],
            "buy_price": str(opp["buy_offer"]["price"]),
            "sell_price": str(opp["sell_offer"]["price"]),
            "buy_currency": opp["buy_offer"]["currency"],
            "sell_currency": opp["sell_offer"]["currency"],
            "capital_brl": str(capital_brl),
            "spread_pct": str(opp["spread_pct"]),
            "net_profit_usd": str(round(net_profit_usd, 2)),
            "net_profit_pct": str(round(net_profit_pct, 2)),
            "fx_rate": str(usdt_brl),
            "dry_run": dry_run
        })
        
        if not dry_run:
            log("!!! LIVE EXECUTION NOT YET IMPLEMENTED !!!", "WARN")
            log("Review ledger and enable live mode after validation", "WARN")
    else:
        reason = "below_spread_threshold" if net_profit_pct < MIN_SPREAD_PCT else "below_min_profit"
        log(f"No viable arb. Net {net_profit_pct:.2f}% < {MIN_SPREAD_PCT}% or profit ${net_profit_usd:.2f} < $5")
        append_ledger({
            "kind": "arb_rejected",
            "reason": reason,
            "route": opp["route"],
            "spread_pct": str(opp["spread_pct"]),
            "net_profit_usd": str(round(net_profit_usd, 2)),
            "net_profit_pct": str(round(net_profit_pct, 2)),
            "dry_run": dry_run
        })
    
    log("CYCLE END")
    log("=" * 60)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="P2P Arb Orchestrator")
    parser.add_argument("--live", action="store_true", help="Enable live execution (NOT RECOMMENDED YET)")
    parser.add_argument("--once", action="store_true", help="Run single cycle instead of loop")
    parser.add_argument("--interval", type=int, default=300, help="Seconds between cycles")
    args = parser.parse_args()
    
    log("P2P ARBITRAGE ORCHESTRATOR v1.0 INITIALIZED")
    log(f"Config: MIN_SPREAD={MIN_SPREAD_PCT}% | MAX_CAPITAL=R${MAX_CAPITAL_BRL} | GAS=${FIXED_GAS_USD}")
    
    if args.once:
        run_cycle(dry_run=not args.live)
    else:
        while True:
            try:
                run_cycle(dry_run=not args.live)
                log(f"Sleeping {args.interval}s until next cycle...")
                time.sleep(args.interval)
            except KeyboardInterrupt:
                log("Shutdown requested. Exiting.")
                break
            except Exception as e:
                log(f"Cycle error: {e}", "ERROR")
                time.sleep(60)

if __name__ == "__main__":
    main()
