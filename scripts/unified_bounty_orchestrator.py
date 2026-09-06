#!/usr/bin/env python3
"""
Unified 4-Phase Bounty Orchestrator v1.0
Implements sequential cycle every 5 minutes via systemd timer:
  Phase 1 (Claims): Execute pending claims via proposal_executor
  Phase 2 (Review/Fix): Scan executed claims for maintainer feedback, generate fix proposals
  Phase 3 (Code/Quality): Orchestrate Claude specialist microtasks via GhostCLI
  Phase 4 (Discovery): Scout new bounties via existing scanners

Provider: ghostcli-auto[1m] via ApiFable local (127.0.0.1:8787) only.
No OpenAI/Codex login. No direct ledger writes. Proposals go to /Agentic/data/aro/proposals/.
Gates preserved: Immunefi fail-closed, RTC bridge blocked, Gmail GitHub->TRASH only.
"""
import sys, os, json, subprocess, time, re, requests
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/Agentic")
LOG_FILE = ROOT / "logs" / "unified_orchestrator.log"
PROPOSALS_DIR = ROOT / "data" / "aro" / "proposals"
STATE_DIR = ROOT / "state"
PRIORITY_QUEUE = STATE_DIR / "bounty_priority_queue.json"
EXECUTOR_SCRIPT = ROOT / "scripts" / "proposal_executor.py"

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def load_json(path):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}

def save_json(path, data):
    path.write_text(json.dumps(data, indent=2, default=str))

def get_ghostcli_config():
    """Load GhostCLI config from env files. Provider: ghostcli-auto[1m] via ApiFable local."""
    env = {}
    for p in [Path("/root/.automaton/.env"), ROOT / ".env"]:
        if p.exists():
            for line in p.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    api_key = env.get("GHOSTCLI_API_KEY", "")
    base_url = env.get("GHOSTCLI_BASE_URL", "http://127.0.0.1:8787")
    model = env.get("GHOSTCLI_MODEL", "ghostcli-auto[1m]")
    # Strip ANSI codes and bracket suffixes
    model = re.sub(r'\x1b\[[0-9;]*m', '', model).split('[')[0].strip()
    if not model:
        model = "ghostcli-auto"
    return api_key, base_url, model

def ghostcli_call(prompt, max_tokens=2048):
    """Call GhostCLI/ApiFable local endpoint."""
    api_key, base_url, model = get_ghostcli_config()
    if not api_key:
        log("ERROR: No GHOSTCLI_API_KEY configured")
        return None
    # Normalize base_url to prevent double /v1/v1 path errors
    clean_base = base_url.rstrip('/')
    if clean_base.endswith('/v1'):
        url = f"{clean_base}/chat/completions"
    else:
        url = f"{clean_base}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.1
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=180)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log(f"GhostCLI call failed: {e}")
        return None

# --- PHASE 1: CLAIMS -------------------------------------------------------
def phase1_claims():
    """Execute pending claims via proposal_executor.py"""
    log("=== PHASE 1: CLAIMS ===")
    q = load_json(PRIORITY_QUEUE)
    aq = q.get("action_queue", [])
    open_claims = [x for x in aq if x.get("status") == "open" and x.get("action") == "claim"]
    log(f"Open claims in queue: {len(open_claims)}")
    if not open_claims:
        log("No open claims to execute.")
        return 0
    # Run proposal executor which processes all pending proposals
    try:
        result = subprocess.run(
            [sys.executable, str(EXECUTOR_SCRIPT)],
            capture_output=True, text=True, timeout=None, cwd=str(ROOT)
        )
        # Count actual .executed marker files instead of parsing stdout text
        import glob as _glob
        executed_count = len(_glob.glob(str(PROPOSALS_DIR / "*.json.executed")))
        log(f"Executor completed. Total executed markers on disk: {executed_count}")
        if result.returncode != 0:
            log(f"Executor stderr: {result.stderr[:500]}")
        return executed_count
    except Exception as e:
        log(f"Executor failed: {e}")
        return 0

# --- PHASE 2: REVIEW/FIX ---------------------------------------------------
def phase2_review_fix():
    """Scan executed claims for maintainer feedback, generate fix proposals."""
    log("=== PHASE 2: REVIEW/FIX ===")
    executed_markers = list(PROPOSALS_DIR.glob("*.json.executed"))
    log(f"Scanning {len(executed_markers)} executed claims for feedback...")
    feedback_found = 0
    from datetime import datetime, timezone, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
    recent_markers = []
    for m in executed_markers:
        try:
            mtime = datetime.fromtimestamp(m.stat().st_mtime, tz=timezone.utc)
            if mtime >= cutoff:
                recent_markers.append(m)
        except Exception:
            continue
    log(f"Recent markers (last 6h): {len(recent_markers)}")
    for marker in recent_markers:
        orig_path = PROPOSALS_DIR / marker.name.replace(".executed", "")
        if not orig_path.exists():
            continue
        try:
            prop = json.loads(orig_path.read_text())
        except Exception:
            continue
        candidate_id = prop.get("candidate_id", "")
        url = prop.get("url", "")
        if not url or "github.com" not in url:
            continue
        if prop.get("feedback_scanned_at"):
            scanned = prop.get("feedback_scanned_at", "")
            try:
                scanned_dt = datetime.fromisoformat(scanned.replace("Z", "+00:00"))
                if scanned_dt >= cutoff:
                    continue
            except Exception:
                pass
        # Check for maintainer feedback via gh CLI
        try:
            parts = url.rstrip("/").split("/")
            owner, repo, kind, number = parts[-4], parts[-3], parts[-2], parts[-1]
            if kind not in ("issues", "pull"):
                continue
            cmd = ["gh", "issue" if kind == "issues" else "pr", "view", number,
                   "--repo", f"{owner}/{repo}", "--json", "comments", "--jq",
                   ".comments[-5:] | .[] | select(.author.login != \"rafaio1\") | {author: .author.login, body: .body}"]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode == 0 and r.stdout.strip():
                import re as _re
                comment_blocks = r.stdout.strip().split("\n")
                actionable = False
                lapsed = False
                live_url_needed = False
                for block in comment_blocks:
                    bl = block.lower()
                    if "claim lapsed" in bl or "bounty is open again" in bl:
                        lapsed = True
                        actionable = True
                    if "live-url" in bl or "published piece" in bl:
                        live_url_needed = True
                        actionable = True
                    if any(kw in bl for kw in ["fix", "change", "update", "wrong", "error", "fail", "reject", "revision"]):
                        actionable = True
                if actionable:
                    feedback_found += 1
                    feedback_type = "lapsed" if lapsed else ("live_url" if live_url_needed else "code_fix")
                    fix_prompt = f"""You are a senior developer. A bounty claim received maintainer feedback.
Bounty: {prop.get('title', 'N/A')}
URL: {url}
Candidate ID: {candidate_id}
Feedback Type: {feedback_type}

Feedback:
{r.stdout.strip()[:2000]}

Generate a {'reclaim strategy' if lapsed else 'fix proposal'} as JSON:
{{"candidate_id": "{candidate_id}", "fix_type": "{feedback_type}", "action_needed": "...", "description": "...", "priority": "high|medium|low"}}
For lapsed claims: explain whether to re-claim or skip.
For live_url claims: identify what needs publishing and where.
Only propose actions you are >80% confident will address the feedback."""
                    response = ghostcli_call(fix_prompt, max_tokens=1500)
                    if response:
                        fix_proposal = {
                            "type": "fix_proposal",
                            "feedback_type": feedback_type,
                            "source_candidate": candidate_id,
                            "generated_at": datetime.now(timezone.utc).isoformat(),
                            "raw_response": response[:3000]
                        }
                        # Sanitize candidate_id for filesystem safety (replace / and : with _)
                        safe_cid = candidate_id.replace("/", "_").replace(":", "_")
                        fix_path = PROPOSALS_DIR / f"fix-{safe_cid}-{int(time.time())}.json"
                        fix_path.write_text(json.dumps(fix_proposal, indent=2, default=str))
                        log(f"Generated fix proposal for {candidate_id}: {fix_path.name}")
                prop["feedback_scanned_at"] = datetime.now(timezone.utc).isoformat()
                orig_path.write_text(json.dumps(prop, indent=2, default=str))
        except Exception as e:
            log(f"Review scan error for {candidate_id}: {e}")
            continue
        time.sleep(1)  # Rate limit
    log(f"Phase 2 complete. Feedback items processed: {feedback_found}")
    return feedback_found

# --- PHASE 3: CODE/QUALITY -------------------------------------------------
def phase3_code_quality():
    """Orchestrate Claude specialist microtasks for code generation and quality."""
    log("=== PHASE 3: CODE/QUALITY ===")
    # Find fix proposals that haven't been acted on
    fix_proposals = list(PROPOSALS_DIR.glob("fix-*.json"))
    unprocessed = []
    for fp in fix_proposals:
        try:
            data = json.loads(fp.read_text())
            if not data.get("acted_on") and not data.get("execution_failed"):
                unprocessed.append((fp, data))
        except Exception:
            continue
    log(f"Unprocessed fix proposals: {len(unprocessed)}")
    processed = 0
    for fp, data in unprocessed[:5]:  # Process up to 5 per cycle
        candidate_id = data.get("source_candidate", "unknown")
        raw = data.get("raw_response", "")
        # Skip non-actionable proposals (already reviewed as SKIP/WAIT/NO-ACTION)
        action_needed = ""
        try:
            parsed_raw = json.loads(raw.strip().strip('`').replace('json\n','').replace('\n```',''))
            action_needed = parsed_raw.get("action_needed", "").lower()
        except Exception:
            pass
        skip_keywords = ["skip", "wait", "no-action", "no action", "monitor only", "not actionable"]
        if any(kw in action_needed for kw in skip_keywords):
            data["acted_on"] = True
            data["skip_reason"] = "non_actionable_feedback"
            data["skipped_at"] = datetime.now(timezone.utc).isoformat()
            fp.write_text(json.dumps(data, indent=2, default=str))
            log(f"Skipped non-actionable proposal: {candidate_id}")
            continue

        # For actionable proposals: generate code implementation plan + execute
        exec_prompt = f"""You are a senior bounty hunter developer. Given this fix proposal, produce a concrete implementation plan.

Fix Proposal:
{raw[:3000]}

Output valid JSON with exactly these fields:
{{
  "approved": true,
  "repo": "owner/repo-name",
  "branch_name": "fix/descriptive-branch-name",
  "files_to_modify": [{{"path": "src/file.ts", "changes_description": "what to change"}}],
  "new_files": [{{"path": "src/new_file.ts", "content_outline": "description"}}],
  "test_plan": "how to verify the fix works",
  "commit_message": "conventional commit message",
  "pr_title": "PR title",
  "pr_body": "PR description referencing the issue",
  "estimated_hours": 2,
  "security_notes": "any security considerations or null if none"
}}

Be specific about file paths and changes. Base your plan on the actual repository structure implied by the issue."""
        plan_response = ghostcli_call(exec_prompt, max_tokens=2048)
        if not plan_response:
            log(f"Failed to get execution plan for {candidate_id}")
            continue

        # Parse and validate the plan
        try:
            clean_resp = plan_response.strip()
            if clean_resp.startswith("```"):
                clean_resp = clean_resp.split("\n", 1)[1].rsplit("```", 1)[0]
            plan = json.loads(clean_resp)
            if not plan.get("approved") or not plan.get("repo"):
                data["quality_review"] = {"approved": False, "reason": "plan_not_approved"}
                data["reviewed_at"] = datetime.now(timezone.utc).isoformat()
                fp.write_text(json.dumps(data, indent=2, default=str))
                log(f"Plan not approved for {candidate_id}")
                processed += 1
                continue
        except (json.JSONDecodeError, KeyError) as e:
            log(f"Failed to parse plan for {candidate_id}: {e}")
            data["execution_failed"] = True
            data["failure_reason"] = f"plan_parse_error: {str(e)[:200]}"
            data["failed_at"] = datetime.now(timezone.utc).isoformat()
            fp.write_text(json.dumps(data, indent=2, default=str))
            continue

        # --- Structural validation gate (post-parse) -------------------------
        # Reject plans that reference paths not present in the target repo.
        try:
            import subprocess, tempfile, os
            repo_name = plan.get("repo", "")
            if "/" in repo_name and repo_name.count("/") == 1:
                with tempfile.TemporaryDirectory() as td:
                    clone_url = f"https://github.com/{repo_name}.git"
                    subprocess.run(
                        ["git", "clone", "--depth=1", clone_url, td],
                        capture_output=True, timeout=60
                    )
                    missing = []
                    for f in plan.get("files_to_modify", []):
                        p = f.get("path")
                        if p and not os.path.exists(os.path.join(td, p)):
                            missing.append(p)
                    for f in plan.get("new_files", []):
                        p = f.get("path")
                        if p:
                            parent = os.path.dirname(os.path.join(td, p))
                            if not os.path.isdir(parent):
                                missing.append(f"{p} (parent dir missing)")
                    if missing:
                        data["execution_failed"] = True
                        data["failure_reason"] = f"hallucinated_paths: {missing[:5]}"
                        data["failed_at"] = datetime.now(timezone.utc).isoformat()
                        fp.write_text(json.dumps(data, indent=2, default=str))
                        log(f"Plan rejected for {candidate_id}: paths not in repo {missing[:3]}")
                        processed += 1
                        continue
        except Exception as e:
            log(f"Structural validation skipped for {candidate_id}: {e}")

        # Store the execution plan and mark for Phase 1 execution
        data["execution_plan"] = plan
        data["quality_review"] = {"approved": True, "plan_generated": True}
        data["reviewed_at"] = datetime.now(timezone.utc).isoformat()
        data["ready_for_execution"] = True
        fp.write_text(json.dumps(data, indent=2, default=str))
        processed += 1
        log(f"Execution plan generated for {candidate_id} -> {plan.get('repo')}")
        time.sleep(1)
    log(f"Phase 3 complete. Proposals reviewed: {processed}")
    return processed

# --- PHASE 4: DISCOVERY ----------------------------------------------------
def phase4_discovery():
    """Scout new bounties via existing scanners."""
    log("=== PHASE 4: DISCOVERY ===")
    # Trigger existing discovery scripts asynchronously with strict timeouts
    discovery_scripts = [
        ROOT / "scripts" / "agentic_superteam_large_bounty_scout.py",
        ROOT / "scripts" / "agentic_superteam_usdc_scout.py",
        ROOT / "scripts" / "algora_bounty_scanner.py",
        ROOT / "scripts" / "rustchain_bounty_scout.py",
        ROOT / "scripts" / "immunefi_live_scanner.py",
        ROOT / "scripts" / "code4rena_contest_scanner.py",
        ROOT / "scripts" / "sherlock_audit_scanner.py",
        ROOT / "scripts" / "gitcoin_bounty_scanner.py",
        ROOT / "scripts" / "layer3_bounty_scanner.py",
        ROOT / "scripts" / "dework_bounty_scanner.py",
        ROOT / "scripts" / "github_usdc_bounty_scanner.py",
    ]
    triggered = 0
    procs = []
    for script in discovery_scripts:
        if script.exists():
            try:
                p = subprocess.Popen(
                    [sys.executable, str(script)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    cwd=str(ROOT)
                )
                procs.append((script.name, p))
                triggered += 1
                log(f"Triggered discovery: {script.name}")
            except Exception as e:
                log(f"Discovery script {script.name} failed: {e}")
    # Wait up to 45s total for all discovery scripts; kill stragglers
    deadline = time.time() + 120
    for name, p in procs:
        remaining = max(1, int(deadline - time.time()))
        try:
            p.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            log(f"Discovery script {name} killed after timeout")
    # Also run gh search for fresh bounties
    try:
        cmd = 'gh search issues "label:bounty state:open" --limit 10 --json repository,title,url,createdAt --jq ".[] | select(.createdAt > \\"2026-09-05\\")"'
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20)
        if r.returncode == 0 and r.stdout.strip():
            items = json.loads(f"[{r.stdout.strip()}]") if r.stdout.strip().startswith("{") else []
            log(f"GitHub search found {len(items)} recent bounty issues")
    except Exception as e:
        log(f"GitHub search failed: {e}")
    # Refresh priority queue after discovery
    pq_script = ROOT / "scripts" / "bounty_priority_queue.py"
    if pq_script.exists():
        try:
            subprocess.run([sys.executable, str(pq_script)],
                         capture_output=True, text=True, timeout=30, cwd=str(ROOT))
            log("Priority queue refreshed after discovery")
        except Exception as e:
            log(f"Priority queue refresh failed: {e}")
    log(f"Phase 4 complete. Discovery scripts triggered: {triggered}")
    return triggered

# --- MAIN CYCLE ------------------------------------------------------------
def run_cycle():
    """Execute one full 4-phase orchestration cycle."""
    cycle_start = datetime.now(timezone.utc)
    log("=" * 60)
    log("UNIFIED BOUNTY ORCHESTRATOR v1.0 - CYCLE START")
    log("=" * 60)

    results = {}
    results["phase1_claims"] = phase1_claims()
    results["phase2_review"] = phase2_review_fix()
    results["phase3_quality"] = phase3_code_quality()
    results["phase4_discovery"] = phase4_discovery()

    elapsed = (datetime.now(timezone.utc) - cycle_start).total_seconds()
    log(f"Cycle complete in {elapsed:.1f}s. Results: {json.dumps(results)}")

    # Save cycle state
    cycle_state = {
        "last_cycle_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": elapsed,
        "results": results,
        "provider": "ghostcli-auto[1m]",
        "api_endpoint": "http://127.0.0.1:8787"
    }
    save_json(STATE_DIR / "unified_orchestrator_state.json", cycle_state)
    return results

if __name__ == "__main__":
    log("Unified Bounty Orchestrator v1.0 starting (single-cycle mode)")
    run_cycle()
