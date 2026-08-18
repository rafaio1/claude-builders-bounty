"""Testes de resiliência a falhas transitórias no claude_cli.run_implement."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from agentic.claude_cli import run_implement


@pytest.fixture
def cli_env(tmp_path: Path) -> dict:
    return {
        "cwd": tmp_path,
        "api_key": "gk-test-key",
        "base_url": "https://ghostcli.dev",
        "model": "claude-sonnet-5[1m]",
    }


def test_run_implement_retries_on_timeout(cli_env: dict, monkeypatch):
    """Timeouts (returncode 124) devem ser retentados até max_attempts."""
    calls = {"n": 0}

    def fake_run(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise subprocess.TimeoutExpired(cmd=args[0], timeout=10, output=b"", stderr=b"timeout")
        completed = subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="SUMMARY: ok after retry",
            stderr="",
        )
        return completed

    monkeypatch.setattr("agentic.claude_cli.claude_bin", lambda: "/usr/bin/claude")
    monkeypatch.setattr("agentic.claude_cli.subprocess.run", fake_run)
    monkeypatch.setattr("agentic.claude_cli.time.sleep", lambda *_: None)

    result = run_implement("prompt", **cli_env, max_attempts=4, backoff_base=0.01, backoff_cap=0.05)

    assert result["ok"] is True
    assert calls["n"] == 3
    assert "retry" not in result["summary"].lower() or "ok" in result["summary"].lower()


def test_run_implement_gives_up_after_max_attempts(cli_env: dict, monkeypatch):
    """Após esgotar tentativas, retorna o último resultado transitório."""

    def always_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=10, output=b"", stderr=b"timeout")

    monkeypatch.setattr("agentic.claude_cli.claude_bin", lambda: "/usr/bin/claude")
    monkeypatch.setattr("agentic.claude_cli.subprocess.run", always_timeout)
    monkeypatch.setattr("agentic.claude_cli.time.sleep", lambda *_: None)

    result = run_implement("prompt", **cli_env, max_attempts=3, backoff_base=0.01, backoff_cap=0.05)

    assert result["ok"] is False
    assert result["returncode"] == 124
    assert "tentativa 3/3" in result["summary"]


def test_run_implement_no_retry_on_deterministic_error(cli_env: dict, monkeypatch):
    """Erros determinísticos (OSError) não devem ser retentados."""
    calls = {"n": 0}

    def fail_once(*args, **kwargs):
        calls["n"] += 1
        raise OSError("permission denied")

    monkeypatch.setattr("agentic.claude_cli.claude_bin", lambda: "/usr/bin/claude")
    monkeypatch.setattr("agentic.claude_cli.subprocess.run", fail_once)

    result = run_implement("prompt", **cli_env, max_attempts=4)

    assert result["ok"] is False
    assert calls["n"] == 1
    assert "permission denied" in result["summary"]


def test_run_implement_no_retry_on_non_transient_exit(cli_env: dict, monkeypatch):
    """Exit codes não-transientes (ex.: 2) retornam imediatamente sem retry."""
    calls = {"n": 0}

    def non_transient(*args, **kwargs):
        calls["n"] += 1
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=2,
            stdout="",
            stderr="invalid api key",
        )

    monkeypatch.setattr("agentic.claude_cli.claude_bin", lambda: "/usr/bin/claude")
    monkeypatch.setattr("agentic.claude_cli.subprocess.run", non_transient)

    result = run_implement("prompt", **cli_env, max_attempts=4)

    assert result["ok"] is False
    assert calls["n"] == 1
    assert result["returncode"] == 2


def test_run_implement_retries_on_5xx_marker(cli_env: dict, monkeypatch):
    """Markers de erro transitório no output (503) disparam retry."""
    calls = {"n": 0}

    def transient_then_ok(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return subprocess.CompletedProcess(
                args=args[0],
                returncode=1,
                stdout="",
                stderr="upstream returned 503 service unavailable",
            )
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="SUMMARY: recovered",
            stderr="",
        )

    monkeypatch.setattr("agentic.claude_cli.claude_bin", lambda: "/usr/bin/claude")
    monkeypatch.setattr("agentic.claude_cli.subprocess.run", transient_then_ok)
    monkeypatch.setattr("agentic.claude_cli.time.sleep", lambda *_: None)

    result = run_implement("prompt", **cli_env, max_attempts=3, backoff_base=0.01, backoff_cap=0.05)

    assert result["ok"] is True
    assert calls["n"] == 2