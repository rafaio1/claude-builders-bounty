from __future__ import annotations

import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentic.config import Settings, load_settings
from agentic.env import apply
from agentic.locks import RunLock

STATUS_PATH = Path("data") / "status.json"


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _which(name: str) -> str:
    return shutil.which(name) or ""


def _cmd_ok(args: list[str], *, timeout: float = 8.0) -> bool:
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def collect_census(root: Path) -> dict[str, Any]:
    env = apply()
    status_file = Path(root) / STATUS_PATH
    last_tick = ""
    if status_file.is_file():
        try:
            payload = json.loads(status_file.read_text(encoding="utf-8"))
            last_tick = str(payload.get("generated_at") or "")
        except (OSError, json.JSONDecodeError, TypeError):
            last_tick = ""
    playwright = bool(_which("playwright-cli")) and _cmd_ok(["playwright-cli", "--version"])
    playwright_mcp = bool(_which("playwright-mcp"))
    return {
        "generated_at": utcnow(),
        "last_tick": last_tick,
        "tools": {
            "playwright": playwright,
            "playwright_mcp": playwright_mcp,
            "jq": bool(_which("jq")),
            "ghostcli": bool(env.get("ghost_key")),
            "bybit_key": bool(env.get("bybit_key")),
            "bybit_secret": bool(env.get("bybit_secret")),
            "bybit_env_file": bool(env.get("bybit_env_file")),
        },
        "stats": {
            "playwright": playwright,
            "ghostcli": bool(env.get("ghost_key")),
        },
    }


def write_status(root: Path, payload: dict[str, Any]) -> Path:
    path = Path(root) / STATUS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return path


def tick(settings: Settings) -> dict[str, Any]:
    if settings.live_trade:
        raise RuntimeError("AGENTIC_LIVE_TRADE=1 recusado; o loop não opera Bybit")
    census = collect_census(settings.root)
    payload = {
        "ok": True,
        "generated_at": utcnow(),
        "running_branch_hint": "main/master",
        "live_trade": False,
        "interval_seconds": settings.interval_seconds,
        "ghostcli_configured": settings.has_ghostcli,
        "tools": census.get("tools"),
        "last_tick": census.get("last_tick"),
    }
    missing = [
        name
        for name, present in (census.get("tools") or {}).items()
        if name in {"playwright", "ghostcli", "bybit_key", "bybit_secret"} and not present
    ]
    payload["ok"] = not missing
    payload["missing"] = missing
    write_status(settings.root, payload)
    return payload


def run_loop(settings: Settings | None = None, *, once: bool = False) -> int:
    settings = settings or load_settings()
    stop = settings.root / ".agentic-loop.stop"
    if stop.exists():
        stop.unlink()
    while True:
        if stop.exists():
            return 0
        with RunLock(settings.lock_path, busy="outro loop Agentic já está rodando"):
            payload = tick(settings)
        if once:
            print(json.dumps(payload, ensure_ascii=False, default=str))
            return 0 if payload.get("ok") else 1
        time.sleep(max(15, int(settings.interval_seconds)))
