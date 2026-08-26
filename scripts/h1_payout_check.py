import requests, json, os, sys, time
from pathlib import Path
sys.path.insert(0, '/Agentic/build/lib')
from agentic.aro.store import append_jsonl

ROOT = Path('/Agentic')

# Load HackerOne credentials
env_path = Path('/root/BugHunter/.env')
env_vars = {}
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            env_vars[k.strip()] = v.strip()

h1_user = env_vars.get('HACKERONE_API_USERNAME')
h1_token = env_vars.get('HACKERONE_API_TOKEN')

if not h1_user or not h1_token:
    print("HackerOne credentials not found.")
    sys.exit(1)

print(f"=== HACKERONE PAYOUT STATUS CHECK ===")
print(f"User: {h1_user}")

# Query HackerOne API for reports submitted by this user
url = "https://api.hackerone.com/v1/reports"
params = {
    "filter": {
        "reporter": h1_user,
        "state": ["new", "triaged", "needs-more-info", "resolved", "not-applicable", "informative", "duplicate", "spam"]
    },
    "sort": "created_at:descending",
    "size": 50
}

try:
    resp = requests.get(url, auth=(h1_user, h1_token), params={"filter[reporter]": h1_user, "sort": "created_at:descending", "size": 50}, timeout=30)
    if resp.status_code == 200:
        data = resp.json()
        reports = data.get('data', [])
        print(f"Found {len(reports)} reports.")
        
        total_bounty_awarded = 0.0
        total_bounty_pending = 0.0
        active_reports = 0
        
        for r in reports:
            attrs = r.get('attributes', {})
            state = attrs.get('state')
            title = attrs.get('title', 'No Title')
            severity = attrs.get('severity_rating')
            
            # Check for bounty awards
            bounty_awarded = float(attrs.get('bounty_awarded_amount', 0) or 0)
            # HackerOne doesn't always expose pending bounty directly in basic list, 
            # but we can check if it's triaged/resolved in a bounty program
            
            print(f"  [{state.upper()}] {title[:60]} | Severity: {severity} | Awarded: ${bounty_awarded}")
            
            if state in ['triaged', 'new', 'needs-more-info']:
                active_reports += 1
                
            total_bounty_awarded += bounty_awarded
            
        print(f"\n=== PAYOUT SUMMARY ===")
        print(f"Active/Open Reports: {active_reports}")
        print(f"Total Bounty Awarded (Historical): ${total_bounty_awarded:,.2f}")
        print(f"Note: Pending bounties are not directly exposed via list API, but active reports in bounty programs represent the pipeline.")
        
        append_jsonl(ROOT, 'ledger.jsonl', {
            'kind': 'hackerone_payout_check',
            'active_reports': str(active_reports),
            'total_awarded_usd': str(total_bounty_awarded),
            'strategy': 'monitoring_h1_for_capital_injection',
            'live': True
        })
    else:
        print(f"H1 API Error: {resp.status_code} - {resp.text[:200]}")
except Exception as e:
    print(f"Error querying H1: {e}")
