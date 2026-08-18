"""Garante que o Playwright MCP permanece desativado para evitar dreno de tokens.

O motor deve sempre reportar playwright_mcp=False e remover variáveis de
ambiente que tentem reativá-lo. Estes testes travam a invariante documentada
em AGENTS.md e loop.py.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def test_loop_census_hardcodes_playwright_mcp_false(tmp_path: Path) -> None:
    """collect_census deve sempre reportar playwright_mcp=False."""
    from agentic.loop import collect_census

    # Cria data/ mínimo para evitar FileNotFoundError no status.json
    (tmp_path / "data").mkdir()
    census = collect_census(tmp_path)
    assert census["tools"]["playwright_mcp"] is False


def test_aro_inventory_hardcodes_playwright_mcp_false() -> None:
    """inventory_tools do ARO deve sempre reportar playwright_mcp=False."""
    from agentic.aro.cycle import inventory_tools

    inv = inventory_tools()
    assert inv["playwright_mcp"] is False


def test_apply_strips_playwright_mcp_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """apply() deve remover qualquer var de ambiente que tente ativar o MCP."""
    # Limpa cache do módulo para forçar reexecução do _load_into_environ
    import agentic.env as env_mod

    monkeypatch.setattr(env_mod, "_APPLY_CACHE", None)

    # Injeta vars que poderiam reativar o MCP
    monkeypatch.setenv("PLAYWRIGHT_MCP", "1")
    monkeypatch.setenv("PLAYWRIGHT_MCP_ENABLED", "true")
    monkeypatch.setenv("MCP_PLAYWRIGHT", "yes")

    env_mod.apply()

    assert "PLAYWRIGHT_MCP" not in os.environ
    assert "PLAYWRIGHT_MCP_ENABLED" not in os.environ
    assert "MCP_PLAYWRIGHT" not in os.environ

    # Restaura para não poluir outros testes
    monkeypatch.delenv("PLAYWRIGHT_MCP", raising=False)
    monkeypatch.delenv("PLAYWRIGHT_MCP_ENABLED", raising=False)
    monkeypatch.delenv("MCP_PLAYWRIGHT", raising=False)