from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ORCHESTRATOR = Path("/Agentic/orchestrator")
if str(ORCHESTRATOR) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR))

from trading_economic_guard import (  # noqa: E402
    TradingEconomicGuardError,
    evaluate_live_trading,
    require_live_trading,
)

NOW = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
LIVE_ENV = {
    "BYBIT_SPOT_LIVE_ENABLED": "true",
    "AGENTIC_LIVE_TRADE": "1",
}


def valid_state() -> dict[str, object]:
    return {
        "real_trading_blocked": False,
        "paper_validation": {"trades": 200, "days": 30},
        "backtest_validation": {"passed": True},
        "oos_validation": {"passed": True},
        "promotion_gates": {
            "backtest_passed": True,
            "oos_passed": True,
            "paper_passed": True,
            "economics_passed": True,
            "inventory_reconciled": True,
        },
        "economics": {
            "known": True,
            "monthly_cost_usd": 25.0,
            "expected_monthly_net_usd": 1.0,
        },
        "inventory_reconciliation": {
            "reconciled": True,
            "unknown_assets_count": 0,
            "open_order_mismatches": 0,
            "unmatched_fills": 0,
        },
        "promotion_manifest": {
            "approved": True,
            "generated_at": (NOW - timedelta(hours=1)).isoformat(),
            "expires_at": (NOW + timedelta(hours=1)).isoformat(),
        },
    }


def write_state(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "reconciliation_state.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def decision(tmp_path: Path, payload: object, *, env=None, now=NOW):
    return evaluate_live_trading(
        env=LIVE_ENV if env is None else env,
        state_path=write_state(tmp_path, payload),
        now=now,
        exchange_name="bybit",
    )


def test_valid_complete_evidence_allows_live(tmp_path: Path) -> None:
    result = decision(tmp_path, valid_state())
    assert result.allowed is True
    assert result.reasons == ()


def test_default_deny_requires_both_explicit_flags(tmp_path: Path) -> None:
    result = decision(tmp_path, valid_state(), env={})
    assert result.allowed is False
    assert result.reasons == (
        "env.bybit_spot_live_enabled_required",
        "env.agentic_live_trade_required",
    )


@pytest.mark.parametrize("blocked", [True, None, "false", 0])
def test_real_trading_blocked_must_be_literal_false(tmp_path: Path, blocked) -> None:
    state = valid_state()
    state["real_trading_blocked"] = blocked
    result = decision(tmp_path, state)
    assert "state.real_trading_blocked_not_false" in result.reasons


@pytest.mark.parametrize(
    ("trades", "days", "reason"),
    [
        (199, 30, "paper.trades_below_200"),
        (200, 29.99, "paper.days_below_30"),
    ],
)
def test_paper_minimums_are_hard_gates(tmp_path: Path, trades, days, reason) -> None:
    state = valid_state()
    state["paper_validation"] = {"trades": trades, "days": days}
    assert reason in decision(tmp_path, state).reasons


@pytest.mark.parametrize(
    ("section", "reason"),
    [
        ("backtest_validation", "backtest.missing"),
        ("oos_validation", "oos.missing"),
        ("promotion_gates", "gates.missing"),
    ],
)
def test_missing_validation_sections_block(tmp_path: Path, section, reason) -> None:
    state = valid_state()
    del state[section]
    assert reason in decision(tmp_path, state).reasons


def test_every_named_promotion_gate_is_required(tmp_path: Path) -> None:
    state = valid_state()
    state["promotion_gates"]["oos_passed"] = False
    result = decision(tmp_path, state)
    assert "gates.oos_passed_not_true" in result.reasons


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("known", False, "economics.known_not_true"),
        ("monthly_cost_usd", None, "economics.monthly_cost_usd_unknown"),
        (
            "expected_monthly_net_usd",
            None,
            "economics.expected_monthly_net_usd_unknown",
        ),
        (
            "expected_monthly_net_usd",
            0,
            "economics.expected_monthly_net_usd_not_positive",
        ),
    ],
)
def test_unknown_or_non_positive_economics_block(
    tmp_path: Path, field, value, reason
) -> None:
    state = valid_state()
    state["economics"][field] = value
    assert reason in decision(tmp_path, state).reasons


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("reconciled", False, "inventory.reconciled_not_true"),
        ("unknown_assets_count", 1, "inventory.unknown_assets_count_not_zero"),
        ("open_order_mismatches", 1, "inventory.open_order_mismatches_not_zero"),
        ("unmatched_fills", 1, "inventory.unmatched_fills_not_zero"),
    ],
)
def test_unreconciled_inventory_blocks(tmp_path: Path, field, value, reason) -> None:
    state = valid_state()
    state["inventory_reconciliation"][field] = value
    assert reason in decision(tmp_path, state).reasons


def test_stale_promotion_manifest_blocks(tmp_path: Path) -> None:
    state = valid_state()
    state["promotion_manifest"]["generated_at"] = (
        NOW - timedelta(hours=24, seconds=1)
    ).isoformat()
    result = decision(tmp_path, state)
    assert "promotion_manifest.stale" in result.reasons


def test_invalid_state_is_deterministic_and_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "reconciliation_state.json"
    path.write_text("{not json", encoding="utf-8")
    result = evaluate_live_trading(
        env={}, state_path=path, now=NOW, exchange_name="bybit"
    )
    assert result.reasons == (
        "env.bybit_spot_live_enabled_required",
        "env.agentic_live_trade_required",
        "state.invalid_json",
    )


def test_require_raises_with_same_deterministic_reasons(tmp_path: Path) -> None:
    state = valid_state()
    state["real_trading_blocked"] = True
    path = write_state(tmp_path, state)
    with pytest.raises(TradingEconomicGuardError) as caught:
        require_live_trading(
            env=LIVE_ENV, state_path=path, now=NOW, exchange_name="bybit"
        )
    assert caught.value.decision.reasons == (
        "state.real_trading_blocked_not_false",
    )


def test_guard_module_has_no_network_dependency() -> None:
    source = (ORCHESTRATOR / "trading_economic_guard.py").read_text(encoding="utf-8")
    assert "import ccxt" not in source
    assert "import requests" not in source
    assert "urllib" not in source


def test_executor_checks_guard_before_exchange_construction() -> None:
    source = (ORCHESTRATOR / "subagent_trailing_unified.py").read_text(
        encoding="utf-8"
    )
    guard_offset = source.index("evaluate_live_trading(exchange_name=EXCHANGE)")
    bybit_offset = source.index("exchange = ccxt.bybit")
    load_markets_offset = source.index("exchange.load_markets()")
    assert guard_offset < bybit_offset < load_markets_offset
