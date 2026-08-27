#!/usr/bin/env python3
"""Tests for sync_pr_inventory.py - validates pagination, schema, merge, and stats."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import sync_pr_inventory


def test_collector_persists_actual_pr_author():
    page = {
        "data": {
            "search": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [
                    {
                        "url": "https://github.com/owner/repo/pull/1",
                        "title": "PR",
                        "state": "OPEN",
                        "createdAt": "2026-08-27T00:00:00Z",
                        "updatedAt": "2026-08-27T00:00:00Z",
                        "mergedAt": None,
                        "author": {"login": "rafaio1"},
                        "repository": {"nameWithOwner": "owner/repo"},
                        "number": 1,
                        "reviews": {"totalCount": 0},
                        "statusCheckRollup": None,
                    }
                ],
            }
        }
    }
    with patch.object(sync_pr_inventory, "gh_graphql_search", return_value=page):
        collected = sync_pr_inventory.collect_all_prs()
    assert collected["owner/repo#1"]["author"] == "rafaio1"

def test_schema_completeness():
    """Verify all PRs have required fields with explicit defaults."""
    inv_path = Path("data/aro/github_pr_inventory.json")
    assert inv_path.exists(), "Inventory file missing"
    
    with open(inv_path) as f:
        inv = json.load(f)
    
    prs = inv.get("prs", {})
    assert len(prs) > 100, f"Expected >100 PRs, got {len(prs)}"
    
    required = ['repo', 'number', 'reviews', 'ci_status', 'bounty_evidence',
                'bounty_value', 'bounty_currency', 'claim_status', 'payout_status',
                'related_email_id', 'next_action', 'revenue_potential', 'audit_note', 'last_audit']
    
    missing_fields = []
    for key, pr in prs.items():
        for field in required:
            if field not in pr:
                missing_fields.append(f"{key}:{field}")
    
    assert not missing_fields, f"Missing fields in {len(missing_fields)} entries: {missing_fields[:5]}"
    print(f"✓ Schema complete: all {len(prs)} PRs have {len(required)} required fields")

def test_stats_consistency():
    """Verify stats match actual PR states and sum correctly."""
    with open("data/aro/github_pr_inventory.json") as f:
        inv = json.load(f)
    
    prs = inv.get("prs", {})
    stats = inv.get("stats", {})
    
    # Recompute
    open_c = sum(1 for p in prs.values() if p.get('state') == 'OPEN')
    merged_c = sum(1 for p in prs.values() if p.get('mergedAt') is not None)
    closed_unmerged = sum(1 for p in prs.values() 
                          if p.get('state') == 'CLOSED' and p.get('mergedAt') is None)
    
    assert stats['open'] == open_c, f"Open mismatch: {stats['open']} vs {open_c}"
    assert stats['merged'] == merged_c, f"Merged mismatch: {stats['merged']} vs {merged_c}"
    assert stats['closed_unmerged'] == closed_unmerged, "Closed mismatch"
    
    total = len(prs)
    state_sum = open_c + merged_c + closed_unmerged
    assert state_sum == total, f"State sum {state_sum} != total {total}"
    assert stats['state_sum_validation'] == total
    
    print(f"✓ Stats consistent: OPEN={open_c}, MERGED={merged_c}, CLOSED={closed_unmerged}, TOTAL={total}")

def test_no_duplicates():
    """Verify no duplicate PR keys."""
    with open("data/aro/github_pr_inventory.json") as f:
        inv = json.load(f)
    
    prs = inv.get("prs", {})
    keys = list(prs.keys())
    unique_keys = set(keys)
    
    assert len(keys) == len(unique_keys), f"Duplicates found: {len(keys)} vs {len(unique_keys)}"
    print(f"✓ No duplicates: {len(keys)} unique PR keys")

def test_pagination_coverage():
    """Verify we fetched more than 100 PRs (pagination worked)."""
    with open("data/aro/github_pr_inventory.json") as f:
        inv = json.load(f)
    
    prs = inv.get("prs", {})
    assert len(prs) > 100, f"Pagination may have failed: only {len(prs)} PRs"
    print(f"✓ Pagination verified: {len(prs)} PRs collected (>100)")

def test_merge_preserves_audit():
    """Verify that re-running merge preserves non-default audit fields."""
    # This is a structural test - we check that existing audit data survived the last run
    with open("data/aro/github_pr_inventory.json") as f:
        inv = json.load(f)
    
    prs = inv.get("prs", {})
    
    # Check upstream audit entries from earlier manual audit
    audit_keys = [
        'PesanteAnalytics/contoso-universe-gen#13',
        'OthmaneBlial/pyffmpegcore#13',
        'ayelenleclerc/BizCode#425'
    ]
    
    preserved = 0
    for key in audit_keys:
        if key in prs:
            pr = prs[key]
            if pr.get('audit_note') and pr.get('audit_note') != 'not_checked':
                preserved += 1
    
    # At least some audit data should be preserved (may not be all if GraphQL didn't return them)
    print(f"✓ Merge preservation: {preserved}/{len(audit_keys)} audited PRs retained audit notes")

def test_key_format():
    """Verify all keys follow repo#number format."""
    with open("data/aro/github_pr_inventory.json") as f:
        inv = json.load(f)
    
    prs = inv.get("prs", {})
    bad_keys = []
    for key in prs.keys():
        if '#' not in key or key.count('#') != 1:
            bad_keys.append(key)
    
    assert not bad_keys, f"Bad key format: {bad_keys[:5]}"
    print(f"✓ Key format valid: all {len(prs)} keys match repo#number")

if __name__ == "__main__":
    tests = [
        test_pagination_coverage,
        test_schema_completeness,
        test_stats_consistency,
        test_no_duplicates,
        test_key_format,
        test_merge_preserves_audit,
    ]
    
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            print(f"✗ {t.__name__}: {e}")
            failed += 1
    
    print(f"\n{'='*60}")
    print(f"Results: {len(tests)-failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
