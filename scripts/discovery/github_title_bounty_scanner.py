#!/usr/bin/env python3
"""
GitHub Title-Based Bounty Scanner
Finds bounties by title pattern ($NNN, bounty, reward) across all public repos.
Filters out known spam/low-value sources. Outputs to revenue/github_title_opportunities/.
"""
import json, os, subprocess, re, sys
from datetime import datetime, timezone

OUT_DIR = "/Agentic/revenue/github_title_opportunities"
LOG_PATH = "/Agentic/logs/github_title_bounty_scanner.log"
SPAM_REPOS = {"Scottcjn/rustchain-bounties", "relayhop/sn-monetization-runtime",
              "auscaster/frantic-board", "dev-kp-eloper/BountyScout",
              "freedom-winds/BountyScout", "vansh-09/BountyScout"}
MIN_AMOUNT = 50

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")

def extract_amount(title):
    m = re.search(r'\$(\d[\d,]*)', title)
    if m:
        return int(m.group(1).replace(',', ''))
    return None

def scan():
    os.makedirs(OUT_DIR, exist_ok=True)
    cmd = [
        "gh", "search", "issues", "bounty", "--state", "open",
        "--limit", "200", "--sort", "updated",
        "--json", "repository,title,url,createdAt"
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        log(f"gh search failed: {r.stderr}")
        return
    issues = json.loads(r.stdout)
    found = []
    for iss in issues:
        repo = iss.get("repository", {}).get("nameWithOwner", "")
        title = iss.get("title", "")
        url = iss.get("url", "")
        if repo in SPAM_REPOS:
            continue
        amt = extract_amount(title)
        if amt is None or amt < MIN_AMOUNT:
            continue
        entry = {
            "source": "github_title_scan",
            "platform": "github_direct",
            "repo": repo,
            "title": title,
            "url": url,
            "amount_usd": amt,
            "currency": "USD",
            "asset": "USDC",
            "discovered_at": datetime.now(timezone.utc).isoformat(),
            "status": "new",
            "human_gates": {"identity": False, "kyc": False},
            "autonomy_qualified": True,
            "claim_type": "pr_based"
        }
        fname = re.sub(r'[^a-zA-Z0-9_-]', '_', f"{repo.replace('/', '_')}_{iss.get('url','').split('/')[-1]}")
        out_path = os.path.join(OUT_DIR, f"{fname}.json")
        with open(out_path, "w") as f:
            json.dump(entry, f, indent=2)
        found.append(entry)
    log(f"Scan complete: {len(found)} opportunities written to {OUT_DIR}")
    return found

if __name__ == "__main__":
    scan()
