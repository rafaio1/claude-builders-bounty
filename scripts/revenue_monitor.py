#!/usr/bin/env python3
"""Autonomous Revenue Recovery & Bounty Monitor v2.0 - Full implementation"""
import sys, os, json, time, re, base64, subprocess, requests, shutil, tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/Agentic")
LOG = ROOT / "logs" / "revenue_monitor.log"
LEDGER = ROOT / "data" / "aro" / "bounty_ledger.json"
ENV_FILE = ROOT / ".env"
WORKSPACE = ROOT / "workspace" / "rework"

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def load_env():
    env = {}
    if ENV_FILE.exists():
        for line in open(ENV_FILE):
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                env[k] = v
    return env

def get_gmail_token(env):
    resp = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": env["GOOGLE_CLIENT_ID"],
        "client_secret": env["GOOGLE_CLIENT_SECRET"],
        "refresh_token": env["GOOGLE_REFRESH_TOKEN"],
        "grant_type": "refresh_token"
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]

def scan_gmail(token):
    headers = {"Authorization": f"Bearer {token}"}
    query = '(merged OR payment OR reward OR rework OR rejected OR invoice OR "payout" OR "transfer completed") after:2026-08-20 -from:grammarly -from:newsletter -subject:"Heavy Hitters"'
    try:
        msgs = requests.get("https://gmail.googleapis.com/gmail/v1/users/me/messages",
            params={"q": query, "maxResults": 30}, headers=headers, timeout=15).json().get("messages", [])
    except Exception as e:
        log(f"Gmail search error: {e}")
        return []
    results = []
    for m in msgs:
        try:
            detail = requests.get(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{m['id']}",
                params={"format": "metadata", "metadataHeaders": ["Subject","From","Date"]},
                headers=headers, timeout=10).json()
            hdrs = {h["name"]: h["value"] for h in detail.get("payload",{}).get("headers",[])}
            frm = hdrs.get("From","").lower()
            if any(x in frm for x in ["grammarly","newsletter","agentmail","embark.email"]):
                continue
            results.append({"subject": hdrs.get("Subject",""), "from": hdrs.get("From",""),
                            "date": hdrs.get("Date",""), "id": m["id"]})
        except Exception as e:
            log(f"  Gmail msg fetch error: {e}")
    return results

def audit_github_prs():
    try:
        out = subprocess.run(["gh","pr","list","--author","rafaio1","--state","all",
            "--limit","100","--json","headRepositoryOwner,number,title,state,mergedAt,url,closedAt"],
            capture_output=True, text=True, timeout=30)
        if out.returncode != 0:
            log(f"GH PR list failed: {out.stderr[:200]}")
            return [], [], []
        data = json.loads(out.stdout)
        merged = [p for p in data if p.get("mergedAt")]
        opened = [p for p in data if p["state"] == "OPEN"]
        closed = [p for p in data if p["state"] == "CLOSED" and not p.get("mergedAt")]
        return merged, opened, closed
    except Exception as e:
        log(f"GH audit error: {e}")
        return [], [], []

def reconcile_ledger(merged_prs):
    ledger = {}
    if LEDGER.exists():
        try: ledger = json.loads(LEDGER.read_text())
        except: pass
    bounties = ledger.get("bounties", [])
    merged_urls = {p["url"] for p in merged_prs}
    updated = False
    for b in bounties:
        pr_url = b.get("pr_url","")
        if pr_url in merged_urls and b.get("status") != "merged":
            b["status"] = "merged"
            b["merged_at"] = datetime.now(timezone.utc).isoformat()
            log(f"BOUNTY MERGED: {b.get('title','?')} ${b.get('bounty_value',0)} -> {pr_url}")
            # Trigger Wise transfer for merged bounty
            try:
                wise_state_path = ROOT / "data" / "aro" / "wise-state.json"
                ws = {}
                if wise_state_path.exists():
                    ws = json.loads(wise_state_path.read_text())
                pending = ws.get("pending_transfers", [])
                val = b.get("bounty_value", 0)
                if val > 0 and pr_url not in [t.get("source_pr") for t in pending]:
                    pending.append({
                        "source_pr": pr_url,
                        "amount_usd": val,
                        "status": "awaiting_payout_confirmation",
                        "detected_at": datetime.now(timezone.utc).isoformat(),
                        "note": f"Merged bounty: {b.get('title','?')}"
                    })
                    ws["pending_transfers"] = pending
                    ws["updated_at"] = datetime.now(timezone.utc).isoformat()
                    wise_state_path.write_text(json.dumps(ws, indent=2, default=str))
                    log(f"WISE TRANSFER QUEUED: ${val} from {pr_url}")
                    # Execute real transfer if credentials available
                    try:
                        import sys
                        sys.path.insert(0, str(ROOT / "revenue" / "wallet-integration"))
                        from wise_bybit_connector import WiseConnector
                        wc = WiseConnector()
                        recipient_id = os.environ.get("WISE_RECIPIENT_ID", "")
                        if wc.connected and recipient_id:
                            result = wc.bridge_crypto_to_wise(val, reference=f"bounty-{pr_url.split('/')[-1]}")
                            if result.get("status") == "success":
                                b["payout_status"] = "transferred"
                                b["wise_transfer_id"] = result.get("transfer_id")
                                log(f"WISE TRANSFER EXECUTED: ${val} -> transfer_id={result['transfer_id']}")
                            elif result.get("status") == "manual_required":
                                log(f"WISE TRANSFER NEEDS MANUAL ACTION: {result.get('message')}")
                                log(f"  -> Complete at: {result.get('action_url', 'wise.com')}")
                                b["payout_status"] = "manual_required"
                                b["wise_quote_id"] = result.get("quote_id")
                            else:
                                log(f"WISE TRANSFER FAILED: {result.get('message','unknown')}")
                    except Exception as te:
                        log(f"Warning: could not execute Wise transfer: {te}")
            except Exception as we:
                log(f"Warning: could not queue Wise transfer: {we}")
            updated = True
    if updated:
        LEDGER.write_text(json.dumps(ledger, indent=2, default=str))
    return bounties

def scrape_bounty_platforms():
    """Check bounty platforms with fallback to web scraping and GitHub GraphQL"""
    found = []
    
    # Opire - API is 404, fallback to web scraping user profile
    try:
        resp = requests.get("https://opire.dev/dev/rafaio1", timeout=15,
            headers={"User-Agent": "RevenueMonitor/2.0"})
        if resp.status_code == 200:
            # Extract bounty links from HTML profile page
            import re
            links = re.findall(r'href="(/bounty/[^"]+)"', resp.text)
            log(f"  PLATFORM [opire]: scraped {len(links)} bounty links from profile")
            for link in links[:10]:
                found.append({"platform": "opire", "url": f"https://opire.dev{link}", "status": "scraped"})
        else:
            log(f"  PLATFORM [opire]: HTTP {resp.status_code}")
    except Exception as e:
        log(f"  PLATFORM [opire]: error {e}")
    
    # Algora - console.algora.io returns HTML, use GraphQL or search
    try:
        resp = requests.get("https://console.algora.io/search?q=rafaio1&type=bounties", timeout=15,
            headers={"User-Agent": "RevenueMonitor/2.0"})
        if resp.status_code == 200:
            import re
            links = re.findall(r'href="(/bounties/[^"]+)"', resp.text)
            log(f"  PLATFORM [algora]: scraped {len(links)} bounty links")
            for link in links[:10]:
                found.append({"platform": "algora", "url": f"https://console.algora.io{link}", "status": "scraped"})
        else:
            log(f"  PLATFORM [algora]: HTTP {resp.status_code}")
    except Exception as e:
        log(f"  PLATFORM [algora]: error {e}")
        
    # GitHub GraphQL for fresh bounty issues across tracked orgs
    try:
        import subprocess
        result = subprocess.run(
            ["gh", "search", "issues", "label:bounty", "state:open", "--limit=20", "--json=repository,number,title,url"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            gh_bounties = json.loads(result.stdout)
            log(f"  PLATFORM [github]: found {len(gh_bounties)} open bounty issues")
            for b in gh_bounties:
                found.append({"platform": "github", "repo": b.get("repository",{}).get("nameWithOwner"), 
                             "issue": b.get("number"), "title": b.get("title"), "url": b.get("url")})
    except Exception as e:
        log(f"  PLATFORM [github]: search error {e}")
        
    return found

def ghostcli_generate_fix(issue_title, issue_url, error_context):
    """Use GhostCLI API to generate a fix for the rework"""
    env = load_env()
    api_key = env.get("GHOSTCLI_API_KEY_FALLBACK") or env.get("GHOSTCLI_API_KEY")
    base_url = env.get("GHOSTCLI_BASE_URL", "https://ghostcli.dev")
    model = re.sub(r'\x1b\[[0-9;]*m', '', env.get("GHOSTCLI_MODEL", "claude-fable-5")).split('[')[0].strip()
    if not api_key:
        log("ERROR: No GhostCLI API key for rework")
        return None
    
    prompt = f"""You are fixing a rejected bounty PR. Generate a complete solution.

ISSUE: {issue_title}
URL: {issue_url}

REJECTION CONTEXT:
{error_context[:3000]}

REQUIREMENTS:
- Provide the exact code changes needed to fix the issue
- Handle all edge cases mentioned in the rejection
- Ensure tests pass
- Output only code and minimal explanation"""
    
    try:
        resp = requests.post(f"{base_url.rstrip('/')}/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 4000,
                "temperature": 0.1
            },
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=120)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        log(f"  GhostCLI generated {len(content)} chars")
        return content
    except Exception as e:
        log(f"  GhostCLI generation failed: {e}")
        return None

def auto_rework_closed_prs(closed_prs):
    """Attempt to fix and resubmit PRs that were closed/rejected"""
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    for pr in closed_prs[:3]:
        repo_owner = pr.get("headRepositoryOwner",{}).get("login","?")
        number = pr.get("number")
        title = pr.get("title","")
        url = pr.get("url","")
        
        rework_marker = WORKSPACE / f"rework_{repo_owner}_{number}.done"
        if rework_marker.exists():
            continue
            
        log(f"REWORK ATTEMPT: [{repo_owner}] #{number} - {title}")
        
        match = re.search(r'github\.com/([^/]+/[^/]+)', url)
        if not match:
            log(f"  Could not parse repo from URL: {url}")
            rework_marker.write_text(datetime.now(timezone.utc).isoformat())
            continue
        repo_full = match.group(1)
        
        tmp_dir = tempfile.mkdtemp(prefix="rework_", dir=str(WORKSPACE))
        try:
            clone_out = subprocess.run(
                ["git", "clone", "--depth", "1", f"https://github.com/{repo_full}.git", tmp_dir],
                capture_output=True, text=True, timeout=60
            )
            if clone_out.returncode != 0:
                log(f"  Clone failed: {clone_out.stderr[:200]}")
                rework_marker.write_text(datetime.now(timezone.utc).isoformat())
                continue
            
            # Get issue/PR details for context
            issue_body = ""
            try:
                issue_out = subprocess.run(
                    ["gh", "issue", "view", str(number), "--repo", repo_full, "--json", "body,title"],
                    capture_output=True, text=True, timeout=30
                )
                if issue_out.returncode == 0:
                    idata = json.loads(issue_out.stdout)
                    issue_body = idata.get("body","")
            except:
                pass
            
            # Also get PR comments for rejection reason
            try:
                comments_out = subprocess.run(
                    ["gh", "pr", "view", str(number), "--repo", repo_full, "--json", "comments,reviews"],
                    capture_output=True, text=True, timeout=30
                )
                if comments_out.returncode == 0:
                    cdata = json.loads(comments_out.stdout)
                    comments = cdata.get("comments",[]) + cdata.get("reviews",[])
                    if comments:
                        issue_body += "\n\n--- COMMENTS ---\n" + "\n".join(
                            c.get("body","")[:500] for c in comments[-5:]
                        )
            except:
                pass
            
            fix_code = ghostcli_generate_fix(title, url, issue_body)
            
            if fix_code:
                log(f"  FIX GENERATED for [{repo_full}] #{number}")
                # Save fix to workspace for manual review or auto-submit
                fix_file = WORKSPACE / f"fix_{repo_owner}_{number}.md"
                fix_file.write_text(f"# Fix for {repo_full}#{number}\n\n{fix_code}")
                log(f"  Saved fix to {fix_file}")
            
            rework_marker.write_text(datetime.now(timezone.utc).isoformat())
            
        except Exception as e:
            log(f"  Rework error: {e}")
        finally:
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except:
                pass

def run_cycle():
    log("=== Revenue Monitor Cycle Start ===")
    env = load_env()

    # 1. Gmail scan
    try:
        token = get_gmail_token(env)
        emails = scan_gmail(token)
        log(f"Gmail: {len(emails)} relevant emails found")
        for e in emails[:5]:
            log(f"  EMAIL: [{e['date']}] {e['subject']} (from: {e['from']})")
    except Exception as e:
        log(f"Gmail scan failed: {e}")

    # 2. GitHub PR audit
    merged, opened, closed = audit_github_prs()
    log(f"GitHub: {len(merged)} merged | {len(opened)} open | {len(closed)} closed-not-merged")
    for p in merged:
        repo = p.get("headRepositoryOwner",{}).get("login","?")
        log(f"  MERGED: [{repo}] #{p['number']} - {p['title']} ({p['mergedAt']})")
    for p in closed[:5]:
        repo = p.get("headRepositoryOwner",{}).get("login","?")
        log(f"  CLOSED: [{repo}] #{p['number']} - {p['title']}")

    # 3. Ledger reconciliation
    bounties = reconcile_ledger(merged)
    paid = sum(b.get("bounty_value",0) for b in bounties if b.get("status") in ("merged","paid"))
    submitted = sum(b.get("bounty_value",0) for b in bounties if b.get("status") == "submitted")
    log(f"Ledger: ${paid} merged/paid | ${submitted} pending submission")

    # 4. Platform scraping
    log("Scanning bounty platforms...")
    platform_bounties = scrape_bounty_platforms()

    # 5. Auto-rework closed PRs
    if closed:
        log(f"Attempting auto-rework for {len(closed)} closed PRs...")
        auto_rework_closed_prs(closed)
    else:
        log("No closed PRs to rework")

    log("=== Cycle Complete ===\n")

if __name__ == "__main__":
    log("Revenue Monitor v2.0 starting (interval=900s, auto-rework+platforms enabled)")
    while True:
        try:
            run_cycle()
        except Exception as e:
            log(f"FATAL cycle error: {e}")
        time.sleep(900)
