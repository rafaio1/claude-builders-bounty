#!/usr/bin/env python3
"""Durable fail-closed repository quarantine for PR revenue classification."""

from copy import deepcopy


BLOCKED_SIGNALS = (
    "issue_label",
    "slash_attempt",
    "slash_claim",
    "pr_open",
    "pr_clean",
    "nominal_bounty",
)

# These policies are deliberately source-controlled. Reactivation requires a
# reviewed code/config change backed by evidence stronger than the signals above.
QUARANTINE_POLICIES = {
    "claude-builders-bounty/claude-builders-bounty": {
        "policy_id": "repo-quarantine-claude-builders-2026-08-27",
        "reason": "repo_quarantined_zero_merged_800_closed_stale_main",
        "detail": (
            "Zero merged PRs, 800 closed PRs, and default branch stale since "
            "2026-03-27; labels, slash commands, open/clean PR state, and nominal "
            "bounty values are not evidence of monetizable or receivable revenue."
        ),
        "evidence": {
            "observed_at": "2026-08-27",
            "merged_prs": 0,
            "closed_prs": 800,
            "default_branch_last_push": "2026-03-27",
        },
    },
    "ClankerNation/OpenAgents": {
        "policy_id": "repo-quarantine-openagents-2026-08-27",
        "reason": "repo_quarantined_zero_merged_1550_closed",
        "detail": (
            "Zero merged PRs and 1550 closed PRs; labels, slash commands, "
            "open/clean PR state, and nominal bounty values are not evidence of "
            "monetizable or receivable revenue."
        ),
        "evidence": {
            "observed_at": "2026-08-27",
            "merged_prs": 0,
            "closed_prs": 1550,
        },
    },
}

_POLICIES_BY_CASEFOLD = {
    repo.casefold(): (repo, policy) for repo, policy in QUARANTINE_POLICIES.items()
}


def quarantine_policy(repo):
    """Return the canonical repo and policy, case-insensitively, or None."""
    return _POLICIES_BY_CASEFOLD.get(str(repo or "").casefold())


def quarantine_pr(pr):
    """Build a zero-value historical queue record for a quarantined repo."""
    matched = quarantine_policy(pr.get("repo"))
    if matched is None:
        return None

    canonical_repo, policy = matched
    number = pr.get("number")
    merged = pr.get("mergedAt") is not None
    return {
        "key": f"{canonical_repo}#{number}",
        "url": pr.get("url"),
        "title": pr.get("title"),
        "state": pr.get("state", "UNKNOWN"),
        "merged": merged,
        "tier": None,
        "ev_score": 0.0,
        "monetizable_usd": 0.0,
        "monetizable": False,
        "receivable_confirmed": False,
        "reason": policy["reason"],
        "quarantine_reason": policy["detail"],
        "quarantine_policy_id": policy["policy_id"],
        "blocked_signals": list(BLOCKED_SIGNALS),
        "action": "quarantine_repository",
        "pr_author": pr.get("author"),
    }


def quarantine_manifest():
    """Return JSON-safe policy evidence without exposing mutable module state."""
    manifest = {}
    for repo, policy in QUARANTINE_POLICIES.items():
        item = deepcopy(policy)
        item["blocked_signals"] = list(BLOCKED_SIGNALS)
        item["monetizable_usd"] = 0.0
        item["receivable_confirmed"] = False
        item["requires_manual_reactivation"] = True
        item["source_records_preserved"] = True
        manifest[repo] = item
    return manifest


__all__ = [
    "BLOCKED_SIGNALS",
    "QUARANTINE_POLICIES",
    "quarantine_manifest",
    "quarantine_policy",
    "quarantine_pr",
]
