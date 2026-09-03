#!/usr/bin/env python3
"""Disabled legacy bridge.

The former implementation injected Telegram text into a fixed root TTY and
tailed a fixed Codex rollout. That is intentionally not a supported execution
path. Use telegram-bridge.service plus telegram-command-dispatcher.timer.
"""

raise SystemExit("legacy Codex/TTY Telegram bridge disabled; use the bounded dispatcher")
