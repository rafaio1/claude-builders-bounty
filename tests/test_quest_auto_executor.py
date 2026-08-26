import json
import os
import sys
import pytest

sys.path.insert(0, "/Agentic/scripts")
import quest_auto_executor as qae


class TestQuestAutoExecutor:
   def test_syntax_valid(self):
       import ast
       source = open("/Agentic/scripts/quest_auto_executor.py").read()
       ast.parse(source)

   def test_no_telegram_calls(self):
       source = open("/Agentic/scripts/quest_auto_executor.py").read()
       assert "telegram_alert" not in source
       assert "send_telegram" not in source
       assert "requests.post" not in source

   def test_load_state_returns_dict_when_missing(self, tmp_path, monkeypatch):
       fake_state = str(tmp_path / "nonexistent_state.json")
       monkeypatch.setattr(qae, "STATE_PATH", fake_state)
       state = qae.load_state()
       assert isinstance(state, dict)
       assert "executed_tasks" in state
       assert "pending_human" in state

   def test_simulate_quest_skips_already_executed(self):
       state = {"executed_tasks": {"q1": {"status": "simulated_success"}}, "pending_human": []}
       quest = {"id": "q1", "platform": "layer3", "chain": "goerli", "quest_type": "deploy"}
       result = qae.simulate_quest_execution(quest, state)
       assert result["status"] == "skipped"

   def test_simulate_quest_mainnet_requires_human(self):
       state = {"executed_tasks": {}, "pending_human": []}
       quest = {"id": "q2", "platform": "rabbithole", "chain": "ethereum", "quest_type": "bridge"}
       result = qae.simulate_quest_execution(quest, state)
       assert result["status"] == "pending_human"
       assert "q2" in state["pending_human"]

   def test_simulate_quest_testnet_executes(self):
       state = {"executed_tasks": {}, "pending_human": []}
       quest = {"id": "q3", "platform": "zealy", "chain": "fuji", "quest_type": "mint"}
       result = qae.simulate_quest_execution(quest, state)
       assert result["status"] == "simulated_success"
       assert result["tx_hash"].startswith("0x")
       assert "q3" in state["executed_tasks"]

   def test_no_secrets_in_source(self):
       source = open("/Agentic/scripts/quest_auto_executor.py").read()
       forbidden = ["TELEGRAM_BOT_TOKEN", "PRIVATE_KEY", "API_SECRET", "WALLET_MNEMONIC"]
       for token in forbidden:
           assert token not in source
