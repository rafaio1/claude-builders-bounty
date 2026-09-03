from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build_capital_supervisor_context.py")
if not MODULE_PATH.exists():
    MODULE_PATH = Path("/usr/local/lib/agentic/build_capital_supervisor_context.py")
SPEC = importlib.util.spec_from_file_location("capital_supervisor_context", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def base_context() -> dict:
    return {
        "context_id": "a" * 32,
        "material_state_id": "b" * 32,
        "generated_at": "2026-09-01T16:20:00+00:00",
        "routing": {"model_alias": "ghostcli-auto[1m]", "base_url": "http://127.0.0.1:8787/v1"},
        "realized_revenue": {"record_count": 0, "total_usd": 0},
        "ledger": {
            "entry_count": 1,
            "status_counts": {"wallet_received": 1},
            "provider_confirmed": [],
            "wallet_received": [
                {
                    "key": "github|org/repo|7",
                    "amount": 4,
                    "asset": "RTC",
                    "status": "wallet_received",
                    "txid": None,
                    "txids": ["2c5ba8fd021ff7e6ef1c0eaad83cbc9e"],
                    "blockers": ["conversion_pending"],
                }
            ],
        },
        "rustchain": {
            "wallet": {"amount_rtc": 64},
            "provider_confirmed_total": {"amount": 14, "asset": "RTC", "entry_count": 3},
            "wallet_received_total": {"amount": 14, "asset": "RTC", "entry_count": 3},
            "settled_total": {"amount": 0, "asset": "RTC", "entry_count": 0},
            "unmapped_balance_rtc": 50,
            "bybit_route": "unsupported_unverified",
            "wise_route": "blocked_no_reconciled_conversion",
            "direct_transfer_performed": False,
        },
        "payout_routes": {
            "status": "ok",
            "summary": {
                "route_count": 1,
                "complete_verified": 0,
                "route_pending": 1,
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
                    "expected_wise_net_verified": None,
                    "mapped_wallet_received_amount": 14,
                    "reason_codes": ["route_not_end_to_end_verified"],
                    "market_quote": {
                        "status": "live_conditional_post_bridge",
                        "observed_at": "2026-09-01T18:37:06Z",
                        "venue": "Raydium_route_api_v2",
                        "input_asset": "wRTC",
                        "input_amount": 14,
                        "intermediate_asset": "SOL",
                        "intermediate_output": 0.036456657,
                        "output_asset": "USDC",
                        "estimated_output": 3.602592,
                        "first_leg_price_impact_pct": 0.77,
                        "slippage_bps": 100,
                        "quote_ok": True,
                        "read_only": True,
                        "expiring": True,
                        "post_bridge_only": True,
                        "native_rtc_to_wrtc_verified": False,
                        "authorizes_execution": False,
                    },
                    "bridge_request": {
                        "status": "watcher_state_missing_pending",
                        "repo": "Scottcjn/Rustchain",
                        "issue_number": 8316,
                        "issue_url": "https://github.com/Scottcjn/Rustchain/issues/8316",
                        "watcher_state_present": False,
                        "target_state_present": False,
                        "trusted_comments_seen": 0,
                        "untrusted_comments_seen": 0,
                        "operator_gate_satisfied": False,
                        "execution_authorized": False,
                        "funds_moved": False,
                    },
                }
            ],
        },
        "large_bounty_candidates": {
            "status": "ok",
            "sources": [
                {"source_state": "superteam_usdc_scout", "status": "ok", "candidate_count": 1},
                {"source_state": "superteam_large_bounty_scout", "status": "ok", "candidate_count": 1},
            ],
            "raw_candidate_count": 2,
            "candidate_count": 1,
            "overlap_duplicate_count": 1,
            "autonomy_qualified_count": 0,
            "verified_expected_wise_net_count": 0,
            "items": [
                {
                    "candidate_id": "st-1",
                    "title": "Large public bounty",
                    "asset": "USDC",
                    "listed_face_value_unrealized": 2000,
                    "expected_wise_net_verified": None,
                    "route_status": "route_pending",
                    "autonomy_qualified": False,
                    "reason_codes": ["MANUAL_REVIEW_REQUIRED"],
                    "source_urls": ["https://superteam.fun/api/listings/details/large-public-bounty"],
                }
            ],
        },
        "email_collection_candidates": {
            "count": 1,
            "items": [
                {
                    "provider": "github",
                    "repo": "org/repo",
                    "target_number": 7,
                    "target_type": "issue",
                    "target_url": "https://github.com/org/repo/issues/7",
                    "strict_state": "payout_confirmation_candidate",
                    "verified": False,
                }
            ],
        },
        "proposal_guard": {"existing_bounty_keys": ["github|org/repo|7"]},
        "telegram_unprocessed": {"count": 0, "items": []},
        "health": {
            "financial_validator": {"status": "valid"},
            "services": {"capital.service": {"active": "active", "sub": "running", "result": "success"}},
            "timers": {
                "audit.timer": {"active": "active", "sub": "waiting", "result": "success"},
                "agentic-superteam-large-bounty-scout.timer": {
                    "active": "active",
                    "sub": "waiting",
                    "result": "success",
                },
            },
        },
    }


class BuildSupervisorContextTests(unittest.TestCase):
    def build(self, payload: dict) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.json"
            source.write_text(json.dumps(payload), encoding="utf-8")
            return MODULE.build(source)

    def test_known_email_target_is_not_actionable(self) -> None:
        result = self.build(base_context())
        self.assertTrue(result["supervision"]["actionable_new_evidence"])
        self.assertIn("wallet_receipt_present", result["supervision"]["actionable_reasons"])
        self.assertEqual(0, result["email_signals"]["new_unmapped_target_count"])
        self.assertFalse(result["supervision"]["human_action_required"])
        self.assertEqual(0, result["financial_truth"]["realized_usd"])
        self.assertEqual(14, result["rustchain"]["wallet_received"]["amount"])

    def test_new_email_target_is_actionable(self) -> None:
        payload = base_context()
        payload["proposal_guard"]["existing_bounty_keys"] = []
        result = self.build(payload)
        self.assertTrue(result["supervision"]["actionable_new_evidence"])
        self.assertIn("new_unmapped_email_target", result["supervision"]["actionable_reasons"])

    def test_runtime_problem_is_actionable(self) -> None:
        payload = base_context()
        payload["health"]["services"]["capital.service"]["active"] = "failed"
        result = self.build(payload)
        self.assertTrue(result["supervision"]["actionable_new_evidence"])
        self.assertIn("runtime_health_problem", result["supervision"]["actionable_reasons"])

    def test_pending_route_and_face_value_are_informational_only(self) -> None:
        result = self.build(base_context())
        route = result["payout_routes"]["routes"][0]
        candidate = result["large_bounties"]["items"][0]
        self.assertNotIn("is_revenue", route)
        self.assertNotIn("is_settlement", route)
        self.assertTrue(route["market_quote"]["quote_ok"])
        self.assertTrue(route["market_quote"]["post_bridge_only"])
        self.assertFalse(route["market_quote"]["native_rtc_to_wrtc_verified"])
        self.assertFalse(route["market_quote"]["authorizes_execution"])
        self.assertEqual("watcher_state_missing_pending", route["bridge_request"]["status"])
        self.assertFalse(route["bridge_request"]["operator_gate_satisfied"])
        self.assertFalse(route["bridge_request"]["execution_authorized"])
        self.assertFalse(route["bridge_request"]["funds_moved"])
        self.assertFalse(result["payout_routes"]["route_pending_is_revenue"])
        self.assertFalse(result["payout_routes"]["route_pending_is_settlement"])
        self.assertEqual(2000, candidate["listed_face_value_unrealized"])
        self.assertTrue(candidate["asset_exact_no_fiat_equivalence"])
        self.assertTrue(result["large_bounties"]["asset_symbols_are_not_fiat_equivalence"])
        self.assertEqual(2, result["large_bounties"]["raw_candidate_count"])
        self.assertEqual(1, result["large_bounties"]["candidate_count"])
        self.assertEqual(1, result["large_bounties"]["overlap_duplicate_count"])
        self.assertEqual(
            "active/waiting/success",
            result["runtime"]["units"]["agentic-superteam-large-bounty-scout.timer"],
        )
        self.assertNotIn("is_revenue", candidate)
        self.assertNotIn("is_settlement", candidate)
        self.assertNotIn("verified_executable_payout_route", result["supervision"]["actionable_reasons"])
        self.assertNotIn(
            "autonomous_large_bounty_with_verified_wise_net",
            result["supervision"]["actionable_reasons"],
        )
        self.assertFalse(result["supervision"]["human_action_required"])

    def test_rtc_evidence_cannot_self_authorize_in_supervisor_context(self) -> None:
        payload = base_context()
        route = payload["payout_routes"]["routes"][0]
        route["market_quote"]["authorizes_execution"] = True
        route["market_quote"]["post_bridge_only"] = False
        route["bridge_request"]["trusted_comments_seen"] = 1
        route["bridge_request"]["operator_gate_satisfied"] = True
        route["bridge_request"]["execution_authorized"] = True
        route["bridge_request"]["funds_moved"] = True
        result = self.build(payload)
        compact = result["payout_routes"]["routes"][0]
        self.assertFalse(compact["market_quote"]["quote_ok"])
        self.assertTrue(compact["market_quote"]["post_bridge_only"])
        self.assertFalse(compact["market_quote"]["authorizes_execution"])
        self.assertFalse(compact["bridge_request"]["operator_gate_satisfied"])
        self.assertFalse(compact["bridge_request"]["execution_authorized"])
        self.assertFalse(compact["bridge_request"]["funds_moved"])
        self.assertNotIn("verified_executable_payout_route", result["supervision"]["actionable_reasons"])

    def test_only_autonomous_verified_wise_net_candidate_is_actionable(self) -> None:
        payload = base_context()
        payload["large_bounty_candidates"]["items"][0]["autonomy_qualified"] = True
        payload["large_bounty_candidates"]["items"][0]["expected_wise_net_verified"] = 1500
        result = self.build(payload)
        self.assertIn(
            "autonomous_large_bounty_with_verified_wise_net",
            result["supervision"]["actionable_reasons"],
        )
        self.assertFalse(result["supervision"]["human_action_required"])

    def test_output_is_bounded_and_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.json"
            output = Path(directory) / "output.json"
            source.write_text(json.dumps(base_context()), encoding="utf-8")
            payload = MODULE.build(source)
            MODULE.atomic_write(output, payload, 8192)
            self.assertLessEqual(output.stat().st_size, 8192)
            self.assertEqual(payload, json.loads(output.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
