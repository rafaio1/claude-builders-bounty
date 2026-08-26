#!/usr/bin/env python3
"""Deterministic PR email agent: poll, classify, act, ledger."""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path("/Agentic/workspace/pr-email-actions")
LEDGER_PATH = WORKSPACE / "ledger_final.json"
GMAIL_CLIENT = Path("/Agentic/tools/gmail_client.py")
REPOS = {
    "OphirPay/OphirPay": WORKSPACE / "ophirpay",
    "PesanteAnalytics/contoso-universe-gen": WORKSPACE / "contoso",
}

def load_ledger():
    if LEDGER_PATH.exists():
        return json.loads(LEDGER_PATH.read_text())
    return []

def save_ledger(entries):
    LEDGER_PATH.write_text(json.dumps(entries, indent=2))

def run_cmd(cmd, **kwargs):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, **kwargs)
    return r.returncode, r.stdout.strip(), r.stderr.strip()

def gh_pr_state(repo, pr_num):
    rc, out, _ = run_cmd(f"gh pr view {pr_num} --repo {repo} --json state,url")
    if rc != 0:
        return None, None
    data = json.loads(out)
    return data.get("state"), data.get("url")

def is_vercel_auth(body):
    return bool(re.search(r"authorize.*vercel|vercel.*authorize", body, re.I))

def classify_and_process():
    ledger = load_ledger()
    seen_ids = {e["message_id"] for e in ledger}
    
    # Poll inbox
    rc, out, _ = run_cmd(f"python3 {GMAIL_CLIENT} search 'newer_than:30d from:github.com subject:PR'")
    if rc != 0 or not out.strip():
        print("No emails found or search failed")
        return
    
    lines = [l for l in out.strip().split("\n") if l.startswith("[")]
    processed = 0
    
    for line in lines:
        m = re.match(r"\[([^\]]+)\].*?\|\s*(.+?)\s*\|\s*(.+)", line)
        if not m:
            continue
        msg_id, sender, subject = m.groups()
        if msg_id in seen_ids:
            continue
            
        # Extract repo and PR number
        pm = re.search(r"\[([^\]]+)\].*?\(PR #(\d+)\)", subject)
        if not pm:
            continue
        repo_full, pr_str = pm.groups()
        pr_num = int(pr_str)
        
        # Check state
        state, url = gh_pr_state(repo_full, pr_num)
        if not state:
            continue
            
        action = None
        trash_now = False
        
        if state in ("CLOSED", "MERGED"):
            action = f"trash_{state.lower()}"
            trash_now = True
        else:
            # OPEN - check if Vercel auth needed
            rc2, body, _ = run_cmd(f"python3 {GMAIL_CLIENT} read {msg_id}")
            if rc2 == 0:
                try:
                    bdata = json.loads(body)
                    full_body = bdata.get("body", "") + " " + bdata.get("snippet", "")
                    if is_vercel_auth(full_body):
                        action = "kept_vercel_auth"
                        trash_now = False
                    else:
                        # Bot success or review without human action needed
                        action = "trash_open_no_action"
                        trash_now = True
                except json.JSONDecodeError:
                    action = "kept_ambiguous"
                    trash_now = False
        
        entry = {
            "message_id": msg_id,
            "repo": repo_full,
            "pr": pr_num,
            "action": action,
            "github_url": url,
            "commit": None,
            "trash_at": datetime.now(timezone.utc).isoformat() if trash_now else None
        }
        ledger.append(entry)
        seen_ids.add(msg_id)
        
        if trash_now:
            run_cmd(f"python3 {GMAIL_CLIENT} trash {msg_id}")
            
        processed += 1
    
    save_ledger(ledger)
    print(f"Processed {processed} new emails. Ledger size: {len(ledger)}")

if __name__ == "__main__":
    classify_and_process()
