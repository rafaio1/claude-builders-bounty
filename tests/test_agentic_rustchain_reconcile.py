#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("agentic_rustchain_reconcile.py")
if not MODULE_PATH.exists():
    MODULE_PATH = Path("/usr/local/lib/agentic/agentic_rustchain_reconcile.py")
SPEC = importlib.util.spec_from_file_location("rustchain_reconcile", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture_history() -> dict:
    rows = [
        (5.0, 38877, 1788120601, "6a600cb0d002d4999b18cd08a0cdba97"),
        (5.0, 38877, 1788120601, "57192c418abe0bd6867f7ada42fe6a4f"),
        (1.0, 38878, 1788120601, "39d1193717912e63040f59d54430bec0"),
        (1.0, 38878, 1788120601, "ff218948ee74dfc51c4086ac500954d9"),
        (1.0, 38878, 1788120601, "2c5ba8fd021ff7e6ef1c0eaad83cbc9e"),
        (1.0, 38878, 1788120601, "e68236514c6554b5cdcbc0e066b6d852"),
        (40.0, 38878, 1788120601, "d2766fff047a87359bc0651fb012743c"),
        (5.0, 38871, 1788117001, "85a84808b75788e791e2e921f99de9d1"),
        (5.0, 38851, 1788104402, "ba9275756fa973756dcad8ebdbcc4f47"),
    ]
    transactions = [
        {
            "amount": amount,
            "epoch": epoch,
            "from": "founder_community",
            "reason": f"transfer_in:founder_community:{txid}",
            "timestamp": timestamp,
            "tx_hash": txid,
            "type": "transfer_in",
        }
        for amount, epoch, timestamp, txid in rows
    ]
    core = {
        "ok": True,
        "miner_id": MODULE.WALLET,
        "total": len(transactions),
        "transactions": transactions,
    }
    return {
        **core,
        "source_url": MODULE.HISTORY_URL,
        "source_urls": [MODULE.HISTORY_URL],
        "documentation_url": MODULE.HISTORY_DOCUMENTATION_URL,
        "response_sha256": MODULE.canonical_json_hash(core),
    }


def fixture_evidence() -> dict:
    wallet = MODULE.WALLET
    claim_rows = []
    claim_times = ["2026-08-29T16:55:45Z", "2026-08-29T16:56:05Z", "2026-08-29T16:56:26Z", "2026-08-29T16:56:53Z"]
    for (comment_id, contribution), created_at in zip(MODULE.ISSUE_CLAIMS, claim_times):
        claim_rows.append(
            {
                "evidence_type": "public_claim_submission",
                "source_url": f"https://github.com/example/{comment_id}",
                "provider_actor": "rafaio1",
                "observed_at": created_at,
                "receive_address": wallet,
                "contribution_url": contribution,
            }
        )
    history = fixture_history()
    receipts = {
        "issue_254": MODULE.uniquely_attribute_receipts(
            history,
            provider_confirmed_at="2026-08-29T20:03:49Z",
            amount_each=1.0,
            count=4,
        ),
        "prs": {
            8295: MODULE.uniquely_attribute_receipts(
                history,
                provider_confirmed_at="2026-08-29T19:00:11Z",
                amount_each=5.0,
                count=1,
            ),
            8289: MODULE.uniquely_attribute_receipts(
                history,
                provider_confirmed_at="2026-08-29T15:38:57Z",
                amount_each=5.0,
                count=1,
            ),
        },
    }
    return {
        "wallet": {
            "miner_id": wallet,
            "amount_i64": 64_000_000,
            "amount_rtc": 64.0,
            "source_url": MODULE.BALANCE_URL,
        },
        "wallet_history": history,
        "wallet_receipts": receipts,
        "issue_254": {
            "claims": claim_rows,
            "provider": {
                "evidence_type": "provider_payout_confirmation",
                "source_url": "https://github.com/Scottcjn/rustchain-bounties/issues/254#issuecomment-5464599807",
                "provider_actor": "Scottcjn",
                "observed_at": "2026-08-29T20:03:49Z",
                "confirmed_amount": 4.0,
                "asset": "RTC",
                "confirmation_text_sha256": "a" * 64,
            },
        },
        "prs": {
            8295: {
                "number": 8295,
                "created_at": "2026-08-29T17:15:54Z",
                "merged_at": "2026-08-29T19:00:02Z",
                "pr_url": "https://github.com/Scottcjn/Rustchain/pull/8295",
                "merge_commit_sha": "b" * 40,
                "provider_confirmed_at": "2026-08-29T19:00:11Z",
                "provider_confirmation_url": "https://github.com/Scottcjn/Rustchain/pull/8295#issuecomment-5464266722",
                "reward": 5.0,
                "provider_text_sha256": "c" * 64,
            },
            8289: {
                "number": 8289,
                "created_at": "2026-08-29T13:51:19Z",
                "merged_at": "2026-08-29T15:38:49Z",
                "pr_url": "https://github.com/Scottcjn/Rustchain/pull/8289",
                "merge_commit_sha": "d" * 40,
                "provider_confirmed_at": "2026-08-29T15:38:57Z",
                "provider_confirmation_url": "https://github.com/Scottcjn/Rustchain/pull/8289#issuecomment-5463304541",
                "reward": 5.0,
                "provider_text_sha256": "e" * 64,
            },
        },
    }


class ReconcilerTests(unittest.TestCase):
    def make_root(self) -> Path:
        root = Path(self.temp.name)
        ledger = root / "data/aro/bounty_receive_ledger.json"
        ledger.parent.mkdir(parents=True)
        ledger.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "ledger_id": "test",
                    "updated_at": "2026-08-29T00:00:00Z",
                    "entries": [
                        {
                            "ledger_id": "legacy",
                            "bounty_key": "unknown|rustchain/rustchain|254|idx21",
                            "repo": "rustchain/rustchain",
                            "issue_or_pr": "254",
                            "reward_asset": "USD",
                            "network": "polygon",
                            "receive_address": "0xwrong",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (root / "data/aro/realized_revenue_ledger.jsonl").write_text("", encoding="utf-8")
        return root

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_reconcile_corrects_legacy_and_is_idempotent(self) -> None:
        root = self.make_root()
        first = MODULE.reconcile(root, fixture_evidence(), now="2026-09-01T14:20:00+00:00")
        ledger = json.loads((root / "data/aro/bounty_receive_ledger.json").read_text(encoding="utf-8"))
        self.assertTrue(first["ledger_changed"])
        self.assertEqual(len(ledger["entries"]), 3)
        self.assertEqual({row["reward_asset"] for row in ledger["entries"]}, {"RTC"})
        self.assertEqual({row["status"] for row in ledger["entries"]}, {"wallet_received"})
        self.assertEqual(sum(row["provider_confirmed_amount"] for row in ledger["entries"]), 14.0)
        self.assertEqual(sum(row["amount_received"] for row in ledger["entries"]), 14.0)
        self.assertEqual(sum(len(row["txids"]) for row in ledger["entries"]), 6)
        self.assertTrue(all(row["confirmation_status"] == "confirmed_immutable_ledger" for row in ledger["entries"]))
        self.assertTrue(all(row["blockers"] == [] for row in ledger["entries"]))
        self.assertTrue(all(row["bybit_route_status"] == "conversion_pending" for row in ledger["entries"]))
        self.assertTrue(all(row["wise_route_status"] == "conversion_pending" for row in ledger["entries"]))
        self.assertTrue(all(row["action_required"] is False for row in ledger["entries"]))
        self.assertTrue(all(row["human_action"] == "none" for row in ledger["entries"]))
        self.assertTrue(all(row["autonomous_recovery"] is True for row in ledger["entries"]))
        self.assertTrue(all(all(isinstance(step, str) and step.strip() for step in row["recovery_steps"]) for row in ledger["entries"]))
        self.assertTrue(all(all("usuario deve" not in step.lower() for step in row["recovery_steps"]) for row in ledger["entries"]))
        notifications = [json.loads(line) for line in (root / "data/aro/inbox/notifications_outbox.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(notifications), 3)
        self.assertTrue(all(item["action_required"] is False for item in notifications))
        self.assertTrue(all(item["informational"] is True for item in notifications))
        self.assertTrue(all(item["autonomous_recovery"] is True for item in notifications))
        self.assertTrue(all(item["alert_class"] == "wallet_received" for item in notifications))
        self.assertTrue(all(item["terminal_blocked"] is False for item in notifications))
        self.assertTrue(all(item["status"] == "wallet_received" for item in notifications))
        self.assertTrue(all(item["txids"] for item in notifications))
        emails = [json.loads(line) for line in (root / "data/aro/inbox/email_outbox.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertTrue(all("Acao humana: nenhuma" in item["body"] for item in emails))
        self.assertTrue(all("BOUNTY RECEBIDO NA CARTEIRA" in item["body"] for item in emails))
        self.assertTrue(first["autonomous_recovery"])
        self.assertIs(first["human_action_required"], False)
        self.assertEqual(first["wallet_history_url"], MODULE.HISTORY_URL)
        self.assertEqual(first["wallet_history_sha256"], fixture_evidence()["wallet_history"]["response_sha256"])
        before = (root / "data/aro/bounty_receive_ledger.json").read_bytes()
        second = MODULE.reconcile(root, fixture_evidence(), now="2026-09-01T14:30:00+00:00")
        after = (root / "data/aro/bounty_receive_ledger.json").read_bytes()
        self.assertFalse(second["ledger_changed"])
        self.assertEqual(before, after)
        self.assertEqual(second["queued_notification_count"], 0)
        self.assertEqual(second["queued_email_count"], 0)

    def test_wallet_receipt_does_not_create_exchange_or_fiat_settlement(self) -> None:
        root = self.make_root()
        result = MODULE.reconcile(root, fixture_evidence(), now="2026-09-01T14:20:00+00:00")
        self.assertEqual(result["wallet"]["amount_rtc"], 64.0)
        self.assertEqual(result["provider_confirmed_total"]["amount"], 14.0)
        self.assertEqual(result["wallet_received_total"]["amount"], 14.0)
        self.assertEqual(result["wallet_received_total"]["entry_count"], 3)
        self.assertEqual(result["wallet_received_total"]["transaction_count"], 6)
        self.assertEqual(result["settled_total"]["amount"], 0.0)
        self.assertEqual(result["settlement_scope"], "conversion_exchange_and_fiat_only")
        self.assertFalse(result["realized_revenue_written"])
        realized = root / "data/aro/realized_revenue_ledger.jsonl"
        self.assertEqual(realized.read_text(encoding="utf-8"), "")

    def test_public_history_uniquely_attributes_all_three_bounties(self) -> None:
        evidence = fixture_evidence()
        receipts = evidence["wallet_receipts"]
        self.assertEqual(receipts["prs"][8289]["txids"], ["ba9275756fa973756dcad8ebdbcc4f47"])
        self.assertEqual(receipts["prs"][8295]["txids"], ["85a84808b75788e791e2e921f99de9d1"])
        self.assertEqual(
            set(receipts["issue_254"]["txids"]),
            {
                "39d1193717912e63040f59d54430bec0",
                "ff218948ee74dfc51c4086ac500954d9",
                "2c5ba8fd021ff7e6ef1c0eaad83cbc9e",
                "e68236514c6554b5cdcbc0e066b6d852",
            },
        )
        self.assertEqual(receipts["issue_254"]["amount_received"], 4.0)

    def test_wallet_history_envelope_is_collected_and_hashed(self) -> None:
        fixture = fixture_history()

        def fetcher(url: str) -> dict:
            self.assertEqual(url, MODULE.HISTORY_URL)
            return {
                "ok": fixture["ok"],
                "miner_id": fixture["miner_id"],
                "total": fixture["total"],
                "transactions": fixture["transactions"],
            }

        observed = MODULE.collect_wallet_history(fetcher)
        self.assertEqual(observed["total"], 9)
        self.assertEqual(observed["response_sha256"], fixture["response_sha256"])
        self.assertEqual(observed["documentation_revision"], MODULE.HISTORY_DOCUMENTATION_REVISION)

    def test_public_history_attribution_fails_closed_when_ambiguous(self) -> None:
        history = json.loads(json.dumps(fixture_history()))
        history["transactions"].append(
            {
                "amount": 5.0,
                "epoch": 38851,
                "from": "founder_community",
                "reason": "transfer_in:founder_community:00000000000000000000000000000000",
                "timestamp": 1788104500,
                "tx_hash": "00000000000000000000000000000000",
                "type": "transfer_in",
            }
        )
        with self.assertRaises(MODULE.EvidenceError):
            MODULE.uniquely_attribute_receipts(
                history,
                provider_confirmed_at="2026-08-29T15:38:57Z",
                amount_each=5.0,
                count=1,
            )

    def test_public_history_attribution_fails_closed_when_issue_credit_missing(self) -> None:
        history = json.loads(json.dumps(fixture_history()))
        history["transactions"] = [
            row for row in history["transactions"] if row.get("tx_hash") != "e68236514c6554b5cdcbc0e066b6d852"
        ]
        with self.assertRaises(MODULE.EvidenceError):
            MODULE.uniquely_attribute_receipts(
                history,
                provider_confirmed_at="2026-08-29T20:03:49Z",
                amount_each=1.0,
                count=4,
            )


if __name__ == "__main__":
    unittest.main()
