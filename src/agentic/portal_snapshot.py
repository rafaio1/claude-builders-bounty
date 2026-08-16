"""Build a sanitized Agentic portal snapshot. Never copies secrets or .env."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentic.portal import sanitize_state

SCHEMA_VERSION = 1
DEFAULT_ROOT = Path("/Agentic")
DEFAULT_INBOX = Path("/var/lib/agentic-portal/inbox.jsonl")
STATUS_LABELS = {
    "pending": "Na fila",
    "developing": "Em develop",
    "in_review": "Em review",
    "applied": "Em master",
    "rejected": "Rejeitada",
    "blocked": "Bloqueada",
}
THEME_LABELS = {
    "engine": "Motor",
    "portal": "Portal",
    "ai": "IA",
    "tools": "Ferramentas",
}


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        return None


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
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
            if isinstance(item, dict):
                rows.append(item)
    except OSError:
        return []
    return rows


def _pretty_time(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "—"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).strftime("%d/%m %H:%M UTC")
    except ValueError:
        return text[:40]


def _latest_aro(root: Path) -> dict[str, Any]:
    reports = Path(root) / "data" / "aro" / "reports"
    newest: Path | None = None
    if reports.is_dir():
        files = sorted(reports.glob("daily-*.json"))
        newest = files[-1] if files else None
    payload = _load_json(newest) if newest else None
    return payload if isinstance(payload, dict) else {}


def _messages(inbox: Path, root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _load_jsonl(inbox):
        at = str(item.get("at") or item.get("datetime") or "")
        rows.append(
            {
                "id": item.get("id") or "",
                "role": "owner",
                "author": item.get("author") or "rafaio",
                "body": item.get("body") or item.get("text") or "",
                "time": _pretty_time(at),
                "datetime": at,
                "at": at,
            }
        )
    for item in _load_jsonl(Path(root) / "data" / "aro" / "messages.jsonl"):
        at = str(item.get("at") or item.get("datetime") or "")
        rows.append(
            {
                "id": item.get("id") or "",
                "role": item.get("role") or "agent",
                "author": item.get("author") or "ARO",
                "body": item.get("body") or "",
                "time": _pretty_time(at),
                "datetime": at,
                "at": at,
            }
        )
    rows.sort(key=lambda item: str(item.get("at") or ""))
    return rows[-80:]


def build_snapshot(
    root: Path,
    *,
    inbox: Path = DEFAULT_INBOX,
) -> dict[str, Any]:
    root = Path(root)
    status = _load_json(root / "data" / "status.json")
    status = status if isinstance(status, dict) else {}
    integrity = _load_json(root / "data" / "integrity.json")
    integrity = integrity if isinstance(integrity, dict) else {}
    ledger = _load_json(root / "improve" / "ledger.json")
    ledger = ledger if isinstance(ledger, dict) else {}
    aro = _latest_aro(root)
    tools = status.get("tools") if isinstance(status.get("tools"), dict) else {}
    aro_status = status.get("aro") if isinstance(status.get("aro"), dict) else {}
    offers = aro.get("offers") if isinstance(aro.get("offers"), list) else []
    generated = str(status.get("generated_at") or utcnow())
    engine = "Pausado" if aro_status.get("paused") else "Em observação"
    if not status:
        engine = "Sem heartbeat"
    findings = []
    for index, item in enumerate(offers, start=1):
        if not isinstance(item, dict):
            continue
        findings.append(
            {
                "id": index,
                "title": item.get("title") or item.get("id") or "Oferta",
                "program": item.get("id") or "offer",
                "severity": "info",
                "status": item.get("status") or "draft",
                "updated_at": _pretty_time(generated),
                "updated_at_iso": generated,
            }
        )
    programs = []
    for name, present in tools.items():
        if name in {"bybit_secret"}:
            continue
        programs.append(
            {
                "handle": name,
                "name": name.replace("_", " "),
                "status": "Presente" if present else "Ausente",
                "findings": 1 if present else 0,
                "reports": 0,
                "last_seen": "autorizada para venda: não",
                "last_seen_iso": generated,
            }
        )
    try:
        from agentic.mail import status as mail_status

        mail = mail_status()
    except Exception:
        mail = {"configured": False}
    if mail.get("address"):
        programs.insert(
            0,
            {
                "handle": "aro-mail",
                "name": mail.get("address"),
                "status": "Verificada" if mail.get("verified") else "Aguardando OTP",
                "findings": 1 if mail.get("configured") else 0,
                "reports": 1 if mail.get("verified") else 0,
                "last_seen": "AgentMail · automação ARO",
                "last_seen_iso": generated,
            },
        )
        if not mail.get("verified"):
            next_action_mail = "Enviar o OTP de 6 dígitos no portal ou: python -m agentic mail verify --otp NNNNNN"
        else:
            next_action_mail = ""
    else:
        next_action_mail = ""
    activity = []
    for item in _load_jsonl(root / "data" / "aro" / "journal.jsonl")[-40:]:
        at = str(item.get("at") or "")
        activity.append(
            {
                "title": item.get("kind") or "ciclo",
                "detail": item.get("summary") or item.get("note") or "Evento ARO",
                "time": _pretty_time(at),
                "datetime": at,
                "status": "warning" if item.get("paused") else "info",
            }
        )
    proposals_out = []
    counts = {
        "total": 0,
        "pending": 0,
        "developing": 0,
        "in_review": 0,
        "applied": 0,
        "rejected": 0,
        "blocked": 0,
        "active": 0,
    }
    for item in ledger.get("proposals") or []:
        if not isinstance(item, dict):
            continue
        status_name = str(item.get("status") or "pending")
        counts["total"] += 1
        counts[status_name] = counts.get(status_name, 0) + 1
        if status_name in {"pending", "developing", "in_review"}:
            counts["active"] += 1
        theme = str(item.get("theme") or "engine")
        kind = str(item.get("kind") or "improvement")
        proposals_out.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "kind": kind,
                "kind_label": "Gargalo" if kind == "bottleneck" else "Melhoria",
                "theme": theme,
                "theme_label": THEME_LABELS.get(theme, "Motor"),
                "priority": item.get("priority") or 3,
                "status": status_name,
                "status_label": STATUS_LABELS.get(status_name, status_name),
                "rationale": item.get("rationale"),
                "change": item.get("change"),
                "never": item.get("never") or [],
                "files_hint": item.get("files_hint") or [],
                "branch": item.get("branch") or "",
                "map_id": item.get("map_id") or "",
            }
        )
    decision = aro.get("decision") if isinstance(aro.get("decision"), dict) else {}
    next_action = str(
        next_action_mail
        or aro_status.get("next_action")
        or decision.get("next_action")
        or "Configurar identidade e destino de payout"
    )
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated,
        "stats": {
            "programs_total": len(offers) or len(findings),
            "findings_total": 0,
            "reports_ready": 1 if not aro_status.get("ready_for_outbound") else 0,
            "submissions_total": 0,
            "engine_status": engine,
            "last_run": _pretty_time(generated),
            "last_run_iso": generated,
            "next_action": next_action,
            "cash_brl": 0,
            "offers_total": len(offers) or len(findings),
            "paused": "sim" if aro_status.get("paused") else "não",
        },
        "findings": findings,
        "activity": activity,
        "programs": programs,
        "reports": findings,
        "submissions": [],
        "heartbeat": {
            "status": "healthy" if status.get("ok") else "degraded",
            "engine_status": engine,
            "generated_at": generated,
            "updated_at": generated,
            "age_seconds": 0,
            "last_activity": generated,
            "pipeline": {},
        },
        "modelos": [
            {"name": os.getenv("GHOSTCLI_MODEL", "claude-sonnet-5[1m]"), "uses": 0, "last_used_at": ""},
            {
                "name": os.getenv("GHOSTCLI_ORCHESTRATOR_MODEL", "claude-fable-5[1m]"),
                "uses": 0,
                "last_used_at": "",
            },
        ],
        "improve": {
            "updated_at": str(ledger.get("updated_at") or ""),
            "map_id": "",
            "summary": next_action,
            "counts": counts,
            "census": {
                "playwright": 1 if tools.get("playwright") else 0,
                "ghostcli": 1 if tools.get("ghostcli") else 0,
                "bybit_key": 1 if tools.get("bybit_key") else 0,
            },
            "proposals": proposals_out[:40],
        },
        "integrity": integrity,
        "ai_eval": {
            "ok": bool(tools.get("ghostcli") and tools.get("playwright")),
            "status": "ok" if tools.get("ghostcli") else "missing",
            "generated_at": generated,
            "summary": "Playwright e GhostCLI reportados só como booleanos; Bybit não opera o caixa ARO.",
            "passed": sum(1 for key in ("playwright", "ghostcli") if tools.get(key)),
            "failed": sum(1 for key in ("playwright", "ghostcli") if not tools.get(key)),
            "total": 2,
            "cases": [
                {
                    "id": "playwright",
                    "ok": bool(tools.get("playwright")),
                    "detail": "playwright-cli",
                },
                {
                    "id": "ghostcli",
                    "ok": bool(tools.get("ghostcli")),
                    "detail": "chave presente (valor omitido)",
                },
            ],
        },
        "messages": _messages(inbox, root),
    }
    return sanitize_state(snapshot)


def write_snapshot(path: Path, payload: dict[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Snapshot sanitizado do portal Agentic")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--inbox", type=Path, default=DEFAULT_INBOX)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = build_snapshot(args.root, inbox=args.inbox)
    write_snapshot(args.output, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
