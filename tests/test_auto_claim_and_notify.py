from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("auto_claim_and_notify.py")
if not MODULE_PATH.exists():
    MODULE_PATH = Path("/Agentic/scripts/auto_claim_and_notify.py")
SPEC = importlib.util.spec_from_file_location("auto_claim_and_notify_hardened", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def safe_item(*, issue: int = 7, body: str = "Provider instructions\n\n/claim\n") -> dict:
    url = f"https://github.com/example/project/issues/{issue}"
    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return {
        "source": "algora",
        "provider": "algora",
        "platform": "github",
        "candidate_id": f"algora-{issue}",
        "stable_id": f"algora:algora-{issue}",
        "url": url,
        "action": "claim",
        "claim_command": "/claim",
        "listing_verified": True,
        "source_fresh": True,
        "provider_verified": True,
        "explicit_execution_contract": True,
        "human_gates_complete": True,
        "human_gates": {
            "kyc": False,
            "identity": False,
            "social": False,
            "video": False,
            "real_funds": False,
            "trading": False,
            "manual": False,
        },
        "asset": "USDC",
        "network": "solana-mainnet",
        "asset_network_exact": True,
        "route_id": "usdc-solana-to-wise",
        "route_status": "complete_verified",
        "self_custody_rail_verified": True,
        "deadline": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        "gross_verified": 1_000,
        "expected_wise_net_verified": 900,
        "payment_confidence_lcb_ppm": 800_000,
        "net_if_paid_verified": 950,
        "time_to_wise_p90_seconds": 86_400,
        "financial_classification": "unrealized_opportunity_not_revenue",
        "funds_moved": False,
        "realized": 0,
        "action_contract": {
            "platform": "github",
            "kind": "github_issue_comment",
            "provider": "algora",
            "target_url": url,
            "claim_command": "/claim",
            "verified": True,
            "autonomous": True,
            "provider_instruction_sha256": body_hash,
        },
    }


def queue_document(rows: list[dict], *, status: str = "ok") -> dict:
    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "action_queue": rows,
        "research_queue": [],
        "monitor_only": [],
        "funds_moved": False,
        "realized": 0,
    }
    payload["result_sha256"] = MODULE.sha256_bytes(MODULE.canonical_json_bytes(payload))
    return payload


class HardenedAutoClaimTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        MODULE.ROOT = root
        MODULE.LEDGER = root / "data/aro/bounty_ledger.json"
        MODULE.PRIORITY_QUEUE = root / "state/bounty_priority_queue.json"
        MODULE.STATE = root / "state/auto_claim_scout_state.json"
        MODULE.LEGACY_INBOX = root / "data/aro/inbox/pending_bounties.jsonl"
        MODULE.LEDGER.parent.mkdir(parents=True)
        MODULE.PRIORITY_QUEUE.parent.mkdir(parents=True)
        MODULE.LEGACY_INBOX.parent.mkdir(parents=True)
        MODULE.LEDGER.write_text('{"entries": []}\n', encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_queue(self, rows: list[dict], *, status: str = "ok") -> None:
        MODULE.PRIORITY_QUEUE.write_text(
            json.dumps(queue_document(rows, status=status), indent=2) + "\n",
            encoding="utf-8",
        )

    def test_empty_action_queue_is_silent_and_does_not_authenticate(self) -> None:
        self.write_queue([])
        with mock.patch.object(MODULE, "github_login") as login:
            self.assertEqual(MODULE.main(), 0)
        login.assert_not_called()
        self.assertEqual(json.loads(MODULE.LEDGER.read_text(encoding="utf-8"))["entries"], [])
        state = json.loads(MODULE.STATE.read_text(encoding="utf-8"))
        self.assertEqual(state["eligible_this_cycle"], 0)
        self.assertEqual(state["claimed_this_cycle"], 0)
        self.assertEqual(state["routine_notifications_emitted"], 0)

    def test_legacy_inbox_is_ignored_even_when_it_contains_a_claimable_looking_url(self) -> None:
        self.write_queue([])
        # Invalid UTF-8 makes accidental legacy parsing fail loudly; the hardened
        # worker succeeds because it never opens this file.
        MODULE.LEGACY_INBOX.write_bytes(
            b'{"url":"https://github.com/attacker/repo/issues/1"}\n\xff'
        )
        with mock.patch.object(MODULE, "github_login") as login:
            self.assertEqual(MODULE.main(), 0)
        login.assert_not_called()
        state = json.loads(MODULE.STATE.read_text(encoding="utf-8"))
        self.assertTrue(state["legacy_inbox_ignored"])

    def test_any_human_gate_blocks_without_authentication_or_network(self) -> None:
        item = safe_item()
        item["human_gates"]["identity"] = True
        self.write_queue([item])
        with (
            mock.patch.object(MODULE, "github_login") as login,
            mock.patch.object(MODULE.subprocess, "run") as run,
        ):
            self.assertEqual(MODULE.main(), 0)
        login.assert_not_called()
        run.assert_not_called()
        state = json.loads(MODULE.STATE.read_text(encoding="utf-8"))
        target = state["targets"][item["stable_id"]]
        self.assertEqual(target["status"], "contract_rejected")
        self.assertEqual(target["last_error"], "human_gate_identity_not_false")

    def test_missing_exact_action_contract_blocks_without_authentication(self) -> None:
        item = safe_item()
        item.pop("action_contract")
        self.write_queue([item])
        with mock.patch.object(MODULE, "github_login") as login:
            self.assertEqual(MODULE.main(), 0)
        login.assert_not_called()
        state = json.loads(MODULE.STATE.read_text(encoding="utf-8"))
        self.assertEqual(state["targets"][item["stable_id"]]["last_error"], "action_contract_missing")

    def test_safe_synthetic_claim_uses_mocked_subprocess_and_is_idempotently_ledged(self) -> None:
        body = "Official provider instructions\n\n/claim\n"
        item = safe_item(body=body)
        self.write_queue([item])
        before = {
            "state": "OPEN",
            "title": "Synthetic bounty",
            "url": item["url"],
            "body": body,
            "comments": [],
        }
        after = {
            **before,
            "comments": [{"author": {"login": "rafaio1"}, "body": "/claim"}],
        }
        responses = [
            subprocess.CompletedProcess([], 0, "rafaio1\n", ""),
            subprocess.CompletedProcess([], 0, json.dumps(before), ""),
            subprocess.CompletedProcess([], 0, "https://github.com/comment/1\n", ""),
            subprocess.CompletedProcess([], 0, json.dumps(after), ""),
        ]
        with (
            mock.patch.object(MODULE.subprocess, "run", side_effect=responses) as run,
            mock.patch.object(MODULE.time, "sleep"),
        ):
            self.assertEqual(MODULE.main(), 0)

        self.assertEqual(run.call_count, 4)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[0], ["/usr/bin/gh", "api", "user", "--jq", ".login"])
        self.assertEqual(
            commands[2],
            [
                "/usr/bin/gh",
                "issue",
                "comment",
                "7",
                "--repo",
                "example/project",
                "--body",
                "/claim",
            ],
        )
        ledger = json.loads(MODULE.LEDGER.read_text(encoding="utf-8"))
        self.assertEqual(len(ledger["entries"]), 1)
        entry = ledger["entries"][0]
        self.assertTrue(entry["claim_verified"])
        self.assertEqual(entry["claim_command"], "/claim")
        self.assertEqual(entry["priority_stable_id"], item["stable_id"])
        self.assertEqual(entry["gross_verified_unrealized"], 1_000)
        self.assertIn("unrealized", entry["note"])

        # A second cycle recognizes the ledger key before GitHub auth/network.
        with mock.patch.object(MODULE.subprocess, "run") as second_run:
            self.assertEqual(MODULE.main(), 0)
        second_run.assert_not_called()
        ledger_again = json.loads(MODULE.LEDGER.read_text(encoding="utf-8"))
        self.assertEqual(len(ledger_again["entries"]), 1)

    def test_live_provider_instruction_hash_change_blocks_before_post(self) -> None:
        item = safe_item(body="/claim\n")
        self.write_queue([item])
        changed = {
            "state": "OPEN",
            "url": item["url"],
            "body": "different instructions\n/claim\n",
            "comments": [],
        }
        responses = [
            subprocess.CompletedProcess([], 0, "rafaio1\n", ""),
            subprocess.CompletedProcess([], 0, json.dumps(changed), ""),
        ]
        with (
            mock.patch.object(MODULE.subprocess, "run", side_effect=responses) as run,
            mock.patch.object(MODULE.time, "sleep"),
        ):
            self.assertEqual(MODULE.main(), 0)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(json.loads(MODULE.LEDGER.read_text(encoding="utf-8"))["entries"], [])
        state = json.loads(MODULE.STATE.read_text(encoding="utf-8"))
        self.assertEqual(
            state["targets"][item["stable_id"]]["last_error"],
            "provider_instruction_hash_mismatch",
        )


if __name__ == "__main__":
    unittest.main()
