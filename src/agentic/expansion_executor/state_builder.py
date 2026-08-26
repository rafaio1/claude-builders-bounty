from __future__ import annotations

from typing import Dict, List, Optional

from .loader import latest_verdict, load_proposals, load_verdicts
from .models import Proposal, ProposalState, QueueItem

VERDICT_STATE_MAP = {
    "APROVAR_IMPLEMENTACAO": ProposalState.APPROVED,
    "PILOTAR": ProposalState.PILOT,
    "PILOTAR_AUTOMATICO_INICIADO": ProposalState.PILOT,
    "PILOTAR_CICLO2_OK": ProposalState.PILOT,
    "PILOTAR_CICLO3_OK_COM_OBS": ProposalState.PILOT,
    "IMPLEMENTADO_PARCIAL": ProposalState.IMPLEMENTED,
    "REVOGADO_PARCIAL": ProposalState.REVOKED,
    "REVOGADO_PILOTO_FALHOU": ProposalState.REVOKED,
    "REVOGADO_PARCIAL_PILOTO_FALHOU": ProposalState.REVOKED,
    "REJEITAR": ProposalState.FAILED,
    "ADIAR": ProposalState.BLOCKED_SOURCE_UNVERIFIED,
}


def _resolve_state(verdict: str) -> ProposalState:
    if not verdict:
        return ProposalState.BLOCKED_SOURCE_UNVERIFIED
    mapped = VERDICT_STATE_MAP.get(verdict)
    if mapped is not None:
        return mapped
    upper = verdict.upper()
    if "REVOG" in upper or "FALHOU" in upper:
        return ProposalState.REVOKED
    if "PILOT" in upper:
        return ProposalState.PILOT
    if "IMPLEMENT" in upper:
        return ProposalState.IMPLEMENTED
    if "APROV" in upper:
        return ProposalState.APPROVED
    if "REJEIT" in upper:
        return ProposalState.FAILED
    return ProposalState.BLOCKED_SOURCE_UNVERIFIED


def build_queue(proposals_path: str, verdicts_path: str) -> List[QueueItem]:
    proposals = load_proposals(__import__("pathlib").Path(proposals_path))
    verdicts = load_verdicts(__import__("pathlib").Path(verdicts_path))
    latest = latest_verdict(verdicts)
    items: List[QueueItem] = []
    for pid, verdict in latest.items():
        proposal: Optional[Proposal] = proposals.get(pid)
        state = _resolve_state(verdict.get("verdict") or "")
        blockers: List[str] = []
        if proposal is None:
            blockers.append("proposal_not_found_in_source")
            if state == ProposalState.APPROVED:
                state = ProposalState.BLOCKED_SOURCE_UNVERIFIED
        else:
            if proposal.max_cost_usd > 0 and not verdict.get("cost_verified"):
                blockers.append("cost_not_verified")
            if not verdict.get("terms_accepted"):
                blockers.append("terms_not_accepted")
            if not verdict.get("account_dependency_cleared"):
                blockers.append("account_dependency_pending")
            if not verdict.get("authorization_granted"):
                blockers.append("authorization_missing")
            if not verdict.get("source_official_verified"):
                blockers.append("source_not_verified")
            if blockers and state in (ProposalState.APPROVED, ProposalState.PILOT, ProposalState.IMPLEMENTED):
                state = ProposalState.BLOCKED_SOURCE_UNVERIFIED
        item = QueueItem(
            proposal_id=pid,
            state=state,
            verdict=verdict.get("verdict") or "",
            verdict_ts=verdict.get("timestamp") or "",
            title=proposal.title if proposal else None,
            category=proposal.category if proposal else None,
            implementation_status=verdict.get("implementation_status"),
            blockers=blockers,
        )
        items.append(item)
    items.sort(key=lambda i: (i.state.value, i.verdict_ts), reverse=True)
    return items
