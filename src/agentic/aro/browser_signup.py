"""Browser signup via playwright-cli. No CAPTCHA bypass."""

from __future__ import annotations

import re
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from agentic import mail as mail_mod

ROOT = Path(__file__).resolve().parents[3]
PLAYWRIGHT_CONFIG = str(ROOT / ".playwright" / "cli.config.json")
USER_AGENT_TIMEOUT = 120


def _cli(*args: str) -> tuple[int, str]:
    if args and args[0] == "open":
        cmd = ["playwright-cli", "open", "--config", PLAYWRIGHT_CONFIG, args[1]]
    else:
        cmd = ["playwright-cli", *args]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=USER_AGENT_TIMEOUT,
            cwd=str(ROOT),
        )
        return result.returncode, (result.stdout or "") + (result.stderr or "")
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return 1, type(exc).__name__


def _close_browser() -> None:
    _cli("close")


def _snapshot_text() -> str:
    _, out = _cli("snapshot")
    return out


def _freelancer_error(text: str) -> str:
    for line in text.splitlines():
        if "alert" in line.lower() and "ref=" in line:
            cleaned = re.sub(r"\[ref=[^\]]+\]", "", line).strip("- ")
            if cleaned:
                return cleaned[:200]
    if "valid email" in text.lower():
        return "invalid_email_rejected"
    return ""


def register_contra(
    email: str,
    *,
    first_name: str = "ARO",
    last_name: str = "Agentic",
) -> dict[str, Any]:
    _close_browser()
    code, out = _cli("open", "https://contra.com/sign-up")
    if code != 0 and "opened" not in out.lower() and "page url" not in out.lower():
        return {"ok": False, "reason": "browser_open_failed", "detail": out[:200]}
    steps = [
        _cli("fill", "e36", first_name),
        _cli("fill", "e37", last_name),
        _cli("fill", "e38", email),
        _cli("click", "e41"),
    ]
    time.sleep(3)
    snap = _snapshot_text()
    _close_browser()
    failed = [s for s in steps if s[0] != 0]
    if failed:
        return {"ok": False, "reason": "form_fill_failed", "detail": failed[0][1][:200]}
    if "sign-up" in snap.lower() and "continue" in snap.lower() and email.lower() in snap.lower():
        return {
            "ok": False,
            "reason": "signup_not_accepted",
            "detail": "formulário não avançou; email pode ser rejeitado pela plataforma",
            "email": email,
        }
    return {"ok": True, "reason": "submitted", "email": email}


def register_freelancer(
    email: str,
    password: str,
    *,
    first_name: str = "ARO",
    last_name: str = "Agentic",
) -> dict[str, Any]:
    _close_browser()
    code, out = _cli("open", "https://www.freelancer.com/signup")
    if code != 0 and "opened" not in out.lower() and "page url" not in out.lower():
        return {"ok": False, "reason": "browser_open_failed", "detail": out[:200]}
    steps = [
        _cli("fill", "e26", first_name),
        _cli("fill", "e31", last_name),
        _cli("fill", "e36", email),
        _cli("fill", "e42", password),
        _cli("click", "e51"),
        _cli("click", "e62"),
    ]
    time.sleep(2)
    snap = _snapshot_text()
    _close_browser()
    failed = [s for s in steps if s[0] != 0]
    if failed:
        return {"ok": False, "reason": "form_fill_failed", "detail": failed[0][1][:200]}
    err = _freelancer_error(snap)
    if err:
        return {"ok": False, "reason": err, "email": email}
    if "/signup" in snap.lower() and "join freelancer" in snap.lower():
        return {
            "ok": False,
            "reason": "signup_not_accepted",
            "detail": "permaneceu na página de signup",
            "email": email,
        }
    return {"ok": True, "reason": "submitted", "email": email, "password_set": True}


def verify_platform_mail(
    inbox_id: str,
    *,
    from_hint: str,
    domain_hint: str = "",
    subject_hint: str = "",
) -> dict[str, Any]:
    message = mail_mod.wait_for_message(
        inbox_id,
        from_contains=from_hint,
        subject_contains=subject_hint,
        timeout_sec=90,
        poll_sec=5,
    )
    if not message:
        return {"ok": False, "verified": False, "reason": "verification_mail_timeout"}
    text = mail_mod._message_text(message)
    link = mail_mod.extract_verification_link(text, domain_hint=domain_hint)
    password = mail_mod.extract_password_from_mail(text)
    if link:
        try:
            req = urllib.request.Request(
                link,
                headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0.0.0"},
            )
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


def generated_password() -> str:
    return secrets.token_urlsafe(14) + "Aa1!"
