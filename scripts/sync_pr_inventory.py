#!/usr/bin/env python3
"""
Idempotent PR Inventory Collector for rafaio1
- Paginates GitHub GraphQL search (author:rafaio1 type:pr) fully
- Merges with existing inventory preserving history
- Enforces schema v2.0 with explicit unknown/not_checked defaults
- Outputs to data/aro/github_pr_inventory.json
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

INVENTORY_PATH = Path("data/aro/github_pr_inventory.json")
SCHEMA_VERSION = "2.0"
REQUIRED_FIELDS = {
    'repo': None,
    'number': None,
    'reviews': 'not_checked',
    'ci_status': 'not_checked',
    'bounty_evidence': 'unknown',
    'bounty_value': None,
    'bounty_currency': None,
    'claim_status': 'unknown',
    'payout_status': 'unknown',
    'related_email_id': None,
    'next_action': 'not_checked',
    'revenue_potential': 'unknown',
    'audit_note': None,
    'last_audit': None
}

def gh_graphql_search(cursor=None):
    """Execute one page of GitHub GraphQL search."""
    query = """
    query($cursor: String) {
      search(query: "author:rafaio1 type:pr", type: ISSUE, first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          ... on PullRequest {
            url title state createdAt updatedAt mergedAt
            repository { nameWithOwner }
            number
            reviews(first: 5) { totalCount }
            statusCheckRollup { state }
          }
        }
      }
    }
    """
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    if cursor:
        cmd += ["-f", f"cursor={cursor}"]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"GraphQL failed: {result.stderr}")
    return json.loads(result.stdout)

def collect_all_prs():
    """Paginate through all results."""
    all_prs = {}
    cursor = None
    page = 0
    
    while True:
        page += 1
        data = gh_graphql_search(cursor)
        search = data.get("data", {}).get("search", {})
        nodes = search.get("nodes", [])
        
        for node in nodes:
            repo = node["repository"]["nameWithOwner"]
            number = node["number"]
            key = f"{repo}#{number}"
            
            all_prs[key] = {
                'url': node["url"],
                'title': node["title"],
                'state': node["state"],
                'mergedAt': node.get("mergedAt"),
                'createdAt': node["createdAt"],
                'updatedAt': node["updatedAt"],
                'repo': repo,
                'number': number,
                'reviews_count': node.get("reviews", {}).get("totalCount"),
                'ci_state': node.get("statusCheckRollup", {}).get("state") if node.get("statusCheckRollup") else None,
                'linked_issues': []  # Can be enriched later
            }
        
        print(f"Page {page}: fetched {len(nodes)} PRs (total so far: {len(all_prs)})")
        
        page_info = search.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
    
    return all_prs

def merge_with_existing(new_prs):
    """Merge new data with existing inventory, preserving audit fields."""
    existing = {}
    if INVENTORY_PATH.exists():
        with open(INVENTORY_PATH) as f:
            inv = json.load(f)
            existing = inv.get("prs", {})
    
    merged = {}
    for key, pr in new_prs.items():
        if key in existing:
            # Preserve audit/bounty fields from existing
            old = existing[key]
            for field in REQUIRED_FIELDS:
                if field in old and old[field] not in (None, 'unknown', 'not_checked'):
                    pr[field] = old[field]
            # Keep linked_issues if new is empty
            if not pr.get('linked_issues') and old.get('linked_issues'):
                pr['linked_issues'] = old['linked_issues']
        merged[key] = pr
    
    # Preserve entries that no longer appear (deleted/transferred repos)
    for key, pr in existing.items():
        if key not in merged:
            pr['_archived'] = True
            merged[key] = pr
    
    return merged

def enforce_schema(prs_dict):
    """Ensure every PR has all required fields with explicit defaults."""
    for key, pr in prs_dict.items():
        # Parse repo/number from key if missing
        if not pr.get('repo') or not pr.get('number'):
            parts = key.split('#')
            if len(parts) == 2:
                pr['repo'] = parts[0]
                try:
                    pr['number'] = int(parts[1])
                except ValueError:
                    pr['number'] = parts[1]
        
        # Add missing fields
        for field, default in REQUIRED_FIELDS.items():
            if field not in pr:
                pr[field] = default

def compute_stats(prs_dict):
    """Compute validated stats."""
    total = len(prs_dict)
    open_c = sum(1 for p in prs_dict.values() if p.get('state') == 'OPEN')
    merged_c = sum(1 for p in prs_dict.values() if p.get('mergedAt') is not None)
    closed_unmerged = sum(1 for p in prs_dict.values() 
                          if p.get('state') == 'CLOSED' and p.get('mergedAt') is None)
    
    state_sum = open_c + merged_c + closed_unmerged
    assert state_sum == total, f"State sum {state_sum} != total {total}"
    
    return {
        'total_prs': total,
        'open': open_c,
        'closed_unmerged': closed_unmerged,
        'merged': merged_c,
        'state_sum_validation': state_sum,
        'generated_at': datetime.now(timezone.utc).isoformat()
    }

def main():
    print("Collecting PRs from GitHub GraphQL...")
    new_prs = collect_all_prs()
    
    print(f"Merging with existing inventory...")
    merged = merge_with_existing(new_prs)
    
    print("Enforcing schema v2.0...")
    enforce_schema(merged)
    
    stats = compute_stats(merged)
    
    output = {
        'schema_version': SCHEMA_VERSION,
        'schema_fields': list(REQUIRED_FIELDS.keys()) + ['url', 'title', 'state', 'mergedAt', 'createdAt', 'updatedAt', 'linked_issues'],
        'stats': stats,
        'prs': merged
    }
    
    INVENTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(INVENTORY_PATH, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(json.dumps(stats, indent=2))
    print(f"\nInventory saved to {INVENTORY_PATH}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
