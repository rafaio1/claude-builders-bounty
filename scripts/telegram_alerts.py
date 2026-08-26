#!/usr/bin/env python3
"""Telegram Alerts Script - Financial Events Only (Gate-Enforced)

This script previously sent bounty merge/rejection notifications directly.
Now ALL notifications route through src/telegram_gate.py.

ONLY confirmed payout events with external reconciliation are sent.
Blocked: bounty_merged (without payout), bounty_rejected, summaries,
test messages, heartbeats, opportunities, paper trades.

Usage:
  python3 scripts/telegram_alerts.py --dry-run  # Validate without sending
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add src to path for gate import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

try:
    from telegram_gate import notify_payout_received, _log as gate_log
except ImportError as e:
    print(f"[FATAL] Cannot import telegram_gate: {e}", flush=True)
    sys.exit(1)

NOTIFICATIONS_PATH = Path("/Agentic/logs/bounty/notifications.json")
SENT_LOG_PATH = Path("/Agentic/logs/bounty/telegram_sent.json")


def load_sent_log():
    """Load IDs of already-sent financial events."""
    if not SENT_LOG_PATH.exists():
        return set()
    try:
        with open(SENT_LOG_PATH, "r") as f:
            data = json.load(f)
        return set(data.get("sent_keys", []))
    except Exception:
        return set()


def save_sent_log(sent_keys: set):
    """Persist sent event IDs."""
    SENT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    trimmed = sorted(list(sent_keys))[-5000:]
    with open(SENT_LOG_PATH, "w") as f:
        json.dump({"sent_keys": trimmed}, f, indent=2)


def process_confirmed_payouts(dry_run: bool = False) -> int:
    """Process only confirmed payout notifications through gate.

    Returns count of successfully sent events.
    """
    if not NOTIFICATIONS_PATH.exists():
        print("No notifications file found.")
        return 0

    try:
        with open(NOTIFICATIONS_PATH, "r") as f:
            notifications = json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to load notifications: {e}")
        return 0

    sent_keys = load_sent_log()
    sent_count = 0

    for n in notifications:
        ntype = n.get("type", "")

        # ONLY process confirmed payouts — block everything else
        if ntype != "payout_confirmed":
            if ntype in ("bounty_merged", "bounty_rejected"):
                gate_log(f"[BLOCKED] {ntype} notification skipped — not confirmed payout")
            continue

        # Generate deterministic event_id
        source = n.get("source", "unknown")
        ref = n.get("external_reference", n.get("tx_id", ""))
        net = float(n.get("net_amount", n.get("amount", 0)))
        ts = n.get("timestamp", "")
        event_id = f"payout:{source}:{ref}:{net}"

        if event_id in sent_keys:
            continue

        if not ref:
            gate_log(f"[BLOCKED] payout missing external_reference: {n.get('repo', 'unknown')}")
            continue

        if net <= 0:
            gate_log(f"[BLOCKED] payout net<=0: {net}")
            continue

        success = notify_payout_received(
            process_id=f"bounty-{n.get('repo', 'unknown')}",
            source=source,
            external_reference=ref,
            gross=float(n.get("gross_amount", net)),
            fees=float(n.get("fees", 0)),
            net=net,
            currency=n.get("currency", "USD"),
            event_id=event_id,
            dry_run=dry_run,
        )

        if success:
            sent_keys.add(event_id)
            sent_count += 1
            print(f"  ✅ Payout confirmed: {source} {ref} net={net:+.2f}")
        else:
            print(f"  ❌ Payout rejected by gate: {source} {ref}")

    if sent_count > 0:
        save_sent_log(sent_keys)

    return sent_count


def main():
    dry_run = "--dry-run" in sys.argv

    if "--test" in sys.argv:
        print("[BLOCKED] Test messages disabled under financial-only gate policy.")
        print("Use --dry-run to validate confirmed payout processing.")
        return

    mode = "DRY-RUN" if dry_run else "LIVE"
    print(f"[{mode}] Processing confirmed payouts via financial gate...")

    sent = process_confirmed_payouts(dry_run=dry_run)
    print(f"\nSent: {sent} confirmed payout(s)")


if __name__ == "__main__":
    main()
