from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _strip(value: str | None) -> str:
    return (value or "").strip().strip('"').strip("'")


@dataclass(frozen=True)
class Settings:
    root: Path
    lock_path: Path
    ghostcli_api_key: str
    ghostcli_base_url: str
    ghostcli_model: str
    ghostcli_orchestrator_model: str
    interval_seconds: int
    live_trade: bool

    @property
    def has_ghostcli(self) -> bool:
        return bool(self.ghostcli_api_key)


def load_settings(root: Path | None = None) -> Settings:
    from agentic.env import apply

    apply()
    base = Path(root) if root is not None else ROOT
    interval_raw = _strip(os.getenv("AGENTIC_INTERVAL_SECONDS")) or "90"
    try:
        interval = max(15, int(interval_raw))
    except ValueError:
        interval = 90
    live = _strip(os.getenv("AGENTIC_LIVE_TRADE")).lower() in {"1", "true", "yes", "on"}
    ghost_base = _strip(os.getenv("GHOSTCLI_BASE_URL")) or "https://ghostcli.dev"
    if not ghost_base.rstrip("/").endswith("/v1"):
        ghost_base = ghost_base.rstrip("/") + "/v1"
    model = _strip(os.getenv("GHOSTCLI_MODEL")) or "claude-sonnet-5[1m]"
    orch = _strip(os.getenv("GHOSTCLI_ORCHESTRATOR_MODEL")) or "claude-fable-5[1m]"
    return Settings(
        root=base,
        lock_path=base / ".agentic.lock",
        ghostcli_api_key=_strip(os.getenv("GHOSTCLI_API_KEY"))
        or _strip(os.getenv("GHOSTCLI_KEY")),
        ghostcli_base_url=ghost_base,
        ghostcli_model=model,
        ghostcli_orchestrator_model=orch,
        interval_seconds=interval,
        live_trade=live,
    )
