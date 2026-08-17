"""Tests for resolve_ghostcli_binary and _smoke_ghostcli diagnostics."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest


def test_resolve_prefers_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """GHOSTCLI_BIN env var takes precedence over all other candidates."""
    fake_bin = tmp_path / "custom-ghostcli"
    fake_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    fake_bin.chmod(fake_bin.stat().st_mode | stat.S_IEXEC)

    monkeypatch.setenv("GHOSTCLI_BIN", str(fake_bin))
    # Ensure sys.prefix and ROOT candidates would NOT match.
    monkeypatch.setattr("sys.prefix", "/nonexistent-prefix")

    from agentic.env import resolve_ghostcli_binary

    result = resolve_ghostcli_binary()
    assert result == str(fake_bin.resolve())


def test_resolve_finds_project_venv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Falls back to ROOT/.venv/bin/ghostcli when sys.prefix misses."""
    venv_bin = tmp_path / ".venv" / "bin" / "ghostcli"
    venv_bin.parent.mkdir(parents=True)
    venv_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    venv_bin.chmod(venv_bin.stat().st_mode | stat.S_IEXEC)

    monkeypatch.delenv("GHOSTCLI_BIN", raising=False)
    monkeypatch.setattr("sys.prefix", "/nonexistent-prefix")

    import agentic.env as env_mod

    original_root = env_mod.ROOT
    try:
        env_mod.ROOT = tmp_path
        from agentic.env import resolve_ghostcli_binary

        result = resolve_ghostcli_binary()
    finally:
        env_mod.ROOT = original_root

    assert result == str(venv_bin.resolve())


def test_resolve_returns_none_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Returns None when no candidate exists anywhere."""
    monkeypatch.delenv("GHOSTCLI_BIN", raising=False)
    monkeypatch.setattr("sys.prefix", "/nonexistent-prefix")

    import agentic.env as env_mod

    original_root = env_mod.ROOT
    try:
        env_mod.ROOT = tmp_path
        with patch("shutil.which", return_value=None):
            from agentic.env import resolve_ghostcli_binary

            assert resolve_ghostcli_binary() is None
    finally:
        env_mod.ROOT = original_root


def test_smoke_ghostcli_reports_binary_field() -> None:
    """_smoke_ghostcli always includes 'binary' in its result dict."""
    from agentic.loop import _smoke_ghostcli

    result = _smoke_ghostcli({"ghost_key": False})
    assert "binary" in result
    assert result["ok"] is False
    assert result["error"] == "ghost_key_not_configured"