from __future__ import annotations

import json
import tempfile
from pathlib import Path

from agentic.expansion_executor.models import ProposalState
from agentic.expansion_executor.state_builder import build_queue


def _write_jsonl(path: Path, records: list) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_latest_verdict_wins_and_dedup():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        proposals = [
            {"proposal_id": "p1", "timestamp": "2026-08-26T10:00:00Z", "title": "A", "category": "c", "tier": "TIER_0", "max_cost_usd": 0},
        ]
        verdicts = [
            {"proposal_id": "p1", "timestamp": "2026-08-26T11:00:00Z", "verdict": "APROVAR_IMPLEMENTACAO"},
            {"proposal_id": "p1", "timestamp": "2026-08-26T12:00:00Z", "verdict": "REJEITAR"},
        ]
        _write_jsonl(p / "proposals.jsonl", proposals)
        _write_jsonl(p / "verdicts.jsonl", verdicts)
        queue = build_queue(str(p / "proposals.jsonl"), str(p / "verdicts.jsonl"))
        assert len(queue) == 1
        assert queue[0].state == ProposalState.FAILED
        assert queue[0].verdict == "REJEITAR"


def test_missing_proposal_blocks_approved():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        _write_jsonl(p / "proposals.jsonl", [])
        verdicts = [{"proposal_id": "ghost", "timestamp": "2026-08-26T12:00:00Z", "verdict": "APROVAR_IMPLEMENTACAO"}]
        _write_jsonl(p / "verdicts.jsonl", verdicts)
        queue = build_queue(str(p / "proposals.jsonl"), str(p / "verdicts.jsonl"))
        assert queue[0].state == ProposalState.BLOCKED_SOURCE_UNVERIFIED
        assert "proposal_not_found_in_source" in queue[0].blockers
        assert queue[0].title is None


def test_blockers_downgrade_actionable_states():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        proposals = [{"proposal_id": "p2", "timestamp": "2026-08-26T10:00:00Z", "title": "B", "category": "c", "tier": "TIER_0", "max_cost_usd": 10}]
        verdicts = [{"proposal_id": "p2", "timestamp": "2026-08-26T11:00:00Z", "verdict": "PILOTAR"}]
        _write_jsonl(p / "proposals.jsonl", proposals)
        _write_jsonl(p / "verdicts.jsonl", verdicts)
        queue = build_queue(str(p / "proposals.jsonl"), str(p / "verdicts.jsonl"))
        assert queue[0].state == ProposalState.BLOCKED_SOURCE_UNVERIFIED
        assert any("source_not_verified" in b for b in queue[0].blockers)
