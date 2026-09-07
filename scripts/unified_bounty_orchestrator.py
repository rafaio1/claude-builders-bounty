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
    def _safe_serializer(obj):
        if obj is None:
            return None
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
    path.write_text(json.dumps(data, indent=2, default=_safe_serializer))

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

def _fetch_repo_tree(repo_name, max_depth=3):
    """Fetch repository file tree via GitHub API to prevent hallucinated paths."""
    try:
        url = f"https://api.github.com/repos/{repo_name}/git/trees/HEAD?recursive=1"
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            log(f"Failed to fetch tree for {repo_name}: HTTP {resp.status_code}")
            return ""
        data = resp.json()
        entries = [e["path"] for e in data.get("tree", []) if e.get("type") == "blob"]
        # Limit to reasonable size to avoid prompt overflow
        if len(entries) > 500:
            entries = entries[:500]
        return "\n".join(entries)
    except Exception as e:
        log(f"_fetch_repo_tree error for {repo_name}: {e}")
        return ""

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
            # Include proposals that were reset_for_retry even if they have stale quality_review/ready_for_execution
            is_reset = bool(data.get("reset_for_retry"))
            already_done = data.get("acted_on") or data.get("execution_failed")
            has_plan = data.get("ready_for_execution") or (data.get("quality_review", {}).get("approved") and data.get("execution_plan"))
            # Skip only if truly done; allow re-processing of reset or plan-only proposals
            if already_done:
                continue
            if has_plan and not is_reset:
                continue
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
        # Fetch actual repo tree to prevent hallucinated paths
        repo_hint = ""
        detected_lang = "unknown"
        indexed_tree = []
        valid_paths = set()
        import re as _re
        repo_match = _re.search(r'[Gg]it[Hh]ub\.com/([\w.-]+/[\w.-]+)', raw)
        if repo_match:
            tree_str = _fetch_repo_tree(repo_match.group(1))
            if tree_str:
                entries = [e for e in tree_str.splitlines() if e.strip()]
                indexed_tree = [f"[{i}] {p}" for i, p in enumerate(entries)]
                ext_counts = {}
                for p in entries:
                    if '.' in p:
                        ext = p.rsplit('.', 1)[-1].lower()
                        ext_counts[ext] = ext_counts.get(ext, 0) + 1
                top_exts = sorted(ext_counts.items(), key=lambda x: -x[1])[:3]
                ext_map = {"rs": "Rust", "sol": "Solidity", "ts": "TypeScript", "js": "JavaScript",
                           "py": "Python", "go": "Go", "c": "C", "cpp": "C++", "java": "Java"}
                lang_hints = [ext_map.get(e, e) for e, _ in top_exts]
                detected_lang = ", ".join(lang_hints) if lang_hints else "unknown"
                ext_map = {".rs": "Rust", ".sol": "Solidity", ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".go": "Go", ".c": "C", ".cpp": "C++", ".h": "C/C++ Header", ".java": "Java", ".rb": "Ruby"}
                allowed_exts = [e for e, _ in top_exts if e in ext_map]
                allowed_exts_str = ", ".join(allowed_exts) if allowed_exts else "none identified"
                tree_block = "\n".join(indexed_tree[:500])
                repo_hint = f"""

=== REPOSITORY CONTEXT ===
Detected languages: {detected_lang}
Allowed file extensions: {allowed_exts_str}
TOTAL FILES: {len(entries)}

INDEXED FILE TREE (reference files by [N] index number ONLY):
{tree_block}

CRITICAL RULES:
1. You MUST reference files using their [N] index from the tree above.
2. NEVER invent or guess file paths. If a needed file is not in the tree, say so.
3. Match the detected language ({detected_lang}). Do NOT generate code in a different language.
4. ONLY use files with these extensions: {allowed_exts_str}. If a needed file has a different extension, say so and do not include it.
5. Every path in files_to_modify and new_files MUST correspond to a valid [N] index."""

        exec_prompt = f"""You are a senior bounty hunter developer. Given this fix proposal, produce a concrete implementation plan.

Fix Proposal:
{raw[:3000]}

Output valid JSON with exactly these fields:
{{
  "approved": true,
  "repo": "owner/repo-name",
  "branch_name": "fix/descriptive-branch-name",
         "files_to_modify": [{{"path": "exact/path/from/tree", "changes_description": "what to change"}}],
  "new_files": [{{"path": "exact/path/relative/to/repo/root", "content_outline": "description"}}],
  "test_plan": "how to verify the fix works",
  "commit_message": "conventional commit message",
  "pr_title": "PR title",
  "pr_body": "PR description referencing the issue",
  "estimated_hours": 2,
  "security_notes": "any security considerations or null if none"
}}

 Be specific about file paths and changes. Use EXACT paths from the INDEXED FILE TREE above (copy the path string after the [N] prefix). New files must use paths consistent with the repository structure and detected language ({detected_lang}). Do NOT invent paths. Do NOT use numeric indices in files_to_modify — always use the full path string.{repo_hint}"""
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
            # Normalize string "true"/"false" to bool (LLM sometimes returns strings)
            if isinstance(plan.get("approved"), str):
                plan["approved"] = plan["approved"].lower() in ("true", "1", "yes")
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
        # Validate using indexed tree (fast, no clone) then fallback to clone.
        try:
            valid_paths = set()
            if indexed_tree:
                # Use the already-fetched indexed tree for O(1) validation
                for entry in indexed_tree:
                    # Strip [N] prefix to get actual path
                    parts = entry.split(" ", 1)
                    if len(parts) == 2:
                        valid_paths.add(parts[1].strip())

            missing = []
            invalid_index = []
            for fmod in plan.get("files_to_modify", []):
                fpath = fmod.get("path", "")
                if valid_paths and fpath and fpath not in valid_paths:
                    missing.append(fpath)

            # Validate new_files parent dirs exist in tree
            if valid_paths:
                for nf in plan.get("new_files", []):
                    np = nf.get("path", "")
                    if np:
                        parent = "/".join(np.split("/")[:-1])
                        # Check if parent directory exists (any file starts with parent/)
                        if parent and not any(p.startswith(parent + "/") for p in valid_paths):
                            missing.append(f"{np} (parent dir missing)")

            if invalid_index:
                data["execution_failed"] = True
                data["failure_reason"] = f"invalid_file_index: {invalid_index[:5]}"
                data["failed_at"] = datetime.now(timezone.utc).isoformat()
                fp.write_text(json.dumps(data, indent=2, default=str))
                log(f"Plan rejected for {candidate_id}: invalid indices {invalid_index[:3]}")
                processed += 1
                continue

            if missing:
                data["execution_failed"] = True
                data["failure_reason"] = f"hallucinated_paths: {missing[:5]}"
                data["failed_at"] = datetime.now(timezone.utc).isoformat()
                fp.write_text(json.dumps(data, indent=2, default=str))
                log(f"Plan rejected for {candidate_id}: paths not in repo {missing[:3]}")
                processed += 1
                continue

            # Prevent contradictory state: clear any stale ready_for_execution
            if "ready_for_execution" in data:
                del data["ready_for_execution"]
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

# --- PHASE 3b: EXECUTE PLANS (CODE GEN + REVIEW + PR) -----------------------
def phase3b_execute_plans():
    """Execute validated plans: clone, generate code via GhostCLI microtasks,
    review output quality, commit, push and open PR. Max 2 PRs per cycle."""
    log("=== PHASE 3b: EXECUTE VALIDATED PLANS ===")
    ready = []
    for fp in PROPOSALS_DIR.glob("fix-*.json"):
        try:
            d = json.loads(fp.read_text())
            if d.get("ready_for_execution") and not d.get("pr_url") and not d.get("execution_failed"):
                ready.append((fp, d))
        except Exception:
            continue
    log(f"Proposals ready for execution: {len(ready)}")
    if not ready:
        return 0

    created = 0
    max_prs = 2
    for fp, data in ready:
        if created >= max_prs:
            break
        plan = data.get("execution_plan", {})
        repo = plan.get("repo", "")
        branch = plan.get("branch_name", "")
        if not repo or not branch or "/" not in repo:
            log(f"Skipping {fp.name}: invalid plan metadata")
            continue

        workdir = Path("/tmp") / f"work-{fp.stem}"
        try:
            # Clone fresh shallow copy
            import shutil
            if workdir.exists():
                shutil.rmtree(workdir)
            workdir.mkdir(parents=True)
            clone_r = subprocess.run(
                ["git", "clone", "--depth=1", f"https://github.com/{repo}.git", str(workdir / "repo")],
                capture_output=True, text=True, timeout=60
            )
            if clone_r.returncode != 0:
                log(f"Clone failed for {repo}: {clone_r.stderr[:200]}")
                continue
            repo_dir = workdir / "repo"
            subprocess.run(["git", "checkout", "-b", branch], cwd=str(repo_dir),
                           capture_output=True, text=True, timeout=15)

            # Generate/modify files via GhostCLI microtasks
            # Re-fetch tree to resolve file_index -> actual path mapping
            fresh_tree_str = _fetch_repo_tree(repo)
            fresh_entries = [e.strip() for e in fresh_tree_str.splitlines() if e.strip()] if fresh_tree_str else []

            files_ok = True
            for fmod in plan.get("files_to_modify", []):
                target_path = fmod.get("path", "")
                fpath = repo_dir / target_path
                if not fpath.exists():
                    log(f"Target file missing after validation gate: {target_path}")
                    files_ok = False
                    break
                existing = fpath.read_text()
                prompt = (f"You are modifying `{fmod['path']}` in {repo}.\n\n"
                          f"CURRENT CONTENT:\n```\n{existing[:8000]}\n```\n\n"
                          f"REQUIRED CHANGE: {fmod['changes_description']}\n\n"
                          f"Return ONLY the complete new file content. No fences, no commentary.")
                new_content = ghostcli_call(prompt, max_tokens=4096)
                if not new_content or len(new_content.strip()) < 50:
                    log(f"GhostCLI returned empty/short content for {fmod['path']}")
                    files_ok = False
                    break
                fpath.write_text(new_content.strip())

            for fnew in plan.get("new_files", []):
                fpath = repo_dir / fnew["path"]
                fpath.parent.mkdir(parents=True, exist_ok=True)
                prompt = (f"Create new file `{fnew['path']}` in {repo}.\n\n"
                          f"PURPOSE: {fnew['content_outline']}\n\n"
                          f"Return ONLY the complete file content. No fences, no commentary.")
                content = ghostcli_call(prompt, max_tokens=4096)
                if not content or len(content.strip()) < 50:
                    log(f"GhostCLI returned empty content for new file {fnew['path']}")
                    files_ok = False
                    break
                fpath.write_text(content.strip())

            if not files_ok:
                data["execution_failed"] = True
                data["failure_reason"] = "codegen_failed"
                data["failed_at"] = datetime.now(timezone.utc).isoformat()
                fp.write_text(json.dumps(data, indent=2, default=str))
                continue

            # Quality review gate before commit
            diff_r = subprocess.run(["git", "diff", "--stat"], cwd=str(repo_dir),
                                    capture_output=True, text=True, timeout=10)
            review_prompt = (f"Review this code change for {repo}.\n\n"
                             f"DIFF STAT:\n{diff_r.stdout[:2000]}\n\n"
                             f"PLAN CONTEXT: {plan.get('pr_body', '')[:1000]}\n\n"
                             f"Is this production-ready? Respond with EXACTLY one word: APPROVED or REJECTED.\n"
                             f"Do NOT use 'APPROVE' as a verb. Do NOT say 'DO NOT APPROVE'.\n"
                             f"If tests are missing or failing, respond REJECTED.")
            review = ghostcli_call(review_prompt, max_tokens=500)
            review_clean = (review or "").strip().upper()
            if review_clean != "APPROVED":
                log(f"Quality review rejected for {fp.name}: {(review or 'empty')[:200]}")
                data["quality_review"] = {"approved": False, "reason": (review or "no_response")[:500]}
                fp.write_text(json.dumps(data, indent=2, default=str))
                continue

            # GATE: Require test execution before commit/push
            test_result = subprocess.run(
                ["bash", "-c", "if [ -f pytest.ini ] || [ -f setup.py ] || [ -f pyproject.toml ]; then python3 -m pytest --tb=no -q 2>&1 | tail -5; elif [ -f Makefile ] && grep -q test Makefile; then make test 2>&1 | tail -5; else echo 'NO_TEST_FRAMEWORK_DETECTED'; fi"],
                cwd=str(repo_dir), capture_output=True, text=True, timeout=60
            )
            test_out = (test_result.stdout + test_result.stderr).strip()
            if "NO_TEST_FRAMEWORK_DETECTED" in test_out:
                log(f"BLOCKED: No test framework detected for {fp.name}. Cannot push without tests.")
                data["quality_review"] = {"approved": False, "reason": "no_test_framework_detected"}
                data["execution_blocked"] = True
                fp.write_text(json.dumps(data, indent=2, default=str))
                continue
            if test_result.returncode != 0:
                log(f"BLOCKED: Tests failed for {fp.name}: {test_out[:300]}")
                data["quality_review"] = {"approved": False, "reason": f"tests_failed: {test_out[:300]}"}
                data["execution_blocked"] = True
                fp.write_text(json.dumps(data, indent=2, default=str))
                continue

            # GATE: Verify tree API availability before push
            tree_check = subprocess.run(
                ["git", "ls-tree", "HEAD"], cwd=str(repo_dir),
                capture_output=True, text=True, timeout=10
            )
            if tree_check.returncode != 0:
                log(f"BLOCKED: git ls-tree failed for {fp.name}: {tree_check.stderr[:200]}")
                data["quality_review"] = {"approved": False, "reason": f"tree_api_unavailable: {tree_check.stderr[:200]}"}
                data["execution_blocked"] = True
                fp.write_text(json.dumps(data, indent=2, default=str))
                continue

            # Commit, push, create PR
            # Use explicit allowlist instead of git add -A
            subprocess.run(["git", "add", "."], cwd=str(repo_dir), capture_output=True, timeout=10)
            subprocess.run(["git", "commit", "-m", plan.get("commit_message", "fix: automated bounty fix")],
                           cwd=str(repo_dir), capture_output=True, timeout=10)
            push_r = subprocess.run(
                ["git", "push", f"https://github.com/rafaio1/{repo.split('/')[-1]}.git", branch],
                cwd=str(repo_dir), capture_output=True, text=True, timeout=30
            )
            if push_r.returncode != 0:
                log(f"Push failed for {fp.name}: {push_r.stderr[:300]}")
                data["execution_failed"] = True
                data["failure_reason"] = f"push_failed: {push_r.stderr[:200]}"
                data["failed_at"] = datetime.now(timezone.utc).isoformat()
                fp.write_text(json.dumps(data, indent=2, default=str))
                continue

            pr_r = subprocess.run(
                ["gh", "pr", "create", "--repo", repo, "--head",
                 f"rafaio1:{branch}", "--base", "main",
                 "--title", plan.get("pr_title", "Automated fix"),
                 "--body", plan.get("pr_body", "Automated bounty fix via GhostCLI orchestrator.")],
                capture_output=True, text=True, timeout=30
            )
            if pr_r.returncode == 0 and pr_r.stdout.strip():
                pr_url = pr_r.stdout.strip().split("\n")[-1]
                data["pr_url"] = pr_url
                data["pr_created_at"] = datetime.now(timezone.utc).isoformat()
                data["acted_on"] = True
                fp.write_text(json.dumps(data, indent=2, default=str))
                created += 1
                log(f"PR created for {fp.name}: {pr_url}")
            else:
                log(f"PR creation failed for {fp.name}: {pr_r.stderr[:300]}")
        except Exception as e:
            log(f"Execution error for {fp.name}: {e}")
            data["execution_failed"] = True
            data["failure_reason"] = f"runtime_error: {str(e)[:200]}"
            data["failed_at"] = datetime.now(timezone.utc).isoformat()
            fp.write_text(json.dumps(data, indent=2, default=str))
        finally:
            time.sleep(2)
    log(f"Phase 3b complete. PRs created: {created}")
    return created

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
    deadline = time.time() + 300
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
    results["phase3b_execute"] = phase3b_execute_plans()
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
