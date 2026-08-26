"""Versioned catalog of locally verified implementations.

This module maps proposal_ids to their concrete local artifacts, services,
and health probes. The expansion_executor consults this catalog each cycle
to determine implementation_status without claiming revenue or external
authorization.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass(frozen=True)
class CatalogEntry:
    proposal_id: str
    code_path: str
    service_unit: str
    health_probe: str  # URL or command to verify causal liveness
    scope: str = "local_build_only"
    version: str = "1.0.0"
    required_files: List[str] = field(default_factory=list)

    def verify_artifacts(self) -> bool:
        """Check that all required files exist on disk."""
        for f in self.required_files:
            if not Path(f).exists():
                return False
        return True

    def verify_health(self) -> bool:
        """Run causal health probe (HTTP GET or systemctl is-active)."""
        try:
            if self.health_probe.startswith("http"):
                result = subprocess.run(
                    ["curl", "-sf", "--max-time", "3", self.health_probe],
                    capture_output=True, timeout=5,
                )
                return result.returncode == 0
            else:
                result = subprocess.run(
                    ["systemctl", "is-active", self.health_probe],
                    capture_output=True, text=True, timeout=5,
                )
                return result.stdout.strip() == "active"
        except Exception:
            return False


# Versioned catalog entries for implemented proposals
CATALOG: Dict[str, CatalogEntry] = {
    "exp-20260826-method-235-cron-job-service": CatalogEntry(
        proposal_id="exp-20260826-method-235-cron-job-service",
        code_path="revenue/products/utility_api/cron/scheduler.py",
        service_unit="agentic-utility-api.service",
        health_probe="http://127.0.0.1:8769/health",
        scope="local_build_only",
        version="1.0.0",
        required_files=[
            "revenue/products/utility_api/cron/scheduler.py",
            "revenue/products/utility_api/server.py",
        ],
    ),
    "exp-20260826-method-241-pdf-generator-api": CatalogEntry(
        proposal_id="exp-20260826-method-241-pdf-generator-api",
        code_path="revenue/products/utility_api/pdf/generator.py",
        service_unit="agentic-utility-api.service",
        health_probe="http://127.0.0.1:8769/health",
        scope="local_build_only",
        version="1.0.0",
        required_files=[
            "revenue/products/utility_api/pdf/generator.py",
            "revenue/products/utility_api/server.py",
        ],
    ),
    "exp-20260826-method-247-image-optimization-api": CatalogEntry(
        proposal_id="exp-20260826-method-247-image-optimization-api",
        code_path="revenue/products/utility_api/image/optimizer.py",
        service_unit="agentic-utility-api.service",
        health_probe="http://127.0.0.1:8769/health",
        scope="local_build_only",
        version="1.0.0",
        required_files=[
            "revenue/products/utility_api/image/optimizer.py",
            "revenue/products/utility_api/server.py",
        ],
    ),
}


def get_catalog_entry(proposal_id: str) -> Optional[CatalogEntry]:
    """Retrieve catalog entry by proposal_id."""
    return CATALOG.get(proposal_id)


def check_implementation_status(proposal_id: str) -> str:
    """Return IMPLEMENTED_LOCAL_VERIFIED, DEGRADED, or FAILED based on real probes."""
    entry = get_catalog_entry(proposal_id)
    if entry is None:
        return "NOT_IN_CATALOG"
    if not entry.verify_artifacts():
        return "FAILED"
    if not entry.verify_health():
        return "DEGRADED"
    return "IMPLEMENTED_LOCAL_VERIFIED"
