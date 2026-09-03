#!/usr/bin/env python3
"""Autonomous Bounty Sweeper - 5min cycle orchestrator.

Scans ledger/state, identifies actionable bounties, dispatches specialist
Codex chats via GhostCLI, monitors progress, and reviews outcomes.
Read-only on canonical ledgers; writes only to proposals/ and logs/.
"""
import json, os, sys, time, subprocess, hashlib, datetime as dt
import concurrent.futures
from pathlib import Path

ROOT = Path("/Agentic")
STATE = ROOT / "state"
LOGS = ROOT / "logs" / "supervisor"
PROPOSALS = ROOT / "data" / "aro" / "proposals"
LEDGER = ROOT / "data" / "aro" / "bounty_receive_ledger.json"
QUEUE = STATE / "bounty_priority_queue.json"
ROUTE_MAP = STATE / "payout_route_map.json"
WALLETS = ROOT / "data" / "aro" / "receive-wallets.json"
SWEEP_STATE = STATE / "autonomous_sweep_state.json"

LOGS.mkdir(parents=True, exist_ok=True)
PROPOSALS.mkdir(parents=True, exist_ok=True)

def now_iso():
    return dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def load_json(p):
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return None

def save_json(p, data):
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, p)

def ledger_entries():
    d = load_json(LEDGER)
    if not d: return []
    if isinstance(d, dict):
        return d.get("entries", [])
    return d if isinstance(d, list) else []

def actionable_filter(entries):
    """Select entries that can progress autonomously right now."""
    out = []
    for e in entries:
        if not isinstance(e, dict): continue
        s = e.get("status","")
        rail = e.get("rail_id","")
        # Normalize rail_id for matching against wallet registry aliases
        norm_rail = rail.replace("crypto_","").replace("_spl","").replace("_trc20","_tron") if isinstance(rail,str) else ""
        if s in ("candidate","submitted") and (rail in (
            "crypto_usdt_polygon","crypto_usdt_trc20","solana_spl","usdt_polygon","usdt_tron") or norm_rail in ("usdt_polygon","usdt_tron","solana")):
            out.append(e)
    return out

RAIL_ALIASES = {
    "crypto_usdt_polygon": ["usdt_polygon","polygon_usdt"],
    "crypto_usdt_trc20": ["usdt_tron","trc20_usdt","usdt_trx"],
    "solana_spl": ["solana","sol","spl_usdc","usdc_solana"],
}

def dispatch_codex_specialist(task_spec: dict) -> dict:
    """Spawn a Codex chat via ghostcli-auto[1m] for a specific bounty task."""
    prompt = task_spec.get("prompt","")
    if not prompt:
        return {"ok": False, "error": "empty_prompt"}
    cmd = [
        "/root/.local/bin/codex", "exec",
        "-m", "ghostcli-auto[1m]",
        "--skip-git-repo-check",
        "-c", 'shell_environment_policy.inherit="all"',
        "-s", "danger-full-access",
        prompt
    ]
    try:
        # Reduced timeout to 120s to prevent single-agent blocking of 5min cycle
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=None, cwd=str(ROOT))
        return {"ok": r.returncode == 0, "rc": r.returncode,
                "stdout": r.stdout[-4000:], "stderr": r.stderr[-2000:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except FileNotFoundError:
        return {"ok": False, "error": "codex_not_found"}

def build_task(entry):
    """Build a specialist prompt for one bounty."""
    bid = entry.get("bounty_key") or entry.get("issue_or_pr") or "unknown"
    repo = entry.get("repo","")
    rail = entry.get("rail_id","")
    status = entry.get("status","")
    wallet_addr = None
    wdata = load_json(WALLETS)
    if wdata:
        items = wdata.get("items",[]) if isinstance(wdata,dict) else []
        # Try exact match first, then aliases
        candidates = [rail] + RAIL_ALIASES.get(rail, [])
        for c in candidates:
            for it in items:
                if isinstance(it,dict) and it.get("rail_id")==c:
                    wallet_addr = it.get("address")
                    if wallet_addr:
                        break
            if wallet_addr:
                break
    prompt = f"""You are a bounty execution specialist. Repo: {repo}. Bounty key: {bid}. Current status: {status}. Rail: {rail}. Receive address: {wallet_addr}.

Your job:
1. Check the latest issue/PR state on GitHub for this bounty.
2. If claim is missing or lapsed, prepare a /claim comment draft (do NOT post).
3. If work is submitted but unmerged, summarize review feedback and next fix.
4. If payout info changed, note new rail/amount.
5. Output a JSON proposal to /Agentic/data/aro/proposals/ with fields: bounty_key, action, evidence_url, proposed_comment, next_status, risks.

Do NOT modify canonical ledgers. Do NOT post comments. Read-only investigation + proposal file only."""
    return {"bounty_key": bid, "prompt": prompt}

def phase_claims_finalize(entries):
    """Phase 1: Finalize claims and lapsed bounties."""
    results = []
    for e in entries:
        status = e.get("status", "")
        if status in ("claim_lapsed", "claim_expired", "open_again"):
            task = build_task(e)
            task["prompt"] += "\n\nPHASE 1 DIRECTIVE: This bounty claim has lapsed. Draft a fresh /claim comment. Do NOT post."
            res = dispatch_codex_specialist(task)
            res["phase"] = "claims_finalize"
            res["bounty_key"] = task["bounty_key"]
            results.append(res)
    return results

def phase_review_adjust(entries):
    """Phase 2: Review feedback on submitted PRs and adjust."""
    results = []
    for e in entries:
        status = e.get("status", "")
        if status in ("submitted", "pr_open", "review_feedback_pending"):
            task = build_task(e)
            task["prompt"] += "\n\nPHASE 2 DIRECTIVE: Review latest PR feedback. Summarize required fixes. Output proposal with action=fix_review_feedback."
            res = dispatch_codex_specialist(task)
            res["phase"] = "review_adjust"
            res["bounty_key"] = task["bounty_key"]
            results.append(res)
    return results

def phase_code_microtask(entries):
    """Phase 3: Dispatch coding/microtask work to specialist agents."""
    results = []
    for e in entries:
        status = e.get("status", "")
        if status in ("claimed", "in_progress", "coding"):
            task = build_task(e)
            task["prompt"] += "\n\nPHASE 3 DIRECTIVE: Execute coding/microtask. Produce patch or implementation. Output proposal with action=submit_work."
            res = dispatch_codex_specialist(task)
            res["phase"] = "code_microtask"
            res["bounty_key"] = task["bounty_key"]
            results.append(res)
    return results

def phase_discovery():
    """Phase 4: Discover new high-value bounties from priority queue."""
    results = []
    q = load_json(QUEUE)
    if not q:
        return results
    research = q.get("research_queue", [])
    for item in research[:3]:
        bid = item.get("bounty_key") or item.get("issue_or_pr") or "unknown"
        repo = item.get("repo", "")
        prompt = f"""You are a bounty discovery specialist. Repo: {repo}. Bounty key: {bid}.

PHASE 4 DIRECTIVE: Investigate this bounty for autonomous eligibility. Check scope, payout rail, and claim requirements. Output proposal to /Agentic/data/aro/proposals/ with action=qualify or action=abandon. Do NOT modify ledgers."""
        task = {"bounty_key": bid, "prompt": prompt}
        res = dispatch_codex_specialist(task)
        res["phase"] = "discovery"
        res["bounty_key"] = bid
        results.append(res)
    return results

def validate_proposal_quality(proposal_dir):
    """Quality gate: ensure proposals have evidence_url and actionable action."""
    valid = 0
    invalid = 0
    for p in Path(proposal_dir).glob("*.json"):
        data = load_json(p)
        if not data:
            invalid += 1
            continue
        action = data.get("action", "")
        evidence = data.get("evidence_url", "")
        if action and action != "blocked_no_network" and evidence:
            valid += 1
        else:
            invalid += 1
    return {"valid": valid, "invalid": invalid}

def sweep_cycle():
    started = now_iso()
    entries = ledger_entries()
    candidates = actionable_filter(entries)

    # Bounded concurrency: max 3 concurrent Codex specialists across ALL phases
    # to prevent exceeding the 5-minute systemd timer window.
    MAX_WORKERS = 3
    PHASE_TIMEOUT_S = 60  # soft cap per phase; tasks already have 120s subprocess timeout

    def run_phase(phase_fn, *args):
        """Execute a phase function with a wall-clock timeout."""
        import threading
        result_container = {"value": []}
        exc_container = {"error": None}

        def target():
            try:
                result_container["value"] = phase_fn(*args)
            except Exception as e:
                exc_container["error"] = str(e)

        t = threading.Thread(target=target)
        t.start()
        t.join(timeout=None)
        if t.is_alive():
            # Phase exceeded timeout; return partial/empty and log
            return [], {"timeout": True, "phase": getattr(phase_fn, "__name__", "unknown")}
        if exc_container["error"]:
            return [], {"error": exc_container["error"], "phase": getattr(phase_fn, "__name__", "unknown")}
        return result_container["value"], None

    # Collect all dispatchable tasks first, then execute with bounded pool
    task_specs = []

    # Phase 1: Claims/Finalize
    for e in candidates:
        status = e.get("status", "")
        if status in ("claim_lapsed", "claim_expired", "open_again", "candidate"):
            task = build_task(e)
            if status == "candidate":
                task["prompt"] += "\n\nPHASE 1 DIRECTIVE: New candidate bounty. Validate scope, payout rail, and autonomous feasibility. If viable, draft /claim comment. Output proposal with action=qualify_claim or action=abandon. Do NOT post or modify ledgers."
            else:
                task["prompt"] += "\n\nPHASE 1 DIRECTIVE: This bounty claim has lapsed. Draft a fresh /claim comment. Do NOT post."
            task["_phase"] = "claims_finalize"
            task_specs.append(task)

    # Phase 2: Review/Adjust
    for e in candidates:
        status = e.get("status", "")
        if status in ("submitted", "pr_open", "review_feedback_pending"):
            task = build_task(e)
            task["prompt"] += "\n\nPHASE 2 DIRECTIVE: Review latest PR feedback. Summarize required fixes. Output proposal with action=fix_review_feedback."
            task["_phase"] = "review_adjust"
            task_specs.append(task)

    # Phase 3: Code/Microtask
    for e in candidates:
        status = e.get("status", "")
        if status in ("claimed", "in_progress", "coding"):
            task = build_task(e)
            task["prompt"] += "\n\nPHASE 3 DIRECTIVE: Execute coding/microtask. Produce patch or implementation. Output proposal with action=submit_work."
            task["_phase"] = "code_microtask"
            task_specs.append(task)

    # Phase 4: Discovery (from priority queue)
    q = load_json(QUEUE)
    if q:
        research = q.get("research_queue", [])
        for item in research[:3]:
            bid = item.get("bounty_key") or item.get("issue_or_pr") or "unknown"
            repo = item.get("repo", "")
            prompt = f"""You are a bounty discovery specialist. Repo: {repo}. Bounty key: {bid}.

PHASE 4 DIRECTIVE: Investigate this bounty for autonomous eligibility. Check scope, payout rail, and claim requirements. Output proposal to /Agentic/data/aro/proposals/ with action=qualify or action=abandon. Do NOT modify ledgers."""
            task_specs.append({"bounty_key": bid, "prompt": prompt, "_phase": "discovery"})

    # Execute all collected tasks with bounded ThreadPoolExecutor
    all_results = []
    phase_errors = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_task = {executor.submit(dispatch_codex_specialist, t): t for t in task_specs}
        for future in concurrent.futures.as_completed(future_to_task, timeout=None):
            task = future_to_task[future]
            try:
                res = future.result(timeout=None)
                res["phase"] = task.get("_phase", "unknown")
                res["bounty_key"] = task.get("bounty_key", "unknown")
                all_results.append(res)
            except concurrent.futures.TimeoutError:
                all_results.append({"ok": False, "error": "future_timeout", "phase": task.get("_phase"), "bounty_key": task.get("bounty_key")})
            except Exception as e:
                all_results.append({"ok": False, "error": str(e), "phase": task.get("_phase"), "bounty_key": task.get("bounty_key")})

    dispatched = sum(1 for r in all_results if r.get("ok"))
    errors = sum(1 for r in all_results if not r.get("ok"))

    # Quality gate
    quality = validate_proposal_quality(PROPOSALS)

    # Per-phase counts from results
    phase_counts = {}
    for r in all_results:
        ph = r.get("phase", "unknown")
        phase_counts[ph] = phase_counts.get(ph, 0) + 1

    summary = {
        "cycle_started_at": started,
        "cycle_finished_at": now_iso(),
        "phases": phase_counts,
        "candidates_total": len(candidates),
        "tasks_queued": len(task_specs),
        "dispatched": dispatched,
        "errors": errors,
        "quality_gate": quality,
        "max_workers": MAX_WORKERS,
        "phase_timeout_s": PHASE_TIMEOUT_S,
        "results": all_results
    }
    save_json(SWEEP_STATE, summary)
    log_path = LOGS / f"sweep-{started.replace(':','-')}.json"
    save_json(log_path, summary)
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    sweep_cycle()
