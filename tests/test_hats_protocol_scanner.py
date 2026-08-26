"""Tests for Hats Protocol & DAO Scanner integration and safety."""
import os
import sys
import inspect

sys.path.insert(0, "/Agentic/scripts")
import hats_protocol_scanner as scanner


def test_scan_returns_expected_ecosystems():
    """Scanner must return all curated DAO ecosystems with required fields."""
    opps = scanner.scan_hats_ecosystems()
    assert len(opps) == 10
    ids = {o["id"] for o in opps}
    assert "HATS-gitcoin-dao" in ids
    assert "HATS-optimism-collective" in ids
    for o in opps:
        assert "payout_method" in o
        assert "autonomous_friendly" in o
        assert "requires_human" in o
        assert isinstance(o["requires_human"], list)


def test_no_telegram_calls_in_scanner():
    """Scanner must never call send_tg or telegram_gate directly."""
    source = inspect.getsource(scanner)
    assert "send_tg(" not in source
    assert "telegram_gate" not in source
    assert "send_telegram" not in source


def test_opportunities_dir_is_gitignored():
    """Revenue opportunities directory must be excluded from version control."""
    gitignore_path = "/Agentic/.gitignore"
    assert os.path.exists(gitignore_path)
    with open(gitignore_path) as f:
        content = f.read()
    assert "revenue/hats_opportunities/" in content


def test_config_is_gitignored():
    """Scanner config file must be excluded from version control."""
    gitignore_path = "/Agentic/.gitignore"
    with open(gitignore_path) as f:
        content = f.read()
    assert "config/hats_protocol_scanner.json" in content


def test_main_runs_without_error(tmp_path):
    """Main function must complete without raising exceptions."""
    import unittest.mock as mock
    with mock.patch.object(scanner, "HATS_CONFIG_PATH", str(tmp_path / "cfg.json")), \
         mock.patch.object(scanner, "HATS_LOG_PATH", str(tmp_path / "scan.log")), \
         mock.patch.object(scanner, "HATS_OPPORTUNITIES_DIR", str(tmp_path / "opps")):
        scanner.main()
    assert (tmp_path / "cfg.json").exists()
    assert (tmp_path / "scan.log").exists()
