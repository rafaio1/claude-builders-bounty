"""Receipt-gated, one-checkpoint executor for Revenue Control Plane v2.

Discovery and qualification remain in :mod:`revenue_db`.  This module only
advances an existing build work order after a durable receipt has been stored.
It never writes opportunity state directly and never manufactures settlement.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from typing import Any

import revenue_db


@dataclass(frozen=True)
class WorkflowStep:
    expected_status: str
    next_status: str
    receipt_type: str
    actors: tuple[str, ...]
    action: str
    observational_without_receipt: bool = False


WORKFLOW_STEPS: dict[str, WorkflowStep] = {
    "queued": WorkflowStep(
        "queued",
        "in_progress",
        "claim_confirmed",
        ("revenue_generator",),
        "confirm_official_claim",
    ),
    "in_progress": WorkflowStep(
        "in_progress",
        "under_review",
        "tests_passed",
        ("revenue_generator",),
        "implement_and_record_tests",
    ),
    "under_review": WorkflowStep(
        "under_review",
        "integration_ready",
        "pr_published",
        ("integrator",),
        "independently_review_then_publish_pull_request",
    ),
    "integration_ready": WorkflowStep(
        "integration_ready",
        "published",
        "review_approved",
        ("reviewer",),
        "observe_independent_maintainer_approval",
    ),
    "published": WorkflowStep(
        "published",
        "completed",
        "delivery_accepted",
        ("contador",),
        "monitor_delivery_acceptance",
        observational_without_receipt=True,
    ),
}

TERMINAL_STATES = frozenset({"completed", "failed", "cancelled"})


def _receipt_for_step(
    work_order_id: str,
    step: WorkflowStep,
    actor_alias: str | None,
    db_path: str | os.PathLike[str] | None,
) -> tuple[str, dict[str, Any] | None]:
    if actor_alias is not None:
        if actor_alias not in step.actors:
            return actor_alias, None
        return actor_alias, revenue_db.find_work_order_action(
            work_order_id,
            step.receipt_type,
            actor_alias,
            db_path,
        )
    for candidate in step.actors:
        receipt = revenue_db.find_work_order_action(
            work_order_id,
            step.receipt_type,
            candidate,
            db_path,
        )
        if receipt:
            return candidate, receipt
    return step.actors[0], None


def plan_next_action(
    work_order_id: str,
    *,
    actor_alias: str | None = None,
    db_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Return one fail-closed next action without mutating state."""
    work_order = revenue_db.get_work_order(work_order_id, db_path)
    if not work_order:
        return {
            "work_order_id": work_order_id,
            "status": "not_found",
            "ready": False,
            "reason": "work_order_not_found",
        }

    status = str(work_order["status"])
    lane = str(work_order["lane"])
    base: dict[str, Any] = {
        "work_order_id": work_order_id,
        "opportunity_id": work_order["opportunity_id"],
        "lane": lane,
        "current_status": status,
        "ready": False,
    }
    if lane == "receivable":
        base.update(
            {
                "status": "observing",
                "action": "observe_canonical_settlement",
                "reason": "settlement_requires_create_and_confirm_settlement",
                "observational": True,
            }
        )
        return base
    if lane != "build":
        base.update({"status": "blocked", "reason": "unknown_lane"})
        return base
    if status in TERMINAL_STATES:
        base.update({"status": "terminal", "reason": f"work_order_{status}"})
        return base

    step = WORKFLOW_STEPS.get(status)
    if not step:
        base.update({"status": "blocked", "reason": "unknown_work_order_status"})
        return base
    if actor_alias is not None and actor_alias not in step.actors:
        base.update(
            {
                "status": "blocked",
                "action": step.action,
                "required_receipt": step.receipt_type,
                "required_actors": list(step.actors),
                "reason": "actor_not_allowed_for_checkpoint",
            }
        )
        return base

    selected_actor, receipt = _receipt_for_step(
        work_order_id,
        step,
        actor_alias,
        db_path,
    )
    base.update(
        {
            "status": "ready" if receipt else "waiting_receipt",
            "action": step.action,
            "next_status": step.next_status,
            "required_receipt": step.receipt_type,
            "required_actors": list(step.actors),
            "actor_alias": selected_actor,
            "receipt_present": bool(receipt),
            "receipt_id": receipt["receipt_id"] if receipt else None,
            "ready": bool(receipt),
            "observational": bool(
                step.observational_without_receipt and receipt is None
            ),
            "reason": None if receipt else "durable_receipt_missing",
        }
    )
    return base


def run_once(
    work_order_id: str,
    *,
    dry_run: bool = True,
    actor_alias: str | None = None,
    db_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Advance at most one checkpoint through the canonical receipt-aware CAS."""
    try:
        plan = plan_next_action(
            work_order_id,
            actor_alias=actor_alias,
            db_path=db_path,
        )
        plan["dry_run"] = bool(dry_run)
        if dry_run or not plan.get("ready"):
            return plan
        advanced = revenue_db.cas_transition_work_order(
            work_order_id,
            str(plan["current_status"]),
            str(plan["next_status"]),
            str(plan["actor_alias"]),
            db_path,
        )
        if not advanced:
            plan.update(
                {
                    "status": "blocked",
                    "ready": False,
                    "reason": "canonical_cas_rejected",
                }
            )
            return plan
        current = revenue_db.get_work_order(work_order_id, db_path)
        plan.update(
            {
                "status": "advanced",
                "ready": False,
                "advanced": True,
                "current_status": current["status"] if current else None,
                "reason": None,
            }
        )
        return plan
    except (OSError, sqlite3.Error, ValueError) as error:
        return {
            "work_order_id": work_order_id,
            "status": "error",
            "ready": False,
            "dry_run": bool(dry_run),
            "reason": type(error).__name__,
        }
