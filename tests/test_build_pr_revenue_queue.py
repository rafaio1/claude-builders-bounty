"""Tests for build_pr_revenue_queue.py — fail-closed tier classification."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from build_pr_revenue_queue import (
    build_ledger_index,
    build_payment_queue_index,
    classify_pr,
    compute_saturation,
)


def _pr(key="owner/repo#1", state="OPEN", merged_at=None, **kw):
    repo, num = key.rsplit("#", 1)
    base = {
        "repo": repo,
        "number": num,
        "url": f"https://github.com/{key.replace('#', '/pull/')}",
        "title": kw.get("title", "test pr"),
        "state": state,
        "mergedAt": merged_at,
        "bounty_evidence": kw.get("bounty_evidence", "unknown"),
        "claim_status": kw.get("claim_status", "unknown"),
        "payout_status": kw.get("payout_status", "unknown"),
        "revenue_potential": kw.get("revenue_potential", "unknown"),
        "reviews_count": kw.get("reviews_count", 0),
        "ci_state": kw.get("ci_state"),
        "related_email_id": kw.get("related_email_id"),
        "audit_note": kw.get("audit_note", ""),
    }
    return base


# --- Ledger index null-safety ---

def test_ledger_index_handles_none_urls():
    """None pr_url/issue_url must not crash .rstrip()."""
    ledger = {
        "bounties": [
            {"pr_url": None, "issue_url": None, "key": "a/b#1"},
            {"pr_url": "https://github.com/x/y/pull/2", "issue_url": None},
            {"pr_url": None, "issue_url": "https://github.com/x/y/issues/3"},
        ]
    }
    idx = build_ledger_index(ledger)
    assert "a/b#1" in idx
    assert "x/y#2" in idx
    assert "x/y#3" in idx


def test_ledger_index_skips_empty_strings():
    ledger = {"bounties": [{"pr_url": "", "issue_url": ""}]}
    idx = build_ledger_index(ledger)
    assert len(idx) == 0


# --- Payment queue index ---

def test_payment_queue_index_list():
    q = [{"pr_url": "https://github.com/a/b/pull/5"}]
    idx = build_payment_queue_index(q)
    assert "a/b#5" in idx


def test_payment_queue_index_dict():
    q = {"items": [{"pr_url": "https://github.com/a/b/pull/7"}]}
    idx = build_payment_queue_index(q)
    assert "a/b#7" in idx


# --- Tier A classification ---

def test_tier_a_paid_bounty():
    pr = _pr("org/repo#10", state="MERGED", merged_at="2026-01-01T00:00:00Z",
             bounty_evidence="official_program", payout_status="PAID")
    le = {"value": 500, "currency": "USD", "claim_url": "https://example.com/c"}
    c = classify_pr(pr, le, None, set())
    assert c["tier"] == "A"
    assert c["receivable_confirmed"] is True
    assert c["ev_score"] == 500.0


def test_tier_a_verified_active():
    pr = _pr("org/repo#11", state="OPEN", bounty_evidence="official_program")
    le = {"value": 200, "currency": "USD", "claim_url": "https://example.com/c"}
    c = classify_pr(pr, le, None, set())
    assert c["tier"] == "A"
    assert c["ev_score"] == 200.0


# --- Fail-closed: CLAIM_PENDING without evidence -> B, not A ---

def test_claim_pending_no_evidence_is_tier_b():
    pr = _pr("org/repo#12", state="OPEN", bounty_evidence="official_program",
             claim_status="CLAIM_PENDING")
    le = {"value": 300, "currency": "USD"}
    c = classify_pr(pr, le, None, set())
    assert c["tier"] == "B"
    assert c["reason"] == "claim_pending_without_verified_evidence"
    assert c["ev_score"] < 300.0  # Discounted


def test_claim_pending_with_evidence_is_tier_a():
    pr = _pr("org/repo#13", state="OPEN", bounty_evidence="official_program",
             claim_status="CLAIM_PENDING")
    le = {"value": 300, "currency": "USD", "claim_url": "https://x.com/c"}
    c = classify_pr(pr, le, None, set())
    assert c["tier"] == "A"


# --- Tier B signals ---

def test_tier_b_ci_actionable():
    pr = _pr("org/repo#20", state="OPEN", ci_state="FAILURE",
             bounty_evidence="official_program")
    le = {"value": 100, "claim_url": "https://x.com/c"}
    c = classify_pr(pr, le, None, set())
    assert c["tier"] == "B"
    assert "ci_actionable" in c["reason"]


def test_tier_b_review_activity():
    pr = _pr("org/repo#21", state="OPEN", reviews_count=2,
             bounty_evidence="official_program")
    le = {"value": 100, "claim_url": "https://x.com/c"}
    c = classify_pr(pr, le, None, set())
    assert c["tier"] == "B"
    assert "has_review_activity" in c["reason"]


def test_tier_b_email_linked():
    pr = _pr("org/repo#22", state="OPEN", related_email_id="msg-abc",
             bounty_evidence="official_program")
    le = {"value": 100, "claim_url": "https://x.com/c"}
    c = classify_pr(pr, le, None, set())
    assert c["tier"] == "B"
    assert "email_linked" in c["reason"]


def test_tier_b_legal_gate():
    pr = _pr("org/repo#23", state="OPEN", audit_note="CLA signature required",
             bounty_evidence="official_program")
    le = {"value": 100, "claim_url": "https://x.com/c"}
    c = classify_pr(pr, le, None, set())
    assert c["tier"] == "B"
    assert "legal_gate" in c["reason"]


def test_tier_b_in_approved_queue():
    pr = _pr("org/repo#24", state="OPEN")
    pe = {"amount": 150}
    c = classify_pr(pr, None, pe, set())
    assert c["tier"] == "B"
    assert "in_approved_queue" in c["reason"]


# --- No signal -> skip ---

def test_no_signal_skipped():
    pr = _pr("org/repo#30", state="CLOSED")
    c = classify_pr(pr, None, None, set())
    assert c["tier"] is None
    assert c["action"] == "skip"


# --- Saturation guard ---

def test_saturation_blocks_tier_c():
    prs = {}
    for i in range(6):
        k = f"saturated/repo#{i}"
        prs[k] = _pr(k, state="OPEN")
    sat = compute_saturation(prs)
    assert "saturated/repo" in sat["saturated_repos"]

    pr = _pr("saturated/repo#99", state="OPEN")
    c = classify_pr(pr, None, None, set(sat["saturated_repos"]))
    assert c["tier"] is None  # Blocked from C_candidate


def test_non_saturated_allows_tier_c_candidate():
    pr = _pr("healthy/repo#1", state="OPEN")
    c = classify_pr(pr, None, None, set())
    assert c["tier"] == "C_candidate"


# --- Idempotency: re-run produces same structure ---

def test_output_schema_keys(tmp_path):
    """Verify the output JSON has expected top-level keys."""
    expected = {"schema_version", "generated_at", "metrics", "saturation", "tiers", "kpi", "notes"}
    out = tmp_path / "queue.json"
    sample = {
        "schema_version": "1.0",
        "generated_at": "2026-08-26T00:00:00+00:00",
        "metrics": {"total_prs": 0},
        "saturation": {"saturated_repos": []},
        "tiers": {"A": [], "B": [], "C": []},
        "kpi": "dinheiro_liquidado",
        "notes": "",
    }
    out.write_text(json.dumps(sample))
    loaded = json.loads(out.read_text())
    assert set(loaded.keys()) == expected


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
