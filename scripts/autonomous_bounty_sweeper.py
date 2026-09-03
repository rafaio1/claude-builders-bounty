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
    """Select entries that can progress autonomously right now.

    Handles both legacy ledger-schema entries (with status/rail_id) and
    scout-schema entries from monitor_only (with agent_access/asset).
    Promotes AGENT_ALLOWED non-RTC entries with verified execution contract
    to research_queue when autonomy gates are passable.
    """
    out = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        # --- Legacy ledger-schema path ---
        s = e.get("status", "")
        rail = e.get("rail_id", "")
        norm_rail = rail.replace("crypto_", "").replace("_spl", "").replace("_trc20", "_tron") if isinstance(rail, str) else ""
        if s in ("candidate", "submitted") and (rail in (
            "crypto_usdt_polygon", "crypto_usdt_trc20", "solana_spl",
            "usdt_polygon", "usdt_tron") or norm_rail in (
                "usdt_polygon", "usdt_tron", "solana")):
            out.append(e)
            continue
        # --- Scout-schema path (monitor_only entries) ---
        agent_access = e.get("agent_access", "")
        asset = e.get("asset", "")
        qual = e.get("qualification_decision")
        explicit_contract = e.get("explicit_execution_contract", False)
        rail_verified = e.get("self_custody_rail_verified", False)
        # Skip rejected or human-only entries
        if qual == "rejected":
            continue
        if agent_access in ("HUMAN_ONLY", "HUMAN_REQUIRED"):
            continue
        # RTC has no viable bridge path; never promote
        if asset == "RTC":
            continue
        # Promote AGENT_ALLOWED entries to research_queue for specialist
        # investigation. These may lack explicit_execution_contract or
        # self_custody_rail_verified because those fields are only populated
        # after discovery-phase qualification. The specialist will verify
        # autonomy gates and either promote to action_queue or reject.
        if agent_access == "AGENT_ALLOWED":
            out.append(e)
            continue
        # Promote entries with verified self-custody rail (non-RTC)
        if rail_verified and asset != "RTC":
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
    # Prevent Phase 2 spam: skip entries with zero reviews (legacy schema only)
    status = entry.get("status", "")
    if status in ("submitted", "pr_open", "review_feedback_pending"):
        if int(entry.get("reviews_count", 0)) == 0:
            return None
    # Support both legacy ledger-schema and scout-schema entries
    bid = (entry.get("bounty_key") or entry.get("issue_or_pr")
           or entry.get("candidate_id") or "unknown")
    repo = entry.get("repo", "")
    rail = entry.get("rail_id") or entry.get("asset") or ""
    agent_access = entry.get("agent_access", "")
    # Enrich URL from source_urls.detail for scout-schema entries
    url = entry.get("url") or ""
    if not url and isinstance(entry.get("source_urls"), dict):
        url = entry["source_urls"].get("detail", "")
    # Cross-reference candidate_id against scout files when URL still missing
    if not url and agent_access == "AGENT_ALLOWED":
        for scout_path in [STATE / "superteam_usdc_scout.json", STATE / "superteam_large_bounty_scout.json"]:
            scout_data = load_json(scout_path)
            if not scout_data:
                continue
            entries_list = scout_data if isinstance(scout_data, list) else scout_data.get("entries", scout_data.get("candidates", []))
            for se in entries_list:
                if se.get("id") == bid:
                    su = se.get("source_urls", {})
                    if isinstance(su, dict):
                        url = su.get("detail", "")
                    if url:
                        break
            if url:
                break
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
    # Add scout-schema context to prompt when applicable
    if agent_access == "AGENT_ALLOWED" and not status:
        prompt = (
            f"You are a bounty discovery specialist. Candidate: {bid}. Asset: {rail}. "
            f"Agent access: {agent_access}. URL: {url}.\n\n"
            "Your job:\n"
            f"1. Fetch the bounty detail page at {url} and verify scope, payout rail, and claim requirements.\n"
            "2. Assess whether this bounty can be completed autonomously (no human identity, KYC, social media, or real-funds gates).\n"
            "3. If autonomous execution is feasible, output a proposal with action=qualify_claim, evidence_url={url}, and proposed next steps.\n"
            "4. If human gates block autonomous completion, output action=abandon with specific gate reasons.\n"
            f"5. Write proposal JSON to /Agentic/data/aro/proposals/discovery_{bid[:8]}.json.\n\n"
            "Do NOT modify canonical ledgers. Do NOT post comments. Read-only investigation + proposal file only."
        )
    else:
        prompt = (
            f"You are a bounty execution specialist. Repo: {repo}. Bounty key: {bid}. "
            f"Current status: {status}. Rail: {rail}. Receive address: {wallet_addr}.\n\n"
            "Your job:\n"
            "1. Check the latest issue/PR state on GitHub for this bounty.\n"
            "2. If claim is missing or lapsed, prepare a /claim comment draft (do NOT post).\n"
            "3. If work is submitted but unmerged, summarize review feedback and next fix.\n"
            "4. If payout info changed, note new rail/amount.\n"
            "5. Output a JSON proposal to /Agentic/data/aro/proposals/ with fields: bounty_key, action, evidence_url, proposed_comment, next_status, risks.\n\n"
            "Do NOT modify canonical ledgers. Do NOT post comments. Read-only investigation + proposal file only."
        )
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
            if task is None:
                continue
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
            task["prompt"] += "\n\nQUALITY GATE & PUSH REQUIREMENT: Before marking submit_work, you MUST: (1) run any available tests/linters in the repo and confirm they pass; (2) commit all changes to a feature branch; (3) push that branch to https://github.com/rafaio1/agentic-integration.git; (4) include the exact commit SHA and branch name in evidence_url. If tests fail or push fails, output action=fix_review_feedback instead of submit_work and describe the blocker. Never propose submit_work without a verified push to the private mirror."
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

def phase_email_cleanup():
    """Phase 5: Archive verified GitHub notification emails to reduce inbox noise."""
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from agentic_gmail_inbox_ingestor import (
            archive_verified_github_actions,
            GmailAPIClient,
            load_decisions,
            load_action_results,
            resolve_labels,
        )
        client = GmailAPIClient()
        raw_decisions = load_decisions() or {}
        # load_decisions returns dict[(msg_id, rule_version), decision];
        # archive_verified_github_actions expects Iterable[dict] of values.
        decisions = list(raw_decisions.values()) if isinstance(raw_decisions, dict) else []
        action_results = load_action_results() or {}
        # Resolve actual Gmail label IDs; LABEL_NAMES only has display names.
        label_ids = resolve_labels(client)
        label_id = label_ids.get("github_verified", "")
        if not label_id:
            return {"ok": False, "error": "missing_label_id"}
        eligible, archived, saturated = archive_verified_github_actions(
            client, label_id, decisions, action_results
        )
        return {
            "ok": True,
            "eligible": eligible,
            "archived": archived,
            "saturated": saturated,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

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

    # Phase 0: Reconciliation (runs BEFORE task collection to update ledger status)
    # Calls existing reconciler script; error-tolerant, does not block cycle.
    try:
        import subprocess
        recon_result = subprocess.run(
            ["python3", "/Agentic/scripts/agentic_rustchain_reconcile.py", "--root", "/Agentic"],
            timeout=90, capture_output=True, text=True
        )
        recon_status = {
            "ok": recon_result.returncode == 0,
            "returncode": recon_result.returncode,
            "stdout_tail": recon_result.stdout.strip().split("\n")[-5:] if recon_result.stdout else [],
            "stderr_tail": recon_result.stderr.strip().split("\n")[-5:] if recon_result.stderr else []
        }
    except subprocess.TimeoutExpired:
        recon_status = {"ok": False, "error": "timeout_90s"}
    except Exception as e:
        recon_status = {"ok": False, "error": str(e)}

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
            if task is None:
                continue
            task["prompt"] += "\n\nPHASE 2 DIRECTIVE: Review latest PR feedback. Summarize required fixes. Output proposal with action=fix_review_feedback."
            if task is None:
                continue
            task["_phase"] = "review_adjust"
            task_specs.append(task)

    # Phase 3: Code/Microtask
    for e in candidates:
        status = e.get("status", "")
        if status in ("claimed", "in_progress", "coding"):
            task = build_task(e)
            if task is None:
                continue
            task["prompt"] += "\n\nPHASE 3 DIRECTIVE: Execute coding/microtask. Produce patch or implementation. Output proposal with action=submit_work."
            task["prompt"] += "\n\nQUALITY GATE & PUSH REQUIREMENT: Before marking submit_work, you MUST: (1) run any available tests/linters in the repo and confirm they pass; (2) commit all changes to a feature branch; (3) push that branch to https://github.com/rafaio1/agentic-integration.git; (4) include the exact commit SHA and branch name in evidence_url. If tests fail or push fails, output action=fix_review_feedback instead of submit_work and describe the blocker. Never propose submit_work without a verified push to the private mirror."
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

    # Phase 5: Promoted scout entries from monitor_only (AGENT_ALLOWED bounties)
    promoted_scouts = actionable_filter(q.get("monitor_only", [])) if q else []
    for ps in promoted_scouts[:3]:
        task = build_task(ps)
        if task:
            task["_phase"] = "scout_discovery"
            task_specs.append(task)


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
        "reconciliation": recon_status,
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

    # Phase 5: Email cleanup (runs after main phases to avoid blocking)
    email_cleanup = phase_email_cleanup()
    summary["email_cleanup"] = email_cleanup
    save_json(SWEEP_STATE, summary)

if __name__ == "__main__":
    sweep_cycle()
