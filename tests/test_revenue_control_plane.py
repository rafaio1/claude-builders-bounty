"""Hermetic control-plane tests: SQLite is the only scheduling input."""

from __future__ import annotations

import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import revenue_control_plane as control_plane
import revenue_db


def test_empty_db_never_reads_global_candidate_json(tmp_path):
    db_path = tmp_path / "revenue.db"
    revenue_db.init_db(db_path)
    control_plane.bootstrap_runtime_identities(db_path)

    assert control_plane.build_work_orders(db_path) == []
    assert revenue_db.status_snapshot(db_path)["lead_count"] == 0


def test_explicit_import_creates_leads_and_never_promotes(tmp_path):
    db_path = tmp_path / "revenue.db"
    candidate_file = tmp_path / "candidates.json"
    candidate_file.write_text(
        json.dumps(
            [
                {
                    "id": "candidate-1",
                    "lane": "build",
                    "repo_key": "owner/repo",
                    "title": "Untrusted candidate",
                    "source_url": "https://github.com/owner/repo/issues/1",
                    "status": "verified",
                    "official_evidence_verified": True,
                    "eligibility_verified": True,
                }
            ]
        ),
        encoding="utf-8",
    )

    assert revenue_db.import_candidates(candidate_file, db_path) == 1
    imported = revenue_db.get_opportunity("candidate-1", db_path)
    assert imported is not None
    assert imported["status"] == "lead"
    assert imported["official_evidence_verified"] == 0
    assert imported["eligibility_verified"] == 0
    control_plane.bootstrap_runtime_identities(db_path)
    assert control_plane.build_work_orders(db_path) == []


def test_plan_status_reports_zero_realized_revenue_without_settlement(tmp_path):
    db_path = tmp_path / "revenue.db"
    status_file = tmp_path / "status.json"

    snapshot = control_plane.plan_once(db_path, status_file=status_file)

    assert snapshot["realized_revenue"] == {}
    assert snapshot["active_work_orders_by_lane"] == {"build": 0, "receivable": 0}
    assert json.loads(status_file.read_text(encoding="utf-8")) == snapshot


def test_plan_once_has_global_budget_of_one_advanced_transition(
    tmp_path, monkeypatch
):
    db_path = tmp_path / "revenue.db"
    calls: list[str] = []
    monkeypatch.setattr(
        control_plane,
        "build_work_orders",
        lambda *args, **kwargs: [{"id": "wo-1"}, {"id": "wo-2"}],
    )

    def run_once(work_order_id, **kwargs):
        calls.append(work_order_id)
        return {"work_order_id": work_order_id, "advanced": True, "status": "advanced"}

    monkeypatch.setattr(control_plane.revenue_workflow, "run_once", run_once)
    snapshot = control_plane.plan_once(db_path)

    assert calls == ["wo-1"]
    assert len(snapshot["workflow"]) == 1
