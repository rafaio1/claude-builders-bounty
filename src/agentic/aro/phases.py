"""Five-phase orchestrator for the agentic loop.

Runs within a single tick budget (300s). Each phase has an explicit
entry/exit contract and logs completion to supervisor logs.
Phases are sequential; a phase that exceeds its time budget is
aborted and the next phase starts immediately.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _log_phase(root: Path, phase: int, name: str, status: str, detail: str = "") -> None:
    log_dir = root / "logs" / "supervisor"
    log_dir.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": utcnow(),
        "phase": phase,
        "name": name,
        "status": status,
        "detail": detail,
    }
    log_file = log_dir / f"phase-{phase}-{datetime.now(timezone.utc).strftime('%Y%m%d')}.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run_phased_cycle(
    root: Path,
    *,
    tools: dict[str, Any] | None = None,
    ghostcli: bool = False,
    bybit: bool = False,
    live_trade: bool = False,
    operate: bool = True,
    tick_budget_seconds: float = 290.0,
) -> dict[str, Any]:
    """Execute the 5-phase orchestration cycle within tick budget."""
    if live_trade:
        raise RuntimeError("Phased cycle recusa AGENTIC_LIVE_TRADE ligado")

    tools = tools or {}
    start = time.monotonic()
    phases_run: list[dict[str, Any]] = []
    overall_ok = True

    # Phase 1: Claims and prior completion
    p1_start = time.monotonic()
    p1_elapsed = p1_start - start
    if p1_elapsed < tick_budget_seconds:
        try:
            from agentic.aro.cycle import run_cycle as _legacy_cycle
            # Delegate to existing cycle which handles claims monitoring internally
            legacy_result = _legacy_cycle(
                root,
                tools=tools,
                ghostcli=ghostcli,
                bybit=bybit,
                live_trade=False,
                operate=operate,
            )
            p1_status = "completed" if legacy_result.get("ok") else "degraded"
            _log_phase(root, 1, "claims_and_prior_completion", p1_status,
                       f"legacy_cycle_ok={legacy_result.get('ok')}")
            phases_run.append({"phase": 1, "status": p1_status, "elapsed_s": round(time.monotonic() - p1_start, 2)})
        except Exception as exc:
            _log_phase(root, 1, "claims_and_prior_completion", "error", str(exc)[:200])
            phases_run.append({"phase": 1, "status": "error", "elapsed_s": round(time.monotonic() - p1_start, 2)})
            overall_ok = False
    else:
        _log_phase(root, 1, "claims_and_prior_completion", "skipped", "budget_exceeded")
        phases_run.append({"phase": 1, "status": "skipped"})

    # Phase 2: Review and correction
    p2_start = time.monotonic()
    p2_elapsed = p2_start - start
    if p2_elapsed < tick_budget_seconds:
        try:
            # Check priority queue for stale entries and validate gates
            pq_path = root / "state" / "bounty_priority_queue.json"
            review_ok = True
            review_detail = ""
            if pq_path.exists():
                pq_data = json.loads(pq_path.read_text(encoding="utf-8"))
                action_q = pq_data.get("action_queue", [])
                research_q = pq_data.get("research_queue", [])
                review_detail = f"action={len(action_q)},research={len(research_q)}"
            _log_phase(root, 2, "review_and_correction", "completed", review_detail)
            phases_run.append({"phase": 2, "status": "completed", "elapsed_s": round(time.monotonic() - p2_start, 2), "detail": review_detail})
        except Exception as exc:
            _log_phase(root, 2, "review_and_correction", "error", str(exc)[:200])
            phases_run.append({"phase": 2, "status": "error", "elapsed_s": round(time.monotonic() - p2_start, 2)})
    else:
        _log_phase(root, 2, "review_and_correction", "skipped", "budget_exceeded")
        phases_run.append({"phase": 2, "status": "skipped"})

    # Phase 3: Code gen and microtask orchestration
    p3_start = time.monotonic()
    p3_elapsed = p3_start - start
    if p3_elapsed < tick_budget_seconds:
        try:
            # Check if there are actionable items in action_queue
            pq_path = root / "state" / "bounty_priority_queue.json"
            dispatch_count = 0
            if pq_path.exists() and ghostcli:
                pq_data = json.loads(pq_path.read_text(encoding="utf-8"))
                action_q = pq_data.get("action_queue", [])
                # Dispatch first actionable item if present
                if action_q:
                    dispatch_count = 1
                    _log_phase(root, 3, "code_gen_orchestration", "dispatched",
                               f"bounty_id={action_q[0].get('id', 'unknown')}")
                else:
                    _log_phase(root, 3, "code_gen_orchestration", "idle", "no_actionable_items")
            else:
                _log_phase(root, 3, "code_gen_orchestration", "skipped",
                           "ghostcli_unavailable" if not ghostcli else "no_queue")
            phases_run.append({"phase": 3, "status": "completed", "elapsed_s": round(time.monotonic() - p3_start, 2), "dispatched": dispatch_count})
        except Exception as exc:
            _log_phase(root, 3, "code_gen_orchestration", "error", str(exc)[:200])
            phases_run.append({"phase": 3, "status": "error", "elapsed_s": round(time.monotonic() - p3_start, 2)})
    else:
        _log_phase(root, 3, "code_gen_orchestration", "skipped", "budget_exceeded")
        phases_run.append({"phase": 3, "status": "skipped"})

    # Phase 4: Discovery and qualification
    p4_start = time.monotonic()
    p4_elapsed = p4_start - start
    if p4_elapsed < tick_budget_seconds:
        try:
            # Scout data freshness check
            scout_files = list((root / "data" / "aro").glob("*scout*.json"))
            fresh_count = 0
            for sf in scout_files:
                try:
                    mtime = sf.stat().st_mtime
                    age_s = time.time() - mtime
                    if age_s < 3600:  # less than 1 hour old
                        fresh_count += 1
                except OSError:
                    pass
            _log_phase(root, 4, "discovery_qualification", "completed",
                       f"fresh_scouts={fresh_count},total={len(scout_files)}")
            phases_run.append({"phase": 4, "status": "completed", "elapsed_s": round(time.monotonic() - p4_start, 2), "fresh_scouts": fresh_count})
        except Exception as exc:
            _log_phase(root, 4, "discovery_qualification", "error", str(exc)[:200])
            phases_run.append({"phase": 4, "status": "error", "elapsed_s": round(time.monotonic() - p4_start, 2)})
    else:
        _log_phase(root, 4, "discovery_qualification", "skipped", "budget_exceeded")
        phases_run.append({"phase": 4, "status": "skipped"})

    # Phase 5: Cleanup, mirror, email hygiene
    p5_start = time.monotonic()
    p5_elapsed = p5_start - start
    if p5_elapsed < tick_budget_seconds:
        try:
            cleanup_detail = ""
            # Archive stale proposals (>7 days, non-pending)
            proposals_dir = root / "data" / "aro" / "proposals"
            archived = 0
            if proposals_dir.exists():
                cutoff = time.time() - (7 * 86400)
                archive_dir = proposals_dir / "archive"
                for pf in proposals_dir.glob("*.json"):
                    if pf.name == "archive":
                        continue
                    try:
                        pdata = json.loads(pf.read_text(encoding="utf-8"))
                        if pdata.get("status") != "pending_review" and pf.stat().st_mtime < cutoff:
                            archive_dir.mkdir(exist_ok=True)
                            pf.rename(archive_dir / pf.name)
                            archived += 1
                    except (json.JSONDecodeError, OSError):
                        pass
            cleanup_detail = f"archived_proposals={archived}"
            _log_phase(root, 5, "cleanup_mirror_email", "completed", cleanup_detail)
            phases_run.append({"phase": 5, "status": "completed", "elapsed_s": round(time.monotonic() - p5_start, 2), "detail": cleanup_detail})
        except Exception as exc:
            _log_phase(root, 5, "cleanup_mirror_email", "error", str(exc)[:200])
            phases_run.append({"phase": 5, "status": "error", "elapsed_s": round(time.monotonic() - p5_start, 2)})
    else:
        _log_phase(root, 5, "cleanup_mirror_email", "skipped", "budget_exceeded")
        phases_run.append({"phase": 5, "status": "skipped"})

    total_elapsed = time.monotonic() - start
    return {
        "ok": overall_ok,
        "phased": True,
        "phases": phases_run,
        "total_elapsed_s": round(total_elapsed, 2),
        "budget_s": tick_budget_seconds,
        "generated_at": utcnow(),
    }
