from __future__ import annotations

import json
from pathlib import Path

from agentic.claude_cli import anthropic_base_url, ghostcli_env, run_implement


def test_anthropic_base_strips_v1() -> None:
    assert anthropic_base_url("https://ghostcli.dev/v1") == "https://ghostcli.dev"
    assert anthropic_base_url("https://ghostcli.dev") == "https://ghostcli.dev"


def test_ghostcli_env_maps_into_anthropic(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    env = ghostcli_env(
        api_key="gk-test",
        base_url="https://ghostcli.dev/v1",
        model="claude-sonnet-5[1m]",
    )
    assert env["ANTHROPIC_API_KEY"] == "gk-test"
    assert env["GHOSTCLI_API_KEY"] == "gk-test"
    assert env["ANTHROPIC_BASE_URL"] == "https://ghostcli.dev"
    assert env["GHOSTCLI_MODEL"] == "claude-sonnet-5[1m]"
    assert env["AGENTIC_LIVE_TRADE"] == "0"


def test_run_implement_writes_sanitized_trace(tmp_path: Path, monkeypatch) -> None:
    """run_implement must persist a sanitized trace even when the CLI is missing."""
    traces_dir = tmp_path / "traces"
    monkeypatch.setattr("agentic.claude_cli._TRACES_DIR", traces_dir)
    # Ensure claude binary is not found so we hit the early-return path.
    monkeypatch.setattr("agentic.claude_cli.claude_bin", lambda: "")

    result = run_implement(
        "implement something with BYBIT_API_SECRET=abcdefgh12345678",
        cwd=tmp_path,
        api_key="gk-test",
        base_url="https://ghostcli.dev",
        model="claude-sonnet-5[1m]",
    )

    assert result["ok"] is False
    assert result["returncode"] == 127

    trace_files = list(traces_dir.glob("*.json"))
    assert len(trace_files) == 1
    record = json.loads(trace_files[0].read_text(encoding="utf-8"))
    assert record["method"] == "claude_cli.run_implement"
    assert record["ok"] is False
    assert record["returncode"] == 127
    # The prompt snippet must be sanitized — no raw secret value.
    assert "abcdefgh12345678" not in record["prompt_snippet"]
    assert "***REDACTED***" in record["prompt_snippet"] or "REDACTED" in record["raw_sanitized"]
