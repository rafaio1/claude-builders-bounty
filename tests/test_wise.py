from __future__ import annotations

import pytest

from agentic.aro import wise


@pytest.fixture(autouse=True)
def reset_wise_backoff() -> None:
    wise._reset_integration_backoff()
    yield
    wise._reset_integration_backoff()


def test_wise_status_without_token(monkeypatch) -> None:
    monkeypatch.setattr(wise, "load_token", lambda: "")
    payload = wise.status()
    assert payload["configured"] is False
    assert payload["ok"] is False
    assert "WISE_API_TOKEN" in payload["reason"]


def test_wise_status_isolates_ssl_eof_and_honors_backoff(monkeypatch) -> None:
    clock = {"now": 100.0}
    calls = {"profiles": 0, "receive": 0}

    monkeypatch.setattr(wise, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(wise, "load_token", lambda: "test-token")

    def profiles(_token: str) -> list[dict[str, object]]:
        calls["profiles"] += 1
        return [{"id": 123, "type": "personal"}]

    def receive(_token: str, _profile_id: object) -> list[dict[str, object]]:
        calls["receive"] += 1
        raise wise.requests.exceptions.SSLError("unexpected EOF")

    monkeypatch.setattr(wise, "_profiles", profiles)
    monkeypatch.setattr(wise, "_balances", lambda _token, _profile_id: [])
    monkeypatch.setattr(wise, "_receive_options", receive)

    failed = wise.status()
    assert failed["ok"] is False
    assert failed["retry_after_seconds"] == 30
    assert failed["integration_error"] == {
        "provider": "wise",
        "kind": "network",
        "error_type": "SSLError",
        "stage": "account_details",
        "retryable": True,
        "consecutive_failures": 1,
        "retry_after_seconds": 30,
    }

    suppressed = wise.status()
    assert suppressed["ok"] is False
    assert suppressed["retry_after_seconds"] == 30
    assert calls == {"profiles": 1, "receive": 1}


def test_wise_backoff_is_capped_and_success_resets_it(monkeypatch) -> None:
    clock = {"now": 200.0}
    should_fail = {"value": True}
    expected_delays = [30, 60, 120, 240, 300, 300]

    monkeypatch.setattr(wise, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(wise, "load_token", lambda: "test-token")
    monkeypatch.setattr(
        wise,
        "_profiles",
        lambda _token: [{"id": 123, "type": "personal"}],
    )
    monkeypatch.setattr(wise, "_balances", lambda _token, _profile_id: [])

    def receive(_token: str, _profile_id: object) -> list[dict[str, object]]:
        if should_fail["value"]:
            raise wise.requests.exceptions.SSLError("unexpected EOF")
        return []

    monkeypatch.setattr(wise, "_receive_options", receive)

    for failures, expected_delay in enumerate(expected_delays, start=1):
        failed = wise.status()
        assert failed["retry_after_seconds"] == expected_delay
        assert failed["integration_error"]["consecutive_failures"] == failures
        clock["now"] += expected_delay

    should_fail["value"] = False
    recovered = wise.status()
    assert recovered["ok"] is True
    assert "integration_error" not in recovered

    should_fail["value"] = True
    failed_again = wise.status()
    assert failed_again["retry_after_seconds"] == 30
    assert failed_again["integration_error"]["consecutive_failures"] == 1


@pytest.mark.parametrize(
    ("status_code", "failing_stage", "expected_kind", "retryable"),
    [
        (401, "profiles", "authentication", False),
        (429, "balances", "rate_limit", True),
        (500, "account_details", "server", True),
    ],
)
def test_wise_http_errors_fail_closed_with_backoff(
    monkeypatch,
    status_code: int,
    failing_stage: str,
    expected_kind: str,
    retryable: bool,
) -> None:
    clock = {"now": 500.0}
    calls: list[str] = []
    monkeypatch.setattr(wise, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(wise, "load_token", lambda: "test-token")

    def get(path: str, _token: str, timeout: float = 20.0):
        del timeout
        stage = (
            "profiles"
            if path == "/v2/profiles"
            else "balances"
            if "/balances" in path
            else "account_details"
        )
        calls.append(stage)
        if stage == failing_stage:
            return status_code, {"external": "untrusted-secret-text"}
        if stage == "profiles":
            return 200, [{"id": 123, "type": "personal"}]
        return 200, []

    monkeypatch.setattr(wise, "_get", get)
    failed = wise.status()

    assert failed["ok"] is False
    assert failed["retry_after_seconds"] == 30
    assert failed["integration_error"] == {
        "provider": "wise",
        "kind": expected_kind,
        "error_type": "WiseHTTPError",
        "stage": failing_stage,
        "retryable": retryable,
        "consecutive_failures": 1,
        "retry_after_seconds": 30,
        "status_code": status_code,
    }
    assert "untrusted-secret-text" not in str(failed)

    suppressed = wise.status()
    assert suppressed["ok"] is False
    assert suppressed["integration_error"]["status_code"] == status_code
    assert calls.count(failing_stage) == 1


def test_wise_malformed_success_payload_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(wise, "load_token", lambda: "test-token")
    monkeypatch.setattr(wise, "_get", lambda *_args, **_kwargs: (200, {"unexpected": True}))

    failed = wise.status()

    assert failed["ok"] is False
    assert failed["integration_error"]["kind"] == "payload"
    assert failed["integration_error"]["stage"] == "profiles"
    assert failed["retry_after_seconds"] == 30
