from __future__ import annotations

from pathlib import Path

from agentic.aro.accounts import PLATFORMS, provision_platform, run_provision
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


def test_provision_requires_authorization(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "ARO.md").write_text("AUTONOMOUS REVENUE OPERATOR\n", encoding="utf-8")
    monkeypatch.delenv("ARO_OPERATOR_ACCOUNTS_AUTHORIZED", raising=False)
    result = run_provision(tmp_path, _cfg(may_open_receive_accounts=False))
    assert result["ok"] is False


def test_provision_wise_and_mail(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ARO_OPERATOR_ACCOUNTS_AUTHORIZED", "1")
    monkeypatch.setattr("agentic.aro.wise.status", lambda: {"ok": True, "configured": True})
    monkeypatch.setattr(
        "agentic.aro.accounts.mail_mod.status",
        lambda: {"configured": True, "verified": True, "address": "agentic-aro@agentmail.to"},
    )
    monkeypatch.setattr(
        "agentic.aro.accounts.mail_mod.ensure_inbox",
        lambda **kwargs: {"ok": True, "email": "test@agentmail.to", "inbox_id": "test@agentmail.to"},
    )
    monkeypatch.setattr(
        "agentic.aro.accounts._probe_url",
        lambda url: {"ok": False, "status_code": 403, "blocked": True, "reason": "antibot"},
    )
    monkeypatch.setattr(
        "agentic.aro.accounts._register_mql5",
        lambda email: {"ok": False, "reason": "registration_rejected"},
    )
    result = run_provision(tmp_path, _cfg())
    assert result["action"] == "provision"
    assert len(result["active"]) >= 2


def test_workana_marked_antibot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ARO_OPERATOR_ACCOUNTS_AUTHORIZED", "1")
    monkeypatch.setattr(
        "agentic.aro.accounts.mail_mod.ensure_inbox",
        lambda **kwargs: {"ok": True, "email": "w@agentmail.to", "inbox_id": "w@agentmail.to"},
    )
    monkeypatch.setattr(
        "agentic.aro.accounts._probe_url",
        lambda url: {"ok": False, "status_code": 403, "blocked": True, "reason": "antibot"},
    )
    spec = next(p for p in PLATFORMS if p.platform_id == "workana")
    row = provision_platform(tmp_path, _cfg(), spec)
    assert row["status"] == "blocked"
    assert row["probe"]["blocked"] is True
