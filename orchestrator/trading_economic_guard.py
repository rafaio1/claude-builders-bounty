"""Pure, fail-closed promotion gate for the real Bybit spot executor.

Importing this module performs no filesystem or network I/O.  Call
``evaluate_live_trading`` immediately before constructing an exchange client.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

DEFAULT_RECONCILIATION_STATE = Path("/Agentic/orchestrator/reconciliation_state.json")
MIN_PAPER_TRADES = 200
MIN_PAPER_DAYS = 30
PROMOTION_MAX_AGE_SECONDS = 24 * 60 * 60
REQUIRED_PROMOTION_GATES = (
    "backtest_passed",
    "oos_passed",
    "paper_passed",
    "economics_passed",
    "inventory_reconciled",
)


@dataclass(frozen=True)
class GuardDecision:
    allowed: bool
    reasons: tuple[str, ...]


class TradingEconomicGuardError(RuntimeError):
    def __init__(self, decision: GuardDecision) -> None:
        self.decision = decision
        super().__init__(";".join(decision.reasons))


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _read_state(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, "state.not_found"
    except OSError:
        return None, "state.unreadable"
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None, "state.invalid_json"
    if not isinstance(payload, dict):
        return None, "state.root_not_object"
    return payload, None


def evaluate_live_trading(
    *,
    env: Mapping[str, str] | None = None,
    state_path: str | Path = DEFAULT_RECONCILIATION_STATE,
    now: datetime | None = None,
    exchange_name: str = "bybit",
) -> GuardDecision:
    """Return a deterministic decision; every missing assertion is a denial."""
    values = os.environ if env is None else env
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    reasons: list[str] = []

    if exchange_name.strip().lower() != "bybit":
        reasons.append("exchange.unsupported")
    if str(values.get("BYBIT_SPOT_LIVE_ENABLED", "")).strip().lower() != "true":
        reasons.append("env.bybit_spot_live_enabled_required")
    if str(values.get("AGENTIC_LIVE_TRADE", "")).strip() != "1":
        reasons.append("env.agentic_live_trade_required")

    state, state_error = _read_state(Path(state_path))
    if state_error is not None:
        reasons.append(state_error)
        return GuardDecision(False, tuple(reasons))
    assert state is not None

    if state.get("real_trading_blocked") is not False:
        reasons.append("state.real_trading_blocked_not_false")

    paper = state.get("paper_validation")
    if not isinstance(paper, dict):
        reasons.append("paper.validation_missing")
    else:
        trades = paper.get("trades")
        days = paper.get("days")
        if not _finite_number(trades) or float(trades) < MIN_PAPER_TRADES:
            reasons.append("paper.trades_below_200")
        if not _finite_number(days) or float(days) < MIN_PAPER_DAYS:
            reasons.append("paper.days_below_30")

    backtest = state.get("backtest_validation")
    if not isinstance(backtest, dict):
        reasons.append("backtest.missing")
    elif backtest.get("passed") is not True:
        reasons.append("backtest.not_passed")

    oos = state.get("oos_validation")
    if not isinstance(oos, dict):
        reasons.append("oos.missing")
    elif oos.get("passed") is not True:
        reasons.append("oos.not_passed")

    gates = state.get("promotion_gates")
    if not isinstance(gates, dict):
        reasons.append("gates.missing")
    else:
        for gate in REQUIRED_PROMOTION_GATES:
            if gates.get(gate) is not True:
                reasons.append(f"gates.{gate}_not_true")

    economics = state.get("economics")
    if not isinstance(economics, dict):
        reasons.append("economics.missing")
    else:
        if economics.get("known") is not True:
            reasons.append("economics.known_not_true")
        monthly_cost = economics.get("monthly_cost_usd")
        if not _finite_number(monthly_cost) or float(monthly_cost) < 0:
            reasons.append("economics.monthly_cost_usd_unknown")
        expected_net = economics.get("expected_monthly_net_usd")
        if not _finite_number(expected_net):
            reasons.append("economics.expected_monthly_net_usd_unknown")
        elif float(expected_net) <= 0:
            reasons.append("economics.expected_monthly_net_usd_not_positive")

    inventory = state.get("inventory_reconciliation")
    if not isinstance(inventory, dict):
        reasons.append("inventory.missing")
    else:
        if inventory.get("reconciled") is not True:
            reasons.append("inventory.reconciled_not_true")
        for key in ("unknown_assets_count", "open_order_mismatches", "unmatched_fills"):
            value = inventory.get(key)
            if not _finite_number(value) or float(value) != 0:
                reasons.append(f"inventory.{key}_not_zero")

    manifest = state.get("promotion_manifest")
    if not isinstance(manifest, dict):
        reasons.append("promotion_manifest.missing")
    else:
        if manifest.get("approved") is not True:
            reasons.append("promotion_manifest.approved_not_true")
        generated_at = _parse_timestamp(manifest.get("generated_at"))
        expires_at = _parse_timestamp(manifest.get("expires_at"))
        if generated_at is None:
            reasons.append("promotion_manifest.generated_at_invalid")
        else:
            age = (current - generated_at).total_seconds()
            if age < -300:
                reasons.append("promotion_manifest.generated_at_in_future")
            elif age > PROMOTION_MAX_AGE_SECONDS:
                reasons.append("promotion_manifest.stale")
        if expires_at is None:
            reasons.append("promotion_manifest.expires_at_invalid")
        elif current >= expires_at:
            reasons.append("promotion_manifest.expired")

    return GuardDecision(not reasons, tuple(reasons))


def require_live_trading(**kwargs: Any) -> GuardDecision:
    decision = evaluate_live_trading(**kwargs)
    if not decision.allowed:
        raise TradingEconomicGuardError(decision)
    return decision
