from __future__ import annotations

import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


budget = load_module("codex_budget_governor", TOOLS / "codex_budget_governor.py")
supervisor = load_module("codex_role_supervisor", TOOLS / "codex_role_supervisor.py")


def config_payload():
    roles = {
        role: {
            "max_turn_tokens": 100,
            "max_daily_tokens": 200,
            "max_daily_cost_usd": None,
            "min_wake_seconds": 60,
        }
        for role in budget.ROLE_KEYS
    }
    return {
        "version": 1,
        "enabled": True,
        "rollout_lookback_seconds": 86400,
        "max_rollout_files": 32,
        "recognized_revenue_currencies": ["USD"],
        "pricing_usd_per_million": {
            "claude-opus-5[1m]": {field: None for field in budget.TOKEN_FIELDS},
            "claude-sonnet-5[1m]": {field: None for field in budget.TOKEN_FIELDS},
        },
        "modes": {
            "zero_revenue": {"max_daily_total_tokens": 500, "roles": roles},
            "funded": {"max_daily_total_tokens": 1000, "roles": roles},
        },
    }


def write_config(path: Path):
    path.write_text(json.dumps(config_payload()), encoding="utf-8")


def create_db(path: Path, rows=()):
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE settlements (
            provider TEXT,
            transaction_id TEXT,
            currency TEXT,
            net_amount REAL,
            status TEXT
        )
        """
    )
    connection.executemany("INSERT INTO settlements VALUES (?, ?, ?, ?, ?)", rows)
    connection.commit()
    connection.close()


def rollout_event(path: Path, session: str, role_marker: str, total: int, input_tokens: int | None = None):
    path.parent.mkdir(parents=True, exist_ok=True)
    events = [
        {"type": "session_meta", "payload": {"id": session, "cwd": "/Agentic"}},
        {"type": "response_item", "payload": {"role": "user", "content": role_marker}},
        {
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": total if input_tokens is None else input_tokens,
                        "cached_input_tokens": 0,
                        "cache_write_input_tokens": 0,
                        "output_tokens": total - (total if input_tokens is None else input_tokens),
                        "reasoning_output_tokens": 0,
                        "total_tokens": total,
                    }
                },
            },
        },
    ]
    with path.open("a", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event) + "\n")


def make_governor(tmp_path: Path, rows=(), ledger_lines=()):
    config = tmp_path / "config.json"
    state = tmp_path / "state.json"
    database = tmp_path / "revenue.db"
    ledger = tmp_path / "ledger.jsonl"
    rollouts = tmp_path / "sessions"
    write_config(config)
    create_db(database, rows)
    ledger.write_text("".join(json.dumps(line) + "\n" for line in ledger_lines), encoding="utf-8")
    return budget.BudgetGovernor(
        config_path=config,
        state_path=state,
        db_path=database,
        ledger_path=ledger,
        rollout_root=rollouts,
    ), rollouts, state


MODELS = {
    "bug_bounty": "claude-opus-5[1m]",
    "revenue_generator": "claude-sonnet-5[1m]",
    "contador": "claude-sonnet-5[1m]",
    "integrator": "claude-opus-5[1m]",
}


def test_config_rejects_bybit_role(tmp_path):
    payload = config_payload()
    payload["modes"]["zero_revenue"]["roles"]["bybit"] = payload["modes"]["zero_revenue"]["roles"]["contador"]
    path = tmp_path / "config.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        budget.load_config(path)
    except ValueError as error:
        assert "forbidden role" in str(error)
    else:
        raise AssertionError("Bybit role must be rejected")


def test_empty_settlements_are_verified_zero_revenue(tmp_path):
    governor, _rollouts, _state = make_governor(tmp_path)
    snapshot = governor.evaluate(1_787_850_000.0, MODELS)
    assert snapshot.revenue_mode == "zero_revenue"
    assert snapshot.revenue_verified is True
    assert snapshot.realized_revenue_usd == 0


def test_unmatched_confirmed_settlement_fails_closed(tmp_path):
    rows = [("wise", "tx-1", "USD", 10.0, "confirmed")]
    governor, _rollouts, _state = make_governor(tmp_path, rows=rows)
    snapshot = governor.evaluate(1_787_850_000.0, MODELS)
    assert snapshot.revenue_mode == "zero_revenue"
    assert snapshot.revenue_verified is False
    assert snapshot.revenue_reason == "settlement_ledger_mismatch"


def test_matched_confirmed_settlement_enables_funded_mode(tmp_path):
    rows = [("wise", "tx-1", "USD", 10.0, "confirmed")]
    ledger = [{"provider": "wise", "transaction_id": "tx-1", "status": "confirmed"}]
    governor, _rollouts, _state = make_governor(tmp_path, rows=rows, ledger_lines=ledger)
    snapshot = governor.evaluate(1_787_850_000.0, MODELS)
    assert snapshot.revenue_mode == "funded"
    assert snapshot.revenue_verified is True
    assert snapshot.realized_revenue_usd == 10.0


def test_rollout_meter_is_incremental_and_does_not_double_count(tmp_path):
    governor, rollouts, _state = make_governor(tmp_path)
    path = rollouts / "2026/08/27/rollout-a.jsonl"
    rollout_event(path, "session-a", "REVENUE BUILDER", 50)
    first = governor.evaluate(1_787_850_000.0, MODELS)
    governor.save()
    second = governor.evaluate(1_787_850_010.0, MODELS)
    assert first.roles["revenue_generator"].tokens_today == 50
    assert second.roles["revenue_generator"].tokens_today == 50
    rollout_event(path, "session-a", "REVENUE BUILDER", 80)
    third = governor.evaluate(1_787_850_020.0, MODELS)
    assert third.roles["revenue_generator"].tokens_today == 80


def test_large_rollout_bootstrap_is_bounded_and_first_cycle_fail_closed(tmp_path):
    governor, rollouts, state_path = make_governor(tmp_path)
    path = rollouts / "2026/08/27/rollout-large.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    initial = [
        {"type": "session_meta", "payload": {"id": "session-large", "cwd": "/Agentic"}},
        {"type": "response_item", "payload": {"role": "user", "content": "REVENUE BUILDER"}},
    ]
    with path.open("w", encoding="utf-8") as handle:
        for event in initial:
            handle.write(json.dumps(event) + "\n")
        filler = json.dumps({"type": "noise", "payload": "x" * 512}) + "\n"
        while handle.tell() <= budget.BOOTSTRAP_READ_LIMIT * 2:
            handle.write(filler)
    rollout_event(path, "session-large", "REVENUE BUILDER", 50)

    first = governor.evaluate(1_787_850_000.0, MODELS)
    assert first.telemetry_stale is True
    assert "bootstrap_limited" in first.telemetry_errors
    assert all(not decision.allowed_prompt for decision in first.roles.values())
    assert first.roles["revenue_generator"].tokens_today == 50
    governor.save()

    saved = json.loads(state_path.read_text(encoding="utf-8"))
    cursor = saved["files"][str(path)]["offset"]
    assert cursor >= path.stat().st_size - budget.BOOTSTRAP_READ_LIMIT
    second = governor.evaluate(1_787_850_010.0, MODELS)
    assert second.telemetry_stale is False
    assert second.roles["revenue_generator"].tokens_today == 50


def test_null_prices_make_cost_unknown_but_tokens_are_enforced(tmp_path):
    governor, rollouts, _state = make_governor(tmp_path)
    rollout_event(rollouts / "2026/08/27/rollout-a.jsonl", "session-a", "REVENUE BUILDER", 150)
    snapshot = governor.evaluate(1_787_850_000.0, MODELS)
    decision = snapshot.roles["revenue_generator"]
    assert decision.estimated_cost_usd is None
    assert snapshot.estimated_cost_usd is None
    assert decision.exhausted is True
    assert decision.allowed_prompt is False


def test_interrupt_is_idempotent_per_session_and_day(tmp_path):
    governor, rollouts, _state = make_governor(tmp_path)
    rollout_event(rollouts / "2026/08/27/rollout-a.jsonl", "session-a", "REVENUE BUILDER", 150)
    first = governor.evaluate(1_787_850_000.0, MODELS)
    assert first.roles["revenue_generator"].should_interrupt is True
    governor.record_action("revenue_generator", "interrupt", 1_787_850_000.0)
    governor.save()
    second = governor.evaluate(1_787_850_010.0, MODELS)
    assert second.roles["revenue_generator"].should_interrupt is False


def missing_observation(role):
    return supervisor.Observation(
        role=role.key,
        target=role.target,
        status="missing",
        goal_state=None,
        pane_pid=None,
        codex_pids=(),
        ready_for_input=False,
        working=False,
        queued_or_busy=False,
        fingerprint="missing",
        detail="missing",
    )


class NoRunner:
    def run(self, argv, *, input_text=None, timeout=8.0):
        raise AssertionError("planning test must not run commands")


def test_exhausted_budget_converts_recovery_to_idle_and_keeps_one_action():
    roles = supervisor.ROLES
    decisions = {
        role.key: budget.RoleBudgetDecision(
            role=role.key,
            allowed_prompt=False,
            recover_idle=True,
            should_interrupt=False,
            exhausted=True,
            tokens_today=999,
            turn_tokens=999,
            estimated_cost_usd=None,
            next_wake_at=999999.0,
            active_session_id="session",
            reason="role_daily_token_cap",
        )
        for role in roles
    }
    snapshot = budget.BudgetSnapshot(
        enabled=True,
        revenue_mode="zero_revenue",
        realized_revenue_usd=0,
        revenue_verified=True,
        revenue_reason="no_confirmed_settlements",
        day="2026-08-27",
        total_tokens_today=999,
        estimated_cost_usd=None,
        telemetry_stale=False,
        telemetry_errors=(),
        roles=decisions,
    )
    state = supervisor.default_state()
    observations = [missing_observation(role) for role in roles]
    supervisor.update_observation_state(state, observations, 10_000.0)
    instance = supervisor.Supervisor(NoRunner(), governor=None)
    action = instance.plan_one(state, observations, 10_000.0, budget=snapshot)
    assert action is not None
    assert action.kind == "recover_idle"
    assert action.role == "bug_bounty"
    assert all("bybit" not in role.key for role in roles)


def test_launch_shell_without_prompt_keeps_codex_idle():
    shell = supervisor.Tmux.launch_shell(supervisor.ROLES[1], include_prompt=False)
    assert "codex" in shell
    assert "claude-sonnet-5[1m]" in shell
    assert "$(cat --" not in shell


def test_tmux_interrupt_uses_single_escape():
    class Runner:
        def __init__(self):
            self.calls = []

        def run(self, argv, *, input_text=None, timeout=8.0):
            self.calls.append(tuple(argv))
            return subprocess.CompletedProcess(argv, 0, "", "")

    runner = Runner()
    supervisor.Tmux(runner).interrupt(supervisor.ROLES[0])
    assert runner.calls == [("tmux", "send-keys", "-t", "bug_bounty:v2", "Escape")]


def test_busy_or_queued_role_is_planned_and_rechecked_for_interrupt():
    roles = supervisor.ROLES
    decisions = {
        role.key: budget.RoleBudgetDecision(
            role=role.key,
            allowed_prompt=False,
            recover_idle=True,
            should_interrupt=role.key == "bug_bounty",
            exhausted=True,
            tokens_today=999,
            turn_tokens=999,
            estimated_cost_usd=None,
            next_wake_at=999999.0,
            active_session_id="session",
            reason="role_daily_token_cap",
        )
        for role in roles
    }
    snapshot = budget.BudgetSnapshot(
        enabled=True,
        revenue_mode="zero_revenue",
        realized_revenue_usd=0,
        revenue_verified=True,
        revenue_reason="no_confirmed_settlements",
        day="2026-08-27",
        total_tokens_today=999,
        estimated_cost_usd=None,
        telemetry_stale=False,
        telemetry_errors=(),
        roles=decisions,
    )
    queued = supervisor.Observation(
        role="bug_bounty",
        target="bug_bounty:v2",
        status="busy_or_queued",
        goal_state=None,
        pane_pid=123,
        codex_pids=(456,),
        ready_for_input=False,
        working=False,
        queued_or_busy=True,
        fingerprint="same-state",
        detail="TUI is not at an empty input prompt",
    )
    observations = [queued, *(missing_observation(role) for role in roles[1:])]
    state = supervisor.default_state()
    supervisor.update_observation_state(state, observations, 10_000.0)
    instance = supervisor.Supervisor(NoRunner(), governor=None, process_reader=dict)
    action = instance.plan_one(state, observations, 10_000.0, budget=snapshot)
    assert action is not None
    assert action.kind == "interrupt"
    assert action.role == "bug_bounty"

    class TmuxDouble:
        def __init__(self):
            self.interrupted = []

        def inspect(self, role, _snapshot):
            return queued

        def interrupt(self, role):
            self.interrupted.append(role.key)

    tmux = TmuxDouble()
    instance.tmux = tmux
    instance.execute(action, queued)
    assert tmux.interrupted == ["bug_bounty"]

    changed = supervisor.Observation(**{**queued.__dict__, "fingerprint": "changed-state"})
    tmux.inspect = lambda role, _snapshot: changed
    try:
        instance.execute(action, queued)
    except RuntimeError as error:
        assert "state changed" in str(error)
    else:
        raise AssertionError("fingerprint race must reject queued interrupt")
    assert tmux.interrupted == ["bug_bounty"]
