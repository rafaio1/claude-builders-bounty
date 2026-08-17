"""Commercial flow: publish → contract → Wise payment → delivery → owner payout."""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

from agentic.aro.config import AroConfig
from agentic.aro.finance import BASE_LIMIT, record_collect, record_owner_payout, snapshot
from agentic.aro.offers import seed_offers
from agentic.aro.store import append_jsonl, list_named, read_jsonl, upsert_named, utcnow
from agentic.aro import wise as wise_mod

DEFAULT_OFFER = "offer-bugfix-api"
STATE_FILE = "wise-state.json"
CATALOG_FILE = "public/catalog.json"


def _dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0").replace(",", ".")).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")


def _load_state(root: Path) -> dict[str, Any]:
    path = Path(root) / "data" / "aro" / STATE_FILE
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_state(root: Path, state: dict[str, Any]) -> None:
    path = Path(root) / "data" / "aro" / STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = utcnow()
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_catalog(root: Path, offers: list[dict[str, Any]], receive: list[dict[str, Any]]) -> Path:
    path = Path(root) / "data" / "aro" / CATALOG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    published = [
        {
            "id": item.get("id"),
            "title": item.get("title"),
            "scope": item.get("scope"),
            "price_floor": item.get("price_floor"),
            "currency": item.get("currency"),
            "delivery_days": item.get("delivery_days"),
            "acceptance": item.get("acceptance"),
            "tier": item.get("tier"),
        }
        for item in offers
        if str(item.get("status") or "") == "published"
    ]
    payload = {
        "updated_at": utcnow(),
        "offers": published,
        "payment": {
            "rail": "wise",
            "currency": "BRL",
            "receive": receive,
            "contact": "agentic-aro@agentmail.to",
            "note": "Serviço prestado por automação autorizada; divulgação quando exigida.",
            "p2p": {
                "available": os.getenv("ARO_P2P_AUTHORIZED", "0") in {"1", "true", "yes", "on"},
                "platform": "bybit_p2p",
                "token": os.getenv("ARO_P2P_TOKEN") or "USDT",
                "currency": os.getenv("ARO_P2P_CURRENCY") or "BRL",
            },
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def publish_offer(root: Path, offer_id: str, config: AroConfig) -> dict[str, Any]:
    if not config.ready_for_outbound:
        raise RuntimeError("ARO não está ready_for_outbound")
    offers = list_named(root, "offers.json")
    target = next((item for item in offers if str(item.get("id")) == offer_id), None)
    if not target:
        raise ValueError(f"oferta desconhecida: {offer_id}")
    floor = _dec(config.price_floor_brl or target.get("price_floor") or "250")
    price = _dec(target.get("price_floor") or floor)
    if str(target.get("tier") or "") == "bootstrap":
        micro_floor = _dec(os.getenv("ARO_MICRO_FLOOR_BRL") or "10")
        floor = min(floor, micro_floor)
    if price < floor:
        raise ValueError(f"preço abaixo do piso {floor}")
    item = dict(target)
    item["status"] = "published"
    item["authorized_to_publish"] = True
    item["published_at"] = utcnow()
    upsert_named(root, "offers.json", item)
    receive = wise_mod.receive_catalog() if config.wise_configured else []
    catalog_path = _write_catalog(root, list_named(root, "offers.json"), receive)
    row = append_jsonl(
        root,
        "journal.jsonl",
        {
            "kind": "publish",
            "offer_id": offer_id,
            "catalog": str(catalog_path.relative_to(root)),
        },
    )
    return {"ok": True, "offer_id": offer_id, "catalog": str(catalog_path), "journal": row.get("hash")}


def ensure_published(root: Path, config: AroConfig, *, default_offer: str = DEFAULT_OFFER) -> dict[str, Any]:
    from agentic.aro.wallets import public_receive_catalog

    offers = list_named(root, "offers.json")
    if any(str(item.get("status")) == "published" for item in offers):
        receive = wise_mod.receive_catalog() if config.wise_configured else []
        receive = public_receive_catalog(root) or receive
        _write_catalog(root, offers, receive)
        return {"ok": True, "action": "catalog_refreshed"}
    return publish_offer(root, default_offer, config)


def create_contract(
    root: Path,
    *,
    offer_id: str,
    client_ref: str,
    amount_brl: str,
    config: AroConfig,
) -> dict[str, Any]:
    if not config.ready_for_outbound:
        raise RuntimeError("ARO não está ready_for_outbound")
    floor = _dec(config.price_floor_brl or "250")
    amount = _dec(amount_brl)
    micro_floor = _dec(os.getenv("ARO_MICRO_FLOOR_BRL") or "10")
    offer = next((o for o in list_named(root, "offers.json") if str(o.get("id")) == offer_id), None)
    if offer and str(offer.get("tier") or "") == "bootstrap":
        floor = min(floor, micro_floor)
    if amount < floor:
        raise ValueError(f"valor abaixo do piso {floor}")
    ident = f"ctr-{utcnow().replace(':', '').replace('+00:00', 'Z')[:15]}"
    item = {
        "id": ident,
        "offer_id": offer_id,
        "client_ref": client_ref.strip()[:120],
        "amount_brl": f"{amount:.2f}",
        "currency": "BRL",
        "status": "awaiting_payment",
        "created_at": utcnow(),
    }
    upsert_named(root, "contracts.json", item)
    append_jsonl(root, "journal.jsonl", {"kind": "contract", "contract_id": ident, "offer_id": offer_id})
    return item


def _contracts_awaiting_payment(root: Path) -> list[dict[str, Any]]:
    return [
        item
        for item in list_named(root, "contracts.json")
        if str(item.get("status") or "") == "awaiting_payment"
    ]


def sync_wise_payments(root: Path, config: AroConfig) -> dict[str, Any]:
    """Detect BRL balance increases and match awaiting contracts (FIFO)."""
    if not config.wise_configured:
        return {"ok": False, "reason": "Wise não configurado", "matched": []}
    wise_status = wise_mod.status()
    if not wise_status.get("ok"):
        return {"ok": False, "reason": wise_status.get("reason") or "Wise indisponível", "matched": []}
    current = _dec(wise_status.get("brl_balance") or "0")
    state = _load_state(root)
    baseline = _dec(state.get("baseline_brl") or "0")
    last = _dec(state.get("last_brl") or "0")
    if baseline <= 0:
        baseline = current
        last = current
        _save_state(
            root,
            {
                "baseline_brl": str(baseline),
                "last_brl": str(last),
                "note": "baseline inicial; só deltas futuros viram receita",
            },
        )
        return {
            "ok": True,
            "action": "baseline_set",
            "brl_balance": str(current),
            "matched": [],
        }
    delta = current - last
    if delta <= 0:
        _save_state(root, {**state, "last_brl": str(current), "baseline_brl": str(baseline)})
        return {"ok": True, "action": "no_inflow", "brl_balance": str(current), "matched": []}
    pending = _contracts_awaiting_payment(root)
    if not pending:
        _save_state(root, {**state, "last_brl": str(current), "unmatched_delta": str(delta)})
        return {
            "ok": True,
            "action": "inflow_without_contract",
            "delta_brl": str(delta),
            "note": "crie contrato ou registe pagamento manualmente",
            "matched": [],
        }
    matched: list[dict[str, Any]] = []
    remaining = delta
    for contract in pending:
        if remaining <= 0:
            break
        need = _dec(contract.get("amount_brl") or "0")
        if need <= 0 or remaining + Decimal("0.01") < need:
            continue
        ident = str(contract.get("id") or "")
        row = record_collect(
            root,
            need,
            contract_id=ident,
            reference=f"wise_balance+{need}",
            source="wise",
        )
        item = dict(contract)
        item["status"] = "paid"
        item["paid_at"] = utcnow()
        item["ledger_hash"] = row.get("hash")
        upsert_named(root, "contracts.json", item)
        matched.append({"contract_id": ident, "amount": f"{need:.2f}", "hash": row.get("hash")})
        remaining -= need
    _save_state(root, {**state, "last_brl": str(current), "baseline_brl": str(baseline)})
    return {
        "ok": True,
        "action": "matched_payments" if matched else "delta_unmatched",
        "delta_brl": str(delta),
        "matched": matched,
        "brl_balance": str(current),
    }


def deliver_contract(root: Path, contract_id: str, *, evidence: str = "") -> dict[str, Any]:
    contracts = list_named(root, "contracts.json")
    target = next((item for item in contracts if str(item.get("id")) == contract_id), None)
    if not target:
        raise ValueError(f"contrato desconhecido: {contract_id}")
    if str(target.get("status")) not in {"paid", "delivered"}:
        raise ValueError("contrato ainda não está pago")
    item = dict(target)
    item["status"] = "delivered"
    item["delivered_at"] = utcnow()
    if evidence:
        item["evidence"] = evidence[:500]
    upsert_named(root, "contracts.json", item)
    append_jsonl(
        root,
        "journal.jsonl",
        {"kind": "delivery", "contract_id": contract_id, "evidence": bool(evidence)},
    )
    return item


def maybe_owner_payout(root: Path, config: AroConfig, *, live: bool = False) -> dict[str, Any]:
    try:
        base = Decimal(str(config.base_limit_brl or "50"))
    except Exception:
        base = BASE_LIMIT
    fin = snapshot(
        root,
        payout_dest_ok=config.money_rail_ready,
        base=base,
        channel=config.payout_channel,
    )
    weekly = fin.get("weekly_payout") or {}
    if not weekly.get("due"):
        return {"ok": True, "action": "no_payout", "finance": fin}
    amount = weekly.get("amount") or "0.00"
    live_flag = live and os.getenv("ARO_WISE_PAYOUT_LIVE") == "1"
    row = record_owner_payout(root, amount, channel=config.payout_channel, live=live_flag)
    append_jsonl(
        root,
        "journal.jsonl",
        {"kind": "owner_payout", "amount": amount, "live": live_flag, "hash": row.get("hash")},
    )
    return {
        "ok": True,
        "action": "owner_payout_recorded",
        "amount": amount,
        "live": live_flag,
        "hash": row.get("hash"),
        "finance": fin,
    }


def run_operate(
    root: Path,
    config: AroConfig,
    *,
    publish: bool = True,
    sync_wise: bool = True,
    payout: bool = True,
) -> dict[str, Any]:
    """One commercial cycle when outbound is authorized."""
    if config.stop_all:
        return {"ok": False, "action": "paused", "reason": "STOP_ALL_OPERATIONS"}
    if not config.ready_for_outbound:
        return {"ok": False, "action": "blocked", "reason": "not ready_for_outbound"}
    from agentic.aro.accounts import run_provision

    accounts_result = run_provision(root, config)
    wise_status = (
        {"ok": False, "configured": config.wise_configured}
        if os.getenv("AGENTIC_ARO_SKIP_WISE") == "1" or not config.wise_configured
        else wise_mod.status()
    )
    if not wise_status.get("ok"):
        return {
            "ok": False,
            "action": "fix_wise_rail",
            "reason": wise_status.get("reason") or "Wise indisponível",
            "accounts": accounts_result,
        }
    seed_offers(root, config)
    from agentic.aro.bootstrap import run_bootstrap

    bootstrap_result = run_bootstrap(root, config)
    from agentic.aro.mission import maybe_milestone_payout, mission_plan
    from agentic.aro.policy import operating_policy
    from agentic.aro.wallets import ensure_receive_rails

    steps: list[dict[str, Any]] = [
        {"kind": "accounts", **accounts_result},
        {"kind": "wallets", **ensure_receive_rails(root, config)},
        {"kind": "bootstrap", **bootstrap_result},
    ]
    if config.p2p_authorized:
        from agentic.aro import p2p as p2p_mod

        steps.append({"kind": "p2p", **p2p_mod.run_p2p(root, config)})
    if publish:
        steps.append(ensure_published(root, config))
    if sync_wise:
        steps.append(sync_wise_payments(root, config))
    payout_result: dict[str, Any] | None = None
    milestone_result: dict[str, Any] | None = None
    if payout:
        milestone_result = maybe_milestone_payout(root, config)
        steps.append(milestone_result)
        payout_result = maybe_owner_payout(root, config)
        steps.append(payout_result)
    try:
        base = Decimal(str(config.base_limit_brl or "50"))
    except Exception:
        base = BASE_LIMIT
    finance = snapshot(
        root,
        payout_dest_ok=config.money_rail_ready,
        base=base,
        channel=config.payout_channel,
    )
    mission = mission_plan(root, base=base, payout_dest_ok=config.money_rail_ready)
    policy = operating_policy(config)
    offers = list_named(root, "offers.json")
    contracts = list_named(root, "contracts.json")
    return {
        "ok": True,
        "action": "operate",
        "steps": steps,
        "finance": finance,
        "mission": mission,
        "policy": policy,
        "wise": {
            "ok": True,
            "brl_balance": wise_status.get("brl_balance"),
            "receive_ready": wise_status.get("receive_ready"),
        },
        "offers_published": sum(1 for o in offers if o.get("status") == "published"),
        "contracts": {
            "total": len(contracts),
            "awaiting_payment": sum(1 for c in contracts if c.get("status") == "awaiting_payment"),
            "paid": sum(1 for c in contracts if c.get("status") == "paid"),
            "delivered": sum(1 for c in contracts if c.get("status") == "delivered"),
        },
        "accounts": accounts_result,
        "bootstrap": bootstrap_result,
        "catalog": str((Path(root) / "data" / "aro" / CATALOG_FILE).relative_to(root)),
        "next": _next_action(finance, contracts, offers, mission),
    }


def _next_action(
    finance: dict[str, Any],
    contracts: list[dict[str, Any]],
    offers: list[dict[str, Any]],
    mission: dict[str, Any] | None = None,
) -> str:
    if not any(str(o.get("status")) == "published" for o in offers):
        return "publicar oferta"
    if mission and not mission.get("milestone_paid") and mission.get("milestone_reached"):
        return f"milestone: pagar R$ {mission.get('milestone_payout_due_brl')} ao owner"
    if mission and not mission.get("milestone_reached"):
        rem = mission.get("milestone_brl", "1000")
        return f"crescer caixa até R$ {rem} (milestone); reinvestir {int((mission.get('reinvest_share_rate') or 0.8)*100)}%"
    if not contracts:
        return "captar cliente: contrato + pagamento Wise"
    awaiting = [c for c in contracts if c.get("status") == "awaiting_payment"]
    if awaiting:
        return f"aguardar pagamento Wise ({len(awaiting)} contrato(s))"
    paid = [c for c in contracts if c.get("status") == "paid"]
    if paid:
        return f"entregar trabalho ({len(paid)} contrato(s) pagos)"
    weekly = finance.get("weekly_payout") or {}
    if weekly.get("due"):
        return f"participação semanal due: R$ {weekly.get('amount')}"
    cash = finance.get("cash") or "0.00"
    return f"operar: caixa R$ {cash}; procurar próximo cliente"
