#!/usr/bin/env python3
"""Deterministic, public-data-only VWAP paper shadow.

This module cannot place an exchange order.  It consumes public, finalized
OHLCV candles and simulates conservative taker fills on the *next* candle.
Persistent state is the source of truth and is replaced atomically.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


ALLOWED_SYMBOLS = ("BTC/USDT", "ETH/USDT", "SOL/USDT")
TIMEFRAME = "5m"
TIMEFRAME_MS = 5 * 60 * 1000
STATE_VERSION = 2
DEFAULT_STATE_FILE = Path("/Agentic/orchestrator/vwap_shadow_state.json")
DEFAULT_LEDGER_FILE = Path("/Agentic/orchestrator/vwap_shadow_ledger.jsonl")
BYBIT_PUBLIC_API = "https://api.bybit.com"
BYBIT_KLINE_PATH = "/v5/market/kline"
MAX_KLINE_LIMIT = 200
MAX_RESPONSE_BYTES = 2_000_000


class PaperShadowError(RuntimeError):
    """Base class for failures that must not be silently repaired."""


class StateCorruptionError(PaperShadowError):
    """The persisted state or derived ledger is malformed or unsafe."""


class MarketDataError(PaperShadowError):
    """Public candle data is invalid, stale, or has an unrecoverable gap."""


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


@dataclass(frozen=True)
class Config:
    symbols: tuple[str, ...] = ALLOWED_SYMBOLS
    timeframe: str = TIMEFRAME
    timeframe_ms: int = TIMEFRAME_MS
    vwap_period: int = 20
    entry_band: float = 2.0
    exit_band: float = 0.5
    max_hold_candles: int = 48
    initial_balance_usdt: float = 100.0
    position_notional_usdt: float = 10.0
    minimum_notional_usdt: float = 5.0
    taker_fee_bps: float = 10.0
    spread_bps: float = 4.0
    slippage_bps: float = 5.0
    max_positions: int = 2
    daily_loss_limit_pct: float = 1.0
    max_consecutive_error_cycles: int = 3
    fetch_limit: int = 200
    http_timeout_seconds: float = 10.0

    @classmethod
    def from_env(cls) -> "Config":
        symbols_raw = os.getenv("VWAP_PAPER_SYMBOLS", ",".join(ALLOWED_SYMBOLS))
        symbols = tuple(item.strip().upper() for item in symbols_raw.split(",") if item.strip())
        config = cls(
            symbols=symbols,
            initial_balance_usdt=_env_float("VWAP_PAPER_INITIAL_BALANCE_USDT", 100.0),
            position_notional_usdt=_env_float("VWAP_PAPER_POSITION_NOTIONAL_USDT", 10.0),
            minimum_notional_usdt=_env_float("VWAP_PAPER_MIN_NOTIONAL_USDT", 5.0),
            taker_fee_bps=_env_float("VWAP_PAPER_TAKER_FEE_BPS", 10.0),
            spread_bps=_env_float("VWAP_PAPER_SPREAD_BPS", 4.0),
            slippage_bps=_env_float("VWAP_PAPER_SLIPPAGE_BPS", 5.0),
            max_positions=_env_int("VWAP_PAPER_MAX_POSITIONS", 2),
            daily_loss_limit_pct=_env_float("VWAP_PAPER_DAILY_LOSS_LIMIT_PCT", 1.0),
            http_timeout_seconds=_env_float("VWAP_PAPER_HTTP_TIMEOUT_SECONDS", 10.0),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if not self.symbols or len(self.symbols) > len(ALLOWED_SYMBOLS):
            raise ValueError("one to three paper symbols are required")
        if len(set(self.symbols)) != len(self.symbols):
            raise ValueError("paper symbols must be unique")
        if any(symbol not in ALLOWED_SYMBOLS for symbol in self.symbols):
            raise ValueError(f"paper symbols are restricted to {ALLOWED_SYMBOLS}")
        if self.timeframe != TIMEFRAME or self.timeframe_ms != TIMEFRAME_MS:
            raise ValueError("only finalized 5m candles are supported")
        if not 1 <= self.max_positions <= 2:
            raise ValueError("max_positions must remain between one and two")
        if self.vwap_period < 5 or self.max_hold_candles < 1:
            raise ValueError("invalid strategy window")
        if self.initial_balance_usdt <= 0:
            raise ValueError("initial virtual balance must be positive")
        if self.minimum_notional_usdt <= 0:
            raise ValueError("minimum notional must be positive")
        if self.position_notional_usdt < self.minimum_notional_usdt:
            raise ValueError("position notional is below the configured minimum")
        if self.position_notional_usdt > self.initial_balance_usdt:
            raise ValueError("position notional exceeds initial virtual balance")
        for name, value in (
            ("taker_fee_bps", self.taker_fee_bps),
            ("spread_bps", self.spread_bps),
            ("slippage_bps", self.slippage_bps),
            ("daily_loss_limit_pct", self.daily_loss_limit_pct),
        ):
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if self.fetch_limit < self.vwap_period + 3:
            raise ValueError("fetch_limit is too small for VWAP and next-candle fills")
        if self.fetch_limit > MAX_KLINE_LIMIT:
            raise ValueError(f"fetch_limit must not exceed {MAX_KLINE_LIMIT}")
        if not 0 < self.http_timeout_seconds <= 15:
            raise ValueError("public HTTP timeout must be between zero and 15 seconds")


def symbol_key(symbol: str) -> str:
    return symbol.replace("/", "_")


def utc_iso(timestamp_ms: int | None = None) -> str:
    if timestamp_ms is None:
        moment = datetime.now(timezone.utc)
    else:
        moment = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    return moment.isoformat()


def new_state(config: Config) -> dict[str, Any]:
    config.validate()
    return {
        "version": STATE_VERSION,
        "virtual": {
            "initial_usdt": config.initial_balance_usdt,
            "cash_usdt": config.initial_balance_usdt,
            "equity_usdt": config.initial_balance_usdt,
            "realized_pnl_usdt": 0.0,
            "unrealized_pnl_usdt": 0.0,
        },
        "symbols": {
            symbol_key(symbol): {
                "last_candle_ts": None,
                "last_mark_price": None,
                "pending_entry": None,
                "position": None,
                "pending_exit": None,
            }
            for symbol in config.symbols
        },
        "daily_realized_pnl_usdt": {},
        "trades": [],
        "trades_count": 0,
        "consecutive_error_cycles": 0,
        "last_run": None,
    }


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise StateCorruptionError(f"{field} is not numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise StateCorruptionError(f"{field} is not numeric") from exc
    if not math.isfinite(number):
        raise StateCorruptionError(f"{field} is not finite")
    return number


def validate_state(state: Any, config: Config) -> dict[str, Any]:
    if not isinstance(state, dict) or state.get("version") != STATE_VERSION:
        raise StateCorruptionError("state version is missing or unsupported")
    virtual = state.get("virtual")
    symbols = state.get("symbols")
    trades = state.get("trades")
    daily = state.get("daily_realized_pnl_usdt")
    if not isinstance(virtual, dict) or not isinstance(symbols, dict):
        raise StateCorruptionError("state virtual/symbols section is malformed")
    if not isinstance(trades, list) or not isinstance(daily, dict):
        raise StateCorruptionError("state trades/daily section is malformed")
    cash = _finite_number(virtual.get("cash_usdt"), "virtual.cash_usdt")
    initial = _finite_number(virtual.get("initial_usdt"), "virtual.initial_usdt")
    _finite_number(virtual.get("equity_usdt"), "virtual.equity_usdt")
    _finite_number(virtual.get("realized_pnl_usdt"), "virtual.realized_pnl_usdt")
    _finite_number(virtual.get("unrealized_pnl_usdt"), "virtual.unrealized_pnl_usdt")
    if cash < -0.000001 or initial <= 0:
        raise StateCorruptionError("virtual balance is invalid")
    if state.get("trades_count") != len(trades):
        raise StateCorruptionError("trades_count does not match the atomic trade journal")
    trade_ids: set[str] = set()
    for trade in trades:
        if not isinstance(trade, dict) or not isinstance(trade.get("trade_id"), str):
            raise StateCorruptionError("trade journal entry is malformed")
        if trade["trade_id"] in trade_ids:
            raise StateCorruptionError("duplicate trade_id in state")
        trade_ids.add(trade["trade_id"])
        for field in ("quantity", "entry_price", "exit_price", "pnl_usdt"):
            _finite_number(trade.get(field), f"trade.{field}")
    error_cycles = state.get("consecutive_error_cycles")
    if not isinstance(error_cycles, int) or isinstance(error_cycles, bool) or error_cycles < 0:
        raise StateCorruptionError("consecutive_error_cycles is invalid")
    position_count = 0
    for symbol in config.symbols:
        item = symbols.get(symbol_key(symbol))
        if not isinstance(item, dict):
            raise StateCorruptionError(f"missing state for {symbol}")
        timestamp = item.get("last_candle_ts")
        if timestamp is not None and (not isinstance(timestamp, int) or timestamp <= 0):
            raise StateCorruptionError(f"invalid last_candle_ts for {symbol}")
        for field in ("pending_entry", "position", "pending_exit"):
            if item.get(field) is not None and not isinstance(item.get(field), dict):
                raise StateCorruptionError(f"invalid {field} for {symbol}")
        mark = item.get("last_mark_price")
        if mark is not None and _finite_number(mark, f"{symbol}.last_mark_price") <= 0:
            raise StateCorruptionError(f"invalid mark price for {symbol}")
        pending_entry = item.get("pending_entry")
        position = item.get("position")
        pending_exit = item.get("pending_exit")
        if pending_entry is not None:
            if position is not None or pending_exit is not None:
                raise StateCorruptionError(f"conflicting pending entry state for {symbol}")
            signal_ts = pending_entry.get("signal_ts")
            if not isinstance(signal_ts, int) or signal_ts <= 0:
                raise StateCorruptionError(f"invalid pending entry timestamp for {symbol}")
            _finite_number(pending_entry.get("signal_z"), f"{symbol}.pending_entry.signal_z")
        if pending_exit is not None:
            if position is None:
                raise StateCorruptionError(f"pending exit without position for {symbol}")
            signal_ts = pending_exit.get("signal_ts")
            if not isinstance(signal_ts, int) or signal_ts <= 0:
                raise StateCorruptionError(f"invalid pending exit timestamp for {symbol}")
            _finite_number(pending_exit.get("signal_z"), f"{symbol}.pending_exit.signal_z")
            if pending_exit.get("reason") not in {"vwap_reversion", "max_hold"}:
                raise StateCorruptionError(f"invalid pending exit reason for {symbol}")
        if position is not None:
            position_count += 1
            for field in (
                "quantity",
                "entry_price",
                "entry_notional_usdt",
                "entry_fee_usdt",
                "entry_z",
            ):
                number = _finite_number(position.get(field), f"{symbol}.{field}")
                if field in {"quantity", "entry_price", "entry_notional_usdt"} and number <= 0:
                    raise StateCorruptionError(f"invalid {field} for {symbol}")
                if field == "entry_fee_usdt" and number < 0:
                    raise StateCorruptionError(f"invalid entry_fee_usdt for {symbol}")
            for field in ("entry_ts", "entry_signal_ts", "hold_count"):
                value = position.get(field)
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    raise StateCorruptionError(f"invalid {field} for {symbol}")
    if position_count > config.max_positions:
        raise StateCorruptionError("persisted positions exceed the hard position cap")
    for day, value in daily.items():
        if not isinstance(day, str):
            raise StateCorruptionError("invalid daily PnL key")
        _finite_number(value, f"daily_realized_pnl_usdt.{day}")
    return state


def load_state(path: Path, config: Config) -> dict[str, Any]:
    if not path.exists():
        return new_state(config)
    try:
        raw = path.read_text(encoding="utf-8")
        state = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StateCorruptionError(f"cannot load state: {type(exc).__name__}") from exc
    return validate_state(state, config)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except BaseException:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def save_state(path: Path, state: Mapping[str, Any], config: Config) -> None:
    validated = validate_state(dict(state), config)
    _atomic_write(path, json.dumps(validated, indent=2, sort_keys=True) + "\n")


def sync_ledger(path: Path, trades: Sequence[Mapping[str, Any]]) -> None:
    lines = [json.dumps(dict(trade), sort_keys=True, separators=(",", ":")) for trade in trades]
    payload = "\n".join(lines)
    if payload:
        payload += "\n"
    _atomic_write(path, payload)


class BybitPublicClient:
    """Minimal unauthenticated client for Bybit's public spot kline route."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        opener: Callable[..., Any] | None = None,
        base_url: str = BYBIT_PUBLIC_API,
    ):
        if not 0 < timeout_seconds <= 15:
            raise ValueError("public HTTP timeout must be between zero and 15 seconds")
        if base_url != BYBIT_PUBLIC_API:
            raise ValueError("public market-data host is fixed")
        self.timeout_seconds = float(timeout_seconds)
        self.base_url = base_url
        if opener is None:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({})).open
        self._opener = opener

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> list[list[Any]]:
        if symbol not in ALLOWED_SYMBOLS:
            raise MarketDataError("symbol is outside the public paper allowlist")
        if timeframe != TIMEFRAME:
            raise MarketDataError("only public 5m klines are allowed")
        bounded_limit = min(max(int(limit), 1), MAX_KLINE_LIMIT)
        query = urllib.parse.urlencode(
            {
                "category": "spot",
                "symbol": symbol.replace("/", ""),
                "interval": "5",
                "limit": str(bounded_limit),
            }
        )
        request = urllib.request.Request(
            f"{self.base_url}{BYBIT_KLINE_PATH}?{query}",
            method="GET",
            headers={
                "Accept": "application/json",
                "User-Agent": "Agentic-VWAP-Paper/2",
            },
        )
        try:
            response = self._opener(request, timeout=self.timeout_seconds)
            with response:
                status = getattr(response, "status", 200)
                if status != 200:
                    raise MarketDataError(f"public kline HTTP status {status}")
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except (TimeoutError, OSError, urllib.error.URLError) as exc:
            raise MarketDataError(f"public kline request failed: {type(exc).__name__}") from exc
        if len(raw) > MAX_RESPONSE_BYTES:
            raise MarketDataError("public kline response exceeds size limit")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise MarketDataError("public kline response is not valid JSON") from exc
        if not isinstance(payload, dict) or payload.get("retCode") != 0:
            raise MarketDataError("public kline retCode is not zero")
        result = payload.get("result")
        rows = result.get("list") if isinstance(result, dict) else None
        if not isinstance(rows, list):
            raise MarketDataError("public kline result.list is not a list")
        parsed: list[list[Any]] = []
        previous_timestamp: int | None = None
        for row in rows:
            if not isinstance(row, list) or len(row) < 6:
                raise MarketDataError("public kline row is malformed")
            try:
                timestamp = int(row[0])
            except (TypeError, ValueError) as exc:
                raise MarketDataError("public kline timestamp is invalid") from exc
            if previous_timestamp is not None and timestamp >= previous_timestamp:
                raise MarketDataError("public kline rows are not newest-first")
            previous_timestamp = timestamp
            parsed.append([timestamp, *row[1:6]])
        parsed.reverse()
        return parsed


def create_public_exchange(config: Config) -> BybitPublicClient:
    return BybitPublicClient(timeout_seconds=config.http_timeout_seconds)


def finalized_candles(raw: Sequence[Sequence[Any]], now_ms: int, config: Config) -> list[list[float]]:
    candles: list[list[float]] = []
    previous_timestamp = 0
    for row in raw:
        if not isinstance(row, Sequence) or len(row) < 6:
            raise MarketDataError("malformed OHLCV row")
        try:
            timestamp = int(row[0])
            values = [float(value) for value in row[1:6]]
        except (TypeError, ValueError) as exc:
            raise MarketDataError("non-numeric OHLCV row") from exc
        if timestamp <= previous_timestamp:
            raise MarketDataError("OHLCV timestamps are not strictly increasing")
        previous_timestamp = timestamp
        if any(not math.isfinite(value) for value in values):
            raise MarketDataError("non-finite OHLCV value")
        if min(values[:4]) <= 0 or values[4] < 0:
            raise MarketDataError("invalid OHLCV price or volume")
        if timestamp + config.timeframe_ms <= now_ms:
            candles.append([float(timestamp), *values])
    return candles


def calculate_signal(candles: Sequence[Sequence[float]], index: int, config: Config) -> tuple[float, float, float]:
    if index < config.vwap_period:
        raise MarketDataError("insufficient prior candles for VWAP")
    window = candles[index - config.vwap_period : index]
    typical_prices = [(row[2] + row[3] + row[4]) / 3.0 for row in window]
    volumes = [row[5] for row in window]
    volume_sum = sum(volumes)
    if volume_sum <= 0:
        raise MarketDataError("VWAP window has zero volume")
    vwap = sum(price * volume for price, volume in zip(typical_prices, volumes)) / volume_sum
    variance = sum((row[4] - vwap) ** 2 for row in window) / len(window)
    standard_deviation = math.sqrt(variance)
    if standard_deviation <= 0:
        raise MarketDataError("VWAP window has zero deviation")
    close = float(candles[index][4])
    return vwap, standard_deviation, (close - vwap) / standard_deviation


def modeled_taker_price(reference_open: float, side: str, config: Config) -> float:
    if reference_open <= 0 or not math.isfinite(reference_open):
        raise MarketDataError("invalid next-candle open")
    modeled_half_spread_bps = config.spread_bps / 2.0
    adverse_bps = modeled_half_spread_bps + config.slippage_bps
    if side == "buy":
        price = reference_open * (1.0 + adverse_bps / 10_000.0)
    elif side == "sell":
        price = reference_open * (1.0 - adverse_bps / 10_000.0)
    else:
        raise ValueError("side must be buy or sell")
    if price <= 0:
        raise MarketDataError("modeled execution price is invalid")
    return price


def active_positions(state: Mapping[str, Any]) -> int:
    return sum(1 for item in state["symbols"].values() if item.get("position") is not None)


def _daily_entry_allowed(state: Mapping[str, Any], timestamp_ms: int, config: Config) -> bool:
    day = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    realized = float(state["daily_realized_pnl_usdt"].get(day, 0.0))
    limit = float(state["virtual"]["initial_usdt"]) * config.daily_loss_limit_pct / 100.0
    return realized > -limit


def _fill_entry(
    state: dict[str, Any],
    symbol: str,
    item: dict[str, Any],
    candle: Sequence[float],
    config: Config,
) -> dict[str, Any]:
    pending = item["pending_entry"]
    item["pending_entry"] = None
    if active_positions(state) >= config.max_positions:
        return {"symbol": symbol, "action": "ENTRY_CANCELED", "reason": "max_positions"}
    fee_rate = config.taker_fee_bps / 10_000.0
    cash = float(state["virtual"]["cash_usdt"])
    affordable = cash / (1.0 + fee_rate)
    notional = min(config.position_notional_usdt, affordable)
    if notional + 1e-9 < config.minimum_notional_usdt:
        return {"symbol": symbol, "action": "ENTRY_CANCELED", "reason": "insufficient_virtual_cash"}
    price = modeled_taker_price(float(candle[1]), "buy", config)
    quantity = notional / price
    entry_fee = notional * fee_rate
    state["virtual"]["cash_usdt"] = cash - notional - entry_fee
    item["position"] = {
        "quantity": quantity,
        "entry_price": price,
        "entry_notional_usdt": notional,
        "entry_fee_usdt": entry_fee,
        "entry_ts": int(candle[0]),
        "entry_signal_ts": int(pending["signal_ts"]),
        "entry_z": float(pending["signal_z"]),
        "hold_count": 0,
    }
    return {
        "symbol": symbol,
        "action": "PAPER_ENTRY_FILLED",
        "price": round(price, 10),
        "quantity": round(quantity, 12),
        "notional_usdt": round(notional, 8),
        "fee_usdt": round(entry_fee, 8),
        "fill_model": "next_closed_candle_open_plus_half_spread_and_slippage",
    }


def _fill_exit(
    state: dict[str, Any],
    symbol: str,
    item: dict[str, Any],
    candle: Sequence[float],
    config: Config,
) -> tuple[dict[str, Any], dict[str, Any]]:
    position = item["position"]
    pending = item["pending_exit"]
    price = modeled_taker_price(float(candle[1]), "sell", config)
    quantity = float(position["quantity"])
    gross_proceeds = quantity * price
    exit_fee = gross_proceeds * config.taker_fee_bps / 10_000.0
    net_proceeds = gross_proceeds - exit_fee
    basis = float(position["entry_notional_usdt"]) + float(position["entry_fee_usdt"])
    pnl_usdt = net_proceeds - basis
    pnl_pct = pnl_usdt / basis * 100.0
    exit_ts = int(candle[0])
    trade_id = f"{symbol}:{int(position['entry_ts'])}:{exit_ts}"
    trade = {
        "trade_id": trade_id,
        "symbol": symbol,
        "side": "long",
        "entry_signal_ts": int(position["entry_signal_ts"]),
        "entry_ts": int(position["entry_ts"]),
        "exit_signal_ts": int(pending["signal_ts"]),
        "exit_ts": exit_ts,
        "entry_price": float(position["entry_price"]),
        "exit_price": price,
        "quantity": quantity,
        "entry_notional_usdt": float(position["entry_notional_usdt"]),
        "gross_proceeds_usdt": gross_proceeds,
        "entry_fee_usdt": float(position["entry_fee_usdt"]),
        "exit_fee_usdt": exit_fee,
        "pnl_usdt": pnl_usdt,
        "pnl_pct": pnl_pct,
        "hold_candles": int(position["hold_count"]),
        "exit_reason": str(pending["reason"]),
        "entry_z": float(position["entry_z"]),
        "exit_z": float(pending["signal_z"]),
        "fee_bps_per_side": config.taker_fee_bps,
        "spread_bps_round_trip": config.spread_bps,
        "slippage_bps_per_side": config.slippage_bps,
        "recorded_at": utc_iso(exit_ts),
    }
    state["virtual"]["cash_usdt"] = float(state["virtual"]["cash_usdt"]) + net_proceeds
    state["virtual"]["realized_pnl_usdt"] = float(state["virtual"]["realized_pnl_usdt"]) + pnl_usdt
    day = datetime.fromtimestamp(exit_ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    daily = state["daily_realized_pnl_usdt"]
    daily[day] = float(daily.get(day, 0.0)) + pnl_usdt
    state["trades"].append(trade)
    state["trades_count"] = len(state["trades"])
    item["position"] = None
    item["pending_exit"] = None
    event = {
        "symbol": symbol,
        "action": "PAPER_EXIT_FILLED",
        "trade_id": trade_id,
        "price": round(price, 10),
        "quantity": round(quantity, 12),
        "pnl_usdt": round(pnl_usdt, 8),
        "pnl_pct": round(pnl_pct, 6),
        "reason": trade["exit_reason"],
    }
    return event, trade


def process_candle(
    state: dict[str, Any],
    symbol: str,
    candles: Sequence[Sequence[float]],
    index: int,
    config: Config,
) -> list[dict[str, Any]]:
    item = state["symbols"][symbol_key(symbol)]
    candle = candles[index]
    timestamp = int(candle[0])
    events: list[dict[str, Any]] = []

    pending_exit = item.get("pending_exit")
    if item.get("position") is not None and pending_exit is not None and timestamp > int(pending_exit["signal_ts"]):
        event, _trade = _fill_exit(state, symbol, item, candle, config)
        events.append(event)
    else:
        pending_entry = item.get("pending_entry")
        if item.get("position") is None and pending_entry is not None and timestamp > int(pending_entry["signal_ts"]):
            events.append(_fill_entry(state, symbol, item, candle, config))

    vwap, deviation, z_score = calculate_signal(candles, index, config)
    item["last_mark_price"] = float(candle[4])
    position = item.get("position")
    if position is not None:
        position["hold_count"] = int(position.get("hold_count", 0)) + 1
        reason = None
        if z_score > -config.exit_band:
            reason = "vwap_reversion"
        elif position["hold_count"] >= config.max_hold_candles:
            reason = "max_hold"
        if reason is not None and item.get("pending_exit") is None:
            item["pending_exit"] = {
                "signal_ts": timestamp,
                "signal_z": z_score,
                "reason": reason,
            }
            events.append(
                {
                    "symbol": symbol,
                    "action": "PAPER_EXIT_SIGNAL",
                    "reason": reason,
                    "signal_ts": timestamp,
                    "z_score": round(z_score, 6),
                }
            )
    elif item.get("pending_entry") is None and z_score < -config.entry_band:
        if _daily_entry_allowed(state, timestamp, config):
            item["pending_entry"] = {
                "signal_ts": timestamp,
                "signal_z": z_score,
                "vwap": vwap,
                "deviation": deviation,
            }
            events.append(
                {
                    "symbol": symbol,
                    "action": "PAPER_ENTRY_SIGNAL",
                    "signal_ts": timestamp,
                    "z_score": round(z_score, 6),
                }
            )
        else:
            events.append({"symbol": symbol, "action": "ENTRY_BLOCKED", "reason": "daily_loss_limit"})
    item["last_candle_ts"] = timestamp
    return events


def _unseen_indices(
    candles: Sequence[Sequence[float]],
    last_candle_ts: int | None,
    config: Config,
) -> list[int]:
    if len(candles) < config.vwap_period + 1:
        raise MarketDataError("insufficient finalized candles")
    if last_candle_ts is None:
        return [len(candles) - 1]
    first_timestamp = int(candles[0][0])
    if first_timestamp > last_candle_ts + config.timeframe_ms:
        raise MarketDataError("state is older than retained public candle history")
    return [index for index, candle in enumerate(candles) if int(candle[0]) > last_candle_ts]


def update_equity(state: dict[str, Any]) -> None:
    market_value = 0.0
    unrealized = 0.0
    for item in state["symbols"].values():
        position = item.get("position")
        mark = item.get("last_mark_price")
        if position is None or mark is None:
            continue
        value = float(position["quantity"]) * float(mark)
        market_value += value
        basis = float(position["entry_notional_usdt"]) + float(position["entry_fee_usdt"])
        unrealized += value - basis
    state["virtual"]["unrealized_pnl_usdt"] = unrealized
    state["virtual"]["equity_usdt"] = float(state["virtual"]["cash_usdt"]) + market_value


def run_shadow_cycle(
    exchange: Any,
    config: Config,
    state_path: Path,
    ledger_path: Path,
    *,
    now_ms: int | None = None,
) -> dict[str, Any]:
    config.validate()
    state = load_state(state_path, config)
    clock_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
    events: list[dict[str, Any]] = []
    error_count = 0

    for symbol in config.symbols:
        try:
            raw = exchange.fetch_ohlcv(symbol, config.timeframe, limit=config.fetch_limit)
            candles = finalized_candles(raw, clock_ms, config)
            item = state["symbols"][symbol_key(symbol)]
            indices = _unseen_indices(candles, item.get("last_candle_ts"), config)
            for index in indices:
                if index < config.vwap_period:
                    raise MarketDataError("unseen candle lacks prior VWAP history")
                events.extend(process_candle(state, symbol, candles, index, config))
        except Exception as exc:  # a symbol failure blocks that symbol and is persisted
            error_count += 1
            events.append(
                {
                    "symbol": symbol,
                    "action": "ERROR",
                    "error_type": type(exc).__name__[:80],
                    "reason": str(exc)[:200],
                }
            )

    if error_count:
        state["consecutive_error_cycles"] = int(state.get("consecutive_error_cycles", 0)) + 1
    else:
        state["consecutive_error_cycles"] = 0
    update_equity(state)
    state["last_run"] = utc_iso(clock_ms)
    save_state(state_path, state, config)
    sync_ledger(ledger_path, state["trades"])

    halted = state["consecutive_error_cycles"] >= config.max_consecutive_error_cycles
    return {
        "mode": "paper_public_only",
        "time": state["last_run"],
        "symbols": list(config.symbols),
        "events": events,
        "errors": error_count,
        "consecutive_error_cycles": state["consecutive_error_cycles"],
        "halted": halted,
        "virtual": state["virtual"],
        "open_positions": active_positions(state),
        "trades_count": state["trades_count"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-file", type=Path, default=Path(os.getenv("VWAP_PAPER_STATE_FILE", DEFAULT_STATE_FILE)))
    parser.add_argument("--ledger-file", type=Path, default=Path(os.getenv("VWAP_PAPER_LEDGER_FILE", DEFAULT_LEDGER_FILE)))
    parser.add_argument("--loop", action="store_true", help="repeat every interval; default is one bounded cycle")
    parser.add_argument("--interval", type=int, default=300)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.interval < 60:
        print(json.dumps({"ok": False, "error": "interval must be at least 60 seconds"}))
        return 2
    try:
        config = Config.from_env()
        exchange = create_public_exchange(config)
    except (ValueError, PaperShadowError) as exc:
        print(json.dumps({"ok": False, "error_type": type(exc).__name__, "reason": str(exc)[:200]}))
        return 2

    while True:
        try:
            result = run_shadow_cycle(exchange, config, args.state_file, args.ledger_file)
        except StateCorruptionError as exc:
            print(json.dumps({"ok": False, "error_type": type(exc).__name__, "reason": str(exc)[:200]}), flush=True)
            return 2
        except Exception as exc:
            print(json.dumps({"ok": False, "error_type": type(exc).__name__, "reason": str(exc)[:200]}), flush=True)
            return 1
        print(json.dumps(result, sort_keys=True), flush=True)
        if result["halted"]:
            return 1
        if not args.loop:
            return 1 if result["errors"] else 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
