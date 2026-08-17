"""Cash limits starting at 50 BRL; grow with ledger. Wise is the money rail."""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Any

from agentic.aro.constitution import OWNER_SHARE_RATE
from agentic.aro.store import append_jsonl, read_jsonl

BASE_LIMIT = Decimal("50.00")
OWNER_RATE = Decimal(str(OWNER_SHARE_RATE))


def _dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0").replace(",", ".")).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")


def _money(value: Decimal) -> str:
    quantized = value.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    return f"{quantized:.2f}"


def ledger_totals(rows: list[dict[str, Any]]) -> dict[str, Decimal]:
    collected = Decimal("0.00")
    expenses = Decimal("0.00")
    owner_paid = Decimal("0.00")
    refunds = Decimal("0.00")
    for row in rows:
        amount = _dec(row.get("amount") or row.get("brl") or 0)
        kind = str(row.get("kind") or row.get("type") or "").lower()
        if kind in {"collect", "received", "revenue", "settled"}:
            collected += amount
        elif kind in {"expense", "fee", "tax", "cost"}:
            expenses += amount
        elif kind in {"owner_payout", "payout", "owner_share"}:
            owner_paid += amount
        elif kind in {"refund", "chargeback"}:
            refunds += amount
    net = collected - refunds - expenses
    cash = net - owner_paid
    if cash < 0:
        cash = Decimal("0.00")
    owner_accrual = (collected - refunds) * OWNER_RATE - owner_paid
    if owner_accrual < 0:
        owner_accrual = Decimal("0.00")
    return {
        "collected": collected,
        "expenses": expenses,
        "refunds": refunds,
        "owner_paid": owner_paid,
        "cash": cash,
        "owner_accrual": owner_accrual,
        "net": net if net > 0 else Decimal("0.00"),
    }


def scaled_limits(*, cash: Decimal, base: Decimal = BASE_LIMIT) -> dict[str, Decimal]:
    """Floor 50 BRL; ceiling grows with cash. Never spend more than cash on hand."""
    if base <= 0:
        base = BASE_LIMIT
    operating = cash * (Decimal("1.00") - OWNER_RATE)
    budget = max(base, operating)
    reserve = max(base, cash * OWNER_RATE)
    if cash <= 0:
        return {
            "base": base,
            "operating_budget": base,
            "max_single_expense": Decimal("0.00"),
            "max_daily_expense": Decimal("0.00"),
            "minimum_cash_reserve": base,
            "minimum_payout": base,
            "spendable": Decimal("0.00"),
        }
    spendable = cash - reserve
    if spendable < 0:
        spendable = Decimal("0.00")
    single = min(spendable, max(base, cash * Decimal("0.10")))
    daily = min(spendable, max(base, cash * Decimal("0.20")))
    return {
        "base": base,
        "operating_budget": min(budget, cash),
        "max_single_expense": single,
        "max_daily_expense": daily,
        "minimum_cash_reserve": min(reserve, cash),
        "minimum_payout": base,
        "spendable": spendable,
    }


def snapshot(
    root: Path,
    *,
    payout_dest_ok: bool,
    base: Decimal = BASE_LIMIT,
    channel: str = "wise",
) -> dict[str, Any]:
    totals = ledger_totals(read_jsonl(root, "ledger.jsonl"))
    limits = scaled_limits(cash=totals["cash"], base=base)
    due = totals["owner_accrual"] >= limits["minimum_payout"] and limits["minimum_payout"] > 0
    if totals["owner_accrual"] <= 0:
        due = False
    can_send = bool(due and payout_dest_ok)
    blocked = ""
    if not due:
        blocked = "sem accrual" if totals["owner_accrual"] <= 0 else "abaixo do piso 50 BRL"
    elif not payout_dest_ok:
        blocked = "trilho Wise indisponível"
    return {
        "currency": "BRL",
        "base_limit": _money(limits["base"]),
        "cash": _money(totals["cash"]),
        "collected": _money(totals["collected"]),
        "owner_accrual": _money(totals["owner_accrual"]),
        "owner_paid": _money(totals["owner_paid"]),
        "owner_share_rate": float(OWNER_RATE),
        "limits": {key: _money(val) for key, val in limits.items()},
        "weekly_payout": {
            "channel": channel,
            "interval": "WEEKLY",
            "due": due,
            "amount": _money(totals["owner_accrual"]) if due else "0.00",
            "blocked": "" if can_send else blocked,
            "note": (
                "Participação 20% do lucro líquido, semanal, via Wise. "
                "Reinvestir ~80% para crescer. Milestone R$ 1000: metade ao owner (uma vez)."
            ),
        },
    }


def record_collect(
    root: Path,
    amount: str | Decimal,
    *,
    contract_id: str = "",
    reference: str = "",
    source: str = "wise",
) -> dict[str, Any]:
    return append_jsonl(
        root,
        "ledger.jsonl",
        {
            "kind": "collect",
            "amount": _money(_dec(amount)),
            "currency": "BRL",
            "contract_id": contract_id,
            "reference": reference,
            "source": source,
        },
    )


def record_expense(
    root: Path,
    amount: str | Decimal,
    *,
    reference: str = "",
    source: str = "expense",
) -> dict[str, Any]:
    return append_jsonl(
        root,
        "ledger.jsonl",
        {
            "kind": "expense",
            "amount": _money(_dec(amount)),
            "currency": "BRL",
            "reference": reference,
            "source": source,
        },
    )


def record_owner_payout(
    root: Path,
    amount: str | Decimal,
    *,
    channel: str = "wise",
    reference: str = "",
    live: bool = False,
) -> dict[str, Any]:
    return append_jsonl(
        root,
        "ledger.jsonl",
        {
            "kind": "owner_payout",
            "amount": _money(_dec(amount)),
            "currency": "BRL",
            "channel": channel,
            "reference": reference,
            "live": live,
        },
    )
