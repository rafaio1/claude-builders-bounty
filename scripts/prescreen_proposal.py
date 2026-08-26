#!/usr/bin/env python3
"""Pre-screening filter for expansion proposals.

Rejects proposals that clearly violate zero-capital or TOS gates before
full council judgment, reducing ADIAR waste. Controlled by PRESCREEN_ENABLED env var.
Logs all rejections to data/expansion/prescreen_rejections.jsonl for audit.
"""
import json
import os
import re
import sys
import datetime
from pathlib import Path

ENABLED = os.environ.get("PRESCREEN_ENABLED", "1") == "1"
REJECTIONS_LOG = Path("data/expansion/prescreen_rejections.jsonl")

# Keywords indicating likely ADIAR causes (from deferral_analysis.json)
CAPITAL_KEYWORDS = [
    r"\busd\s*\d+", r"\bbrl\s*\d+", r"\$\s*\d+", r"r\$\s*\d+",
    r"\bpago\b", r"\bpaid\b", r"\bcusto\b", r"\bcost\b",
    r"\bpre[cç]o\b", r"\bprice\b", r"\bassinatura\b", r"\bsubscription\b",
    r"\bretainer\b", r"\blicen[cç]a\b", r"\blicense\b",
    r"\binvestimento\b", r"\binvestment\b", r"\bcapital\s+necess",
    r"\bfee\s+mensal", r"\bmensalidade\b", r"\bplano\s+pago\b",
]

TOS_LEGAL_KEYWORDS = [
    r"\btos\b", r"\btermos\s+de\s+servi[cç]o\b", r"\bterms\s+of\s+service\b",
    r"\bcontrato\b", r"\bcontract\b", r"\bcompliance\s+legal\b",
    r"\bregula[tç]", r"\bky[cç]\b", r"\baml\b",
    r"\bsublicens", r"\bresell(?:er|ing)\s+(?:direct|white[- ]?label)",
    r"\bproibid", r"\brestrit", r"\bn[aã]o\s+(?:permit|autoriz)",
]

def check_proposal(proposal: dict) -> tuple[bool, str | None]:
    """Return (should_reject, reason) based on keyword scan."""
    if not ENABLED:
        return False, None

    text = json.dumps(proposal, ensure_ascii=False).lower()

    capital_hits = [kw for kw in CAPITAL_KEYWORDS if re.search(kw, text)]
    tos_hits = [kw for kw in TOS_LEGAL_KEYWORDS if re.search(kw, text)]

    # Only reject if BOTH capital AND tos signals present (reduces false positives)
    # OR if capital signal is very strong (multiple matches)
    if len(capital_hits) >= 2 and tos_hits:
        return True, f"CAPITAL+TOS: capital_keywords={len(capital_hits)}, tos_keywords={len(tos_hits)}"
    if len(capital_hits) >= 3:
        return True, f"CAPITAL_STRONG: {len(capital_hits)} capital keyword matches"
    if tos_hits and any(kw in text for kw in ["sublicens", "proibid", "resell direct"]):
        return True, f"TOS_EXPLICIT: restricted terms found"

    return False, None


def log_rejection(proposal_id: str, reason: str, proposal_title: str):
    REJECTIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "proposal_id": proposal_id,
        "title": proposal_title,
        "rejection_reason": reason,
        "action": "AUTO_REJECTED_PRESCREEN",
    }
    with open(REJECTIONS_LOG, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: prescreen_proposal.py <proposal_json_file_or_stdin>")
        sys.exit(1)

    source = sys.argv[1]
    if source == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(source).read_text()

    try:
        proposal = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON: {e}", file=sys.stderr)
        sys.exit(2)

    rejected, reason = check_proposal(proposal)
    pid = proposal.get("proposal_id", "UNKNOWN")
    title = proposal.get("title", "UNTITLED")

    if rejected:
        log_rejection(pid, reason, title)
        print(f"REJECTED: {pid} — {reason}")
        sys.exit(0)
    else:
        print(f"PASSED: {pid}")
        sys.exit(0)
