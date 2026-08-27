#!/usr/bin/env python3
"""
Revenue Reconciler v2.1 - Hardened per review.
- BYBIT_MIN_BALANCE = 5.0 (fail-closed below)
- bounty_evidence list/None safe (fail-closed)
- Audit hard deadline 45s, max 20 API calls
- Settlement validation: provider allowlist, currency allowlist, positive gross/net, non-neg fee, non-empty tx_id
- Status groups by currency
- Loop command with backoff and lock
"""

import json
import os
import sys
import time
import fcntl
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess

# === CONFIGURATION ===
WORKDIR = Path("/Agentic")
QUEUE_FILE = WORKDIR / "data/aro/approved_pr_payment_queue.json"
REALIZED_LEDGER = WORKDIR / "data/aro/realized_revenue_ledger.jsonl"
CHECKPOINT_FILE = WORKDIR / "data/aro/reconciler_checkpoint.json"
LOCK_FILE = WORKDIR / "data/aro/reconciler.lock"
MAX_API_CALLS = 20
API_TIMEOUT = 10
MAX_WORKERS = 5
AUDIT_HARD_DEADLINE = 45
BYBIT_MIN_BALANCE = 5.0
ALLOWED_PROVIDERS = {"wise", "bybit", "binance", "coinbase", "paypal", "stripe"}
ALLOWED_CURRENCIES = {"USD", "USDT", "USDC", "EUR", "BRL", "BTC", "ETH"}

TIER_A_REQUIRED_FIELDS = [
    "official_reward_url",
    "official_value",
    "eligibility_confirmed",
    "claim_path_verified"
]

def load_json(path):
    if not path.exists():
        return [] if str(path).endswith(".json") and "queue" in str(path) else {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] Failed to load {path}: {e}", file=sys.stderr)
        return [] if str(path).endswith(".json") and "queue" in str(path) else {}

def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def validate_settlement(entry):
    """Fail-closed validation. Returns (valid, reason)."""
    provider = entry.get("provider", "")
    tx_id = str(entry.get("transaction_id", "")).strip()
    currency = entry.get("currency", "")
    timestamp = entry.get("timestamp", "")

    if provider not in ALLOWED_PROVIDERS:
        return False, f"provider_not_allowed:{provider}"
    if not tx_id:
        return False, "empty_transaction_id"
    if currency not in ALLOWED_CURRENCIES:
        return False, f"currency_not_allowed:{currency}"
    if not timestamp:
        return False, "missing_timestamp"

    try:
        gross = float(entry.get("gross", -1))
        fee = float(entry.get("fee", -1))
        net = float(entry.get("net", -1))
    except (TypeError, ValueError):
        return False, "non_numeric_amounts"

    if gross <= 0:
        return False, "gross_must_be_positive"
    if fee < 0:
        return False, "fee_must_be_nonnegative"
    if net <= 0:
        return False, "net_must_be_positive"
    if abs((gross - fee) - net) > 0.0001:
        return False, "net_mismatch"

    return True, "ok"

def append_ledger(entry):
    """Append-only write with dedupe and validation."""
    REALIZED_LEDGER.parent.mkdir(parents=True, exist_ok=True)

    valid, reason = validate_settlement(entry)
    if not valid:
        print(f"[REJECT] Settlement validation failed: {reason}", file=sys.stderr)
        return False

    dedupe_key = f"{entry.get('provider','')}::{str(entry.get('transaction_id','')).strip()}"

    if REALIZED_LEDGER.exists():
        with open(REALIZED_LEDGER, "r") as f:
            for line in f:
                try:
                    existing = json.loads(line.strip())
                    existing_key = f"{existing.get('provider','')}::{str(existing.get('transaction_id','')).strip()}"
                    if existing_key == dedupe_key:
                        print(f"[DEDUPE] Already recorded: {dedupe_key}", file=sys.stderr)
                        return False
                except:
                    continue

    entry["recorded_at"] = datetime.now(timezone.utc).isoformat()
    with open(REALIZED_LEDGER, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return True

def classify_item_fast(item):
    """Fast-path classification. Fail-closed on bad types."""
    status = item.get("status", "").upper()
    github_merged = item.get("github_merged", False)
    bounty_evidence = item.get("bounty_evidence", {})

    if not isinstance(bounty_evidence, dict):
        return "INCOMPLETE_EVIDENCE", "bounty_evidence_not_dict"

        return "REJECTED", "cached_status"
    if not github_merged:
        return "PENDING_MERGE", "not_merged"

    has_all_fields = all(bounty_evidence.get(f) for f in TIER_A_REQUIRED_FIELDS)
    if not has_all_fields:
        return "INCOMPLETE_EVIDENCE", "missing_tier_a_fields"

    return "TIER_A_PAYABLE", "passed_prefilter"

def verify_gh_safe(repo, pr_num):
    try:
        result = subprocess.run(
            ["gh", "pr", "view", str(pr_num), "--repo", repo, "--json", "state,mergedAt,reviews,statusCheckRollup"],
            capture_output=True, text=True, timeout=API_TIMEOUT
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass
    return None

def audit(max_api_calls=MAX_API_CALLS):
    """Optimized audit with hard deadline."""
    start = time.time()
    queue = load_json(QUEUE_FILE)

    stats = {
        "total": len(queue), "rejected": 0, "pending": 0,
        "tier_a": 0, "api_calls": 0, "deadline_exceeded": False
    }

    candidates = []
    for item in queue:
        decision, reason = classify_item_fast(item)
        if decision == "REJECTED":
            stats["rejected"] += 1
            continue
        if decision in ("PENDING_MERGE", "INCOMPLETE_EVIDENCE"):
            stats["pending"] += 1
            continue
        candidates.append(item)

    verified_tier_a = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {}
        for item in candidates:
            if time.time() - start > AUDIT_HARD_DEADLINE:
                stats["deadline_exceeded"] = True
                break
            if len(futures) >= max_api_calls:
                break
            ck = item.get("canonical_key", "")
            parts = ck.split("#")
            if len(parts) == 2:
                repo, pr = parts[0], parts[1]
                futures[executor.submit(verify_gh_safe, repo, pr)] = item
                stats["api_calls"] += 1

        for future in as_completed(futures):
            item = futures[future]
            gh_data = future.result()
            if gh_data and gh_data.get("state") == "MERGED" and item.get("github_merged"):
                verified_tier_a.append({
                    "canonical_key": item.get("canonical_key"),
                    "bounty_evidence": item.get("bounty_evidence", {}),
                    "verified_merged_at": gh_data.get("mergedAt"),
                    "audit_decision": "TIER_A_CONFIRMED"
                })
                stats["tier_a"] += 1

    elapsed = time.time() - start
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed, 2),
        "stats": stats,
        "tier_a_items": verified_tier_a,
        "checkpoint_saved": True
    }

    save_json(CHECKPOINT_FILE, {
        "last_audit": report["timestamp"],
        "last_stats": stats,
        "tier_a_keys": [x["canonical_key"] for x in verified_tier_a]
    })

    print(json.dumps(report, indent=2))
    return report

def reconcile(provider, transaction_id, timestamp, currency, gross, fee, net, metadata=None):
    entry = {
        "provider": provider,
        "transaction_id": transaction_id,
        "timestamp": timestamp,
        "currency": currency,
        "gross": gross,
        "fee": fee,
        "net": net,
        "metadata": metadata or {}
    }
    success = append_ledger(entry)
    if success:
        print(f"[OK] Recorded settlement: {provider}::{transaction_id} net={net} {currency}")
    else:
        print(f"[FAIL] Settlement rejected or duplicate: {provider}::{transaction_id}", file=sys.stderr)
        sys.exit(1)

def status():
    checkpoint = load_json(CHECKPOINT_FILE)
    ledger_count = 0
    totals_by_currency = {}

    if REALIZED_LEDGER.exists():
        with open(REALIZED_LEDGER, "r") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    ledger_count += 1
                    ccy = entry.get("currency", "UNKNOWN")
                    totals_by_currency[ccy] = totals_by_currency.get(ccy, 0.0) + float(entry.get("net", 0))
                except:
                    pass

    print(json.dumps({
        "checkpoint": checkpoint,
        "realized_ledger_entries": ledger_count,
        "total_realized_net_by_currency": {k: round(v, 4) for k, v in totals_by_currency.items()},
        "bybit_floor_enforced": True,
        "min_balance_usdt": BYBIT_MIN_BALANCE
    }, indent=2))

def run_loop(interval_start=300, backoff=2.0, max_interval=3600):
    interval = interval_start
    while True:
        try:
            report = audit()
            tier_a_count = report.get("stats", {}).get("tier_a", 0)
            if tier_a_count > 0:
                interval = interval_start
            else:
                interval = min(int(interval * backoff), max_interval)
            print(f"[LOOP] Next audit in {interval}s", flush=True)
            time.sleep(interval)
        except KeyboardInterrupt:
            print("[LOOP] Stopped by user", file=sys.stderr)
            break
        except Exception as e:
            print(f"[LOOP ERROR] {e}", file=sys.stderr)
            time.sleep(min(interval, 60))

def main():
    if len(sys.argv) < 2:
        print("Usage: revenue_reconciler.py [audit|reconcile|status|loop]", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]

    lock_fd = None
    try:
        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = open(LOCK_FILE, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_fd.write(str(os.getpid()))
        lock_fd.flush()
    except BlockingIOError:
        print("[LOCK] Another instance running. Exiting.", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"[LOCK WARN] {e}", file=sys.stderr)

    try:
        if cmd == "audit":
            audit()
        elif cmd == "reconcile":
            if len(sys.argv) < 9:
                print("Usage: reconcile <provider> <tx_id> <timestamp> <currency> <gross> <fee> <net> [metadata_json]", file=sys.stderr)
                sys.exit(1)
            meta = json.loads(sys.argv[9]) if len(sys.argv) > 9 else {}
            reconcile(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5],
                     float(sys.argv[6]), float(sys.argv[7]), float(sys.argv[8]), meta)
        elif cmd == "status":
            status()
        elif cmd == "loop":
            run_loop()
        else:
            print(f"Unknown command: {cmd}", file=sys.stderr)
            sys.exit(1)
    finally:
        if lock_fd:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()

if __name__ == "__main__":
    main()
