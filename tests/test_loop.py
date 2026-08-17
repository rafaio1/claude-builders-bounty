from __future__ import annotations

from pathlib import Path

from agentic.config import Settings
import json

from agentic.loop import LAST_TICK_PATH, collect_census, tick


def test_tick_writes_status_without_secrets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("BYBIT_REAL_API_KEY", raising=False)
    monkeypatch.delenv("BYBIT_API_KEY", raising=False)
    monkeypatch.setenv("GHOSTCLI_API_KEY", "")
    settings = Settings(
        root=tmp_path,
        lock_path=tmp_path / ".agentic.lock",
        ghostcli_api_key="",
        ghostcli_base_url="https://ghost.invalid/v1",
        ghostcli_model="x",
        ghostcli_orchestrator_model="x",
        interval_seconds=90,
        live_trade=False,
    )
    payload = tick(settings)
    text = (tmp_path / "data" / "status.json").read_text(encoding="utf-8")
    assert "BYBIT_" not in text
    assert "GHOSTCLI_API_KEY" not in text
    assert payload["live_trade"] is False
    assert "tools" in payload
    assert "aro" in payload
    assert payload["aro"]["ready_for_outbound"] is False


def test_tick_rejects_live_trade(tmp_path: Path) -> None:
    settings = Settings(
        root=tmp_path,
        lock_path=tmp_path / ".agentic.lock",
        ghostcli_api_key="",
        ghostcli_base_url="https://ghost.invalid/v1",
        ghostcli_model="x",
        ghostcli_orchestrator_model="x",
        interval_seconds=90,
        live_trade=True,
    )
    try:
        tick(settings)
    except RuntimeError as exc:
        assert "AGENTIC_LIVE_TRADE" in str(exc)
    else:
        raise AssertionError("deveria recusar trade live")


def test_census_booleans_only(tmp_path: Path) -> None:
    census = collect_census(tmp_path)
    tools = census["tools"]
    assert set(tools) >= {"playwright", "claude", "ghostcli", "bybit_key", "bybit_secret"}
    for value in tools.values():
        assert isinstance(value, bool)


def test_census_smoke_structured(tmp_path: Path) -> None:
    """Smoke tests devem devolver dict estruturado por ferramenta, não apenas bool."""
    census = collect_census(tmp_path)
    smoke = census.get("smoke")
    assert isinstance(smoke, dict), "census deve conter chave 'smoke' com resultados estruturados"
    expected_tools = {"playwright", "jq", "ghostcli"}
    assert expected_tools.issubset(smoke.keys()), f"smoke deve cobrir {expected_tools}"
    for tool_name, result in smoke.items():
        assert isinstance(result, dict), f"smoke[{tool_name}] deve ser dict"
        assert "ok" in result, f"smoke[{tool_name}] deve ter campo 'ok'"
        assert isinstance(result["ok"], bool), f"smoke[{tool_name}].ok deve ser bool"
        assert "error" in result, f"smoke[{tool_name}] deve ter campo 'error'"
        # tools.X deve refletir smoke.X.ok para consistência
        assert census["tools"][tool_name] == result["ok"]


def test_tick_writes_last_tick_snapshot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("BYBIT_REAL_API_KEY", raising=False)
    monkeypatch.delenv("BYBIT_API_KEY", raising=False)
    monkeypatch.setenv("GHOSTCLI_API_KEY", "")
    settings = Settings(
        root=tmp_path,
        lock_path=tmp_path / ".agentic.lock",
        ghostcli_api_key="",
        ghostcli_base_url="https://ghost.invalid/v1",
        ghostcli_model="x",
        ghostcli_orchestrator_model="x",
        interval_seconds=90,
        live_trade=False,
    )
    tick(settings)
    last_tick_file = tmp_path / LAST_TICK_PATH
    assert last_tick_file.is_file()
    snapshot = json.loads(last_tick_file.read_text(encoding="utf-8"))
    assert "ts" in snapshot
    assert isinstance(snapshot["tools_ok"], int)
    assert snapshot["tools_ok"] >= 0
