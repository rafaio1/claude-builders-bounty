#!/usr/bin/env python3
"""Telegram Listener for Codex Session 22183.
Polls Telegram for new messages and injects them into the active Codex session stdin.
Runs with full access (root, no sandbox)."""
import sys
import os
import subprocess
import time

sys.path.insert(0, "/Agentic/src")
from telegram_ops import start_listener, send_message, _log, POLL_INTERVAL_SEC

CODEX_SESSION_ID = "22183"
CODEX_PID = "668289"
TTY_PATH = "/dev/pts/4"
FIFO_PATH = f"/tmp/codex-{CODEX_SESSION_ID}.stdin"


def find_codex_tty():
    """Try to find the PTY slave path for the running codex session."""
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid,tty,cmd"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if "codex" in line and CODEX_SESSION_ID in line:
                parts = line.split()
                if len(parts) >= 2 and parts[1] != "?":
                    tty = parts[1]
                    if not tty.startswith("/"):
                        tty = f"/dev/{tty}"
                    if os.path.exists(tty):
                        return tty
    except Exception as e:
        _log(f"TTY discovery error: {e}", "WARN")
    return None


def inject_to_codex(text: str):
    """Send text to Codex session via TTY (primary) or FIFO (fallback)."""
    _log(f"Injecting to Codex {CODEX_SESSION_ID}: {text[:80]}")
    # Primary: write directly to the TTY where codex is reading stdin
    tty = TTY_PATH
    if not os.path.exists(tty):
        tty = find_codex_tty()
    if tty and os.path.exists(tty):
        try:
            with open(tty, "w") as f:
                f.write(text + "\n")
            _log(f"Sent via TTY {tty}")
            return True
        except Exception as e:
            _log(f"TTY write failed: {e}", "WARN")
    # Fallback: FIFO
    if os.path.exists(FIFO_PATH):
        try:
            with open(FIFO_PATH, "w") as f:
                f.write(text + "\n")
            _log("Sent via FIFO")
            return True
        except Exception as e:
            _log(f"FIFO write failed: {e}", "WARN")
    send_message(f"⚠️ Não consegui injetar o comando na sessão Codex.")
    return False


def on_message(text: str):
    """Handler called by telegram_ops when a new message arrives."""
    if not text.strip():
        return
    inject_to_codex(text)


if __name__ == "__main__":
    _log(f"Starting Telegram listener for Codex session {CODEX_SESSION_ID}")
    _log(f"FIFO path: {FIFO_PATH}")
    _log(f"Poll interval: {POLL_INTERVAL_SEC}s")
    if not os.path.exists(FIFO_PATH):
        try:
            os.mkfifo(FIFO_PATH)
            os.chmod(FIFO_PATH, 0o666)
            _log(f"Created FIFO at {FIFO_PATH}")
        except Exception as e:
            _log(f"Could not create FIFO: {e}", "WARN")
    thread = start_listener(handler=on_message, daemon=False)
    try:
        thread.join()
    except KeyboardInterrupt:
        _log("Listener stopped by user")
