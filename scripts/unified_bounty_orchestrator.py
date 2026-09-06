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
    url = f"{base_url.rstrip('/')}/v1/chat/completions"
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
        executed_count = result.stdout.count(".executed")
        log(f"Executor completed. Executed markers found in output: {executed_count}")
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
    for marker in executed_markers[-20:]:  # Last 20 to avoid excessive API calls
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
        # Check for maintainer feedback via gh CLI
        try:
            parts = url.rstrip("/").split("/")
            owner, repo, kind, number = parts[-4], parts[-3], parts[-2], parts[-1]
            if kind not in ("issues", "pull"):
                continue
            cmd = ["gh", "issue" if kind == "issues" else "pr", "view", number,
                   "--repo", f"{owner}/{repo}", "--json", "comments", "--jq",
                   ".comments[-3:] | .[] | select(.author.login != \"rafaio1\") | .body"]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode == 0 and r.stdout.strip():
                comments = r.stdout.strip()
                # Check if there's actionable feedback (not just bot messages)
                if any(kw in comments.lower() for kw in ["fix", "change", "update", "wrong", "error", "fail", "reject"]):
                    feedback_found += 1
                    fix_prompt = f"""You are a senior developer. A bounty claim received maintainer feedback.
Bounty: {prop.get('title', 'N/A')}
URL: {url}
Candidate ID: {candidate_id}

Feedback:
{comments[:2000]}

Generate a fix proposal as JSON:
{{"candidate_id": "{candidate_id}", "fix_type": "code|docs|config", "files_to_change": [...], "description": "...", "priority": "high|medium|low"}}
Only propose fixes you are >80% confident will address the feedback."""
                    response = ghostcli_call(fix_prompt, max_tokens=1500)
                    if response:
                        fix_proposal = {
                            "type": "fix_proposal",
                            "source_candidate": candidate_id,
                            "generated_at": datetime.now(timezone.utc).isoformat(),
                            "raw_response": response[:3000]
                        }
                        fix_path = PROPOSALS_DIR / f"fix-{candidate_id}-{int(time.time())}.json"
                        fix_path.write_text(json.dumps(fix_proposal, indent=2, default=str))
                        log(f"Generated fix proposal for {candidate_id}: {fix_path.name}")
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
            if not data.get("acted_on"):
                unprocessed.append((fp, data))
        except Exception:
            continue
    log(f"Unprocessed fix proposals: {len(unprocessed)}")
    processed = 0
    for fp, data in unprocessed[:5]:  # Process up to 5 per cycle
        candidate_id = data.get("source_candidate", "unknown")
        raw = data.get("raw_response", "")
        quality_prompt = f"""Review this fix proposal for quality and completeness.
Proposal: {raw[:2000]}

Check:
1. Are the proposed changes specific and actionable?
2. Do they address the original feedback?
3. Are there any security concerns?
4. Is the scope appropriate (<4h work)?

Respond with JSON: {{"approved": true/false, "issues": [...], "suggested_improvements": [...]}}"""
        review = ghostcli_call(quality_prompt, max_tokens=1000)
        if review:
            data["quality_review"] = review[:2000]
            data["reviewed_at"] = datetime.now(timezone.utc).isoformat()
            # Mark as reviewed but not yet acted - execution happens in next Phase 1 cycle
            fp.write_text(json.dumps(data, indent=2, default=str))
            processed += 1
            log(f"Quality review completed for {candidate_id}")
        time.sleep(1)
    log(f"Phase 3 complete. Proposals reviewed: {processed}")
    return processed

# --- PHASE 4: DISCOVERY ----------------------------------------------------
def phase4_discovery():
    """Scout new bounties via existing scanners."""
    log("=== PHASE 4: DISCOVERY ===")
    # Trigger existing discovery scripts if available
    discovery_scripts = [
        ROOT / "scripts" / "superteam_bounty_scout.py",
        ROOT / "scripts" / "algora_bounty_scanner.py",
        ROOT / "scripts" / "opire_bounty_scanner.py",
    ]
    triggered = 0
    for script in discovery_scripts:
        if script.exists():
            try:
                subprocess.run([sys.executable, str(script)],
                             capture_output=True, text=True, timeout=120, cwd=str(ROOT))
                triggered += 1
                log(f"Triggered discovery: {script.name}")
            except Exception as e:
                log(f"Discovery script {script.name} failed: {e}")
    # Also run gh search for fresh bounties
    try:
        cmd = 'gh search issues "label:bounty state:open" --limit 10 --json repository,title,url,createdAt --jq ".[] | select(.createdAt > \\"2026-09-05\\")"'
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
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
                         capture_output=True, text=True, timeout=60, cwd=str(ROOT))
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
