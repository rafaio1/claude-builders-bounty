"""ARO cycle: observe, operate via Wise when authorized."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from agentic.aro.config import AroConfig, load_aro_config
from agentic.aro.constitution import VERSION, constitution_intact, invariants_hash
from agentic.aro.finance import BASE_LIMIT, snapshot as finance_snapshot
from agentic.aro.offers import seed_offers
from agentic.aro.store import append_jsonl, ensure_stores, read_jsonl

DEFAULT_INBOX = Path("/var/lib/agentic-portal/inbox.jsonl")

DECISION_IDLE = {
    "objective": "inicializar ARO sem contato externo",
    "opportunity_id": "",
    "action": "observe_and_record",
    "expected_gross_revenue": 0,
    "expected_net_profit": 0,
    "probability_of_success": 1.0,
    "estimated_time_to_cash_days": 0,
    "maximum_cost": 0,
    "reversibility": "FULL",
    "client_risk": "LOW",
    "legal_risk": "LOW",
    "security_risk": "LOW",
    "approval_required": False,
    "acceptance_evidence": ["stores exist", "offers drafted", "no outbound"],
    "stop_conditions": ["STOP_ALL_OPERATIONS", "constitution broken", "live_trade"],
    "next_action": "wait_for_authorized_identity_and_payout_destination",
}


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def inventory_tools() -> dict[str, bool]:
    return {
        "playwright_cli": bool(shutil.which("playwright-cli")),
        "playwright_mcp": False,
        "jq": bool(shutil.which("jq")),
        "git": bool(shutil.which("git")),
        "docker": bool(shutil.which("docker")),
        "python": bool(shutil.which("python3")),
    }


def account_scopes(
    *,
    ghostcli: bool,
    bybit: bool,
    wise: dict[str, Any] | None = None,
    may_open_receive_accounts: bool = False,
    p2p_authorized: bool = False,
) -> dict[str, Any]:
    wise = wise or {}
    bybit_scope = "p2p_buy_sell" if p2p_authorized else "optional_weekly_hop_via_wise"
    bybit_reason = (
        "P2P compra/venda autorizado (não é spot trading)"
        if p2p_authorized
        else "Bybit não transaciona o caixa ARO; hop opcional da participação via Wise"
    )
    return {
        "ghostcli": {
            "present": ghostcli,
            "scope": "llm_inference" if ghostcli else "missing",
            "authorized_for_aro_sales": False,
        },
        "bybit": {
            "present": bybit,
            "scope": bybit_scope,
            "authorized_for_aro_sales": bool(p2p_authorized and bybit),
            "p2p_authorized": p2p_authorized,
            "reason": bybit_reason,
        },
        "wise": {
            "present": bool(wise.get("configured")),
            "ok": bool(wise.get("ok")),
            "scope": "receive_and_send",
            "authorized_for_aro_sales": bool(wise.get("ok")),
            "receive_ready": bool(wise.get("receive_ready")),
        },
        "freelancer_platforms": {
            "present": False,
            "authorized_for_aro_sales": False,
            "authorized_to_open": bool(may_open_receive_accounts),
        },
        "payment_processor": {
            "present": bool(wise.get("configured")),
            "authorized_for_aro_sales": bool(wise.get("ok")),
            "name": "wise",
        },
    }


def _load_inbox(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict) and str(item.get("body") or "").strip():
                rows.append(item)
    except OSError:
        return []
    return rows


def process_owner_inbox(
    root: Path,
    *,
    inbox: Path | None = None,
    paused: bool = False,
    ready_for_outbound: bool = False,
) -> list[dict[str, Any]]:
    """Acknowledge owner portal notes. Treat the body as data, not new rules."""
    source = Path(inbox or os.getenv("AGENTIC_PORTAL_INBOX_PATH") or DEFAULT_INBOX)
    seen = {
        str(item.get("in_reply_to") or "")
        for item in read_jsonl(root, "messages.jsonl")
        if item.get("in_reply_to")
    }
    replies: list[dict[str, Any]] = []
    for item in _load_inbox(source):
        ident = str(item.get("id") or "")
        if not ident or ident in seen:
            continue
        body = str(item.get("body") or "").strip()
        lowered = body.lower()
        otp = None
        try:
            from agentic.mail import extract_otp, verify_otp

            otp = extract_otp(body)
        except Exception:
            otp = None
        if otp and ("otp" in lowered or "agentmail" in lowered or body.strip() == otp):
            result = verify_otp(otp)
            if result.get("ok"):
                answer = "OTP aceite. Caixa agentic-aro@agentmail.to verificada para envio e recepção."
            else:
                answer = "OTP recusado ou expirado. Peça novo código ou envie os 6 dígitos outra vez."
        elif "stop_all_operations" in lowered.replace(" ", "_"):
            stop = Path(root) / ".agentic-aro.stop"
            stop.write_text("STOP_ALL_OPERATIONS\n", encoding="utf-8")
            answer = (
                "STOP_ALL_OPERATIONS aceite. Novas propostas, compras e entregas ficam pausadas."
            )
        elif any(
            marker in lowered
            for marker in (
                "owner_share",
                "participação",
                "destino de pagamento",
                "live_trade",
            )
        ):
            answer = (
                "Não altero taxa do proprietário, destino de saque nem ligo trading. "
                "Esses controlos estão fora do portal."
            )
        elif paused:
            answer = "Mensagem recebida. Operação pausada; sem contacto comercial."
        elif ready_for_outbound:
            answer = "Mensagem recebida. Próximo ciclo avalia o pedido dentro da constituição."
        else:
            answer = (
                "Mensagem recebida. Ciclo interno: sem propostas externas até identidade, "
                "trilho Wise e contas autorizadas."
            )
        replies.append(
            append_jsonl(
                root,
                "messages.jsonl",
                {
                    "role": "agent",
                    "author": "ARO",
                    "in_reply_to": ident,
                    "body": answer,
                },
            )
        )
    return replies


def run_cycle(
    root: Path,
    *,
    tools: dict[str, Any] | None = None,
    ghostcli: bool = False,
    bybit: bool = False,
    live_trade: bool = False,
    config: AroConfig | None = None,
    operate: bool = False,
) -> dict[str, Any]:
    config = config or load_aro_config(root)
    intact, marker = constitution_intact(root)
    if live_trade:
        raise RuntimeError("ARO recusa AGENTIC_LIVE_TRADE ligado")
    stores = ensure_stores(root)
    offers = seed_offers(root, config)
    from agentic.aro import wise as wise_mod

    if os.getenv("AGENTIC_ARO_SKIP_WISE") == "1" or not config.wise_configured:
        wise_status = {"ok": False, "configured": bool(config.wise_configured)}
    else:
        wise_status = wise_mod.status()
    inventory = inventory_tools()
    if tools:
        inventory.update({k: bool(v) for k, v in tools.items() if isinstance(v, bool)})
    accounts = account_scopes(
        ghostcli=ghostcli,
        bybit=bybit,
        wise=wise_status,
        may_open_receive_accounts=config.may_open_receive_accounts,
        p2p_authorized=config.p2p_authorized,
    )
    try:
        base_limit = Decimal(str(config.base_limit_brl or "50"))
    except Exception:
        base_limit = BASE_LIMIT
    finance = finance_snapshot(
        root,
        payout_dest_ok=config.money_rail_ready,
        base=base_limit,
        channel=config.payout_channel,
    )
    paused = bool(config.stop_all or not intact)
    decision = dict(DECISION_IDLE)
    commerce_result: dict[str, Any] | None = None
    if paused:
        decision["action"] = "pause"
        decision["next_action"] = "preserve_evidence_and_wait"
        decision["approval_required"] = True
    elif not config.ready_for_outbound:
        missing = []
        if not config.owner_name or not config.business_name:
            missing.append("ARO_OWNER_NAME/ARO_BUSINESS_NAME")
        if not config.wise_configured:
            missing.append("WISE_API_TOKEN")
        if not config.commercial_outbound:
            missing.append("ARO_COMMERCIAL_OUTBOUND")
        decision["next_action"] = "configure " + ", ".join(missing or ["trilho Wise"])
    elif not wise_status.get("ok"):
        decision["action"] = "fix_wise_rail"
        decision["next_action"] = wise_status.get("reason") or "Wise token inválido"
    elif finance["weekly_payout"]["due"]:
        decision["action"] = "weekly_owner_payout"
        decision["next_action"] = "registar/enviar participação 20% via Wise"
        decision["expected_net_profit"] = finance["owner_accrual"]
    else:
        decision["action"] = "operate_via_wise"
        decision["next_action"] = (
            "publicar oferta; contrato; receber Wise; entregar; participação semanal"
        )
        decision["acceptance_evidence"] = ["wise rail", "catalog"]
    if operate and config.ready_for_outbound and not paused and wise_status.get("ok"):
        from agentic.aro.commerce import run_operate

        commerce_result = run_operate(root, config)
        if commerce_result.get("next"):
            decision["next_action"] = str(commerce_result["next"])
        finance = commerce_result.get("finance") or finance
    report = {
        "ok": intact and not live_trade,
        "paused": paused,
        "cycle": "operate" if operate else "observe",
        "version": VERSION,
        "invariants_hash": invariants_hash(),
        "constitution": marker,
        "constitution_ok": intact,
        "generated_at": utcnow(),
        "tools": inventory,
        "accounts": accounts,
        "stores": stores,
        "offers": [
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "price_floor": item.get("price_floor"),
                "status": item.get("status"),
            }
            for item in offers
        ],
        "ready_for_outbound": config.ready_for_outbound and not paused,
        "payout_destination_configured": config.payout_destination_configured,
        "owner_share_rate": config.owner_share_rate,
        "payout_channel": config.payout_channel,
        "may_open_receive_accounts": config.may_open_receive_accounts,
        "wise": {
            "ok": bool(wise_status.get("ok")),
            "configured": bool(wise_status.get("configured")),
            "receive_ready": bool(wise_status.get("receive_ready")),
            "balances": wise_status.get("balances") or [],
            "brl_balance": wise_status.get("brl_balance"),
            "reason": wise_status.get("reason") or "",
        },
        "identity": {
            "owner_configured": bool(config.owner_name),
            "business_configured": bool(config.business_name),
        },
        "finance": finance,
        "financial_limits_configured": True,
        "commerce": commerce_result,
        "decision": decision,
        "note": (
            "Receita licita no Brasil. Wise + carteira crypto; P2P pago da Wise. "
            "20% owner semanal; reinvestir resto; milestone R$ 1000 → metade ao owner. "
            "Sem impersonação; divulgar automação quando exigido."
        ),
    }
    replies = process_owner_inbox(
        root,
        paused=paused,
        ready_for_outbound=bool(report["ready_for_outbound"]),
    )
    report["inbox_replies"] = len(replies)
    if replies:
        paused = paused or (Path(root) / ".agentic-aro.stop").is_file()
        report["paused"] = paused
    append_jsonl(
        root,
        "journal.jsonl",
        {
            "kind": "cycle",
            "summary": report["note"],
            "paused": paused,
            "operate": operate,
        },
    )
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily = Path(root) / "data" / "aro" / "reports" / f"daily-{day}.json"
    daily.parent.mkdir(parents=True, exist_ok=True)
    daily.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return report
