"""Tests for Layer3 Quest Executor integration and safety."""
import os
import sys
import inspect

sys.path.insert(0, "/Agentic/scripts")
import layer3_quest_executor as scanner


def test_scan_returns_expected_campaigns():
    """Scanner must return all curated campaigns with required fields."""
    opps = scanner.scan_layer3_quests()
    assert len(opps) == 10
    ids = {o["id"] for o in opps}
    assert "L3-zksync-era-testnet_deploy" in ids
    assert "L3-starknet-bridge_testnet" in ids
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
    assert "revenue/layer3_opportunities/" in content


def test_config_is_gitignored():
    """Scanner config file must be excluded from version control."""
    gitignore_path = "/Agentic/.gitignore"
    with open(gitignore_path) as f:
        content = f.read()
    assert "config/layer3_scanner.json" in content


def test_main_runs_without_error(tmp_path):
    """Main function must complete without raising exceptions."""
    import unittest.mock as mock
    with mock.patch.object(scanner, "L3_CONFIG_PATH", str(tmp_path / "cfg.json")), \
         mock.patch.object(scanner, "L3_LOG_PATH", str(tmp_path / "scan.log")), \
         mock.patch.object(scanner, "L3_OPPORTUNITIES_DIR", str(tmp_path / "opps")):
        scanner.main()
    assert (tmp_path / "cfg.json").exists()
    assert (tmp_path / "scan.log").exists()
