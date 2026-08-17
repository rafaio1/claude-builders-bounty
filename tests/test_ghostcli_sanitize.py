from __future__ import annotations

import pytest

from agentic.ghostcli import sanitize_trace


def test_sanitize_authorization_bearer() -> None:
    text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    out = sanitize_trace(text)
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in out
    assert "***REDACTED***" in out


def test_sanitize_ghostcli_api_key_assignment() -> None:
    text = 'Config loaded: GHOSTCLI_API_KEY=gk-live-abcdefghijklmnopqrstuvwx'
    out = sanitize_trace(text)
    assert "gk-live-abcdefghijklmnopqrstuvwx" not in out
    assert "***REDACTED***" in out


def test_sanitize_bybit_credentials() -> None:
    text = "BYBIT_API_SECRET=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0"
    out = sanitize_trace(text)
    assert "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0" not in out
    assert "***REDACTED***" in out


def test_sanitize_cookie_header() -> None:
    text = "Cookie: session=abc123def456ghi789jkl012mno345pqr678stu901vwx234; path=/"
    out = sanitize_trace(text)
    assert "abc123def456ghi789jkl012mno345pqr678stu901vwx234" not in out
    assert "***REDACTED***" in out


def test_sanitize_generic_long_token() -> None:
    text = "token=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnop"
    out = sanitize_trace(text)
    assert "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnop" not in out
    assert "***TOKEN_REDACTED***" in out


def test_sanitize_preserves_safe_text() -> None:
    text = "Model returned verdict approve with reason: patch looks good"
    assert sanitize_trace(text) == text


def test_sanitize_empty_and_non_string() -> None:
    assert sanitize_trace("") == ""
    assert sanitize_trace(None) == ""  # type: ignore[arg-type]
    assert sanitize_trace(123) == ""  # type: ignore[arg-type]


def test_sanitize_does_not_touch_short_strings() -> None:
    text = "short value abc123"
    assert sanitize_trace(text) == text


def test_sanitize_multiple_secrets_in_one_trace() -> None:
    text = (
        "Request headers:\n"
        "Authorization: Bearer sk_live_abcdefghijklmnopqrstuvwxyz123456\n"
        "Cookie: sid=aaaabbbbccccddddeeeeffffgggghhhhiiiijjjj\n"
        "Body: {\"model\": \"test\"}"
    )
    out = sanitize_trace(text)
    assert "sk_live_abcdefghijklmnopqrstuvwxyz123456" not in out
    assert "aaaabbbbccccddddeeeeffffgggghhhhiiiijjjj" not in out
    assert "\"model\": \"test\"" in out