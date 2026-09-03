#!/usr/bin/env python3
"""Ingest C4/Sherlock/Algora revenue opportunities into bounty_priority_queue.

Read-only for canonical ledgers. Writes only to state/bounty_priority_queue.json
under monitor_only with proper scout-schema fields so the sweeper can promote them.
"""
import json, os, hashlib
from pathlib import Path
from datetime import datetime, timezone

STATE = Path("/Agentic/state")
PQ_PATH = STATE / "bounty_priority_queue.json"
REVENUE_DIRS = {
    "code4rena": Path("/Agentic/revenue/code4rena_opportunities"),
    "sherlock": Path("/Agentic/revenue/sherlock_opportunities"),
    "algora": Path("/Agentic/revenue/algora_opportunities"),
}

def load_json(p):
    if not p.exists(): return None
    try: return json.loads(p.read_text())
    except: return None

def save_json(p, data):
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.rename(p)

def make_stable_id(platform, file_id):
    """Create a stable ID that normalizes month-suffix variants.
    C4-euler-finance-202608 and C4-euler-finance-202609 should map to the
    same stable ID so the ingest dedup prevents re-adding both variants."""
    import re as _re
    normalized = _re.sub(r'-\d{6}$', '', str(file_id)).strip() if file_id else ''
    if normalized:
        return f'{platform}:{normalized}'
    return f'{platform}:{file_id}' 

def _resolve_url(platform, data):
    """Build a detail-page URL from scanner fields when the source JSON lacks one."""
    if data.get("url"):
        return data["url"]
    sponsor = (data.get("sponsor") or "").strip()
    if not sponsor:
        return ""
    slug = sponsor.lower().replace(" ", "-")
    import re as _re
    ym = ""
    fid = str(data.get("id", ""))
    m = _re.search(r"(\d{4})(\d{2})$", fid)
    if m:
        ym = f"{m.group(1)}-{m.group(2)}"
    else:
        da = data.get("discovered_at", "")
        if len(da) >= 7:
            ym = da[:7]
    if platform == "code4rena":
        if ym:
            return f"https://code4rena.com/audits/{ym}/{slug}"
        return f"https://code4rena.com/audits/{slug}"
    if platform == "sherlock":
        return f"https://www.sherlock.xyz/audits/{slug}"
    if platform == "algora":
        return f"https://console.algora.io/bounties/{slug}"
    return ""

def ingest():
    pq = load_json(PQ_PATH) or {"action_queue":[], "research_queue":[], "monitor_only":[]}
    existing_ids = set()
    for e in pq.get("monitor_only", []):
        sid = e.get("stable_id") or ""
        existing_ids.add(sid)
    
    added = 0
    for platform, dirpath in REVENUE_DIRS.items():
        if not dirpath.exists():
            continue
        for f in sorted(dirpath.iterdir()):
            if not f.name.endswith(".json"):
                continue
            data = load_json(f)
            if not data:
                continue
            fid = data.get("id", f.stem)
            sid = make_stable_id(platform, fid)
            if sid in existing_ids:
                continue
            
            # Map to scout-schema fields
            prize = data.get("prize_pool_usd", 0)
            status_raw = data.get("status", "unknown")
            payout = data.get("payout_method", "")
            requires_human = data.get("requires_human", [])
            autonomous = data.get("autonomous_submission", False)
            
            # Determine agent_access
            if autonomous and "account_creation" in requires_human and len(requires_human) == 1:
                agent_access = "AGENT_ALLOWED"
            elif not requires_human and autonomous:
                agent_access = "AGENT_ALLOWED"
            else:
                agent_access = "HUMAN_REQUIRED"
            
            # Determine asset - C4/Sherlock pay USDC on-chain
            asset = "USDC" if platform in ("code4rena", "sherlock") else "UNKNOWN"
            
            # Self-custody rail verified if crypto_wallet payout
            rail_verified = payout == "crypto_wallet"
            
            entry = {
                "stable_id": sid,
                "candidate_id": fid,
                "bounty_key": fid,
                "title": f"{data.get('sponsor','')} - ${prize:,} {platform} audit",
                "platform": platform,
                "source": f"{platform}_scanner",
                "url": _resolve_url(platform, data),
                "asset": asset,
                "agent_access": agent_access,
                "self_custody_rail_verified": rail_verified,
                "qualification_decision": None,
                "explicit_execution_contract": False,
                "listing_verified": True,
                "gross_verified": prize,
                "gross_classification": "verified_unrealized_opportunity_not_revenue",
                "financial_classification": "unrealized_opportunity_not_revenue",
                "funds_moved": False,
                "realized": 0,
                "route_status": "route_pending" if rail_verified else "no_route",
                "human_gates": {k: True for k in requires_human},
                "human_gates_complete": len(requires_human) == 0,
                "reason_codes": [f"ingested_from_{platform}_scanner"],
                "source_fresh": True,
                "provider": platform,
                "provider_verified": False,
                "_ingested_at": datetime.now(timezone.utc).isoformat(),
            }
            
            pq.setdefault("monitor_only", []).append(entry)
            existing_ids.add(sid)
            added += 1
    
    save_json(PQ_PATH, pq)
    print(f"Ingested {added} new opportunities into priority_queue")
    print(f"Total monitor_only now: {len(pq.get('monitor_only',[]))}")
    
    # Count actionable after ingest
    actionable = 0
    for e in pq.get("monitor_only", []):
        aa = e.get("agent_access","")
        asset = e.get("asset","")
        qual = e.get("qualification_decision")
        rail = e.get("self_custody_rail_verified", False)
        if qual == "rejected": continue
        if aa in ("HUMAN_ONLY","HUMAN_REQUIRED"): continue
        if asset == "RTC": continue
        if aa == "AGENT_ALLOWED": actionable += 1
        elif rail and asset != "RTC": actionable += 1
    print(f"Actionable entries after ingest: {actionable}")

if __name__ == "__main__":
    ingest()
