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
HEALTH_PATH = Path("data") / "health.json"
LAST_TICK_PATH = Path("data") / "last_tick.json"

# Campos de ferramentas que DEVEM ser sanitizados (nunca gravar valores reais)
_SECRET_TOOL_FIELDS = frozenset(
    {"ghostcli", "bybit_key", "bybit_secret", "bybit_env_file"}
)

# TTL do cache de checagens estáveis (segundos). Itens que falharam na última
# verificação são sempre reexecutados no tick seguinte para detectar recuperação.
_CENSUS_CACHE_TTL_SECONDS = 90


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _monotonic() -> float:
    """Relógio monotónico para TTL; isolado para facilitar testes."""
    return time.monotonic()


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


class _CensusCache:
    """Cache em memória com TTL curto para checagens de ferramentas estáveis.

    Evita reexecutar `_which`/subprocess a cada tick quando nada mudou.
    Itens que falharam (`False`) nunca ficam em cache — são reavaliados no
    próximo tick para capturar instalação/configuração tardia.
    """

    def __init__(self, ttl_seconds: int = _CENSUS_CACHE_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[float, bool]] = {}

    def get(self, key: str) -> bool | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        ts, value = entry
        # Só devolve se for True e ainda dentro do TTL. Falhas nunca entram.
        if not value or (_monotonic() - ts) > self._ttl:
            self._store.pop(key, None)
            return None
        return value

    def put(self, key: str, value: bool) -> None:
        # Só armazena resultados positivos; negativos são sempre recalculados.
        if value:
            self._store[key] = (_monotonic(), True)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)


_census_cache = _CensusCache()


def _cached_check(key: str, check_fn: callable[[], bool]) -> bool:
    """Executa `check_fn` só se o cache não tiver um resultado válido recente."""
    cached = _census_cache.get(key)
    if cached is not None:
        return cached
    result = bool(check_fn())
    _census_cache.put(key, result)
    return result


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
    playwright = _cached_check(
        "playwright",
        lambda: bool(_which("playwright-cli")) and _cmd_ok(["playwright-cli", "--version"]),
    )
    playwright_mcp = _cached_check(
        "playwright_mcp",
        lambda: bool(_which("playwright-mcp")),
    )
    claude = _cached_check(
        "claude",
        lambda: bool(_which("claude")) and _cmd_ok(["claude", "--version"]),
    )
    jq = _cached_check("jq", lambda: bool(_which("jq")))
    ghostcli = _cached_check("ghostcli", lambda: bool(env.get("ghost_key")))
    bybit_key = _cached_check("bybit_key", lambda: bool(env.get("bybit_key")))
    bybit_secret = _cached_check("bybit_secret", lambda: bool(env.get("bybit_secret")))
    bybit_env_file = _cached_check(
        "bybit_env_file", lambda: bool(env.get("bybit_env_file"))
    )
    return {
        "generated_at": utcnow(),
        "last_tick": last_tick,
        "tools": {
            "playwright": playwright,
            "playwright_mcp": playwright_mcp,
            "jq": jq,
            "claude": claude,
            "ghostcli": ghostcli,
            "bybit_key": bybit_key,
            "bybit_secret": bybit_secret,
            "bybit_env_file": bybit_env_file,
        },
        "stats": {
            "playwright": playwright,
            "claude": claude,
            "ghostcli": ghostcli,
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
        raise RuntimeError("AGENTIC_LIVE_TRADE ligado recusado; o loop não opera Bybit")
    census = collect_census(settings.root)
    tools = census.get("tools") or {}
    from agentic.aro.cycle import run_cycle

    aro = run_cycle(
        settings.root,
        tools={
            "playwright_cli": bool(tools.get("playwright")),
            "playwright_mcp": bool(tools.get("playwright_mcp")),
            "jq": bool(tools.get("jq")),
        },
        ghostcli=bool(tools.get("ghostcli")),
        bybit=bool(tools.get("bybit_key") and tools.get("bybit_secret")),
        live_trade=False,
    )
    payload = {
        "ok": True,
        "generated_at": utcnow(),
        "running_branch_hint": "main/master",
        "live_trade": False,
        "interval_seconds": settings.interval_seconds,
        "ghostcli_configured": settings.has_ghostcli,
        "tools": tools,
        "last_tick": census.get("last_tick"),
        "aro": {
            "ok": bool(aro.get("ok")),
            "paused": bool(aro.get("paused")),
            "ready_for_outbound": bool(aro.get("ready_for_outbound")),
            "constitution_ok": bool(aro.get("constitution_ok")),
                "payout_destination_configured": bool(aro.get("payout_destination_configured")),
                "fiscal_destination": (aro.get("fiscal") or {}).get("destination") or "",
                "offers": len(aro.get("offers") or []),
            "next_action": (aro.get("decision") or {}).get("next_action"),
        },
    }
    missing = [
        name
        for name, present in tools.items()
        if name in {"playwright", "ghostcli", "bybit_key", "bybit_secret"} and not present
    ]
    payload["ok"] = not missing
    payload["missing"] = missing
    write_status(settings.root, payload)
    _write_health_snapshot(settings.root, tools, aro)
    _write_last_tick(settings.root, tools)
    return payload


def _write_last_tick(root: Path, tools: dict[str, Any]) -> Path:
    """Grava rastro leve de frescor do tick em data/last_tick.json (fora do git).

    Contém apenas timestamp ISO-8601 e contagem de ferramentas ok, para que
    portal/reviewer saibam se o loop está vivo entre censos sem depender do
    status.json completo.
    """
    path = Path(root) / LAST_TICK_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    ok_count = sum(1 for v in (tools or {}).values() if bool(v))
    snapshot = {
        "ts": utcnow(),
        "tools_ok": ok_count,
    }
    path.write_text(
        json.dumps(snapshot, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def _sanitize_tool_status(tools: dict[str, Any]) -> dict[str, bool]:
    """Retorna apenas flags booleanos; campos sensíveis viram True/False sem valores."""
    sanitized: dict[str, bool] = {}
    for name, value in (tools or {}).items():
        if name in _SECRET_TOOL_FIELDS:
            sanitized[name] = bool(value)
        else:
            sanitized[name] = bool(value)
    return sanitized


def _write_health_snapshot(
    root: Path, tools: dict[str, Any], aro: dict[str, Any]
) -> Path:
    """Grava snapshot sanitizado de saúde em data/health.json (gitignorado)."""
    path = Path(root) / HEALTH_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "generated_at": utcnow(),
        "live_trade": False,
        "tools": _sanitize_tool_status(tools),
        "aro": {
            "ok": bool((aro or {}).get("ok")),
            "paused": bool((aro or {}).get("paused")),
            "constitution_ok": bool((aro or {}).get("constitution_ok")),
            "ready_for_outbound": bool((aro or {}).get("ready_for_outbound")),
            "offers": len((aro or {}).get("offers") or []),
            "next_action": ((aro or {}).get("decision") or {}).get("next_action"),
        },
    }
    path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return path


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
