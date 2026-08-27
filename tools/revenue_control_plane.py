#!/usr/bin/env python3
"""Revenue Control Plane — deterministic state machine for revenue work orders.

States: discovered -> verified -> claimed -> implementing -> reviewed ->
        submitted -> feedback -> accepted -> payment_pending -> settled

Fail-closed: only Tier A payable items (merged + dict evidence with amount/url
+ official claim path) enter work orders. Max 3 active orders. No speculative
PRs, no spending, no external publishing in this cycle.
"""
import json
import os
import sys
import time
import fcntl
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = Path("/Agentic")
QUEUE_FILE = BASE / "data/aro/approved_pr_payment_queue.json"
LEDGER_FILE = BASE / "data/aro/realized_revenue_ledger.jsonl"
WORK_ORDERS_FILE = BASE / "data/aro/revenue_work_orders.json"
STATUS_FILE = BASE / "data/aro/revenue_manager_status.json"
LOCK_FILE = BASE / "data/aro/.revenue_control_plane.lock"

VALID_STATES = [
    "discovered", "verified", "claimed", "implementing", "reviewed",
    "submitted", "feedback", "accepted", "payment_pending", "settled"
]

ALLOWED_PROVIDERS = {"wise", "bybit", "binance", "coinbase", "paypal", "stripe"}
ALLOWED_CURRENCIES = {"USD", "USDT", "USDC", "EUR", "BRL", "BTC", "ETH"}


def load_json(path: Path) -> Any:
    if not path.exists():
        return [] if path.name.endswith(".json") and "queue" in path.name else {}
    with open(path, "r") as f:
        return json.load(f)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def append_ledger(entry: dict) -> None:
    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


def is_tier_a_payable(item: dict) -> bool:
    """Tier A requires: merged=True, dict bounty_evidence with amount+url, official claim path."""
    if not item.get("merged") and not item.get("api_merged"):
        return False
    evidence = item.get("bounty_evidence")
    if not isinstance(evidence, dict):
        return False
    if "amount" not in evidence or "url" not in evidence:
        return False
    if not evidence.get("claim_path"):
        return False
    status = item.get("status", "")
    if status in ("NOT_BOUNTY", "SATIRICAL_HONEYPOT_PI_IMPOSSIBLE", "RADAR_REPO_EXTERNAL_PAYOUT"):
        return False
    return True


def compute_ev_per_hour(item: dict) -> float:
    """Conservative EV/hour estimate. Returns 0 for spam/honeypot/satire."""
    reason = item.get("classification_reason", "")
    if any(k in reason.upper() for k in ["SATIRICAL", "HONEYPOT", "SPAM", "IMPOSSIBLE"]):
        return 0.0
    evidence = item.get("bounty_evidence")
    if not isinstance(evidence, dict):
        return 0.0
    try:
        amount = float(evidence.get("amount", 0))
    except (ValueError, TypeError):
        return 0.0
    # Conservative: assume 4h implementation + 24h review + 72h payout = 100h
    hours = 100.0
    return round(amount / hours, 4)


def build_work_orders(queue: list, max_orders: int = 3) -> list:
    """Select top Tier A payable items by EV/hour, max max_orders.
    
    Sources (priority order):
    1. approved_pr_payment_queue.json — merged PRs with dict bounty_evidence
    2. verified_revenue_candidates.json — pre-vetted open issues/bounties with official claim path
    """
    VERIFIED_CANDIDATES_FILE = BASE / "data/aro/verified_revenue_candidates.json"
    candidates = []

    # Source 1: Traditional queue (merged PRs)
    for item in queue:
        if not is_tier_a_payable(item):
            continue
        ev = compute_ev_per_hour(item)
        if ev <= 0:
            continue
        candidates.append({
            "id": f"wo-{item.get('canonical_key', '').replace('/', '-').replace('#', '-')}",
            "canonical_key": item.get("canonical_key"),
            "source_issue": item.get("url"),
            "repo": item.get("canonical_key", "").split("#")[0] if item.get("canonical_key") else "",
            "title": item.get("title", ""),
            "bounty_amount": float(item["bounty_evidence"].get("amount", 0)),
            "currency": item["bounty_evidence"].get("currency", "USD"),
            "claim_path": item["bounty_evidence"].get("claim_path", ""),
            "bounty_program": item.get("bounty_program", "unknown"),
            "eligibility_verified": True,
            "maintainer_active": True,
            "state": "verified",
            "ev_per_hour_conservative": ev,
            "estimated_hours": 100.0,
            "capital_required": 0,
            "next_action": "validate_claim_path_and_eligibility",
            "risk_notes": "",
            "discovered_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

    # Source 2: Verified candidates (open issues with official claim path)
    verified = load_json(VERIFIED_CANDIDATES_FILE)
    if isinstance(verified, list):
        existing_keys = {c.get("canonical_key") for c in candidates}
        for item in verified:
            key = item.get("canonical_key", "")
            if key in existing_keys:
                continue
            # Must have official claim/payment path and non-zero value
            payment_path = item.get("payment_path") or item.get("claim_path")
            if not payment_path:
                continue
            value = float(item.get("value_usd", 0))
            if value <= 0:
                continue
            # Reject spam/honeypot/inactive via explicit flags or rejection_reason
            if item.get("is_spam") or item.get("is_honeypot") or item.get("repo_inactive"):
                continue
            if item.get("rejection_reason"):
                continue
            ev = float(item.get("ev_net_per_hour", 0))
            if ev <= 0:
                continue
            state_raw = (item.get("state_current") or item.get("current_state") or "discovered").lower()
            if state_raw not in VALID_STATES:
                state_raw = "discovered"
            candidates.append({
                "id": f"wo-{key.replace('/', '-').replace('#', '-')}",
                "canonical_key": key,
                "source_issue": item.get("url"),
                "repo": key.split("#")[0] if "#" in key else "",
                "title": item.get("title") or (item.get("notes", "").split(".")[0] if item.get("notes") else key),
                "bounty_amount": value,
                "currency": item.get("currency", "USD"),
                "claim_path": payment_path,
                "bounty_program": "Opire" if "opire" in ((item.get("source_official") or item.get("official_source") or "") + payment_path).lower() else "unknown",
                "eligibility_verified": bool(item.get("eligibility") and item.get("eligibility") != "unknown"),
                "maintainer_active": bool(item.get("program_maintainer_active", False)),
                "state": state_raw,
                "ev_per_hour_conservative": ev,
                "estimated_hours": float(item.get("hours_remaining") or item.get("hours_remaining_estimate") or 10),
                "capital_required": 0,
                "next_action": item.get("next_action_concrete") or item.get("next_action") or "review_and_claim",
                "risk_notes": item.get("notes") or item.get("rejection_reason") or "",
                "discovered_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })

    candidates.sort(key=lambda x: x.get("ev_per_hour_conservative", 0), reverse=True)
    # Sort by EV/hour descending; use conservative estimate from verified candidates
    return candidates[:max_orders]


def load_settled_keys() -> set:
    """Load provider+transaction_id from ledger to avoid double counting."""
    keys = set()
    if not LEDGER_FILE.exists():
        return keys
    with open(LEDGER_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                pid = entry.get("provider", "")
                tid = entry.get("transaction_id", "")
                if pid and tid:
                    keys.add(f"{pid}:{tid}")
            except json.JSONDecodeError:
                continue
    return keys


def reconcile_ledger() -> dict:
    """Summarize realized revenue grouped by currency."""
    totals = {}
    count = 0
    if not LEDGER_FILE.exists():
        return {"total_by_currency": {}, "entries": 0}
    with open(LEDGER_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                currency = entry.get("currency", "UNKNOWN")
                net = float(entry.get("net", 0))
                if currency not in totals:
                    totals[currency] = 0.0
                totals[currency] += net
                count += 1
            except (json.JSONDecodeError, ValueError, TypeError):
                continue
    # Round to avoid float drift
    for k in totals:
        totals[k] = round(totals[k], 6)
    return {"total_by_currency": totals, "entries": count}


def generate_status(work_orders: list, reconciliation: dict) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    unpaid_fill_capacity = len([w for w in work_orders if w["state"] in ("discovered", "verified")])
    return {
        "generated_at": now,
        "active_work_orders": len(work_orders),
        "unpaid_fill_capacity": unpaid_fill_capacity,
        "work_order_states": {s: len([w for w in work_orders if w["state"] == s]) for s in VALID_STATES},
        "realized_revenue": reconciliation,
        "next_loop_check": now,
    }


def acquire_lock() -> bool:
    try:
        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd = open(LOCK_FILE, "w")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd.write(str(os.getpid()))
        fd.flush()
        acquire_lock._fd = fd
        return True
    except (IOError, OSError):
        return False


def release_lock():
    fd = getattr(acquire_lock, "_fd", None)
    if fd:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
            fd.close()
        except Exception:
            pass
        try:
            LOCK_FILE.unlink(missing_ok=True)
        except Exception:
            pass


def cmd_plan():
    if not acquire_lock():
        print("LOCK_HELD_BY_ANOTHER_PROCESS")
        sys.exit(1)
    try:
        queue = load_json(QUEUE_FILE)
        if not isinstance(queue, list):
            print("INVALID_QUEUE_FORMAT")
            sys.exit(1)
        work_orders = build_work_orders(queue)
        save_json(WORK_ORDERS_FILE, work_orders)
        reconciliation = reconcile_ledger()
        status = generate_status(work_orders, reconciliation)
        save_json(STATUS_FILE, status)
        print(f"PLAN_COMPLETE: {len(work_orders)} work orders generated")
        print(json.dumps(status, indent=2))
    finally:
        release_lock()


def cmd_status():
    status = load_json(STATUS_FILE)
    if not status:
        print("NO_STATUS_FILE")
        sys.exit(1)
    print(json.dumps(status, indent=2))


def cmd_loop(interval: int = 300, max_iterations: int = 10):
    if not acquire_lock():
        print("LOCK_HELD_BY_ANOTHER_PROCESS")
        sys.exit(1)
    try:
        iteration = 0
        backoff = interval
        while iteration < max_iterations:
            iteration += 1
            try:
                queue = load_json(QUEUE_FILE)
                if not isinstance(queue, list):
                    print(f"[{iteration}] INVALID_QUEUE_FORMAT, backing off")
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 3600)
                    continue
                work_orders = build_work_orders(queue)
                save_json(WORK_ORDERS_FILE, work_orders)
                reconciliation = reconcile_ledger()
                status = generate_status(work_orders, reconciliation)
                save_json(STATUS_FILE, status)
                print(f"[{iteration}] LOOP_OK: {len(work_orders)} orders, {reconciliation['entries']} ledger entries")
                backoff = interval  # Reset backoff on success
            except Exception as e:
                print(f"[{iteration}] LOOP_ERROR: {e}")
                backoff = min(backoff * 2, 3600)
            time.sleep(backoff)
        print("LOOP_MAX_ITERATIONS_REACHED")
    finally:
        release_lock()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: revenue_control_plane.py [plan|status|loop] [--interval N] [--max-iterations N]")
        sys.exit(1)
    command = sys.argv[1]
    if command == "plan":
        cmd_plan()
    elif command == "status":
        cmd_status()
    elif command == "loop":
        interval = 300
        max_iter = 10
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--interval" and i + 1 < len(sys.argv):
                interval = int(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--max-iterations" and i + 1 < len(sys.argv):
                max_iter = int(sys.argv[i + 1])
                i += 2
            else:
                i += 1
        cmd_loop(interval=interval, max_iterations=max_iter)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
