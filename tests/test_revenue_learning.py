"""Scoped tests for verified-outcome strategy learning."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import revenue_control_plane
import revenue_db
import revenue_learning


def timestamp(value: datetime | None = None) -> str:
    return (value or datetime.now(timezone.utc)).isoformat()


def lane(snapshot: dict, name: str) -> dict:
    return next(item for item in snapshot["lanes"] if item["lane"] == name)


def payload_digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def record_outcome(
    db_path: Path,
    *,
    subject: str,
    outcome: str,
    source: str,
    source_id: str,
    evidence_url: str,
    observed_at: str,
) -> bool:
    return revenue_learning.record_verified_outcome(
        lane="build",
        subject_key=subject,
        outcome_type=outcome,
        source_kind=source,
        source_event_id=source_id,
        evidence_url=evidence_url,
        payload_sha256=payload_digest(f"{source}:{source_id}:{outcome}"),
        observed_at=observed_at,
        db_path=db_path,
    )


def test_nominal_values_never_become_realized_revenue(tmp_path):
    db_path = tmp_path / "revenue.db"
    revenue_db.create_lead(
        {
            "id": "nominal-1",
            "lane": "build",
            "repo_key": "owner/nominal",
            "title": "Nominal bounty",
            "source_url": "https://github.com/owner/nominal/issues/1",
            "estimated_payout_usd": 1_000_000,
        },
        db_path,
    )
    with revenue_db.connect(db_path, immediate=True) as conn:
        conn.execute(
            "UPDATE opportunities SET bounty_amount_usd=100000 WHERE id='nominal-1'"
        )

    learned = lane(revenue_learning.strategy_snapshot(db_path), "build")

    assert learned["terminal_outcomes"] == 0
    assert learned["realized_settlement_net_usd"] == 0
    assert learned["measured_cost_usd"] == 0
    assert learned["profitable"] is None
    assert learned["profitability_status"] == "unknown_costs"
    with pytest.raises(ValueError, match="confirmed settlement"):
        revenue_learning.record_verified_outcome(
            lane="build",
            subject_key="nominal-1",
            outcome_type="settled",
            source_kind="github_api",
            source_event_id="fake-paid",
            evidence_url="https://api.github.com/repos/owner/nominal/pulls/1",
            payload_sha256="0" * 64,
            observed_at=timestamp(),
            db_path=db_path,
        )


def test_official_terminal_outcomes_are_idempotent_and_conversion_only(tmp_path):
    db_path = tmp_path / "revenue.db"
    base = datetime.now(timezone.utc) - timedelta(minutes=10)
    observations = [
        (
            "accepted-subject",
            "accepted",
            "github_api",
            "pr-accepted",
            "https://api.github.com/repos/owner/repo/pulls/1",
        ),
        (
            "merged-subject",
            "merged",
            "github_api",
            "pr-merged",
            "https://api.github.com/repos/owner/repo/pulls/2",
        ),
        (
            "duplicate-subject",
            "duplicate",
            "hackerone_api",
            "h1-duplicate",
            "https://api.hackerone.com/v1/hackers/reports/3",
        ),
        (
            "informative-subject",
            "informative",
            "hackerone_api",
            "h1-informative",
            "https://api.hackerone.com/v1/hackers/reports/4",
        ),
        (
            "rejected-subject",
            "rejected",
            "github_api",
            "pr-rejected",
            "https://api.github.com/repos/owner/repo/pulls/5",
        ),
    ]
    for offset, observation in enumerate(observations):
        assert record_outcome(
            db_path,
            subject=observation[0],
            outcome=observation[1],
            source=observation[2],
            source_id=observation[3],
            evidence_url=observation[4],
            observed_at=timestamp(base + timedelta(minutes=offset)),
        )
    assert not record_outcome(
        db_path,
        subject=observations[0][0],
        outcome=observations[0][1],
        source=observations[0][2],
        source_id=observations[0][3],
        evidence_url=observations[0][4],
        observed_at=timestamp(base),
    )

    first = lane(revenue_learning.strategy_snapshot(db_path), "build")
    second = lane(revenue_learning.strategy_snapshot(db_path), "build")

    assert first["terminal_outcomes"] == second["terminal_outcomes"] == 5
    assert first["accepted_outcomes"] == 1
    assert first["merged_outcomes"] == 1
    assert first["duplicate_outcomes"] == 1
    assert first["informative_outcomes"] == 1
    assert first["rejected_outcomes"] == 1
    assert first["acceptance_conversion"] == 0.4
    assert first["settlement_conversion"] == 0
    assert first["realized_settlement_net_usd"] == 0
    assert first["decision"] == "pivot"
    with pytest.raises(ValueError, match="allowlisted official adapter"):
        record_outcome(
            db_path,
            subject="fake",
            outcome="merged",
            source="github_api",
            source_id="fake",
            evidence_url="https://example.invalid/fake",
            observed_at=timestamp(),
        )


def seed_confirmed_settlement(db_path: Path, received: datetime) -> None:
    revenue_db.init_db(db_path)
    assert revenue_db.upsert_identity("contador", "ghostcli", db_path)
    revenue_db.create_lead(
        {
            "id": "paid-1",
            "lane": "receivable",
            "repo_key": "owner/paid",
            "title": "Paid delivery",
            "source_url": "https://github.com/owner/paid/pull/1",
        },
        db_path,
    )
    observed = timestamp(received)
    with revenue_db.connect(db_path, immediate=True) as conn:
        conn.execute(
            """UPDATE opportunities
               SET status='settled', payout_method='stripe', currency='USD',
                   bounty_amount_usd=5000, updated_at=?
               WHERE id='paid-1'""",
            (observed,),
        )
        conn.execute(
            """INSERT INTO work_orders
               (id, opportunity_id, lane, actor_alias, collector_alias,
                status, ev_net_per_hour, created_at, updated_at)
               VALUES ('wo-paid-1', 'paid-1', 'receivable', 'contador', 'contador',
                       'completed', 9999, ?, ?)""",
            (observed, observed),
        )
        conn.execute(
            """INSERT INTO settlements
               (id, work_order_id, provider, transaction_id,
                provider_verification_url, provider_verification_id,
                provider_verified_at, collector_alias, currency, gross_amount,
                fee_amount, net_amount, status, received_at, created_at, updated_at)
               VALUES ('settlement-paid-1', 'wo-paid-1', 'stripe', 'po_learning_1',
                       'https://dashboard.stripe.com/payouts/po_learning_1',
                       'po_learning_1', ?, 'contador', 'USD', 100, 3, 97,
                       'confirmed', ?, ?, ?)""",
            (observed, observed, observed, observed),
        )


def test_profitability_requires_settlement_and_complete_measured_costs(tmp_path):
    db_path = tmp_path / "revenue.db"
    received = datetime.now(timezone.utc) - timedelta(hours=1)
    seed_confirmed_settlement(db_path, received)

    before_costs = lane(revenue_learning.strategy_snapshot(db_path), "receivable")

    assert before_costs["terminal_outcomes"] == 1
    assert before_costs["settled_outcomes"] == 1
    assert before_costs["realized_settlement_net_usd"] == 97
    assert before_costs["costs_known"] is False
    assert before_costs["profitable"] is None
    assert before_costs["decision"] == "measure_costs"
    assert revenue_learning.sync_confirmed_settlements(db_path) == 0

    period_start = received - timedelta(minutes=30)
    period_end = received + timedelta(minutes=30)
    measured_at = datetime.now(timezone.utc)
    amounts = {"compute": 10.0, "api": 2.0, "server": 5.0}
    for category, amount in amounts.items():
        evidence = tmp_path / f"{category}.json"
        evidence.write_text(json.dumps({"category": category, "amount_usd": amount}))
        digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
        kwargs = {
            "measurement_id": f"meter-{category}-1",
            "lane": "receivable",
            "category": category,
            "amount_usd": amount,
            "period_start": timestamp(period_start),
            "period_end": timestamp(period_end),
            "source_kind": "local_meter",
            "evidence_ref": str(evidence),
            "payload_sha256": digest,
            "measured_at": timestamp(measured_at),
            "db_path": db_path,
        }
        assert revenue_learning.record_measured_cost(**kwargs)
        assert not revenue_learning.record_measured_cost(**kwargs)

    after_costs = lane(revenue_learning.strategy_snapshot(db_path), "receivable")

    assert after_costs["realized_settlement_net_usd"] == 97
    assert after_costs["measured_cost_usd"] == 17
    assert after_costs["realized_profit_usd"] == 80
    assert after_costs["costs_known"] is True
    assert after_costs["profitable"] is True
    assert after_costs["profitability_status"] == "profitable"
    assert after_costs["decision"] == "active"


def test_exploration_cap_is_enforced_before_work_order_creation(tmp_path, monkeypatch):
    db_path = tmp_path / "revenue.db"
    for number, lane_name in enumerate(("build", "receivable", "build"), 1):
        revenue_db.create_lead(
            {
                "id": f"candidate-{number}",
                "lane": lane_name,
                "repo_key": f"owner/repo-{number}",
                "title": f"Candidate {number}",
                "source_url": f"https://github.com/owner/repo-{number}/issues/{number}",
            },
            db_path,
        )
        with revenue_db.connect(db_path, immediate=True) as conn:
            conn.execute(
                "UPDATE opportunities SET status='verified', ev_net_per_hour=? WHERE id=?",
                (100 - number, f"candidate-{number}"),
            )
    attempted: list[str] = []

    def fake_create(opportunity_id, *args, **kwargs):
        attempted.append(opportunity_id)
        return f"wo-{opportunity_id}"

    monkeypatch.setattr(revenue_db, "create_work_order", fake_create)

    revenue_learning.build_ranked_work_orders(db_path, max_orders=3)

    assert revenue_learning.exploration_slot_limit(3) == 1
    assert len(attempted) == 1


def test_control_plane_exposes_learning_and_actions_fail_closed(tmp_path):
    db_path = tmp_path / "revenue.db"
    snapshot = revenue_control_plane.plan_once(
        db_path,
        status_file=tmp_path / "status.json",
    )

    assert snapshot["realized_revenue"] == {}
    assert snapshot["learning"]["exploration_slots"] == 1
    assert {item["decision"] for item in snapshot["learning"]["lanes"]} == {"explore"}
    assert revenue_learning.gate_action("discovery")["status"] == "autonomous"
    assert revenue_learning.gate_action(
        "platform_submission", official_scope_authorized=True
    )["status"] == "autonomous"
    assert revenue_learning.gate_action("platform_submission")["status"] == "human_required"
    assert revenue_learning.gate_action("unknown_action")["status"] == "human_required"
    for condition in revenue_learning.HUMAN_REQUIRED_CONDITIONS:
        result = revenue_learning.gate_action("monitoring", conditions=[condition])
        assert result["status"] == "human_required"
        assert condition in result["reasons"]
