from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ProposalState(str, Enum):
    APPROVED = "APPROVED"
    PILOT = "PILOT"
    IMPLEMENTED = "IMPLEMENTED"
    REVOKED = "REVOKED"
    BLOCKED_SOURCE_UNVERIFIED = "BLOCKED_SOURCE_UNVERIFIED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    timestamp: str
    title: str
    category: str
    tier: str
    max_cost_usd: float
    evidence: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QueueItem:
    proposal_id: str
    state: ProposalState
    verdict: str
    verdict_ts: str
    title: Optional[str] = None
    category: Optional[str] = None
    implementation_status: Optional[str] = None
    blockers: List[str] = field(default_factory=list)
    last_updated: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "state": self.state.value,
            "verdict": self.verdict,
            "verdict_ts": self.verdict_ts,
            "title": self.title,
            "category": self.category,
            "implementation_status": self.implementation_status,
            "blockers": self.blockers,
            "last_updated": self.last_updated,
        }
