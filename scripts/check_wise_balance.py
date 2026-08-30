#!/usr/bin/env python3
"""Check Wise balance and update state/wise_balance.json"""
import json, os, sys, urllib.request, urllib.error
from datetime import datetime, timezone

STATE_PATH = "state/wise_balance.json"
ENV_PATH = "/root/.automaton/.env"

def load_env():
    env = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    return env

def main():
    env = load_env()
    api_key = env.get("WISE_API_KEY") or env.get("WISE_TOKEN")
    
    result = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "no_credentials",
        "balance_usd": 0.0,
        "balances": {},
        "error": None
    }
    
    if not api_key:
        result["error"] = "WISE_API_KEY not found in /root/.automaton/.env"
        print(json.dumps(result, indent=2))
        with open(STATE_PATH, "w") as f:
            json.dump(result, f, indent=2)
        return
    
    # Try Wise API v1 balances endpoint
    url = "https://api.transferwise.com/v1/balances"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    })
    
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            result["status"] = "ok"
            if isinstance(data, list):
                for acct in data:
                    currency = acct.get("currency", "UNKNOWN")
                    amount = acct.get("amount", {}).get("value", 0)
                    result["balances"][currency] = amount
                    if currency == "USD":
                        result["balance_usd"] = float(amount)
            elif isinstance(data, dict):
                result["balances"] = data
                result["balance_usd"] = float(data.get("USD", {}).get("value", 0))
    except urllib.error.HTTPError as e:
        result["status"] = "api_error"
        result["error"] = f"HTTP {e.code}: {e.reason}"
        # Try v2 endpoint
        try:
            profile_url = "https://api.transferwise.com/v2/profiles"
            req2 = urllib.request.Request(profile_url, headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            })
            with urllib.request.urlopen(req2, timeout=15) as resp2:
                profiles = json.loads(resp2.read())
                result["profiles_found"] = len(profiles) if isinstance(profiles, list) else 1
                result["hint"] = "Use profile ID to query /v4/profiles/{id}/balances"
        except Exception as e2:
            result["v2_error"] = str(e2)
    except Exception as e:
        result["status"] = "connection_error"
        result["error"] = str(e)
    
    print(json.dumps(result, indent=2))
    with open(STATE_PATH, "w") as f:
        json.dump(result, f, indent=2)

if __name__ == "__main__":
    main()
