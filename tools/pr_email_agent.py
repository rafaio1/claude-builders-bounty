#!/usr/bin/env python3
"""Deterministic PR email agent: poll, classify, act, ledger (safe default)."""
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path("/Agentic/workspace/pr-email-actions")
LEDGER_PATH = WORKSPACE / "ledger_final.json"
ACTION_QUEUE_PATH = WORKSPACE / "action_queue.jsonl"
GMAIL_CLIENT = Path("/Agentic/tools/gmail_client.py")

# Keywords that ALWAYS preserve the message (never trash)
PROTECT_PATTERNS = re.compile(
     r"changes requested|review required|action required|authorize|invite|please review|"
     r"cla |contributor license|contract|payout|bounty|reward|payment|"
     r"security |vulnerability|ci failure|build failed|test fail|"
     r"question|needs info|awaiting response|human review|@[\w\-]+\s+review",
     re.IGNORECASE,
 )

# Only these bot patterns are safe to trash on OPEN PRs (informational success)
BOT_SUCCESS_PATTERNS = re.compile(
    r"vercel\[bot\].*successfully deployed|"
    r"github-actions\[bot\].*all checks passed|"
    r"codecov\[bot\].*coverage report|"
    r"dependabot\[bot\].*merged automatically",
    re.IGNORECASE,
)


def load_ledger():
    if LEDGER_PATH.exists():
        return json.loads(LEDGER_PATH.read_text())
    return []


def save_ledger_atomic(entries):
    """Atomic write with file lock to prevent corruption."""
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=WORKSPACE, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            json.dump(entries, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
            fcntl.flock(f, fcntl.LOCK_UN)
        os.replace(tmp_path, LEDGER_PATH)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def append_action_queue(entry):
    """Append to JSONL action queue atomically."""
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    with open(ACTION_QUEUE_PATH, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps(entry) + "\n")
        f.flush()
        os.fsync(f.fileno())
        fcntl.flock(f, fcntl.LOCK_UN)


def run_cmd_list(cmd_list, **kwargs):
    """Run command as list (no shell interpolation)."""
    r = subprocess.run(cmd_list, capture_output=True, text=True, **kwargs)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def gh_pr_state(repo, pr_num):
    rc, out, _ = run_cmd_list(
        ["gh", "pr", "view", str(pr_num), "--repo", repo, "--json", "state,url"]
    )
    if rc != 0:
        return None, None
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return None, None
    return data.get("state"), data.get("url")


def gmail_search(query):
    rc, out, _ = run_cmd_list(["python3", str(GMAIL_CLIENT), "search", query])
    if rc != 0:
        return []
    return [l for l in out.strip().split("\n") if l.startswith("[")]


def gmail_read(msg_id):
    rc, out, _ = run_cmd_list(["python3", str(GMAIL_CLIENT), "read", msg_id])
    if rc != 0:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def gmail_trash(msg_id):
    run_cmd_list(["python3", str(GMAIL_CLIENT), "trash", msg_id])


def needs_human_action(body_text):
    """Return True if body contains any protected keyword."""
    return bool(PROTECT_PATTERNS.search(body_text))


def is_bot_success_only(body_text):
    """Return True only if body matches known safe bot success pattern."""
    return bool(BOT_SUCCESS_PATTERNS.search(body_text))


def classify_message(state, body_text):
    """Classify an open PR message. Returns (action, trash_now)."""
    if state in ("CLOSED", "MERGED"):
        return f"trash_{state.lower()}", True

    # OPEN PR classification — SAFE DEFAULT
    if needs_human_action(body_text):
        return "keep_action_needed", False

    if is_bot_success_only(body_text):
        return "trash_bot_success", True

    # Default: preserve ambiguous/open messages
    return "kept_ambiguous", False


def classify_and_process():
    ledger = load_ledger()
    seen_ids = {e["message_id"] for e in ledger}

    lines = gmail_search("newer_than:30d from:github.com subject:PR")
    if not lines:
        print("No emails found or search failed")
        return

    processed = 0

    for line in lines:
        m = re.match(r"\[([^\]]+)\].*?\|\s*(.+?)\s*\|\s*(.+)", line)
        if not m:
            continue
        msg_id, sender, subject = m.groups()
        if msg_id in seen_ids:
            continue

        pm = re.search(r"\[([^\]]+)\].*?\(PR #(\d+)\)", subject)
        if not pm:
            continue
        repo_full, pr_str = pm.groups()
        pr_num = int(pr_str)

        state, url = gh_pr_state(repo_full, pr_num)
        if not state:
            continue

        body_text = ""
        bdata = gmail_read(msg_id)
        if bdata:
            body_text = bdata.get("body", "") + " " + bdata.get("snippet", "")

        action, trash_now = classify_message(state, body_text)

        entry = {
            "message_id": msg_id,
            "repo": repo_full,
            "pr": pr_num,
            "action": action,
            "github_url": url,
            "commit": None,
            "trash_at": datetime.now(timezone.utc).isoformat() if trash_now else None,
        }
        ledger.append(entry)
        seen_ids.add(msg_id)

        if not trash_now:
            append_action_queue(entry)
        else:
            gmail_trash(msg_id)

        processed += 1

    save_ledger_atomic(ledger)
    print(f"Processed {processed} new emails. Ledger size: {len(ledger)}")


if __name__ == "__main__":
    classify_and_process()
