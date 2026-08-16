from __future__ import annotations

from agentic.env import apply


def test_apply_does_not_print_and_sets_kill_switch(capsys) -> None:
    status = apply()
    captured = capsys.readouterr()
    assert "BYBIT_" not in captured.out
    assert "gcli_" not in captured.out
    assert status["live_trade"] == "0"
    assert isinstance(status["bybit_key"], bool)
    assert isinstance(status["ghost_key"], bool)
