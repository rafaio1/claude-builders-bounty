#!/usr/bin/env python3
"""
Immunefi Deep Scanner - Extracts individual bounty details from program pages.
Focuses on high-value programs identified by immunefi_live_scanner.py.
Zero-capital: reads public pages only via playwright-cli.
"""

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone

OUTPUT_DIR = "/Agentic/revenue/immunefi_deep_opportunities"
LOG_PATH = "/Agentic/logs/immunefi_deep_scanner.log"
LIVE_OPP_DIR = "/Agentic/revenue/immunefi_opportunities"

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")

def get_high_value_programs():
    """Load high-value programs from live scanner output."""
    programs = []
    if not os.path.exists(LIVE_OPP_DIR):
        return programs
    for fname in os.listdir(LIVE_OPP_DIR):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(LIVE_OPP_DIR, fname)
        try:
            with open(path) as f:
                data = json.load(f)
            if data.get("max_bounty_usd", 0) >= 50_000:
                programs.append(data)
        except:
            pass
    programs.sort(key=lambda x: x.get("max_bounty_usd", 0), reverse=True)
    return programs[:5]  # Top 5 highest value

def fetch_page_text(url):
    """Fetch page text using playwright-cli with session reuse and retry."""
    for attempt in range(2):
        try:
            # Try snapshot first (reuses existing session if open)
            snap = subprocess.run(["playwright-cli", "snapshot"], capture_output=True, text=True, timeout=5)
            if "Error" in snap.stdout or snap.returncode != 0:
                subprocess.run(["playwright-cli", "open", url], capture_output=True, timeout=30)
                time.sleep(8)
            else:
                # Navigate within existing session
                subprocess.run(["playwright-cli", "eval", f"window.location.href='{url}'"], capture_output=True, timeout=10)
                time.sleep(6)
            
            result = subprocess.run(
                ["playwright-cli", "eval", "() => document.querySelector('main')?.innerText?.substring(0, 10000) || document.body.innerText.substring(0, 10000)"],
                capture_output=True, text=True, timeout=20
            )
            match = re.search(r'### Result\n"(.*?)"\n### Ran', result.stdout, re.DOTALL)
            if match:
                text = match.group(1).replace("\\n", "\n").replace("\\t", "\t")
                if len(text) > 200:
                    return text
            if attempt == 0:
                log(f"  Retry fetch for {url} (attempt {attempt+1})")
                subprocess.run(["playwright-cli", "close"], capture_output=True, timeout=5)
                time.sleep(2)
                continue
            return result.stdout
        except Exception as e:
            log(f"ERROR fetching {url} (attempt {attempt+1}): {e}")
            if attempt == 0:
                subprocess.run(["playwright-cli", "close"], capture_output=True, timeout=5)
                time.sleep(2)
    return ""

def parse_bounty_details(text, program_name):
    """Extract vulnerability categories and payout tiers from program page."""
    details = {"program": program_name, "categories": [], "tiers": [], "raw_snippet": text[:2000]}
    
    # Look for common severity/payout patterns
    tier_patterns = [
        r'(Critical|High|Medium|Low)\s*[:\-]?\s*\$?([\d,.]+[kKmM]?)',
        r'(Smart Contract|Blockchain|DeFi|Bridge|Oracle)\s*[:\-]?\s*\$?([\d,.]+[kKmM]?)',
    ]
    
    for pattern in tier_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            details["tiers"].append({"severity": m[0], "payout": m[1]})
    
    # Look for asset/scope keywords
    scope_keywords = ["smart contract", "solidity", "vyper", "rust", "cosmwasm", 
                      "bridge", "oracle", "dex", "lending", "staking", "governance"]
    found_scope = [kw for kw in scope_keywords if kw.lower() in text.lower()]
    details["scope_keywords"] = list(set(found_scope))
    
    return details

def main():
    log("=== Immunefi Deep Scanner Cycle Start ===")
    
    programs = get_high_value_programs()
    log(f"Loaded {len(programs)} high-value programs for deep scan")
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    scanned = 0
    
    for prog in programs:
        name = prog.get("name", "Unknown")
        opp_id = prog.get("id", f"IMF-{name.lower().replace(' ', '-')}")
        
        # Construct likely URL slug
        slug = name.lower().replace(" ", "-").replace(".", "").replace(",", "")
        url = f"https://immunefi.com/bug-bounty/{slug}/"
        
        log(f"Scanning: {name} -> {url}")
        text = fetch_page_text(url)
        
        if len(text) < 100:
            log(f"  WARN: Short response for {name}, skipping detail extraction")
            continue
        
        details = parse_bounty_details(text, name)
        details["source_url"] = url
        details["parent_opportunity_id"] = opp_id
        details["scanned_at"] = datetime.now(timezone.utc).isoformat()
        
        out_path = os.path.join(OUTPUT_DIR, f"{opp_id}-deep.json")
        with open(out_path, "w") as f:
            json.dump(details, f, indent=2)
        
        log(f"  Found {len(details['tiers'])} payout tiers, {len(details['scope_keywords'])} scope keywords")
        scanned += 1
        time.sleep(2)  # Rate limit courtesy
    
    log(f"Deep scan complete: {scanned}/{len(programs)} programs processed")
    log("=== Immunefi Deep Scanner Cycle Complete ===")

if __name__ == "__main__":
    main()
