"""Run Claude Code CLI against GhostCLI (ANTHROPIC_* → ghostcli.dev)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


def anthropic_base_url(ghostcli_base_url: str) -> str:
    base = (ghostcli_base_url or "https://ghostcli.dev").rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3].rstrip("/")
    return base or "https://ghostcli.dev"


def ghostcli_env(
    *,
    api_key: str,
    base_url: str,
    model: str,
) -> dict[str, str]:
    """Map GhostCLI credentials into the env Claude Code expects."""
    env = os.environ.copy()
    key = (api_key or "").strip()
    if key:
        env["GHOSTCLI_API_KEY"] = key
        env["ANTHROPIC_API_KEY"] = key
    ghost_base = anthropic_base_url(base_url)
    env["GHOSTCLI_BASE_URL"] = ghost_base
    env["ANTHROPIC_BASE_URL"] = ghost_base
    if model:
        env["GHOSTCLI_MODEL"] = model
        env["ANTHROPIC_MODEL"] = model
    env["AGENTIC_LIVE_TRADE"] = "0"
    # Avoid interactive auth / keychain when running from systemd.
    env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
    return env


def claude_bin() -> str:
    return shutil.which("claude") or ""


def available() -> bool:
    return bool(claude_bin())


def run_implement(
    prompt: str,
    *,
    cwd: Path,
    api_key: str,
    base_url: str,
    model: str,
    timeout: float = 1500.0,
) -> dict[str, Any]:
    """Dump one implement prompt into Claude CLI (tools on, GhostCLI models)."""
    binary = claude_bin()
    if not binary:
        return {
            "ok": False,
            "summary": "claude CLI ausente no PATH",
            "output": "",
            "returncode": 127,
            "model": model,
        }
    if not (api_key or "").strip():
        return {
            "ok": False,
            "summary": "GHOSTCLI_API_KEY ausente para Claude CLI",
            "output": "",
            "returncode": 2,
            "model": model,
        }

    env = ghostcli_env(api_key=api_key, base_url=base_url, model=model)
    # Root cannot use --dangerously-skip-permissions. acceptEdits + allowlist works.
    # Put the prompt after "--": --allowedTools/--disallowedTools are variadic and
    # would otherwise swallow the prompt as fake tool names.
    cmd = [
        binary,
        "-p",
        "--permission-mode",
        "acceptEdits",
        "--allowedTools",
        "Bash,Read,Edit,Write,Glob,Grep",
        "--output-format",
        "text",
        "--model",
        model or "claude-sonnet-5[1m]",
        "--",
        prompt,
    ]
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        out = ((exc.stdout or "") + "\n" + (exc.stderr or "")).strip()
        return {
            "ok": False,
            "summary": f"claude CLI timeout após {int(timeout)}s",
            "output": out[-8000:],
            "returncode": 124,
            "model": model,
        }
    except OSError as exc:
        return {
            "ok": False,
            "summary": f"falha ao executar claude CLI: {exc}",
            "output": "",
            "returncode": 1,
            "model": model,
        }

    output = ((completed.stdout or "") + "\n" + (completed.stderr or "")).strip()
    summary = (completed.stdout or "").strip() or (completed.stderr or "").strip()
    return {
        "ok": completed.returncode == 0,
        "summary": summary[:2000],
        "output": output[-12000:],
        "returncode": completed.returncode,
        "model": model,
    }
