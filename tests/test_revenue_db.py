"""Negative and persistence tests for Revenue Control Plane v2."""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import revenue_db


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def candidate(opportunity_id: str, *, lane: str = "build", source_url: str | None = None):
    suffix = opportunity_id.rsplit("-", 1)[-1]
    return {
        "id": opportunity_id,
        "lane": lane,
        "repo_key": f"owner/repo-{suffix}",
        "title": f"Opportunity {opportunity_id}",
        "source_url": source_url
        or (
            f"https://github.com/owner/repo-{suffix}/issues/{int(suffix) + 1}"
            if suffix.isdigit()
            else "https://github.com/owner/repo/issues/1"
        ),
    }


def official_validation(opportunity_id: str, **overrides):
    suffix = opportunity_id.rsplit("-", 1)[-1]
    values = {
        "platform": "opire",
        "official_reward_id": f"opire-{suffix}",
        "official_evidence_url": f"https://app.opire.dev/rewards/opire-{suffix}",
        "official_evidence_kind": "official_reward",
        "evidence_checked_at": timestamp(),
        "platform_state": "open",
        "linked_state": "open",
        "bounty_amount_usd": 100.0,
        "currency": "USD",
        "claim_path": f"https://app.opire.dev/rewards/opire-{suffix}/claim",
        "payout_method": "stripe",
        "payer_identity": "verified-maintainer",
        "payout_eligible": True,
        "eligibility_verified": True,
        "official_evidence_verified": True,
        "automation_eligible": True,
        "human_action_required": False,
        "feasibility_verified": True,
        "competition_checked": True,
        "active_competitors": 0,
        "estimated_hours": 1.0,
        "payout_probability": 0.90,
    }
    values.update(overrides)
    return values


def seed_lead(db_path: Path, opportunity_id: str, *, lane: str = "build", source_url=None):
    item = candidate(opportunity_id, lane=lane, source_url=source_url)
    revenue_db.create_lead(item, db_path)
    revenue_db.record_repo_health(
        item["repo_key"],
        is_active=True,
        maintainer_active=True,
        health_score=0.9,
        checked_at=timestamp(),
        evidence_url=f"https://github.com/{item['repo_key']}",
        db_path=db_path,
    )
    validation = official_validation(opportunity_id)
    if lane == "receivable":
        validation.update(
            {
                "linked_state": "merged",
                "automation_eligible": True,
                "human_action_required": False,
                "feasibility_verified": False,
                "competition_checked": False,
                "active_competitors": None,
                "estimated_hours": 0.5,
                "payout_probability": 0.95,
            }
        )
    assert revenue_db.record_official_validation(opportunity_id, validation, db_path)
    return item


def verify_seeded(db_path: Path, opportunity_id: str, *, lane: str = "build"):
    item = seed_lead(db_path, opportunity_id, lane=lane)
    valid, reasons = revenue_db.verify_opportunity(opportunity_id, db_path)
    assert valid, reasons
    return item


def test_db_path_is_absolute_and_relative_override_is_rejected(tmp_path):
    assert revenue_db.resolve_db_path().is_absolute()
    with pytest.raises(ValueError):
        revenue_db.resolve_db_path("relative/revenue.db")
    assert revenue_db.resolve_db_path(tmp_path / "revenue.db").is_absolute()


def test_init_is_idempotent_and_persists_round_trip(tmp_path):
    db_path = tmp_path / "revenue.db"
    assert revenue_db.init_db(db_path) == db_path.resolve()
    assert revenue_db.init_db(db_path) == db_path.resolve()
    revenue_db.create_lead(candidate("candidate-1"), db_path)

    reopened = revenue_db.get_opportunity("candidate-1", db_path)

    assert reopened is not None
    assert reopened["status"] == "lead"
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0] == 1


def test_pr_url_is_never_official_bounty_evidence(tmp_path):
    db_path = tmp_path / "revenue.db"
    pr_url = "https://github.com/owner/repo/pull/99"
    seed_lead(db_path, "candidate-pr", source_url=pr_url)
    assert revenue_db.record_official_validation(
        "candidate-pr",
        {
            "official_evidence_url": pr_url,
            "official_evidence_kind": "official_reward",
            "official_evidence_verified": True,
        },
        db_path,
    )

    valid, reasons = revenue_db.verify_opportunity("candidate-pr", db_path)

    assert not valid
    assert "evidence_not_distinct_from_source" in reasons
    assert "build_source_not_github_issue" in reasons


def test_platform_open_but_linked_github_issue_closed_is_rejected(tmp_path):
    db_path = tmp_path / "revenue.db"
    seed_lead(db_path, "candidate-48191")
    assert revenue_db.record_official_validation(
        "candidate-48191", {"platform_state": "open", "linked_state": "closed"}, db_path
    )

    valid, reasons = revenue_db.verify_opportunity("candidate-48191", db_path)

    assert not valid
    assert "linked_issue_not_open" in reasons


def test_inactive_repo_is_rejected(tmp_path):
    db_path = tmp_path / "revenue.db"
    item = seed_lead(db_path, "candidate-2")
    revenue_db.record_repo_health(
        item["repo_key"],
        is_active=False,
        maintainer_active=True,
        health_score=0.9,
        checked_at=timestamp(),
        evidence_url=f"https://github.com/{item['repo_key']}",
        db_path=db_path,
    )

    valid, reasons = revenue_db.verify_opportunity("candidate-2", db_path)

    assert not valid
    assert "repo_inactive" in reasons


def test_human_authored_comment_or_video_requirement_rejects_automation(tmp_path):
    db_path = tmp_path / "revenue.db"
    seed_lead(db_path, "candidate-329")
    assert revenue_db.record_official_validation(
        "candidate-329",
        {"automation_eligible": False, "human_action_required": True},
        db_path,
    )

    valid, reasons = revenue_db.verify_opportunity("candidate-329", db_path)

    assert not valid
    assert "automation_ineligible" in reasons
    assert "human_action_required" in reasons


@pytest.mark.parametrize(
    ("override", "expected_reason"),
    [
        ({"bounty_amount_usd": 50_000_000}, "implausible_bounty_amount"),
        ({"official_reward_id": ""}, "official_reward_id_missing"),
        ({"claim_path": ""}, "claim_path_missing"),
        ({"payout_method": "wise"}, "unsupported_payout_method"),
        ({"payer_identity": ""}, "payer_identity_missing"),
        ({"active_competitors": 2}, "active_or_unknown_competition"),
        ({"feasibility_verified": False}, "feasibility_unverified"),
    ],
)
def test_official_source_hard_gates_fail_closed(tmp_path, override, expected_reason):
    db_path = tmp_path / "revenue.db"
    seed_lead(db_path, "candidate-3")
    assert revenue_db.record_official_validation("candidate-3", override, db_path)

    valid, reasons = revenue_db.verify_opportunity("candidate-3", db_path)

    assert not valid
    assert expected_reason in reasons


def test_unknown_alias_is_not_allowlisted_or_schedulable(tmp_path):
    db_path = tmp_path / "revenue.db"
    verify_seeded(db_path, "candidate-4")

    assert not revenue_db.upsert_identity("unknown-agent", "ghostcli", db_path)
    assert revenue_db.create_work_order("candidate-4", "unknown-agent", db_path) is None


def test_conservative_overhead_and_probability_cap_are_persisted(tmp_path):
    db_path = tmp_path / "revenue.db"
    verify_seeded(db_path, "candidate-5")

    stored = revenue_db.get_opportunity("candidate-5", db_path)

    assert stored is not None
    assert stored["estimated_hours"] == 1.0
    assert stored["conservative_hours"] == 2.5  # 1h * 1.5 + 1h overhead
    assert stored["ev_net_per_hour"] == 20.0  # 100 * capped 0.50 / 2.5h


def test_low_value_high_effort_build_is_rejected(tmp_path):
    db_path = tmp_path / "revenue.db"
    seed_lead(db_path, "candidate-50")
    assert revenue_db.record_official_validation(
        "candidate-50",
        {"bounty_amount_usd": 10.0, "estimated_hours": 7.0},
        db_path,
    )

    valid, reasons = revenue_db.verify_opportunity("candidate-50", db_path)

    assert not valid
    assert "autonomous_effort_exceeds_limit" in reasons
    assert "ev_below_floor" in reasons


def test_viable_bounded_build_clears_profitability_gate(tmp_path):
    db_path = tmp_path / "revenue.db"
    seed_lead(db_path, "candidate-51")
    assert revenue_db.record_official_validation(
        "candidate-51",
        {"bounty_amount_usd": 100.0, "estimated_hours": 2.0},
        db_path,
    )

    valid, reasons = revenue_db.verify_opportunity("candidate-51", db_path)
    stored = revenue_db.get_opportunity("candidate-51", db_path)

    assert valid, reasons
    assert stored["conservative_hours"] == 4.0
    assert stored["ev_net_per_hour"] == 12.5


def test_build_and_receivable_lanes_remain_distinct(tmp_path):
    db_path = tmp_path / "revenue.db"
    verify_seeded(db_path, "candidate-6", lane="build")
    verify_seeded(db_path, "candidate-7", lane="receivable")
    assert revenue_db.upsert_identity("revenue_generator", "ghostcli", db_path)
    assert revenue_db.upsert_identity("contador", "ghostcli", db_path)

    orders = revenue_db.build_work_orders(db_path)

    by_lane = {order["lane"]: order for order in orders}
    assert by_lane["build"]["status"] == "queued"
    assert by_lane["build"]["actor_alias"] == "revenue_generator"
    assert by_lane["receivable"]["status"] == "collection"
    assert by_lane["receivable"]["actor_alias"] == "contador"


def test_database_trigger_enforces_three_active_orders(tmp_path):
    db_path = tmp_path / "revenue.db"
    assert revenue_db.upsert_identity("revenue_generator", "ghostcli", db_path)
    for index in range(4):
        verify_seeded(db_path, f"candidate-{10 + index}")

    created = [
        revenue_db.create_work_order(f"candidate-{10 + index}", "revenue_generator", db_path)
        for index in range(4)
    ]

    assert all(created[:3])
    assert created[3] is None
    assert len(revenue_db.build_work_orders(db_path)) == 3
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0] == 3


def test_work_order_cas_is_idempotent_and_rejects_invalid_transition(tmp_path):
    db_path = tmp_path / "revenue.db"
    verify_seeded(db_path, "candidate-20")
    assert revenue_db.upsert_identity("revenue_generator", "ghostcli", db_path)
    work_order_id = revenue_db.create_work_order(
        "candidate-20", "revenue_generator", db_path
    )
    assert work_order_id

    assert revenue_db.cas_transition_work_order(
        work_order_id, "queued", "in_progress", "revenue_generator", db_path
    )
    assert not revenue_db.cas_transition_work_order(
        work_order_id, "queued", "in_progress", "revenue_generator", db_path
    )
    assert not revenue_db.cas_transition_work_order(
        work_order_id, "in_progress", "published", "revenue_generator", db_path
    )
    assert revenue_db.get_work_order(work_order_id, db_path)["status"] == "in_progress"


def seed_receivable_work_order(db_path: Path, opportunity_id: str = "candidate-21") -> str:
    verify_seeded(db_path, opportunity_id, lane="receivable")
    assert revenue_db.upsert_identity("contador", "ghostcli", db_path)
    work_order_id = revenue_db.create_work_order(opportunity_id, "contador", db_path)
    assert work_order_id
    assert revenue_db.get_work_order(work_order_id, db_path)["status"] == "collection"
    assert revenue_db.get_opportunity(opportunity_id, db_path)["status"] == "payment_pending"
    return work_order_id


def settlement_evidence(transaction_id: str = "po_verified_1"):
    return {
        "collector_alias": "contador",
        "provider_verification_url": (
            f"https://dashboard.stripe.com/payouts/{transaction_id}"
        ),
        "provider_verification_id": transaction_id,
        "provider_verified_at": timestamp(),
    }


def create_verified_settlement(
    db_path: Path,
    work_order_id: str,
    settlement_id: str = "settlement-1",
    transaction_id: str = "po_verified_1",
) -> bool:
    return revenue_db.create_settlement(
        settlement_id,
        work_order_id,
        "stripe",
        transaction_id,
        "USD",
        100,
        3,
        97,
        db_path,
        **settlement_evidence(transaction_id),
    )


def test_fake_settlement_provider_is_rejected(tmp_path):
    db_path = tmp_path / "revenue.db"
    work_order_id = seed_receivable_work_order(db_path)

    assert not revenue_db.create_settlement(
        "settlement-fake",
        work_order_id,
        "fake-provider",
        "fake-1",
        "USD",
        100,
        3,
        97,
        db_path,
        collector_alias="contador",
        provider_verification_url="https://fake.invalid/transfers/fake-1",
        provider_verification_id="fake-1",
        provider_verified_at=timestamp(),
    )


def test_settlement_rejects_build_or_queued_work_order(tmp_path):
    db_path = tmp_path / "revenue.db"
    verify_seeded(db_path, "candidate-22", lane="build")
    assert revenue_db.upsert_identity("revenue_generator", "ghostcli", db_path)
    assert revenue_db.upsert_identity("contador", "ghostcli", db_path)
    build_order = revenue_db.create_work_order(
        "candidate-22", "revenue_generator", db_path
    )
    assert build_order

    assert not revenue_db.create_settlement(
        "settlement-build",
        build_order,
        "stripe",
        "po_build_1",
        "USD",
        100,
        3,
        97,
        db_path,
        **settlement_evidence("po_build_1"),
    )


def test_settlement_requires_fresh_complete_provider_verification(tmp_path):
    db_path = tmp_path / "revenue.db"
    work_order_id = seed_receivable_work_order(db_path)

    assert not revenue_db.create_settlement(
        "settlement-missing",
        work_order_id,
        "stripe",
        "po_missing_1",
        "USD",
        100,
        3,
        97,
        db_path,
        collector_alias="contador",
    )
    stale = settlement_evidence("po_stale_1")
    stale["provider_verified_at"] = "2020-01-01T00:00:00+00:00"
    assert not revenue_db.create_settlement(
        "settlement-stale",
        work_order_id,
        "stripe",
        "po_stale_1",
        "USD",
        100,
        3,
        97,
        db_path,
        **stale,
    )


def test_settlement_rejects_wrong_collector_and_duplicate_transaction(tmp_path):
    db_path = tmp_path / "revenue.db"
    work_order_id = seed_receivable_work_order(db_path)
    assert revenue_db.upsert_identity("collector", "ghostcli", db_path)

    wrong_actor = settlement_evidence("po_wrong_1")
    wrong_actor["collector_alias"] = "collector"
    assert not revenue_db.create_settlement(
        "settlement-wrong",
        work_order_id,
        "stripe",
        "po_wrong_1",
        "USD",
        100,
        3,
        97,
        db_path,
        **wrong_actor,
    )
    assert create_verified_settlement(db_path, work_order_id)
    assert not create_verified_settlement(
        db_path,
        work_order_id,
        settlement_id="settlement-duplicate",
        transaction_id="po_verified_1",
    )
    assert not revenue_db.confirm_settlement("settlement-1", "collector", db_path)


def test_premature_confirmation_fails_and_pending_is_not_revenue(tmp_path):
    db_path = tmp_path / "revenue.db"
    work_order_id = seed_receivable_work_order(db_path)
    assert create_verified_settlement(db_path, work_order_id)
    assert revenue_db.status_snapshot(db_path)["realized_revenue"] == {}
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE work_orders SET status='published' WHERE id=?", (work_order_id,)
        )
        conn.commit()

    assert not revenue_db.confirm_settlement("settlement-1", "contador", db_path)
    assert revenue_db.status_snapshot(db_path)["realized_revenue"] == {}


def test_confirmed_settlement_completes_collection_atomically_and_is_idempotent(tmp_path):
    db_path = tmp_path / "revenue.db"
    work_order_id = seed_receivable_work_order(db_path)
    assert create_verified_settlement(db_path, work_order_id)

    assert revenue_db.confirm_settlement("settlement-1", "contador", db_path)
    assert revenue_db.confirm_settlement("settlement-1", "contador", db_path)
    assert revenue_db.get_work_order(work_order_id, db_path)["status"] == "completed"
    assert revenue_db.get_opportunity("candidate-21", db_path)["status"] == "settled"
    assert revenue_db.status_snapshot(db_path)["realized_revenue"] == {"USD": 97.0}
