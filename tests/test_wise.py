from __future__ import annotations

from agentic.aro import wise


def test_wise_status_without_token(monkeypatch) -> None:
    monkeypatch.setattr(wise, "load_token", lambda: "")
    payload = wise.status()
    assert payload["configured"] is False
    assert payload["ok"] is False
    assert "WISE_API_TOKEN" in payload["reason"]
