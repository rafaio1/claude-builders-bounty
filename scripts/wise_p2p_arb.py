#!/usr/bin/env python3
"""Wise P2P Arbitrage Bot v3 - Deep Analysis with Fees, Gas, and Sanity Checks"""
import os, sys, json, time, requests
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path("/Agentic")
LOG = ROOT / "logs" / "wise_p2p_arb.log"
load_dotenv(ROOT / ".env")

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def get_wise_balances():
    api_key = os.getenv("WISE_API_KEY")
    profile_id = os.getenv("WISE_PROFILE_ID")
    if not api_key or not profile_id:
        return {"USD": 0.0, "BRL": 0.0}
    try:
        r = requests.get(
            f"https://api.wise.com/v4/profiles/{profile_id}/balances?types=STANDARD",
            headers={"Authorization": f"Bearer {api_key}"}, timeout=15
        )
        if r.status_code == 200:
            bals = r.json()
            usd = next((b for b in bals if b.get("currency") == "USD"), None)
            brl = next((b for b in bals if b.get("currency") == "BRL"), None)
            return {
                "USD": float(usd["amount"]["value"]) if usd else 0.0,
                "BRL": float(brl["amount"]["value"]) if brl else 0.0
            }
    except Exception as e:
        log(f"Wise balance error: {e}")
    return {"USD": 0.0, "BRL": 0.0}

def get_official_rate():
    """Get official BRL/USD rate (USD per 1 BRL)"""
    api_key = os.getenv("WISE_API_KEY")
    try:
        r = requests.get(
            "https://api.wise.com/v1/rates?source=BRL&target=USD",
            headers={"Authorization": f"Bearer {api_key}"}, timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and len(data) > 0:
                return float(data[0].get("rate", 0.19))
    except:
        pass
    return 0.1941 # Fallback approx 5.15 BRL/USD

def scan_hodlhodl():
    """Scan HodlHodl for BRL->BTC and BTC->USDT offers"""
    results = []
    try:
        btc_brl = requests.get(
            "https://hodlhodl.com/api/v1/offers?currency=BRL&asset=BTC&type=buy&limit=30",
            timeout=15, headers={"User-Agent": "WiseArbBot/3.0"}
        )
        btc_usdt = requests.get(
            "https://hodlhodl.com/api/v1/offers?currency=USDT&asset=BTC&type=sell&limit=30",
            timeout=15, headers={"User-Agent": "WiseArbBot/3.0"}
        )
        
        if btc_brl.status_code == 200 and btc_usdt.status_code == 200:
            brl_offers = btc_brl.json().get("offers", [])
            usdt_offers = btc_usdt.json().get("offers", [])
            
            # Realistic BTC/BRL price range (e.g., 200k to 500k BRL per BTC)
            valid_brl = [float(o.get("price", 0)) for o in brl_offers 
                        if 200000 < float(o.get("price", 0)) < 600000]
            # Realistic BTC/USDT price range (e.g., 40k to 90k USDT per BTC)
            valid_usdt = [float(o.get("price", 0)) for o in usdt_offers 
                         if 40000 < float(o.get("price", 0)) < 100000]
            
            if valid_brl and valid_usdt:
                best_buy_brl = min(valid_brl)
                best_sell_usdt = max(valid_usdt)
                implied_brl_per_usd = best_buy_brl / best_sell_usdt
                
                results.append({
                    "platform": "hodlhodl",
                    "implied_brl_per_usd": round(implied_brl_per_usd, 4),
                    "buy_brl_per_btc": best_buy_brl,
                    "sell_usdt_per_btc": best_sell_usdt,
                    "valid_brl": len(valid_brl),
                    "valid_usdt": len(valid_usdt)
                })
    except Exception as e:
        log(f"HodlHodl scan error: {e}")
    return results

def deep_arb_analysis(brl_amount, p2p_brl_per_usd, official_usd_per_brl):
    """
    Minucious calculation including:
    1. Wise Conversion Fees
    2. P2P Platform Fees (HodlHodl maker/taker)
    3. Network Gas Fees (BTC receive, BTC send, USDT withdraw)
    4. Slippage Buffer
    """
    # Constants based on current network averages
    WISE_FEE_PCT = 0.023          # ~2.3% Wise conversion/transfer fee
    HODLHODL_FEE_PCT = 0.006      # ~0.6% per P2P trade (we do 2: BRL->BTC, BTC->USDT)
    SLIPPAGE_BUFFER_PCT = 0.015   # 1.5% buffer for order book depth/execution
    
    # Fixed Network Gas Fees (in USD)
    BTC_RECEIVE_FEE_USD = 2.50    # Fee to receive BTC from first P2P seller
    BTC_SEND_FEE_USD = 3.50       # Fee to send BTC to second P2P buyer
    USDT_WITHDRAW_FEE_USD = 1.50  # TRC20/BEP20 USDT network fee
    
    total_fixed_gas_usd = BTC_RECEIVE_FEE_USD + BTC_SEND_FEE_USD + USDT_WITHDRAW_FEE_USD
    
    # Official Route: BRL -> USD via Wise
    official_gross_usd = brl_amount * official_usd_per_brl
    official_net_usd = official_gross_usd * (1 - WISE_FEE_PCT)
    
    # P2P Route: BRL -> BTC -> USDT
    # p2p_brl_per_usd is how many BRL we pay for 1 USD equivalent
    p2p_gross_usd = brl_amount / p2p_brl_per_usd
    
    # Deduct P2P percentage fees (applied twice) and slippage
    p2p_net_after_pct = p2p_gross_usd * (1 - (HODLHODL_FEE_PCT * 2) - SLIPPAGE_BUFFER_PCT)
    
    # Deduct fixed gas fees
    p2p_final_usd = p2p_net_after_pct - total_fixed_gas_usd
    
    # Net Profit of Arb vs just using Wise
    arb_profit_usd = p2p_final_usd - official_net_usd
    roi_pct = (arb_profit_usd / official_net_usd) * 100 if official_net_usd > 0 else 0
    
    # Sanity Check: P2P rate shouldn't be wildly different from official (likely API garbage or scam offer)
    official_brl_per_usd = 1.0 / official_usd_per_brl
    sanity_ratio = p2p_brl_per_usd / official_brl_per_usd
    
    is_sane = 0.85 < sanity_ratio < 1.15
    is_viable = arb_profit_usd > 5.0 and is_sane  # Must make at least $5 net profit and pass sanity
    
    return {
        "official_net_usd": round(official_net_usd, 2),
        "p2p_final_usd": round(p2p_final_usd, 2),
        "arb_profit_usd": round(arb_profit_usd, 2),
        "roi_pct": round(roi_pct, 2),
        "fixed_gas_usd": total_fixed_gas_usd,
        "sanity_ratio": round(sanity_ratio, 3),
        "is_sane": is_sane,
        "is_viable": is_viable
    }

def main():
    log("=== WISE P2P ARB BOT v3 (DEEP ANALYSIS) STARTING ===")
    log("Accounting for: Wise Fees, HodlHodl Fees, BTC/USDT Gas, Slippage, Sanity Checks")
    
    while True:
        try:
            bals = get_wise_balances()
            official_usd_per_brl = get_official_rate()
            official_brl_per_usd = 1.0 / official_usd_per_brl
            
            log(f"Balances: BRL={bals['BRL']:.2f} | USD={bals['USD']:.2f}")
            log(f"Official Rate: 1 USD = {official_brl_per_usd:.4f} BRL")
            
            market = scan_hodlhodl()
            
            if not market:
                log("No valid P2P market data this cycle")
                time.sleep(300)
                continue
                
            offer = market[0]
            p2p_brl_per_usd = offer["implied_brl_per_usd"]
            log(f"P2P Implied: 1 USD = {p2p_brl_per_usd:.4f} BRL (via BTC triangulation)")
            
            # Test with available BRL balance
            test_amount = bals["BRL"]
            if test_amount < 50:
                log(f"Capital too low ({test_amount} BRL) to cover fixed gas fees (~$7.50 USD). Need funding.")
                time.sleep(300)
                continue
                
            analysis = deep_arb_analysis(test_amount, p2p_brl_per_usd, official_usd_per_brl)
            
            log(f"--- DEEP ANALYSIS FOR R$ {test_amount} ---")
            log(f"  Wise Direct Net: ${analysis['official_net_usd']}")
            log(f"  P2P Arb Net:   ${analysis['p2p_final_usd']} (after ~${analysis['fixed_gas_usd']} gas + % fees)")
            log(f"  Net Arb Profit: ${analysis['arb_profit_usd']} (ROI: {analysis['roi_pct']}%)")
            log(f"  Sanity Check:   {analysis['sanity_ratio']} (Valid: {analysis['is_sane']})")
            
            if analysis["is_viable"]:
                log(f"!!! VIABLE OPPORTUNITY DETECTED !!!")
                log(f"Ready for manual review and execution via Wise/HodlHodl interfaces.")
            else:
                if not analysis["is_sane"]:
                    log(f"REJECTED: P2P rate failed sanity check (likely API error or scam offer).")
                else:
                    log(f"REJECTED: Gas and platform fees exceed potential spread. Arb not profitable.")
            
            time.sleep(300)
        except KeyboardInterrupt:
            break
        except Exception as e:
            log(f"Cycle error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
