from __future__ import annotations

import fcntl
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .models import ProposalState, QueueItem
from .state_builder import build_queue
from .catalog import CATALOG, check_implementation_status

logger = logging.getLogger(__name__)


class ExpansionExecutor:
    """Idempotent executor for expansion proposals with lock and dry-run support."""

    def __init__(
        self,
        proposals_path: str,
        verdicts_path: str,
        state_output: str,
        queue_output: str,
        lock_path: str = "/tmp/expansion_executor.lock",
        max_per_cycle: int = 3,
        dry_run: bool = True,
    ) -> None:
        self.proposals_path = proposals_path
        self.verdicts_path = verdicts_path
        self.state_output = state_output
        self.queue_output = queue_output
        self.lock_path = lock_path
        self.max_per_cycle = max_per_cycle
        self.dry_run = dry_run

    def _acquire_lock(self):
        self._lock_fh = open(self.lock_path, "w")
        try:
            fcntl.flock(self._lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another executor instance is already running")

    def _release_lock(self):
        if hasattr(self, "_lock_fh"):
            try:
                fcntl.flock(self._lock_fh.fileno(), fcntl.LOCK_UN)
            finally:
                self._lock_fh.close()

    def _execute_item(self, item: QueueItem) -> Dict:
        result = {
            "proposal_id": item.proposal_id,
            "state": item.state.value,
            "dry_run": self.dry_run,
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "action": None,
            "error": None,
        }
        if item.blockers:
            result["action"] = "skipped_blocked"
            result["blockers"] = item.blockers
            return result
        if item.state == ProposalState.APPROVED:
            result["action"] = "queued_for_pilot" if not self.dry_run else "dry_run_queued_for_pilot"
        elif item.state == ProposalState.PILOT:
            result["action"] = "pilot_executed" if not self.dry_run else "dry_run_pilot"
        elif item.state == ProposalState.IMPLEMENTED:
            result["action"] = "verified_implementation" if not self.dry_run else "dry_run_verify"
        elif item.state in (ProposalState.REVOKED, ProposalState.FAILED, ProposalState.BLOCKED_SOURCE_UNVERIFIED):
            result["action"] = "no_op_terminal_state"
        else:
            result["action"] = "unknown_state"
        return result

    def run(self) -> Dict:
        self._acquire_lock()
        try:
            queue = build_queue(self.proposals_path, self.verdicts_path)
            executed: List[Dict] = []
            actionable = [
                i for i in queue
                if i.state in (ProposalState.APPROVED, ProposalState.PILOT, ProposalState.IMPLEMENTED)
                and not i.blockers
            ]
            for item in actionable[: self.max_per_cycle]:
                try:
                    result = self._execute_item(item)
                    executed.append(result)
                    logger.info("Executed %s: %s", item.proposal_id, result["action"])
                except Exception as exc:  # noqa: BLE001
                    executed.append({
                        "proposal_id": item.proposal_id,
                        "state": item.state.value,
                        "action": "error",
                        "error": str(exc),
                    })
                    logger.exception("Failed executing %s", item.proposal_id)
            summary = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "total_queue_size": len(queue),
                "actionable_count": len(actionable),
                "executed_this_cycle": len(executed),
                "max_per_cycle": self.max_per_cycle,
                "dry_run": self.dry_run,
                "build_implemented": sum(1 for i in queue if i.implementation_status == "IMPLEMENTED_LOCAL_VERIFIED"),
                "monetization_actionable": 0,
                "catalog_entries": len(CATALOG),
                "results": executed,
            }
            Path(self.state_output).parent.mkdir(parents=True, exist_ok=True)
            Path(self.queue_output).parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_output, "w", encoding="utf-8") as fh:
                json.dump(summary, fh, indent=2, ensure_ascii=False)
            with open(self.queue_output, "w", encoding="utf-8") as fh:
                for item in queue:
                    fh.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
            return summary
        finally:
            self._release_lock()
