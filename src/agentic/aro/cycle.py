"""ARO cycle 1: observe, record, do not contact or pay."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentic.aro.config import AroConfig, load_aro_config
from agentic.aro.constitution import VERSION, constitution_intact, invariants_hash
from agentic.aro.offers import seed_offers
from agentic.aro.store import append_jsonl, ensure_stores

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
        "playwright_mcp": bool(shutil.which("playwright-mcp")),
        "jq": bool(shutil.which("jq")),
        "git": bool(shutil.which("git")),
        "docker": bool(shutil.which("docker")),
        "python": bool(shutil.which("python3")),
    }


def account_scopes(*, ghostcli: bool, bybit: bool) -> dict[str, Any]:
    return {
        "ghostcli": {
            "present": ghostcli,
            "scope": "llm_inference" if ghostcli else "missing",
            "authorized_for_aro_sales": False,
        },
        "bybit": {
            "present": bybit,
            "scope": "unauthorized_for_aro_operating_cash",
            "authorized_for_aro_sales": False,
            "reason": "constituição proíbe trading especulativo com o caixa operacional",
        },
        "freelancer_platforms": {
            "present": False,
            "authorized_for_aro_sales": False,
        },
        "payment_processor": {
            "present": False,
            "authorized_for_aro_sales": False,
        },
    }


def run_cycle(
    root: Path,
    *,
    tools: dict[str, Any] | None = None,
    ghostcli: bool = False,
    bybit: bool = False,
    live_trade: bool = False,
    config: AroConfig | None = None,
) -> dict[str, Any]:
    config = config or load_aro_config(root)
    intact, marker = constitution_intact(root)
    if live_trade:
        raise RuntimeError("ARO recusa AGENTIC_LIVE_TRADE=1")
    stores = ensure_stores(root)
    offers = seed_offers(root, config)
    inventory = inventory_tools()
    if tools:
        inventory.update({k: bool(v) for k, v in tools.items() if isinstance(v, bool)})
    accounts = account_scopes(ghostcli=ghostcli, bybit=bybit)
    paused = bool(config.stop_all or not intact)
    decision = dict(DECISION_IDLE)
    if paused:
        decision["action"] = "pause"
        decision["next_action"] = "preserve_evidence_and_wait"
        decision["approval_required"] = True
    elif not config.ready_for_outbound:
        missing = []
        if not config.owner_name or not config.business_name:
            missing.append("ARO_OWNER_NAME/ARO_BUSINESS_NAME")
        if not config.payout_destination_configured:
            missing.append("aro-payout.dest")
        if not config.commercial_outbound:
            missing.append("ARO_COMMERCIAL_OUTBOUND")
        decision["next_action"] = "configure " + ", ".join(missing or ["limites financeiros"])
    report = {
        "ok": intact and not live_trade,
        "paused": paused,
        "cycle": "observe",
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
        "financial_limits_configured": bool(
            config.minimum_payout
            and config.max_single_expense
            and config.minimum_cash_reserve
        ),
        "decision": decision,
        "note": (
            "Ciclo 1 interno: sem propostas, publicações, pagamentos ou uso de Bybit. "
            "Configure identidade, destino de payout (ficheiro 0600 fora do git) e "
            "ARO_COMMERCIAL_OUTBOUND=1 só depois de contas autorizadas."
        ),
    }
    append_jsonl(root, "journal.jsonl", {"kind": "cycle", "summary": report["note"], "paused": paused})
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily = Path(root) / "data" / "aro" / "reports" / f"daily-{day}.json"
    daily.parent.mkdir(parents=True, exist_ok=True)
    daily.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return report
