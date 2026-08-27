#!/usr/bin/env python3
"""Conservative tmux supervisor for the persistent Codex revenue roles.

The supervisor intentionally manages only four named tmux targets.  It never
touches the trading process.  A cycle may mutate at most one role, and live
work is left alone unless the Codex TUI is visibly idle and its terminal state
has remained stable for a grace period.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

WORKSPACE = Path("/Agentic")
ENV_FILE = Path("/root/.config/ghostcli/env.sh")
PROMPT_ROOT = WORKSPACE / "deploy/systemd/codex-role-prompts"
STATE_FILE = WORKSPACE / "state/codex_role_supervisor.json"
LOCK_FILE = Path("/run/lock/agentic-codex-role-supervisor.lock")

DEFAULT_INTERVAL_SECONDS = 90
GLOBAL_ACTION_COOLDOWN_SECONDS = 90
MAX_BACKOFF_SECONDS = 30 * 60
CAPTURE_LINES = 180

ANSI_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
GOAL_RE = re.compile(
    r"\bGoal\s+(active|paused|stalled|unmet|achieved|complete|completed|blocked)\b",
    re.IGNORECASE,
)
WORKING_RE = re.compile(r"\bWorking\s*\([^\n]*esc to interrupt", re.IGNORECASE)
READY_MARKERS = (
    "Ask Codex to do anything",
    "Improve documentation in @filename",
)
GOAL_EXITED_STATES = {"paused", "stalled", "unmet", "achieved", "complete", "completed", "blocked"}


@dataclass(frozen=True)
class Role:
    key: str
    session: str
    window: str
    model: str
    prompt_file: Path
    playwright_enabled: bool
    reorient_interval_seconds: int
    stable_seconds: int = 180
    recovery_cooldown_seconds: int = 10 * 60

    @property
    def target(self) -> str:
        return f"{self.session}:{self.window}"


ROLES: tuple[Role, ...] = (
    Role(
        key="bug_bounty",
        session="bug_bounty",
        window="v2",
        model="claude-opus-5[1m]",
        prompt_file=PROMPT_ROOT / "bug_bounty.txt",
        playwright_enabled=True,
        reorient_interval_seconds=30 * 60,
    ),
    Role(
        key="revenue_generator",
        session="revenue_generator",
        window="v2",
        model="claude-sonnet-5[1m]",
        prompt_file=PROMPT_ROOT / "revenue_generator.txt",
        playwright_enabled=False,
        reorient_interval_seconds=15 * 60,
    ),
    Role(
        key="contador",
        session="contador",
        window="0",
        model="claude-sonnet-5[1m]",
        prompt_file=PROMPT_ROOT / "contador.txt",
        playwright_enabled=False,
        reorient_interval_seconds=4 * 60 * 60,
    ),
    Role(
        key="integrator",
        session="integrator",
        window="0",
        model="claude-opus-5[1m]",
        prompt_file=PROMPT_ROOT / "integrator.txt",
        playwright_enabled=False,
        reorient_interval_seconds=30 * 60,
    ),
)


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    ppid: int
    command: str
    argv: tuple[str, ...]


@dataclass(frozen=True)
class Observation:
    role: str
    target: str
    status: str
    goal_state: str | None
    pane_pid: int | None
    codex_pids: tuple[int, ...]
    ready_for_input: bool
    working: bool
    queued_or_busy: bool
    fingerprint: str
    detail: str

    @property
    def hard_down(self) -> bool:
        return self.status in {"missing", "dead", "exited"}

    @property
    def signature(self) -> str:
        return f"{self.status}|{self.goal_state or '-'}|{self.pane_pid or 0}"


@dataclass(frozen=True)
class PlannedAction:
    role: str
    kind: str
    reason: str
    expected_fingerprint: str
    prompt_bucket: int | None = None


class Runner(Protocol):
    def run(
        self,
        argv: Sequence[str],
        *,
        input_text: str | None = None,
        timeout: float = 8.0,
    ) -> subprocess.CompletedProcess[str]: ...


class SubprocessRunner:
    def run(
        self,
        argv: Sequence[str],
        *,
        input_text: str | None = None,
        timeout: float = 8.0,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(argv),
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )


def _clean_capture(value: str) -> str:
    return ANSI_RE.sub("", value).replace("\r", "")


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def read_process_snapshot(proc_root: Path = Path("/proc")) -> dict[int, ProcessInfo]:
    snapshot: dict[int, ProcessInfo] = {}
    try:
        entries = proc_root.iterdir()
    except OSError:
        return snapshot
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text(encoding="utf-8", errors="replace")
            right = stat.rfind(")")
            fields = stat[right + 2 :].split()
            ppid = int(fields[1])
            raw = (entry / "cmdline").read_bytes().split(b"\0")
            argv = tuple(part.decode("utf-8", errors="replace") for part in raw if part)
            command = (entry / "comm").read_text(encoding="utf-8", errors="replace").strip()
            pid = int(entry.name)
        except (OSError, ValueError, IndexError):
            continue
        snapshot[pid] = ProcessInfo(pid=pid, ppid=ppid, command=command, argv=argv)
    return snapshot


def descendant_pids(root_pid: int, snapshot: Mapping[int, ProcessInfo]) -> set[int]:
    descendants = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, info in snapshot.items():
            if pid not in descendants and info.ppid in descendants:
                descendants.add(pid)
                changed = True
    return descendants


def is_codex_process(info: ProcessInfo) -> bool:
    if info.command == "codex":
        return True
    if not info.argv:
        return False
    return Path(info.argv[0]).name == "codex"


def classify_capture(
    role: Role,
    *,
    pane_dead: bool,
    pane_pid: int,
    capture: str,
    snapshot: Mapping[int, ProcessInfo],
) -> Observation:
    cleaned = _clean_capture(capture)
    footer_lines = cleaned.splitlines()[-32:]
    footer = "\n".join(footer_lines)
    goal_matches = GOAL_RE.findall(footer)
    goal_state = goal_matches[-1].lower() if goal_matches else None
    prompt_lines = [line for line in footer_lines if line.lstrip().startswith("›")]
    latest_prompt = prompt_lines[-1] if prompt_lines else ""
    ready = any(marker in latest_prompt for marker in READY_MARKERS)
    working = bool(WORKING_RE.search(footer))
    descendants = descendant_pids(pane_pid, snapshot)
    codex_pids = tuple(sorted(pid for pid in descendants if pid in snapshot and is_codex_process(snapshot[pid])))

    if pane_dead:
        status = "dead"
        detail = "tmux pane is dead"
    elif not codex_pids:
        status = "exited"
        detail = "no live Codex process below pane"
    elif working:
        status = "working"
        detail = "Codex footer reports active work"
    elif not ready:
        status = "busy_or_queued"
        detail = "TUI is not at an empty input prompt"
    elif goal_state in GOAL_EXITED_STATES:
        status = "goal_exited"
        detail = f"idle TUI reports Goal {goal_state}"
    else:
        status = "idle"
        detail = "live Codex is at an empty input prompt"

    return Observation(
        role=role.key,
        target=role.target,
        status=status,
        goal_state=goal_state,
        pane_pid=pane_pid,
        codex_pids=codex_pids,
        ready_for_input=ready,
        working=working,
        queued_or_busy=status == "busy_or_queued",
        fingerprint=_hash_text(cleaned),
        detail=detail,
    )


class Tmux:
    def __init__(self, runner: Runner):
        self.runner = runner

    def inspect(self, role: Role, snapshot: Mapping[int, ProcessInfo]) -> Observation:
        metadata = self.runner.run(
            [
                "tmux",
                "display-message",
                "-p",
                "-t",
                role.target,
                "#{pane_dead}|#{pane_pid}|#{pane_current_command}",
            ]
        )
        if metadata.returncode != 0:
            return Observation(
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
                detail="tmux target does not exist",
            )
        parts = metadata.stdout.rstrip("\n").split("|")
        if len(parts) < 2:
            raise RuntimeError(f"unexpected tmux metadata for {role.target}")
        pane_dead = parts[0] == "1"
        pane_pid = int(parts[1])
        captured = self.runner.run(
            ["tmux", "capture-pane", "-p", "-J", "-S", f"-{CAPTURE_LINES}", "-t", role.target],
            timeout=12.0,
        )
        if captured.returncode != 0:
            raise RuntimeError(f"tmux capture failed for {role.target}: {captured.stderr.strip()}")
        return classify_capture(
            role,
            pane_dead=pane_dead,
            pane_pid=pane_pid,
            capture=captured.stdout,
            snapshot=snapshot,
        )

    @staticmethod
    def launch_shell(role: Role) -> str:
        args = ["codex", "--dangerously-bypass-approvals-and-sandbox"]
        if not role.playwright_enabled:
            args.extend(["-c", "mcp_servers.playwright.enabled=false"])
        args.extend(["--model", role.model, f"$(cat -- {shlex.quote(str(role.prompt_file))})"])
        # Keep command substitution in a quoted shell argument.  Prompt content is
        # data and is not evaluated a second time by the shell.
        quoted_args = [shlex.quote(arg) for arg in args[:-1]]
        prompt_arg = f'"$(cat -- {shlex.quote(str(role.prompt_file))})"'
        body = " ".join(
            [
                "set -a;",
                f". {shlex.quote(str(ENV_FILE))};",
                "set +a;",
                "exec",
                *quoted_args,
                prompt_arg,
            ]
        )
        return shlex.join(["/bin/bash", "-lc", body])

    def _session_exists(self, session: str) -> bool:
        result = self.runner.run(["tmux", "has-session", "-t", f"={session}"])
        return result.returncode == 0

    def recover(self, role: Role) -> None:
        shell_command = self.launch_shell(role)
        if not self._session_exists(role.session):
            create = self.runner.run(
                [
                    "systemd-run",
                    "--scope",
                    "--quiet",
                    "--",
                    "tmux",
                    "new-session",
                    "-d",
                    "-s",
                    role.session,
                    "-n",
                    role.window,
                    "-c",
                    str(WORKSPACE),
                    shell_command,
                ],
                timeout=15.0,
            )
            if create.returncode != 0:
                raise RuntimeError(f"cannot create {role.target}: {create.stderr.strip()}")
            return

        window_exists = self.runner.run(
            ["tmux", "display-message", "-p", "-t", role.target, "#{window_id}"]
        )
        if window_exists.returncode != 0:
            create = self.runner.run(
                [
                    "tmux",
                    "new-window",
                    "-d",
                    "-t",
                    f"={role.session}:",
                    "-n",
                    role.window,
                    "-c",
                    str(WORKSPACE),
                    shell_command,
                ],
                timeout=15.0,
            )
            if create.returncode != 0:
                raise RuntimeError(f"cannot create window {role.target}: {create.stderr.strip()}")
            return

        self.relaunch(role)

    def relaunch(self, role: Role) -> None:
        result = self.runner.run(
            [
                "tmux",
                "respawn-pane",
                "-k",
                "-t",
                role.target,
                "-c",
                str(WORKSPACE),
                self.launch_shell(role),
            ],
            timeout=15.0,
        )
        if result.returncode != 0:
            raise RuntimeError(f"cannot respawn {role.target}: {result.stderr.strip()}")

    def reorient(self, role: Role, prompt: str) -> None:
        buffer_name = f"codex-supervisor-{role.key}"
        loaded = self.runner.run(
            ["tmux", "load-buffer", "-b", buffer_name, "-"],
            input_text=prompt,
        )
        if loaded.returncode != 0:
            raise RuntimeError(f"cannot load prompt for {role.target}: {loaded.stderr.strip()}")
        pasted = self.runner.run(
            ["tmux", "paste-buffer", "-d", "-b", buffer_name, "-t", role.target]
        )
        if pasted.returncode != 0:
            raise RuntimeError(f"cannot paste prompt for {role.target}: {pasted.stderr.strip()}")
        entered = self.runner.run(["tmux", "send-keys", "-t", role.target, "Enter"])
        if entered.returncode != 0:
            raise RuntimeError(f"cannot submit prompt for {role.target}: {entered.stderr.strip()}")


def default_state() -> dict[str, Any]:
    return {
        "version": 1,
        "cursor": 0,
        "last_global_action_at": 0.0,
        "roles": {},
    }


def load_state(path: Path = STATE_FILE) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_state()
    if not isinstance(loaded, dict) or loaded.get("version") != 1:
        return default_state()
    loaded.setdefault("cursor", 0)
    loaded.setdefault("last_global_action_at", 0.0)
    loaded.setdefault("roles", {})
    return loaded


def save_state(state: Mapping[str, Any], path: Path = STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, sort_keys=True)
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


def role_state(state: dict[str, Any], role: Role) -> dict[str, Any]:
    roles = state.setdefault("roles", {})
    current = roles.setdefault(
        role.key,
        {
            "observed_signature": "",
            "observed_since": 0.0,
            "last_action_at": 0.0,
            "last_prompt_bucket": None,
            "failure_count": 0,
            "next_retry_at": 0.0,
        },
    )
    return current


def update_observation_state(state: dict[str, Any], observations: Iterable[Observation], now: float) -> None:
    role_map = {role.key: role for role in ROLES}
    for observation in observations:
        current = role_state(state, role_map[observation.role])
        if current.get("observed_signature") != observation.signature:
            current["observed_signature"] = observation.signature
            current["observed_since"] = now
        current["last_observed_at"] = now
        current["last_status"] = observation.status
        current["last_goal_state"] = observation.goal_state
        current["last_fingerprint"] = observation.fingerprint


def _eligible_action(
    role: Role,
    observation: Observation,
    current: Mapping[str, Any],
    *,
    now: float,
) -> PlannedAction | None:
    if now < float(current.get("next_retry_at", 0.0)):
        return None

    last_action = float(current.get("last_action_at", 0.0))
    observed_since = float(current.get("observed_since", now))
    stable_for = max(0.0, now - observed_since)

    if observation.hard_down:
        if now - last_action < role.recovery_cooldown_seconds:
            return None
        return PlannedAction(
            role=role.key,
            kind="recover",
            reason=observation.detail,
            expected_fingerprint=observation.fingerprint,
        )

    if observation.status == "goal_exited":
        if not observation.ready_for_input or stable_for < role.stable_seconds:
            return None
        if now - last_action < role.recovery_cooldown_seconds:
            return None
        return PlannedAction(
            role=role.key,
            kind="relaunch",
            reason=observation.detail,
            expected_fingerprint=observation.fingerprint,
        )

    if observation.status != "idle":
        return None
    if not observation.ready_for_input or stable_for < role.stable_seconds:
        return None
    if now - last_action < role.reorient_interval_seconds:
        return None
    bucket = int(now // role.reorient_interval_seconds)
    if current.get("last_prompt_bucket") == bucket:
        return None
    return PlannedAction(
        role=role.key,
        kind="reorient",
        reason=observation.detail,
        expected_fingerprint=observation.fingerprint,
        prompt_bucket=bucket,
    )


class Supervisor:
    def __init__(
        self,
        runner: Runner,
        *,
        roles: Sequence[Role] = ROLES,
        state_path: Path = STATE_FILE,
        clock: Any = time.time,
        process_reader: Any = read_process_snapshot,
    ):
        self.runner = runner
        self.tmux = Tmux(runner)
        self.roles = tuple(roles)
        self.state_path = state_path
        self.clock = clock
        self.process_reader = process_reader

    def observe_all(self) -> list[Observation]:
        snapshot = self.process_reader()
        return [self.tmux.inspect(role, snapshot) for role in self.roles]

    def plan_one(
        self,
        state: dict[str, Any],
        observations: Sequence[Observation],
        now: float,
    ) -> PlannedAction | None:
        if now - float(state.get("last_global_action_at", 0.0)) < GLOBAL_ACTION_COOLDOWN_SECONDS:
            return None
        by_role = {observation.role: observation for observation in observations}
        start = int(state.get("cursor", 0)) % len(self.roles)
        for offset in range(len(self.roles)):
            index = (start + offset) % len(self.roles)
            role = self.roles[index]
            action = _eligible_action(role, by_role[role.key], role_state(state, role), now=now)
            if action is not None:
                state["cursor"] = (index + 1) % len(self.roles)
                return action
        return None

    def _role(self, key: str) -> Role:
        return next(role for role in self.roles if role.key == key)

    def execute(self, action: PlannedAction, before: Observation) -> None:
        role = self._role(action.role)
        refreshed = self.tmux.inspect(role, self.process_reader())
        if action.kind == "recover":
            if not refreshed.hard_down:
                raise RuntimeError(f"recovery race: {role.target} is no longer down")
            self.tmux.recover(role)
            return

        if refreshed.fingerprint != action.expected_fingerprint:
            raise RuntimeError(f"state changed before action on {role.target}")
        if refreshed.working or not refreshed.ready_for_input:
            raise RuntimeError(f"{role.target} is no longer safely idle")
        if action.kind == "relaunch":
            self.tmux.relaunch(role)
            return
        if action.kind == "reorient":
            prompt = role.prompt_file.read_text(encoding="utf-8").strip()
            if not prompt:
                raise RuntimeError(f"empty role prompt: {role.prompt_file}")
            self.tmux.reorient(role, prompt)
            return
        raise RuntimeError(f"unknown action kind: {action.kind}")

    def run_cycle(self, *, dry_run: bool = False, persist: bool = True) -> dict[str, Any]:
        now = float(self.clock())
        state = load_state(self.state_path)
        observations = self.observe_all()
        update_observation_state(state, observations, now)
        action = self.plan_one(state, observations, now)
        result: dict[str, Any] = {
            "time": now,
            "dry_run": dry_run,
            "action": asdict(action) if action else None,
            "observations": [asdict(observation) for observation in observations],
        }
        if action is not None and not dry_run:
            current = role_state(state, self._role(action.role))
            before = next(item for item in observations if item.role == action.role)
            try:
                self.execute(action, before)
            except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as error:
                failures = int(current.get("failure_count", 0)) + 1
                current["failure_count"] = failures
                current["next_retry_at"] = now + min(MAX_BACKOFF_SECONDS, 60 * (2 ** (failures - 1)))
                result["error"] = str(error)
            else:
                current["failure_count"] = 0
                current["next_retry_at"] = 0.0
                current["last_action_at"] = now
                current["last_action_kind"] = action.kind
                if action.prompt_bucket is not None:
                    current["last_prompt_bucket"] = action.prompt_bucket
                current["observed_signature"] = ""
                current["observed_since"] = now
                state["last_global_action_at"] = now
                result["executed"] = True
        if persist and not dry_run:
            save_state(state, self.state_path)
        return result

    def status(self) -> dict[str, Any]:
        now = float(self.clock())
        state = load_state(self.state_path)
        observations = self.observe_all()
        details = []
        for observation in observations:
            current = role_state(state, self._role(observation.role))
            details.append(
                {
                    **asdict(observation),
                    "observed_since": current.get("observed_since"),
                    "last_action_at": current.get("last_action_at"),
                    "next_retry_at": current.get("next_retry_at"),
                }
            )
        return {"time": now, "roles": details}


def validate_prerequisites(roles: Sequence[Role] = ROLES) -> list[str]:
    errors: list[str] = []
    if not WORKSPACE.is_dir():
        errors.append(f"missing workspace: {WORKSPACE}")
    if not ENV_FILE.is_file():
        errors.append(f"missing GhostCLI env: {ENV_FILE}")
    for executable in ("codex", "systemd-run", "tmux"):
        if shutil.which(executable) is None:
            errors.append(f"missing executable: {executable}")
    for role in roles:
        if not role.prompt_file.is_file():
            errors.append(f"missing prompt for {role.key}: {role.prompt_file}")
        if "z-ai" in role.model.lower() or "ollama" in role.model.lower():
            errors.append(f"forbidden model for {role.key}: {role.model}")
    return errors


def _print(payload: Mapping[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if "roles" in payload:
        for role in payload["roles"]:
            print(
                f"{role['role']}: {role['status']} target={role['target']} "
                f"goal={role.get('goal_state') or '-'} pids={role.get('codex_pids') or []}"
            )
        return
    action = payload.get("action")
    if action:
        prefix = "DRY-RUN" if payload.get("dry_run") else "ACTION"
        print(f"{prefix} {action['kind']} role={action['role']} reason={action['reason']}")
    else:
        print("NO_ACTION")


def _lock() -> Any:
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    handle = LOCK_FILE.open("a+", encoding="utf-8")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    return handle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    status = subparsers.add_parser("status", help="read-only role status")
    status.add_argument("--json", action="store_true")
    run = subparsers.add_parser("run", help="run one cycle or the supervisor loop")
    run.add_argument("--once", action="store_true")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--json", action="store_true")
    run.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    supervisor = Supervisor(SubprocessRunner())
    if args.command == "status":
        _print(supervisor.status(), args.json)
        return 0

    errors = validate_prerequisites()
    if errors:
        _print({"errors": errors}, True)
        return 2
    if args.interval < 30:
        print("interval must be at least 30 seconds", file=sys.stderr)
        return 2
    lock_handle = None
    if not args.dry_run:
        try:
            lock_handle = _lock()
        except BlockingIOError:
            print("another supervisor instance holds the lock", file=sys.stderr)
            return 3

    try:
        while True:
            result = supervisor.run_cycle(dry_run=args.dry_run, persist=not args.dry_run)
            _print(result, args.json)
            if args.once or args.dry_run:
                return 1 if result.get("error") else 0
            time.sleep(args.interval)
    finally:
        if lock_handle is not None:
            lock_handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
