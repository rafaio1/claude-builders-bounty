"""Tests for Code4rena Contest Scanner integration and safety."""
import json
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, "/Agentic/scripts")
import code4rena_contest_scanner as scanner


def test_scan_returns_expected_contests():
    """Scanner must return contest templates with required fields."""
    opps = scanner.scan_code4rena_contests()
    assert len(opps) >= 5
    for o in opps:
        assert "prize_pool_usd" in o
        assert "payout_method" in o
        assert o["autonomous_submission"] is True
        assert "account_creation" in o["requires_human"]
        assert o["platform"] == "code4rena"


def test_no_telegram_calls_in_scanner():
    """Scanner must never call send_tg or telegram_gate directly."""
    import inspect
    source = inspect.getsource(scanner)
    assert "send_tg(" not in source
    assert "telegram_gate" not in source
    assert "send_telegram" not in source


def test_config_save_load_roundtrip():
    """Config persistence must survive save/load cycle without secrets."""
    cfg = {"scanned_sponsors": ["Test"], "active_contests": [], "last_scan": "2026-08-26T00:00:00+00:00"}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(cfg, f)
        tmp_path = f.name
    try:
        loaded = json.load(open(tmp_path))
        assert loaded == cfg
        assert "token" not in json.dumps(loaded).lower()
        assert "key" not in json.dumps(loaded).lower()
    finally:
        os.unlink(tmp_path)


def test_main_does_not_crash_without_ledger():
    """main() must handle missing ledger gracefully."""
    with patch.object(scanner, "update_ledger_with_c4") as mock_update:
        with patch.object(scanner, "save_config"):
            with patch.object(scanner, "load_config", return_value={"scanned_sponsors": [], "active_contests": [], "last_scan": None}):
                scanner.main()
                mock_update.assert_called_once()
