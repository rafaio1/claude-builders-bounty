#!/usr/bin/env python3
"""
Agentic Bounty Orchestrator v4 - 5-phase autonomous execution cycle.
Phase 1: Claims Sweep (lapsed/open PRs/re-claim)
Phase 2: Microtask Orchestration (dispatch to Claude via GhostCLI)
Phase 3: Self-Review (validate outputs before mirror)
Phase 4: Discovery (non-RTC, non-Stripe, auto-payout bounties)
Phase 5: Cleanup & Private Mirror Sync

Constraints:
- Provider: ghostcli-auto[1m] only
- Never modify canonical ledgers directly; write proposals
- RTC: monitor only, never move native without verified DApp route
- Approval policy: Never (no escalated permissions)
- Playwright: CLI only, never MCP
- Financial validation: only paid/completed ledger entries count as revenue
"""
import json, os, sys, subprocess, datetime, hashlib, glob, time
from pathlib import Path

STATE_DIR = Path("/Agentic/state")
LOG_DIR = Path("/Agentic/logs/supervisor")
PROPOSALS_DIR = Path("/Agentic/data/aro/proposals")
QUEUE_PATH = STATE_DIR / "bounty_priority_queue.json"
CYCLE_STATE_PATH = STATE_DIR / "orchestrator_cycle_state.json"
IMMUNEFI_OPPS_DIR = Path("/Agentic/revenue/immunefi_opportunities")
GMAIL_TRASH_STATE = STATE_DIR / "gmail_trash_backfill_v2_state.json"
PRIVATE_MIRROR_REPO = "rafaio1/claude-builders-bounty.git"
GHOSTCLI_MODEL = "ghostcli-auto[1m]"

LOG_DIR.mkdir(parents=True, exist_ok=True)
PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
IMMUNEFI_OPPS_DIR.mkdir(parents=True, exist_ok=True)

def log(msg, level="INFO"):
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    log_file = LOG_DIR / f"orchestrator-{datetime.date.today().isoformat()}.log"
    with open(log_file, "a") as f:
        f.write(line + "\n")

def load_json(path):
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception as e:
        log(f"Failed to load {p}: {e}", "ERROR")
        return None

def save_json(path, data):
    p = Path(path)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.rename(p)

def run_claude_microtask(prompt: str, task_id: str) -> dict:
    """Dispatch a microtask to Claude via GhostCLI provider. Returns result dict."""
    log(f"  Dispatching microtask {task_id} to {GHOSTCLI_MODEL}")
    try:
        env = os.environ.copy()
        env["ANTHROPIC_BASE_URL"] = "https://ghostcli.dev"
        cmd = [
            "claude", "--model", GHOSTCLI_MODEL,
            "-p", prompt, "--output-format", "json"
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env, cwd="/Agentic")
        if r.returncode == 0 and r.stdout.strip():
            try:
                result = json.loads(r.stdout)
                # Extract actual text content from Claude API envelope
                actual_output = result.get("result", "") if isinstance(result, dict) else str(result)
                if not actual_output and isinstance(result, dict):
                    # Fallback: check for content in nested structures
                    actual_output = str(result)
                log(f"  Microtask {task_id} completed successfully (output_len={len(str(actual_output))})")
                return {"status": "success", "output": actual_output, "task_id": task_id}
            except json.JSONDecodeError:
                log(f"  Microtask {task_id} returned non-JSON output", "WARN")
                return {"status": "success_raw", "output": r.stdout[:2000], "task_id": task_id}
        else:
            log(f"  Microtask {task_id} failed: rc={r.returncode} stderr={r.stderr[:500]}", "ERROR")
            return {"status": "error", "error": r.stderr[:1000], "task_id": task_id}
    except subprocess.TimeoutExpired:
        log(f"  Microtask {task_id} timed out after 300s", "ERROR")
        return {"status": "timeout", "task_id": task_id}
    except Exception as e:
        log(f"  Microtask {task_id} exception: {e}", "ERROR")
        return {"status": "exception", "error": str(e), "task_id": task_id}

def sync_private_mirror():
    """Sync current state and proposals to private GitHub mirror."""
    log("  Syncing to private mirror")
    try:
        cmds = [
            ["git", "add", "-A"],
            ["git", "commit", "-m", f"auto-mirror: orchestrator-v4 cycle {datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')}"],
            ["git", "push", "fork", "sync/autonomous-pipeline-20260903:main", "--force-with-lease"]
        ]
        for cmd in cmds:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd="/Agentic")
            if r.returncode != 0 and "nothing to commit" not in r.stdout:
                log(f"  Mirror sync step failed: {' '.join(cmd)} rc={r.returncode}", "WARN")
                return False
        log("  Private mirror sync complete")
        return True
    except Exception as e:
        log(f"  Mirror sync error: {e}", "ERROR")
        return False

# ── Phase 1: Claims Sweep ─────────────────────────────────────────────
def phase1_sweep_claims():
    """Check open PRs, lapsed claims, and re-actionable items."""
    log("PHASE 1: Sweeping claims and prior work")
    results = {"prs_checked": 0, "lapsed_found": 0, "proposals_created": 0, "reclaims_queued": 0}

    # Check known open PRs
    pr_checks = [
        ("Lilly-Protocol/lily-backend", 367),
        ("Opire/opire", 4077),
        ("Opire/opire", 4078),
        ("Opire/opire", 4079),
    ]
    for repo, num in pr_checks:
        try:
            r = subprocess.run(
                ["curl", "-sf", f"https://api.github.com/repos/{repo}/pulls/{num}"],
                capture_output=True, text=True, timeout=30
            )
            if r.returncode == 0:
                pr = json.loads(r.stdout)
                results["prs_checked"] += 1
                state = pr.get("state")
                merged = pr.get("merged")
                log(f"  PR {repo}#{num}: state={state} merged={merged}")
                if state == "open" and not merged:
                    # Queue microtask to check review status
                    results["reclaims_queued"] += 1
        except Exception as e:
            log(f"  PR check error {repo}#{num}: {e}", "WARN")

    # Scan proposals for stale/lapsed items needing re-claim
    proposal_files = sorted(glob.glob(str(PROPOSALS_DIR / "*.json")))
    for pf in proposal_files[-30:]:
        prop = load_json(pf)
        if not prop:
            continue
        status = prop.get("status", "")
        if status in ("lapsed", "claim_expired", "needs_reclaim"):
            results["lapsed_found"] += 1
            log(f"  Lapsed proposal: {Path(pf).name} status={status}")
            # Create reclaim proposal
            cid = prop.get("candidate_id", f"reclaim-{int(time.time())}")
            reclaim_prop = {
                "candidate_id": cid,
                "type": "reclaim_proposal",
                "status": "pending_execution",
                "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "original_proposal": Path(pf).name,
                "context": prop.get("context", {})
            }
            prop_hash = hashlib.sha256(json.dumps(reclaim_prop, sort_keys=True, default=str).encode()).hexdigest()[:12]
            save_json(PROPOSALS_DIR / f"{cid}-reclaim-{prop_hash}.json", reclaim_prop)
            results["proposals_created"] += 1

    log(f"  Phase 1 result: {results}")
    return results

# ── Phase 2: Microtask Orchestration ──────────────────────────────────
def phase2_microtask_orchestration():
    """Dispatch actionable proposals to Claude microtasks."""
    log("PHASE 2: Microtask orchestration")
    results = {"dispatched": 0, "completed": 0, "failed": 0, "skipped_superseded": 0, "total_scanned": 0}

    # Scan ALL proposals, not just last 50 — actionable items may be anywhere
    proposal_files = sorted(glob.glob(str(PROPOSALS_DIR / "*.json")))
    results["total_scanned"] = len(proposal_files)
    actionable = []
    for pf in proposal_files:
        prop = load_json(pf)
        if not prop:
            continue
        # Skip superseded proposals entirely
        if prop.get("action") == "superseded":
            results["skipped_superseded"] += 1
            continue
        # Skip proposals already processed by Phase 2 or promoted by Phase 3
        if prop.get("status") in ("microtask_completed", "review_approved", "review_rejected"):
            results["skipped_superseded"] += 1
            continue
        # Accept both legacy status field and next_status field for actionable items
        status = prop.get("status", "")
        next_status = prop.get("next_status", "")
        action = prop.get("action", "")
        is_actionable_status = status == "pending_execution" or next_status in (
            "claim_pending", "in_progress", "candidate", "submitted", "awaiting_first_review"
        )
        is_valid_type = prop.get("type") in ("reclaim_proposal", "execution_proposal", "discovery_proposal", None)
        # For next_status-based proposals, also accept by action type
        is_valid_action = action in ("qualify_claim", "investigate_claim", "submit_work", "fix_review_feedback", "monitor_pr_review", "claim", "reclaim_lapsed", None)
        if is_actionable_status and (is_valid_type or is_valid_action):
            actionable.append((pf, prop))

    log(f"  Found {len(actionable)} actionable proposals (skipped {results['skipped_superseded']} superseded)")
    for pf, prop in actionable[:5]:  # Max 5 microtasks per cycle
        task_id = prop.get("candidate_id", Path(pf).stem)
        ctx = prop.get("context", {})
        prompt = f"""Execute bounty task: {ctx.get('title', 'unknown')}
URL: {ctx.get('url', 'N/A')}
Type: {prop.get('type')}
Instructions: Review the bounty requirements, prepare claim or submission, and report status.
Do NOT modify canonical ledgers. Write findings to proposals directory.
Provider: {GHOSTCLI_MODEL}"""
        
        result = run_claude_microtask(prompt, task_id)
        results["dispatched"] += 1
        
        if result["status"] in ("success", "success_raw"):
            results["completed"] += 1
            # Update proposal status
            prop["status"] = "microtask_completed"
            raw_output = result.get("output", "")
            if not isinstance(raw_output, str):
                raw_output = str(raw_output)
            prop["microtask_result"] = raw_output[:500]
            prop["completed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            save_json(pf, prop)
        else:
            results["failed"] += 1
            prop["status"] = "microtask_failed"
            raw_error = result.get("error", "unknown")
            if not isinstance(raw_error, str):
                raw_error = str(raw_error)
            prop["error"] = raw_error[:500]
            save_json(pf, prop)

    log(f"  Phase 2 result: {results}")
    return results

# ── Phase 3: Self-Review ──────────────────────────────────────────────
def phase3_self_review():
    """Validate microtask outputs before promoting to mirror."""
    log("PHASE 3: Self-review of completed microtasks")
    results = {"reviewed": 0, "approved": 0, "rejected": 0, "total_scanned": 0}

    # Scan ALL proposals, not just last 30 — completed microtasks may be anywhere
    proposal_files = sorted(glob.glob(str(PROPOSALS_DIR / "*.json")))
    results["total_scanned"] = len(proposal_files)
    for pf in proposal_files:
        prop = load_json(pf)
        if not prop or prop.get("status") != "microtask_completed":
            continue
        results["reviewed"] += 1
        
        # Basic validation: must have non-empty result
        output = prop.get("microtask_result", "")
        if len(output) > 50 and "error" not in output.lower():
            prop["status"] = "review_approved"
            results["approved"] += 1
        else:
            prop["status"] = "review_rejected"
            prop["rejection_reason"] = "insufficient_output_or_error_detected"
            results["rejected"] += 1
        save_json(pf, prop)

    log(f"  Phase 3 result: {results}")
    return results

# ── Phase 4: Discovery (Non-RTC Focus) ───────────────────────────────
def phase4_discovery():
    """Discover new bounties with autonomous payout paths (skip RTC-blocked)."""
    log("PHASE 4: Discovery (non-RTC autonomous bounties)")
    results = {"immunefi_new": 0, "research_promoted": 0, "proposals_created": 0, "skipped_rtc": 0}

    # Count fresh Immunefi opportunities (created today, high value)
    today = datetime.date.today().isoformat()
    opp_files = sorted(glob.glob(str(IMMUNEFI_OPPS_DIR / "*.json")))
    high_value = []
    for of in opp_files:
        opp = load_json(of)
        if not opp:
            continue
        discovered = opp.get("discovered_at", "")
        asset = opp.get("asset", "").lower()
        # Skip RTC assets
        if "rtc" in asset or "rustchain" in asset:
            results["skipped_rtc"] += 1
            continue
        if today in discovered and opp.get("max_bounty_usd", 0) >= 10000:
            high_value.append(opp)
            results["immunefi_new"] += 1

    log(f"  Fresh non-RTC high-value Immunefi: {results['immunefi_new']} (skipped RTC: {results['skipped_rtc']})")
    for hv in high_value[:3]:
        log(f"    {hv['name']}: ${hv.get('max_bounty_display', '?')} asset={hv.get('asset','?')}")
        # Create discovery proposal for top finds
        cid = f"immunefi-{hv.get('name','').replace(' ','-').lower()[:30]}-{int(time.time())}"
        proposal = {
            "candidate_id": cid,
            "type": "discovery_proposal",
            "status": "pending_qualification",
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "context": {
                "source": "immunefi_live",
                "title": hv.get("name", ""),
                "url": hv.get("url", ""),
                "asset": hv.get("asset", "unknown"),
                "gross": hv.get("max_bounty_usd", 0),
                "payout_type": hv.get("payout_type", "crypto")
            }
        }
        prop_hash = hashlib.sha256(json.dumps(proposal, sort_keys=True, default=str).encode()).hexdigest()[:12]
        save_json(PROPOSALS_DIR / f"{cid}-{prop_hash}.json", proposal)
        results["proposals_created"] += 1

    # Promote top research_queue item if non-RTC
    queue = load_json(QUEUE_PATH)
    if queue:
        rq = queue.get("research_queue", [])
        for item in rq[:5]:
            asset = item.get("asset", "").lower()
            if "rtc" in asset or "rustchain" in asset:
                results["skipped_rtc"] += 1
                continue
            results["research_promoted"] += 1
            log(f"  Top non-RTC research: {item.get('title', 'untitled')[:80]}")
            cid = item.get("candidate_id", f"research-{int(time.time())}")
            proposal = {
                "candidate_id": cid,
                "type": "discovery_proposal",
                "status": "pending_qualification",
                "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "context": {
                    "source": "research_queue",
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "asset": item.get("asset", "unknown"),
                    "gross": item.get("gross_verified", 0)
                }
            }
            prop_hash = hashlib.sha256(json.dumps(proposal, sort_keys=True, default=str).encode()).hexdigest()[:12]
            save_json(PROPOSALS_DIR / f"{cid}-{prop_hash}.json", proposal)
            results["proposals_created"] += 1
            break  # Only promote one per cycle

    log(f"  Phase 4 result: {results}")
    return results

# ── Phase 5: Cleanup & Mirror Sync ───────────────────────────────────
def phase5_cleanup_and_mirror():
    """Clean stale proposals and sync to private mirror."""
    log("PHASE 5: Cleanup and mirror sync")
    results = {"cleaned": 0, "mirror_synced": False}

    # Archive old completed/rejected proposals (>7 days)
    cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)).isoformat()
    proposal_files = sorted(glob.glob(str(PROPOSALS_DIR / "*.json")))
    archive_dir = PROPOSALS_DIR / "archive"
    archive_dir.mkdir(exist_ok=True)
    for pf in proposal_files:
        prop = load_json(pf)
        if not prop:
            continue
        status = prop.get("status", "")
        created = prop.get("created_at", "")
        if status in ("review_approved", "review_rejected", "abandoned") and created < cutoff:
            try:
                pf_path = Path(pf)
                pf_path.rename(archive_dir / pf_path.name)
                results["cleaned"] += 1
            except Exception as e:
                log(f"  Archive failed for {pf}: {e}", "WARN")

    # Sync to private mirror
    results["mirror_synced"] = sync_private_mirror()

    log(f"  Phase 5 result: {results}")
    return results

# ── Main Cycle ────────────────────────────────────────────────────────
def main():
    cycle_start = datetime.datetime.now(datetime.timezone.utc).isoformat()
    log("=== ORCHESTRATOR v4 CYCLE START ===")

    p1 = phase1_sweep_claims()
    p2 = phase2_microtask_orchestration()
    p3 = phase3_self_review()
    p4 = phase4_discovery()
    p5 = phase5_cleanup_and_mirror()

    cycle_state = {
        "version": 4,
        "last_run": cycle_start,
        "phase1_sweep": p1,
        "phase2_microtask": p2,
        "phase3_review": p3,
        "phase4_discovery": p4,
        "phase5_cleanup": p5,
        "next_cycle_minutes": 5
    }
    save_json(CYCLE_STATE_PATH, cycle_state)

    total_actions = (p1.get("proposals_created", 0) + p2.get("completed", 0) + 
                     p4.get("proposals_created", 0))
    log(f"=== CYCLE COMPLETE: {total_actions} actions, phases=[v4,{p1},{p2},{p3},{p4},{p5}] ===")

if __name__ == "__main__":
    main()
