"""ARO runtime config. Payout destination file is never written by the agent."""

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
WISE_ENV_FILE = Path("/root/.automaton/wise.env")


def _strip(value: str | None) -> str:
    return (value or "").strip().strip('"').strip("'")


def _money(name: str, default: str = "") -> str:
    return _strip(os.getenv(name)) or default


def _load_env_file(path: Path, *, overwrite: bool) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        value = val.strip().strip("'").strip('"')
        if overwrite:
            os.environ[key] = value
        else:
            os.environ.setdefault(key, value)


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
    wise_configured: bool
    payout_channel: str
    may_open_receive_accounts: bool
    base_limit_brl: str
    price_floor_brl: str
    p2p_authorized: bool
    stop_all: bool

    @property
    def money_rail_ready(self) -> bool:
        if self.payout_channel == "wise":
            return self.wise_configured
        return self.payout_destination_configured

    @property
    def ready_for_outbound(self) -> bool:
        return (
            self.commercial_outbound
            and self.money_rail_ready
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
    _load_env_file(ARO_ENV_FILE, overwrite=True)
    _load_env_file(WISE_ENV_FILE, overwrite=True)
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
    open_recv = _strip(os.getenv("ARO_MAY_OPEN_RECEIVE_ACCOUNTS")).lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    wise_token = _strip(os.getenv("WISE_API_TOKEN") or os.getenv("WISE_API_KEY"))
    channel = (_strip(os.getenv("ARO_PAYOUT_CHANNEL")) or "wise").lower()
    return AroConfig(
        owner_name=_strip(os.getenv("ARO_OWNER_NAME")),
        business_name=_strip(os.getenv("ARO_BUSINESS_NAME")),
        jurisdiction=JURISDICTION,
        base_currency=BASE_CURRENCY,
        owner_share_rate=OWNER_SHARE_RATE,
        owner_share_base="NET_COLLECTED_CASH",
        payout_interval=PAYOUT_INTERVAL,
        minimum_payout=_money("ARO_MINIMUM_PAYOUT", "50"),
        initial_operating_budget=_money("ARO_INITIAL_OPERATING_BUDGET", "50"),
        max_single_expense=_money("ARO_MAX_SINGLE_EXPENSE", "50"),
        max_daily_expense=_money("ARO_MAX_DAILY_EXPENSE", "50"),
        minimum_cash_reserve=_money("ARO_MINIMUM_CASH_RESERVE", "50"),
        payout_destination_configured=dest_ok or bool(wise_token),
        commercial_outbound=outbound,
        wise_configured=bool(wise_token),
        payout_channel=channel,
        may_open_receive_accounts=open_recv or outbound,
        base_limit_brl=_money("ARO_BASE_LIMIT_BRL", "50"),
        price_floor_brl=_money("ARO_PRICE_FLOOR_BRL", "250"),
        p2p_authorized=_strip(os.getenv("ARO_P2P_AUTHORIZED")).lower() in {
            "1",
            "true",
            "yes",
            "on",
        },
        stop_all=stop_all_active(root),
    )
