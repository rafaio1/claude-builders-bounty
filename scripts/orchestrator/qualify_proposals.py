#!/usr/bin/env python3
"""Phase 4.5: Qualification Pipeline for pending_qualification proposals."""
import json, os, sys, hashlib, glob
from datetime import datetime, timezone
from pathlib import Path

PROPOSALS_DIR = Path("/Agentic/data/aro/proposals")
PRIORITY_QUEUE = Path("/Agentic/state/bounty_priority_queue.json")
LOG_FILE = Path("/Agentic/logs/supervisor/qualification_run.log")

# Autonomous-friendly platforms that don't require human account creation
AUTONOMOUS_PLATFORMS = {"immunefi", "code4rena", "sherlock", "hats"}
HUMAN_GATE_PLATFORMS = {"galxe", "layer3"}  # Typically require social/wallet auth

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def load_priority_queue():
    if PRIORITY_QUEUE.exists():
        with open(PRIORITY_QUEUE) as f:
            return json.load(f)
    return {"action_queue": [], "research_queue": []}

def save_priority_queue(q):
    PRIORITY_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    with open(PRIORITY_QUEUE, "w") as f:
        json.dump(q, f, indent=2)

def qualify_proposal(data, filepath):
    """Returns (new_status, reason, promoted_entry_or_None)"""
    ctx = data.get("context", {})
    platform = ctx.get("platform", "").lower()
    requires_human = ctx.get("requires_human", [])
    gross = ctx.get("gross", 0) or 0
    asset = ctx.get("asset", "UNKNOWN")
    autonomous = ctx.get("autonomous_submission", False)
    candidate_id = data.get("candidate_id", filepath.stem)
    
    # Gate 1: Human gates block autonomous execution
    if requires_human and any(g in requires_human for g in ["kyc", "identity_verification"]):
        return "archived_human_gate", f"Requires human: {requires_human}", None
    
    # Gate 2: Platform must be autonomous-friendly
    if platform not in AUTONOMOUS_PLATFORMS:
        return "archived_platform_gate", f"Platform {platform} not in autonomous set", None
    
    # Gate 3: Must have valid payout info
    if gross <= 0 or asset == "UNKNOWN":
        return "archived_invalid_payout", f"gross={gross}, asset={asset}", None
    
    # Gate 4: Dedup check - skip if already in queue
    queue = load_priority_queue()
    existing_ids = {item.get("candidate_id") for item in queue.get("action_queue", []) + queue.get("research_queue", [])}
    if candidate_id in existing_ids:
        return "skipped_duplicate", "Already in priority queue", None
    
    # Passed all gates -> promote to research_queue for claim preparation
    entry = {
        "candidate_id": candidate_id,
        "platform": platform,
        "title": ctx.get("title", ""),
        "max_payout_usd": gross,
        "payout_asset": asset,
        "url": ctx.get("url", ""),
        "source_file": str(filepath),
        "qualified_at": datetime.now(timezone.utc).isoformat(),
        "expected_net_to_wise": None  # To be filled by claim prep phase
    }
    return "review_approved", "Passed all qualification gates", entry

def main():
    files = sorted(PROPOSALS_DIR.glob("*.json"))
    pending = [f for f in files if '"pending_qualification"' in f.read_text()]
    
    log(f"Qualification run: {len(pending)} pending proposals found")
    
    stats = {"promoted": 0, "archived": 0, "skipped": 0, "errors": 0}
    queue = load_priority_queue()
    
    for fp in pending:
        try:
            with open(fp) as f:
                data = json.load(f)
            
            new_status, reason, entry = qualify_proposal(data, fp)
            
            # Update proposal file status
            data["status"] = new_status
            data["qualification_reason"] = reason
            data["qualified_at"] = datetime.now(timezone.utc).isoformat()
            with open(fp, "w") as f:
                json.dump(data, f, indent=2)
            
            if entry:
                queue.setdefault("research_queue", []).append(entry)
                stats["promoted"] += 1
                log(f"PROMOTED: {data.get('candidate_id')} -> research_queue ({reason})")
            elif "duplicate" in new_status:
                stats["skipped"] += 1
            else:
                stats["archived"] += 1
                log(f"ARCHIVED: {data.get('candidate_id')} ({reason})")
                
        except Exception as e:
            stats["errors"] += 1
            log(f"ERROR: {fp.name}: {e}")
    
    save_priority_queue(queue)
    log(f"Qualification complete: {stats}")
    return stats

if __name__ == "__main__":
    main()
