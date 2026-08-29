#!/usr/bin/env python3
"""Central reconciliation script - checks all service balances and updates state."""
import os, sys, hashlib, hmac, time, json, urllib.request, urllib.parse

def check_binance():
    key = os.environ.get("BINANCE_API_KEY", "")
    secret = os.environ.get("BINANCE_API_SECRET", "")
    if not key or not secret:
        return {"status": "no_credentials", "balance_usd": 0, "can_trade": False}
    ts = int(time.time() * 1000)
    qs = urllib.parse.urlencode({"timestamp": ts})
    sig = hmac.new(secret.encode(), qs.encode(), hashlib.sha256).hexdigest()
    url = f"https://api.binance.com/api/v3/account?{qs}&signature={sig}"
    req = urllib.request.Request(url, headers={"X-MBX-APIKEY": key})
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        balances = [b for b in data.get("balances", []) if float(b["free"]) > 0 or float(b["locked"]) > 0]
        total_usd = 0
        for b in balances:
            asset = b["asset"]
            free = float(b["free"])
            locked = float(b["locked"])
            if asset in ("USDT", "BUSD", "USDC", "FDUSD", "TUSD"):
                val = free + locked
            elif asset.startswith("LD"):
                try:
                    underlying = asset[2:]
                    purl = f"https://api.binance.com/api/v3/ticker/price?symbol={underlying}USDT"
                    presp = urllib.request.urlopen(purl, timeout=5)
                    price = float(json.loads(presp.read())["price"])
                    val = (free + locked) * price
                except:
                    val = 0
            else:
                try:
                    purl = f"https://api.binance.com/api/v3/ticker/price?symbol={asset}USDT"
                    presp = urllib.request.urlopen(purl, timeout=5)
                    price = float(json.loads(presp.read())["price"])
                    val = (free + locked) * price
                except:
                    val = 0
            total_usd += val
        return {
            "status": "operational",
            "balance_usd": round(total_usd, 2),
            "can_trade": data.get("canTrade", False),
            "balances": [{"asset": b["asset"], "free": b["free"], "locked": b["locked"]} for b in balances],
            "active_positions": []
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "balance_usd": 0}

def check_bybit():
    bkey = os.environ.get("BYBIT_REAL_API_KEY") or os.environ.get("BYBIT_API_KEY", "")
    bsec = os.environ.get("BYBIT_REAL_API_SECRET") or os.environ.get("BYBIT_API_SECRET", "")
    mode = os.environ.get("BYBIT_MODE", "")
    if not bkey or not bsec:
        return {"status": "no_credentials", "balance_usd": 0}
    ts = str(int(time.time() * 1000))
    results = []
    for acct_type in ("UNIFIED", "SPOT", "CONTRACT"):
        params = {"api_key": bkey, "timestamp": ts, "accountType": acct_type}
        sorted_params = dict(sorted(params.items()))
        param_str = urllib.parse.urlencode(sorted_params)
        sig = hmac.new(bsec.encode(), param_str.encode(), hashlib.sha256).hexdigest()
        url = f"https://api.bybit.com/v5/account/wallet-balance?{param_str}&sign={sig}"
        req = urllib.request.Request(url)
        try:
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read())
            ret_code = data.get("retCode")
            ret_msg = data.get("retMsg")
            if ret_code == 0:
                result = {"status": "operational", "mode": mode, "account_type": acct_type, "ret_code": ret_code}
                for acc in data.get("result", {}).get("list", []):
                    result["total_equity"] = acc.get("totalEquity")
                    result["available_to_withdraw"] = acc.get("availableToWithdraw")
                    coins = []
                    for c in acc.get("coin", []):
                        w = float(c.get("walletBalance", "0"))
                        if w > 0:
                            coins.append({"coin": c.get("coin"), "balance": c.get("walletBalance"), "usd": c.get("usdValue")})
                    result["coins"] = coins
                    try:
                        result["balance_usd"] = float(acc.get("totalEquity", "0"))
                    except:
                        result["balance_usd"] = 0
                results.append(result)
                break
            else:
                results.append({"status": "api_error", "account_type": acct_type, "ret_code": ret_code, "ret_msg": ret_msg, "balance_usd": 0})
        except Exception as e:
            results.append({"status": "error", "account_type": acct_type, "error": str(e), "balance_usd": 0})
    for r in results:
        if r.get("status") == "operational":
            return r
    if results:
        return results[0]
    return {"status": "no_credentials", "balance_usd": 0}

def check_wise():
    wkey = os.environ.get("WISE_API_KEY", "")
    wprofile = os.environ.get("WISE_PROFILE_ID", "")
    wrecipient = os.environ.get("WISE_RECIPIENT_ID", "")
    if not wkey:
        return {"status": "no_credentials", "profile_id": wprofile, "recipient_id": wrecipient}
    base = "https://api.transferwise.com"
    try:
        url = f"{base}/v1/borderless-accounts?profileId={wprofile}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {wkey}"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        balances = []
        total_usd = 0
        for acc in data:
            for bal in acc.get("balances", []):
                currency = bal.get("currency", "")
                amount = float(bal.get("amount", {}).get("value", 0))
                if amount > 0:
                    balances.append({
                        "currency": currency,
                        "amount": amount,
                        "type": bal.get("balanceType", "")
                    })
                    if currency == "USD":
                        total_usd += amount
                    elif currency == "BRL":
                        total_usd += amount * 0.18
                    elif currency == "EUR":
                        total_usd += amount * 1.08
                    elif currency == "GBP":
                        total_usd += amount * 1.27
                    else:
                        total_usd += amount
        return {
            "status": "operational",
            "domain": base,
            "profile_id": wprofile,
            "recipient_id": wrecipient,
            "balances": balances,
            "balance_usd": round(total_usd, 2)
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "profile_id": wprofile, "recipient_id": wrecipient}

def check_mt5():
    mt5_account = os.environ.get("MT5_ACCOUNT", "")
    mt5_server = os.environ.get("MT5_SERVER", "")
    mt5_pass = "SET" if os.environ.get("MT5_PASS") else "NOT_SET"
    wine_running = os.system("pgrep -x wine > /dev/null 2>&1") == 0
    mt5_server_running = os.system("pgrep -f mt5server > /dev/null 2>&1") == 0
    return {
        "status": "offline" if not mt5_server_running else "online",
        "account": mt5_account if mt5_account else "not_in_env_check_master_control",
        "server": mt5_server if mt5_server else "not_in_env",
        "pass": mt5_pass,
        "wine_running": wine_running,
        "mt5_server_running": mt5_server_running
    }

def main():
    print("=== ORCA CENTRAL RECONCILIATION ===")
    print(f"Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime())}")
    print()
    print("--- BINANCE ---")
    binance = check_binance()
    print(json.dumps(binance, indent=2))
    print()
    print("--- BYBIT ---")
    bybit = check_bybit()
    print(json.dumps(bybit, indent=2))
    print()
    print("--- WISE ---")
    wise = check_wise()
    print(json.dumps(wise, indent=2))
    print()
    print("--- XM/MT5 ---")
    mt5 = check_mt5()
    print(json.dumps(mt5, indent=2))
    print()
    total = binance.get("balance_usd", 0) + bybit.get("balance_usd", 0) + wise.get("balance_usd", 0)
    state = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "services": {
            "binance": binance,
            "bybit": bybit,
            "wise": wise,
            "xm_mt5": mt5
        },
        "total_capital_usd": round(total, 2)
    }
    with open("/Agentic/state/reconciliation.json", "w") as f:
        json.dump(state, f, indent=2)
    print(f"\nState written to /Agentic/state/reconciliation.json")
    print(f"Total capital: ${state['total_capital_usd']:.2f}")

if __name__ == "__main__":
    main()
