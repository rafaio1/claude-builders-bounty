"""Wise money rail: receive from clients and send owner share. Never print the token."""

from __future__ import annotations

import os
from decimal import Decimal
from math import ceil
from pathlib import Path
from time import monotonic
from typing import Any

import requests

WISE_ENV = Path("/root/.automaton/wise.env")
WISE_API = "https://api.wise.com"
WISE_STATE = "wise-state.json"
WISE_BACKOFF_BASE_SECONDS = 30
WISE_BACKOFF_MAX_SECONDS = 300
WISE_BACKOFF_MAX_FAILURES = 10

_backoff_failures = 0
_backoff_until = 0.0
_backoff_error_type = ""
_backoff_stage = ""
_backoff_error_kind = "network"
_backoff_retryable = True
_backoff_status_code: int | None = None


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


def _reset_integration_backoff() -> None:
    global _backoff_error_kind, _backoff_error_type, _backoff_failures
    global _backoff_retryable, _backoff_stage, _backoff_status_code, _backoff_until

    _backoff_failures = 0
    _backoff_until = 0.0
    _backoff_error_type = ""
    _backoff_stage = ""
    _backoff_error_kind = "network"
    _backoff_retryable = True
    _backoff_status_code = None


class WiseHTTPError(requests.HTTPError):
    def __init__(self, status_code: int):
        super().__init__(f"Wise API returned HTTP {status_code}")
        self.status_code = status_code


class WisePayloadError(requests.RequestException):
    """Raised when a successful Wise response cannot be safely interpreted."""


def _integration_error_payload(
    *,
    error_type: str,
    stage: str,
    failures: int,
    retry_after_seconds: int,
    profiles: int = 0,
    kind: str = "network",
    retryable: bool = True,
    status_code: int | None = None,
) -> dict[str, Any]:
    safe_error_type = (error_type or "RequestException")[:80]
    safe_stage = (stage or "request")[:80]
    payload = {
        "ok": False,
        "configured": True,
        "reason": (
            f"Wise integration unavailable ({safe_error_type} at {safe_stage}); "
            f"retry in {retry_after_seconds}s"
        ),
        "profiles": profiles,
        "balances": [],
        "receive": [],
        "retry_after_seconds": retry_after_seconds,
        "integration_error": {
            "provider": "wise",
            "kind": kind,
            "error_type": safe_error_type,
            "stage": safe_stage,
            "retryable": retryable,
            "consecutive_failures": failures,
            "retry_after_seconds": retry_after_seconds,
        },
    }
    if status_code is not None:
        payload["integration_error"]["status_code"] = status_code
    return payload


def _active_backoff_payload() -> dict[str, Any] | None:
    remaining = _backoff_until - monotonic()
    if remaining <= 0:
        return None
    return _integration_error_payload(
        error_type=_backoff_error_type,
        stage=_backoff_stage,
        failures=_backoff_failures,
        retry_after_seconds=max(1, ceil(remaining)),
        kind=_backoff_error_kind,
        retryable=_backoff_retryable,
        status_code=_backoff_status_code,
    )


def _record_integration_error(
    exc: requests.RequestException,
    *,
    stage: str,
    profiles: int = 0,
) -> dict[str, Any]:
    global _backoff_error_kind, _backoff_error_type, _backoff_failures
    global _backoff_retryable, _backoff_stage, _backoff_status_code, _backoff_until

    failures = min(_backoff_failures + 1, WISE_BACKOFF_MAX_FAILURES)
    delay = min(
        WISE_BACKOFF_MAX_SECONDS,
        WISE_BACKOFF_BASE_SECONDS * (2 ** (failures - 1)),
    )
    _backoff_failures = failures
    _backoff_until = monotonic() + delay
    _backoff_error_type = type(exc).__name__
    _backoff_stage = stage
    status_code = getattr(exc, "status_code", None)
    if status_code in {401, 403}:
        kind, retryable = "authentication", False
    elif status_code == 429:
        kind, retryable = "rate_limit", True
    elif isinstance(status_code, int) and status_code >= 500:
        kind, retryable = "server", True
    elif isinstance(exc, WisePayloadError):
        kind, retryable = "payload", True
    elif status_code is not None:
        kind, retryable = "http", False
    else:
        kind, retryable = "network", True
    _backoff_error_kind = kind
    _backoff_retryable = retryable
    _backoff_status_code = status_code
    return _integration_error_payload(
        error_type=_backoff_error_type,
        stage=stage,
        failures=failures,
        retry_after_seconds=delay,
        profiles=profiles,
        kind=kind,
        retryable=retryable,
        status_code=status_code,
    )


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


def _require_success(status_code: int) -> None:
    if status_code != 200:
        raise WiseHTTPError(status_code)


def _profiles(token: str) -> list[dict[str, Any]]:
    status, payload = _get("/v2/profiles", token)
    _require_success(status)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        rows = payload.get("profiles") or payload.get("content") or []
        if isinstance(rows, list):
            return [item for item in rows if isinstance(item, dict)]
    raise WisePayloadError("invalid profiles payload")


def _balances(token: str, profile_id: Any) -> list[dict[str, Any]]:
    status, payload = _get(f"/v4/profiles/{profile_id}/balances?types=STANDARD", token)
    _require_success(status)
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get("balances"), list):
        rows = payload["balances"]
    else:
        raise WisePayloadError("invalid balances payload")
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
    _require_success(status)
    if not isinstance(payload, list):
        raise WisePayloadError("invalid account-details payload")
    rows = payload
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
    backoff = _active_backoff_payload()
    if backoff is not None:
        return backoff
    profiles: list[dict[str, Any]] = []
    stage = "profiles"
    try:
        profiles = _profiles(token)
        if not profiles:
            raise WisePayloadError("no Wise profiles available")
        profile = profiles[0]
        profile_id = profile.get("id")
        if not profile_id:
            raise WisePayloadError("Wise profile is missing id")
        kind = str((profile.get("type") or profile.get("profileType") or "")).lower()
        stage = "balances"
        balances = _balances(token, profile_id)
        stage = "account_details"
        receive = _receive_options(token, profile_id)
    except requests.RequestException as exc:
        return _record_integration_error(
            exc,
            stage=stage,
            profiles=len(profiles),
        )
    _reset_integration_backoff()
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
