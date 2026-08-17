from __future__ import annotations

from agentic.aro.opportunities import _classify, run_scout
from agentic.aro.config import AroConfig


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


def test_classify_refuses_holy_grail() -> None:
    result = _classify("Profitable EAs wanted", "")
    assert result["verdict"] == "refuse"
    assert result["refuse"]


def test_classify_fits_debug_job() -> None:
    result = _classify(
        "Experienced MQL5 Coder Wanted — Debug & Go-Live Support",
        "review existing mq5 source code",
    )
    assert result["verdict"] == "strong_fit"
    assert result["offer_map"] == "offer-bugfix-api"


def test_scout_seeds_channels(tmp_path) -> None:
    (tmp_path / "ARO.md").write_text(
        "AUTONOMOUS REVENUE OPERATOR\nOWNER_SHARE_RATE = 0.20\nSTOP_ALL_OPERATIONS\n"
        "Nunca utilize empréstimos\nNão faça spam\n",
        encoding="utf-8",
    )
    report = run_scout(tmp_path, _cfg(), max_jobs=0)
    assert report["ok"] is True
    assert report["channels"] >= 5
