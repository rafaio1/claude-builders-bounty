import json
import os
import sys
import pytest

sys.path.insert(0, "/Agentic/scripts")
import zealy_campaign_scanner as zcs


class TestZealyCampaignScanner:
   def test_scan_returns_expected_count(self):
       opps = zcs.scan_zealy_campaigns()
       assert len(opps) == 10

   def test_opportunity_schema(self):
       opps = zcs.scan_zealy_campaigns()
       required = {"id", "platform", "protocol", "quest_type", "reward_usd", "chain", "autonomous_capable", "status"}
       for o in opps:
           assert required.issubset(o.keys())
           assert o["platform"] == "zealy"
           assert isinstance(o["reward_usd"], (int, float))
           assert o["reward_usd"] > 0

   def test_no_telegram_calls(self):
       source = open("/Agentic/scripts/zealy_campaign_scanner.py").read()
       assert "telegram_alert" not in source
       assert "send_telegram" not in source
       assert "requests.post" not in source

   def test_gitignore_entries(self):
       gi = open("/Agentic/.gitignore").read()
       assert "config/zealy_scanner.json" in gi
       assert "revenue/zealy_opportunities/" in gi

   def test_main_execution_dry_run(self, tmp_path, monkeypatch):
       monkeypatch.setattr(zcs, "ZEALY_CONFIG_PATH", str(tmp_path / "cfg.json"))
       monkeypatch.setattr(zcs, "ZEALY_LOG_PATH", str(tmp_path / "scan.log"))
       monkeypatch.setattr(zcs, "ZEALY_OPPORTUNITIES_DIR", str(tmp_path / "opps"))
       zcs.main()
       assert (tmp_path / "cfg.json").exists()
       cfg = json.loads((tmp_path / "cfg.json").read_text())
       assert cfg["last_scan"] is not None
       assert len(cfg["scanned_campaigns"]) == 10
       opp_files = list((tmp_path / "opps").glob("*.json"))
       assert len(opp_files) == 10
