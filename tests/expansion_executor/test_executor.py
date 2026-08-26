from __future__ import annotations

import json
import tempfile
from pathlib import Path

from agentic.expansion_executor.executor import ExpansionExecutor


def _write_jsonl(path: Path, records: list) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_executor_dry_run_respects_limit_and_lock():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        proposals = [
            {"proposal_id": f"p{i}", "timestamp": "2026-08-26T10:00:00Z", "title": f"T{i}", "category": "c", "tier": "TIER_0", "max_cost_usd": 0}
            for i in range(5)
        ]
        verdicts = [
            {"proposal_id": f"p{i}", "timestamp": "2026-08-26T11:00:00Z", "verdict": "APROVAR_IMPLEMENTACAO", "source_official_verified": True, "terms_accepted": True, "cost_verified": True, "account_dependency_cleared": True, "authorization_granted": True}
            for i in range(5)
        ]
        _write_jsonl(p / "proposals.jsonl", proposals)
        _write_jsonl(p / "verdicts.jsonl", verdicts)
        executor = ExpansionExecutor(
            proposals_path=str(p / "proposals.jsonl"),
            verdicts_path=str(p / "verdicts.jsonl"),
            state_output=str(p / "state.json"),
            queue_output=str(p / "queue.jsonl"),
            lock_path=str(p / "exec.lock"),
            max_per_cycle=2,
            dry_run=True,
        )
        summary = executor.run()
        assert summary["executed_this_cycle"] <= 2
        assert summary["dry_run"] is True
        assert Path(p / "state.json").exists()
        assert Path(p / "queue.jsonl").exists()
