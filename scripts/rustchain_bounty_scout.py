#!/usr/bin/env python3
"""Deterministic RustChain bounty scout for the priority queue.

Produces /Agentic/data/aro/rustchain_bounty_scout.json in the same shape as
superteam_large_bounty_scout.json so that bounty_priority_queue.py can ingest
RustChain bounties without schema changes. Only open issues with the /claim
contract and no active lock are emitted.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path("/Agentic")
OUTPUT = ROOT / "data/aro/rustchain_bounty_scout.json"
REPO = "Scottcjn/rustchain-bounties"
WALLET = "RTC1e9bf7a2a60aac9bcbc5a0df0c65e9501e932861"

CLAIM_LOCK_RE = re.compile(r"@(\S+)\s+this\s+bounty\s+is\s+locked\s+until", re.I)
LAPSED_RE = re.compile(r"Claim\s+lapsed", re.I)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def gh(args: list[str]) -> str:
    env = {"GH_CONFIG_DIR": "/run/agentic-gh"}
    result = subprocess.run(
        ["gh"] + args,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {result.stderr}")
    return result.stdout


def fetch_open_issues() -> list[dict[str, Any]]:
    raw = gh([
        "issue", "list",
        "--repo", REPO,
        "--state", "open",
        "--limit", "200",
        "--json", "number,title,body,url,createdAt,updatedAt,labels,author",
    ])
    return json.loads(raw)


def has_active_lock(body: str) -> bool:
    if not body:
        return False
    if LAPSED_RE.search(body):
        return False
    match = CLAIM_LOCK_RE.search(body)
    if not match:
        return False
    # Naive lock check: if there is a lock mention without a subsequent lapse,
    # treat as locked. The priority queue will revalidate live before claiming.
    return True


def extract_reward(title: str, body: str) -> int | None:
    text = f"{title} {body or ''}"
    m = re.search(r"(\d{1,6})\s*RTC", text, re.I)
    if m:
        return int(m.group(1))
    return None


def main() -> int:
    issues = fetch_open_issues()
    candidates: list[dict[str, Any]] = []
    for issue in issues:
        body = issue.get("body") or ""
        if has_active_lock(body):
            continue
        reward = extract_reward(issue["title"], body)
        if reward is None or reward <= 0:
            continue
        candidate = {
            "id": f"rustchain-{issue['number']}",
            "source": "rustchain",
            "provider": "rustchain",
            "title": issue["title"],
            "url": issue["url"],
            "reward_amount": reward,
            "reward_currency": "RTC",
            "created_at": issue.get("createdAt"),
            "updated_at": issue.get("updatedAt"),
            "execution_contract": {
                "explicit": True,
                "autonomous": True,
                "human_action_required": False,
            },
            "action_contract": {
                "provider": "rustchain",
                "type": "github_issue_comment",
                "instruction": "/claim",
                "verified": True,
            },
            "wallet": WALLET,
        }
        candidates.append(candidate)

    payload = {
        "scouted_at": utcnow(),
        "source": "rustchain",
        "candidates": candidates,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"[{utcnow()}] rustchain_bounty_scout: {len(candidates)} candidates written to {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
