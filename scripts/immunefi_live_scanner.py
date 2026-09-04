#!/usr/bin/env python3
"""
Immunefi Live Bounty Scanner
Replaces static templates with real-time data from Immunefi bug bounty listings.
Zero-capital: only reads public pages, no API key needed.
Outputs opportunities to /Agentic/revenue/immunefi_opportunities/
"""

import json
import os
import re
import subprocess
from datetime import datetime, timezone

OUTPUT_DIR = "/Agentic/revenue/immunefi_opportunities"
LOG_PATH = "/Agentic/logs/immunefi_live_scanner.log"
STATE_PATH = "/Agentic/config/immunefi_scanner_state.json"

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")

def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"seen_ids": [], "last_scan": None}

def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)

def parse_bounty_text(text):
    """Parse the innerText of Immunefi bug-bounty page into structured records."""
    opportunities = []
    # Split by "View bounty" which terminates each listing
    blocks = text.split("View bounty")
    for block in blocks[:-1]:  # last split is trailing junk
        lines = [l.strip() for l in block.strip().split("\n") if l.strip()]
        if len(lines) < 4:
            continue
        
        name = lines[0] if lines else "Unknown"
        max_bounty = "$0"
        vault_tvl = "$0"
        total_paid = "Private"
        
        # Find dollar amounts
        dollar_matches = re.findall(r'\$[\d,.]+[kKmM]?', block)
        if len(dollar_matches) >= 2:
            vault_tvl = dollar_matches[0]
            max_bounty = dollar_matches[1]
        if len(dollar_matches) >= 3:
            total_paid = dollar_matches[2]
        
        # Parse numeric value for sorting
        def parse_usd(s):
            s = s.replace(",", "").replace("$", "")
            mult = 1
            if s.endswith(("k", "K")):
                mult = 1_000
                s = s[:-1]
            elif s.endswith(("m", "M")):
                mult = 1_000_000
                s = s[:-1]
            try:
                return float(s) * mult
            except:
                return 0.0
        
        max_val = parse_usd(max_bounty)
        
        opp_id = f"IMF-{name.lower().replace(' ', '-')}-{datetime.now(timezone.utc).strftime('%Y%m')}"
        
        opportunities.append({
            "id": opp_id,
            "platform": "immunefi",
            "name": name,
            "max_bounty_usd": max_val,
            "max_bounty_display": max_bounty,
            "vault_tvl": vault_tvl,
            "total_paid": total_paid,
            "payout_method": "crypto_wallet",
            "autonomous_submission": True,
            "submission_format": "markdown_vulnerability_report",
            "requires_human": [],
            "discovered_at": datetime.now(timezone.utc).isoformat(),
            "status": "active"
        })
    
    return opportunities

def main():
    log("=== Immunefi Live Scanner Cycle Start ===")
    
    # Use playwright-cli to get fresh page content
    try:
        result = subprocess.run(
            ["playwright-cli", "open", "https://immunefi.com/bug-bounty/"],
            capture_output=True, text=True, timeout=30
        )
        import time; time.sleep(6)
        
        eval_result = subprocess.run(
            ["playwright-cli", "eval", 
             "() => document.querySelector('main')?.innerText?.substring(0, 8000) || document.body.innerText.substring(0, 8000)"],
            capture_output=True, text=True, timeout=15
        )
        page_text = eval_result.stdout
    except Exception as e:
        log(f"ERROR: Failed to fetch Immunefi page: {e}")
        return
    
    if not page_text or "Result" not in page_text:
        log("ERROR: No valid page content retrieved")
        return
    
    # Extract the actual text from playwright eval output
    match = re.search(r'### Result\n"(.*?)"\n### Ran', page_text, re.DOTALL)
    if match:
        raw_text = match.group(1).replace("\\n", "\n").replace("\\t", "\t")
    else:
        raw_text = page_text
    
    opportunities = parse_bounty_text(raw_text)
    log(f"Parsed {len(opportunities)} bounty programs from live page")
    
    # Filter high-value (>= $50k max bounty)
    high_value = [o for o in opportunities if o["max_bounty_usd"] >= 50_000]
    high_value.sort(key=lambda x: x["max_bounty_usd"], reverse=True)
    log(f"High-value bounties (>=$50k): {len(high_value)}")
    
    # Save all opportunities
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    state = load_state()
    new_count = 0
    
    for opp in opportunities:
        path = os.path.join(OUTPUT_DIR, f"{opp['id']}.json")
        with open(path, "w") as f:
            json.dump(opp, f, indent=2)
        if opp["id"] not in state["seen_ids"]:
            state["seen_ids"].append(opp["id"])
            new_count += 1
    
    state["last_scan"] = datetime.now(timezone.utc).isoformat()
    state["total_programs"] = len(opportunities)
    state["high_value_count"] = len(high_value)
    save_state(state)
    
    # Print top 10 for visibility
    for i, opp in enumerate(high_value[:10]):
        log(f"  TOP-{i+1}: {opp['name']} — Max: {opp['max_bounty_display']} — TVL: {opp['vault_tvl']}")
    
    log(f"Scan complete: {len(opportunities)} programs, {new_count} new, {len(high_value)} high-value")
    log("=== Immunefi Live Scanner Cycle Complete ===")

if __name__ == "__main__":
    main()
