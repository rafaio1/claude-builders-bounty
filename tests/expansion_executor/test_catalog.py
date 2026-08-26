from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from agentic.expansion_executor.catalog import (
    CATALOG,
    CatalogEntry,
    check_implementation_status,
)
from agentic.expansion_executor.models import ProposalState
from agentic.expansion_executor.state_builder import build_queue


def test_catalog_contains_required_proposals():
    required = [
        "exp-20260826-method-235-cron-job-service",
        "exp-20260826-method-241-pdf-generator-api",
        "exp-20260826-method-247-image-optimization-api",
    ]
    for pid in required:
        assert pid in CATALOG, f"Missing catalog entry for {pid}"
        entry = CATALOG[pid]
        assert entry.scope == "local_build_only"
        assert entry.service_unit == "agentic-utility-api.service"
        assert entry.health_probe.startswith("http://127.0.0.1")


def test_check_implementation_status_returns_failed_when_artifacts_missing():
    with patch.object(CatalogEntry, "verify_artifacts", return_value=False):
        status = check_implementation_status("exp-20260826-method-235-cron-job-service")
        assert status == "FAILED"


def test_check_implementation_status_returns_degraded_when_health_fails():
    with patch.object(CatalogEntry, "verify_artifacts", return_value=True), \
         patch.object(CatalogEntry, "verify_health", return_value=False):
        status = check_implementation_status("exp-20260826-method-241-pdf-generator-api")
        assert status == "DEGRADED"


def test_check_implementation_status_returns_verified_when_all_pass():
    with patch.object(CatalogEntry, "verify_artifacts", return_value=True), \
         patch.object(CatalogEntry, "verify_health", return_value=True):
        status = check_implementation_status("exp-20260826-method-247-image-optimization-api")
        assert status == "IMPLEMENTED_LOCAL_VERIFIED"


def test_state_builder_uses_catalog_for_implementation_status():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        proposals = [
            {"proposal_id": "exp-20260826-method-235-cron-job-service", "timestamp": "2026-08-26T10:00:00Z",
             "title": "Cron", "category": "infra", "tier": "TIER1", "max_cost_usd": 0},
        ]
        verdicts = [
            {"proposal_id": "exp-20260826-method-235-cron-job-service", "timestamp": "2026-08-26T12:00:00Z",
             "verdict": "PILOTAR", "source_official_verified": True, "terms_accepted": True,
             "account_dependency_cleared": True, "authorization_granted": True, "cost_verified": True},
        ]
        _write_jsonl(p / "proposals.jsonl", proposals)
        _write_jsonl(p / "verdicts.jsonl", verdicts)
        with patch("agentic.expansion_executor.state_builder.check_implementation_status", return_value="IMPLEMENTED_LOCAL_VERIFIED"):
            queue = build_queue(str(p / "proposals.jsonl"), str(p / "verdicts.jsonl"))
            assert len(queue) == 1
            assert queue[0].implementation_status == "IMPLEMENTED_LOCAL_VERIFIED"


def _write_jsonl(path: Path, records: list) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
