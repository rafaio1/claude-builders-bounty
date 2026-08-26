#!/usr/bin/env python3
"""
Perpetual Trading Activation Monitor
Waits for USDT balance >= 10 and auto-starts bybit_perp_compounder.py
Also monitors bounty payouts and logs capital events.
"""
import sys, os, json, time, hashlib, hmac, requests, subprocess, logging
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, "/Agentic/build/lib")
from agentic.env import bybit_credentials
from agentic.aro.store import append_jsonl

ROOT = Path("/Agentic")
LOG_FILE = ROOT / "logs" / "perp_activation_monitor.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("PerpActivationMonitor")

api_key, secret = bybit_credentials()
recv_window = "5000"
base = "https://api.bybit.com"
session = requests.Session()
session.trust_env = False

PERP_SCRIPT = ROOT / "scripts" / "bybit_perp_compounder.py"
MIN_BALANCE_FOR_PERP = 10.0
CHECK_INTERVAL = 60  # seconds

def safe_float(val, default=0.0):
    if val is None or val == '':
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

def sign(payload):
    ts = str(int(time.time() * 1000))
    raw = f"{ts}{api_key}{recv_window}{payload}"
    return ts, hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()

def get(path, query=""):
    url = f"{base}{path}"
    if query: url += f"?{query}"
    ts, sig = sign(query)
    h = {"X-BAPI-API-KEY": api_key, "X-BAPI-TIMESTAMP": ts, "X-BAPI-RECV-WINDOW": recv_window, "X-BAPI-SIGN": sig}
    try:
        resp = session.get(url, headers=h, timeout=15)
        return resp.json()
    except Exception as e:
        logger.error(f"GET {path} failed: {e}")
        return {"retCode": -1}

def get_usdt_balance():
    res = get("/v5/account/wallet-balance", "accountType=UNIFIED")
    if res.get("retCode") == 0:
        for coin in res["result"]["list"][0].get("coin", []):
            if coin["coin"] == "USDT":
                return safe_float(coin.get("walletBalance"), 0.0)
    return 0.0

def is_perp_compounder_running():
    try:
        result = subprocess.run(
            ["pgrep", "-f", "bybit_perp_compounder.py"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except:
        return False

def start_perp_compounder():
    logger.info("STARTING bybit_perp_compounder.py...")
    try:
        proc = subprocess.Popen(
            [sys.executable, str(PERP_SCRIPT)],
            stdout=open(ROOT / "logs" / "bybit_perp_compounder.log", "a"),
            stderr=subprocess.STDOUT,
            cwd=str(ROOT)
        )
        logger.info(f"Perp compounder started with PID {proc.pid}")
        append_jsonl(ROOT, "ledger.jsonl", {
            "kind": "perp_trading_activated",
            "pid": str(proc.pid),
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        return True
    except Exception as e:
        logger.error(f"Failed to start perp compounder: {e}")
        return False

def check_bounty_payouts():
    """Check if any bounties moved to paid status."""
    ledger_path = ROOT / "data" / "aro" / "bounty_ledger.json"
    if not ledger_path.exists():
        return 0
    
    try:
        with open(ledger_path) as f:
            data = json.load(f)
        
        paid = [b for b in data.get("bounties", []) 
                if b.get("status") in ("paid", "completed", "merged")]
        total_paid = sum(b.get("bounty_value", 0) for b in paid)
        
        # Check for new payouts vs last known
        state_file = ROOT / "data" / "aro" / "payout_tracker_state.json"
        last_known = 0
        if state_file.exists():
            with open(state_file) as f:
                last_known = json.load(f).get("total_paid", 0)
        
        if total_paid > last_known:
            new_payout = total_paid - last_known
            logger.info(f"NEW BOUNTY PAYOUT DETECTED: ${new_payout:,.2f} (total: ${total_paid:,.2f})")
            append_jsonl(ROOT, "ledger.jsonl", {
                "kind": "bounty_payout_received",
                "new_amount": str(new_payout),
                "total_paid": str(total_paid),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            with open(state_file, "w") as f:
                json.dump({"total_paid": total_paid, "updated": datetime.now(timezone.utc).isoformat()}, f)
        
        return total_paid
    except Exception as e:
        logger.error(f"Bounty payout check error: {e}")
        return 0

if __name__ == "__main__":
    logger.info("=== PERPETUAL ACTIVATION MONITOR STARTED ===")
    logger.info(f"Target: ${MIN_BALANCE_FOR_PERP} USDT to activate perp trading")
    logger.info(f"Check interval: {CHECK_INTERVAL}s")
    
    while True:
        try:
            bal = get_usdt_balance()
            running = is_perp_compounder_running()
            
            logger.info(f"Balance: ${bal:.4f} | Perp running: {running}")
            
            # Check for bounty payouts
            check_bounty_payouts()
            
            if bal >= MIN_BALANCE_FOR_PERP and not running:
                logger.info(f"✅ BALANCE SUFFICIENT (${bal:.2f} >= ${MIN_BALANCE_FOR_PERP})")
                logger.info("Activating perpetual trading...")
                start_perp_compounder()
            elif bal >= MIN_BALANCE_FOR_PERP and running:
                logger.info("Perp trading active and running.")
            else:
                needed = MIN_BALANCE_FOR_PERP - bal
                logger.info(f"⏳ Waiting for ${needed:.2f} more USDT...")
                
                # If was running but balance dropped, it may have crashed or been stopped
                if running and bal < MIN_BALANCE_FOR_PERP:
                    logger.warning("Balance dropped below threshold while running!")
            
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            logger.info("Monitor stopped by user")
            break
        except Exception as e:
            logger.error(f"Monitor loop error: {e}", exc_info=True)
            time.sleep(30)
