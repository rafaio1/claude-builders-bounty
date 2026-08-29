#!/usr/bin/env python3
"""
Wise P2P Arbitrage Bot v5 - Binance Spot + Wise Rate Delta
Uses reliable Binance spot USDT/BRL as proxy since P2P API is geo-blocked.
Monitors spread between Wise official rate and Binance spot for conversion opportunities.
"""
import os, sys, json, time, requests
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/Agentic")
LOG = ROOT / "logs" / "wise_p2p_arb.log"
WISE_STATE = ROOT / "data" / "aro" / "wise-state.json"

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[ARB] [{ts}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def get_wise_rate():
    """Get official BRL/USD rate from Wise"""
    api_key = os.getenv("WISE_API_KEY")
    if not api_key:
        return 0.1925
    try:
        r = requests.get(
            "https://api.wise.com/v1/rates?source=BRL&target=USD",
            headers={"Authorization": f"Bearer {api_key}"}, timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and len(data) > 0:
                return float(data[0].get("rate", 0.1925))
    except Exception as e:
        log(f"Wise rate error: {e}")
    return 0.1925

def get_binance_spot():
    """Get USDT/BRL spot price from Binance public API"""
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/ticker/price?symbol=USDTBRL",
            timeout=10
        )
        if r.status_code == 200:
            return float(r.json().get("price", 0))
    except Exception as e:
        log(f"Binance spot error: {e}")
    return None

def run_cycle():
    log("Starting arb cycle v5 (Binance Spot vs Wise)")
    
    wise_usd_per_brl = get_wise_rate()
    binance_brl_per_usdt = get_binance_spot()
    
    if not binance_brl_per_usdt or binance_brl_per_usdt <= 0:
        log("Failed to get Binance spot price")
        return
    
    # Convert Binance BRL/USDT to USD/BRL for comparison
    binance_usd_per_brl = 1.0 / binance_brl_per_usdt
    
    # Wise fees ~0.41%, Binance spot taker ~0.1%
    total_fee_pct = 0.0051
    effective_binance = binance_usd_per_brl * (1 - total_fee_pct)
    
    spread_pct = ((effective_binance - wise_usd_per_brl) / wise_usd_per_brl) * 100
    
    state = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "wise_usd_per_brl": round(wise_usd_per_brl, 6),
        "binance_brl_per_usdt": round(binance_brl_per_usdt, 4),
        "binance_usd_per_brl_eff": round(effective_binance, 6),
        "spread_pct": round(spread_pct, 3),
        "actionable": abs(spread_pct) > 2.0,
        "direction": "BUY_USDT_VIA_BINANCE" if spread_pct > 2.0 else ("SELL_USDT_VIA_BINANCE" if spread_pct < -2.0 else "NEUTRAL")
    }
    
    WISE_STATE.parent.mkdir(parents=True, exist_ok=True)
    WISE_STATE.write_text(json.dumps(state, indent=2))
    
    log(f"Wise={wise_usd_per_brl:.6f} | Binance={binance_brl_per_usdt:.4f} BRL/USDT | Spread={spread_pct:+.3f}% | Action={state['direction']}")
    
    if state["actionable"]:
        log(f"🚨 ACTIONABLE SPREAD DETECTED: {spread_pct:+.3f}% — Review for execution")

if __name__ == "__main__":
    log("Wise Arb v5 starting (Binance Spot baseline)")
    while True:
        try:
            run_cycle()
            time.sleep(300)
        except KeyboardInterrupt:
            break
        except Exception as e:
            log(f"Fatal: {e}")
            time.sleep(60)
