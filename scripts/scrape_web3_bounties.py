#!/usr/bin/env python3
"""
Web3 Bounty Scraper - Sherlock, Immunefi, Hats Finance
Injects active/upcoming contests into bounty_ledger.json for the bounty engine.
Uses playwright-cli eval for reliable JS-based scraping of SPAs.
"""
import json, os, sys, time, re, subprocess
from datetime import datetime, timezone
from pathlib import Path

LEDGER_FILE = Path("/Agentic/data/aro/bounty_ledger.json")
FAILED_REPOS = Path("/Agentic/data/aro/failed_repos.json")
LOG_PREFIX = "[WEB3-SCRAPER]"

def log(msg):
    print(f"{LOG_PREFIX} [{datetime.now(timezone.utc).isoformat()}] {msg}", flush=True)

def load_json(p):
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except Exception:
        return {}

def save_json(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))

def pw_eval(url, js_code, wait=5):
    """Open URL, wait, run JS eval, return parsed JSON or raw string."""
    try:
        subprocess.run(["playwright-cli", "open", url], capture_output=True, timeout=30)
        time.sleep(wait)
        r = subprocess.run(["playwright-cli", "eval", js_code], capture_output=True, text=True, timeout=30)
        subprocess.run(["playwright-cli", "close"], capture_output=True, timeout=10)
        out = r.stdout.strip()
        # Extract JSON from result block
        m = re.search(r'### Result\n"?(.*?)"?\n###', out, re.DOTALL)
        if m:
            raw = m.group(1).strip().strip('"')
            # Unescape
            raw = raw.replace('\\"', '"').replace('\\n', '\n')
            try:
                return json.loads(raw)
            except Exception:
                return raw
        return out
    except Exception as e:
        log(f"Playwright eval error: {e}")
        return None

def scrape_immunefi():
    """Scrape Immunefi bug bounties via JS eval on table rows."""
    log("Scraping Immunefi...")
    js = """JSON.stringify(Array.from(document.querySelectorAll('table tbody tr')).slice(0,30).map(r => {
        const cells = r.querySelectorAll('td');
        const nameEl = cells[0];
        const link = nameEl?.querySelector('a');
        return {
            name: nameEl?.innerText?.trim()?.split('\\n')[0] || '',
            maxBounty: cells[2]?.innerText?.trim() || '0',
            url: link?.href || ''
        };
    }).filter(x => x.url && x.name))"""
    data = pw_eval("https://immunefi.com/bug-bounty/", js, wait=6)
    bounties = []
    if isinstance(data, list):
        for item in data:
            name = item.get("name", "")
            raw_val = item.get("maxBounty", "0")
            # Parse "$250k", "$3M", "$50k" etc
            nums = re.sub(r'[^\d.]', '', raw_val.replace('k','000').replace('M','000000'))
            try:
                val = float(nums) if nums else 0
            except ValueError:
                val = 0
            if val < 1000:
                continue
            bounties.append({
                "source": "immunefi",
                "url": item.get("url", ""),
                "title": f"[Immunefi] {name} Bug Bounty - {raw_val}",
                "value_usd": str(int(val)),
                "labels": ["web3", "bug-bounty", "security", "defi"],
                "body_preview": f"Max reward: {raw_val}",
                "discovered_at": datetime.now(timezone.utc).isoformat()
            })
    log(f"Immunefi: found {len(bounties)} bounties")
    return bounties

def scrape_sherlock():
    """Scrape Sherlock audit contests via JS eval."""
    log("Scraping Sherlock...")
    js = """JSON.stringify(Array.from(document.querySelectorAll('a[href*="/contests/"]')).slice(0,20).map(a => ({
        title: a.innerText?.trim()?.substring(0,100) || '',
        url: a.href || ''
    })).filter(x => x.url.includes('/contests/') && x.title.length > 3))"""
    data = pw_eval("https://www.sherlock.xyz/contests", js, wait=6)
    bounties = []
    if isinstance(data, list):
        seen = set()
        for item in data:
            url = item.get("url", "")
            if url in seen or not url:
                continue
            seen.add(url)
            title = item.get("title", "Sherlock Audit Contest")
            # Try to extract prize from title
            m = re.search(r'\$[\d,.]+[kKmM]?', title)
            val_str = m.group(0) if m else "0"
            nums = re.sub(r'[^\d.]', '', val_str.replace('k','000').replace('K','000').replace('M','000000'))
            try:
                val = float(nums) if nums else 0
            except ValueError:
                val = 0
            bounties.append({
                "source": "sherlock",
                "url": url,
                "title": f"[Sherlock] {title}",
                "value_usd": str(int(val)) if val > 0 else "unknown",
                "labels": ["web3", "audit", "solidity", "security"],
                "body_preview": "Sherlock audit contest",
                "discovered_at": datetime.now(timezone.utc).isoformat()
            })
    log(f"Sherlock: found {len(bounties)} contests")
    return bounties

def scrape_hats_finance():
    """Scrape Hats Finance competitions via JS eval."""
    log("Scraping Hats Finance...")
    js = """JSON.stringify(Array.from(document.querySelectorAll('a[href*="/competition/"], a[href*="/vault/"]')).slice(0,20).map(a => ({
        title: a.innerText?.trim()?.substring(0,100) || '',
        url: a.href || ''
    })).filter(x => x.url && x.title.length > 3))"""
    data = pw_eval("https://app.hats.finance/competitions", js, wait=6)
    bounties = []
    if isinstance(data, list):
        seen = set()
        for item in data:
            url = item.get("url", "")
            if url in seen or not url:
                continue
            seen.add(url)
            title = item.get("title", "Hats Finance Competition")
            m = re.search(r'\$[\d,.]+[kKmM]?', title)
            val_str = m.group(0) if m else "0"
            nums = re.sub(r'[^\d.]', '', val_str.replace('k','000').replace('K','000').replace('M','000000'))
            try:
                val = float(nums) if nums else 0
            except ValueError:
                val = 0
            bounties.append({
                "source": "hats-finance",
                "url": url,
                "title": f"[Hats] {title}",
                "value_usd": str(int(val)) if val > 0 else "unknown",
                "labels": ["web3", "audit", "security"],
                "body_preview": "Hats Finance competition",
                "discovered_at": datetime.now(timezone.utc).isoformat()
            })
    log(f"Hats Finance: found {len(bounties)} competitions")
    return bounties

def inject_into_ledger(new_bounties):
    """Merge new web3 bounties into the main ledger without duplicates."""
    ledger = load_json(LEDGER_FILE)
    if "bounties" not in ledger:
        ledger["bounties"] = []
    
    existing_urls = {b.get("url") for b in ledger["bounties"] if b.get("url")}
    added = 0
    for b in new_bounties:
        url = b.get("url", "")
        if url and url not in existing_urls:
            entry = {
                "url": url,
                "title": b.get("title", ""),
                "value_usd": b.get("value_usd", "unknown"),
                "source": b.get("source", "web3-scraper"),
                "status": "discovered",
                "labels": b.get("labels", []),
                "discovered_at": b.get("discovered_at", datetime.now(timezone.utc).isoformat()),
                "submitted_at": None,
                "pr_url": None,
                "payout_verified": False,
                "payout_amount": 0
            }
            ledger["bounties"].append(entry)
            existing_urls.add(url)
            added += 1
    
    save_json(LEDGER_FILE, ledger)
    log(f"Injected {added} new web3 bounties into ledger (total: {len(ledger['bounties'])})")
    return added

def main():
    log("=== Web3 Bounty Scraper Starting ===")
    all_bounties = []
    
    all_bounties.extend(scrape_immunefi())
    time.sleep(2)
    all_bounties.extend(scrape_sherlock())
    time.sleep(2)
    all_bounties.extend(scrape_hats_finance())
    
    if all_bounties:
        inject_into_ledger(all_bounties)
    else:
        log("No active web3 bounties found this cycle")
    
    log(f"=== Cycle complete: {len(all_bounties)} total found ===")

if __name__ == "__main__":
    main()
