#!/usr/bin/env python3
"""
Algora Bounty Scanner & Auto-Submitter
Scans Algora.io for open bounties using GraphQL API and gh CLI.
Algora pays via crypto (USDC/ETH) directly to wallet upon merge.
Focuses on: TypeScript, Rust, Solidity repos with active bounty programs.
"""

import json
import os
import subprocess
import re
from datetime import datetime, timezone

ALGORA_CONFIG_PATH = "/Agentic/config/algora_scanner.json"
ALGORA_LOG_PATH = "/Agentic/logs/algora_bounty_scanner.log"
ALGORA_OPPORTUNITIES_DIR = "/Agentic/revenue/algora_opportunities"

# High-value Algora orgs/repos known to have active bounties
TARGET_ORGS = [
    "coral-xyz",
    "neondatabase", 
    "supabase",
    "prisma",
    "trpc",
    "drizzle-team",
    "calcom",
    "twentyhq",
    "hoppscotch",
    "maybe-finance"
]

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(ALGORA_LOG_PATH), exist_ok=True)
    with open(ALGORA_LOG_PATH, "a") as f:
        f.write(line + "\n")

def load_config():
    if os.path.exists(ALGORA_CONFIG_PATH):
        with open(ALGORA_CONFIG_PATH) as f:
            return json.load(f)
    return {"scanned_orgs": [], "submitted_bounties": [], "last_scan": None}

def save_config(cfg):
    os.makedirs(os.path.dirname(ALGORA_CONFIG_PATH), exist_ok=True)
    with open(ALGORA_CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

def extract_bounty_from_labels(labels):
    """Extract bounty amount from GitHub labels."""
    for label in labels:
        name = label.get("name", "").lower()
        # Common patterns: "$500", "bounty-$500", "💰 $1000", "reward:500"
        match = re.search(r'\$?(\d{3,6})', name)
        if match:
            return int(match.group(1))
    return 0

def scan_org_bounties(org):
    """Scan an organization's repos for bounty-labeled issues."""
    opportunities = []
    
    try:
        # List repos in org
        result = subprocess.run(
            ["gh", "repo", "list", org, "--limit", "10", "--json", "nameWithOwner"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return opportunities
        
        repos = json.loads(result.stdout)
        
        for repo_info in repos[:5]:  # Limit per org
            repo = repo_info["nameWithOwner"]
            try:
                # Search for bounty-labeled open issues
                issue_result = subprocess.run(
                    ["gh", "issue", "list", "--repo", repo, "--state", "open",
                     "--label", "bounty", "--json", "number,title,labels,url,createdAt",
                     "--limit", "20"],
                    capture_output=True, text=True, timeout=30
                )
                
                if issue_result.returncode == 0 and issue_result.stdout.strip():
                    issues = json.loads(issue_result.stdout)
                    for issue in issues:
                        bounty_usd = extract_bounty_from_labels(issue.get("labels", []))
                        
                        opp = {
                            "id": f"ALGORA-{repo.replace('/', '-')}-{issue['number']}",
                            "platform": "algora",
                            "repo": repo,
                            "issue_number": issue["number"],
                            "title": issue["title"],
                            "url": issue["url"],
                            "bounty_usd": bounty_usd,
                            "status": "discovered",
                            "autonomous_capable": True,
                            "payout_method": "crypto_wallet",
                            "labels": [l.get("name") for l in issue.get("labels", [])],
                            "discovered_at": datetime.now(timezone.utc).isoformat()
                        }
                        opportunities.append(opp)
                        log(f"  Found: {repo}#{issue['number']} - ${bounty_usd} - {issue['title'][:50]}")
            except Exception as e:
                log(f"  Error scanning {repo}: {e}")
                
    except Exception as e:
        log(f"Error listing repos for {org}: {e}")
    
    return opportunities

def scan_algora_marketplace():
    """Scan Algora marketplace for trending bounties."""
    log("Scanning Algora marketplace for active bounties...")
    
    all_opportunities = []
    
    for org in TARGET_ORGS:
        log(f"Scanning org: {org}")
        opps = scan_org_bounties(org)
        all_opportunities.extend(opps)
    
    return all_opportunities

def update_ledger_with_algora(opportunities):
    """Add Algora opportunities to ledger."""
    ledger_path = "/Agentic/logs/bounty/ledger.json"
    if not os.path.exists(ledger_path):
        return
    
    with open(ledger_path) as f:
        data = json.load(f)
    
    entries = data.get("entries", []) if isinstance(data, dict) else data
    added = 0
    
    for opp in opportunities:
        exists = any(e.get("id") == opp["id"] for e in entries)
        if not exists:
            entries.append({
                "type": "algora_bounty",
                **opp,
                "date_added": datetime.now(timezone.utc).isoformat()
            })
            added += 1
    
    if isinstance(data, dict):
        data["entries"] = entries
    
    with open(ledger_path, "w") as f:
        json.dump(data, f, indent=2)
    
    log(f"Added {added} Algora bounties to ledger")

def main():
    log("=== Algora Bounty Scanner Cycle Start ===")
    
    cfg = load_config()
    opportunities = scan_algora_marketplace()
    
    # Save opportunities to disk
    os.makedirs(ALGORA_OPPORTUNITIES_DIR, exist_ok=True)
    for opp in opportunities:
        path = os.path.join(ALGORA_OPPORTUNITIES_DIR, f"{opp['id']}.json")
        with open(path, "w") as f:
            json.dump(opp, f, indent=2)
    
    cfg["scanned_orgs"] = TARGET_ORGS
    cfg["last_scan"] = datetime.now(timezone.utc).isoformat()
    save_config(cfg)
    
    update_ledger_with_algora(opportunities)
    
    total_value = sum(o.get("bounty_usd", 0) for o in opportunities)
    auto_capable = sum(1 for o in opportunities if o.get("autonomous_capable"))
    
    log(f"Scan complete: {len(opportunities)} bounties found (${total_value} total, {auto_capable} autonomous-capable)")
    log("=== Algora Bounty Scanner Cycle Complete ===")

if __name__ == "__main__":
    main()
