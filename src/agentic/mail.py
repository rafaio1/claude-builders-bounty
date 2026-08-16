"""AgentMail identity for ARO. Secrets live in /root/.automaton/aro-mail.env."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

MAIL_ENV = Path("/root/.automaton/aro-mail.env")
API_BASE = "https://api.agentmail.to/v0"
OTP_RE = re.compile(r"\b(\d{6})\b")


def _strip(value: str | None) -> str:
    return (value or "").strip().strip('"').strip("'")


def load_mail_env() -> dict[str, str]:
    data: dict[str, str] = {}
    if MAIL_ENV.is_file():
        for raw in MAIL_ENV.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            data[key.strip()] = val.strip().strip("'").strip('"')
            os.environ.setdefault(key.strip(), data[key.strip()])
    return data


def _write_flag(name: str, value: str) -> None:
    env = load_mail_env()
    env[name] = value
    order = [
        "AGENTMAIL_API_KEY",
        "AGENTMAIL_ORGANIZATION_ID",
        "AGENTMAIL_INBOX_ID",
        "ARO_MAIL_ADDRESS",
        "ARO_MAIL_DISPLAY",
        "ARO_MAIL_VERIFIED",
        "ARO_MAIL_PROVIDER",
        "ARO_MAIL_OWNER_NOTIFY",
    ]
    lines = [f"{key}={env[key]}" for key in order if key in env]
    for key, val in env.items():
        if key not in order:
            lines.append(f"{key}={val}")
    MAIL_ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
    MAIL_ENV.chmod(0o600)


def status() -> dict[str, Any]:
    env = load_mail_env()
    address = _strip(env.get("ARO_MAIL_ADDRESS") or env.get("AGENTMAIL_INBOX_ID"))
    return {
        "configured": bool(env.get("AGENTMAIL_API_KEY") and address),
        "provider": _strip(env.get("ARO_MAIL_PROVIDER")) or "agentmail",
        "address": address,
        "display_name": _strip(env.get("ARO_MAIL_DISPLAY")) or "ARO Agentic",
        "verified": _strip(env.get("ARO_MAIL_VERIFIED")).lower() in {"1", "true", "yes"},
        "inbox_id": _strip(env.get("AGENTMAIL_INBOX_ID")),
        "owner_notify": _strip(env.get("ARO_MAIL_OWNER_NOTIFY")),
        "api_key_present": bool(env.get("AGENTMAIL_API_KEY")),
    }


def _request(method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    env = load_mail_env()
    key = _strip(env.get("AGENTMAIL_API_KEY"))
    if not key:
        raise RuntimeError("AGENTMAIL_API_KEY ausente")
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        API_BASE + path,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw) if raw else {}
            return resp.status, data if isinstance(data, dict) else {"value": data}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {"error": raw[:300]}
        return exc.code, data if isinstance(data, dict) else {"error": str(data)}


def verify_otp(code: str) -> dict[str, Any]:
    digits = "".join(ch for ch in str(code) if ch.isdigit())
    if len(digits) != 6:
        return {"ok": False, "error": "OTP deve ter 6 dígitos"}
    status_code, data = _request("POST", "/agent/verify", {"otp_code": digits})
    ok = status_code == 200 and bool(data.get("verified") is True or data.get("verified") == "true")
    if ok:
        _write_flag("ARO_MAIL_VERIFIED", "1")
    return {"ok": ok, "http": status_code, "verified": ok, "detail": data.get("error") or data.get("message") or ""}


def extract_otp(text: str) -> str | None:
    match = OTP_RE.search(str(text or ""))
    return match.group(1) if match else None
