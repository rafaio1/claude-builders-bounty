#!/usr/bin/env python3
"""
Supersession Detector V1
Detects when a newer proposal supersedes an older one via cross-reference
of proposal_id in body text + temporal ordering.

Usage:
    python3 scripts/detect_supersession.py [proposals.jsonl] [output.json]

Defaults:
    input:  data/expansion/proposals.jsonl
    output: data/expansion/supersession_scan.json
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = REPO_ROOT / "data" / "expansion" / "proposals.jsonl"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "expansion" / "supersession_scan.json"

SUPERSESSION_KEYWORDS = [
    "supersede", "supersedes", "superseded", "supersession",
    "replaces", "replace", "replaced", "replacement",
    "obsoletes", "obsolete", "deprecates", "deprecated",
    "substitui", "substituir", "substituido", "substituição",
    "revoga", "revogar", "revogado",
    "foi adiada", "adiada por", "proposta anterior",
    "complementa", "já está configurado e validado",
    "sem timers", "pipeline não roda",
]


def load_proposals(path: str) -> list[dict]:
    proposals = []
    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                proposals.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"WARN: skipping malformed JSON at line {line_num}: {e}", file=sys.stderr)
    return proposals


def extract_timestamp(proposal: dict) -> datetime | None:
    """Extract timestamp from proposal_id (exp-YYYYMMDD-*) or metadata."""
    pid = proposal.get("proposal_id", "") or proposal.get("id", "")
    m = re.match(r"exp-(\d{8})", pid)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%d")
        except ValueError:
            pass
    for key in ("timestamp", "created_at", "date"):
        val = proposal.get(key)
        if val:
            try:
                return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass
    return None


def has_supersession_signal(text: str) -> bool:
    lower = text.lower()
    # Primary: explicit supersession keywords
    if any(kw in lower for kw in SUPERSESSION_KEYWORDS):
        return True
    # Secondary: structural patterns indicating continuation/replacement
    # These catch cases where proposal B references A as predecessor without using "supersede"
    structural_patterns = [
        "proposta anterior",
        "foi adiada",
        "adiada por falta",
        "complementa exp-",
        "já está configurado e validado",
        "conforme veredito exp-",
    ]
    return any(pat in lower for pat in structural_patterns)


def find_cross_references(text: str, known_ids: set[str]) -> set[str]:
    """Find proposal_ids mentioned in text body."""
    found = set()
    for pid in known_ids:
        if pid and pid in text:
            found.add(pid)
    return found


def detect_supersessions(proposals: list[dict]) -> list[dict]:
    known_ids = {p.get("proposal_id") or p.get("id") for p in proposals}
    known_ids.discard(None)
    known_ids.discard("")

    # Build index for O(1) lookup
    proposal_index = {}
    for p in proposals:
        pid = p.get("proposal_id") or p.get("id")
        if pid:
            proposal_index[pid] = p

    results = []
    seen_pairs = set()

    for prop in proposals:
        pid = prop.get("proposal_id") or prop.get("id")
        if not pid:
            continue

        ts = extract_timestamp(prop)
        body = json.dumps(prop, ensure_ascii=False)

        # STRICT MODE: Only count as supersession if BOTH cross-reference AND keyword exist.
        # Pure substring matches (e.g. METHOD_17 in METHOD_173) are false positives.
        if not has_supersession_signal(body):
            continue

        refs = find_cross_references(body, known_ids)
        refs.discard(pid)

        if not refs:
            continue

        for ref_id in refs:
            ref_prop = proposal_index.get(ref_id)
            ref_ts = extract_timestamp(ref_prop) if ref_prop else None

            # Determine direction: newer supersedes older
            if ts and ref_ts:
                if ts >= ref_ts:
                    older, newer = ref_id, pid
                else:
                    older, newer = pid, ref_id
            else:
                # Without timestamps, assume the referencing one is newer
                older, newer = ref_id, pid

            pair_key = (older, newer)
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            context = "cross_reference_with_supersession_keyword"
            results.append({
                "older": older,
                "newer": newer,
                "context": context,
            })

    # Sort by older id for deterministic output
    results.sort(key=lambda x: (x["older"], x["newer"]))
    return results


def main():
    input_path = sys.argv[1] if len(sys.argv) > 1 else str(DEFAULT_INPUT)
    output_path = sys.argv[2] if len(sys.argv) > 2 else str(DEFAULT_OUTPUT)

    if not Path(input_path).exists():
        print(f"ERROR: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    proposals = load_proposals(input_path)
    print(f"Loaded {len(proposals)} proposals from {input_path}")

    supersessions = detect_supersessions(proposals)
    print(f"Detected {len(supersessions)} supersession pairs")

    output = {
        "generated_at": datetime.utcnow().isoformat() + "+00:00",
        "method": "Cross-reference proposal_id in body text + supersession keywords + temporal ordering",
        "total_proposals_scanned": len(proposals),
        "superseded": supersessions,
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"Results written to {output_path}")


if __name__ == "__main__":
    main()
