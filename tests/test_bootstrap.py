from __future__ import annotations

from pathlib import Path

from agentic.aro.bootstrap import micro_floor_brl, publish_micro_offers, run_bootstrap, seed_micro_offers
from agentic.aro.config import AroConfig
from agentic.aro.commerce import publish_offer
from agentic.aro.store import list_named


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
        p2p_authorized=False,
        stop_all=False,
    )
    base.update(overrides)
    return AroConfig(**base)


def test_micro_floor_defaults_low() -> None:
    assert micro_floor_brl(_cfg()) == "10"


def test_seed_micro_offers(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ARO_MICRO_FLOOR_BRL", "10")
    offers = seed_micro_offers(tmp_path, _cfg())
    micro = [o for o in offers if str(o.get("tier")) == "bootstrap"]
    assert len(micro) >= 3
    assert all(str(o.get("price_floor")) == "10" for o in micro if o.get("id", "").startswith("offer-micro"))


def test_publish_micro_below_premium_floor(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ARO_MICRO_FLOOR_BRL", "10")
    seed_micro_offers(tmp_path, _cfg())
    monkeypatch.setattr(
        "agentic.aro.commerce.wise_mod.receive_catalog",
        lambda: [],
    )
    result = publish_offer(tmp_path, "offer-micro-question", _cfg())
    assert result["ok"] is True
    row = next(o for o in list_named(tmp_path, "offers.json") if o["id"] == "offer-micro-question")
    assert row["status"] == "published"


def test_bootstrap_disabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ARO_BOOTSTRAP_MODE", "0")
    result = run_bootstrap(tmp_path, _cfg())
    assert result["ok"] is False
