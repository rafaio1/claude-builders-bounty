#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build_capital_cycle_context.py")
if not MODULE_PATH.exists():
    MODULE_PATH = Path("/usr/local/lib/agentic/build_capital_cycle_context.py")
spec = importlib.util.spec_from_file_location("capital_context", MODULE_PATH)
assert spec and spec.loader
MODULE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MODULE)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def priority_candidate(candidate_id: str, amount: int) -> dict:
    return {
        "source": "opire",
        "candidate_id": candidate_id,
        "stable_id": f"opire:{candidate_id}",
        "title": f"Candidate {candidate_id}",
        "provider": "opire",
        "listing_verified": True,
        "source_fresh": True,
        "provider_verified": True,
        "agent_access": "AGENT_ALLOWED",
        "human_gates": {
            "kyc": False,
            "identity": False,
            "social": False,
            "video": False,
            "real_funds": False,
            "trading": False,
            "manual": False,
        },
        "human_gates_complete": True,
        "asset": "USDC",
        "network": "solana-mainnet",
        "asset_network_exact": True,
        "deadline": "2026-09-20T00:00:00Z",
        "gross_verified": amount,
        "route_id": "usdc_solana_to_wise",
        "route_status": "complete_verified",
        "self_custody_rail_verified": True,
        "explicit_execution_contract": True,
        "expected_wise_net_verified": amount - 10,
        "payment_confidence_lcb_ppm": 900000,
        "net_if_paid_verified": amount - 5,
        "time_to_wise_p90_seconds": 3600,
        "financial_classification": "unrealized_opportunity_not_revenue",
        "funds_moved": False,
        "realized": 0,
        "reason_codes": [],
    }


class CapitalContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "Agentic"
        aro = self.root / "data/aro"
        aro.mkdir(parents=True)
        ledger = {
            "schema_version": "1.0",
            "entries": [
                {
                    "ledger_id": "a",
                    "bounty_key": "github|owner/repo|1",
                    "status": "wallet_received",
                    "repo": "owner/repo",
                    "reward_asset": "RTC",
                    "provider_confirmed_amount": 4,
                    "amount_received": 4,
                    "txid": None,
                    "txids": [
                        "2c5ba8fd021ff7e6ef1c0eaad83cbc9e",
                        "39d1193717912e63040f59d54430bec0",
                        "e68236514c6554b5cdcbc0e066b6d852",
                        "ff218948ee74dfc51c4086ac500954d9",
                    ],
                    "provider_evidence": [{"source_url": "https://github.com/owner/repo/issues/1"}],
                    "blockers": [{"type": "conversion_pending"}],
                },
                {
                    "ledger_id": "b",
                    "bounty_key": "github|owner/repo|2",
                    "status": "submitted",
                    "repo": "owner/repo",
                    "pr_number": 20,
                    "reward_asset": "USD",
                    "expected_amount": 50,
                    "blockers": [{"type": "blocked_missing_verified_payment_rail"}],
                },
                {
                    "ledger_id": "c",
                    "bounty_key": "github|owner/repo|3",
                    "status": "blocked_no_payment_rail",
                    "repo": "owner/repo",
                    "blockers": [{"type": "blocked_missing_receive_rail"}],
                },
            ],
        }
        (aro / "bounty_receive_ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
        write_jsonl(aro / "realized_revenue_ledger.jsonl", [])
        write_jsonl(
            aro / "proposals/email_bounty_signals.jsonl",
            [
                {
                    "schema_version": 1,
                    "source": "gmail_read_only",
                    "verification": "unverified_email_signal",
                    "signal_id": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                    "message_id": "m2",
                    "message_timestamp": "2026-08-29T00:00:00Z",
                    "provider": "github",
                    "repo": "owner/repo",
                    "subject": "Payment body must never leak (PR #20)",
                    "body": "SECRET EMAIL BODY",
                    "collection_candidate": True,
                    "strict_state": "payout_confirmation_candidate",
                    "verification": "unverified_email_signal",
                    "evidence_terms": ["sent", "reward"],
                },
                {
                    "schema_version": 1,
                    "source": "gmail_read_only",
                    "verification": "unverified_email_signal",
                    "signal_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "message_id": "m1",
                    "message_timestamp": "2026-08-28T00:00:00Z",
                    "provider": "github",
                    "repo": "owner/repo",
                    "subject": "Accepted work (Issue #1)",
                    "snippet": "SECRET SNIPPET",
                    "collection_candidate": True,
                    "strict_state": "acceptance_candidate",
                    "verification": "unverified_email_signal",
                    "evidence_terms": ["accepted", "bounty"],
                },
                {
                    "signal_id": "tail-false",
                    "message_id": "m3",
                    "subject": "Routine CI mail",
                    "collection_candidate": False,
                },
            ],
        )
        write_jsonl(
            aro / "inbox/user_commands.jsonl",
            [
                {
                    "correlation_id": "cmd-1",
                    "timestamp": "2026-09-01T00:00:00Z",
                    "sender_username": "rafaio1",
                    "processed": False,
                    "text": "inspect token=SHOULD_NOT_LEAK",
                },
                {"correlation_id": "cmd-2", "processed": True, "text": "done"},
            ],
        )
        rustchain = {
            "status": "verified_public_evidence",
            "observed_at": "2026-09-01T00:00:00Z",
            "wallet": {"miner_id": "RTC1", "amount_rtc": 64, "source_url": "https://rustchain.org/wallet/balance?miner_id=RTC1"},
            "provider_confirmed_total": {"asset": "RTC", "amount": 4, "entry_count": 1},
            "wallet_received_total": {"asset": "RTC", "amount": 4, "entry_count": 1},
            "settled_total": {"asset": "RTC", "amount": 0, "entry_count": 0},
            "balance_not_mapped_to_these_records_rtc": 50,
            "bybit_route_status": "unsupported_unverified",
            "wise_route_status": "blocked_no_reconciled_conversion",
            "direct_transfer_performed": False,
            "canonical_bounty_keys": ["github|owner/repo|1"],
            "ledger_sha256": MODULE.sha256_bytes((aro / "bounty_receive_ledger.json").read_bytes()),
            "evidence_urls": ["https://github.com/owner/repo/issues/1"],
        }
        (aro / "rustchain_reconciliation.json").write_text(json.dumps(rustchain), encoding="utf-8")
        state = self.root / "state"
        state.mkdir()
        (state / "financial_ledger_semantic_validation.json").write_text(
            json.dumps({"status": "valid", "checked_at": "2026-09-01T00:00:00Z", "error_count": 0}),
            encoding="utf-8",
        )
        payout_routes = {
            "schema_version": "1.0",
            "generated_at": "2026-09-01T00:00:00Z",
            "status": "ok",
            "policy": {
                "human_action": "none",
                "ranking_dimensions": ["expected_wise_net", "payment_and_rail_confidence", "cost", "risk", "time_to_wise"],
                "realized_only_after": "wise_inbound_transaction_causally_reconciled",
            },
            "summary": {
                "route_count": 1,
                "complete_verified": 0,
                "route_pending": 1,
                "candidate_count": 1,
                "candidates_with_verified_wise_net": 0,
                "funds_moved": False,
            },
            "routes": [
                {
                    "route_id": "rtc_native_to_wise",
                    "asset": "RTC",
                    "network": "rustchain-native",
                    "status": "route_pending",
                    "route_complete_verified": False,
                    "execution_enabled": False,
                    "expected_wise_net": None,
                    "mapped_wallet_received_amount": 4,
                    "receive_ready": True,
                    "reason_codes": ["route_not_end_to_end_verified"],
                }
            ],
            "priority_candidates": [
                {
                    "candidate_id": "st-1",
                    "source": "superteam",
                    "title": "Large public bounty",
                    "asset": "USDC",
                    "network": "unknown_until_provider_contract",
                    "gross_listed_amount": 2000,
                    "expected_wise_net": None,
                    "route_status": "route_pending",
                    "autonomy_qualified": False,
                    "reason_codes": ["wise_net_not_executable"],
                    "source_urls": ["https://superteam.fun/api/listings/details/large-public-bounty"],
                }
            ],
        }
        (state / "payout_route_map.json").write_text(json.dumps(payout_routes), encoding="utf-8")
        scout = {
            "schema_version": "1.0",
            "generated_at": "2026-09-01T00:00:00Z",
            "status": "ok",
            "policy": {"public_data_only": True, "read_only": True},
            "summary": {"list_filter_candidate_count": 1, "autonomy_qualified_count": 0},
            "candidates": [
                {
                    "id": "st-1",
                    "rank": 1,
                    "title": "Large public bounty",
                    "deadline": "2026-09-17T20:59:59Z",
                    "reward": {
                        "amount": 2000,
                        "token": "USDC",
                        "classification": "UNREALIZED_UNAUDITED_MAXIMUM_INDIVIDUAL_FACE_VALUE",
                        "amount_basis": "MAXIMUM_INDIVIDUAL_REWARD",
                        "total_pool_amount": 10000,
                        "total_pool_classification": "UNREALIZED_UNAUDITED_POOL_FACE_VALUE",
                    },
                    "autonomy_qualified": False,
                    "autonomy_reason_codes": ["AUTONOMY_DEFAULT_DENY", "MANUAL_REVIEW_REQUIRED"],
                    "source_urls": {
                        "detail": "https://superteam.fun/api/listings/details/large-public-bounty"
                    },
                }
            ],
        }
        (state / "superteam_usdc_scout.json").write_text(json.dumps(scout), encoding="utf-8")
        self.health = lambda: {"services": {"capital": {"active": "active"}}, "timers": {}}

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_priority_state(
        self,
        *,
        generated_at: str,
        action: list[dict],
        research: list[dict],
        monitor: list[dict],
    ) -> None:
        rows = action + research + monitor
        payload = {
            "schema_version": "1.0",
            "generated_at": generated_at,
            "status": "ok",
            "policy": {
                "human_gate_disposition": "monitor_only",
                "gross_is_revenue": False,
                "settlement_evidence_consumed": False,
                "execution_performed": False,
            },
            "action_queue": action,
            "research_queue": research,
            "monitor_only": monitor,
            "summary": {
                "candidate_count": len(rows),
                "action_count": len(action),
                "research_count": len(research),
                "monitor_only_count": len(monitor),
            },
            "funds_moved": False,
            "realized": 0,
        }
        payload["result_sha256"] = MODULE.sha256_bytes(MODULE.canonical_bytes(payload))
        path = self.root / "state/bounty_priority_queue.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_compact_context_counts_candidates_before_false_tail_and_redacts(self) -> None:
        now = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)
        first = MODULE.build_context(self.root, now=now, health_provider=self.health)
        second = MODULE.build_context(self.root, now=now, health_provider=self.health)
        self.assertEqual(first, second)
        self.assertEqual(first["email_collection_candidates"]["count"], 2)
        self.assertEqual(
            [row["signal_id"] for row in first["email_collection_candidates"]["items"]],
            ["aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"],
        )
        self.assertEqual(first["email_collection_candidates"]["items"][0]["target_url"], "https://github.com/owner/repo/issues/1")
        self.assertEqual(first["email_collection_candidates"]["items"][1]["target_url"], "https://github.com/owner/repo/pull/20")
        self.assertEqual(first["proposal_guard"]["existing_key_count"], 3)
        self.assertEqual(
            first["proposal_guard"]["existing_bounty_keys"],
            ["github|owner/repo|1", "github|owner/repo|2", "github|owner/repo|3"],
        )
        self.assertEqual(first["proposal_guard"]["generic_helper_allowed_statuses"], ["candidate", "submitted"])
        self.assertEqual(first["proposal_guard"]["rustchain_monitor_only_keys"], ["github|owner/repo|1"])
        self.assertEqual(first["ledger"]["status_counts"]["wallet_received"], 1)
        self.assertIsNone(first["ledger"]["wallet_received"][0]["txid"])
        self.assertEqual(len(first["ledger"]["wallet_received"][0]["txids"]), 4)
        self.assertEqual(first["rustchain"]["wallet_received_total"]["amount"], 4)
        encoded = MODULE.canonical_bytes(first)
        self.assertLess(len(encoded), MODULE.MAX_CONTEXT_BYTES)
        self.assertNotIn(b"SECRET EMAIL BODY", encoded)
        self.assertNotIn(b"SECRET SNIPPET", encoded)
        self.assertNotIn(b"SHOULD_NOT_LEAK", encoded)
        self.assertIn(b"token=[REDACTED]", encoded)
        self.assertEqual(MODULE.forbidden_key_paths(first), [])

    def test_priority_queue_exposes_top_rows_without_promoting_monitor_to_revenue(self) -> None:
        action = priority_candidate("action-1", 4000)
        research = priority_candidate("research-1", 3000)
        research["route_status"] = "route_pending"
        research["explicit_execution_contract"] = False
        research["reason_codes"] = ["route_pending"]
        monitor = priority_candidate("monitor-1", 5000)
        monitor["agent_access"] = "HUMAN_REQUIRED"
        monitor["human_gates"]["identity"] = True
        monitor["reason_codes"] = ["human_gate_identity"]
        self.write_priority_state(
            generated_at="2026-09-01T00:00:00Z",
            action=[action],
            research=[research],
            monitor=[monitor],
        )

        context = MODULE.build_context(
            self.root,
            now=datetime(2026, 9, 1, 0, 5, tzinfo=timezone.utc),
            health_provider=self.health,
        )
        priority = context["bounty_priority_queue"]
        self.assertEqual("ok", priority["status"])
        self.assertTrue(priority["fresh"])
        self.assertEqual("action-1", priority["action_queue"][0]["candidate_id"])
        self.assertTrue(priority["action_queue"][0]["actionable"])
        self.assertEqual("research-1", priority["research_queue"][0]["candidate_id"])
        self.assertFalse(priority["research_queue"][0]["actionable"])
        self.assertEqual("monitor-1", priority["monitor_only"][0]["candidate_id"])
        self.assertFalse(priority["monitor_only"][0]["actionable"])
        self.assertFalse(priority["monitor_only"][0]["is_revenue"])
        self.assertFalse(priority["monitor_only_is_actionable"])
        self.assertEqual(1, priority["summary"]["effective_action_count"])

    def test_stale_priority_queue_suppresses_action_but_keeps_informational_tops(self) -> None:
        action = priority_candidate("stale-action", 4000)
        research = priority_candidate("research-1", 3000)
        monitor = priority_candidate("monitor-1", 5000)
        self.write_priority_state(
            generated_at="2026-09-01T00:00:00Z",
            action=[action],
            research=[research],
            monitor=[monitor],
        )

        context = MODULE.build_context(
            self.root,
            now=datetime(2026, 9, 1, 1, 0, tzinfo=timezone.utc),
            health_provider=self.health,
        )
        priority = context["bounty_priority_queue"]
        self.assertEqual("stale_fail_closed", priority["status"])
        self.assertFalse(priority["fresh"])
        self.assertEqual([], priority["action_queue"])
        self.assertEqual(1, priority["summary"]["suppressed_action_count"])
        self.assertEqual("research-1", priority["research_queue"][0]["candidate_id"])
        self.assertEqual("monitor-1", priority["monitor_only"][0]["candidate_id"])

    def test_tampered_priority_queue_hash_suppresses_action(self) -> None:
        action = priority_candidate("tampered-action", 4000)
        self.write_priority_state(
            generated_at="2026-09-01T00:00:00Z",
            action=[action],
            research=[],
            monitor=[],
        )
        path = self.root / "state/bounty_priority_queue.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["action_queue"][0]["gross_verified"] = 999999
        path.write_text(json.dumps(payload), encoding="utf-8")

        context = MODULE.build_context(
            self.root,
            now=datetime(2026, 9, 1, 0, 5, tzinfo=timezone.utc),
            health_provider=self.health,
        )

        priority = context["bounty_priority_queue"]
        self.assertEqual("invalid_fail_closed", priority["status"])
        self.assertEqual([], priority["action_queue"])
        self.assertIn("priority_result_hash_mismatch", priority["reason_codes"])

    def test_invalid_action_contract_is_suppressed_fail_closed(self) -> None:
        action = priority_candidate("unsafe-action", 4000)
        action["human_gates"]["identity"] = True
        self.write_priority_state(
            generated_at="2026-09-01T00:00:00Z",
            action=[action],
            research=[],
            monitor=[],
        )

        context = MODULE.build_context(
            self.root,
            now=datetime(2026, 9, 1, 0, 5, tzinfo=timezone.utc),
            health_provider=self.health,
        )
        priority = context["bounty_priority_queue"]
        self.assertEqual("invalid_fail_closed", priority["status"])
        self.assertIn("action_contract_invalid", priority["reason_codes"])
        self.assertEqual([], priority["action_queue"])
        self.assertEqual(1, priority["summary"]["suppressed_action_count"])

    def test_priority_poll_timestamp_does_not_churn_material_state(self) -> None:
        monitor = priority_candidate("monitor-1", 5000)
        self.write_priority_state(
            generated_at="2026-09-01T00:00:00Z",
            action=[],
            research=[],
            monitor=[monitor],
        )
        first = MODULE.build_context(
            self.root,
            now=datetime(2026, 9, 1, 0, 5, tzinfo=timezone.utc),
            health_provider=self.health,
        )
        self.write_priority_state(
            generated_at="2026-09-01T00:10:00Z",
            action=[],
            research=[],
            monitor=[monitor],
        )
        second = MODULE.build_context(
            self.root,
            now=datetime(2026, 9, 1, 0, 15, tzinfo=timezone.utc),
            health_provider=self.health,
        )
        self.assertEqual(first["material_state_id"], second["material_state_id"])
        self.assertNotEqual(first["context_id"], second["context_id"])

    def test_missing_priority_queue_is_backward_compatible_and_fail_closed(self) -> None:
        context = MODULE.build_context(self.root, health_provider=self.health)
        priority = context["bounty_priority_queue"]
        self.assertEqual("unavailable", priority["status"])
        self.assertEqual([], priority["action_queue"])
        self.assertEqual(0, priority["summary"]["effective_action_count"])

    def test_route_and_scout_values_remain_non_financial_and_zero_human(self) -> None:
        context = MODULE.build_context(self.root, health_provider=self.health)
        route = context["payout_routes"]["routes"][0]
        candidate = context["large_bounty_candidates"]["items"][0]
        self.assertEqual("route_pending", route["status"])
        self.assertFalse(route["execution_enabled"])
        self.assertFalse(route["is_revenue"])
        self.assertFalse(route["is_settlement"])
        self.assertIsNone(route["expected_wise_net_verified"])
        self.assertEqual(2000, candidate["listed_face_value_unrealized"])
        self.assertIsNone(candidate["expected_wise_net_verified"])
        self.assertFalse(candidate["autonomy_qualified"])
        self.assertFalse(candidate["is_revenue"])
        self.assertFalse(candidate["is_settlement"])
        self.assertFalse(context["payout_routes"]["human_action_required"])
        self.assertFalse(context["large_bounty_candidates"]["human_action_required"])
        self.assertIn("agentic-payout-route-planner.timer", MODULE.TIMER_UNITS)
        self.assertIn("agentic-superteam-usdc-scout.timer", MODULE.TIMER_UNITS)
        self.assertIn("agentic-superteam-large-bounty-scout.timer", MODULE.TIMER_UNITS)
        self.assertIn("agentic-wallet-recovery-notifier.timer", MODULE.TIMER_UNITS)
        self.assertEqual(
            "unavailable",
            context["large_bounty_candidates"]["sources"][1]["status"],
        )

    def test_optional_large_scout_keeps_usdg_distinct_and_unrealized(self) -> None:
        primary_path = self.root / "state/superteam_usdc_scout.json"
        large = json.loads(primary_path.read_text(encoding="utf-8"))
        large["candidates"][0]["id"] = "large-usdg-1"
        large["candidates"][0]["title"] = "Large USDG bounty"
        large["candidates"][0]["reward"]["amount"] = 10000
        large["candidates"][0]["reward"]["token"] = "USDG"
        large["candidates"][0]["source_urls"]["detail"] = (
            "https://superteam.fun/api/listings/details/large-usdg-bounty"
        )
        path = self.root / "state/superteam_large_bounty_scout.json"
        path.write_text(json.dumps(large), encoding="utf-8")

        context = MODULE.build_context(self.root, health_provider=self.health)
        combined = context["large_bounty_candidates"]
        top = combined["items"][0]
        self.assertEqual(2, combined["candidate_count"])
        self.assertEqual("USDG", top["asset"])
        self.assertTrue(top["asset_exact_no_fiat_equivalence"])
        self.assertEqual(10000, top["listed_face_value_unrealized"])
        self.assertIsNone(top["expected_wise_net_verified"])
        self.assertFalse(top["is_revenue"])
        self.assertFalse(top["is_settlement"])
        self.assertTrue(combined["asset_symbols_are_not_fiat_equivalence"])

    def test_overlapping_scouts_are_deduplicated_and_general_source_wins(self) -> None:
        primary_path = self.root / "state/superteam_usdc_scout.json"
        general = json.loads(primary_path.read_text(encoding="utf-8"))
        general["candidates"][0]["title"] = "General validated duplicate"
        path = self.root / "state/superteam_large_bounty_scout.json"
        path.write_text(json.dumps(general), encoding="utf-8")

        context = MODULE.build_context(self.root, health_provider=self.health)
        combined = context["large_bounty_candidates"]
        self.assertEqual(2, combined["raw_candidate_count"])
        self.assertEqual(1, combined["candidate_count"])
        self.assertEqual(1, combined["overlap_duplicate_count"])
        self.assertEqual("General validated duplicate", combined["items"][0]["title"])
        self.assertEqual(
            "superteam_large_bounty_scout",
            combined["items"][0]["source_state"],
        )
        self.assertEqual(
            [1, 1],
            [row["candidate_count"] for row in combined["sources"]],
        )

    def test_general_scout_timer_health_is_preserved(self) -> None:
        unit = "agentic-superteam-large-bounty-scout.timer"
        context = MODULE.build_context(
            self.root,
            health_provider=lambda: {
                "services": {},
                "timers": {
                    unit: {"active": "active", "sub": "waiting", "result": "success"}
                },
            },
        )
        self.assertEqual(
            {"active": "active", "sub": "waiting", "result": "success"},
            context["health"]["timers"][unit],
        )

    def test_pending_route_cannot_be_execution_enabled(self) -> None:
        path = self.root / "state/payout_route_map.json"
        state = json.loads(path.read_text(encoding="utf-8"))
        state["routes"][0]["execution_enabled"] = True
        path.write_text(json.dumps(state), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ContextError, "route_pending cannot"):
            MODULE.build_context(self.root, health_provider=self.health)

    def test_scout_face_value_must_remain_explicitly_unrealized(self) -> None:
        path = self.root / "state/superteam_usdc_scout.json"
        state = json.loads(path.read_text(encoding="utf-8"))
        state["candidates"][0]["reward"]["classification"] = "revenue"
        path.write_text(json.dumps(state), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ContextError, "not explicitly unrealized"):
            MODULE.build_context(self.root, health_provider=self.health)

    def test_invalid_jsonl_fails_closed(self) -> None:
        path = self.root / "data/aro/proposals/email_bounty_signals.jsonl"
        path.write_text("not-json\n", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ContextError, "invalid JSONL"):
            MODULE.build_context(self.root, health_provider=self.health)

    def test_acceptance_non_financial_disclaimer_is_excluded_and_mismatch_fails_closed(self) -> None:
        path = self.root / "data/aro/proposals/email_bounty_signals.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        acceptance = next(row for row in rows if row.get("strict_state") == "acceptance_candidate")
        acceptance["non_financial_disclaimer"] = True
        acceptance["collection_candidate"] = False
        payout = next(row for row in rows if row.get("strict_state") == "payout_confirmation_candidate")
        payout["non_financial_disclaimer"] = True
        write_jsonl(path, rows)

        context = MODULE.build_context(self.root, health_provider=self.health)
        self.assertEqual(context["email_collection_candidates"]["count"], 1)
        self.assertEqual(
            [row["signal_id"] for row in context["email_collection_candidates"]["items"]],
            ["bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"],
        )

        acceptance["collection_candidate"] = True
        write_jsonl(path, rows)
        with self.assertRaisesRegex(MODULE.ContextError, "email candidate contract mismatch"):
            MODULE.build_context(self.root, health_provider=self.health)

    def test_material_state_ignores_polling_churn_but_context_id_tracks_it(self) -> None:
        first = MODULE.build_context(
            self.root,
            now=datetime(2026, 9, 1, 12, tzinfo=timezone.utc),
            health_provider=lambda: {"services": {"capital": {"active": "active", "pid": 10}}, "timers": {}},
        )

        rustchain_path = self.root / "data/aro/rustchain_reconciliation.json"
        rustchain = json.loads(rustchain_path.read_text(encoding="utf-8"))
        rustchain["observed_at"] = "2026-09-01T13:00:00Z"
        rustchain_path.write_text(json.dumps(rustchain), encoding="utf-8")
        signals_path = self.root / "data/aro/proposals/email_bounty_signals.jsonl"
        with signals_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"signal_id": "poll-only", "collection_candidate": False}) + "\n")
        commands_path = self.root / "data/aro/inbox/user_commands.jsonl"
        with commands_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"correlation_id": "already-done", "processed": True}) + "\n")

        second = MODULE.build_context(
            self.root,
            now=datetime(2026, 9, 1, 13, tzinfo=timezone.utc),
            health_provider=lambda: {"services": {"capital": {"active": "active", "pid": 11}}, "timers": {}},
        )
        self.assertEqual(first["material_state_id"], second["material_state_id"])
        self.assertNotEqual(first["context_id"], second["context_id"])

    def test_duplicate_bounty_key_fails_closed(self) -> None:
        path = self.root / "data/aro/bounty_receive_ledger.json"
        ledger = json.loads(path.read_text(encoding="utf-8"))
        duplicate = dict(ledger["entries"][0])
        duplicate["ledger_id"] = "duplicate-id"
        ledger["entries"].append(duplicate)
        path.write_text(json.dumps(ledger), encoding="utf-8")
        rustchain_path = self.root / "data/aro/rustchain_reconciliation.json"
        rustchain = json.loads(rustchain_path.read_text(encoding="utf-8"))
        rustchain["ledger_sha256"] = MODULE.sha256_bytes(path.read_bytes())
        rustchain_path.write_text(json.dumps(rustchain), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ContextError, "duplicate bounty_key"):
            MODULE.build_context(self.root, health_provider=self.health)


if __name__ == "__main__":
    unittest.main()
