#!/usr/bin/env python3
"""Post-rate-limit-reset batch checker. Run after 12:15 UTC."""
import subprocess, json, sys, time
from datetime import datetime, timezone

TARGET_PRS = [
    # High priority: SBL bounty candidates
    ('SecureBananaLabs/bug-bounty', 12147),
    ('SecureBananaLabs/bug-bounty', 12128),
    # Closed PRs to verify merge status
    ('IntersectMBO/govtool', None),  # Will search by author
    ('relayhop/ClaudeEarnSelf-runtime', None),
]

def check_pr_merged(owner, repo, number):
    try:
        r = subprocess.run(
            ['gh', 'api', f'/repos/{owner}/{repo}/pulls/{number}', '--jq', '.merged'],
            capture_output=True, text=True, timeout=15
        )
        if r.returncode == 0:
            return r.stdout.strip() == 'true'
        return None
    except:
        return None

def search_author_prs(owner, repo, author='rafaio1'):
    try:
        q = f'repo:{owner}/{repo} is:pr author:{author}'
        r = subprocess.run(
            ['gh', 'search', 'prs', q, '--json', 'number,state,title,updatedAt', '--limit', '50'],
            capture_output=True, text=True, timeout=20
        )
        if r.returncode == 0:
            return json.loads(r.stdout)
        return []
    except:
        return []

results = {'checked_at': datetime.now(timezone.utc).isoformat(), 'prs': [], 'searches': []}

# Check specific PRs
for owner, repo, number in TARGET_PRS:
    if number:
        merged = check_pr_merged(owner, repo, number)
        results['prs'].append({'owner': owner, 'repo': repo, 'number': number, 'merged': merged})
        print(f'{owner}/{repo}#{number}: merged={merged}')
        time.sleep(1)  # Rate limit courtesy

# Search closed PRs by author in key repos
for owner, repo, _ in TARGET_PRS:
    prs = search_author_prs(owner, repo)
    results['searches'].append({'owner': owner, 'repo': repo, 'count': len(prs), 'prs': prs[:10]})
    print(f'{owner}/{repo}: found {len(prs)} PRs by rafaio1')
    time.sleep(2)

with open('/Agentic/data/aro/post_reset_check.json', 'w') as f:
    json.dump(results, f, indent=2)

print('POST_RESET_CHECK_COMPLETE')
