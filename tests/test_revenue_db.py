"""Negative and persistence tests for Revenue Control Plane v2."""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import revenue_db
import revenue_evidence
import revenue_settlement_evidence


@pytest.fixture(autouse=True)
def configured_stripe_destination(monkeypatch):
    monkeypatch.setenv("STRIPE_DESTINATION_ACCOUNT_ID", "acct_test")


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
            f"https://github.com/owner/repo-{suffix}/pull/{int(suffix) + 1}"
            if lane == "receivable" and suffix.isdigit()
            else f"https://github.com/owner/repo-{suffix}/issues/{int(suffix) + 1}"
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
        "ownership_assignee": "rafaio1",
        "ownership_evidence_url": f"https://github.com/owner/repo-{suffix}/issues/1",
        "ownership_evidence_kind": "github_assignment",
        "ownership_verified": True,
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
                "pr_author": "rafaio1",
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


def test_third_party_pr_slash_claim_never_proves_ownership(tmp_path):
    db_path = tmp_path / "revenue.db"
    seed_lead(
        db_path,
        "candidate-ownership",
        lane="receivable",
        source_url="https://github.com/owner/repo-ownership/pull/1",
    )
    assert revenue_db.record_official_validation(
        "candidate-ownership",
        {
            "pr_author": "Bakomebandias",
            "ownership_assignee": "rafaio1",
            "ownership_evidence_url": (
                "https://github.com/owner/repo-ownership/pull/1#issuecomment-1"
            ),
            "ownership_evidence_kind": "claim_comment",
            "ownership_verified": True,
        },
        db_path,
    )

    valid, reasons = revenue_db.verify_opportunity("candidate-ownership", db_path)

    assert not valid
    assert "claim_comment_not_ownership" in reasons
    assert "claimant_ownership_unverified" in reasons


def test_third_party_pr_with_explicit_official_assignment_is_owned(tmp_path):
    db_path = tmp_path / "revenue.db"
    seed_lead(
        db_path,
        "candidate-transfer",
        lane="receivable",
        source_url="https://github.com/owner/repo-transfer/pull/1",
    )
    assert revenue_db.record_official_validation(
        "candidate-transfer",
        {
            "pr_author": "Bakomebandias",
            "ownership_assignee": "rafaio1",
            "ownership_evidence_url": "https://github.com/owner/repo-transfer/pull/1",
            "ownership_evidence_kind": "github_assignment",
            "ownership_verified": True,
        },
        db_path,
    )

    valid, reasons = revenue_db.verify_opportunity("candidate-transfer", db_path)

    assert valid, reasons


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


def fake_github_api(repo_key: str, issue_number: int, pr_number: int):
    head_sha = "a" * 40
    state = {
        "pull": {
            "html_url": f"https://github.com/{repo_key}/pull/{pr_number}",
            "node_id": f"PR_{pr_number}",
            "state": "open",
            "draft": False,
            "body": f"Closes #{issue_number}",
            "user": {"login": "rafaio1"},
            "base": {"repo": {"full_name": repo_key}},
            "head": {"sha": head_sha},
            "merged": False,
            "merged_at": None,
            "merged_by": None,
            "merge_commit_sha": None,
        }
    }

    def get(path: str):
        if path.endswith(f"/issues/{issue_number}"):
            return {
                "html_url": f"https://github.com/{repo_key}/issues/{issue_number}",
                "node_id": f"ISSUE_{issue_number}",
                "state": "open",
                "assignees": [{"login": "rafaio1"}],
                "updated_at": "2026-08-28T10:00:00Z",
            }
        if path.endswith("/actions/runs/1"):
            return {
                "id": 1,
                "html_url": f"https://github.com/{repo_key}/actions/runs/1",
                "repository": {"full_name": repo_key},
                "status": "completed",
                "conclusion": "success",
                "head_sha": head_sha,
                "run_attempt": 1,
                "event": "pull_request",
            }
        if path.endswith(f"/pulls/{pr_number}/reviews/77"):
            return {
                "id": 77,
                "state": "APPROVED",
                "user": {"login": "maintainer"},
                "author_association": "MEMBER",
                "commit_id": head_sha,
                "submitted_at": "2026-08-28T10:10:00Z",
            }
        if path.endswith(f"/pulls/{pr_number}"):
            return state["pull"]
        raise AssertionError(f"unexpected API path: {path}")

    return state, get


def test_issue_reference_uses_numeric_boundaries():
    assert revenue_evidence._issue_linked("Closes #1", "owner/repo", 1)
    assert not revenue_evidence._issue_linked("Closes #10", "owner/repo", 1)
    assert not revenue_evidence._issue_linked("Closes #100", "owner/repo", 1)
    assert revenue_evidence._issue_linked(
        "Fixes https://github.com/owner/repo/issues/1",
        "owner/repo",
        1,
    )


def test_work_order_cas_requires_official_receipts_and_waits_for_platform(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "revenue.db"
    verify_seeded(db_path, "candidate-20")
    for alias in ("revenue_generator", "reviewer", "integrator", "contador"):
        assert revenue_db.upsert_identity(alias, "ghostcli", db_path)
    work_order_id = revenue_db.create_work_order(
        "candidate-20", "revenue_generator", db_path
    )
    assert work_order_id

    # A caller cannot bypass the external-evidence checkpoint.
    assert not revenue_db.cas_transition_work_order(
        work_order_id, "queued", "in_progress", "revenue_generator", db_path
    )
    assert revenue_db.get_work_order(work_order_id, db_path)["status"] == "queued"

    state, api_get = fake_github_api("owner/repo-20", 21, 22)
    monkeypatch.setattr(revenue_evidence, "_github_get", api_get)

    claim = revenue_db.verify_and_record_work_order_action(
        work_order_id,
        "claim_confirmed",
        "https://github.com/owner/repo-20/issues/21",
        db_path,
    )
    assert claim["actor_alias"] == "revenue_generator"
    assert revenue_db.cas_transition_work_order(
        work_order_id, "queued", "in_progress", "revenue_generator", db_path
    )
    assert revenue_db.get_opportunity("candidate-20", db_path)["status"] == "implementing"
    assert not revenue_db.cas_transition_work_order(
        work_order_id, "queued", "in_progress", "revenue_generator", db_path
    )
    assert not revenue_db.cas_transition_work_order(
        work_order_id, "in_progress", "published", "revenue_generator", db_path
    )

    revenue_db.verify_and_record_work_order_action(
        work_order_id,
        "tests_passed",
        "https://github.com/owner/repo-20/actions/runs/1",
        db_path,
    )
    assert revenue_db.cas_transition_work_order(
        work_order_id, "in_progress", "under_review", "revenue_generator", db_path
    )
    revenue_db.verify_and_record_work_order_action(
        work_order_id,
        "pr_published",
        "https://github.com/owner/repo-20/pull/22",
        db_path,
    )
    assert revenue_db.cas_transition_work_order(
        work_order_id, "under_review", "integration_ready", "integrator", db_path
    )
    assert revenue_db.get_opportunity("candidate-20", db_path)["status"] == "submitted"
    revenue_db.verify_and_record_work_order_action(
        work_order_id,
        "review_approved",
        "https://github.com/owner/repo-20/pull/22#pullrequestreview-77",
        db_path,
    )
    assert revenue_db.cas_transition_work_order(
        work_order_id, "integration_ready", "published", "reviewer", db_path
    )
    assert revenue_db.get_opportunity("candidate-20", db_path)["status"] == "reviewed"
    state["pull"].update(
        {
            "state": "closed",
            "merged": True,
            "merged_at": "2026-08-28T10:20:00Z",
            "merged_by": {"login": "maintainer"},
            "merge_commit_sha": "b" * 40,
        }
    )
    revenue_db.verify_and_record_work_order_action(
        work_order_id,
        "delivery_accepted",
        "https://github.com/owner/repo-20/pull/22",
        db_path,
    )
    assert revenue_db.cas_transition_work_order(
        work_order_id, "published", "completed", "contador", db_path
    )
    assert revenue_db.get_work_order(work_order_id, db_path)["status"] == "completed"
    assert revenue_db.get_opportunity("candidate-20", db_path)["status"] == "accepted"
    with revenue_db.connect(db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM opportunities WHERE lane='receivable'"
        ).fetchone()[0] == 0
        event = conn.execute(
            """SELECT event_type FROM events
               WHERE entity_id='candidate-20'
               ORDER BY id DESC LIMIT 1"""
        ).fetchone()
        assert event["event_type"] == "platform_revalidation_required"


def test_official_action_receipt_is_idempotent_and_cannot_be_reused(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "revenue.db"
    verify_seeded(db_path, "candidate-22")
    assert revenue_db.upsert_identity("revenue_generator", "ghostcli", db_path)
    work_order_id = revenue_db.create_work_order(
        "candidate-22", "revenue_generator", db_path
    )
    _, api_get = fake_github_api("owner/repo-22", 23, 24)
    monkeypatch.setattr(revenue_evidence, "_github_get", api_get)
    first = revenue_db.verify_and_record_work_order_action(
        work_order_id,
        "claim_confirmed",
        "https://github.com/owner/repo-22/issues/23",
        db_path,
    )
    replay = revenue_db.verify_and_record_work_order_action(
        work_order_id,
        "claim_confirmed",
        "https://github.com/owner/repo-22/issues/23",
        db_path,
    )
    assert first["created"] is True
    assert replay["created"] is False
    assert first["payload_sha256"] == replay["payload_sha256"]
    assert revenue_db.cas_transition_work_order(
        work_order_id, "queued", "in_progress", "revenue_generator", db_path
    )
    stored = revenue_db.get_work_order_action(first["idempotency_key"], db_path)
    assert stored["consumed_at"] is not None
    assert revenue_db.get_work_order(work_order_id, db_path)["version"] == 1
    with pytest.raises(ValueError, match="current work-order status"):
        revenue_db.verify_and_record_work_order_action(
            work_order_id,
            "claim_confirmed",
            "https://github.com/owner/repo-22/issues/23",
            db_path,
        )


def test_review_from_unprivileged_external_account_is_rejected(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "revenue.db"
    verify_seeded(db_path, "candidate-25")
    for alias in ("revenue_generator", "reviewer", "integrator", "contador"):
        assert revenue_db.upsert_identity(alias, "ghostcli", db_path)
    work_order_id = revenue_db.create_work_order(
        "candidate-25", "revenue_generator", db_path
    )
    _, base_get = fake_github_api("owner/repo-25", 26, 27)

    def api_get(path: str):
        response = base_get(path)
        if path.endswith("/pulls/27/reviews/77"):
            response = dict(response)
            response["author_association"] = "CONTRIBUTOR"
        return response

    monkeypatch.setattr(revenue_evidence, "_github_get", api_get)
    for action, url, expected, new, actor in (
        (
            "claim_confirmed",
            "https://github.com/owner/repo-25/issues/26",
            "queued",
            "in_progress",
            "revenue_generator",
        ),
        (
            "tests_passed",
            "https://github.com/owner/repo-25/actions/runs/1",
            "in_progress",
            "under_review",
            "revenue_generator",
        ),
        (
            "pr_published",
            "https://github.com/owner/repo-25/pull/27",
            "under_review",
            "integration_ready",
            "integrator",
        ),
    ):
        revenue_db.verify_and_record_work_order_action(
            work_order_id, action, url, db_path
        )
        assert revenue_db.cas_transition_work_order(
            work_order_id, expected, new, actor, db_path
        )
    with pytest.raises(ValueError, match="authorized maintainer"):
        revenue_db.verify_and_record_work_order_action(
            work_order_id,
            "review_approved",
            "https://github.com/owner/repo-25/pull/27#pullrequestreview-77",
            db_path,
        )


def test_official_action_rejects_wrong_repo_and_raw_receipt_api_is_absent(tmp_path):
    db_path = tmp_path / "revenue.db"
    verify_seeded(db_path, "candidate-23")
    assert revenue_db.upsert_identity("revenue_generator", "ghostcli", db_path)
    work_order_id = revenue_db.create_work_order(
        "candidate-23", "revenue_generator", db_path
    )

    assert not hasattr(revenue_db, "record_work_order_action")
    with pytest.raises(ValueError, match="different repository"):
        revenue_db.verify_and_record_work_order_action(
            work_order_id,
            "claim_confirmed",
            "https://github.com/attacker/other/issues/1",
            db_path,
        )


def test_typed_evidence_rejects_generic_url_and_stale_receipt(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "revenue.db"
    verify_seeded(db_path, "candidate-24")
    assert revenue_db.upsert_identity("revenue_generator", "ghostcli", db_path)
    work_order_id = revenue_db.create_work_order(
        "candidate-24", "revenue_generator", db_path
    )

    _, api_get = fake_github_api("owner/repo-24", 25, 26)
    monkeypatch.setattr(revenue_evidence, "_github_get", api_get)
    claim = revenue_db.verify_and_record_work_order_action(
        work_order_id,
        "claim_confirmed",
        "https://github.com/owner/repo-24/issues/25",
        db_path,
    )
    with revenue_db.connect(db_path) as conn:
        conn.execute(
            "UPDATE work_order_actions SET observed_at=? WHERE idempotency_key=?",
            (
                (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                claim["idempotency_key"],
            ),
        )
    assert not revenue_db.cas_transition_work_order(
        work_order_id, "queued", "in_progress", "revenue_generator", db_path
    )

    revenue_db.verify_and_record_work_order_action(
        work_order_id,
        "claim_confirmed",
        "https://github.com/owner/repo-24/issues/25",
        db_path,
    )
    assert revenue_db.cas_transition_work_order(
        work_order_id, "queued", "in_progress", "revenue_generator", db_path
    )
    with pytest.raises(ValueError, match="Actions run URL"):
        revenue_db.verify_and_record_work_order_action(
            work_order_id,
            "tests_passed",
            "https://github.com/owner/repo-24",
            db_path,
        )


def test_partial_action_schema_aborts_instead_of_silent_if_not_exists(tmp_path):
    db_path = tmp_path / "partial.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE work_order_actions (idempotency_key TEXT PRIMARY KEY)"
        )
    with pytest.raises(RuntimeError, match="explicit migration required"):
        revenue_db.init_db(db_path)


def seed_receivable_work_order(db_path: Path, opportunity_id: str = "candidate-21") -> str:
    verify_seeded(db_path, opportunity_id, lane="receivable")
    assert revenue_db.upsert_identity("contador", "ghostcli", db_path)
    work_order_id = revenue_db.create_work_order(opportunity_id, "contador", db_path)
    assert work_order_id
    assert revenue_db.get_work_order(work_order_id, db_path)["status"] == "collection"
    assert revenue_db.get_opportunity(opportunity_id, db_path)["status"] == "payment_pending"
    return work_order_id


def install_verified_stripe_response(
    work_order_id: str,
    transaction_id: str = "tr_verified_1",
    *,
    destination: str = "acct_test",
    destination_status: str = "available",
    reversed_transfer: bool = False,
) -> None:
    revenue_settlement_evidence._stripe_get = lambda transfer_id: {
        "id": transfer_id,
        "object": "transfer",
        "livemode": True,
        "amount": 10000,
        "currency": "usd",
        "created": int(datetime.now(timezone.utc).timestamp()) - 60,
        "destination": destination,
        "destination_payment": "py_test",
        "balance_transaction": "txn_platform",
        "reversed": reversed_transfer,
        "amount_reversed": 10000 if reversed_transfer else 0,
        "metadata": {
            "agentic_work_order_id": work_order_id,
            "official_reward_id": "opire-21",
            "payer_identity": "verified-maintainer",
        },
    }
    revenue_settlement_evidence._stripe_get_platform_balance_transaction = (
        lambda balance_id: {
            "id": balance_id,
            "object": "balance_transaction",
            "status": "available",
            "amount": -10000,
            "currency": "usd",
            "source": transaction_id,
        }
    )
    revenue_settlement_evidence._stripe_get_destination_payment = (
        lambda payment_id, destination: {
            "id": payment_id,
            "object": "charge",
            "paid": True,
            "refunded": False,
            "amount_refunded": 0,
            "amount": 10000,
            "currency": "usd",
            "balance_transaction": "txn_destination",
        }
    )
    revenue_settlement_evidence._stripe_get_destination_balance_transaction = (
        lambda balance_id, destination: {
            "id": balance_id,
            "object": "balance_transaction",
            "status": destination_status,
            "amount": 10000,
            "net": 9700,
            "fee": 300,
            "currency": "usd",
            "available_on": int(datetime.now(timezone.utc).timestamp())
            + (3600 if destination_status != "available" else -30),
            "source": "py_test",
        }
    )


def create_verified_settlement(
    db_path: Path,
    work_order_id: str,
    settlement_id: str = "settlement-1",
    transaction_id: str = "tr_verified_1",
) -> bool:
    install_verified_stripe_response(work_order_id, transaction_id)
    result = revenue_db.verify_and_record_settlement(
        work_order_id,
        "stripe",
        transaction_id,
        db_path,
    )
    return bool(result.get("created"))


def test_fake_settlement_provider_is_rejected(tmp_path):
    db_path = tmp_path / "revenue.db"
    work_order_id = seed_receivable_work_order(db_path)

    with pytest.raises(ValueError, match="eligible collection lane"):
        revenue_db.verify_and_record_settlement(
        work_order_id,
        "fake-provider",
        "fake-1",
        db_path,
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

    with pytest.raises(ValueError, match="eligible collection lane"):
        revenue_db.verify_and_record_settlement(
        build_order,
        "stripe",
        "po_build_1",
        db_path,
        )


def test_settlement_requires_official_live_paid_provider_response(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "revenue.db"
    work_order_id = seed_receivable_work_order(db_path)

    monkeypatch.setattr(
        revenue_settlement_evidence,
        "_stripe_get",
        lambda transfer_id: {
            "id": transfer_id,
            "object": "transfer",
            "livemode": False,
            "amount": 10000,
            "currency": "usd",
            "created": int(datetime.now(timezone.utc).timestamp()) - 60,
        },
    )
    with pytest.raises(ValueError, match="not live money"):
        revenue_db.verify_and_record_settlement(
            work_order_id, "stripe", "tr_test_1", db_path
        )
    assert revenue_db.status_snapshot(db_path)["realized_revenue"] == {}


def test_real_stripe_transfer_unrelated_to_reward_is_rejected(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "revenue.db"
    work_order_id = seed_receivable_work_order(db_path)
    monkeypatch.setattr(
        revenue_settlement_evidence,
        "_stripe_get",
        lambda transfer_id: {
            "id": transfer_id,
            "object": "transfer",
            "livemode": True,
            "amount": 10000,
            "currency": "usd",
            "created": int(datetime.now(timezone.utc).timestamp()) - 60,
            "destination": "acct_test",
            "destination_payment": "py_test",
            "balance_transaction": "txn_test",
            "reversed": False,
            "amount_reversed": 0,
            "metadata": {
                "agentic_work_order_id": "some-other-work-order",
                "official_reward_id": "unrelated-reward",
                "payer_identity": "someone-else",
            },
        },
    )
    with pytest.raises(ValueError, match="not attributed to this reward"):
        revenue_db.verify_and_record_settlement(
            work_order_id, "stripe", "tr_unrelated_1", db_path
        )
    assert revenue_db.status_snapshot(db_path)["realized_revenue"] == {}


def test_settlement_derives_collector_and_replay_is_idempotent(tmp_path):
    db_path = tmp_path / "revenue.db"
    work_order_id = seed_receivable_work_order(db_path)
    assert revenue_db.upsert_identity("collector", "ghostcli", db_path)

    assert create_verified_settlement(db_path, work_order_id)
    assert not create_verified_settlement(
        db_path,
        work_order_id,
        settlement_id="settlement-duplicate",
        transaction_id="tr_verified_1",
    )
    assert not revenue_db.confirm_settlement("settlement-1", "collector", db_path)


def test_reversed_provider_transfer_never_becomes_revenue(tmp_path, monkeypatch):
    db_path = tmp_path / "revenue.db"
    work_order_id = seed_receivable_work_order(db_path)
    monkeypatch.setattr(
        revenue_settlement_evidence,
        "_stripe_get",
        lambda transfer_id: {
            "id": transfer_id,
            "object": "transfer",
            "livemode": True,
            "amount": 10000,
            "currency": "usd",
            "created": int(datetime.now(timezone.utc).timestamp()) - 60,
            "reversed": True,
            "amount_reversed": 10000,
        },
    )
    with pytest.raises(ValueError, match="reversed"):
        revenue_db.verify_and_record_settlement(
            work_order_id, "stripe", "tr_reversed_1", db_path
        )
    assert revenue_db.status_snapshot(db_path)["realized_revenue"] == {}
    assert revenue_db.get_work_order(work_order_id, db_path)["status"] == "collection"


def test_confirmed_settlement_completes_collection_atomically_and_is_idempotent(tmp_path):
    db_path = tmp_path / "revenue.db"
    work_order_id = seed_receivable_work_order(db_path)
    assert create_verified_settlement(db_path, work_order_id)
    assert revenue_db.get_work_order(work_order_id, db_path)["status"] == "completed"
    assert revenue_db.get_opportunity("candidate-21", db_path)["status"] == "settled"
    assert revenue_db.status_snapshot(db_path)["realized_revenue"] == {"USD": 97.0}


def test_settlement_rejects_transfer_to_unconfigured_destination(tmp_path):
    db_path = tmp_path / "revenue.db"
    work_order_id = seed_receivable_work_order(db_path)
    install_verified_stripe_response(
        work_order_id,
        "tr_wrong_destination",
        destination="acct_other",
    )
    with pytest.raises(ValueError, match="destination mismatch"):
        revenue_db.verify_and_record_settlement(
            work_order_id, "stripe", "tr_wrong_destination", db_path
        )
    assert revenue_db.status_snapshot(db_path)["realized_revenue"] == {}


def test_settlement_rejects_unavailable_destination_balance(tmp_path):
    db_path = tmp_path / "revenue.db"
    work_order_id = seed_receivable_work_order(db_path)
    install_verified_stripe_response(
        work_order_id,
        "tr_unavailable",
        destination_status="pending",
    )
    with pytest.raises(ValueError, match="not available or linked"):
        revenue_db.verify_and_record_settlement(
            work_order_id, "stripe", "tr_unavailable", db_path
        )
    assert revenue_db.status_snapshot(db_path)["realized_revenue"] == {}


def test_later_transfer_reversal_removes_revenue_once(tmp_path):
    db_path = tmp_path / "revenue.db"
    work_order_id = seed_receivable_work_order(db_path)
    assert create_verified_settlement(db_path, work_order_id)
    install_verified_stripe_response(
        work_order_id,
        "tr_verified_1",
        reversed_transfer=True,
    )

    result = revenue_db.revalidate_confirmed_settlements(db_path)
    assert result == [{"work_order_id": work_order_id, "status": "reversed"}]
    assert revenue_db.status_snapshot(db_path)["realized_revenue"] == {}
    assert revenue_db.get_work_order(work_order_id, db_path)["status"] == "collection"
    assert revenue_db.get_opportunity("candidate-21", db_path)["status"] == "payment_pending"
    assert revenue_db.revalidate_confirmed_settlements(db_path) == []
    with revenue_db.connect(db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='settlement_reversal_adjustment'"
        ).fetchone()[0] == 1
