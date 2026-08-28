"""Behavior tests for the receipt-gated revenue workflow."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import revenue_db
import revenue_evidence
import revenue_workflow


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def seed_work_order(db_path: Path, *, lane: str = "build") -> tuple[str, str]:
    suffix = "build" if lane == "build" else "receivable"
    opportunity_id = f"workflow-{suffix}"
    repo_key = f"owner/workflow-{suffix}"
    source_url = (
        f"https://github.com/{repo_key}/issues/1"
        if lane == "build"
        else f"https://github.com/{repo_key}/pull/2"
    )
    revenue_db.create_lead(
        {
            "id": opportunity_id,
            "lane": lane,
            "repo_key": repo_key,
            "title": f"Workflow {suffix}",
            "source_url": source_url,
        },
        db_path,
    )
    revenue_db.record_repo_health(
        repo_key,
        is_active=True,
        maintainer_active=True,
        health_score=0.9,
        checked_at=now(),
        evidence_url=f"https://github.com/{repo_key}",
        db_path=db_path,
    )
    validation = {
        "platform": "opire",
        "official_reward_id": f"reward-{suffix}",
        "official_evidence_url": f"https://app.opire.dev/rewards/{suffix}",
        "official_evidence_kind": "official_reward",
        "evidence_checked_at": now(),
        "platform_state": "open",
        "linked_state": "open" if lane == "build" else "merged",
        "bounty_amount_usd": 100.0,
        "currency": "USD",
        "claim_path": f"https://app.opire.dev/rewards/{suffix}/claim",
        "payout_method": "stripe",
        "payer_identity": "verified-maintainer",
        "ownership_assignee": "rafaio1",
        "ownership_evidence_url": f"https://github.com/{repo_key}/issues/1",
        "ownership_evidence_kind": "github_assignment",
        "ownership_verified": True,
        "payout_eligible": True,
        "eligibility_verified": True,
        "official_evidence_verified": True,
        "automation_eligible": True,
        "human_action_required": False,
        "feasibility_verified": lane == "build",
        "competition_checked": lane == "build",
        "active_competitors": 0 if lane == "build" else None,
        "estimated_hours": 1.0 if lane == "build" else 0.5,
        "payout_probability": 0.5 if lane == "build" else 0.9,
        "pr_author": "rafaio1" if lane == "receivable" else None,
    }
    assert revenue_db.record_official_validation(opportunity_id, validation, db_path)
    valid, reasons = revenue_db.verify_opportunity(opportunity_id, db_path)
    assert valid, reasons
    for alias in ("revenue_generator", "reviewer", "integrator", "contador"):
        assert revenue_db.upsert_identity(alias, "test", db_path)
    actor = "revenue_generator" if lane == "build" else "contador"
    work_order_id = revenue_db.create_work_order(opportunity_id, actor, db_path)
    assert work_order_id
    return opportunity_id, work_order_id


def add_receipt(
    db_path: Path,
    work_order_id: str,
    action: str,
    actor: str,
    marker: str,
) -> None:
    work = revenue_db.get_work_order(work_order_id, db_path)
    opportunity = revenue_db.get_opportunity(work["opportunity_id"], db_path)
    evidence_paths = {
        "claim_confirmed": "issues/1",
        "tests_passed": "actions/runs/1",
        "review_approved": "pull/2#pullrequestreview-77",
        "pr_published": "pull/2",
        "delivery_accepted": "pull/2",
    }
    head_sha = "a" * 40
    pull = {
        "html_url": f"https://github.com/{opportunity['repo_key']}/pull/2",
        "node_id": "PR_2",
        "state": "closed" if action == "delivery_accepted" else "open",
        "draft": False,
        "body": "Closes #1",
        "user": {"login": "rafaio1"},
        "base": {"repo": {"full_name": opportunity["repo_key"]}},
        "head": {"sha": head_sha},
        "merged": action == "delivery_accepted",
        "merged_at": "2026-08-28T10:20:00Z" if action == "delivery_accepted" else None,
        "merged_by": {"login": "maintainer"} if action == "delivery_accepted" else None,
        "merge_commit_sha": "b" * 40 if action == "delivery_accepted" else None,
    }

    def get(path: str):
        if path.endswith("/issues/1"):
            return {
                "html_url": f"https://github.com/{opportunity['repo_key']}/issues/1",
                "node_id": "ISSUE_1",
                "state": "open",
                "assignees": [{"login": "rafaio1"}],
                "updated_at": "2026-08-28T10:00:00Z",
            }
        if path.endswith("/actions/runs/1"):
            return {
                "id": 1,
                "html_url": f"https://github.com/{opportunity['repo_key']}/actions/runs/1",
                "repository": {"full_name": opportunity["repo_key"]},
                "status": "completed",
                "conclusion": "success",
                "head_sha": head_sha,
                "run_attempt": 1,
                "event": "pull_request",
            }
        if path.endswith("/pulls/2/reviews/77"):
            return {
                "id": 77,
                "state": "APPROVED",
                "user": {"login": "maintainer"},
                "author_association": "MEMBER",
                "commit_id": head_sha,
                "submitted_at": "2026-08-28T10:10:00Z",
            }
        if path.endswith("/pulls/2"):
            return pull
        raise AssertionError(path)

    revenue_evidence._github_get = get
    receipt = revenue_db.verify_and_record_work_order_action(
        work_order_id,
        action,
        f"https://github.com/{opportunity['repo_key']}/{evidence_paths[action]}",
        db_path,
    )
    assert receipt["actor_alias"] == revenue_evidence.ACTION_ACTORS[action]


def test_missing_receipt_and_dry_run_never_mutate(tmp_path):
    db_path = tmp_path / "revenue.db"
    _, work_order_id = seed_work_order(db_path)

    dry = revenue_workflow.run_once(work_order_id, db_path=db_path)
    live = revenue_workflow.run_once(
        work_order_id,
        dry_run=False,
        db_path=db_path,
    )

    assert dry["status"] == "waiting_receipt"
    assert dry["required_receipt"] == "claim_confirmed"
    assert live["status"] == "waiting_receipt"
    assert revenue_db.get_work_order(work_order_id, db_path)["status"] == "queued"


def test_one_receipt_advances_exactly_one_checkpoint(tmp_path):
    db_path = tmp_path / "revenue.db"
    opportunity_id, work_order_id = seed_work_order(db_path)
    add_receipt(
        db_path,
        work_order_id,
        "claim_confirmed",
        "revenue_generator",
        "a",
    )

    preview = revenue_workflow.run_once(work_order_id, db_path=db_path)
    assert preview["status"] == "ready"
    assert revenue_db.get_work_order(work_order_id, db_path)["status"] == "queued"

    result = revenue_workflow.run_once(
        work_order_id,
        dry_run=False,
        db_path=db_path,
    )
    assert result["status"] == "advanced"
    assert result["current_status"] == "in_progress"
    assert revenue_db.get_opportunity(opportunity_id, db_path)["status"] == "implementing"
    next_plan = revenue_workflow.run_once(
        work_order_id,
        dry_run=False,
        db_path=db_path,
    )
    assert next_plan["required_receipt"] == "tests_passed"
    assert revenue_db.get_work_order(work_order_id, db_path)["status"] == "in_progress"


def test_wrong_actor_cannot_self_approve(tmp_path):
    db_path = tmp_path / "revenue.db"
    _, work_order_id = seed_work_order(db_path)
    add_receipt(db_path, work_order_id, "claim_confirmed", "reviewer", "b")

    result = revenue_workflow.run_once(
        work_order_id,
        dry_run=False,
        actor_alias="reviewer",
        db_path=db_path,
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "actor_not_allowed_for_checkpoint"
    assert revenue_db.get_work_order(work_order_id, db_path)["status"] == "queued"


def test_full_build_lifecycle_waits_for_platform_before_receivable(tmp_path):
    db_path = tmp_path / "revenue.db"
    opportunity_id, work_order_id = seed_work_order(db_path)
    checkpoints = (
        ("claim_confirmed", "revenue_generator", "a"),
        ("tests_passed", "revenue_generator", "b"),
        ("pr_published", "integrator", "d"),
        ("review_approved", "reviewer", "c"),
    )
    for action, actor, marker in checkpoints:
        add_receipt(db_path, work_order_id, action, actor, marker)
        result = revenue_workflow.run_once(
            work_order_id,
            dry_run=False,
            db_path=db_path,
        )
        assert result["status"] == "advanced"

    monitor = revenue_workflow.run_once(
        work_order_id,
        dry_run=False,
        db_path=db_path,
    )
    assert monitor["status"] == "waiting_receipt"
    assert monitor["observational"] is True
    assert revenue_db.get_work_order(work_order_id, db_path)["status"] == "published"

    add_receipt(db_path, work_order_id, "delivery_accepted", "contador", "e")
    accepted = revenue_workflow.run_once(
        work_order_id,
        dry_run=False,
        db_path=db_path,
    )
    assert accepted["status"] == "advanced"
    assert accepted["current_status"] == "completed"
    opportunity = revenue_db.get_opportunity(opportunity_id, db_path)
    assert opportunity["status"] == "accepted"
    assert opportunity["status"] not in {"payment_pending", "settled"}
    with revenue_db.connect(db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM opportunities WHERE lane='receivable'"
        ).fetchone()[0] == 0
    assert revenue_db.status_snapshot(db_path)["realized_revenue"] == {}


def test_receivable_lane_is_observational_only(tmp_path):
    db_path = tmp_path / "revenue.db"
    opportunity_id, work_order_id = seed_work_order(db_path, lane="receivable")

    result = revenue_workflow.run_once(
        work_order_id,
        dry_run=False,
        db_path=db_path,
    )

    assert result["status"] == "observing"
    assert result["observational"] is True
    assert revenue_db.get_work_order(work_order_id, db_path)["status"] == "collection"
    assert revenue_db.get_opportunity(opportunity_id, db_path)["status"] == "payment_pending"
    assert revenue_db.status_snapshot(db_path)["realized_revenue"] == {}
