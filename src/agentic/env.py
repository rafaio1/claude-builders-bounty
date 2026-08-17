"""Load GhostCLI + Bybit from canonical files. Never print secret values."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any

AUTOMATON_ENV = Path("/root/.automaton/.env")
BYBIT_ENV = Path("/root/.automaton/bybit-murre.env")
MURRE_ENV = Path("/opt/murre/.env")
ROOT = Path(__file__).resolve().parents[2]
LOCAL_ENV = ROOT / ".env"

# Module-level cache so env files are read only once per process.
_APPLY_CACHE: dict[str, object] | None = None

# Keys whose values must never appear in logs/traces.
_SECRET_KEYS: frozenset[str] = frozenset(
    {
        "BYBIT_API_KEY",
        "BYBIT_API_SECRET",
        "BYBIT_REAL_API_KEY",
        "BYBIT_REAL_API_SECRET",
        "GHOSTCLI_API_KEY",
        "GHOSTCLI_KEY",
        "ANTHROPIC_API_KEY",
        "AGENTMAIL_API_KEY",
        "ARO_MAIL_ADDRESS",
    }
)

# Patterns used by mask_secrets to redact accidental leaks.
_MASK_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"(?i)((?:BYBIT_(?:REAL_)?API_(?:KEY|SECRET)|GHOSTCLI_(?:API_)?KEY|"
            r"ANTHROPIC_API_KEY|AGENTMAIL_API_KEY|ARO_MAIL_ADDRESS)"
            r"\s*[:=]\s*)[\"']?[\w\-\.~+/]{6,}={0,2}[\"']?"
        ),
        r'\1"***REDACTED***"',
    ),
    (re.compile(r"\b[A-Za-z0-9_\-\.~+/]{32,}={0,2}\b"), "***TOKEN_REDACTED***"),
)


def parse_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.is_file():
        return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        data[key.strip()] = val.strip().strip("'").strip('"')
    return data


def _load_into_environ() -> None:
    """Read canonical env files and populate os.environ (idempotent)."""
    merged: dict[str, str] = {}
    for path in (AUTOMATON_ENV, MURRE_ENV, BYBIT_ENV, LOCAL_ENV):
        merged.update(parse_env_file(path))
    for key, value in merged.items():
        os.environ.setdefault(key, value)

    key = os.environ.get("BYBIT_REAL_API_KEY") or os.environ.get("BYBIT_API_KEY") or ""
    secret = os.environ.get("BYBIT_REAL_API_SECRET") or os.environ.get("BYBIT_API_SECRET") or ""
    if key:
        os.environ.setdefault("BYBIT_API_KEY", key)
        os.environ.setdefault("BYBIT_REAL_API_KEY", key)
    if secret:
        os.environ.setdefault("BYBIT_API_SECRET", secret)
        os.environ.setdefault("BYBIT_REAL_API_SECRET", secret)
    os.environ.setdefault("BYBIT_MODE", "live")
    os.environ.setdefault("BYBIT_CATEGORY", "spot")
    os.environ.setdefault("BYBIT_ENV_FILE", str(BYBIT_ENV))
    os.environ.setdefault("AGENTIC_LIVE_TRADE", "0")
    ghost_key = os.environ.get("GHOSTCLI_API_KEY") or os.environ.get("GHOSTCLI_KEY") or ""
    if ghost_key:
        os.environ.setdefault("ANTHROPIC_API_KEY", ghost_key)
    ghost_base = (os.environ.get("GHOSTCLI_BASE_URL") or "https://ghostcli.dev").rstrip("/")
    if ghost_base.endswith("/v1"):
        ghost_base = ghost_base[:-3].rstrip("/")
    os.environ.setdefault("ANTHROPIC_BASE_URL", ghost_base or "https://ghostcli.dev")
    mail_env = Path("/root/.automaton/aro-mail.env")
    if mail_env.is_file():
        for mkey, mvalue in parse_env_file(mail_env).items():
            os.environ.setdefault(mkey, mvalue)


def apply() -> dict[str, object]:
    """Load env files once and return a status summary (no secret values)."""
    global _APPLY_CACHE
    if _APPLY_CACHE is not None:
        return _APPLY_CACHE

    _load_into_environ()

    _APPLY_CACHE = {
        "bybit_env_file": BYBIT_ENV.is_file(),
        "bybit_key": bool(os.environ.get("BYBIT_REAL_API_KEY") or os.environ.get("BYBIT_API_KEY")),
        "bybit_secret": bool(
            os.environ.get("BYBIT_REAL_API_SECRET") or os.environ.get("BYBIT_API_SECRET")
        ),
        "ghost_key": bool(os.environ.get("GHOSTCLI_API_KEY")),
        "claude": bool(shutil.which("claude")),
        "mail_key": bool(os.environ.get("AGENTMAIL_API_KEY")),
        "mail_address": bool(os.environ.get("ARO_MAIL_ADDRESS")),
        "mode": os.environ.get("BYBIT_MODE", ""),
        "category": os.environ.get("BYBIT_CATEGORY", ""),
        "live_trade": os.environ.get("AGENTIC_LIVE_TRADE", "0"),
    }
    return _APPLY_CACHE


def bybit_credentials() -> tuple[str, str]:
    apply()
    key = os.environ.get("BYBIT_REAL_API_KEY") or os.environ.get("BYBIT_API_KEY") or ""
    secret = os.environ.get("BYBIT_REAL_API_SECRET") or os.environ.get("BYBIT_API_SECRET") or ""
    if not key or not secret:
        raise RuntimeError("Bybit credentials missing in /root/.automaton/bybit-murre.env")
    return key, secret


def mask_secrets(text: Any) -> str:
    """Redact secret values from arbitrary text before logging/tracing.

    Use this on any string that originates from env state or may echo
    credential material. Non-string inputs are coerced safely.
    """
    if not isinstance(text, str):
        try:
            text = str(text)
        except Exception:
            return ""
    out = text
    for pattern, replacement in _MASK_PATTERNS:
        out = pattern.sub(replacement, out)
    return out
