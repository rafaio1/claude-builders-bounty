from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import unittest
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

try:
    from high_value_bounty import bounty_priority_queue as queue
except ModuleNotFoundError:
    module_path = Path("/usr/local/lib/agentic/bounty_priority_queue.py")
    spec = importlib.util.spec_from_file_location("bounty_priority_queue", module_path)
    if spec is None or spec.loader is None:
        raise
    queue = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(queue)


UTC = timezone.utc
NOW = datetime(2026, 9, 1, 20, 0, 0, tzinfo=UTC)
FRESH = "2026-09-01T19:30:00Z"
STALE = "2026-09-01T12:00:00Z"
DEADLINE = "2026-09-10T00:00:00Z"


def empty_source(name: str, *, generated_at: str = FRESH) -> dict:
    return {
        "schema_version": "1.0",
        "scout": name,
        "generated_at": generated_at,
        "status": "ok",
        "candidates": [],
    }


def human_gates(**overrides: bool) -> dict[str, bool]:
    result = {
        "kyc": False,
        "identity": False,
        "social": False,
        "video": False,
        "real_funds": False,
        "trading": False,
        "manual": False,
    }
    result.update(overrides)
    return result


def candidate(
    candidate_id: str,
    *,
    amount: int = 1_000,
    asset: str = "USDC",
    network: str = "solana-mainnet",
    expected_wise_net: int = 900,
    confidence_ppm: int = 800_000,
    net_if_paid: int = 950,
    time_p90: int = 86_400,
    deadline: str = DEADLINE,
    gates: dict[str, bool] | None = None,
    agent_access: str = "AGENT_ALLOWED",
) -> dict:
    return {
        "id": candidate_id,
        "title": f"Bounty {candidate_id}",
        "status": "OPEN",
        "verified_listing": True,
        "provider_verified": True,
        "agent_access": agent_access,
        "human_gates": human_gates() if gates is None else gates,
        "reward": {"amount": amount, "token": asset},
        "network": network,
        "deadline": deadline,
        "execution_contract": {
            "explicit": True,
            "autonomous": True,
            "human_action_required": False,
        },
        "economics": {
            "expected_wise_net_verified": expected_wise_net,
            "payment_confidence_lcb_ppm": confidence_ppm,
            "net_if_paid_verified": net_if_paid,
            "time_to_wise_p90_seconds": time_p90,
        },
    }


def route_map(*, generated_at: str = FRESH) -> dict:
    return {
        "schema_version": "1.0",
        "generated_at": generated_at,
        "status": "ok",
        "routes": [
            {
                "route_id": "usdc_solana_to_wise",
                "asset": "USDC",
                "network": "solana-mainnet",
                "role": "client_receive_self_custody",
                "receive_ready": True,
                "status": "complete_verified",
                "route_complete_verified": True,
                "execution_enabled": True,
                "reason_codes": [],
            },
            {
                "route_id": "rtc_native_to_wise",
                "asset": "RTC",
                "network": "rustchain-native",
                "role": "client_receive_self_custody",
                "receive_ready": True,
                "status": "route_pending",
                "route_complete_verified": False,
                "execution_enabled": False,
                "reason_codes": ["conversion_rail_unverified"],
            },
        ],
        "priority_candidates": [],
    }


def build(
    *,
    superteam: dict | None = None,
    routes: dict | None = None,
    algora: dict | None = None,
    opire: dict | None = None,
) -> dict:
    return queue.build_priority_queue(
        superteam or empty_source("superteam_large_bounty"),
        routes or route_map(),
        algora or empty_source("algora"),
        opire or empty_source("opire"),
        now=NOW,
    )


class BountyPriorityQueueTests(unittest.TestCase):
    def test_default_paths_match_live_qualifier_receipts(self) -> None:
        self.assertEqual(queue.DEFAULT_ALGORA, Path("/Agentic/state/algora_bounty_qualifications.json"))
        self.assertEqual(queue.DEFAULT_OPIRE, Path("/Agentic/state/opire_bounty_qualifications.json"))

    def test_live_qualifier_shape_is_fresh_but_human_workflow_is_monitor_only(self) -> None:
        algora = {
            "schema_version": "1.0",
            "generated_at": FRESH,
            "source": {"platform": "algora"},
            "qualification_count": 1,
            "qualified_count": 0,
            "qualified_candidates": [],
            "qualifications": [
                {
                    "candidate_key": "algora-high",
                    "decision": "rejected",
                    "title": "Official Algora reward",
                    "url": "https://github.com/example/repo/issues/1",
                    "verified_at": FRESH,
                    "financial_truth": {"face_value_usd": 5_000},
                    "gates": {
                        "official_algora_active_bounty": True,
                        "canonical_algora_open_board": True,
                        "payment_authority_proven": True,
                        "issue_open_unassigned": True,
                    },
                    "quality": {"demo_video_required_by_algora": True},
                    "rejection_reasons": ["competition_present"],
                }
            ],
            "workflow_contract": {
                "application_allowed": False,
                "implementation_allowed": False,
                "requires_before_application": ["user_algora_github_oauth_verified"],
            },
        }

        result = build(algora=algora)

        self.assertEqual(result["source_health"]["algora"]["status"], "ok")
        self.assertTrue(result["source_health"]["algora"]["fresh"])
        self.assertEqual(result["action_queue"], [])
        self.assertEqual(result["research_queue"], [])
        self.assertEqual(result["monitor_only"][0]["candidate_id"], "algora-high")
        self.assertEqual(result["monitor_only"][0]["gross_verified"], 5_000)
        self.assertIn("provider_workflow_human_gate", result["monitor_only"][0]["reason_codes"])
        self.assertIn("qualification_rejected", result["monitor_only"][0]["reason_codes"])

    def test_qualifier_without_valid_manifest_status_fails_closed(self) -> None:
        opire = {
            "schema_version": "1.0",
            "generated_at": FRESH,
            "source": {"platform": "opire"},
            "qualification_count": 2,
            "qualified_count": 0,
            "qualified_candidates": [],
            "qualifications": [],
        }

        result = build(opire=opire)

        self.assertFalse(result["source_health"]["opire"]["fresh"])
        self.assertIn("source_status_not_ready", result["source_health"]["opire"]["reason_codes"])
        self.assertEqual(result["action_queue"], [])

    def test_largest_verified_expected_wise_net_is_first_action(self) -> None:
        source = empty_source("superteam_large_bounty")
        source["candidates"] = [
            candidate("smaller", expected_wise_net=500, confidence_ppm=950_000),
            candidate("larger", expected_wise_net=900, confidence_ppm=700_000),
        ]

        result = build(superteam=source)

        self.assertEqual([row["candidate_id"] for row in result["action_queue"]], ["larger", "smaller"])
        self.assertEqual(result["summary"]["action_count"], 2)

    def test_verified_action_contract_fields_are_preserved_without_authorizing_them(self) -> None:
        source = empty_source("algora")
        row = candidate("claimable")
        row.update(
            {
                "provider": "algora",
                "platform": "github",
                "url": "https://github.com/example/repo/issues/7",
                "action": "claim",
                "claim_command": "/claim",
                "action_contract": {
                    "platform": "github",
                    "kind": "github_issue_comment",
                    "provider": "algora",
                    "target_url": "https://github.com/example/repo/issues/7",
                    "claim_command": "/claim",
                    "verified": True,
                    "autonomous": True,
                    "provider_instruction_sha256": "a" * 64,
                    "secret": "must-not-propagate",
                },
            }
        )
        source["candidates"] = [row]

        result = build(algora=source)

        action = result["action_queue"][0]
        self.assertEqual(action["url"], row["url"])
        self.assertEqual(action["platform"], "github")
        self.assertEqual(action["action"], "claim")
        self.assertEqual(action["claim_command"], "/claim")
        self.assertEqual(action["action_contract"]["provider_instruction_sha256"], "a" * 64)
        self.assertNotIn("secret", action["action_contract"])

    def test_high_face_value_human_only_is_excluded_from_action(self) -> None:
        source = empty_source("superteam_large_bounty")
        source["candidates"] = [
            candidate(
                "huge-human-only",
                amount=10_000_000,
                expected_wise_net=9_000_000,
                gates=human_gates(kyc=True),
                agent_access="HUMAN_ONLY",
            ),
            candidate("autonomous", amount=2_000, expected_wise_net=1_500),
        ]

        result = build(superteam=source)

        self.assertEqual([row["candidate_id"] for row in result["action_queue"]], ["autonomous"])
        self.assertEqual([row["candidate_id"] for row in result["monitor_only"]], ["huge-human-only"])
        self.assertIn("human_gate_kyc", result["monitor_only"][0]["reason_codes"])

    def test_each_explicit_human_gate_is_monitor_only(self) -> None:
        for gate_name in ("kyc", "identity", "social", "video", "real_funds", "trading", "manual"):
            with self.subTest(gate=gate_name):
                source = empty_source("superteam_large_bounty")
                source["candidates"] = [
                    candidate(f"blocked-{gate_name}", gates=human_gates(**{gate_name: True}))
                ]

                result = build(superteam=source)

                self.assertEqual(result["action_queue"], [])
                self.assertEqual(result["research_queue"], [])
                self.assertEqual(result["monitor_only"][0]["candidate_id"], f"blocked-{gate_name}")
                self.assertIn(f"human_gate_{gate_name}", result["monitor_only"][0]["reason_codes"])

    def test_route_pending_without_human_gate_is_research(self) -> None:
        source = empty_source("algora")
        source["candidates"] = [
            candidate(
                "rtc-pending",
                asset="RTC",
                network="rustchain-native",
                amount=14,
                expected_wise_net=3,
                net_if_paid=3,
            )
        ]

        result = build(algora=source)

        self.assertEqual(result["action_queue"], [])
        self.assertEqual([row["candidate_id"] for row in result["research_queue"]], ["rtc-pending"])
        self.assertEqual(result["research_queue"][0]["route_status"], "route_pending")
        self.assertIn("route_pending", result["research_queue"][0]["reason_codes"])

    def test_route_pending_with_operator_gate_is_monitor_only(self) -> None:
        source = empty_source("algora")
        source["candidates"] = [
            candidate("rtc-operator", asset="RTC", network="rustchain-native", amount=14)
        ]
        routes = route_map()
        routes["routes"][1]["reason_codes"] = ["native_bridge_operator_required"]

        result = build(algora=source, routes=routes)

        self.assertEqual(result["action_queue"], [])
        self.assertEqual(result["research_queue"], [])
        self.assertEqual(result["monitor_only"][0]["candidate_id"], "rtc-operator")
        self.assertIn("route_human_gate", result["monitor_only"][0]["reason_codes"])

    def test_stale_listing_source_is_never_actionable(self) -> None:
        source = empty_source("opire", generated_at=STALE)
        source["candidates"] = [candidate("stale-but-attractive", expected_wise_net=50_000)]

        result = build(opire=source)

        self.assertEqual(result["action_queue"], [])
        self.assertEqual([row["candidate_id"] for row in result["research_queue"]], ["stale-but-attractive"])
        self.assertFalse(result["research_queue"][0]["source_fresh"])
        self.assertEqual(result["status"], "degraded_fail_closed")

    def test_action_tie_break_is_stable_by_deadline_then_id(self) -> None:
        source = empty_source("superteam_large_bounty")
        source["candidates"] = [
            candidate("z-last"),
            candidate("b-later", deadline="2026-09-11T00:00:00Z"),
            candidate("a-first"),
        ]

        first = build(superteam=source)
        source["candidates"].reverse()
        second = build(superteam=source)

        expected = ["a-first", "z-last", "b-later"]
        self.assertEqual([row["candidate_id"] for row in first["action_queue"]], expected)
        self.assertEqual([row["candidate_id"] for row in second["action_queue"]], expected)
        self.assertEqual(first["action_queue"], second["action_queue"])

    def test_no_queue_invents_revenue_or_fund_movement(self) -> None:
        superteam = empty_source("superteam_large_bounty")
        superteam["candidates"] = [candidate("action")]
        algora = empty_source("algora")
        algora["candidates"] = [
            candidate("research", asset="RTC", network="rustchain-native", amount=14)
        ]
        opire = empty_source("opire")
        opire["candidates"] = [
            candidate("monitor", amount=100_000, gates=human_gates(video=True), agent_access="HUMAN_ONLY")
        ]

        result = build(superteam=superteam, algora=algora, opire=opire)

        self.assertFalse(result["funds_moved"])
        self.assertEqual(result["realized"], 0)
        self.assertFalse(result["summary"]["funds_moved"])
        self.assertEqual(result["summary"]["realized"], 0)
        for name in ("action_queue", "research_queue", "monitor_only"):
            for row in result[name]:
                self.assertFalse(row["funds_moved"])
                self.assertEqual(row["realized"], 0)
                self.assertEqual(row["financial_classification"], "unrealized_opportunity_not_revenue")
                self.assertNotIn("revenue", row)

    def test_path_runner_records_raw_input_hashes_and_writes_private_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            values = {
                "superteam_large": empty_source("superteam_large_bounty"),
                "payout_route_map": route_map(),
                "algora": empty_source("algora"),
                "opire": empty_source("opire"),
            }
            paths: dict[str, Path] = {}
            raw_by_name: dict[str, bytes] = {}
            for name, value in values.items():
                path = root / f"{name}.json"
                raw = json.dumps(value, indent=2).encode("utf-8")
                path.write_bytes(raw)
                paths[name] = path
                raw_by_name[name] = raw
            output = root / "queue.json"

            result = queue.run_from_paths(
                superteam_large_path=paths["superteam_large"],
                payout_route_map_path=paths["payout_route_map"],
                algora_path=paths["algora"],
                opire_path=paths["opire"],
                output_path=output,
                now=NOW,
            )

            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), result)
            for name, raw in raw_by_name.items():
                self.assertEqual(result["input_hashes"][name], hashlib.sha256(raw).hexdigest())
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)

    def test_missing_inputs_write_empty_degraded_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            output = root / "queue.json"

            result = queue.run_from_paths(
                superteam_large_path=root / "missing-superteam.json",
                payout_route_map_path=root / "missing-routes.json",
                algora_path=root / "missing-algora.json",
                opire_path=root / "missing-opire.json",
                output_path=output,
                now=NOW,
            )

            self.assertEqual(result["status"], "degraded_fail_closed")
            self.assertEqual(result["action_queue"], [])
            self.assertEqual(result["research_queue"], [])
            self.assertEqual(result["monitor_only"], [])
            self.assertTrue(output.exists())
            self.assertTrue(all(value is None for value in result["input_hashes"].values()))


if __name__ == "__main__":
    unittest.main()
