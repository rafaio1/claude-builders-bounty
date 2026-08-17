"""Autonomous platform account provisioning. No CAPTCHA bypass, no fake identities."""

from __future__ import annotations

import json
import os
import re
import secrets
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from agentic.aro.config import AroConfig
from agentic.aro.store import append_jsonl, list_named, upsert_named, utcnow
from agentic import mail as mail_mod

ACCOUNTS_ENV = Path("/root/.automaton/aro-accounts.env")
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
RETRY_HOURS = 6


@dataclass(frozen=True)
class PlatformSpec:
    platform_id: str
    title: str
    signup_url: str
    inbox_display: str
    kind: str  # api | http | antibot


PLATFORMS: tuple[PlatformSpec, ...] = (
    PlatformSpec("wise", "Wise money rail", "", "ARO Wise", "api"),
    PlatformSpec("agentmail", "AgentMail inbound", "", "AgentMail", "api"),
    PlatformSpec("mql5", "MQL5 Freelance", "https://www.mql5.com/pt/auth_register", "ARO MQL5", "http"),
    PlatformSpec("contra", "Contra", "https://contra.com/sign-up", "ARO Contra", "browser"),
    PlatformSpec("freelancer", "Freelancer.com", "https://www.freelancer.com/signup", "ARO Freelancer", "browser"),
    PlatformSpec("workana", "Workana BR", "https://www.workana.com/signup", "ARO Workana", "antibot"),
    PlatformSpec("99freelas", "99freelas BR", "https://www.99freelas.com.br/register", "ARO 99freelas", "antibot"),
)


def _authorized(config: AroConfig) -> bool:
    flag = os.getenv("ARO_OPERATOR_ACCOUNTS_AUTHORIZED", "").lower()
    return flag in {"1", "true", "yes", "on"} and config.may_open_receive_accounts


def _load_accounts_env() -> dict[str, str]:
    data: dict[str, str] = {}
    if not ACCOUNTS_ENV.is_file():
        return data
    for raw in ACCOUNTS_ENV.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        data[key.strip()] = val.strip()
    return data


def _save_accounts_env(values: dict[str, str]) -> None:
    existing = _load_accounts_env()
    existing.update({k: v for k, v in values.items() if v})
    lines = ["# ARO platform accounts — mode 0600. Never commit."]
    for key in sorted(existing):
        lines.append(f"{key}={existing[key]}")
    ACCOUNTS_ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ACCOUNTS_ENV.chmod(0o600)


def _public_email(config: AroConfig) -> str:
    return (
        os.getenv("ARO_PUBLIC_EMAIL")
        or mail_mod.status().get("address")
        or "agentic-aro@agentmail.to"
    ).strip()


def _public_display(config: AroConfig) -> str:
    return (os.getenv("ARO_PUBLIC_DISPLAY") or config.business_name or "ARO").strip()


def _account_row(root, platform_id: str) -> dict[str, Any]:
    for item in list_named(root, "accounts.json"):
        if str(item.get("platform_id") or item.get("id")) == platform_id:
            return item
    return {"platform_id": platform_id, "status": "pending"}


def _should_retry(row: dict[str, Any]) -> bool:
    if row.get("status") in {"active", "verified"}:
        return False
    if row.get("status") == "blocked":
        return True
    last = str(row.get("last_attempt_at") or "")
    if not last:
        return True
    try:
        from datetime import datetime, timezone

        then = datetime.fromisoformat(last.replace("Z", "+00:00"))
        elapsed = datetime.now(timezone.utc) - then
        hours = 1 if row.get("status") == "blocked" else RETRY_HOURS
        return elapsed.total_seconds() >= hours * 3600
    except Exception:
        return True


def _update_account(root, platform_id: str, **fields: Any) -> dict[str, Any]:
    row = _account_row(root, platform_id)
    row.update(fields)
    row["platform_id"] = platform_id
    row["updated_at"] = utcnow()
    upsert_named(root, "accounts.json", row, key="platform_id")
    return row


def _probe_url(url: str) -> dict[str, Any]:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=20,
            allow_redirects=True,
        )
        body = (response.text or "")[:400].lower()
        blocked = response.status_code in {403, 429} or "cloudflare" in body or "captcha" in body
        return {
            "ok": response.status_code < 400 and not blocked,
            "status_code": response.status_code,
            "blocked": blocked,
            "reason": "antibot" if blocked else "",
        }
    except requests.RequestException as exc:
        return {"ok": False, "status_code": 0, "blocked": True, "reason": type(exc).__name__}


def _public_display(config: AroConfig) -> str:
    return (os.getenv("ARO_PUBLIC_DISPLAY") or config.business_name or "ARO").strip()


def _register_browser(
    spec: PlatformSpec,
    email: str,
    inbox_id: str,
    config: AroConfig,
) -> dict[str, Any]:
    from agentic.aro import browser_signup as browser

    label = _public_display(config)
    if spec.platform_id == "contra":
        reg = browser.register_contra(email, first_name=label, last_name="Agentic")
        hints = ("contra", "contra.com", "Contra")
    elif spec.platform_id == "freelancer":
        password = browser.generated_password()
        reg = browser.register_freelancer(email, password, first_name=label, last_name="Agentic")
        if reg.get("ok"):
            _save_accounts_env({"FREELANCER_PASSWORD_SET": "1"})
        hints = ("freelancer", "freelancer.com", "")
    else:
        return {"ok": False, "reason": "unknown_browser_platform"}
    if not reg.get("ok"):
        return reg
    verify = browser.verify_platform_mail(
        inbox_id,
        from_hint=hints[0],
        domain_hint=hints[1],
        subject_hint=hints[2],
    )
    return {**reg, "verify": verify, "verified": verify.get("verified")}


def _register_mql5(email: str) -> dict[str, Any]:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    session.get("https://www.mql5.com/pt", timeout=20)
    page = session.get("https://www.mql5.com/pt/auth_register", timeout=20).text
    match = re.search(r'name="__signature"\s+value="([^"]+)"', page)
    if not match:
        return {"ok": False, "reason": "signature_missing"}
    username = "aroagentic" + secrets.token_hex(3)
    files = {
        "__signature": (None, match.group(1)),
        "IsValidate": (None, "0"),
        "username": (None, username),
        "email": (None, email),
        "PrefixId": (None, "Register+Page16"),
    }
    response = session.post(
        "https://www.mql5.com/pt/auth_register_short",
        files=files,
        headers={
            "Referer": "https://www.mql5.com/pt/auth_register",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
        },
        timeout=20,
    )
    body = response.text.strip()
    if '"common":["error"]' in body.replace(" ", ""):
        return {"ok": False, "reason": "registration_rejected", "username": username, "detail": body[:120]}
    return {"ok": True, "username": username, "detail": body[:120]}


def _verify_inbox_mail(
    inbox_id: str,
    *,
    subject_hint: str = "",
    from_hint: str = "",
    domain_hint: str = "",
) -> dict[str, Any]:
    message = mail_mod.wait_for_message(
        inbox_id,
        subject_contains=subject_hint,
        from_contains=from_hint,
        timeout_sec=60,
        poll_sec=4,
    )
    if not message:
        return {"ok": False, "reason": "verification_mail_timeout"}
    text = mail_mod._message_text(message)
    link = mail_mod.extract_verification_link(text, domain_hint=domain_hint)
    password = mail_mod.extract_password_from_mail(text)
    if link:
        try:
            req = urllib.request.Request(link, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=20) as resp:
                _ = resp.read(256)
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
    return {
        "ok": bool(link or password),
        "verified": bool(link or password),
        "link_found": bool(link),
        "password_found": bool(password),
    }


def provision_platform(root, config: AroConfig, spec: PlatformSpec) -> dict[str, Any]:
    row = _account_row(root, spec.platform_id)
    if row.get("status") in {"active", "verified"} and not _should_retry(row):
        return {"ok": True, "platform_id": spec.platform_id, "status": row.get("status"), "action": "noop"}
    if not _should_retry(row):
        return {
            "ok": False,
            "platform_id": spec.platform_id,
            "status": row.get("status"),
            "action": "cooldown",
            "reason": row.get("blocker") or "retry_later",
        }

    _update_account(root, spec.platform_id, last_attempt_at=utcnow(), status="provisioning")

    if spec.platform_id == "wise":
        from agentic.aro import wise as wise_mod

        payload = wise_mod.status()
        status = "active" if payload.get("ok") else "blocked"
        row = _update_account(
            root,
            spec.platform_id,
            status=status,
            blocker="" if status == "active" else payload.get("reason") or "wise_unavailable",
            email=_public_email(config),
        )
        return {"ok": status == "active", "platform_id": spec.platform_id, "status": status, "wise": payload}

    if spec.platform_id == "agentmail":
        payload = mail_mod.status()
        status = "active" if payload.get("configured") and payload.get("verified") else "blocked"
        row = _update_account(
            root,
            spec.platform_id,
            status=status,
            email=payload.get("address") or "",
            blocker="" if status == "active" else "mail_not_verified",
        )
        return {"ok": status == "active", "platform_id": spec.platform_id, "status": status}

    inbox = mail_mod.ensure_inbox(display_name=spec.inbox_display)
    if not inbox.get("ok") and spec.platform_id == "99freelas":
        workana = _account_row(root, "workana")
        if workana.get("email"):
            inbox = {
                "ok": True,
                "email": workana.get("email"),
                "inbox_id": workana.get("email"),
                "shared_with": "workana",
            }
    if not inbox.get("ok") and spec.platform_id == "freelancer":
        contra = _account_row(root, "contra")
        if contra.get("email"):
            inbox = {
                "ok": True,
                "email": contra.get("email"),
                "inbox_id": contra.get("email"),
                "shared_with": "contra",
            }
    if not inbox.get("ok"):
        row = _update_account(
            root,
            spec.platform_id,
            status="blocked",
            blocker="agentmail_inbox_limit",
            detail=inbox.get("detail") or "",
        )
        return {"ok": False, "platform_id": spec.platform_id, "status": "blocked", "inbox": inbox}

    email = str(inbox.get("email") or "")
    _save_accounts_env({f"{spec.platform_id.upper()}_EMAIL": email})

    if spec.kind == "antibot":
        probe = _probe_url(spec.signup_url)
        status = "blocked" if probe.get("blocked") else "pending_browser"
        row = _update_account(
            root,
            spec.platform_id,
            status=status,
            email=email,
            signup_url=spec.signup_url,
            blocker="cloudflare_or_captcha" if probe.get("blocked") else "",
            probe=probe,
            note="Signup bloqueado por antibot neste IP; o ciclo re-tenta sem contornar CAPTCHA.",
        )
        return {
            "ok": False,
            "platform_id": spec.platform_id,
            "status": status,
            "email": email,
            "probe": probe,
        }

    if spec.kind == "browser":
        reg = _register_browser(spec, email, str(inbox.get("inbox_id") or email), config)
        if not reg.get("ok"):
            row = _update_account(
                root,
                spec.platform_id,
                status="blocked",
                email=email,
                blocker=reg.get("reason") or "signup_failed",
                detail=str(reg.get("detail") or "")[:200],
            )
            return {"ok": False, "platform_id": spec.platform_id, "status": "blocked", "register": reg, "email": email}
        status = "verified" if reg.get("verified") else "pending_verification"
        row = _update_account(
            root,
            spec.platform_id,
            status=status,
            email=email,
            verified=bool(reg.get("verified")),
            blocker="" if reg.get("verified") else "awaiting_verification_mail",
        )
        return {
            "ok": reg.get("verified") is True,
            "platform_id": spec.platform_id,
            "status": status,
            "email": email,
            "register": reg,
        }

    if spec.platform_id == "mql5":
        reg = _register_mql5(email)
        if not reg.get("ok"):
            row = _update_account(
                root,
                spec.platform_id,
                status="blocked",
                email=email,
                username=reg.get("username") or "",
                blocker=reg.get("reason") or "registration_failed",
                detail=reg.get("detail") or "",
            )
            return {"ok": False, "platform_id": spec.platform_id, "status": "blocked", "register": reg, "email": email}
        verify = _verify_inbox_mail(
            str(inbox.get("inbox_id") or email),
            subject_hint="MQL5",
            from_hint="mql5",
            domain_hint="mql5.com",
        )
        status = "verified" if verify.get("verified") else "pending_verification"
        _save_accounts_env(
            {
                "MQL5_USERNAME": str(reg.get("username") or ""),
                "MQL5_EMAIL": email,
            }
        )
        row = _update_account(
            root,
            spec.platform_id,
            status=status,
            email=email,
            username=reg.get("username") or "",
            verified=bool(verify.get("verified")),
            blocker="" if verify.get("verified") else "awaiting_mql5_mail",
        )
        return {
            "ok": verify.get("verified") is True,
            "platform_id": spec.platform_id,
            "status": status,
            "email": email,
            "username": reg.get("username"),
            "verify": verify,
        }

    row = _update_account(root, spec.platform_id, status="pending", email=email)
    return {"ok": False, "platform_id": spec.platform_id, "status": "pending", "email": email}


def run_provision(root, config: AroConfig) -> dict[str, Any]:
    if not _authorized(config):
        return {
            "ok": False,
            "action": "blocked",
            "reason": "ARO_OPERATOR_ACCOUNTS_AUTHORIZED ou ARO_MAY_OPEN_RECEIVE_ACCOUNTS desligado",
        }
    if not config.ready_for_outbound:
        return {"ok": False, "action": "blocked", "reason": "not ready_for_outbound"}

    steps: list[dict[str, Any]] = []
    for spec in PLATFORMS:
        steps.append(provision_platform(root, config, spec))

    active = [s for s in steps if s.get("status") in {"active", "verified"}]
    blocked = [s for s in steps if s.get("status") == "blocked"]
    append_jsonl(
        root,
        "journal.jsonl",
        {
            "kind": "accounts_provision",
            "active": len(active),
            "blocked": len(blocked),
        },
    )
    accounts = list_named(root, "accounts.json")
    return {
        "ok": len(active) >= 2,
        "action": "provision",
        "active": [{"platform_id": s.get("platform_id"), "status": s.get("status")} for s in active],
        "blocked": [
            {
                "platform_id": s.get("platform_id"),
                "status": s.get("status"),
                "blocker": _account_row(root, str(s.get("platform_id"))).get("blocker"),
            }
            for s in blocked
        ],
        "steps": steps,
        "accounts": accounts,
        "next": _next_provision(active, blocked, accounts),
    }


def _next_provision(
    active: list[dict[str, Any]],
    blocked: list[dict[str, Any]],
    accounts: list[dict[str, Any]],
) -> str:
    ids = {str(a.get("platform_id")) for a in accounts if a.get("status") in {"active", "verified"}}
    if "mql5" not in ids:
        return "continuar provisionamento MQL5 (re-tenta a cada 6h; antibot pode bloquear IP)"
    if "workana" not in ids and "99freelas" not in ids:
        return "Workana/99freelas bloqueados por antibot neste IP; usar MQL5 + catálogo Wise"
    return "contas base activas; responder jobs e captar clientes"
