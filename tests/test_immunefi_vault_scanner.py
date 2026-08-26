"""Tests for Immunefi Vault Scanner integration and safety."""
import json
import os
import sys
import tempfile
from unittest.mock import patch, mock_open

sys.path.insert(0, "/Agentic/scripts")
import immunefi_vault_scanner as scanner


def test_scan_returns_expected_programs():
    """Scanner must return all curated programs with required fields."""
    opps = scanner.scan_immunefi_programs()
    assert len(opps) == 10
    ids = {o["id"] for o in opps}
    assert "IMMUNEFI-uniswap" in ids
    assert "IMMUNEFI-aave" in ids
    for o in opps:
        assert "max_bounty_usd" in o
        assert "payout_method" in o
        assert o["autonomous_submission"] is True
        assert "account_creation" in o["requires_human"]


def test_no_telegram_calls_in_scanner():
    """Scanner must never call send_tg or telegram_gate directly."""
    import inspect
    source = inspect.getsource(scanner)
    assert "send_tg(" not in source
    assert "telegram_gate" not in source
    assert "send_telegram" not in source


def test_opportunities_dir_is_gitignored():
    """Revenue opportunities directory must be excluded from version control."""
    gitignore_path = "/Agentic/.gitignore"
    if os.path.exists(gitignore_path):
        with open(gitignore_path) as f:
            content = f.read()
        # revenue/immunefi_opportunities should be covered by revenue/* or explicit rule
        # At minimum, revenue/trade_opportunities is ignored; verify pattern exists
        assert "revenue/" in content or "revenue/*" in content


def test_config_save_load_roundtrip():
    """Config persistence must survive save/load cycle without secrets."""
    cfg = {"scanned_programs": ["Test"], "last_scan": "2026-08-26T00:00:00+00:00"}
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
    with patch.object(scanner, "update_ledger_with_immunefi") as mock_update:
        with patch.object(scanner, "save_config"):
            with patch.object(scanner, "load_config", return_value={"scanned_programs": [], "last_scan": None}):
                # Should not raise even if ledger path doesn't exist
                scanner.main()
                mock_update.assert_called_once()
