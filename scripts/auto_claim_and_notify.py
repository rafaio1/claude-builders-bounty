#!/usr/bin/env python3
"""Fail-closed, idempotent autonomous GitHub bounty claim worker.

The worker consumes only the ordered ``action_queue`` produced by
``bounty_priority_queue.py``.  The historical JSONL inbox is deliberately not
read.  A GitHub comment is allowed only when both the queue item and the live
issue prove the exact ``/claim`` action contract.

Routine claims remain silent.  Telegram/email are reserved for verified wallet
receipts, verified settlements, or durable hard blocks handled by the existing
financial notification gate.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path("/Agentic")
LEDGER = ROOT / "data/aro/bounty_ledger.json"
PRIORITY_QUEUE = ROOT / "state/bounty_priority_queue.json"
STATE = ROOT / "state/auto_claim_scout_state.json"

# Kept only as an explicit audit marker.  This path must never be read by this
# worker; unqualified legacy rows do not carry an executable provider contract.
LEGACY_INBOX = ROOT / "data/aro/inbox/pending_bounties.jsonl"

MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_ACTIONS_PER_CYCLE = 100
MAX_QUEUE_AGE_SECONDS = 2 * 60 * 60
MAX_FUTURE_SKEW_SECONDS = 5 * 60

ISSUE_URL = re.compile(
    r"^https://github\.com/"
    r"([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/"
    r"([A-Za-z0-9](?:[A-Za-z0-9._-]{0,99}))/issues/([1-9][0-9]*)/?$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EXACT_CLAIM_LINE = re.compile(r"(?m)^\s*/claim\s*$")

CANONICAL_HUMAN_GATES = (
    "kyc",
    "identity",
    "social",
    "video",
    "real_funds",
    "trading",
    "manual",
)

# This worker implements one provider action: an exact GitHub issue comment.
# A provider must still supply a verified, body-hash-bound contract in the
# action item.  Merely being named here never makes a listing actionable.
ALLOWED_PROVIDER_CONTRACTS = {
    "algora": ("github", "github_issue_comment", "/claim"),
    "opire": ("github", "github_issue_comment", "/claim"),
    "rustchain": ("github", "github_issue_comment", "/claim"),
}

CLAIMED_LEDGER_STATUSES = {
    "claimed",
    "completed_pending_payout",
    "submitted",
    "in_review",
}


class ContractRejected(RuntimeError):
    """A queue item is not authorized for autonomous execution."""


def utcnow_datetime() -> datetime:
    return datetime.now(timezone.utc)


def utcnow() -> str:
    return utcnow_datetime().isoformat()


def log(message: str) -> None:
    print(f"[{utcnow()}] {message}", flush=True)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _reject_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate_json_key:{key}")
        result[key] = value
    return result


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    size = path.stat().st_size
    if size > MAX_JSON_BYTES:
        raise ValueError("json_too_large")
    return json.loads(
        path.read_text(encoding="utf-8-sig", errors="strict"),
        object_pairs_hook=_reject_duplicate_keys,
    )


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temporary = Path(temporary_name)
    try:
        os.chmod(temporary, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def parse_decimal(value: Any, *, minimum: Decimal, maximum: Decimal | None = None) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not number.is_finite() or number < minimum or (maximum is not None and number > maximum):
        return None
    return number


def run_gh(arguments: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/usr/bin/gh", *arguments],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def github_login() -> str:
    result = run_gh(["api", "user", "--jq", ".login"])
    login = result.stdout.strip()
    if result.returncode != 0 or not login:
        raise RuntimeError("github_auth_unavailable")
    return login


def issue_snapshot(repo: str, number: int) -> dict[str, Any]:
    result = run_gh(
        [
            "issue",
            "view",
            str(number),
            "--repo",
            repo,
            "--json",
            "state,title,url,body,comments",
        ]
    )
    if result.returncode != 0:
        raise RuntimeError("github_issue_read_failed")
    try:
        payload = json.loads(result.stdout, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, ValueError) as error:
        raise RuntimeError("github_issue_invalid_response") from error
    if not isinstance(payload, dict):
        raise RuntimeError("github_issue_invalid_response")
    return payload


def has_exact_claim(snapshot: Mapping[str, Any], login: str) -> bool:
    comments = snapshot.get("comments")
    if not isinstance(comments, list):
        return False
    for comment in comments:
        if not isinstance(comment, Mapping):
            continue
        author = comment.get("author")
        author_login = str(author.get("login") or "") if isinstance(author, Mapping) else ""
        body = str(comment.get("body") or "").strip()
        if author_login.casefold() == login.casefold() and body == "/claim":
            return True
    return False


def verify_live_issue_contract(
    snapshot: Mapping[str, Any],
    *,
    expected_url: str,
    expected_body_sha256: str,
) -> None:
    if str(snapshot.get("state") or "").upper() != "OPEN":
        raise ContractRejected("issue_not_open")
    if str(snapshot.get("url") or "").rstrip("/") != expected_url.rstrip("/"):
        raise ContractRejected("issue_url_mismatch")
    body = snapshot.get("body")
    if not isinstance(body, str):
        raise ContractRejected("provider_instruction_body_missing")
    if sha256_bytes(body.encode("utf-8")) != expected_body_sha256:
        raise ContractRejected("provider_instruction_hash_mismatch")
    if EXACT_CLAIM_LINE.search(body) is None:
        raise ContractRejected("provider_instruction_exact_claim_missing")


def post_and_verify_claim(repo: str, number: int, login: str, expected_url: str) -> None:
    result = run_gh(["issue", "comment", str(number), "--repo", repo, "--body", "/claim"])
    if result.returncode != 0:
        raise RuntimeError("github_claim_write_failed")
    verification = issue_snapshot(repo, number)
    if str(verification.get("url") or "").rstrip("/") != expected_url.rstrip("/"):
        raise RuntimeError("github_claim_verification_url_mismatch")
    if not has_exact_claim(verification, login):
        raise RuntimeError("github_claim_verification_failed")


def validate_queue_document(payload: Any, now: datetime) -> tuple[list[Mapping[str, Any]], str]:
    if not isinstance(payload, Mapping):
        raise ValueError("priority_queue_not_object")

    recorded_hash = payload.get("result_sha256")
    if not isinstance(recorded_hash, str) or SHA256_RE.fullmatch(recorded_hash) is None:
        raise ValueError("priority_queue_hash_missing_or_invalid")
    unhashed = dict(payload)
    unhashed.pop("result_sha256", None)
    if sha256_bytes(canonical_json_bytes(unhashed)) != recorded_hash:
        raise ValueError("priority_queue_hash_mismatch")

    generated_at = parse_timestamp(payload.get("generated_at"))
    if generated_at is None:
        raise ValueError("priority_queue_timestamp_missing_or_invalid")
    age_seconds = (now - generated_at).total_seconds()
    if age_seconds < -MAX_FUTURE_SKEW_SECONDS or age_seconds > MAX_QUEUE_AGE_SECONDS:
        raise ValueError("priority_queue_stale")

    status = str(payload.get("status") or "").strip().lower()
    rows = payload.get("action_queue")
    if not isinstance(rows, list):
        raise ValueError("priority_queue_actions_not_list")
    if len(rows) > MAX_ACTIONS_PER_CYCLE:
        raise ValueError("priority_queue_too_many_actions")
    if any(not isinstance(row, Mapping) for row in rows):
        raise ValueError("priority_queue_action_not_object")
    if status != "ok" and rows:
        raise ValueError("degraded_priority_queue_has_actions")
    return list(rows), status


def validate_action_item(item: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    stable_id = str(item.get("stable_id") or "").strip()
    if not stable_id or len(stable_id) > 300:
        raise ContractRejected("stable_id_missing_or_invalid")

    match = ISSUE_URL.fullmatch(str(item.get("url") or "").strip())
    if match is None:
        raise ContractRejected("github_issue_url_missing_or_invalid")
    owner, name, raw_number = match.groups()
    if ".." in name or name.endswith("."):
        raise ContractRejected("github_repo_name_invalid")
    repo, number = f"{owner}/{name}", int(raw_number)
    expected_url = str(item["url"]).rstrip("/")

    provider = str(item.get("provider") or "").strip().lower()
    platform = str(item.get("platform") or "").strip().lower()
    source = str(item.get("source") or "").strip().lower()
    expected_contract = ALLOWED_PROVIDER_CONTRACTS.get(provider)
    if expected_contract is None or expected_contract[0] != platform or source != provider:
        raise ContractRejected("provider_or_platform_not_allowlisted")

    if item.get("action") != "claim" or item.get("claim_command") != "/claim":
        raise ContractRejected("exact_claim_action_missing")
    for key in ("explicit_execution_contract", "listing_verified", "provider_verified", "source_fresh"):
        if item.get(key) is not True:
            raise ContractRejected(f"{key}_not_true")

    gates = item.get("human_gates")
    if item.get("human_gates_complete") is not True or not isinstance(gates, Mapping):
        raise ContractRejected("human_gates_incomplete")
    for gate in CANONICAL_HUMAN_GATES:
        if gates.get(gate) is not False:
            raise ContractRejected(f"human_gate_{gate}_not_false")
    if any(value is not False for value in gates.values()):
        raise ContractRejected("human_gate_extra_not_false")

    asset = str(item.get("asset") or "").strip()
    network = str(item.get("network") or "").strip()
    route_id = str(item.get("route_id") or "").strip()
    if not asset or not network or not route_id or item.get("asset_network_exact") is not True:
        raise ContractRejected("exact_asset_network_route_missing")
    if item.get("route_status") != "complete_verified" or item.get("self_custody_rail_verified") is not True:
        raise ContractRejected("route_or_self_custody_not_verified")

    deadline = parse_timestamp(item.get("deadline"))
    if deadline is None or deadline <= now:
        raise ContractRejected("deadline_missing_or_expired")

    positive_metrics = (
        "gross_verified",
        "expected_wise_net_verified",
        "net_if_paid_verified",
    )
    for key in positive_metrics:
        if parse_decimal(item.get(key), minimum=Decimal("0.000000000001")) is None:
            raise ContractRejected(f"{key}_missing_or_invalid")
    confidence = parse_decimal(
        item.get("payment_confidence_lcb_ppm"),
        minimum=Decimal(1),
        maximum=Decimal(1_000_000),
    )
    if confidence is None or confidence != confidence.to_integral_value():
        raise ContractRejected("payment_confidence_lcb_missing_or_invalid")
    time_p90 = parse_decimal(item.get("time_to_wise_p90_seconds"), minimum=Decimal(0))
    if time_p90 is None or time_p90 != time_p90.to_integral_value():
        raise ContractRejected("time_to_wise_p90_missing_or_invalid")

    contract = item.get("action_contract")
    if not isinstance(contract, Mapping):
        raise ContractRejected("action_contract_missing")
    contract_values = (
        str(contract.get("platform") or "").strip().lower(),
        str(contract.get("kind") or "").strip().lower(),
        contract.get("claim_command"),
    )
    if contract_values != expected_contract:
        raise ContractRejected("action_contract_not_allowlisted")
    if str(contract.get("provider") or "").strip().lower() != provider:
        raise ContractRejected("action_contract_provider_mismatch")
    if str(contract.get("target_url") or "").rstrip("/") != expected_url:
        raise ContractRejected("action_contract_target_mismatch")
    if contract.get("verified") is not True or contract.get("autonomous") is not True:
        raise ContractRejected("action_contract_not_verified_autonomous")
    instruction_hash = str(contract.get("provider_instruction_sha256") or "").strip().lower()
    if SHA256_RE.fullmatch(instruction_hash) is None:
        raise ContractRejected("provider_instruction_hash_missing_or_invalid")

    return {
        "stable_id": stable_id,
        "repo": repo,
        "issue": number,
        "key": f"{repo}#{number}",
        "url": expected_url,
        "provider": provider,
        "platform": platform,
        "instruction_sha256": instruction_hash,
        "contract_sha256": sha256_bytes(canonical_json_bytes(contract)),
        "gross_verified": item.get("gross_verified"),
        "asset": asset,
        "network": network,
        "route_id": route_id,
    }


def _target_record(targets: dict[str, Any], item: Mapping[str, Any], index: int) -> dict[str, Any]:
    stable_id = str(item.get("stable_id") or f"invalid-action-index-{index}")[:300]
    record = targets.setdefault(stable_id, {"attempts": 0})
    if not isinstance(record, dict):
        record = {"attempts": 0}
        targets[stable_id] = record
    return record


def main() -> int:
    log("Starting autonomous priority claim cycle")
    cycle_now = utcnow_datetime()
    try:
        queue_payload = load_json(PRIORITY_QUEUE, None)
        action_rows, queue_status = validate_queue_document(queue_payload, cycle_now)
        ledger = load_json(LEDGER, {"entries": []})
        state = load_json(STATE, {"schema_version": 2, "targets": {}})
    except Exception as exc:
        log(f"OPERATIONAL_FAILURE type={type(exc).__name__} reason={str(exc)[:160]}")
        return 3

    if not isinstance(ledger, dict) or not isinstance(ledger.get("entries"), list):
        log("OPERATIONAL_FAILURE reason=ledger_entries_invalid")
        return 3
    if not isinstance(state, dict):
        log("OPERATIONAL_FAILURE reason=state_invalid")
        return 3
    entries: list[Any] = ledger["entries"]
    targets = state.setdefault("targets", {})
    if not isinstance(targets, dict):
        log("OPERATIONAL_FAILURE reason=state_targets_invalid")
        return 3

    claimed_keys = {
        f"{row.get('repo')}#{row.get('issue')}"
        for row in entries
        if isinstance(row, Mapping) and row.get("status") in CLAIMED_LEDGER_STATUSES
    }

    eligible: list[dict[str, Any]] = []
    rejected = 0
    for index, item in enumerate(action_rows):
        record = _target_record(targets, item, index)
        record["last_evaluated_at"] = utcnow()
        try:
            candidate = validate_action_item(item, cycle_now)
        except ContractRejected as exc:
            rejected += 1
            record.update({"status": "contract_rejected", "last_error": str(exc)})
            log(f"CONTRACT_REJECTED stable_id={str(item.get('stable_id') or index)[:120]} reason={exc}")
            continue
        if candidate["key"] in claimed_keys:
            record.update({"status": "already_in_ledger", "last_error": None})
            continue
        eligible.append(candidate)

    login: str | None = None
    failures = 0
    claimed = 0
    ledger_changed = False
    if eligible:
        try:
            login = github_login()
        except Exception as exc:
            log(f"OPERATIONAL_FAILURE type={type(exc).__name__} reason=github_auth_unavailable")
            return 2

    # Preserve the upstream order.  No local sorting may promote a lower-value
    # action over the priority queue's first eligible item.
    for candidate in eligible:
        record = targets[candidate["stable_id"]]
        record["last_attempt_at"] = utcnow()
        record["attempts"] = int(record.get("attempts") or 0) + 1
        try:
            snapshot = issue_snapshot(candidate["repo"], candidate["issue"])
            verify_live_issue_contract(
                snapshot,
                expected_url=candidate["url"],
                expected_body_sha256=candidate["instruction_sha256"],
            )
            already_claimed = has_exact_claim(snapshot, login or "")
            if not already_claimed:
                post_and_verify_claim(
                    candidate["repo"],
                    candidate["issue"],
                    login or "",
                    candidate["url"],
                )
            claimed_at = utcnow()
            entries.append(
                {
                    "repo": candidate["repo"],
                    "issue": candidate["issue"],
                    "url": candidate["url"],
                    "status": "claimed",
                    "claimed_at": claimed_at,
                    "claim_actor": login,
                    "claim_command": "/claim",
                    "claim_verified": True,
                    "provider": candidate["provider"],
                    "platform": candidate["platform"],
                    "priority_stable_id": candidate["stable_id"],
                    "action_contract_sha256": candidate["contract_sha256"],
                    "provider_instruction_sha256": candidate["instruction_sha256"],
                    "gross_verified_unrealized": candidate["gross_verified"],
                    "asset": candidate["asset"],
                    "network": candidate["network"],
                    "route_id": candidate["route_id"],
                    "note": "Autonomous exact /claim verified on the provider issue; reward remains unrealized.",
                }
            )
            claimed_keys.add(candidate["key"])
            record.update({"status": "claimed", "claimed_at": claimed_at, "last_error": None})
            ledger_changed = True
            claimed += 1
            log(f"CLAIMED key={candidate['key']} existing={str(already_claimed).lower()}")
        except ContractRejected as exc:
            rejected += 1
            record.update({"status": "live_contract_rejected", "last_error": str(exc)})
            log(f"HARD_BLOCK key={candidate['key']} reason={exc}")
        except Exception as exc:
            failures += 1
            record.update(
                {
                    "status": "retrying",
                    "last_error": str(exc)[:500],
                    "last_error_type": type(exc).__name__,
                }
            )
            log(f"RETRY key={candidate['key']} attempt={record['attempts']} type={type(exc).__name__}")
        time.sleep(2)

    state.update(
        {
            "schema_version": 2,
            "updated_at": utcnow(),
            "queue_status": queue_status,
            "queue_result_sha256": queue_payload.get("result_sha256") if isinstance(queue_payload, Mapping) else None,
            "github_actor": login or state.get("github_actor"),
            "eligible_this_cycle": len(eligible),
            "claimed_this_cycle": claimed,
            "contract_rejected_this_cycle": rejected,
            "operational_failures_this_cycle": failures,
            "legacy_inbox_ignored": True,
            "routine_notifications_emitted": 0,
        }
    )
    atomic_json(STATE, state)
    if ledger_changed:
        ledger["updated_at"] = utcnow()
        atomic_json(LEDGER, ledger)
    log(f"Cycle complete eligible={len(eligible)} claimed={claimed} rejected={rejected} failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
