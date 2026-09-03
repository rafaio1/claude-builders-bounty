#!/usr/bin/env python3
"""Safe GitHub-only TRASH backfill for Gmail (v2 - corrected).

Rules enforced per owner directive:
- Eligibility: rule_version == "gmail-inbox-v1", status == "classified_untrusted_input",
  content_fingerprint present, sender_domain == github.com or *.github.com,
  AND (dkim_pass OR dmarc_pass). NO exclusion for financial/security/bounty signals;
  those are preserved in ledger/decisions already. ALL authenticated GitHub goes to TRASH.
- Two-phase receipt: write intent BEFORE mutation, write applied ONLY after HTTP success.
  On resume, only applied prevents re-mutation; intent-only is retried.
- Mutation: batchModify removeLabelIds=["INBOX","UNREAD"], addLabelIds=["TRASH"]. Never DELETE.
- Idempotent on applied receipts. Batch-limited and resumable.
- Never touches non-GitHub senders.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path("/Agentic")
DECISIONS_PATH = ROOT / "data" / "aro" / "inbox" / "gmail_decisions.jsonl"
RECEIPTS_PATH = ROOT / "data" / "aro" / "inbox" / "gmail_trash_receipts_v2.jsonl"
STATE_PATH = ROOT / "state" / "gmail_trash_backfill_v2_state.json"
LOCK_PATH = Path("/run/agentic-gmail-trash-backfill-v2/lock")
SCHEMA_VERSION = 2
BATCH_SIZE = 50
MAX_NETWORK_PER_RUN = 500
REQUIRED_RULE_VERSION = "gmail-inbox-v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    if not records:
        return
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    with open(path, "a", encoding="utf-8") as handle:
        os.chmod(path, 0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def load_receipts_by_phase() -> tuple[set[str], set[str]]:
    """Return (intent_ids, applied_ids) from v2 receipts."""
    intent_ids: set[str] = set()
    applied_ids: set[str] = set()
    if not RECEIPTS_PATH.exists():
        return intent_ids, applied_ids
    with open(RECEIPTS_PATH, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            mid = obj.get("message_id")
            phase = obj.get("phase")
            if not mid:
                continue
            mid_str = str(mid)
            if phase == "intent":
                intent_ids.add(mid_str)
            elif phase == "applied":
                applied_ids.add(mid_str)
    return intent_ids, applied_ids


def is_eligible(decision: dict[str, Any]) -> bool:
    # Rule version gate
    if decision.get("rule_version") != REQUIRED_RULE_VERSION:
        return False
    # Status gate
    if decision.get("status") != "classified_untrusted_input":
        return False
    # Content fingerprint required
    if not decision.get("content_fingerprint"):
        return False
    # Sender domain gate
    domain = str(decision.get("sender_domain", "")).lower()
    if domain != "github.com" and not domain.endswith(".github.com"):
        return False
    # Authentication gate
    auth = decision.get("authentication", {}) or {}
    if not (auth.get("dkim_pass") or auth.get("dmarc_pass")):
        return False
    return True


def eligible_message_ids(max_candidates: int = 10000) -> list[str]:
    eligible: list[str] = []
    if not DECISIONS_PATH.exists():
        return eligible
    with open(DECISIONS_PATH, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                decision = json.loads(line)
            except Exception:
                continue
            if not is_eligible(decision):
                continue
            mid = decision.get("message_id")
            if mid:
                eligible.append(str(mid))
            if len(eligible) >= max_candidates:
                break
    return sorted(set(eligible))


def atomic_state_write(payload: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".trash_v2_state.", dir=STATE_PATH.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as h:
            json.dump(payload, h, ensure_ascii=False, indent=2, sort_keys=True)
            h.write("\n")
            h.flush()
            os.fsync(h.fileno())
        os.replace(tmp, STATE_PATH)
        os.chmod(STATE_PATH, 0o600)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def get_gmail_client():
    sys.path.insert(0, str(ROOT / "scripts"))
    from agentic_gmail_inbox_ingestor import GmailAPIClient  # type: ignore
    return GmailAPIClient()


def fetch_labels(client) -> dict[str, str]:
    resp = client._api("GET", "labels")
    mapping: dict[str, str] = {}
    for label in resp.get("labels", []):
        mapping[label["name"]] = label["id"]
    return mapping


def trash_batch(client, label_id_trash: str, message_ids: list[str]) -> tuple[int, list[str]]:
    if not message_ids:
        return 0, []
    errors: list[str] = []
    try:
        client._api(
            "POST",
            "messages/batchModify",
            json={
                "ids": message_ids,
                "removeLabelIds": ["INBOX", "UNREAD"],
                "addLabelIds": [label_id_trash],
            },
        )
        return len(message_ids), errors
    except Exception as exc:
        errors.append(f"batchModify failed: {exc}")
        return 0, errors


def run(max_batches: int = 10, dry_run: bool = False) -> dict[str, Any]:
    LOCK_PATH.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    lock_fd = open(LOCK_PATH, "w", encoding="utf-8")
    try:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return {"status": "skipped", "reason": "lock_held"}

    start = utc_now()
    intent_ids, applied_ids = load_receipts_by_phase()
    candidates = eligible_message_ids()
    # Only messages that have NOT been applied are pending.
    # Intent-only messages ARE retried (they may have crashed before applied).
    pending = [mid for mid in candidates if mid not in applied_ids]

    state_before = {
        "schema_version": SCHEMA_VERSION,
        "started_at": start,
        "candidates_total": len(candidates),
        "already_applied": len(applied_ids),
        "intent_only_retryable": len(intent_ids - applied_ids),
        "pending_before": len(pending),
        "dry_run": dry_run,
    }

    if dry_run:
        state_before["status"] = "dry_run_complete"
        state_before["completed_at"] = utc_now()
        atomic_state_write(state_before)
        return state_before

    client = get_gmail_client()
    labels = fetch_labels(client)
    trash_label = labels.get("TRASH")
    if not trash_label:
        state_before["status"] = "error"
        state_before["error"] = "TRASH label not found"
        state_before["completed_at"] = utc_now()
        atomic_state_write(state_before)
        return state_before

    processed = 0
    trashed = 0
    error_count = 0
    all_errors: list[str] = []
    batches_done = 0

    for i in range(0, min(len(pending), max_batches * BATCH_SIZE), BATCH_SIZE):
        batch = pending[i : i + BATCH_SIZE]
        # Phase 1: write intent for this batch
        intent_records = []
        for mid in batch:
            intent_records.append({
                "schema_version": SCHEMA_VERSION,
                "message_id": mid,
                "phase": "intent",
                "action": "trash",
                "provider": "github",
                "authenticated": True,
                "receipt_at": utc_now(),
                "rule_version": "github_trash_v2",
            })
        append_jsonl(RECEIPTS_PATH, intent_records)

        # Phase 2: mutate
        count, errs = trash_batch(client, trash_label, batch)

        # Phase 3: write applied ONLY for successful mutations
        if count > 0:
            applied_records = []
            for mid in batch:
                applied_records.append({
                    "schema_version": SCHEMA_VERSION,
                    "message_id": mid,
                    "phase": "applied",
                    "action": "trash",
                    "provider": "github",
                    "authenticated": True,
                    "receipt_at": utc_now(),
                    "rule_version": "github_trash_v2",
                })
            append_jsonl(RECEIPTS_PATH, applied_records)

        trashed += count
        error_count += len(errs)
        all_errors.extend(errs)
        processed += len(batch)
        batches_done += 1
        if processed >= MAX_NETWORK_PER_RUN:
            break

    final_state = {
        **state_before,
        "processed": processed,
        "trashed": trashed,
        "errors": error_count,
        "error_samples": all_errors[:10],
        "batches_done": batches_done,
        "status": "ok" if error_count == 0 else "partial",
        "completed_at": utc_now(),
    }
    atomic_state_write(final_state)
    return final_state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-batches", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = run(max_batches=args.max_batches, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") in {"ok", "dry_run_complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
