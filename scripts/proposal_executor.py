#!/usr/bin/env python3
"""Proposal Executor - consumes proposals from /Agentic/data/aro/proposals/
and executes approved actions (post comments, update state) via gh CLI.
Read-only on canonical ledgers; writes only execution markers and logs.
No timeouts. Runs as systemd service every 2 minutes."""
import json, os, subprocess, sys, time, re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/Agentic")
PROPOSALS = ROOT / "data" / "aro" / "proposals"
LOG_DIR = ROOT / "logs" / "supervisor"
EXECUTED_MARKER = ".executed"

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_DIR / "proposal-executor.log", "a") as f:
        f.write(line + "\n")

def run_gh(args):
    """Run gh CLI command without timeout."""
    try:
        r = subprocess.run(
            ["gh"] + args,
            capture_output=True, text=True, timeout=None, cwd=str(ROOT)
        )
        return r.returncode == 0, r.stdout, r.stderr
    except Exception as e:
        return False, "", str(e)

def parse_bounty_key(bounty_key):
    """Parse bounty_key into (platform, owner, repo, kind, number).
    Formats supported:
      github|owner|repo|pr123
      github|owner|repo|issue456
      github|owner-repo|N|pr123  (legacy sweeper format where N is issue group)
    Returns None if unparseable."""
    parts = bounty_key.split("|")
    if len(parts) < 4:
        return None
    platform = parts[0]
    if platform != "github":
        return None

    # Detect legacy format: github|owner-repo|digit|prNNN
    # In legacy format, parts[1] contains hyphenated owner-repo or just repo name
    # and parts[2] is a digit (issue group number)
    m_target = re.match(r"(pr|issue)(\d+)", parts[3])
    if not m_target:
        return None
    kind = m_target.group(1)
    number = m_target.group(2)

    # Try standard format first: github|owner|repo|target
    if len(parts) >= 4 and "/" not in parts[1] and re.match(r"\d+$", parts[2]):
        # Legacy format: github|claude-builders-bounty|3|pr3928
        # The actual repo is likely owner/owner (e.g., claude-builders-bounty/claude-builders-bounty)
        # or we need to look up the real repo from evidence_url
        owner_repo = parts[1]
        return ("github", owner_repo, owner_repo, kind, number)
    elif "/" in parts[1]:
        # Standard: github|owner/repo|... but this doesn't match our split
        pass
    
    # Fallback: parts[1]=owner, parts[2]=repo
    if len(parts) >= 4 and not re.match(r"\d+$", parts[2]):
        return ("github", parts[1], parts[2], kind, number)
    
    return None

def execute_proposal(proposal_path):
    """Execute a single proposal file. Returns (success, message)."""
    try:
        data = json.loads(proposal_path.read_text())
    except Exception as e:
        return False, f"invalid_json: {e}"

    action = data.get("action") or data.get("next_action") or ""
    bounty_key = data.get("bounty_key", "unknown")
    comment = data.get("proposed_comment")
    evidence_url = data.get("evidence_url", "")

    # monitor_pr_review and superseded are valid but non-executable (no comment to post)
    if action in ("monitor_pr_review", "superseded", "abandon", "wait_for_review", "noop_blocked_onboarding",
                  "await_maintainer_review", "monitor_verifier_response", "verify_claim_status_and_deliverable",
                  "clone_and_investigate_rustchain_mcp",
                  "reclaim_lapsed", "investigate_claim", "provide_live_url"):
        return True, f"non_executable_{action}"
    if action not in ("claim", "fix_review_feedback", "submit_work", "qualify", "qualify_claim"):
        return False, f"action_not_executable: {action}"

    if not comment and action not in ("monitor_pr_review", "superseded"):
        return False, "no_proposed_comment"

    # Try parsing bounty_key first
    parsed = parse_bounty_key(bounty_key)
    
    # If bounty_key parsing fails or gives wrong repo, extract from evidence_url
    if not parsed and evidence_url:
        # Extract from URL like https://github.com/owner/repo/pull/123
        url_match = re.match(r"https?://github\.com/([^/]+)/([^/]+)/(pull|issues)/(\d+)", evidence_url)
        if url_match:
            owner = url_match.group(1)
            repo = url_match.group(2)
            kind = "pr" if url_match.group(3) == "pull" else "issue"
            number = url_match.group(4)
            parsed = ("github", owner, repo, kind, number)
    
    if not parsed:
        return False, f"cannot_resolve_repo: {bounty_key}"
    
    platform, owner, repo, kind, number = parsed
    full_repo = f"{owner}/{repo}"

    cmd = [kind, "comment", number, "--repo", full_repo, "--body", comment]
    ok, stdout, stderr = run_gh(cmd)

    if ok:
        marker = proposal_path.with_suffix(proposal_path.suffix + EXECUTED_MARKER)
        marker.write_text(json.dumps({
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "bounty_key": bounty_key,
            "resolved_repo": full_repo,
            "gh_output": stdout[:500]
        }, indent=2))
        log(f"EXECUTED: {action} on {full_repo}#{number} for {bounty_key}")
        return True, "posted"
    else:
        log(f"FAILED: {action} on {full_repo}#{number}: {stderr[:300]}")
        return False, f"gh_failed: {stderr[:200]}"

def main():
    log("=== Proposal Executor cycle start ===")
    if not PROPOSALS.exists():
        log("No proposals directory")
        return

    proposals = sorted(PROPOSALS.glob("*.json"))
    executed = 0
    failed = 0
    skipped = 0

    for p in proposals:
        if p.name.endswith(EXECUTED_MARKER):
            continue
        marker = p.with_suffix(p.suffix + EXECUTED_MARKER)
        if marker.exists():
            continue

        success, msg = execute_proposal(p)
        if success:
            executed += 1
        else:
            skipped += 1
            log(f"SKIP {p.name}: {msg}")

    log(f"Cycle done: executed={executed}, skipped={skipped}, total={len(proposals)}")
    # Exit cleanly when no executable work remains to avoid restart loop
    if executed == 0 and skipped > 0:
        log("No actionable proposals; exiting cleanly (no restart needed)")
        sys.exit(0)

if __name__ == "__main__":
    main()
