#!/usr/bin/env python3
"""Revenue Control Plane v2 command runner.

SQLite is the sole scheduling source.  Candidate JSON is accepted only through
the explicit ``import-leads`` command and is never promoted automatically.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Iterable

import revenue_learning
import revenue_db
import revenue_workflow


BASE = Path("/Agentic")
STATUS_FILE = BASE / "data/aro/revenue_manager_v2_status.json"
LOCK_FILE = BASE / "data/aro/.revenue_control_plane_v2.lock"


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temporary, path)


def acquire_lock(lock_path: Path = LOCK_FILE) -> bool:
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = lock_path.open("w", encoding="utf-8")
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        descriptor.write(str(os.getpid()))
        descriptor.flush()
        acquire_lock._descriptor = descriptor
        acquire_lock._path = lock_path
        return True
    except OSError:
        return False


def release_lock() -> None:
    descriptor = getattr(acquire_lock, "_descriptor", None)
    lock_path = getattr(acquire_lock, "_path", None)
    if descriptor is None:
        return
    try:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        descriptor.close()
    finally:
        if lock_path:
            lock_path.unlink(missing_ok=True)
        acquire_lock._descriptor = None


def bootstrap_runtime_identities(db_path: str | os.PathLike[str] | None = None) -> None:
    """Create only role aliases that are compiled into the allowlist."""
    for alias in ("revenue_generator", "contador", "reviewer", "integrator", "collector"):
        if not revenue_db.upsert_identity(alias, "ghostcli", db_path):
            raise RuntimeError(f"identity rejected by allowlist: {alias}")


def build_work_orders(
    db_path: str | os.PathLike[str] | None = None,
    *,
    max_orders: int = revenue_db.MAX_ACTIVE_WORK_ORDERS,
    supported_payout_methods: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Schedule verified rows through the realized-outcome strategy gate."""
    return revenue_learning.build_ranked_work_orders(
        db_path,
        max_orders=max_orders,
        supported_payout_methods=supported_payout_methods,
    )


def plan_once(
    db_path: str | os.PathLike[str] | None = None,
    *,
    max_orders: int = revenue_db.MAX_ACTIVE_WORK_ORDERS,
    supported_payout_methods: Iterable[str] | None = None,
    status_file: Path = STATUS_FILE,
) -> dict[str, Any]:
    revenue_db.init_db(db_path)
    bootstrap_runtime_identities(db_path)
    settlement_revalidation = revenue_db.revalidate_confirmed_settlements(
        db_path,
        max_items=20,
    )
    work_orders = build_work_orders(
        db_path,
        max_orders=max_orders,
        supported_payout_methods=supported_payout_methods,
    )
    workflow_results = []
    for work_order in work_orders:
        result = revenue_workflow.run_once(
            str(work_order["id"]),
            dry_run=False,
            db_path=db_path,
        )
        workflow_results.append(result)
        if result.get("advanced") is True:
            break
    snapshot = revenue_db.status_snapshot(db_path)
    snapshot["settlement_revalidation"] = settlement_revalidation
    snapshot["workflow"] = workflow_results
    snapshot["learning"] = revenue_learning.strategy_snapshot(
        db_path,
        max_orders=max_orders,
        refresh=False,
    )
    save_json(status_file, snapshot)
    return snapshot


def cmd_plan(args: argparse.Namespace) -> int:
    if not acquire_lock(Path(args.lock_file)):
        print("LOCK_HELD_BY_ANOTHER_PROCESS", file=sys.stderr)
        return 1
    try:
        snapshot = plan_once(
            args.db,
            max_orders=args.max_orders,
            supported_payout_methods=args.payout_method,
            status_file=Path(args.status_file),
        )
        print(json.dumps(snapshot, indent=2, sort_keys=True))
        return 0
    finally:
        release_lock()


def cmd_import_leads(args: argparse.Namespace) -> int:
    count = revenue_db.import_candidates(args.path, args.db)
    print(json.dumps({"imported_leads": count, "promoted": 0}, sort_keys=True))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    snapshot = revenue_db.status_snapshot(args.db)
    snapshot["learning"] = revenue_learning.strategy_snapshot(args.db)
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


def cmd_workflow_once(args: argparse.Namespace) -> int:
    result = revenue_workflow.run_once(
        args.work_order_id,
        dry_run=not args.apply,
        actor_alias=args.actor,
        db_path=args.db,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result.get("status") in {"error", "not_found"} else 0


def cmd_verify_evidence(args: argparse.Namespace) -> int:
    try:
        result = revenue_db.verify_and_record_work_order_action(
            args.work_order_id,
            args.action,
            args.evidence_url,
            args.db,
        )
    except (OSError, ValueError) as error:
        print(
            json.dumps(
                {
                    "status": "rejected",
                    "reason": type(error).__name__,
                    "work_order_id": args.work_order_id,
                    "action": args.action,
                },
                sort_keys=True,
            )
        )
        return 1
    safe = {
        key: result.get(key)
        for key in (
            "work_order_id",
            "action_type",
            "evidence_url",
            "receipt_id",
            "observed_at",
            "actor_alias",
            "expected_from_status",
            "work_order_version",
            "created",
        )
    }
    safe["status"] = "verified"
    print(json.dumps(safe, indent=2, sort_keys=True))
    return 0


def cmd_verify_settlement(args: argparse.Namespace) -> int:
    try:
        result = revenue_db.verify_and_record_settlement(
            args.work_order_id,
            args.provider,
            args.transaction_id,
            args.db,
        )
    except (OSError, ValueError) as error:
        print(
            json.dumps(
                {
                    "status": "rejected",
                    "reason": type(error).__name__,
                    "work_order_id": args.work_order_id,
                    "provider": args.provider,
                },
                sort_keys=True,
            )
        )
        return 1
    safe = {
        key: result.get(key)
        for key in (
            "id",
            "work_order_id",
            "provider",
            "transaction_id",
            "currency",
            "net_amount",
            "status",
            "received_at",
            "created",
        )
    }
    print(json.dumps(safe, indent=2, sort_keys=True))
    return 0


def cmd_loop(args: argparse.Namespace) -> int:
    if not acquire_lock(Path(args.lock_file)):
        print("LOCK_HELD_BY_ANOTHER_PROCESS", file=sys.stderr)
        return 1
    try:
        for iteration in range(1, args.max_iterations + 1):
            try:
                snapshot = plan_once(
                    args.db,
                    max_orders=args.max_orders,
                    supported_payout_methods=args.payout_method,
                    status_file=Path(args.status_file),
                )
                print(
                    json.dumps(
                        {"iteration": iteration, "status": "ok", "snapshot": snapshot},
                        sort_keys=True,
                    ),
                    flush=True,
                )
            except Exception as error:
                print(
                    json.dumps(
                        {"iteration": iteration, "status": "error", "error": str(error)},
                        sort_keys=True,
                    ),
                    flush=True,
                )
            if iteration < args.max_iterations:
                time.sleep(args.interval)
        return 0
    finally:
        release_lock()


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--db", help="absolute v2 SQLite path")
    root.add_argument("--status-file", default=str(STATUS_FILE))
    root.add_argument("--lock-file", default=str(LOCK_FILE))
    subparsers = root.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan")
    plan.add_argument("--max-orders", type=int, default=revenue_db.MAX_ACTIVE_WORK_ORDERS)
    plan.add_argument("--payout-method", action="append")
    plan.set_defaults(handler=cmd_plan)

    import_leads = subparsers.add_parser("import-leads")
    import_leads.add_argument("path", help="explicit bounded JSON list")
    import_leads.set_defaults(handler=cmd_import_leads)

    status = subparsers.add_parser("status")
    status.set_defaults(handler=cmd_status)

    workflow_once = subparsers.add_parser("workflow-once")
    workflow_once.add_argument("work_order_id")
    workflow_once.add_argument("--actor")
    workflow_once.add_argument(
        "--apply",
        action="store_true",
        help="advance one checkpoint only when its durable receipt exists",
    )
    workflow_once.set_defaults(handler=cmd_workflow_once)

    verify_evidence = subparsers.add_parser("verify-evidence")
    verify_evidence.add_argument("work_order_id")
    verify_evidence.add_argument(
        "action",
        choices=sorted(revenue_db._WORK_ORDER_ACTION_ALLOWLIST),
    )
    verify_evidence.add_argument("evidence_url")
    verify_evidence.set_defaults(handler=cmd_verify_evidence)

    verify_settlement = subparsers.add_parser("verify-settlement")
    verify_settlement.add_argument("work_order_id")
    verify_settlement.add_argument("provider", choices=("stripe",))
    verify_settlement.add_argument("transaction_id")
    verify_settlement.set_defaults(handler=cmd_verify_settlement)

    loop = subparsers.add_parser("loop")
    loop.add_argument("--interval", type=int, default=300)
    loop.add_argument("--max-iterations", type=int, default=10)
    loop.add_argument("--max-orders", type=int, default=revenue_db.MAX_ACTIVE_WORK_ORDERS)
    loop.add_argument("--payout-method", action="append")
    loop.set_defaults(handler=cmd_loop)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.db is not None:
        revenue_db.resolve_db_path(args.db)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
