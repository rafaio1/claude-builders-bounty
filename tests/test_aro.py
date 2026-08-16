from __future__ import annotations

from pathlib import Path

from agentic.aro.config import AroConfig
from agentic.aro.constitution import (
    OWNER_SHARE_RATE,
    constitution_intact,
    patch_weakens_constitution,
    required_markers,
)
from agentic.aro.cycle import run_cycle
from agentic.aro.store import read_jsonl
from agentic.improve import apply_files, is_allowed_path


def _aro_md() -> str:
    return "\n".join(required_markers()) + "\n"


def _config(**overrides) -> AroConfig:
    base = dict(
        owner_name="",
        business_name="",
        jurisdiction="Brasil",
        base_currency="BRL",
        owner_share_rate=0.20,
        owner_share_base="NET_COLLECTED_CASH",
        payout_interval="WEEKLY",
        minimum_payout="",
        initial_operating_budget="",
        max_single_expense="",
        max_daily_expense="",
        minimum_cash_reserve="",
        payout_destination_configured=False,
        commercial_outbound=False,
        price_floor_brl="250",
        stop_all=False,
    )
    base.update(overrides)
    return AroConfig(**base)


def test_share_rate_immutable() -> None:
    assert OWNER_SHARE_RATE == 0.20


def test_cycle_seeds_offers_without_outbound(tmp_path: Path) -> None:
    (tmp_path / "ARO.md").write_text(_aro_md(), encoding="utf-8")
    report = run_cycle(tmp_path, ghostcli=True, bybit=True, config=_config())
    assert report["constitution_ok"] is True
    assert report["ready_for_outbound"] is False
    assert report["accounts"]["bybit"]["authorized_for_aro_sales"] is False
    assert len(report["offers"]) == 3
    assert (tmp_path / "data" / "aro" / "ledger.jsonl").is_file()
    journal = read_jsonl(tmp_path, "journal.jsonl")
    assert journal
    assert report["decision"]["action"] == "observe_and_record"


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
