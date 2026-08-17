"""AgentMail identity for ARO. Secrets live in /root/.automaton/aro-mail.env."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

MAIL_ENV = Path("/root/.automaton/aro-mail.env")
API_BASE = "https://api.agentmail.to/v0"
OTP_RE = re.compile(r"\b(\d{6})\b")
LINK_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
PASSWORD_RE = re.compile(
    r"(?i)(?:password|senha|passwort)[\s:*\-]{0,12}([A-Za-z0-9!@#$%^&*._\-+=]{6,64})"
)


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


def list_inboxes() -> list[dict[str, Any]]:
    code, data = _request("GET", "/inboxes")
    if code != 200:
        return []
    rows = data.get("inboxes") if isinstance(data, dict) else []
    return [row for row in rows if isinstance(row, dict)]


def ensure_inbox(*, display_name: str, hint: str = "") -> dict[str, Any]:
    """Reuse an inbox whose display_name matches, or create/reclaim one if quota allows."""
    target = display_name.strip()
    inboxes = list_inboxes()
    for row in inboxes:
        if str(row.get("display_name") or "").strip().lower() == target.lower():
            return {"ok": True, "created": False, "inbox_id": row.get("inbox_id"), "email": row.get("email")}
    payload = {"display_name": target}
    if hint:
        payload["inbox_id"] = hint
    code, data = _request("POST", "/inboxes", payload)
    if code == 200 and (data.get("inbox_id") or data.get("email")):
        return {
            "ok": True,
            "created": True,
            "http": code,
            "inbox_id": data.get("inbox_id") or data.get("email"),
            "email": data.get("email") or data.get("inbox_id"),
            "detail": "",
        }
    if code == 403 and str(data.get("code") or "") == "limit_exceeded":
        primary = load_mail_env().get("AGENTMAIL_INBOX_ID") or load_mail_env().get("ARO_MAIL_ADDRESS")
        for row in inboxes:
            inbox_id = str(row.get("inbox_id") or "")
            if not inbox_id or inbox_id == primary:
                continue
            name = str(row.get("display_name") or "")
            if name.lower().startswith("aro ") and name.lower() != target.lower():
                continue
            if name.lower() in {"agentmail", "aro"} or name.lower().startswith("aro "):
                patched = update_inbox(inbox_id, display_name=target)
                if patched.get("ok"):
                    return {
                        "ok": True,
                        "created": False,
                        "reclaimed": True,
                        "inbox_id": inbox_id,
                        "email": row.get("email") or inbox_id,
                    }
        for row in inboxes:
            inbox_id = str(row.get("inbox_id") or "")
            if inbox_id and inbox_id != primary:
                patched = update_inbox(inbox_id, display_name=target)
                if patched.get("ok"):
                    return {
                        "ok": True,
                        "created": False,
                        "reclaimed": True,
                        "inbox_id": inbox_id,
                        "email": row.get("email") or inbox_id,
                    }
    return {
        "ok": False,
        "created": False,
        "http": code,
        "inbox_id": "",
        "email": "",
        "detail": data.get("message") or data.get("error") or "",
    }


def update_inbox(inbox_id: str, *, display_name: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if display_name:
        payload["display_name"] = display_name
    if not payload:
        return {"ok": False}
    code, data = _request("PATCH", f"/inboxes/{inbox_id}", payload)
    return {"ok": code == 200, "http": code, "inbox_id": inbox_id, "detail": data}


def list_messages(inbox_id: str, *, limit: int = 10, subject: str = "") -> list[dict[str, Any]]:
    query = f"/inboxes/{inbox_id}/messages?limit={max(1, min(limit, 100))}"
    if subject:
        query += f"&subject={urllib.parse.quote(subject)}"
    code, data = _request("GET", query)
    if code != 200 or not isinstance(data, dict):
        return []
    rows = data.get("messages") or []
    return [row for row in rows if isinstance(row, dict)]


def get_message(inbox_id: str, message_id: str) -> dict[str, Any]:
    code, data = _request("GET", f"/inboxes/{inbox_id}/messages/{message_id}")
    if code != 200 or not isinstance(data, dict):
        return {}
    return data


def _message_text(message: dict[str, Any]) -> str:
    parts = [
        str(message.get("subject") or ""),
        str(message.get("text") or ""),
        str(message.get("body") or ""),
        str(message.get("html") or ""),
        str(message.get("preview") or ""),
    ]
    return "\n".join(parts)


def wait_for_message(
    inbox_id: str,
    *,
    subject_contains: str = "",
    from_contains: str = "",
    timeout_sec: int = 90,
    poll_sec: int = 5,
) -> dict[str, Any] | None:
    import time

    deadline = time.time() + max(5, timeout_sec)
    seen: set[str] = set()
    while time.time() < deadline:
        for row in list_messages(inbox_id, limit=20):
            ident = str(row.get("message_id") or "")
            if ident and ident in seen:
                continue
            if ident:
                seen.add(ident)
            subj = str(row.get("subject") or "").lower()
            sender = str(row.get("from") or "").lower()
            if subject_contains and subject_contains.lower() not in subj:
                continue
            if from_contains and from_contains.lower() not in sender:
                continue
            full = get_message(inbox_id, ident) if ident else row
            return full or row
        time.sleep(max(2, poll_sec))
    return None


def extract_verification_link(text: str, *, domain_hint: str = "") -> str | None:
    blob = str(text or "")
    for link in LINK_RE.findall(blob):
        lowered = link.lower()
        if any(token in lowered for token in ("verify", "confirm", "activation", "activate", "register")):
            if not domain_hint or domain_hint.lower() in lowered:
                return link.rstrip(").,;]")
    return None


def extract_password_from_mail(text: str) -> str | None:
    match = PASSWORD_RE.search(str(text or ""))
    return match.group(1) if match else None
