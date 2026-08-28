#!/usr/bin/env python3
"""Fail-closed token and cost governor for persistent Agentic Codex roles."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import revenue_db

WORKSPACE = Path("/Agentic")
DEFAULT_CONFIG_PATH = WORKSPACE / "config/codex_budget_governor.json"
DEFAULT_STATE_PATH = WORKSPACE / "state/codex_budget_governor.json"
DEFAULT_DB_PATH = WORKSPACE / "data/aro/revenue_control_plane_v2.db"
DEFAULT_LEDGER_PATH = WORKSPACE / "data/aro/realized_revenue_ledger.jsonl"
DEFAULT_ROLLOUT_ROOT = Path("/root/.codex/sessions")

ROLE_KEYS = ("bug_bounty", "revenue_generator", "contador", "integrator")
ROLE_MARKERS = {
    "bug_bounty": "OPERADOR DE BUG BOUNTY",
    "revenue_generator": "REVENUE BUILDER",
    "contador": "CONTADOR FINANCEIRO",
    "integrator": "REVIEWER INTEGRATOR",
}
TOKEN_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
)
PROMPT_ACTIONS = {"recover", "relaunch", "reorient"}
BOOTSTRAP_READ_LIMIT = 256 * 1024
BOOTSTRAP_HEAD_LIMIT = 64 * 1024


@dataclass(frozen=True)
class RevenueSnapshot:
    mode: str
    realized_usd: float
    verified: bool
    reason: str


@dataclass(frozen=True)
class RoleBudgetDecision:
    role: str
    allowed_prompt: bool
    recover_idle: bool
    should_interrupt: bool
    exhausted: bool
    tokens_today: int
    turn_tokens: int
    estimated_cost_usd: float | None
    next_wake_at: float
    active_session_id: str | None
    reason: str


@dataclass(frozen=True)
class BudgetSnapshot:
    enabled: bool
    revenue_mode: str
    realized_revenue_usd: float
    revenue_verified: bool
    revenue_reason: str
    day: str
    total_tokens_today: int
    estimated_cost_usd: float | None
    telemetry_stale: bool
    telemetry_errors: tuple[str, ...]
    roles: dict[str, RoleBudgetDecision]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_day(now: float) -> str:
    return datetime.fromtimestamp(now, tz=UTC).date().isoformat()


def _next_utc_day(now: float) -> float:
    current = datetime.fromtimestamp(now, tz=UTC)
    tomorrow = datetime.combine(current.date() + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    return tomorrow.timestamp()


def _empty_usage() -> dict[str, int]:
    return {field: 0 for field in (*TOKEN_FIELDS, "total_tokens")}


def _add_usage(target: dict[str, int], delta: Mapping[str, int]) -> None:
    for field in (*TOKEN_FIELDS, "total_tokens"):
        target[field] = int(target.get(field, 0)) + max(0, int(delta.get(field, 0)))


def _atomic_json_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def default_runtime_state(now: float) -> dict[str, Any]:
    return {
        "version": 1,
        "day": _utc_day(now),
        "day_total_tokens": 0,
        "files": {},
        "sessions": {},
        "roles": {
            role: {
                "tokens_today": 0,
                "usage_today": _empty_usage(),
                "active_session_id": None,
                "active_session_mtime": 0.0,
                "turn_tokens": 0,
                "last_inference_at": 0.0,
                "last_interrupt_session_id": None,
                "last_interrupt_day": None,
            }
            for role in ROLE_KEYS
        },
    }


def load_runtime_state(path: Path, now: float) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_runtime_state(now)
    if not isinstance(loaded, dict) or loaded.get("version") != 1:
        return default_runtime_state(now)
    default = default_runtime_state(now)
    for key in ("files", "sessions", "roles"):
        loaded.setdefault(key, default[key])
    loaded.setdefault("day", default["day"])
    loaded.setdefault("day_total_tokens", 0)
    for role in ROLE_KEYS:
        current = loaded["roles"].setdefault(role, default["roles"][role])
        for key, value in default["roles"][role].items():
            current.setdefault(key, value)
    return loaded


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != 1:
        raise ValueError("budget governor config version must be 1")
    modes = payload.get("modes")
    if not isinstance(modes, dict) or not {"zero_revenue", "funded"}.issubset(modes):
        raise ValueError("budget governor config requires zero_revenue and funded modes")
    for mode_name, mode in modes.items():
        roles = mode.get("roles", {})
        unknown = set(roles) - set(ROLE_KEYS)
        if unknown:
            raise ValueError(f"forbidden role(s) in {mode_name}: {sorted(unknown)}")
        missing = set(ROLE_KEYS) - set(roles)
        if missing:
            raise ValueError(f"missing role(s) in {mode_name}: {sorted(missing)}")
        if int(mode.get("max_daily_total_tokens", 0)) <= 0:
            raise ValueError(f"invalid daily token cap in {mode_name}")
    return payload


def _walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _settled_ledger_keys(path: Path) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8", errors="strict") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid realized ledger line {number}") from error
            for item in _walk_dicts(value):
                provider = item.get("provider") or item.get("settlement_provider")
                transaction = item.get("transaction_id") or item.get("tx_id")
                status = str(item.get("status", "")).lower()
                recognized = item.get("revenue_recognized") is True or item.get("confirmed") is True
                if status in {"confirmed", "settled", "paid", "received"}:
                    recognized = True
                if provider and transaction and recognized:
                    keys.add((str(provider), str(transaction)))
    return keys


def read_revenue_snapshot(
    db_path: Path,
    ledger_path: Path,
    recognized_currencies: set[str],
) -> RevenueSnapshot:
    # Kept in the signature for deployment compatibility only.  The legacy
    # JSONL ledger is never an authority for funded mode.
    _ = ledger_path
    try:
        truth = revenue_db.read_realized_revenue(db_path, recognized_currencies)
    except (OSError, ValueError, sqlite3.Error) as error:
        return RevenueSnapshot("zero_revenue", 0.0, False, f"revenue_db_unavailable:{type(error).__name__}")
    if not bool(truth.get("verified")):
        return RevenueSnapshot(
            "zero_revenue", 0.0, False, str(truth.get("reason") or "unverified_revenue")
        )
    realized = sum(
        float(amount) for amount in dict(truth.get("realized_revenue") or {}).values()
    )
    if realized <= 0:
        return RevenueSnapshot(
            "zero_revenue", 0.0, True, str(truth.get("reason") or "no_confirmed_settlements")
        )
    return RevenueSnapshot(
        "funded", realized, True, str(truth.get("reason") or "confirmed_settlements_reconciled")
    )


def estimate_cost_usd(
    model: str,
    usage: Mapping[str, int],
    pricing: Mapping[str, Any],
) -> float | None:
    rates = pricing.get(model)
    if not isinstance(rates, dict):
        return None if any(int(usage.get(field, 0)) > 0 for field in TOKEN_FIELDS) else 0.0
    total = 0.0
    for field in TOKEN_FIELDS:
        count = max(0, int(usage.get(field, 0)))
        if count == 0:
            continue
        rate = rates.get(field)
        if rate is None:
            return None
        total += count * float(rate) / 1_000_000.0
    return total


def _content_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_content_text(child) for child in value.values())
    if isinstance(value, list):
        return " ".join(_content_text(child) for child in value)
    return ""


def _role_from_text(value: str) -> str | None:
    upper = value.upper()
    for role, marker in ROLE_MARKERS.items():
        if marker in upper:
            return role
    return None


class RolloutMeter:
    def __init__(self, root: Path, *, lookback_seconds: int, max_files: int):
        self.root = root
        self.lookback_seconds = lookback_seconds
        self.max_files = max_files

    def _candidates(self, now: float) -> tuple[list[Path], list[str]]:
        if not self.root.is_dir():
            return [], ["rollout_root_missing"]
        candidates: list[tuple[float, Path]] = []
        try:
            for path in self.root.rglob("*.jsonl"):
                try:
                    modified = path.stat().st_mtime
                except OSError:
                    continue
                if now - modified <= self.lookback_seconds:
                    candidates.append((modified, path))
        except OSError:
            return [], ["rollout_scan_failed"]
        candidates.sort(reverse=True)
        errors = []
        if len(candidates) > self.max_files:
            errors.append("rollout_file_limit_exceeded")
        return [path for _modified, path in candidates[: self.max_files]], errors

    def update(self, state: dict[str, Any], now: float) -> list[str]:
        day = _utc_day(now)
        if state.get("day") != day:
            state["day"] = day
            state["day_total_tokens"] = 0
            for role in ROLE_KEYS:
                role_state = state["roles"][role]
                role_state["tokens_today"] = 0
                role_state["usage_today"] = _empty_usage()

        paths, errors = self._candidates(now)
        for path in paths:
            error = self._update_file(state, path)
            if error:
                errors.append(error)
        state["last_telemetry_at"] = now
        state["telemetry_errors"] = sorted(set(errors))
        return errors

    def _update_file(self, state: dict[str, Any], path: Path) -> str | None:
        key = str(path)
        try:
            stat = path.stat()
        except OSError:
            return "rollout_stat_failed"
        known_file = key in state["files"]
        file_state = state["files"].setdefault(
            key,
            {"inode": stat.st_ino, "offset": 0, "session_id": None, "role": None, "cwd": None},
        )
        if file_state.get("inode") != stat.st_ino or stat.st_size < int(file_state.get("offset", 0)):
            file_state.update({"inode": stat.st_ino, "offset": 0})
            known_file = False
        offset = int(file_state.get("offset", 0))
        bootstrap_limited = not known_file and offset == 0 and stat.st_size > BOOTSTRAP_READ_LIMIT
        try:
            with path.open("rb") as handle:
                if bootstrap_limited:
                    # Identity lives at the start and cumulative token totals live near
                    # the tail. Read a fixed total budget instead of replaying a huge
                    # historical rollout on first sight.
                    head = handle.read(BOOTSTRAP_HEAD_LIMIT)
                    tail_start = max(BOOTSTRAP_HEAD_LIMIT, stat.st_size - (BOOTSTRAP_READ_LIMIT - BOOTSTRAP_HEAD_LIMIT))
                    handle.seek(tail_start)
                    tail = handle.read(BOOTSTRAP_READ_LIMIT - BOOTSTRAP_HEAD_LIMIT)
                else:
                    handle.seek(offset)
                    raw = handle.read()
        except OSError:
            return "rollout_read_failed"
        if bootstrap_limited:
            head_newline = head.rfind(b"\n")
            head_complete = head[: head_newline + 1] if head_newline >= 0 else b""
            tail_last_newline = tail.rfind(b"\n")
            if tail_last_newline < 0:
                return "bootstrap_limited"
            tail_complete = tail[: tail_last_newline + 1]
            if tail_start:
                tail_first_newline = tail_complete.find(b"\n")
                tail_complete = tail_complete[tail_first_newline + 1 :] if tail_first_newline >= 0 else b""
            raw = head_complete + tail_complete
            file_state["offset"] = tail_start + tail_last_newline + 1
        if not raw:
            return None
        newline = raw.rfind(b"\n")
        if newline < 0:
            return None
        complete = raw[: newline + 1]
        if not bootstrap_limited:
            file_state["offset"] = offset + len(complete)
        token_events: list[dict[str, int]] = []
        for raw_line in complete.splitlines():
            try:
                event = json.loads(raw_line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                return "rollout_json_invalid"
            payload = event.get("payload", {})
            event_type = event.get("type")
            if event_type == "session_meta":
                file_state["session_id"] = payload.get("id") or file_state.get("session_id")
                file_state["cwd"] = payload.get("cwd") or file_state.get("cwd")
            elif event_type == "response_item" and payload.get("role") == "user":
                detected = _role_from_text(_content_text(payload.get("content")))
                if detected:
                    file_state["role"] = detected
            elif event_type == "event_msg" and payload.get("type") == "token_count":
                usage = payload.get("info", {}).get("total_token_usage", {})
                token_events.append({field: max(0, int(usage.get(field, 0))) for field in (*TOKEN_FIELDS, "total_tokens")})

        role = file_state.get("role")
        session_id = file_state.get("session_id")
        if file_state.get("cwd") != str(WORKSPACE) or role not in ROLE_KEYS or not session_id:
            return None
        session = state["sessions"].setdefault(
            session_id,
            {"role": role, "last_usage": _empty_usage(), "last_mtime": 0.0},
        )
        if session.get("role") != role:
            return "rollout_role_conflict"
        for usage in token_events:
            previous = session.get("last_usage", _empty_usage())
            if int(usage["total_tokens"]) < int(previous.get("total_tokens", 0)):
                return "rollout_token_counter_regressed"
            delta = {
                field: max(0, int(usage.get(field, 0)) - int(previous.get(field, 0)))
                for field in (*TOKEN_FIELDS, "total_tokens")
            }
            _add_usage(state["roles"][role]["usage_today"], delta)
            state["roles"][role]["tokens_today"] += delta["total_tokens"]
            state["day_total_tokens"] += delta["total_tokens"]
            session["last_usage"] = usage
        session["last_mtime"] = stat.st_mtime
        role_state = state["roles"][role]
        if stat.st_mtime >= float(role_state.get("active_session_mtime", 0.0)):
            role_state["active_session_mtime"] = stat.st_mtime
            role_state["active_session_id"] = session_id
            role_state["turn_tokens"] = int(session.get("last_usage", {}).get("total_tokens", 0))
        return "bootstrap_limited" if bootstrap_limited else None


class BudgetGovernor:
    def __init__(
        self,
        *,
        config_path: Path = DEFAULT_CONFIG_PATH,
        state_path: Path = DEFAULT_STATE_PATH,
        db_path: Path = DEFAULT_DB_PATH,
        ledger_path: Path = DEFAULT_LEDGER_PATH,
        rollout_root: Path = DEFAULT_ROLLOUT_ROOT,
    ):
        self.config_path = config_path
        self.state_path = state_path
        self.db_path = db_path
        self.ledger_path = ledger_path
        self.rollout_root = rollout_root
        self._state: dict[str, Any] | None = None
        self._snapshot: BudgetSnapshot | None = None

    def _config_failure(self, now: float, reason: str) -> BudgetSnapshot:
        state = load_runtime_state(self.state_path, now)
        decisions = {
            role: RoleBudgetDecision(
                role=role,
                allowed_prompt=False,
                recover_idle=True,
                should_interrupt=False,
                exhausted=True,
                tokens_today=int(state["roles"][role].get("tokens_today", 0)),
                turn_tokens=int(state["roles"][role].get("turn_tokens", 0)),
                estimated_cost_usd=None,
                next_wake_at=_next_utc_day(now),
                active_session_id=state["roles"][role].get("active_session_id"),
                reason=reason,
            )
            for role in ROLE_KEYS
        }
        snapshot = BudgetSnapshot(
            enabled=True,
            revenue_mode="zero_revenue",
            realized_revenue_usd=0.0,
            revenue_verified=False,
            revenue_reason=reason,
            day=state["day"],
            total_tokens_today=int(state.get("day_total_tokens", 0)),
            estimated_cost_usd=None,
            telemetry_stale=True,
            telemetry_errors=(reason,),
            roles=decisions,
        )
        self._state = state
        self._snapshot = snapshot
        return snapshot

    def evaluate(self, now: float, role_models: Mapping[str, str]) -> BudgetSnapshot:
        try:
            config = load_config(self.config_path)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            return self._config_failure(now, f"budget_config_invalid:{type(error).__name__}")
        state = load_runtime_state(self.state_path, now)
        meter = RolloutMeter(
            self.rollout_root,
            lookback_seconds=int(config.get("rollout_lookback_seconds", 86_400)),
            max_files=int(config.get("max_rollout_files", 96)),
        )
        telemetry_errors = meter.update(state, now)
        recognized = {str(item).upper() for item in config.get("recognized_revenue_currencies", ["USD"])}
        revenue = read_revenue_snapshot(self.db_path, self.ledger_path, recognized)
        mode_name = "funded" if revenue.mode == "funded" and revenue.verified else "zero_revenue"
        mode = config["modes"][mode_name]
        pricing = config.get("pricing_usd_per_million", {})
        telemetry_stale = bool(telemetry_errors)
        total_cap = int(mode["max_daily_total_tokens"])
        total_exhausted = int(state["day_total_tokens"]) >= total_cap
        decisions: dict[str, RoleBudgetDecision] = {}
        total_cost = 0.0
        total_cost_known = True
        for role in ROLE_KEYS:
            role_config = mode["roles"][role]
            role_state = state["roles"][role]
            tokens_today = int(role_state.get("tokens_today", 0))
            turn_tokens = int(role_state.get("turn_tokens", 0))
            model = role_models.get(role, "")
            cost = estimate_cost_usd(model, role_state.get("usage_today", {}), pricing)
            if cost is None:
                total_cost_known = False
            else:
                total_cost += cost
            daily_exhausted = tokens_today >= int(role_config["max_daily_tokens"])
            turn_exhausted = turn_tokens >= int(role_config["max_turn_tokens"])
            cost_limit = role_config.get("max_daily_cost_usd")
            cost_exhausted = cost_limit is not None and cost is not None and cost >= float(cost_limit)
            exhausted = total_exhausted or daily_exhausted or turn_exhausted or cost_exhausted
            last_inference = float(role_state.get("last_inference_at", 0.0))
            min_wake = int(role_config["min_wake_seconds"])
            cadence_due = now - last_inference >= min_wake
            enabled = bool(config.get("enabled", True))
            allowed = not enabled or (not telemetry_stale and not exhausted and cadence_due)
            active_session = role_state.get("active_session_id")
            already_interrupted = (
                role_state.get("last_interrupt_session_id") == active_session
                and role_state.get("last_interrupt_day") == state["day"]
            )
            should_interrupt = bool(enabled and exhausted and active_session and not already_interrupted)
            if telemetry_stale:
                reason = "telemetry_stale"
            elif total_exhausted:
                reason = "daily_total_token_cap"
            elif daily_exhausted:
                reason = "role_daily_token_cap"
            elif turn_exhausted:
                reason = "role_turn_token_cap"
            elif cost_exhausted:
                reason = "role_daily_cost_cap"
            elif not cadence_due:
                reason = "minimum_wake_interval"
            elif not enabled:
                reason = "governor_disabled"
            else:
                reason = "within_budget"
            next_wake = _next_utc_day(now) if exhausted else max(now, last_inference + min_wake)
            decisions[role] = RoleBudgetDecision(
                role=role,
                allowed_prompt=allowed,
                recover_idle=not allowed,
                should_interrupt=should_interrupt,
                exhausted=exhausted,
                tokens_today=tokens_today,
                turn_tokens=turn_tokens,
                estimated_cost_usd=cost,
                next_wake_at=next_wake,
                active_session_id=active_session,
                reason=reason,
            )
        snapshot = BudgetSnapshot(
            enabled=bool(config.get("enabled", True)),
            revenue_mode=mode_name,
            realized_revenue_usd=revenue.realized_usd,
            revenue_verified=revenue.verified,
            revenue_reason=revenue.reason,
            day=state["day"],
            total_tokens_today=int(state["day_total_tokens"]),
            estimated_cost_usd=total_cost if total_cost_known else None,
            telemetry_stale=telemetry_stale,
            telemetry_errors=tuple(sorted(set(telemetry_errors))),
            roles=decisions,
        )
        self._state = state
        self._snapshot = snapshot
        return snapshot

    def record_action(self, role: str, action_kind: str, now: float) -> None:
        if self._state is None or role not in ROLE_KEYS:
            return
        current = self._state["roles"][role]
        if action_kind in PROMPT_ACTIONS:
            current["last_inference_at"] = now
        elif action_kind == "interrupt":
            current["last_interrupt_session_id"] = current.get("active_session_id")
            current["last_interrupt_day"] = self._state.get("day")

    def save(self) -> None:
        if self._state is not None:
            _atomic_json_write(self.state_path, self._state)
