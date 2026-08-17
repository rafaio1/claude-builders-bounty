"""Owner mission: 20% profit share, reinvest the rest, milestone at 1000 BRL (half to owner)."""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

from agentic.aro.constitution import OWNER_SHARE_RATE
from agentic.aro.finance import BASE_LIMIT, _dec, _money, ledger_totals, record_owner_payout, snapshot
from agentic.aro.store import append_jsonl, read_jsonl, utcnow

STATE_FILE = "milestone-state.json"
DEFAULT_MILESTONE_BRL = Decimal("1000.00")
DEFAULT_MILESTONE_OWNER_SHARE = Decimal("0.50")
REINVEST_SHARE = Decimal("1.00") - Decimal(str(OWNER_SHARE_RATE))


def _strip(value: str | None) -> str:
    return (value or "").strip().strip('"').strip("'")


def milestone_brl() -> Decimal:
    return _dec(os.getenv("ARO_MILESTONE_BRL") or "1000")


def milestone_owner_share() -> Decimal:
    return _dec(os.getenv("ARO_MILESTONE_OWNER_SHARE") or "0.50")


def _state_path(root: Path) -> Path:
    return Path(root) / "data" / "aro" / STATE_FILE


def load_milestone_state(root: Path) -> dict[str, Any]:
    path = _state_path(root)
    if not path.is_file():
        return {"milestone_paid": False, "paid_amount": "0.00"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"milestone_paid": False, "paid_amount": "0.00"}
    return data if isinstance(data, dict) else {"milestone_paid": False}


def save_milestone_state(root: Path, state: dict[str, Any]) -> None:
    path = _state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = utcnow()
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mission_plan(root: Path, *, base: Decimal = BASE_LIMIT, payout_dest_ok: bool = True) -> dict[str, Any]:
    """Describe reinvest vs owner share and milestone progress."""
    totals = ledger_totals(read_jsonl(root, "ledger.jsonl"))
    cash = totals["cash"]
    milestone = milestone_brl()
    mshare = milestone_owner_share()
    state = load_milestone_state(root)
    fin = snapshot(root, payout_dest_ok=payout_dest_ok, base=base)
    reached = cash >= milestone
    milestone_amount = (milestone * mshare).quantize(Decimal("0.01"))
    return {
        "mission": "20% lucro ao owner; resto reinveste para crescer capital",
        "owner_share_rate": float(OWNER_SHARE_RATE),
        "reinvest_share_rate": float(REINVEST_SHARE),
        "cash_brl": _money(cash),
        "collected_brl": _money(totals["collected"]),
        "milestone_brl": _money(milestone),
        "milestone_owner_share": float(mshare),
        "milestone_reached": reached,
        "milestone_paid": bool(state.get("milestone_paid")),
        "milestone_payout_due_brl": _money(milestone_amount) if reached and not state.get("milestone_paid") else "0.00",
        "weekly_accrual_brl": fin.get("owner_accrual"),
        "reinvest_budget_brl": _money(cash * REINVEST_SHARE if cash > 0 else Decimal("0")),
        "strategy": (
            "Micro-ofertas + Wise + P2P (Wise paga) + carteira crypto; "
            f"ao atingir R$ {_money(milestone)} owner recebe {_money(milestone_amount)} (metade); "
            "semanalmente 20% do lucro líquido."
        ),
    }


def maybe_milestone_payout(root: Path, config, *, live: bool = False) -> dict[str, Any]:
    """When cash ≥ milestone BRL, pay half of milestone to owner (once)."""
    from agentic.aro.config import AroConfig

    if not isinstance(config, AroConfig):
        return {"ok": False, "action": "skipped"}
    totals = ledger_totals(read_jsonl(root, "ledger.jsonl"))
    cash = totals["cash"]
    milestone = milestone_brl()
    state = load_milestone_state(root)
    if state.get("milestone_paid"):
        return {"ok": True, "action": "milestone_already_paid", "paid_amount": state.get("paid_amount")}
    if cash < milestone:
        return {
            "ok": True,
            "action": "milestone_pending",
            "cash_brl": _money(cash),
            "need_brl": _money(milestone),
            "remaining_brl": _money(milestone - cash),
        }
    amount = (milestone * milestone_owner_share()).quantize(Decimal("0.01"))
    if amount <= 0:
        return {"ok": False, "action": "milestone_zero"}
    if amount > cash:
        amount = cash
    live_flag = live and os.getenv("ARO_WISE_PAYOUT_LIVE") == "1"
    row = record_owner_payout(
        root,
        amount,
        channel=config.payout_channel,
        reference="milestone_1000_half_owner",
        live=live_flag,
    )
    save_milestone_state(
        root,
        {"milestone_paid": True, "paid_amount": _money(amount), "paid_at": utcnow(), "hash": row.get("hash")},
    )
    append_jsonl(
        root,
        "journal.jsonl",
        {"kind": "milestone_payout", "amount": _money(amount), "live": live_flag, "hash": row.get("hash")},
    )
    return {
        "ok": True,
        "action": "milestone_payout_recorded",
        "amount": _money(amount),
        "live": live_flag,
        "hash": row.get("hash"),
        "note": f"Metade de R$ {_money(milestone)} ao owner; restante reinveste.",
    }
