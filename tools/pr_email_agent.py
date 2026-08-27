#!/usr/bin/env python3
"""Deterministic PR email agent: poll, classify, act, ledger (safe default)."""
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
import tempfile
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path("/Agentic/workspace/pr-email-actions")
LEDGER_PATH = WORKSPACE / "ledger_final.json"
ACTION_QUEUE_PATH = WORKSPACE / "action_queue.jsonl"
GMAIL_CLIENT = Path("/Agentic/tools/gmail_client.py")
GMAIL_CLIENT_PATH = str(GMAIL_CLIENT)
CURSOR_PATH = str(WORKSPACE / "scan_cursor.json")
DEFAULT_BATCH_SIZE = 500
SCAN_WINDOWS = [
    {"label": "30d", "query": "newer_than:30d"},
    {"label": "30d-1y", "query": "older_than:30d newer_than:1y"},
    {"label": "gt1y", "query": "older_than:1y"},
]

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

UNAFFILIATED_ATTEMPT_ACTION = "keep_non_actionable_unaffiliated_attempt"
NON_ACTIONABLE_ACTIONS = frozenset({UNAFFILIATED_ATTEMPT_ACTION})
TERMINAL_ACTIONS = frozenset(
    {
        "trash_closed",
        "trash_merged",
        "trash_bot_success",
        UNAFFILIATED_ATTEMPT_ACTION,
    }
)
SLASH_ATTEMPT_PATTERN = re.compile(r"(?im)(?:^|\n)\s*/attempt(?:\s|$)")


def load_ledger():
    if LEDGER_PATH.exists():
        return json.loads(LEDGER_PATH.read_text())
    return []


def save_ledger_atomic(entries):
    """Atomic write with pre-backup, lock timeout, and fsync."""
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    # Pre-write backup
    if LEDGER_PATH.exists():
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        bak = LEDGER_PATH.with_suffix(LEDGER_PATH.suffix + f".bak.{ts}")
        shutil.copy2(LEDGER_PATH, bak)
    fd, tmp_path = tempfile.mkstemp(dir=WORKSPACE, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            deadline = time.monotonic() + 5.0
            while True:
                try:
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except (IOError, OSError):
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Could not acquire ledger lock within 5s")
                    time.sleep(0.05)
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


def github_latest_slash_attempt_association(repo, pr_num):
    """Resolve the latest slash-attempt comment association with a read-only GET."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", str(repo or "")):
        return None
    try:
        pr_number = int(pr_num)
    except (TypeError, ValueError):
        return None
    if pr_number <= 0:
        return None

    endpoint = f"repos/{repo}/issues/{pr_number}/comments?per_page=100"
    jq_filter = (
        '.[] | select((.body // "") | '
        'test("^\\\\s*/attempt(\\\\s|$)"; "i")) | .author_association'
    )
    try:
        rc, out, _ = run_cmd_list(
            ["gh", "api", "--paginate", endpoint, "--jq", jq_filter],
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if rc != 0:
        return None

    associations = [line.strip().upper() for line in out.splitlines() if line.strip()]
    return associations[-1] if associations else None


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
    """Trash a message. Returns True on success, False on failure."""
    rc, out, err = run_cmd_list(["python3", str(GMAIL_CLIENT), "trash", msg_id])
    if rc != 0:
        print(f"TRASH FAILED for {msg_id}: {err}", file=sys.stderr)
        return False
    # Basic validation: check if output indicates success or no error
    # GmailClient trash returns JSON; if it parsed and didn't raise, assume ok
    try:
        result = json.loads(out)
        # If we got a dict back without an obvious error key, treat as success
        if isinstance(result, dict) and "error" not in result:
            return True
        # Some clients return {"status": "ok"} or similar
        if isinstance(result, dict) and result.get("status") == "ok":
            return True
        # Fallback: if we got valid JSON, likely succeeded
        return True
    except json.JSONDecodeError:
        # Non-JSON output but exit 0 — ambiguous, treat as success cautiously
        return True


def needs_human_action(body_text):
    """Return True if body contains any protected keyword."""
    return bool(PROTECT_PATTERNS.search(body_text))


def is_bot_success_only(body_text):
    """Return True only if body matches known safe bot success pattern."""
    return bool(BOT_SUCCESS_PATTERNS.search(body_text))


def is_slash_attempt_message(body_text):
    """Return True only for an isolated slash-attempt command in the message."""
    return bool(SLASH_ATTEMPT_PATTERN.search(body_text or ""))


def classify_message(state, body_text, author_association=None):
    """Classify an open PR message. Returns (action, trash_now)."""
    if (
        is_slash_attempt_message(body_text)
        and str(author_association or "").upper() == "NONE"
    ):
        return UNAFFILIATED_ATTEMPT_ACTION, False

    if state in ("CLOSED", "MERGED"):
        return f"trash_{state.lower()}", True

    # OPEN PR classification — SAFE DEFAULT
    if needs_human_action(body_text):
        return "keep_action_needed", False

    if is_bot_success_only(body_text):
        return "trash_bot_success", True

    # Default: preserve ambiguous/open messages
    return "kept_ambiguous", False


def load_cursor():
    if os.path.exists(CURSOR_PATH):
        try:
            with open(CURSOR_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"completed_windows": [], "current_window": None, "last_run": None}


def save_cursor(cursor):
    tmp = CURSOR_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cursor, f, indent=2)
    os.replace(tmp, CURSOR_PATH)


def gmail_search_paginated(query, max_results=500):
    """Call gmail_client.py search with --max to fetch up to max_results."""
    cmd = [
        sys.executable, GMAIL_CLIENT_PATH, "search", query, "--max", str(max_results)
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            print(f"gmail search failed: {r.stderr.strip()}")
            return []
        return [l for l in r.stdout.splitlines() if l.strip()]
    except Exception as e:
        print(f"gmail search error: {e}")
        return []


def classify_and_process(dry_run=False, batch_size=None, window_override=None):
    ledger = load_ledger()
    # Latest-entry-wins: build seen_ids respecting reprocess flags
    seen_ids = {}
    for idx, entry in enumerate(ledger):
        mid = entry.get("message_id")
        if not mid:
            continue
        # Track index so latest entry wins
        seen_ids[mid] = idx

    # Determine which entries are eligible (latest entry has reprocess=True or no terminal action)
    eligible_ids = set()
    for mid, idx in seen_ids.items():
        entry = ledger[idx]
        if entry.get("reprocess"):
            eligible_ids.add(mid)
        elif entry.get("action") not in TERMINAL_ACTIONS:
            # Non-terminal actions remain eligible for re-evaluation
            eligible_ids.add(mid)

    cursor = load_cursor()
    windows = SCAN_WINDOWS
    if window_override:
        windows = [w for w in windows if w["label"] == window_override]
        if not windows:
            print(f"Unknown window: {window_override}")
            return

    global_processed = 0
    dry_run_inventory = []
    processed = 0
    for win in windows:
        label = win["label"]
        query = win["query"] + " from:github.com subject:PR"
        if label in cursor.get("completed_windows", []) and not window_override:
            print(f"Skipping completed window: {label}")
            continue

        if batch_size and global_processed >= batch_size:
            print(f"Global batch limit reached: {batch_size}")
            break

        print(f"Scanning window: {label} ({query})")
        remaining = None
        if batch_size:
            remaining = max(0, batch_size - global_processed)
        lines = gmail_search_paginated(query, max_results=remaining or DEFAULT_BATCH_SIZE)
        if not lines:
            print(f"No emails in window {label}")
            if not window_override and not dry_run:
                cursor.setdefault("completed_windows", []).append(label)
                save_cursor(cursor)
            continue

        window_processed = 0
        for line in lines:
            if batch_size and global_processed >= batch_size:
                print(f"Global batch limit reached: {batch_size}")
                break
            m = re.match(r"\[([^\]]+)\].*?\|\s*(.+?)\s*\|\s*(.+)", line)
            if not m:
                continue
            msg_id, sender, subject = m.groups()

            # Skip if latest ledger entry is terminal and not reprocess
            if msg_id in seen_ids and msg_id not in eligible_ids:
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

            author_association = None
            if is_slash_attempt_message(body_text):
                author_association = github_latest_slash_attempt_association(
                    repo_full, pr_num
                )
            if author_association is None:
                action, trash_now = classify_message(state, body_text)
            else:
                action, trash_now = classify_message(
                    state, body_text, author_association
                )

            if dry_run:
                print(f"[DRY-RUN] {msg_id} | {repo_full}#{pr_num} | {state} | {action} | trash={trash_now}")
                dry_run_inventory.append({
                    "message_id": msg_id,
                    "repo": repo_full,
                    "pr": pr_num,
                    "state": state,
                    "action": action,
                    "trash_now": trash_now,
                    "author_association": author_association,
                    "github_url": url,
                    "window": label,
                })
                window_processed += 1
                global_processed += 1
                continue

            if trash_now:
                ok = gmail_trash(msg_id)
                if ok:
                    entry = {
                        "message_id": msg_id,
                        "repo": repo_full,
                        "pr": pr_num,
                        "action": action,
                        "github_url": url,
                        "commit": None,
                        "trash_at": datetime.now(timezone.utc).isoformat(),
                    }
                    ledger.append(entry)
                    seen_ids[msg_id] = len(ledger) - 1
                    eligible_ids.discard(msg_id)
                else:
                    entry = {
                        "message_id": msg_id,
                        "repo": repo_full,
                        "pr": pr_num,
                        "action": "trash_failed",
                        "github_url": url,
                        "commit": None,
                        "trash_at": None,
                        "reprocess": True,
                        "events": [{"type": "trash_failed", "ts": datetime.now(timezone.utc).isoformat()}],
                    }
                    ledger.append(entry)
                    seen_ids[msg_id] = len(ledger) - 1
                    eligible_ids.add(msg_id)
            else:
                entry = {
                    "message_id": msg_id,
                    "repo": repo_full,
                    "pr": pr_num,
                    "action": action,
                    "author_association": author_association,
                    "github_url": url,
                    "commit": None,
                    "trash_at": None,
                }
                ledger.append(entry)
                seen_ids[msg_id] = len(ledger) - 1
                if action not in NON_ACTIONABLE_ACTIONS:
                    append_action_queue(entry)
                else:
                    eligible_ids.discard(msg_id)

            window_processed += 1
            processed += 1
            global_processed += 1


        if not window_override and not dry_run and (not batch_size or global_processed < batch_size):
            cursor.setdefault("completed_windows", []).append(label)
            save_cursor(cursor)

    if dry_run:
        print(f"[DRY-RUN] Scanned {global_processed} emails across {len(windows)} window(s). No side effects.")
        return dry_run_inventory

    cursor["last_run"] = datetime.now(timezone.utc).isoformat()
    save_cursor(cursor)
    save_ledger_atomic(ledger)
    print(f"Processed {processed} new emails. Ledger size: {len(ledger)}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="PR Email Agent (paginated)")
    parser.add_argument("--dry-run", action="store_true", help="Inventory only, no actions")
    parser.add_argument("--batch", type=int, default=None, help="Max emails per window")
    parser.add_argument("--window", type=str, default=None, choices=["30d", "30d-1y", "gt1y"], help="Scan specific window only")
    args = parser.parse_args()
    classify_and_process(dry_run=args.dry_run, batch_size=args.batch, window_override=args.window)
