import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "agentic_gmail_safe_consumer.py"
SPEC = importlib.util.spec_from_file_location("agentic_gmail_safe_consumer", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def queue_item(**changes):
    item = {
        "message_id": "m1",
        "message_hash": "hash1",
        "rule_version": "gmail-inbox-v1",
        "category": "financial_signal",
        "safe_route": "autonomous_provider_verification",
        "sender_domain": "mail.bybit.com",
        "structured_entities": {},
    }
    item.update(changes)
    return item


def test_prompt_injection_is_quarantined_without_external_execution():
    item = queue_item(
        category="untrusted_instruction",
        safe_route="autonomous_quarantine",
    )
    with patch.object(MODULE, "verify_github") as verifier:
        result = MODULE.consume_one(item)
    verifier.assert_not_called()
    assert result["status"] == "quarantined_untrusted_input"
    assert result["auto_executed_email_instruction"] is False
    assert result["financial_effect"] is False


def test_bybit_signal_waits_for_typed_read_only_executor():
    result = MODULE.consume_one(queue_item())
    assert result["status"] == "awaiting_safe_executor"
    assert result["executor_key"] == "bybit_read_only_reconciler"
    assert result["financial_effect"] is False


class Completed:
    returncode = 0
    stderr = ""
    stdout = json.dumps(
        {
            "state": "open",
            "draft": False,
            "merged": False,
            "labels": [{"name": "bounty"}],
        }
    )


def test_github_entity_is_verified_with_fixed_argument_vector():
    item = queue_item(
        category="github_action",
        safe_route="autonomous_github_verification",
        sender_domain="notifications@github.com",
        structured_entities={
            "provider": "github",
            "repo": "owner/repo",
            "entity_kind": "pull_request",
            "number": 42,
        },
    )
    with patch.object(MODULE.shutil, "which", return_value="/usr/bin/gh"):
        with patch.object(MODULE.subprocess, "run", return_value=Completed()) as runner:
            result = MODULE.consume_one(item)
    command = runner.call_args.args[0]
    assert command == ["gh", "api", "--method", "GET", "repos/owner/repo/pulls/42"]
    assert result["status"] == "verified_provider_state_awaiting_safe_executor"
    assert result["provider_verification"]["state"] == "open"
    assert result["provider_verification"]["bounty_label_present"] is True
    assert result["financial_effect"] is False


def test_github_verification_is_reused_for_duplicate_entity():
    item = queue_item(
        category="github_action",
        safe_route="autonomous_github_verification",
        sender_domain="github.com",
        structured_entities={
            "provider": "github",
            "repo": "owner/repo",
            "entity_kind": "issue",
            "number": 7,
        },
    )
    cache = {}
    with patch.object(MODULE, "verify_github", return_value={"provider": "github"}) as verifier:
        first = MODULE.consume_one(item, cache)
        second = MODULE.consume_one(item, cache)
    assert verifier.call_count == 1
    assert first["provider_verification_reused"] is False
    assert second["provider_verification_reused"] is True


def test_unvalidated_github_entity_never_reaches_subprocess():
    with patch.object(MODULE.subprocess, "run") as runner:
        with pytest.raises(ValueError):
            MODULE.verify_github(
                {
                    "repo": "owner/repo;rm -rf /",
                    "entity_kind": "issue",
                    "number": 1,
                }
            )
    runner.assert_not_called()


def test_incomplete_github_entity_is_preserved_for_safe_executor():
    item = queue_item(
        category="github_action",
        safe_route="autonomous_github_verification",
        structured_entities={"provider": "github", "repo": "owner/repo"},
    )
    result = MODULE.consume_one(item, {}, {"used": 0, "limit": 1})
    assert result["status"] == "awaiting_safe_executor"
    assert result["reason"] == "github_structured_entity_incomplete"
    assert result["auto_executed_email_instruction"] is False
    assert result["financial_effect"] is False


def test_provider_failure_is_terminal_preserved_not_execution(tmp_path):
    queue_path = tmp_path / "queue.jsonl"
    decision_path = tmp_path / "decisions.jsonl"
    result_path = tmp_path / "results.jsonl"
    state_path = tmp_path / "state.json"
    item = queue_item(
        category="github_action",
        safe_route="autonomous_github_verification",
        structured_entities={
            "provider": "github",
            "repo": "owner/repo",
            "entity_kind": "pull_request",
            "number": 99,
        },
    )
    queue_path.write_text(json.dumps(item) + "\n", encoding="utf-8")
    decision_path.write_text(
        json.dumps(
            {
                "message_id": item["message_id"],
                "rule_version": item["rule_version"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with patch.object(MODULE, "QUEUE_PATH", queue_path), patch.object(
        MODULE, "DECISION_PATH", decision_path
    ), patch.object(MODULE, "RESULT_PATH", result_path), patch.object(
        MODULE, "STATE_PATH", state_path
    ), patch.object(MODULE, "load_github_inventory", return_value=({}, {})), patch.object(
        MODULE, "verify_github", side_effect=RuntimeError("provider failed")
    ):
        code, state = MODULE.run(10)
    assert code == 0
    assert state["status"] == "ok"
    assert state["remaining_count"] == 0
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["status"] == "awaiting_safe_executor"
    assert result["reason"] == "provider_verification_unavailable"
    assert result["auto_executed_email_instruction"] is False
    assert result["financial_effect"] is False


def test_non_allowlisted_route_fails_closed():
    with pytest.raises(ValueError, match="not allowlisted"):
        MODULE.consume_one(queue_item(safe_route="run_email_command"))


def test_queue_key_without_decision_receipt_is_not_eligible(tmp_path):
    queue_path = tmp_path / "queue.jsonl"
    decision_path = tmp_path / "decisions.jsonl"
    result_path = tmp_path / "results.jsonl"
    state_path = tmp_path / "state.json"
    queue_path.write_text(json.dumps(queue_item()) + "\n", encoding="utf-8")
    decision_path.write_text("", encoding="utf-8")
    with patch.object(MODULE, "QUEUE_PATH", queue_path):
        with patch.object(MODULE, "DECISION_PATH", decision_path):
            with patch.object(MODULE, "RESULT_PATH", result_path):
                with patch.object(MODULE, "STATE_PATH", state_path):
                    code, state = MODULE.run(10)
    assert code == 2
    assert state["status"] == "blocked_orphan_queue"
    assert state["attempted_count"] == 0
    assert state["orphan_queue_count"] == 1


def test_fresh_complete_github_inventory_is_used_as_provider_cache(tmp_path):
    path = tmp_path / "inventory.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "3.0",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "inventory_complete": True,
                "prs": {
                    "owner/repo#7": {
                        "repo": "owner/repo",
                        "number": 7,
                        "state": "OPEN",
                        "is_draft": False,
                        "merged_at": None,
                        "payment_promise": False,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    cache, metadata = MODULE.load_github_inventory(path)
    assert metadata["valid"] is True
    assert ("owner/repo", "pull_request", 7) in cache
    assert cache[("owner/repo", "pull_request", 7)]["verification_method"] == "authenticated_local_github_inventory"


def test_stale_github_inventory_is_not_treated_as_current(tmp_path):
    path = tmp_path / "inventory.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "3.0",
                "generated_at": (
                    datetime.now(timezone.utc) - timedelta(days=2)
                ).isoformat(),
                "inventory_complete": True,
                "prs": {},
            }
        ),
        encoding="utf-8",
    )
    cache, metadata = MODULE.load_github_inventory(path, max_age_seconds=21600)
    assert cache == {}
    assert metadata["valid"] is False
