from __future__ import annotations

from pathlib import Path

from agentic.config import Settings
import json

from agentic.loop import (
    LAST_TICK_PATH,
    _PLAYWRIGHT_PROCESS_LIMIT,
    _cleanup_playwright_zombies,
    _count_playwright_processes,
    collect_census,
    tick,
)


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


def test_smoke_ghostcli_uses_api_not_binary(tmp_path: Path, monkeypatch) -> None:
    """Smoke do GhostCLI deve validar via API HTTP, não por binário no PATH.

    Regressão: o ambiente de execução não tem `ghostcli` como executável;
    a integração é exclusivamente via classe GhostCLI (HTTP). O smoke test
    antigo chamava `["ghostcli", "status"]` e quebrava com FileNotFoundError,
    bloqueando a fila de develop/review.
    """
    from agentic.loop import _smoke_ghostcli

    # Sem chave → erro claro, sem exceção
    result_no_key = _smoke_ghostcli({"ghost_key": False})
    assert result_no_key["ok"] is False
    assert result_no_key["error"] == "ghost_key_not_configured"

    # Com chave mas endpoint inválido → ok=False com erro estruturado (não FileNotFoundError)
    monkeypatch.setenv("GHOSTCLI_API_KEY", "gk-test-smoke")
    monkeypatch.setenv("GHOSTCLI_BASE_URL", "https://ghost.invalid/v1")
    result_bad_host = _smoke_ghostcli({"ghost_key": True})
    assert isinstance(result_bad_host, dict)
    assert result_bad_host["ok"] is False
    assert "FileNotFoundError" not in str(result_bad_host.get("error", ""))
    assert "returncode" in result_bad_host
    assert "error" in result_bad_host


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


def test_count_playwright_processes_returns_int(monkeypatch) -> None:
    """_count_playwright_processes deve devolver int e nunca levantar."""
    import subprocess

    # Simula pgrep retornando contagem válida.
    def fake_run(args, **kwargs):
        class R:
            returncode = 0
            stdout = "7\n"
            stderr = ""
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert _count_playwright_processes() == 7


def test_count_playwright_processes_handles_error(monkeypatch) -> None:
    """Em caso de erro/timeout, devolve 0 sem levantar."""
    import subprocess

    def fake_run(args, **kwargs):
        raise OSError("pgrep missing")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert _count_playwright_processes() == 0


def test_cleanup_skips_when_under_limit(monkeypatch) -> None:
    """Se contagem está abaixo do limite, não executa pkill."""
    import subprocess

    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(args)
        class R:
            returncode = 1
            stdout = "0\n"
            stderr = ""
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = _cleanup_playwright_zombies()
    assert result["killed"] is False
    # Apenas pgrep deve ter sido chamado; nenhum pkill.
    assert all(args[0] != "pkill" for args in calls)


def test_cleanup_kills_when_over_limit(monkeypatch) -> None:
    """Acima do limite, executa SIGTERM e (se necessário) SIGKILL."""
    import subprocess

    call_log: list[list[str]] = []
    pgrep_results = iter(["20\n", "5\n", "5\n"])

    def fake_run(args, **kwargs):
        call_log.append(args)
        class R:
            pass
        r = R()
        if args[0] == "pgrep":
            r.returncode = 0
            r.stdout = next(pgrep_results)
            r.stderr = ""
        else:
            # pkill
            r.returncode = 0
            r.stdout = ""
            r.stderr = ""
        return r

    monkeypatch.setattr(subprocess, "run", fake_run)
    # Acelera sleeps internos da limpeza.
    import agentic.loop as loop_mod
    monkeypatch.setattr(loop_mod.time, "sleep", lambda *_: None)

    result = _cleanup_playwright_zombies()
    assert result["before"] == 20
    assert result["killed"] is True
    # Deve ter chamado pkill pelo menos uma vez (SIGTERM).
    assert any(args[0] == "pkill" for args in call_log)
