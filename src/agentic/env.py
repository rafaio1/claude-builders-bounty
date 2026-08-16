"""Load GhostCLI + Bybit from canonical files. Never print secret values."""

from __future__ import annotations

import os
from pathlib import Path

AUTOMATON_ENV = Path("/root/.automaton/.env")
BYBIT_ENV = Path("/root/.automaton/bybit-murre.env")
MURRE_ENV = Path("/opt/murre/.env")
ROOT = Path(__file__).resolve().parents[2]
LOCAL_ENV = ROOT / ".env"


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


def apply() -> dict[str, object]:
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

    return {
        "bybit_env_file": BYBIT_ENV.is_file(),
        "bybit_key": bool(os.environ.get("BYBIT_REAL_API_KEY") or os.environ.get("BYBIT_API_KEY")),
        "bybit_secret": bool(os.environ.get("BYBIT_REAL_API_SECRET") or os.environ.get("BYBIT_API_SECRET")),
        "ghost_key": bool(os.environ.get("GHOSTCLI_API_KEY")),
        "mode": os.environ.get("BYBIT_MODE", ""),
        "category": os.environ.get("BYBIT_CATEGORY", ""),
        "live_trade": os.environ.get("AGENTIC_LIVE_TRADE", "0"),
    }


def bybit_credentials() -> tuple[str, str]:
    apply()
    key = os.environ.get("BYBIT_REAL_API_KEY") or os.environ.get("BYBIT_API_KEY") or ""
    secret = os.environ.get("BYBIT_REAL_API_SECRET") or os.environ.get("BYBIT_API_SECRET") or ""
    if not key or not secret:
        raise RuntimeError("Bybit credentials missing in /root/.automaton/bybit-murre.env")
    return key, secret
