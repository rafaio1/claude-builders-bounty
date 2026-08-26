"""Tests for RabbitHole Campaign Scanner integration and safety."""
import os
import sys
import inspect

sys.path.insert(0, "/Agentic/scripts")
import rabbithole_campaign_scanner as scanner


def test_scan_returns_expected_campaigns():
    """Scanner must return all curated campaigns with required fields."""
    opps = scanner.scan_rabbithole_campaigns()
    assert len(opps) == 10
    ids = {o["id"] for o in opps}
    assert "RH-arbitrum-odyssey-bridge_and_swap" in ids
    assert "RH-base-onboarding-bridge_and_deploy" in ids
    for o in opps:
        assert "reward_usd" in o
        assert "payout_method" in o
        assert "autonomous_capable" in o
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
    assert "revenue/rabbithole_opportunities/" in content


def test_config_is_gitignored():
    """Scanner config file must be excluded from version control."""
    gitignore_path = "/Agentic/.gitignore"
    with open(gitignore_path) as f:
        content = f.read()
    assert "config/rabbithole_scanner.json" in content


def test_main_runs_without_error(tmp_path):
    """Main function must complete without raising exceptions."""
    import unittest.mock as mock
    with mock.patch.object(scanner, "RH_CONFIG_PATH", str(tmp_path / "cfg.json")), \
         mock.patch.object(scanner, "RH_LOG_PATH", str(tmp_path / "scan.log")), \
         mock.patch.object(scanner, "RH_OPPORTUNITIES_DIR", str(tmp_path / "opps")):
        scanner.main()
    assert (tmp_path / "cfg.json").exists()
    assert (tmp_path / "scan.log").exists()
