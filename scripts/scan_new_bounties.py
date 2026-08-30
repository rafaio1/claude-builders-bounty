#!/usr/bin/env python3
"""Scan Superteam Earn for new high-value bounties and log opportunities."""
import json
import re
import subprocess
from datetime import datetime

def get_bounty_list():
    """Use playwright-cli to fetch current bounty listings."""
    cmd = "playwright-cli open 'https://superteam.fun/earn/all?tab=bounties&category=Content'"
    subprocess.run(cmd, shell=True, capture_output=True)
    
    # Read snapshot
    import glob
    snapshots = sorted(glob.glob(".playwright-cli/page-*.yml"))
    if not snapshots:
        return []
    
    with open(snapshots[-1]) as f:
        content = f.read()
    
    # Parse bounty entries
    pattern = r'link "([^"]+)" \[ref=e\d+\].*?\$?([\d,]+)\s*(USDC|USDG)'
    matches = re.findall(pattern, content, re.IGNORECASE)
    
    bounties = []
    for title, amount, currency in matches:
        try:
            value = int(amount.replace(",", ""))
            bounties.append({
                "title": title.strip(),
                "value": value,
                "currency": currency.upper(),
                "scanned_at": datetime.utcnow().isoformat()
            })
        except ValueError:
            continue
    
    return bounties

if __name__ == "__main__":
    print(f"[{datetime.utcnow().isoformat()}] Scanning for new bounties...")
    bounties = get_bounty_list()
    
    # Filter high-value (>= $500)
    high_value = [b for b in bounties if b["value"] >= 500]
    
    output_path = "state/new_bounty_scan.json"
    with open(output_path, "w") as f:
        json.dump({"scan_time": datetime.utcnow().isoformat(), "total_found": len(bounties), "high_value": high_value}, f, indent=2)
    
    print(f"Found {len(bounties)} bounties, {len(high_value)} high-value (>=$500)")
    for b in high_value[:10]:
        print(f"  - {b['title']}: {b['value']} {b['currency']}")
