# Codex role supervisor

This service supervises only these tmux targets:

- `bug_bounty:v2` — `claude-opus-5[1m]`, Playwright available
- `revenue_generator:v2` — `claude-sonnet-5[1m]`, Playwright disabled
- `contador:0` — `claude-sonnet-5[1m]`, Playwright disabled
- `integrator:0` — `claude-opus-5[1m]`, Playwright disabled

It never touches `bybit_spot`. It reads `/root/.config/ghostcli/env.sh` only in
the launched role shell. One cycle can recover or reorient at most one role.
Goal-exited TUIs must be visibly idle and stable before a fresh Codex process is
started. This includes `blocked`, which is relaunched instead of receiving a
plain prompt that could remain queued behind the blocked goal. A non-empty or
queued TUI input suppresses all action.

The supervisor process is bounded by a 10% CPU quota, 128 MiB memory limit and
32 tasks, with systemd start-rate limiting. No `/proc`, tmux socket or GhostCLI
environment hardening is applied because those are required for observation and
recovery. If no tmux server exists after boot, its first session is created in a
transient systemd scope so Codex/tmux descendants do not inherit the
supervisor-only 128 MiB and 32-task cgroup limits.

Read-only status:

```bash
python3 /Agentic/tools/codex_role_supervisor.py status --json
```

Evaluation without mutation or state writes:

```bash
python3 /Agentic/tools/codex_role_supervisor.py run --once --dry-run --json
```

Proposed deployment (not performed by adding these files):

```bash
install -m 0644 /Agentic/deploy/systemd/agentic-codex-role-supervisor.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now agentic-codex-role-supervisor.service
```

Before activation, run the unit tests and one dry run, inspect all four role
observations, and verify that no live `working` or `busy_or_queued` TUI is
selected for action.
