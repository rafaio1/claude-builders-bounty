from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from agentic.aro.config import AroConfig
from agentic.aro.finance import ledger_totals, record_expense
from agentic.aro import p2p as p2p_mod


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


def test_p2p_blocked_without_authorization(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("ARO_P2P_AUTHORIZED", raising=False)
    result = p2p_mod.run_p2p(tmp_path, _cfg(p2p_authorized=False))
    assert result["ok"] is False
    assert result["reason"] == "ARO_P2P_AUTHORIZED=0"


def test_post_ad_dry_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ARO_P2P_AUTHORIZED", "1")
    monkeypatch.delenv("ARO_P2P_LIVE", raising=False)
    monkeypatch.setattr("agentic.aro.p2p.configured", lambda: True)
    result = p2p_mod.post_ad(
        tmp_path,
        _cfg(),
        side="1",
        price="5.50",
        quantity="100",
        min_amount="50",
        max_amount="500",
        payment_ids=["1"],
    )
    assert result["ok"] is True
    assert result["action"] == "dry_run"


def test_sync_ledger_records_finished_orders(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ARO_P2P_AUTHORIZED", "1")

    def fake_orders(**kwargs):
        return {
            "ok": True,
            "items": [
                {"id": "ord-1", "status": 50, "side": 1, "amount": "100.00", "currencyId": "BRL"},
                {"id": "ord-2", "status": 50, "side": 0, "amount": "30.00", "currencyId": "BRL"},
            ],
        }

    monkeypatch.setattr("agentic.aro.p2p.list_orders", fake_orders)
    sync = p2p_mod.sync_ledger(tmp_path, _cfg())
    assert sync["ok"] is True
    assert len(sync["recorded"]) == 2
    totals = ledger_totals(__import__("agentic.aro.store", fromlist=["read_jsonl"]).read_jsonl(tmp_path, "ledger.jsonl"))
    assert totals["collected"] == Decimal("100.00")
    assert totals["expenses"] == Decimal("30.00")
    sync2 = p2p_mod.sync_ledger(tmp_path, _cfg())
    assert sync2["recorded"] == []


def test_record_expense() -> None:
    from agentic.aro.store import read_jsonl

    root = Path("/tmp/aro-p2p-test-expense")
    root.mkdir(parents=True, exist_ok=True)
    data = root / "data" / "aro"
    data.mkdir(parents=True, exist_ok=True)
    record_expense(root, "25.00", reference="test", source="bybit_p2p_buy")
    rows = read_jsonl(root, "ledger.jsonl")
    assert rows[-1]["kind"] == "expense"
    assert rows[-1]["amount"] == "25.00"
