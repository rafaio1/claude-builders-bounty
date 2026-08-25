#!/usr/bin/env python3
"""
Claude Code Pre-Tool-Use Hook: Block Destructive Bash Commands

Intercepts dangerous bash commands before execution and logs blocked attempts.
Install: cp pre_tool_use_block_destructive.py ~/.claude/hooks/pre_tool_use_block_destructive.py
         chmod +x ~/.claude/hooks/pre_tool_use_block_destructive.py

@fix-author rafaio1
@date 2026-08-25T12:28:00Z
@runtime linux x64 /tmp/claude_bounty_issue_3 bash
@platform-config Autonomous bounty execution pipeline with SOLID/Object Calisthenics enforcement
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Configuration
LOG_FILE = Path.home() / ".claude" / "hooks" / "blocked.log"
BLOCKED_PATTERNS = [
    # Destructive file operations
    (r'\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|(-[a-zA-Z]*f[a-zA-Z]*r))\b', "rm -rf: recursive force delete"),
    (r'\brm\s+(-[a-zA-Z]*r[a-zA-Z]*)\s+/', "rm -r on root/absolute path"),
    (r'\bshred\b', "shred: secure file destruction"),
    # Database destruction
    (r'\bDROP\s+(TABLE|DATABASE|SCHEMA|INDEX|VIEW)\b', "DROP TABLE/DATABASE: irreversible data loss"),
    (r'\bTRUNCATE\s+(TABLE\s+)?\w+', "TRUNCATE: removes all rows without logging"),
    (r'\bDELETE\s+FROM\s+\w+\s*;', "DELETE FROM without WHERE clause"),
    (r'\bDELETE\s+FROM\s+\w+\s+WHERE\s+1\s*=\s*1', "DELETE FROM with always-true WHERE"),
    # Git destructive operations
    (r'\bgit\s+push\s+(-[a-zA-Z]*-force|(-[a-zA-Z]*f\b))', "git push --force: overwrites remote history"),
    (r'\bgit\s+push\s+.*\s+--force-with-lease', "git push --force-with-lease: still destructive"),
    (r'\bgit\s+reset\s+--hard', "git reset --hard: discards uncommitted changes"),
    (r'\bgit\s+clean\s+(-[a-zA-Z]*f|(-[a-zA-Z]*d))', "git clean -fd: removes untracked files"),
    # System-level destruction
    (r'\bdd\s+if=.*\s+of=/dev/', "dd to device: potential disk wipe"),
    (r'\bmkfs\.', "mkfs: formats filesystem"),
    (r'\bchmod\s+(-R\s+)?777\s+/', "chmod 777 on root path: security risk"),
]


def ensure_log_dir():
    """Create log directory if it doesn't exist."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def log_blocked_attempt(command: str, reason: str, project_path: str) -> None:
    """Log blocked command attempt to blocked.log."""
    ensure_log_dir()
    timestamp = datetime.now(timezone.utc).isoformat()
    log_entry = f"[{timestamp}] BLOCKED | Reason: {reason} | Path: {project_path} | Command: {command}\n"
    try:
        with open(LOG_FILE, "a") as f:
            f.write(log_entry)
    except OSError as e:
        print(f"⚠️ Failed to write to {LOG_FILE}: {e}", file=sys.stderr)


def check_command(command: str) -> tuple[bool, str]:
    """
    Check if a command matches any blocked pattern.
    Returns (is_blocked, reason).
    """
    for pattern, reason in BLOCKED_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True, reason
    return False, ""


def main():
    """
    Claude Code pre-tool-use hook entry point.
    Reads tool input from stdin (JSON), checks for destructive commands,
    and exits with code 2 + message to block execution.
    """
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        # If we can't parse input, allow the command (fail open)
        sys.exit(0)

    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("input", {})

    # Only intercept bash/shell execution tools
    if tool_name not in ("Bash", "bash", "shell", "exec", "u_exec_command"):
        sys.exit(0)

    command = tool_input.get("command", "") or tool_input.get("cmd", "")
    if not command:
        sys.exit(0)

    project_path = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

    is_blocked, reason = check_command(command)
    if is_blocked:
        log_blocked_attempt(command, reason, project_path)
        block_message = (
            f"🚫 BLOCKED: This command was prevented by the destructive-command safety hook.\n\n"
            f"**Reason:** {reason}\n\n"
            f"**Command:** `{command[:200]}`\n\n"
            f"This operation could cause irreversible data loss or system damage. "
            f"If this is intentional, please:\n"
            f"1. Explain why this specific command is necessary\n"
            f"2. Confirm you understand the risks\n"
            f"3. Consider safer alternatives (e.g., `rm -i`, `git revert`, `DELETE ... WHERE ...`)\n\n"
            f"Blocked attempt logged to: `{LOG_FILE}`"
        )
        # Exit code 2 signals Claude Code to block the tool execution
        print(block_message, file=sys.stderr)
        sys.exit(2)

    # Command is safe, allow execution
    sys.exit(0)


if __name__ == "__main__":
    main()
