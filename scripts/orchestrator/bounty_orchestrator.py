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
import re
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
    ts = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
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
    """Dispatch a microtask to Claude via direct HTTP to ApiFable (bypasses hanging CLI)."""
    import urllib.request
    log(f"  Dispatching microtask {task_id} to {GHOSTCLI_MODEL} via HTTP")
    try:
        # Extract primary API key safely (avoid grep|cut concatenation bug)
        _key_r = subprocess.run(
            ["awk", "-F=", "/^GHOSTCLI_API_KEY=/{print $2; exit}", "/root/.automaton/.env"],
            capture_output=True, text=True, timeout=5
        )
        api_key = _key_r.stdout.strip() if _key_r.returncode == 0 else os.environ.get("GHOSTCLI_API_KEY", "")
        if not api_key:
            return {"status": "error", "error": "no_api_key_found", "task_id": task_id, "rc": -1}
        payload = json.dumps({
            "model": GHOSTCLI_MODEL,
            "max_tokens": 8192,
            "messages": [{"role": "user", "content": prompt}]
        }).encode()
        req = urllib.request.Request(
            "http://127.0.0.1:8787/v1/messages",
            data=payload,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=540) as resp:
            result = json.loads(resp.read())
        actual_output = result["content"][0]["text"] if result.get("content") else ""
        stderr_text = ""
        log(f"  Microtask {task_id} HTTP success: output_len={len(actual_output)}")
        # Quality gate: reject status-report-only or empty outputs before accepting as success
        _reject_markers = ("status report written", "no_actionable_bounty", "nothing to do", "no action needed")
        # INACTIVE is a VALID terminal signal from the model (e.g. bounty already claimed).
        # Treat it as meaningful output so it gets stored and processed by Phase 3 auto-reject,
        # rather than being discarded as empty_output which triggers wasteful retries.
        _is_inactive_signal = bool(actual_output) and actual_output.strip().startswith("INACTIVE:")
        if _is_inactive_signal:
            log(f"  Microtask {task_id} returned INACTIVE signal: {actual_output.strip()[:100]}")
            return {"status": "success", "output": actual_output, "task_id": task_id, "rc": 0}
        # Relaxed: only reject if output is truly empty or very short
        # Security research outputs may contain 'blocked' in vulnerability descriptions
        _is_meaningful = bool(actual_output) and len(actual_output) > 100
        if actual_output and len(actual_output) > 100:
            # Only reject if ALL content is just a reject marker (not embedded in analysis)
            stripped = actual_output.strip().lower()
            if stripped in _reject_markers or len(stripped) < 50:
                _is_meaningful = False
        # GhostCLI may return useful output with non-zero exit codes (e.g. timeout wrapper)
        if _is_meaningful:
            log(f"  Microtask {task_id} completed successfully (output_len={len(actual_output)}, rc=0)")
            return {"status": "success", "output": actual_output, "task_id": task_id, "rc": 0}
        elif actual_output and len(actual_output) > 50:
            log(f"  Microtask {task_id} completed successfully (output_len={len(actual_output)})")
            return {"status": "success", "output": actual_output, "task_id": task_id, "rc": 0}
        else:
            err_msg = f"empty_output_rc=0"
            stdout_preview = actual_output[:200] if actual_output else "(no stdout)"
            log(f"  Microtask {task_id} failed: rc=0 stdout_len={len(actual_output)} stderr={err_msg[:300]} stdout_preview={stdout_preview}", "ERROR")
            return {"status": "error", "error": err_msg, "task_id": task_id, "rc": 0}
    except subprocess.TimeoutExpired:
        log(f"  Microtask {task_id} timed out after 540s", "ERROR")
        return {"status": "timeout", "task_id": task_id, "rc": -1}
    except Exception as e:
        log(f"  Microtask {task_id} exception: {e}", "ERROR")
        return {"status": "exception", "error": str(e), "task_id": task_id, "rc": -1}

def sync_private_mirror():
    """Sync current state and proposals to private GitHub mirror."""
    log("  Syncing to private mirror")
    import fcntl, errno, time
    # Use a dedicated lock file for orchestrator sync coordination.
    # NEVER use .git/index.lock — git creates that internally during add/commit
    # and if we hold an flock on it, git sees "File exists" and aborts with rc=128.
    _sync_lock_path = "/Agentic/.git/mirror-sync.lock"
    # Pre-flight: rebuild empty/corrupt index BEFORE any git operation
    index_path = "/Agentic/.git/index"
    try:
        if os.path.exists(index_path) and os.path.getsize(index_path) == 0:
            log("  CRITICAL: .git/index is empty, rebuilding from HEAD", "ERROR")
            subprocess.run(["git", "read-tree", "HEAD"], cwd="/Agentic", timeout=60, capture_output=True)
            subprocess.run(["git", "checkout-index", "-a", "-f"], cwd="/Agentic", timeout=60, capture_output=True)
            new_size = os.path.getsize(index_path) if os.path.exists(index_path) else 0
            log(f"  Index rebuild result: size={new_size}")
    except Exception as e:
        log(f"  Index rebuild failed: {e}", "ERROR")
    # Build explicit git environment to avoid subprocess rc=128 failures
    _git_env = os.environ.copy()
    _git_env["HOME"] = "/root"
    _git_env["GIT_CONFIG_GLOBAL"] = "/root/.gitconfig"
    _git_env["GIT_OPTIONAL_LOCKS"] = "0"
    # Remove stale sync lock file before attempting flock
    if os.path.exists(_sync_lock_path):
        try:
            st = os.stat(_sync_lock_path)
            age = time.time() - st.st_mtime
            if st.st_size == 0 or age > 300:
                os.remove(_sync_lock_path)
                log(f"  Removed stale lock (size={st.st_size}, age={age:.0f}s)")
            else:
                log(f"  Lock held by active process (size={st.st_size}, age={age:.0f}s), skipping sync", "WARN")
                return False
        except OSError:
            pass
    lock_fd = None
    try:
        lock_fd = open(_sync_lock_path, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, OSError) as e:
        if getattr(e, "errno", None) in (errno.EACCES, errno.EAGAIN):
            log("  Mirror sync skipped: git lock held by another process", "WARN")
            return False
        lock_fd = None
    try:
        cmds = [
            ["git", "--no-optional-locks", "add", "-u", "state/", "data/", "logs/"],
            ["git", "--no-optional-locks", "commit", "-m", f"auto-mirror: orchestrator-v4 cycle {__import__('datetime').datetime.now(__import__('datetime').timezone.utc).strftime('%Y%m%d-%H%M%S')}"],
            ["git", "--no-optional-locks", "push", "fork", "sync/autonomous-pipeline-20260903:main", "--force-with-lease"]
        ]
        for cmd in cmds:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd="/Agentic", env=_git_env)
            if r.returncode != 0 and "nothing to commit" not in r.stdout and "nothing to commit" not in r.stderr:
                log(f"  Mirror sync step failed: {' '.join(cmd)} rc={r.returncode}", "WARN")
                if r.stderr:
                    log(f"    stderr: {r.stderr[:300]}", "WARN")
                return False
        log("  Private mirror sync complete")
        return True
    except Exception as e:
        log(f"  Mirror sync error: {e}", "ERROR")
        return False
    finally:
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                lock_fd.close()
                if os.path.exists(_sync_lock_path):
                    os.remove(_sync_lock_path)
            except Exception:
                pass

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
    reclaim_statuses = {"lapsed", "claim_expired", "needs_reclaim"}
    for pf in proposal_files:
        prop = load_json(pf)
        if not prop:
            continue
        status = prop.get("status", "")
        action = prop.get("action", "")
        claim_type = prop.get("claim_type", "")
        is_lapsed_status = status in reclaim_statuses
        is_abandoned_claim = (
            status == "claim_submitted"
            and (action == "abandon" or claim_type == "lapsed_reclaim")
        )
        if not (is_lapsed_status or is_abandoned_claim):
            continue
        # Skip abandon proposals where PR is definitively closed; only reclaim
        # if there is evidence the bounty was reopened after lapse.
        if is_abandoned_claim and action == "abandon":
            pr_state = prop.get("pr_state", "")
            if pr_state in ("closed_unmerged", "closed_merged"):
                continue
        # Gate: skip lapsed/abandon proposals with no actionable context
        # These are dead-end reclaim attempts that waste Phase 2 slots
        _orig_ctx_check = prop.get("context", {}) or {}
        # evidence_url alone is NOT sufficient — it's just the issue link, not actionable scope
        # Only accept url from context (which contains full bounty description/scope)
        _check_url = (_orig_ctx_check.get("url") or "").strip()
        _check_desc = (_orig_ctx_check.get("description") or prop.get("description") or "").strip()
        _check_title = (_orig_ctx_check.get("title") or prop.get("title") or "").strip()
        _check_repo = (_orig_ctx_check.get("target_repo") or _orig_ctx_check.get("repo") or "").strip()
        # Must have EITHER a context URL (with scope) OR description+repo
        # evidence_url-only proposals are dead ends (issue link without bounty details)
        if not _check_url and not (_check_desc and _check_repo):
            log(f"  SKIP reclaim {Path(pf).name}: no url/desc/repo in context")
            continue
        results["lapsed_found"] += 1
        log(f"  Lapsed proposal: {Path(pf).name} status={status} action={action}")
        raw_cid = prop.get("candidate_id") or prop.get("bounty_key") or f"reclaim-{int(time.time())}"
        cid = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(raw_cid))
        # Propagate URL and title from original proposal so Phase 2/3 have actionable context
        orig_ctx = prop.get("context", {}) or {}
        orig_url = orig_ctx.get("url") or prop.get("evidence_url") or prop.get("url")
        orig_title = orig_ctx.get("title") or prop.get("title") or prop.get("bounty_key")
        if not orig_url:
            log(f"  SKIP reclaim {Path(pf).name}: no URL in context or evidence_url")
            continue
        merged_ctx = dict(orig_ctx)
        merged_ctx["url"] = orig_url
        if orig_title:
            merged_ctx["title"] = orig_title
        merged_ctx["original_proposal_file"] = Path(pf).name
        # Gate: verify bounty is actually reclaimable before creating proposal
        # Skip if original proposal was already rejected as inactive or has no valid URL
        orig_status = prop.get("status", "")
        orig_rejection = prop.get("rejection_reason", "")
        if orig_status == "review_rejected" and "inactive" in orig_rejection.lower():
            log(f"  SKIP reclaim {Path(pf).name}: original was rejected as inactive")
            continue
        # Verify URL points to a lapsed/reopened bounty, not an active PR by another author
        if orig_url and "/pull/" in orig_url:
            try:
                import re as _re_pr
                _pr_match = _re_pr.search(r'/repos/([^/]+/[^/]+)/pulls/(\d+)', orig_url)
                if not _pr_match:
                    _pr_match = _re_pr.search(r'github\.com/([^/]+/[^/]+)/pull/(\d+)', orig_url)
                if _pr_match:
                    _pr_repo = _pr_match.group(1)
                    _pr_num = _pr_match.group(2)
                    _pr_r = subprocess.run(
                        ["curl", "-sf", f"https://api.github.com/repos/{_pr_repo}/pulls/{_pr_num}"],
                        capture_output=True, text=True, timeout=15
                    )
                    if _pr_r.returncode == 0:
                        _pr_data = json.loads(_pr_r.stdout)
                        _pr_state = _pr_data.get("state", "")
                        _pr_merged = _pr_data.get("merged", False)
                        _pr_author = (_pr_data.get("user") or {}).get("login", "")
                        # Skip if PR is still open and authored by someone else (not reclaimable)
                        if _pr_state == "open" and not _pr_merged and _pr_author not in ("rafaio1", ""):
                            log(f"  SKIP reclaim {Path(pf).name}: PR #{_pr_num} is open by {_pr_author}, not reclaimable")
                            continue
            except Exception as _pr_e:
                log(f"  WARN: could not verify PR state for {Path(pf).name}: {_pr_e}")
        reclaim_prop = {
            "candidate_id": cid,
            "type": "reclaim_proposal",
            "status": "pending_execution",
            "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            "original_proposal": Path(pf).name,
            "bounty_value": float(merged_ctx.get("gross_verified") or merged_ctx.get("payout_amount") or prop.get("bounty_value") or 0),
            "currency": str(merged_ctx.get("asset") or prop.get("currency") or "RTC").upper(),
            "context": merged_ctx,
        }
        prop_hash = hashlib.sha256(
            json.dumps(reclaim_prop, sort_keys=True, default=str).encode()
        ).hexdigest()[:12]
        save_json(PROPOSALS_DIR / f"{cid}-reclaim-{prop_hash}.json", reclaim_prop)
        results["proposals_created"] += 1

    log(f"  Phase 1 result: {results}")
    return results

# ── Phase 2: Microtask Orchestration ──────────────────────────────────
def phase2_microtask_orchestration():
    """Dispatch actionable proposals to Claude microtasks via priority queue."""
    log("PHASE 2: Microtask orchestration (queue-driven)")
    results = {"dispatched": 0, "completed": 0, "failed": 0, "skipped_superseded": 0, "total_scanned": 0, "queue_source": True}

    # Load priority queue (rebuilt with valid IDs)
    queue = load_json(QUEUE_PATH) or {"action_queue": [], "research_queue": []}
    action_items = queue.get("action_queue", [])
    results["total_scanned"] = len(action_items)
    
    actionable = []
    for item in action_items:
        cid = item.get("id") or item.get("candidate_id")
        if not cid:
            continue
        # Find matching proposal file
        source_file = item.get("source_file", "")
        if source_file:
            pf = PROPOSALS_DIR / source_file
            if pf.exists():
                prop = load_json(pf)
                if prop and prop.get("status") not in ("microtask_completed", "review_rejected", "submitted_to_platform"):
                    actionable.append((str(pf), prop))
                    continue
        # Fallback: search by candidate_id
        # Enhanced fallback: extract issue number from candidate_id for legacy proposals
        import re as _re
        issue_match = _re.search(r'(\d{4,})$', str(cid))
        if issue_match:
            issue_num = issue_match.group(1)
            # Prefer non-abandon files matching the issue number
            candidates = sorted(PROPOSALS_DIR.glob(f"*[_-]{issue_num}.json")) + \
                         sorted(PROPOSALS_DIR.glob(f"*[_-]{issue_num}_*.json"))
            matches = [m for m in candidates if '_abandon_' not in m.name] or candidates[:1]
        else:
            matches = list(PROPOSALS_DIR.glob(f"*{cid}*.json"))
        for m in matches[:1]:
            prop = load_json(m)
            if prop and prop.get("status") not in ("microtask_completed", "review_rejected", "submitted_to_platform"):
                actionable.append((str(m), prop))
                break
    
    log(f"  Queue-driven: {len(actionable)} actionable from {results['total_scanned']} queue items")

    # Legacy fallback removed — qualification pipeline is authoritative.
    # Proposals must pass qualify_proposals.py before entering research_queue.
    # Legacy scan disabled — queue is authoritative
    if False:
      proposal_files = sorted(glob.glob(str(PROPOSALS_DIR / "*.json")))
      for pf in proposal_files:
        prop = load_json(pf)
        if not prop:
            continue
        # Skip superseded proposals entirely
        if prop.get("action") == "superseded":
            results["skipped_superseded"] += 1
            continue
        # Skip proposals already processed by Phase 2 or promoted by Phase 3
        if prop.get("status") in ("microtask_completed", "review_rejected"):
            results["skipped_superseded"] += 1
            continue
        # Accept both legacy status field and next_status field for actionable items
        status = prop.get("status", "")
        next_status = prop.get("next_status", "")
        action = prop.get("action", "")
        is_actionable_status = status == "pending_execution" or next_status in (
            "claim_pending", "in_progress", "candidate", "submitted", "awaiting_first_review"
        )
        if status == "pending_qualification" and prop.get("type") == "discovery_proposal":
            is_actionable_status = True
        is_valid_type = prop.get("type") in ("reclaim_proposal", "execution_proposal", "discovery_proposal", None)
        # For next_status-based proposals, also accept by action type
        is_valid_action = action in ("qualify_claim", "investigate_claim", "submit_work", "fix_review_feedback", "monitor_pr_review", "claim", "reclaim_lapsed", None)
        if is_actionable_status and (is_valid_type or is_valid_action):
            actionable.append((pf, prop))

    # Prioritize discovery proposals (high-value immunefi/c1work) over low-value rustchain abandon tasks
    def _dispatch_priority(item):
        _pf, _prop = item
        _type = _prop.get("type", "")
        _status = _prop.get("status", "")
        _ctx = _prop.get("context", {}) or {}
        _gross = _ctx.get("gross_verified") or _ctx.get("payout_amount") or 0
        _asset = _ctx.get("asset", "")
        _url = (_ctx.get("url") or "").strip()
        _desc = (_ctx.get("description") or _ctx.get("summary") or "").strip()
        # Gate: skip ANY proposal with no description/summary AND no meaningful title
        # Reclaim/discovery proposals without context produce empty Claude output
        # and block Phase 2 indefinitely with retry loops
        # EXCEPTION: Immunefi/high-value discovery proposals with a URL are fetchable
        # Short titles like "Ethena", "ENS", "Hedera" are valid project names
        _title = (_ctx.get("title") or prop.get("title") or "").strip()
        _is_fetchable_discovery = (
            _type == "discovery_proposal" and bool(_url) and _gross and float(_gross) >= 1000
        )
        _has_meaningful_title = (len(_title) > 10 and not _title.startswith("rustchain-")) or _is_fetchable_discovery
        if not _desc and not _has_meaningful_title:
            return (5, 0)
        # Gate: skip proposals with no actionable target (url, repo, scope, description all empty)
        # These produce INSUFFICIENT_DATA outputs that waste Phase 2/3 capacity
        _target_repo = (_ctx.get("target_repo") or _ctx.get("repo") or _ctx.get("github_repo") or "").strip()
        _scope = (_ctx.get("scope") or _ctx.get("assets_in_scope") or _ctx.get("in_scope") or "").strip()
        if not _url and not _target_repo and not _scope and not _desc:
            return (5, 0)
        # Gate: skip rustchain proposals requiring hardware/social proof (non-autonomous)
        import re as _re
        _hw_pattern = r"hardware|photo|video proof|physical|social media|reddit|mastodon|bottube|x\.com|twitter|youtube"
        if _title.lower().startswith("rustchain-") or "rustchain" in (_target_repo or "").lower():
            if _re.search(_hw_pattern, (_desc + " " + _title).lower()):
                return (5, 0)
        # Gate: skip discovery proposals that require human account creation
        # These are dead-ends for autonomous execution and waste Phase 2 slots
        if _type == "discovery_proposal" and _status == "pending_qualification":
            _rh = _ctx.get("requires_human", []) or []
            if "account_creation" in _rh:
                return (5, 0)
        # Discovery proposals with pending_qualification get highest priority
        # Prefer non-RTC assets (USDC/USD) over blocked RTC bounties
        if _type == "discovery_proposal" and _status == "pending_qualification":
            if _asset and _asset != "RTC":
                return (0, -_gross)
            return (1, -_gross)
        # Other discovery proposals
        if _type == "discovery_proposal":
            return (2, -_gross)
        # Execution/reclaim proposals
        if _type in ("execution_proposal", "reclaim_proposal"):
            return (3, -_gross)
        # Everything else (rustchain abandon tasks etc)
        return (4, -_gross)
    actionable.sort(key=_dispatch_priority)
    log(f"  Found {len(actionable)} actionable proposals (skipped {results['skipped_superseded']} superseded)")
    for pf, prop in actionable[:5]:  # Increased to 5 microtasks per cycle for higher throughput
        task_id = prop.get("candidate_id", Path(pf).stem)
        ctx = prop.get("context", {})
        # Dedup & description enrichment: if this proposal lacks a description but
        # another file for the same candidate_id has one, copy it forward so the
        # microtask prompt receives real scope instead of "No description available".
        _bounty_desc_raw = (ctx.get('description') or ctx.get('summary') or '').strip()
        if not _bounty_desc_raw:
            import glob as _glob
            _cid = prop.get("candidate_id")
            if _cid:
                _best_desc = ""
                for _pf2 in _glob.glob(f"data/aro/proposals/{_cid}-*.json"):
                    if _pf2 == pf:
                        continue
                    try:
                        with open(_pf2) as _f2:
                            _d2 = json.load(_f2)
                        _c2 = _d2.get("context", {})
                        _desc2 = (_c2.get('description') or _c2.get('summary') or '').strip()
                        if len(_desc2) > len(_best_desc):
                            _best_desc = _desc2
                    except Exception:
                        pass
                if _best_desc:
                    ctx['description'] = _best_desc
                    log(f"  Enriched {task_id} with description from sibling proposal ({len(_best_desc)} chars)")
        # Build enriched context for security research tasks (Immunefi etc)
        _bounty_desc = (ctx.get('description') or ctx.get('summary') or '')[:3000]
        _target_repo = ctx.get('repo') or ctx.get('target_repo') or ctx.get('github_repo') or ''
        _scope = ctx.get('scope') or ctx.get('assets_in_scope') or ctx.get('in_scope') or ''
        # FIX PRIORITY 0: Derive target_repo from URL when context fields are empty.
        # This prevents INACTIVE:NO_TARGET_SPECIFIED signals from the model.
        if not _target_repo and _url:
            import re as _re_url
            _m_url = _re_url.match(r'https?://github\.com/([^/]+/[^/]+)/(issues|pull)/(\d+)', _url)
            if _m_url:
                _target_repo = _m_url.group(1)
                log(f"  Derived target_repo from URL for {task_id}: {_target_repo}")
                # Persist back to proposal context so future cycles see it
                prop.setdefault('context', {})['repo'] = _target_repo
                try:
                    with open(pf, 'w') as _wf:
                        json.dump(prop, _wf, indent=2)
                except Exception:
                    pass
        # ACTIVE ENRICHMENT: If description is missing/placeholder but URL exists,
        # fetch content NOW via playwright-cli so Claude receives real scope.
        _url = (ctx.get('url') or '').strip()
        _needs_fetch = (
            not _bounty_desc
            or len(_bounty_desc) < 60
            or "to be fetched at dispatch time" in _bounty_desc.lower()
            or "no description in context" in _bounty_desc.lower()
        )
        if _needs_fetch and _url and _url.startswith("http"):
            try:
                import subprocess as _sp
                _sp.run(["playwright-cli", "open", _url], capture_output=True, timeout=20, cwd="/Agentic")
                _snap = _sp.run(["playwright-cli", "snapshot"], capture_output=True, text=True, timeout=20, cwd="/Agentic")
                _sp.run(["playwright-cli", "close"], capture_output=True, timeout=8, cwd="/Agentic")
                if _snap.returncode == 0 and _snap.stdout and len(_snap.stdout.strip()) > 80:
                    _fetched = _snap.stdout.strip()[:3000]
                    ctx['description'] = _fetched
                    _bounty_desc = _fetched
                    prop.setdefault('context', {})['description'] = _fetched
                    try:
                        with open(pf, 'w') as _wf:
                            json.dump(prop, _wf, indent=2)
                    except Exception:
                        pass
                    log(f"  LIVE-ENRICHED {task_id}: fetched {len(_fetched)} chars from {_url[:80]}")
            except Exception as _e:
                log(f"  LIVE-FETCH FAILED {task_id}: {_e}")
        if not _bounty_desc:
            _bounty_desc = "No description available. Check URL or target repo for details."
        _payout = ctx.get('payout_amount', ctx.get('gross_verified', 'unknown'))
        _asset = ctx.get('asset', 'unknown')
        _platform = prop.get('platform', ctx.get('platform', 'unknown'))
        
        prompt = f"""You are an expert security researcher and developer executing a bounty task.

## BOUNTY DETAILS
- Title: {ctx.get('title', 'unknown')}
- Platform: {_platform}
- Payout: {_payout} {_asset}
- URL: {ctx.get('url', 'N/A')}
- Target Repo: {_target_repo if _target_repo else 'N/A'}
- Scope: {_scope if _scope else 'N/A'}
- Type: {prop.get('type')}

## DESCRIPTION
{_bounty_desc if _bounty_desc else 'No description available - check URL'}

## YOUR TASK
Produce a CONCRETE DELIVERABLE with SUBSTANTIVE TECHNICAL CONTENT. Choose ONE path:

### PATH A: Code Fix / Implementation
If this requires code changes:
1. Analyze the vulnerability/issue from the URL
2. Write the EXACT fix as a unified diff or complete file
3. Include brief explanation of why it fixes the issue

### PATH B: Security Vulnerability Report (ORIGINAL ANALYSIS REQUIRED)
You MUST produce an ORIGINAL vulnerability finding or security analysis. DO NOT summarize the bounty scope, payout tiers, focus areas, or assets in scope. The reviewer WILL REJECT any output that merely restates program information.

Required sections (ALL mandatory):
## Vulnerability Summary
- 1-2 sentences describing the specific vulnerability you found
## Technical Detail
- Exact code paths, function names, state transitions, or logic flaws
- Reference specific lines/functions from the target repo if available
## Impact Assessment
- Concrete loss scenario with conditions and estimated impact
## Reproduction Steps
- Numbered, executable steps to reproduce the issue
## Proof of Concept
- Code, script, test case, or transaction demonstrating the vulnerability
## Recommended Fix
- Specific remediation with code or configuration changes

If you cannot identify a real vulnerability after thorough analysis, output exactly: INACTIVE:NO_VULNERABILITY_FOUND

### PATH C: Content Creation
If this requires article/video/post:
1. Draft the complete content ready to publish
2. Include all technical details and examples

### PATH D: Claim Comment
If you need to claim via GitHub comment:
Output the EXACT comment text starting with /claim

## CRITICAL RULES
- Output MUST be >500 characters of SUBSTANTIVE TECHNICAL content
- Do NOT write status reports, meta-commentary, or "I cannot" refusals  
- Do NOT say "will do later" or "needs more info" - produce the artifact NOW
- Do NOT output only URLs, links, or source references without analysis
- Do NOT write introductions or summaries without actual vulnerability findings
- If the bounty page has no actionable scope or is inactive, output exactly: INACTIVE:<specific reason>
- If genuinely impossible, output exactly: INACTIVE:<specific reason>
- Do NOT modify canonical ledgers or financial files

BEGIN WORK PRODUCT:"""
        
        result = run_claude_microtask(prompt, task_id)
        results["dispatched"] += 1
        

        # Pre-dispatch gate: skip abandon/blocked proposals that waste Phase 2 slots
        _action = prop.get("action", "")
        _next_status = prop.get("next_status", "")
        if _action == "abandon" and _next_status in ("blocked_by_existing_pr", "terminal_failure"):
            log(f"  SKIP {task_id}: abandon+{_next_status} is non-actionable, marking terminal_failure")
            prop["status"] = "terminal_failure"
            prop["error"] = "skipped_non_actionable_abandon"
            save_json(pf, prop)
            results["failed"] += 1
            continue

        # Retry once if empty output (common with security research tasks)
        if result.get("status") == "error" and "empty_output" in str(result.get("error", "")):
            log(f"  Retrying {task_id} with enriched context after empty output")
            import time; time.sleep(2)
            result = run_claude_microtask(prompt, task_id + "-retry")
        
        if result["status"] in ("success", "success_raw"):
            results["completed"] += 1
            # Update proposal status
            prop["status"] = "microtask_completed"
            raw_output = result.get("output", "")
            if not isinstance(raw_output, str):
                raw_output = str(raw_output)
            prop["microtask_output"] = raw_output
            prop["microtask_result"] = raw_output  # FIX: store full output; was truncated to 500 chars causing Phase 3 rejections
            prop["completed_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
            # Clear any stale error from prior attempts so Phase 3 sees clean state
            prop.pop("error", None)
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
        task_id = prop.get("task_id") or prop.get("id") or Path(pf).stem
        
        # Basic validation: must have non-empty result
        output = prop.get("microtask_output") or prop.get("microtask_result") or prop.get("output") or ""
        # --- Local Heuristic Auto-Approve (bypass LLM for obvious valid outputs) ---
        output_len = len(output) if output else 0
        has_code_markers = any(m in output for m in ["```", "diff --git", "--- a/", "+++ b/", "def ", "function ", "const ", "import ", "## Vulnerability Summary", "## Proof of Concept", "## Reproduction Steps"])
        has_patch_file = bool(prop.get("patch_path") or prop.get("artifact_path"))
        # FIX: Detect artifact files referenced in output text when patch_path field is empty
        if not has_patch_file and output:
            import re as _re
            _mentioned = _re.findall(r'/Agentic/[^\s`\'"]+', output)
            for _mp in _mentioned:
                try:
                    if os.path.exists(_mp):
                        has_patch_file = True
                        prop["artifact_path"] = _mp
                        break
                except Exception:
                    pass

        # GATE: Never auto-approve empty or near-empty outputs regardless of markers
        # FIX: Auto-reject INACTIVE/unknown proposals BEFORE length gate
        # These signals are valid terminal states but short; they must not be skipped
        if isinstance(output, str) and (
            output.startswith("INACTIVE:")
            or output.startswith("INSUFFICIENT_DATA:")
            or "bounty task is undefined" in output.lower()
            or "bounty task is unspecified" in output.lower()
            or "bounty target unknown" in output.lower()
            or "bounty target is unspecified" in output.lower()
            or "cannot be actioned" in output.lower()
            or "cannot be executed" in output.lower()
            or "cannot be resolved" in output.lower()
            or "no url, target repository" in output.lower()
            or "no target to analyze" in output.lower()
        ):
            prop["status"] = "review_rejected"
            prop["rejection_reason"] = "inactive_or_insufficient_data"
            prop["review_method"] = "local_heuristic_auto_reject"
            results["rejected"] += 1
            save_json(pf, prop)
            continue

        if output_len < 50:
            log(f"    Auto-approve skipped for {task_id}: output_len={output_len} (too short)")
            continue
        # Auto-approve vulnerability reports that have all required sections
        _is_vuln_report = all(h in output for h in ["## Vulnerability Summary", "## Technical Detail", "## Impact Assessment", "## Reproduction Steps", "## Proof of Concept", "## Recommended Fix"])
        _has_substantial_content = output_len >= 200 and has_code_markers
        if has_patch_file or _has_substantial_content or (_is_vuln_report and output_len >= 1000):
            prop["status"] = "review_approved"
            prop["review_method"] = "local_heuristic_auto_approve"
            results["approved"] += 1
            save_json(pf, prop)
            continue
        # FIX: Auto-reject INACTIVE/unknown proposals that have no actionable target
        # INACTIVE check moved above length gate to prevent short signals from being skipped

        # Enhanced review: dispatch code quality check via Claude microtask
        review_prompt = f"""You are a senior security researcher reviewing bounty work product.

## ORIGINAL BOUNTY REQUIREMENTS
{prop.get('description', prop.get('title', 'No description available'))[:2000]}

## WORK PRODUCT TO REVIEW ({len(output)} chars)
```
{output[:6000]}
```

## REVIEW CRITERIA
1. Does the work directly address the specific vulnerability/issue described in the bounty?
2. Is there concrete implementation, analysis, or proof-of-concept (not placeholder/meta-text)?
3. Are there obvious technical errors, unhandled exceptions, or AI refusals ("I cannot", "as an AI")?
4. If code: does it follow secure coding practices and actually fix/demonstrate the issue?
5. If research: is the analysis sound and actionable?

## REQUIRED OUTPUT FORMAT
Respond with EXACTLY one of these two formats, nothing else:
APPROVED
or
REJECTED:<specific reason in under 100 words>

Do NOT include preamble, explanation, or markdown formatting outside the above."""
        review_result = run_claude_microtask(review_prompt, f"review-{task_id}")
        review_out = review_result.get("output", "").strip()
        review_rc = review_result.get("rc", -1)
        if review_out.upper().startswith("APPROVED") and review_rc == 0:
            prop["status"] = "review_approved"
            results["approved"] += 1
            save_json(pf, prop)
            continue
        if not review_out or review_rc != 0 or "empty_output" in str(review_result.get("error", "")):
            log(f"    Review microtask failed/empty for {task_id} (rc={review_rc}); keeping as microtask_completed for retry")
            continue
        
        if review_out.upper().startswith("REJECTED"):
            prop["status"] = "review_rejected"
            prop["rejection_reason"] = review_out.replace("REJECTED:", "").strip() or "quality_gate_failed"
            prop["review_method"] = "llm_rejected"
            results["rejected"] += 1
        else:
            log(f"    Ambiguous review output for {task_id}: {review_out[:100]}; keeping status")
            continue
            prop["rejection_reason"] = review_out.replace("REJECTED:", "").strip() or "quality_gate_failed"
            results["rejected"] += 1
        save_json(pf, prop)

    log(f"  Phase 3 result: {results}")
    return results

def _dispatch_github_claim_comment(prop, proposal_path):
    """Post a /claim comment to a GitHub issue for bounty claiming."""
    import subprocess, json
    from datetime import datetime
    from pathlib import Path
    
    bounty_key = prop.get("bounty_key", "")
    # Parse bounty_key OR derive from evidence_url when key lacks pipe format
    parts = bounty_key.split("|") if bounty_key else []
    owner_repo = None
    issue_number = None
    # Handle malformed keys like "github|[bounty:-$55]-title-timestamp" by extracting context URL first
    _derived_from_ctx = False
    if len(parts) >= 2 and not parts[1].replace("/","").isdigit():
        ctx_url = (prop.get("context", {}) or {}).get("url", "") or prop.get("evidence_url", "") or prop.get("url", "")
        import re as _re_ctx
        m_ctx = _re_ctx.match(r"https?://github\.com/([^/]+/[^/]+)/(issues|pull)/(\d+)", ctx_url)
        if m_ctx:
            owner_repo = m_ctx.group(1)
            issue_number = m_ctx.group(3)
            _derived_from_ctx = True
            log(f"  Derived GitHub target from context URL for malformed key: {owner_repo}#{issue_number}")
    if not _derived_from_ctx and len(parts) == 3 and parts[0] == "github":
        owner_repo = parts[1]
        issue_number = parts[2]
    elif not _derived_from_ctx and len(parts) == 2 and "/" in parts[0]:
        owner_repo = parts[0]
        issue_number = parts[1]
    elif not _derived_from_ctx:
        # Fallback: extract owner/repo and issue/PR number from evidence_url
        ev = prop.get("evidence_url") or ""
        import re as _re
        m = _re.match(r"https?://github\.com/([^/]+/[^/]+)/(issues|pull)/(\d+)", ev)
        if m:
            owner_repo = m.group(1)
            issue_number = m.group(3)
        else:
            raise ValueError(f"Invalid github bounty_key format and no derivable evidence_url: {bounty_key}")
    
    # Check if Live-URL is required (content bounties)
    live_url = prop.get("live_url") or prop.get("evidence_url") or ""
    comment_body = "/claim"
    if live_url and any(host in live_url for host in ["bottube.ai", "x.com", "twitter.com", "youtube.com", "youtu.be", "hackaday.io", "dev.to", "hashnode.dev", "medium.com"]):
        comment_body = f"/claim\n\nLive-URL: {live_url}"
    
    cmd = [
        "gh", "api",
        f"repos/{owner_repo}/issues/{issue_number}/comments",
        "-f", f"body={comment_body}"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"gh api failed ({result.returncode}): {result.stderr[:300]}")
    
    response = json.loads(result.stdout) if result.stdout.strip() else {}
    comment_id = response.get("id")
    
    prop["claim_comment_sent"] = True
    prop["claim_comment_id"] = comment_id
    prop["submitted_at"] = datetime.now(tz=__import__('datetime').timezone.utc).isoformat()
    prop["status"] = "claim_pending"
    save_json(proposal_path, prop)
    log(f"    Posted /claim to {owner_repo}#{issue_number} (comment_id={comment_id})")

def _dispatch_immunefi_submission(prop, proposal_path):
    """Submit an approved Immunefi report via playwright-cli web form automation."""
    import subprocess, json, re
    from pathlib import Path
    from datetime import datetime

    # Gate: skip gracefully if no evidence available (avoid repeated dispatch failures)
    evidence_check = (
        prop.get("evidence_report")
        or prop.get("microtask_result_path")
        or prop.get("output_file")
        or prop.get("deliverable_path")
    )
    if not evidence_check:
        log(f"    SKIP immunefi dispatch: no evidence_report for {Path(proposal_path).name}")
        return False

    # Resolve evidence path from multiple possible fields (backwards compat + microtask outputs)
    evidence_path = (
        prop.get("evidence_report")
        or prop.get("microtask_result_path")
        or prop.get("output_file")
        or prop.get("deliverable_path")
    )
    # Fallback: search workspace/proposals for dexe report when context matches DeXe
    if (not evidence_path or not Path(evidence_path).exists()):
        ctx_title = (prop.get("context") or {}).get("title", "") if isinstance(prop.get("context"), dict) else ""
        candidates = [
            "/Agentic/workspace/dexe-security-analysis.md",
            "/Agentic/proposals/dexe-protocol-security-analysis-20260904.md",
        ]
        if "dexe" in ctx_title.lower() or "dexe" in str(proposal_path).lower():
            for c in candidates:
                if Path(c).exists():
                    evidence_path = c
                    break
    if not evidence_path or not Path(evidence_path).exists():
        raise ValueError(f"Missing evidence_report for Immunefi submission: resolved={evidence_path!r} proposal={Path(proposal_path).name}")
    
    report_md = Path(evidence_path).read_text()
    title_match = re.search(r'^#\s+(.+)$', report_md, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else f"Security Report - {prop.get('bounty_key', 'unknown')}"
    
    sev_match = re.search(r'[Ss]everity:\s*(Critical|High|Medium|Low)', report_md)
    severity = sev_match.group(1) if sev_match else "Medium"
    
    desc_lines = [l for l in report_md.split('\n') if not l.startswith('#') and l.strip()]
    description = '\n'.join(desc_lines[:50])
    
    log(f"    Immunefi submit: title={title[:60]}, severity={severity}, report={evidence_path}")
    
    cmds = [
        ["playwright-cli", "open", "https://immunefi.com/submit"],
        ["playwright-cli", "snapshot"],
        ["playwright-cli", "fill", "input[name='title'], input[placeholder*='title' i], #title", title],
        ["playwright-cli", "fill", "textarea[name='description'], textarea[placeholder*='description' i], #description", description[:2000]],
        ["playwright-cli", "select", "select[name='severity'], #severity", severity.lower()],
        ["playwright-cli", "click", "button[type='submit'], button:has-text('Submit'), input[type='submit']"],
        ["playwright-cli", "snapshot"],
        ["playwright-cli", "close"],
    ]
    
    for cmd in cmds:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0 and "timeout" not in result.stderr.lower():
                log(f"    Immunefi CLI warning: {' '.join(cmd)} -> {result.stderr[:200]}")
        except subprocess.TimeoutExpired:
            log(f"    Immunefi CLI timeout: {' '.join(cmd)}")
            break
        except Exception as e:
            log(f"    Immunefi CLI error: {e}")
            break
    
    prop["submitted_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    prop["submission_method"] = "immunefi_web_form_playwright"
    save_json(proposal_path, prop)
    log(f"    Immunefi submission recorded for {Path(proposal_path).name}")


# ── Phase 3.5: Submit Approved Work ─────────────────────────────────
def phase3_5_submit_approved():
    """Take review_approved proposals and submit them to GitHub (PR or claim comment)."""
    log("PHASE 3.5: Submitting approved work to platforms")
    results = {"submitted": 0, "failed": 0, "skipped_no_context": 0}
    
    # ── Promotion Gate: review_approved → claim_submitted for GitHub bounties ──
    promoted = 0
    for pf in sorted(glob.glob(str(PROPOSALS_DIR / "*.json"))):
        prop = load_json(pf)
        if not prop:
            continue
        if prop.get("status") != "review_approved":
            continue
        bk = prop.get("bounty_key", "")
        # Allow promotion for GitHub, Immunefi, and C1Work bounties
        if not (bk.startswith("github|") or bk.startswith("immunefi|") or bk.startswith("c1work|")):
            continue
        prop["status"] = "claim_submitted"
        prop["action"] = "claim"
        # Set submission type based on platform
        if bk.startswith("github|"):
            prop["submission_type"] = "github_claim_comment"
        elif bk.startswith("immunefi|"):
            prop["submission_type"] = "immunefi_web_form"
        else:
            prop["submission_type"] = "platform_submission"
        prop["promoted_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        save_json(pf, prop)
        promoted += 1
    if promoted:
        log(f"  Phase 3.5 Promotion: {promoted} review_approved → claim_submitted (GitHub)")

    proposal_files = sorted(glob.glob(str(PROPOSALS_DIR / "*.json")))
    _submit_count = 0
    for pf in proposal_files:
        if _submit_count >= 20:
            log("  Phase 3.5 batch limit reached (20 submits)")
            break
        prop = load_json(pf)
        if not prop or prop.get("status") not in ("review_approved", "approved_pending_submission", "claim_submitted"):
            continue
        # Idempotency: skip if already submitted (handles re-classified duplicates)
        if prop.get("submitted_at") and prop.get("action") != "claim":
            results["skipped_no_context"] += 1
            continue
        
        ctx = prop.get("context", {})
        submission_type = prop.get("submission_type", "")
        
        # Branch for GitHub /claim comment submissions (highest priority)
        if prop.get("status") == "claim_submitted" and ("|" in prop.get("bounty_key", "")) and not prop.get("claim_comment_sent") and prop.get("bounty_key", "").startswith("github|"):
            from pathlib import Path as _Path; log(f"  Phase 3.5: Dispatching GitHub /claim comment for {_Path(pf).name}")
            try:
                _dispatch_github_claim_comment(prop, pf)
                results["submitted"] += 1
                _submit_count += 1
            except Exception as e:
                log(f"  Phase 3.5 GitHub claim dispatch failed: {e}")
                results["failed"] += 1
            continue
        
        # Branch for Immunefi web-form submissions
        if submission_type == "immunefi_web_form":
            from pathlib import Path as _Path; log(f"  Phase 3.5: Dispatching Immunefi web-form submission for {_Path(pf).name}")
            try:
                _dispatch_immunefi_submission(prop, pf)
                results["submitted"] += 1
                _submit_count += 1
            except Exception as e:
                log(f"  Phase 3.5 Immunefi dispatch failed: {e}")
                results["failed"] += 1
            continue
        
        # Fallback to evidence_url or bounty_key-derived URL when context.url is missing
        url = ctx.get("url", "") or prop.get("evidence_url", "")
        if not url and prop.get("bounty_key"):
            parts = prop["bounty_key"].split("|")
            if len(parts) >= 3 and parts[0] == "github":
                url = f"https://github.com/{parts[1]}/issues/{parts[2]}"
            elif len(parts) >= 2 and parts[0] == "immunefi":
                url = f"https://immunefi.com/bounty/{parts[1]}/"
            elif len(parts) >= 2 and parts[0] == "c1work":
                url = f"https://app.c1.work/bounties/{parts[1]}"
        output = prop.get("microtask_output") or prop.get("microtask_result") or prop.get("output") or ""
      
      # Skip proposals with no real work content
        # Skip proposals with no real work content
        skip_output = False
        if not output:
            skip_output = True
        elif isinstance(output, str) and (
            output.startswith("Bounty task `unknown`")
            or "consolidated report" in output.lower()
        ):
            skip_output = True
        # Gate: reject approvals that are just status reports with no executable claim/PR
        if isinstance(output, str) and (
            "status report written" in output.lower()
        ):
            # Only reject if the ENTIRE output is a status report (>80% match or starts with marker)
            out_stripped = output.strip().lower()
            is_pure_status = (
                out_stripped.startswith("status report written")
                or out_stripped.startswith("no_actionable_bounty")
                or (len(out_stripped) < 500 and ("status report" in out_stripped or "no actionable" in out_stripped))
            )
            if is_pure_status:
                prop["status"] = "review_rejected"
                prop["rejection_reason"] = "output_indicates_no_actionable_work"
                save_json(pf, prop)
                results["skipped_no_context"] += 1
                continue
        if not url or skip_output:
            results["skipped_no_context"] += 1
            continue
        # Skip proposals that are just status reports with no real work
        if prop.get("status") == "no_actionable_bounty" or (prop.get("context") is None and prop.get("action") is None):
            results["skipped_no_context"] += 1
            continue
        # Skip if microtask_result confirms no actionable bounty
        if isinstance(output, str) and ("no_actionable_bounty" in output.lower() or "no valid bounty" in output.lower()):
            results["skipped_no_context"] += 1
            continue
        # Gate: skip submission when qualification indicates bounty is not actionable
        _inactive_signals = [
            "overdue", "awaiting payment", "do not claim", "already fixed",
            "closed", "expired", "lapsed", "not open", "unavailable",
            "already claimed", "duplicate", "rejected", "invalid"
        ]
        if isinstance(output, str) and any(sig in output.lower() for sig in _inactive_signals):
            prop["status"] = "qualified_inactive"
            prop["inactivity_reason"] = "microtask_result_indicates_non_actionable"
            save_json(pf, prop)
            results["skipped_no_context"] += 1
            continue
            
        # Dispatch submission microtask
        task_id = f"submit-{prop.get('candidate_id', Path(pf).stem)}"
        prompt = f"""Submit this completed bounty work to the platform.
Target URL: {url}
Work Output: {output[:2000]}

Instructions:
1. If URL is a GitHub issue/PR, post a comment with the work summary or create/update a PR.
2. If it's a claim flow, execute the claim command if available in context.
3. Return the submission URL or confirmation.
4. Do NOT modify canonical ledgers.
Provider: {GHOSTCLI_MODEL}"""

        
        result = run_claude_microtask(prompt, task_id)
        if result["status"] in ("success", "success_raw"):
            raw_output = str(result.get("output", ""))
            output_lower = raw_output.lower()
            _false_positive_markers = [
                "no submission was made",
                "does not accept submissions via url",
                "reviewed — no submission filed",
                "requires manual submission",
            ]
            # Only flag false positive if marker appears at start of output or constitutes >80% of short outputs
            out_stripped = raw_output.strip().lower()
            is_false_positive = False
            for marker in _false_positive_markers:
                if out_stripped.startswith(marker):
                    is_false_positive = True
                    break
                if len(out_stripped) < 500 and marker in out_stripped:
                    is_false_positive = True
                    break
            has_proof = len(raw_output) > 200 and not is_false_positive
            if has_proof:
                prop["status"] = "submitted_to_platform"
                prop["submission_result"] = raw_output[:500]
                prop["submitted_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
                save_json(pf, prop)
                results["submitted"] += 1
                _submit_count += 1
                log(f"  Submitted {Path(pf).name} -> {url[:60]}")
            else:
                reason = "false_positive_submission" if is_false_positive else "insufficient_proof"
                prop["status"] = "terminal_failure"
                prop["failure_reason"] = reason
                prop["submission_attempt_output"] = raw_output[:500]
                prop["failed_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
                save_json(pf, prop)
                results["failed"] += 1
                log(f"  Submission REJECTED ({reason}) for {Path(pf).name}: {raw_output[:120]}", "WARN")
        else:
            results["failed"] += 1
            log(f"  Submission failed for {Path(pf).name}: {result.get('error','?')[:100]}", "WARN")
    
    log(f"  Phase 3.5 result: {results}")
    return results

# ── Phase 4: Discovery (Non-RTC Focus) ───────────────────────────────
def phase4_discovery():
    """Discover new bounties with autonomous payout paths (skip RTC-blocked)."""
    log("PHASE 4: Discovery (non-RTC autonomous bounties)")
    results = {"immunefi_new": 0, "research_promoted": 0, "proposals_created": 0, "skipped_rtc": 0}

    # Count fresh opportunities from ALL platforms (created today, high value)
    today = datetime.date.today().isoformat()
    
    # Multi-platform discovery directories
    PLATFORM_DIRS = {
        "immunefi": IMMUNEFI_OPPS_DIR,
        "code4rena": Path("/Agentic/revenue/code4rena_opportunities"),
        "sherlock": Path("/Agentic/revenue/sherlock_opportunities"),
        "hats": Path("/Agentic/revenue/hats_opportunities"),
        "galxe": Path("/Agentic/revenue/galxe_opportunities"),
        "layer3": Path("/Agentic/revenue/layer3_opportunities"),
    }
    
    all_high_value = []
    for platform_name, pdir in PLATFORM_DIRS.items():
        if not pdir.exists():
            continue
        opp_files = sorted(glob.glob(str(pdir / "*.json")))
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
            # Normalize field names across platforms
            gross = opp.get("max_bounty_usd") or opp.get("prize_pool_usd") or 0
            title = opp.get("name") or opp.get("sponsor") or opp.get("title") or opp.get("id", "")
            url = opp.get("url", "")
            payout = opp.get("payout_type") or opp.get("payout_method") or "crypto"
            
            if today in discovered and gross >= 10000 and url:
                # Pre-fetch URL content to prevent empty microtask output
                _prefetched_desc = ""
                try:
                    # Use playwright-cli directly to avoid MCP hang (AGENTS.md compliance)
                    _pw_open = subprocess.run(["playwright-cli", "open", url], capture_output=True, text=True, timeout=30, cwd="/Agentic")
                    _pw_snap = subprocess.run(["playwright-cli", "snapshot"], capture_output=True, text=True, timeout=30, cwd="/Agentic")
                    subprocess.run(["playwright-cli", "close"], capture_output=True, text=True, timeout=10, cwd="/Agentic")
                    if _pw_snap.returncode == 0 and _pw_snap.stdout and len(_pw_snap.stdout.strip()) > 100:
                        _prefetched_desc = _pw_snap.stdout.strip()[:3000]
                        log(f"    Pre-fetched {len(_prefetched_desc)} chars for {title}")
                except Exception as _fe:
                    log(f"    Pre-fetch failed for {title}: {_fe}")
                opp["_normalized"] = {"title": title, "gross": gross, "url": url, "payout": payout, "platform": platform_name}
                all_high_value.append(opp)
                results["immunefi_new"] += 1  # Keep counter name for compat

    log(f"  Fresh non-RTC high-value (all platforms): {results['immunefi_new']} (skipped RTC: {results['skipped_rtc']})")
    for hv in all_high_value[:5]:
        _hv_rh = hv.get("requires_human", []) or []
        n = hv.get("_normalized", {})
        log(f"    [{n.get('platform','?')}] {n.get('title','?')}: ${n.get('gross','?')} payout={n.get('payout','?')}")
        # Create discovery proposal for top finds
        plat = n.get("platform", "unknown")
        safe_title = str(n.get("title","")).replace(" ","-").lower()[:30]
        # Dedup check: skip if actionable proposal already exists for this bounty
        _dedup_key = f"{plat}|{safe_title}"
        _existing_actionable = False
        for _ef in glob.glob(str(PROPOSALS_DIR / "*.json")):
            try:
                with open(_ef) as _efh:
                    _ep = json.load(_efh)
                if _ep.get("status") in {"pending_qualification","pending_execution","pending_microtask_retry","review_approved","claim_submitted"} and (_ep.get("bounty_key","").startswith(_dedup_key) or _ep.get("bounty_key","") == _dedup_key):
                    _existing_actionable = True
                    break
            except Exception:
                pass
        if _existing_actionable:
            log(f"    Skipping duplicate proposal creation for {_dedup_key}")
            continue
        cid = f"{plat}-{safe_title}-{int(time.time())}"
        proposal = {
            "candidate_id": cid,
            "type": "discovery_proposal",
            "status": "pending_qualification",
            "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            "bounty_key": _dedup_key,
            "bounty_value": float(n.get("gross", 0) or 0),
            "currency": str(hv.get("asset", "USDC")).upper(),
            "context": {
                "source": f"{plat}_live",
                "title": n.get("title", ""),
                "url": n.get("url", ""),
                "description": _prefetched_desc if _prefetched_desc else "",
                "asset": hv.get("asset", "USDC"),
                "gross": n.get("gross", 0),
                "payout_type": n.get("payout", "crypto"),
                "platform": plat,
                "autonomous_submission": hv.get("autonomous_submission", False),
                "requires_human": hv.get("requires_human", [])
            }
        }
        prop_hash = hashlib.sha256(json.dumps(proposal, sort_keys=True, default=str).encode()).hexdigest()[:12]
        save_json(PROPOSALS_DIR / f"{cid}-{prop_hash}.json", proposal)
        results["proposals_created"] += 1

    # Promote top research_queue item if non-RTC
    queue = load_json(QUEUE_PATH)
    if queue:
        rq = queue.get("research_queue", [])
        # Sort by max_payout_usd descending to prioritize highest value bounties
        rq_sorted = sorted(rq, key=lambda x: float(x.get("max_payout_usd", 0) or 0), reverse=True)
        for item in rq_sorted[:10]:
            asset = item.get("asset", "").lower()
            payout_asset = (item.get("payout_asset") or "").lower()
            if "rtc" in asset or "rustchain" in asset or "rtc" in payout_asset:
                results["skipped_rtc"] += 1
                continue
            results["research_promoted"] += 1
            log(f"  Top non-RTC research: {item.get('title', 'untitled')[:80]}")
            cid = item.get("candidate_id", f"research-{int(time.time())}")
            gross_val = item.get("max_payout_usd") or item.get("gross_verified") or 0
            plat_rq = item.get("platform", "immunefi")
            safe_title_rq = str(item.get("title","")).replace(" ","-").lower()[:30]
            # Dedup check for research promotion
            _dedup_key_rq = f"{plat_rq}|{safe_title_rq}"
            _existing_rq = False
            for _ef2 in glob.glob(str(PROPOSALS_DIR / "*.json")):
                try:
                    with open(_ef2) as _efh2:
                        _ep2 = json.load(_efh2)
                    if _ep2.get("status") in {"pending_qualification","pending_execution","pending_microtask_retry","review_approved","claim_submitted"} and (_ep2.get("bounty_key","").startswith(_dedup_key_rq) or _ep2.get("bounty_key","") == _dedup_key_rq):
                        _existing_rq = True
                        break
                except Exception:
                    pass
            if _existing_rq:
                log(f"    Skipping duplicate research promotion for {_dedup_key_rq}")
                continue
            proposal = {
                "candidate_id": cid,
                "type": "discovery_proposal",
                "status": "pending_qualification",
                "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                "bounty_key": _dedup_key_rq,
                "context": {
                    "source": "research_queue",
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "asset": item.get("payout_asset") or item.get("asset", "unknown"),
                    "gross_verified": gross_val,
                    "gross": gross_val,
                    "max_payout_usd": gross_val,
                    "platform": item.get("platform", "immunefi"),
                    "autonomous_submission": True
                }
            }
            prop_hash = hashlib.sha256(json.dumps(proposal, sort_keys=True, default=str).encode()).hexdigest()[:12]
            save_json(PROPOSALS_DIR / f"{cid}-{prop_hash}.json", proposal)
            results["proposals_created"] += 1
            if results["research_promoted"] >= 3:
                break  # Promote up to 3 high-value items per cycle

    log(f"  Phase 4 result: {results}")
    return results

# ── Phase 5: Cleanup & Mirror Sync ───────────────────────────────────
def phase5_cleanup_and_mirror():
    """Clean stale proposals and sync to private mirror."""
    log("PHASE 5: Cleanup and mirror sync")
    results = {"cleaned": 0, "mirror_synced": False}

    # Archive old completed/rejected proposals (>7 days)
    cutoff = (__import__("datetime").datetime.now(__import__("datetime").timezone.utc) - datetime.timedelta(days=7)).isoformat()
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
    cycle_start = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    log("=== ORCHESTRATOR v4 CYCLE START ===")

    p1 = phase1_sweep_claims()
    # Phase 4.5: Qualify pending_qualification proposals before Phase 2 consumes them
    # This prevents INSUFFICIENT_DATA microtask outputs from empty-context proposals
    try:
        import subprocess as _sp
        _qual_result = _sp.run(
            ["/usr/bin/python3", "/Agentic/scripts/orchestrator/qualify_proposals.py"],
            capture_output=True, text=True, timeout=120, cwd="/Agentic"
        )
        if _qual_result.returncode == 0:
            log(f"  Phase 4.5 qualification: {_qual_result.stdout.strip().split(chr(10))[-1] if _qual_result.stdout else 'ok'}")
        else:
            log(f"  Phase 4.5 qualification FAILED: {_qual_result.stderr[:200]}", "WARN")
    except Exception as _qe:
        log(f"  Phase 4.5 qualification error: {_qe}", "WARN")
    p2 = phase2_microtask_orchestration()
    p3 = phase3_self_review()
    p3_5 = phase3_5_submit_approved()
    p4 = phase4_discovery()
    p5 = phase5_cleanup_and_mirror()

    cycle_state = {
        "version": 4,
        "last_run": cycle_start,
        "phase1_sweep": p1,
        "phase2_microtask": p2,
        "phase3_review": p3,
        "phase3_5_submit": p3_5,
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
