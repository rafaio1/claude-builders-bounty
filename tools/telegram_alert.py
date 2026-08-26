#!/usr/bin/env python3
"""Telegram Alert - Financial Events Only (Gate-Enforced)

All notifications now route through src/telegram_gate.py.
Only confirmed, reconciled financial events are sent:
  - payout_received (via send_payment_alert)
  - trade_realized
  - transfer_confirmed

Blocked: bounties submitted, PRs merged (without payout), test messages,
heartbeats, opportunities, paper trades, scans, status reports.

Usage:
    from tools.telegram_alert import send_payment_alert
    send_payment_alert(source="wise", amount=500.0, external_ref="W-12345", net=495.0)
"""
import sys
from pathlib import Path
from typing import Optional

# Add src to path for gate import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

try:
    from telegram_gate import send_financial_event, notify_payout_received, _log as gate_log
except ImportError as e:
    print(f"[FATAL] Cannot import telegram_gate: {e}", flush=True)
    sys.exit(1)


def send_payment_alert(
    source: str,
    amount: float,
    details: str = "",
    external_ref: Optional[str] = None,
    net: Optional[float] = None,
    fees: float = 0.0,
    currency: str = "USD",
    event_id: Optional[str] = None,
    dry_run: bool = False,
) -> bool:
    """Send confirmed payout notification through gate.

    Only call this when payment is actually received and reconciled.
    Never call for pending, expected, or potential payments.
    """
    if net is None:
        net = amount - fees

    if not external_ref:
        gate_log("[BLOCKED] send_payment_alert missing external_ref — cannot verify")
        return False

    if not event_id:
        event_id = f"payout:{source}:{external_ref}:{net}"

    return notify_payout_received(
        process_id=f"payout-{source}",
        source=source,
        external_reference=external_ref,
        gross=float(amount),
        fees=float(fees),
        net=float(net),
        currency=currency,
        event_id=event_id,
        dry_run=dry_run,
    )


# Legacy stubs — silently blocked, logged, return False
def send_alert(*args, **kwargs) -> bool:
    gate_log("[BLOCKED] send_alert called — non-financial alerts disabled")
    return False

def send_message(*args, **kwargs) -> bool:
    gate_log("[BLOCKED] send_message called — direct messaging disabled")
    return False

def send_bounty_alert(*args, **kwargs) -> bool:
    gate_log("[BLOCKED] send_bounty_alert called — bounty submissions not financial events")
    return False

def send_pr_merged_alert(*args, **kwargs) -> bool:
    gate_log("[BLOCKED] send_pr_merged_alert called — PR merge != confirmed payout")
    return False

def setup(*args, **kwargs) -> None:
    gate_log("[BLOCKED] setup called — chat detection disabled under gate policy")
    return None


def _cli():
    import argparse
    p = argparse.ArgumentParser(description="Telegram Financial Alert CLI (Gate-Enforced)")
    p.add_argument("--dry-run", action="store_true", help="Validate without sending")
    p.add_argument("--source", required=True, help="Payment source (wise, bybit, binance)")
    p.add_argument("--amount", type=float, required=True, help="Gross amount received")
    p.add_argument("--net", type=float, help="Net after fees (default: amount)")
    p.add_argument("--fees", type=float, default=0.0, help="Fees deducted")
    p.add_argument("--ref", required=True, help="External reference ID for reconciliation")
    p.add_argument("--currency", default="USD", help="Currency code")
    args = p.parse_args()

    success = send_payment_alert(
        source=args.source,
        amount=args.amount,
        net=args.net,
        fees=args.fees,
        external_ref=args.ref,
        currency=args.currency,
        dry_run=args.dry_run,
    )
    if success:
        print("OK: Financial event sent via gate.")
    else:
        print("BLOCKED: Event rejected by gate (check logs).")
        sys.exit(1)


if __name__ == "__main__":
    _cli()
