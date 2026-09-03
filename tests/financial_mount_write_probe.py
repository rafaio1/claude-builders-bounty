#!/usr/bin/env python3
from __future__ import annotations

import errno
import os


TARGETS = (
    ("ingress", "/Agentic/data/aro/proposals/ledger_proposals.jsonl", True),
    ("decisions", "/Agentic/data/aro/proposals/proposal_decisions.jsonl", False),
    ("email_signals", "/Agentic/data/aro/proposals/email_bounty_signals.jsonl", False),
    ("canonical_bounty", "/Agentic/data/aro/bounty_receive_ledger.json", False),
    ("canonical_realized", "/Agentic/data/aro/realized_revenue_ledger.jsonl", False),
    ("authority_snapshot", "/var/lib/agentic/ledger-authority/authoritative_bounty_receive_ledger.json", False),
    ("authority_realized", "/var/lib/agentic/ledger-authority/authoritative_realized_revenue_ledger.jsonl", False),
    ("authority_manifest", "/var/lib/agentic/ledger-authority/authoritative_manifest.json", False),
)


failures = 0
for label, path, should_open in TARGETS:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CLOEXEC)
    except OSError as exc:
        result = errno.errorcode.get(exc.errno, str(exc.errno))
        print(f"BLOCKED {result} {label} {path}")
        if should_open:
            failures += 1
    else:
        os.close(descriptor)  # Deliberately never call write().
        print(f"OPENABLE_NO_WRITE {label} {path}")
        if not should_open:
            failures += 1

raise SystemExit(1 if failures else 0)
