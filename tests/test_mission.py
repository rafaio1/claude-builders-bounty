from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from agentic.aro.config import AroConfig
from agentic.aro.finance import ledger_totals, record_collect
from agentic.aro.mission import maybe_milestone_payout, mission_plan, milestone_brl
from agentic.aro.policy import full_autonomy_authorized, operating_policy
from agentic.aro.store import read_jsonl


def _cfg(**overrides) -> AroConfig:
    base = dict(
        owner_name="Owner",
        business_name="Biz",
        jurisdiction="Brasil",
        base_currency="BRL",
        owner_share_rate=0.20,
        owner_share_base="NET_COLLECTED_CASH",
        payout_interval="WEEKLY",
        minimum_payout="50",
        initial_operating_budget="50",
        max_single_expense="50",
        max_daily_expense="50",
        minimum_cash_reserve="50",
        payout_destination_configured=True,
        commercial_outbound=True,
        wise_configured=True,
        payout_channel="wise",
        may_open_receive_accounts=True,
        base_limit_brl="50",
        price_floor_brl="250",
        p2p_authorized=True,
        stop_all=False,
    )
    base.update(overrides)
    return AroConfig(**base)


def test_policy_licit_and_no_impersonation() -> None:
    pol = operating_policy(_cfg())
    assert pol["licit_revenue_only"] is True
    assert pol["jurisdiction"] == "Brasil"
    assert any("imperson" in f for f in pol["forbidden"])


def test_mission_plan_shows_milestone(tmp_path: Path) -> None:
    (tmp_path / "data" / "aro").mkdir(parents=True)
    plan = mission_plan(tmp_path, payout_dest_ok=True)
    assert plan["owner_share_rate"] == 0.20
    assert plan["milestone_brl"] == "1000.00"
    assert plan["milestone_reached"] is False


def test_milestone_payout_at_1000(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "data" / "aro").mkdir(parents=True)
    record_collect(tmp_path, "1000.00", source="test")
    result = maybe_milestone_payout(tmp_path, _cfg())
    assert result["action"] == "milestone_payout_recorded"
    assert result["amount"] == "500.00"
    totals = ledger_totals(read_jsonl(tmp_path, "ledger.jsonl"))
    assert totals["owner_paid"] == Decimal("500.00")


def test_full_autonomy_flag(monkeypatch) -> None:
    monkeypatch.setenv("ARO_FULL_AUTONOMY", "1")
    assert full_autonomy_authorized() is True
