"""Tests for strict trace sanitization (paths + secrets) in ghostcli/env."""

from __future__ import annotations

import pytest

from agentic.env import mask_paths, mask_secrets
from agentic.ghostcli import sanitize_trace


class TestMaskPaths:
    """mask_paths must redact absolute filesystem paths."""

    def test_root_home_path(self) -> None:
        text = "loaded config from /root/.automaton/.env successfully"
        out = mask_paths(text)
        assert "/root/.automaton" not in out
        assert "***PATH_REDACTED***" in out

    def test_home_user_path(self) -> None:
        text = "cache at /home/deploy/app/cache.db"
        out = mask_paths(text)
        assert "/home/deploy" not in out
        assert "***PATH_REDACTED***" in out

    def test_opt_path(self) -> None:
        text = "binary: /opt/murre/bin/runner"
        out = mask_paths(text)
        assert "/opt/murre" not in out

    def test_tmp_path(self) -> None:
        text = "temp file /tmp/agent-upload-xyz.csv"
        out = mask_paths(text)
        assert "/tmp/agent-upload" not in out

    def test_windows_user_path(self) -> None:
        text = r"log saved to C:\Users\Admin\AppData\Local\agentic.log"
        out = mask_paths(text)
        assert r"C:\Users\Admin" not in out
        assert "***PATH_REDACTED***" in out

    def test_no_false_positive_relative(self) -> None:
        text = "relative/path/to/file.txt and ./local"
        out = mask_paths(text)
        assert out == text

    def test_non_string_coerced(self) -> None:
        # None is coerced to "None" which contains no paths, so it passes through.
        assert mask_paths(None) == "None"
        assert mask_paths(123) == "123"


class TestSanitizeTraceStrict:
    """sanitize_trace must apply both secret and path masking."""

    def test_masks_api_key_and_path(self) -> None:
        text = (
            "Using GHOSTCLI_API_KEY=sk_live_abcdefghijk1234567890 "
            "from /root/.automaton/.env"
        )
        out = sanitize_trace(text)
        assert "sk_live_abcdefghijk1234567890" not in out
        assert "/root/.automaton/.env" not in out
        assert "***REDACTED***" in out
        assert "***PATH_REDACTED***" in out

    def test_masks_bybit_secret_in_json_trace(self) -> None:
        text = '{"key": "BYBIT_API_SECRET", "value": "aB3dEfGhIjKlMnOpQrStUvWxYz123456"}'
        out = sanitize_trace(text)
        assert "aB3dEfGhIjKlMnOpQrStUvWxYz123456" not in out

    def test_masks_long_token(self) -> None:
        token = "A" * 40
        text = f"bearer {token}"
        out = sanitize_trace(text)
        assert token not in out

    def test_preserves_safe_text(self) -> None:
        text = "All systems nominal. No secrets here."
        assert sanitize_trace(text) == text

    def test_non_string_returns_empty(self) -> None:
        assert sanitize_trace(None) == ""  # type: ignore[arg-type]
        assert sanitize_trace(42) == ""  # type: ignore[arg-type]


class TestMaskSecretsStillWorks:
    """Ensure existing mask_secrets behaviour is unchanged."""

    def test_known_key_redacted(self) -> None:
        text = "ANTHROPIC_API_KEY=sk-ant-abc123def456ghi789jkl012mno345"
        out = mask_secrets(text)
        assert "sk-ant-abc123def456ghi789jkl012mno345" not in out
        assert "***REDACTED***" in out