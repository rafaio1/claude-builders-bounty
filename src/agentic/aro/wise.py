"""Wise money rail: receive from clients and send owner share. Never print the token."""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from typing import Any

import requests

WISE_ENV = Path("/root/.automaton/wise.env")
WISE_API = "https://api.wise.com"
WISE_STATE = "wise-state.json"


def _strip(value: str | None) -> str:
    return (value or "").strip().strip('"').strip("'")


def load_token() -> str:
    if WISE_ENV.is_file():
        for raw in WISE_ENV.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            if key.strip() in {"WISE_API_TOKEN", "WISE_API_KEY", "API_TOKEN"}:
                os.environ[key.strip()] = val.strip().strip("'").strip('"')
    base = _strip(os.getenv("WISE_BASE_URL")) or WISE_API
    os.environ.setdefault("WISE_BASE_URL", base)
    return _strip(os.getenv("WISE_API_TOKEN") or os.getenv("WISE_API_KEY"))


def api_base() -> str:
    return _strip(os.getenv("WISE_BASE_URL")) or WISE_API


def configured() -> bool:
    return bool(load_token())


def _get(path: str, token: str, timeout: float = 20.0) -> tuple[int, Any]:
    session = requests.Session()
    session.trust_env = False
    response = session.get(
        f"{api_base()}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "Agentic-ARO/0.1",
        },
        timeout=timeout,
    )
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": (response.text or "")[:200]}
    return response.status_code, payload


def _profiles(token: str) -> list[dict[str, Any]]:
    status, payload = _get("/v2/profiles", token)
    if status != 200:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        rows = payload.get("profiles") or payload.get("content") or []
        if isinstance(rows, list):
            return [item for item in rows if isinstance(item, dict)]
    return []


def _balances(token: str, profile_id: Any) -> list[dict[str, Any]]:
    status, payload = _get(f"/v4/profiles/{profile_id}/balances?types=STANDARD", token)
    if status != 200:
        return []
    rows = payload if isinstance(payload, list) else (payload or {}).get("balances") or []
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        amount = item.get("amount") if isinstance(item.get("amount"), dict) else {}
        out.append(
            {
                "currency": str(amount.get("currency") or item.get("currency") or ""),
                "value": str(amount.get("value") or "0"),
            }
        )
    return out


def brl_balance(balances: list[dict[str, Any]]) -> Decimal:
    for item in balances:
        if str(item.get("currency") or "").upper() == "BRL":
            try:
                return Decimal(str(item.get("value") or "0")).quantize(Decimal("0.01"))
            except Exception:
                return Decimal("0.00")
    return Decimal("0.00")


def _currency_code(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("code") or value.get("currency") or "")
    return str(value or "")


def _receive_options(token: str, profile_id: Any) -> list[dict[str, Any]]:
    status, payload = _get(f"/v1/profiles/{profile_id}/account-details", token)
    if status != 200:
        return []
    rows = payload if isinstance(payload, list) else []
    options: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        receive = item.get("receiveOptions")
        if not isinstance(receive, list):
            receive = []
        kinds: list[str] = []
        has_local = False
        for opt in receive:
            if not isinstance(opt, dict):
                continue
            kind = str(opt.get("type") or opt.get("title") or "")
            kinds.append(kind)
            if opt.get("details"):
                has_local = True
        currency = _currency_code(item.get("currency"))
        if not currency and not has_local:
            continue
        options.append(
            {
                "currency": currency,
                "title": str(item.get("title") or "")[:80],
                "receive_options": kinds[:6],
                "details_present": has_local,
            }
        )
    return options


def status() -> dict[str, Any]:
    """Connectivity snapshot. No token, no full account numbers."""
    token = load_token()
    if not token:
        return {
            "ok": False,
            "configured": False,
            "reason": "WISE_API_TOKEN ausente em /root/.automaton/wise.env",
            "profiles": 0,
            "balances": [],
            "receive": [],
        }
    try:
        profiles = _profiles(token)
    except requests.RequestException as exc:
        return {
            "ok": False,
            "configured": True,
            "reason": f"Wise HTTP falhou: {type(exc).__name__}",
            "profiles": 0,
            "balances": [],
            "receive": [],
        }
    if not profiles:
        return {
            "ok": False,
            "configured": True,
            "reason": "token Wise recusado ou sem profiles",
            "profiles": 0,
            "balances": [],
            "receive": [],
        }
    profile = profiles[0]
    profile_id = profile.get("id")
    kind = str((profile.get("type") or profile.get("profileType") or "")).lower()
    balances = _balances(token, profile_id) if profile_id else []
    receive = _receive_options(token, profile_id) if profile_id else []
    return {
        "ok": True,
        "configured": True,
        "reason": "",
        "profiles": len(profiles),
        "profile_id": profile_id,
        "profile_type": kind or "unknown",
        "balances": balances[:8],
        "brl_balance": str(brl_balance(balances)),
        "receive": receive[:8],
        "receive_ready": any(item.get("details_present") for item in receive),
        "rail": "wise",
    }


def receive_catalog() -> list[dict[str, Any]]:
    """Safe receive instructions for clients (no full account numbers)."""
    payload = status()
    if not payload.get("ok"):
        return []
    catalog: list[dict[str, Any]] = []
    for item in payload.get("receive") or []:
        if not item.get("details_present"):
            continue
        catalog.append(
            {
                "currency": item.get("currency"),
                "title": item.get("title"),
                "methods": item.get("receive_options") or [],
                "note": "Peça dados completos por e-mail após contrato assinado.",
            }
        )
    return catalog
