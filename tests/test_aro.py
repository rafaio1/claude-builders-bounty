from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from agentic.aro.commerce import create_contract, deliver_contract, publish_offer, run_operate
from agentic.aro.config import AroConfig
from agentic.aro.constitution import OWNER_SHARE_RATE, constitution_intact, patch_weakens_constitution, required_markers
from agentic.aro.cycle import process_owner_inbox, run_cycle
from agentic.aro.finance import ledger_totals, record_collect, scaled_limits
from agentic.aro.store import read_jsonl
from agentic.improve import apply_files, is_allowed_path


def _aro_md() -> str:
    return "\n".join(required_markers()) + "\n"


def _config(**overrides) -> AroConfig:
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


def test_limits_start_at_50_and_grow_with_cash() -> None:
    empty = scaled_limits(cash=Decimal("0"))
    assert empty["max_single_expense"] == Decimal("0.00")
    assert empty["minimum_payout"] == Decimal("50.00")
    grown = scaled_limits(cash=Decimal("1000.00"))
    assert grown["operating_budget"] > Decimal("50.00")
    assert grown["spendable"] > Decimal("50.00")


def test_cycle_seeds_offers_without_outbound(tmp_path: Path) -> None:
    (tmp_path / "ARO.md").write_text(_aro_md(), encoding="utf-8")
    report = run_cycle(tmp_path, ghostcli=True, bybit=True, config=_config(commercial_outbound=False))
    assert report["constitution_ok"] is True
    assert report["ready_for_outbound"] is False
    assert report["accounts"]["bybit"]["authorized_for_aro_sales"] is False
    assert len(report["offers"]) == 3
    assert (tmp_path / "data" / "aro" / "ledger.jsonl").is_file()
    journal = read_jsonl(tmp_path, "journal.jsonl")
    assert journal


def test_commerce_publish_and_contract(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "ARO.md").write_text(_aro_md(), encoding="utf-8")
    cfg = _config()
    from agentic.aro.offers import seed_offers

    seed_offers(tmp_path, cfg)
    monkeypatch.setattr(
        "agentic.aro.commerce.wise_mod.receive_catalog",
        lambda: [{"currency": "BRL", "title": "Local", "methods": ["PIX"], "note": ""}],
    )
    pub = publish_offer(tmp_path, "offer-bugfix-api", cfg)
    assert pub["ok"] is True
    assert (tmp_path / "data" / "aro" / "public" / "catalog.json").is_file()
    ctr = create_contract(
        tmp_path,
        offer_id="offer-bugfix-api",
        client_ref="cliente-teste",
        amount_brl="250.00",
        config=cfg,
    )
    assert ctr["status"] == "awaiting_payment"
    record_collect(tmp_path, "250.00", contract_id=ctr["id"], source="test")
    ctr["status"] = "paid"
    from agentic.aro.store import upsert_named

    upsert_named(tmp_path, "contracts.json", ctr)
    delivered = deliver_contract(tmp_path, ctr["id"], evidence="patch ok")
    assert delivered["status"] == "delivered"
    totals = ledger_totals(read_jsonl(tmp_path, "ledger.jsonl"))
    assert totals["collected"] == Decimal("250.00")
    assert totals["owner_accrual"] == Decimal("50.00")


def test_operate_skips_wise_when_not_configured(tmp_path: Path) -> None:
    (tmp_path / "ARO.md").write_text(_aro_md(), encoding="utf-8")
    cfg = _config(wise_configured=False, commercial_outbound=False)
    result = run_operate(tmp_path, cfg)
    assert result["ok"] is False


def test_stop_pauses_cycle(tmp_path: Path) -> None:
    (tmp_path / "ARO.md").write_text(_aro_md(), encoding="utf-8")
    (tmp_path / ".agentic-aro.stop").write_text("STOP_ALL_OPERATIONS\n", encoding="utf-8")
    report = run_cycle(tmp_path, config=_config(stop_all=True))
    assert report["paused"] is True
    assert report["decision"]["action"] == "pause"


def test_cycle_rejects_live_trade(tmp_path: Path) -> None:
    (tmp_path / "ARO.md").write_text(_aro_md(), encoding="utf-8")
    try:
        run_cycle(tmp_path, live_trade=True, config=_config())
    except RuntimeError as exc:
        assert "LIVE_TRADE" in str(exc)
    else:
        raise AssertionError("deveria recusar trade live")


def test_patch_cannot_weaken_constitution() -> None:
    reason = patch_weakens_constitution("ARO.md", "texto sem regras")
    assert reason
    assert patch_weakens_constitution("src/agentic/loop.py", "x") is None


def test_apply_files_rejects_weakened_aro(tmp_path: Path) -> None:
    (tmp_path / "ARO.md").write_text(_aro_md(), encoding="utf-8")
    assert is_allowed_path("ARO.md")
    try:
        apply_files(tmp_path, [{"path": "ARO.md", "content": "sem constituição\n"}])
    except ValueError as exc:
        assert "constituição" in str(exc) or "enfraquecida" in str(exc)
    else:
        raise AssertionError("deveria recusar ARO.md enfraquecido")


def test_constitution_intact_on_markers(tmp_path: Path) -> None:
    (tmp_path / "ARO.md").write_text(_aro_md(), encoding="utf-8")
    ok, _detail = constitution_intact(tmp_path)
    assert ok is True


def test_owner_inbox_gets_agent_reply(tmp_path: Path) -> None:
    (tmp_path / "ARO.md").write_text(_aro_md(), encoding="utf-8")
    inbox = tmp_path / "inbox.jsonl"
    inbox.write_text(
        '{"id": "note-abc-1234", "role": "owner", "body": "qual o status?",'
        ' "at": "2026-08-16T14:00:00+00:00"}\n',
        encoding="utf-8",
    )
    replies = process_owner_inbox(tmp_path, inbox=inbox, paused=False)
    assert len(replies) == 1
    assert "Mensagem recebida" in replies[0]["body"]
    again = process_owner_inbox(tmp_path, inbox=inbox, paused=False)
    assert again == []


def test_share_rate_immutable() -> None:
    assert OWNER_SHARE_RATE == 0.20
