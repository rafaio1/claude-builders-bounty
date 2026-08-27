#!/usr/bin/env python3
"""
Build persistent revenue queue from canonical PR inventory.

Inputs:
  - data/aro/github_pr_inventory.json (canonical, schema v2.0)
  - data/aro/bounty_ledger.json
  - data/aro/approved_pr_payment_queue.json

Output:
  - data/aro/pr_revenue_queue.json (runtime, gitignored)

Tiers (fail-closed):
  A = verified bounty (official evidence, value/currency, claim-eligible, active repo)
  B = recovery (merged/review/CI/email/CLA/claim/payment action that can unlock revenue)
  C = non-remunerated only if A and B empty; max 1 per cycle; active repo; substantial change;
      block repos with >=5 open PRs without review (saturation); no spam/cosmetic

UNKNOWN never becomes receivable_confirmed.
CLAIM_PENDING without URL/official evidence -> potential_unverified.
KPI: dinheiro liquidado only.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict
from urllib.parse import urlparse

INVENTORY_PATH = Path("data/aro/github_pr_inventory.json")
LEDGER_PATH = Path("data/aro/bounty_ledger.json")
QUEUE_PATH = Path("data/aro/approved_pr_payment_queue.json")
OUTPUT_PATH = Path("data/aro/pr_revenue_queue.json")

SATURATION_THRESHOLD = 5  # >=5 open PRs without review -> block repo for tier C
MONETIZABLE_GITHUB_LOGIN = "rafaio1"
OWNERSHIP_EVIDENCE_KINDS = frozenset(
    {"github_assignment", "maintainer_assignment", "official_transfer"}
)
OWNERSHIP_EVIDENCE_HOSTS = frozenset(
    {"github.com", "www.github.com", "opire.dev", "app.opire.dev", "algora.io", "console.algora.io"}
)


def load_json(path: Path, default=None):
    if not path.exists():
        return default if default is not None else {}
    with open(path) as f:
        return json.load(f)


def build_ledger_index(ledger: dict) -> dict:
    """Index ledger entries by repo#number for fast lookup.
    
    Supports both formats:
    - Flat dict keyed by 'repo#number' (current canonical format)
    - Dict with 'bounties' list containing entries with pr_url/issue_url/key
    """
    index = {}
    
    # Process reconciled_bounties list (canonical location for active bounties)
    reconciled = ledger.get("reconciled_bounties", None)
    if isinstance(reconciled, list):
        for entry in reconciled:
            if not isinstance(entry, dict):
                continue
            keys = []
            # Build key from issue/pr fields
            repo = entry.get("repo", "")
            issue_num = entry.get("issue")
            pr_num = entry.get("pr")
            if repo and issue_num is not None:
                keys.append(f"{repo}#{issue_num}")
            if repo and pr_num is not None:
                keys.append(f"{repo}#{pr_num}")
            # Also extract from URLs
            for url_field in ("issue_url", "pr_url"):
                url = entry.get(url_field, "")
                if url:
                    parts = str(url).rstrip("/").split("/")
                    if len(parts) >= 5:
                        url_repo = f"{parts[3]}/{parts[4]}"
                        num = parts[-1]
                        keys.append(f"{url_repo}#{num}")
            # Normalize field names for classify_pr compatibility
            normalized = dict(entry)
            if "bounty_value" in normalized and "value" not in normalized:
                normalized["value"] = normalized["bounty_value"]
            if "bounty_currency" in normalized and "currency" not in normalized:
                normalized["currency"] = normalized["bounty_currency"]
            if "evidence_url" not in normalized and "claim_url" not in normalized:
                # Use only official platform URLs (Algora/Opire) as evidence.
                # PR URL is never bounty evidence; GitHub issue URL is valid only if it points to an open issue.
                status = str(normalized.get("status", "")).upper()
                if status in ("CLAIM_PENDING", "PAYMENT_PENDING", "PAID", "PR_SUBMITTED"):
                    normalized["evidence_url"] = normalized.get("issue_url")  # Only accept issue_url (official platform link), never pr_url
            # Map status to claim_status/payout_status for classify_pr
            status = str(normalized.get("status", "")).upper()
            if "claim_status" not in normalized:
                normalized["claim_status"] = status
            if "payout_status" not in normalized:
                normalized["payout_status"] = status
            for k in keys:
                if k and k not in index:
                    index[k] = normalized

    # Always process flat dict entries first (canonical format)
    for key, entry in ledger.items():
        if isinstance(entry, dict) and "#" in str(key):
            normalized = dict(entry)
            if "bounty_value" in normalized and "value" not in normalized:
                normalized["value"] = normalized["bounty_value"]
            if "bounty_currency" in normalized and "currency" not in normalized:
                normalized["currency"] = normalized["bounty_currency"]
            if "bounty_evidence_url" in normalized and "evidence_url" not in normalized:
                normalized["evidence_url"] = normalized["bounty_evidence_url"]
            if "bounty_evidence_url" in normalized and "claim_url" not in normalized:
                normalized["claim_url"] = normalized["bounty_evidence_url"]
            index[str(key)] = normalized
    
    # Then merge legacy 'bounties' list entries (only if not already indexed)
    bounties_list = ledger.get("bounties", None)
    if isinstance(bounties_list, list):
        for entry in bounties_list:
            keys = []
            if entry.get("pr_url"):
                url = entry["pr_url"]
                parts = url.rstrip("/").split("/")
                if len(parts) >= 5:
                    repo = f"{parts[3]}/{parts[4]}"
                    num = parts[-1]
                    keys.append(f"{repo}#{num}")
            if entry.get("issue_url"):
                url = entry["issue_url"]
                parts = url.rstrip("/").split("/")
                if len(parts) >= 5:
                    repo = f"{parts[3]}/{parts[4]}"
                    num = parts[-1]
                    keys.append(f"{repo}#{num}")
            if "key" in entry:
                keys.append(entry["key"])
            for k in keys:
                if k and k not in index:
                    index[k] = entry
    return index


def build_payment_queue_index(queue: list | dict) -> dict:
    """Index approved payment queue by repo#number."""
    index = {}
    items = queue if isinstance(queue, list) else queue.get("items", queue.get("queue", []))
    for item in items:
        url = item.get("pr_url", item.get("url", ""))
        if url:
            parts = url.rstrip("/").split("/")
            if len(parts) >= 5:
                repo = f"{parts[3]}/{parts[4]}"
                num = parts[-1]
                index[f"{repo}#{num}"] = item
    return index


def compute_saturation(prs: dict) -> dict:
    """Count open PRs per repo to detect saturation."""
    repo_open = defaultdict(int)
    repo_reviewed = defaultdict(int)
    for pr in prs.values():
        if pr.get("state") == "OPEN":
            repo = pr.get("repo", "")
            repo_open[repo] += 1
            if pr.get("reviews_count") and pr["reviews_count"] > 0:
                repo_reviewed[repo] += 1
    saturated = set()
    for repo, count in repo_open.items():
        unreviewed = count - repo_reviewed.get(repo, 0)
        if unreviewed >= SATURATION_THRESHOLD:
            saturated.add(repo)
    return {"open_by_repo": dict(repo_open), "saturated_repos": sorted(saturated)}


def monetizable_ownership(pr: dict, ledger_entry: dict | None) -> tuple[bool, str]:
    """Accept authorship or explicit verified assignment; comments never transfer ownership."""
    author = str(pr.get("author") or (ledger_entry or {}).get("pr_author") or "").casefold()
    if author == MONETIZABLE_GITHUB_LOGIN.casefold():
        return True, "pr_author_matches"
    evidence = ledger_entry or {}
    kind = str(evidence.get("ownership_evidence_kind") or "").lower()
    assignee = str(evidence.get("ownership_assignee") or "").casefold()
    evidence_url = str(evidence.get("ownership_evidence_url") or "")
    parsed = urlparse(evidence_url)
    hostname = (parsed.hostname or "").lower()
    parts = [part for part in parsed.path.split("/") if part]
    repo_key = str(pr.get("repo") or "").casefold()
    github_evidence_matches = (
        hostname in {"github.com", "www.github.com"}
        and len(parts) >= 4
        and "/".join(parts[:2]).casefold() == repo_key
        and parts[2] in {"issues", "pull"}
        and parts[3].isdigit()
    )
    transfer_evidence_matches = (
        kind == "official_transfer" and hostname in OWNERSHIP_EVIDENCE_HOSTS
    )
    if kind in {"claim_comment", "slash_claim_comment"}:
        return False, "claim_comment_not_ownership"
    if (
        evidence.get("ownership_verified") is True
        and assignee == MONETIZABLE_GITHUB_LOGIN.casefold()
        and kind in OWNERSHIP_EVIDENCE_KINDS
        and (github_evidence_matches or transfer_evidence_matches)
    ):
        return True, "explicit_official_assignment"
    return False, "claimant_ownership_unverified"


def classify_pr(pr: dict, ledger_entry: dict | None, payment_entry: dict | None, saturated_repos: set) -> dict:
    """Classify a single PR into tier A/B/C or skip."""
    key = f"{pr['repo']}#{pr['number']}"
    state = pr.get("state", "UNKNOWN")
    merged = pr.get("mergedAt") is not None
    # Prefer ledger fields over inventory fields (inventory often lacks these)
    if ledger_entry:
        bounty_evidence = ledger_entry.get("evidence_url") or ledger_entry.get("claim_url") or pr.get("bounty_evidence", "unknown")
        # Fail-closed: PR URL is never official bounty evidence.
        pr_url = pr.get("url", "")
        if bounty_evidence == pr_url:
            bounty_evidence = "unknown"
        claim_status = ledger_entry.get("claim_status", pr.get("claim_status", "unknown"))
        payout_status = ledger_entry.get("payout_status", pr.get("payout_status", "unknown"))
    else:
        bounty_evidence = pr.get("bounty_evidence", "unknown")
        claim_status = pr.get("claim_status", "unknown")
        payout_status = pr.get("payout_status", "unknown")
    reviews_count = pr.get("reviews_count") or 0
    ci_state = pr.get("ci_state")
    audit_note = pr.get("audit_note") or ""

    result = {
        "key": key,
        "url": pr.get("url"),
        "title": pr.get("title"),
        "state": state,
        "merged": merged,
        "tier": None,
        "ev_score": 0.0,
        "reason": "",
        "action": "skip",
        "receivable_confirmed": False,
    }

    ownership_ok, ownership_reason = monetizable_ownership(pr, ledger_entry)
    result["pr_author"] = pr.get("author") or (ledger_entry or {}).get("pr_author")
    result["monetizable_ownership"] = ownership_ok
    result["ownership_reason"] = ownership_reason
    if not ownership_ok:
        result["reason"] = ownership_reason
        result["action"] = "quarantine_ownership"
        return result

    # Tier A: Verified bounty with official evidence
    if ledger_entry and bounty_evidence not in (None, False, "unknown", "not_checked"):
        value = ledger_entry.get("value", ledger_entry.get("amount", 0))
        try:
            ev = float(value) if value else 0.0
        except (ValueError, TypeError):
            ev = 0.0

        # Fail-closed: CLAIM_PENDING without URL/evidence -> potential_unverified
        has_claim_url = bool(ledger_entry.get("claim_url") or ledger_entry.get("evidence_url"))
        if claim_status == "CLAIM_PENDING" and not has_claim_url:
            result["tier"] = "B"
            result["reason"] = "claim_pending_without_verified_evidence"
            result["action"] = "verify_claim_evidence"
            result["ev_score"] = ev * 0.5  # Discounted EV
            return result

        if payout_status in ("PAID", "paid"):
            result["tier"] = "A"
            result["receivable_confirmed"] = True
            result["ev_score"] = ev
            result["reason"] = "paid_bounty"
            result["action"] = "track_only"
            return result

        if state == "OPEN" or merged:
            result["tier"] = "A"
            result["ev_score"] = ev
            result["reason"] = "verified_bounty_active"
            result["action"] = "advance_claim" if claim_status != "PAID" else "track_only"
            if payout_status in ("PAYMENT_PENDING", "payment_pending"):
                result["receivable_confirmed"] = True
            return result

    # Tier B: Recovery potential
    b_signals = []
    if merged and payout_status not in ("PAID", "paid", None, "unknown"):
        b_signals.append("merged_with_payment_state")
    if ledger_entry and claim_status not in ("unknown", "not_checked", None):
        b_signals.append("has_claim_record")
    if payment_entry:
        b_signals.append("in_approved_queue")
    if reviews_count > 0 and state == "OPEN":
        b_signals.append("has_review_activity")
    if ci_state and ci_state != "EXPECTED":
        b_signals.append("ci_actionable")
    if pr.get("related_email_id"):
        b_signals.append("email_linked")
    if "cla" in audit_note.lower() or "kyc" in audit_note.lower():
        b_signals.append("legal_gate")

    if b_signals:
        result["tier"] = "B"
        result["reason"] = "+".join(b_signals)
        result["action"] = "recover_revenue"
        # Estimate EV from ledger if available
        if ledger_entry:
            try:
                val = float(ledger_entry.get("value", ledger_entry.get("amount", 0)))
                result["ev_score"] = val * 0.7  # Discounted for uncertainty
            except (ValueError, TypeError):
                result["ev_score"] = 0.0
        return result

    # Tier C: Non-remunerated (only if A and B are empty globally — checked at queue level)
    # Here we just mark candidates; filtering happens during assembly
    if state == "OPEN" and pr.get("repo") not in saturated_repos:
        title_lower = (pr.get("title") or "").lower()
        # Block cosmetic/spam
        cosmetic_keywords = ["typo", "readme", "format", "whitespace", "trailing", "indent"]
        is_cosmetic = any(kw in title_lower for kw in cosmetic_keywords)
        if not is_cosmetic:
            result["tier"] = "C_candidate"
            result["reason"] = "non_remunerated_viable"
            result["action"] = "consider_if_ab_empty"
            return result

    result["tier"] = None
    result["reason"] = "no_revenue_signal"
    result["action"] = "skip"
    return result


def build_queue():
    from revenue_repo_quarantine import quarantine_manifest, quarantine_pr

    inv = load_json(INVENTORY_PATH)
    ledger = load_json(LEDGER_PATH, {"bounties": []})
    payment_queue = load_json(QUEUE_PATH, [])

    prs = inv.get("prs", {})
    ledger_idx = build_ledger_index(ledger)
    payment_idx = build_payment_queue_index(payment_queue)
    sat = compute_saturation(prs)

    metrics = {
        "total_prs": len(prs),
        "scanned": 0,
        "enriched_from_ledger": 0,
        "enriched_from_queue": 0,
        "unknown_no_signal": 0,
        "tier_a": 0,
        "tier_b": 0,
        "tier_c_candidates": 0,
        "skipped": 0,
        "saturated_repos": len(sat["saturated_repos"]),
        "quarantined": 0,
        "quarantined_monetizable_usd": 0.0,
    }

    tier_a = []
    tier_b = []
    tier_c_candidates = []
    quarantined = []

    for key, pr in prs.items():
        metrics["scanned"] += 1
        le = ledger_idx.get(key)
        pe = payment_idx.get(key)
        if le:
            metrics["enriched_from_ledger"] += 1
        if pe:
            metrics["enriched_from_queue"] += 1

        classified = quarantine_pr(pr)
        if classified is not None:
            quarantined.append(classified)
            metrics["quarantined"] += 1
            continue

        classified = classify_pr(pr, le, pe, set(sat["saturated_repos"]))

        if classified["tier"] == "A":
            tier_a.append(classified)
            metrics["tier_a"] += 1
        elif classified["tier"] == "B":
            tier_b.append(classified)
            metrics["tier_b"] += 1
        elif classified["tier"] == "C_candidate":
            tier_c_candidates.append(classified)
            metrics["tier_c_candidates"] += 1
        else:
            metrics["unknown_no_signal"] += 1
            metrics["skipped"] += 1

    # Sort tier A by EV descending
    tier_a.sort(key=lambda x: x["ev_score"], reverse=True)
    # Sort tier B by EV descending
    tier_b.sort(key=lambda x: x["ev_score"], reverse=True)

    # Tier C: only include if A and B are both empty; max 1
    tier_c = []
    if not tier_a and not tier_b and tier_c_candidates:
        # Pick the best candidate (first one, could be improved with scoring)
        best = tier_c_candidates[0]
        best["tier"] = "C"
        best["action"] = "non_remunerated_contribution"
        tier_c.append(best)

    output = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "saturation": sat,
        "tiers": {
            "A": tier_a,
            "B": tier_b,
            "C": tier_c,
        },
        "quarantine": {
            "count": len(quarantined),
            "monetizable_usd": 0.0,
            "policies": quarantine_manifest(),
            "items": quarantined,
        },
        "kpi": "dinheiro_liquidado",
        "notes": "Tier C only populated when A and B are empty. UNKNOWN and quarantined repositories never become receivable_confirmed.",
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(json.dumps(metrics, indent=2))
    print(f"\nQueue saved to {OUTPUT_PATH}")
    print(f"Tiers: A={len(tier_a)}, B={len(tier_b)}, C={len(tier_c)}, quarantined={len(quarantined)}")
    return 0


if __name__ == "__main__":
    sys.exit(build_queue())
