"""ARO runtime config. Payout destination is never written by the agent."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from agentic.aro.constitution import (
    BASE_CURRENCY,
    JURISDICTION,
    OWNER_SHARE_RATE,
    PAYOUT_INTERVAL,
    STOP_FILENAME,
)

PAYOUT_DEST_FILE = Path("/root/.automaton/aro-payout.dest")
ARO_ENV_FILE = Path("/root/.automaton/aro.env")


def _strip(value: str | None) -> str:
    return (value or "").strip().strip('"').strip("'")


def _money(name: str, default: str = "") -> str:
    return _strip(os.getenv(name)) or default


@dataclass(frozen=True)
class AroConfig:
    owner_name: str
    business_name: str
    jurisdiction: str
    base_currency: str
    owner_share_rate: float
    owner_share_base: str
    payout_interval: str
    minimum_payout: str
    initial_operating_budget: str
    max_single_expense: str
    max_daily_expense: str
    minimum_cash_reserve: str
    payout_destination_configured: bool
    commercial_outbound: bool
    price_floor_brl: str
    stop_all: bool

    @property
    def ready_for_outbound(self) -> bool:
        return (
            self.commercial_outbound
            and self.payout_destination_configured
            and bool(self.owner_name)
            and bool(self.business_name)
            and not self.stop_all
        )


def stop_all_active(root: Path) -> bool:
    if (Path(root) / STOP_FILENAME).is_file():
        return True
    flag = _strip(os.getenv("ARO_STOP_ALL_OPERATIONS")).lower()
    return flag in {"1", "true", "yes", "on", "STOP_ALL_OPERATIONS".lower()}


def load_aro_config(root: Path) -> AroConfig:
    if ARO_ENV_FILE.is_file():
        for raw in ARO_ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip("'").strip('"'))
    dest_ok = PAYOUT_DEST_FILE.is_file() and PAYOUT_DEST_FILE.stat().st_size > 0
    if dest_ok:
        mode = PAYOUT_DEST_FILE.stat().st_mode & 0o777
        dest_ok = (mode & 0o077) == 0
    outbound = _strip(os.getenv("ARO_COMMERCIAL_OUTBOUND")).lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    return AroConfig(
        owner_name=_strip(os.getenv("ARO_OWNER_NAME")),
        business_name=_strip(os.getenv("ARO_BUSINESS_NAME")),
        jurisdiction=JURISDICTION,
        base_currency=BASE_CURRENCY,
        owner_share_rate=OWNER_SHARE_RATE,
        owner_share_base="NET_COLLECTED_CASH",
        payout_interval=PAYOUT_INTERVAL,
        minimum_payout=_money("ARO_MINIMUM_PAYOUT"),
        initial_operating_budget=_money("ARO_INITIAL_OPERATING_BUDGET"),
        max_single_expense=_money("ARO_MAX_SINGLE_EXPENSE"),
        max_daily_expense=_money("ARO_MAX_DAILY_EXPENSE"),
        minimum_cash_reserve=_money("ARO_MINIMUM_CASH_RESERVE"),
        payout_destination_configured=dest_ok,
        commercial_outbound=outbound,
        price_floor_brl=_money("ARO_PRICE_FLOOR_BRL", "250"),
        stop_all=stop_all_active(root),
    )
