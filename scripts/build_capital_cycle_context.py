#!/usr/bin/env python3
"""Build the small, deterministic input snapshot used by capital AI cycles."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


SCHEMA_VERSION = 1
DEFAULT_ROOT = Path("/Agentic")
DEFAULT_OUTPUT = Path("/var/lib/agentic/capital_cycle_context.json")
MAX_CONTEXT_BYTES = 32768
GITHUB_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SIGNAL_ID_RE = re.compile(r"^[0-9a-f]{32}$")
TARGET_RE = re.compile(r"\((Issue|PR)\s+#(\d+)\)", re.IGNORECASE)
EMAIL_CANDIDATE_STATES = {
    "payout_confirmation_candidate",
    "award_or_winner_candidate",
    "acceptance_candidate",
}
BOUNTY_PROVIDERS = {
    "algora",
    "gitcoin",
    "immunefi",
    "issuehunt",
    "polar",
    "superteam",
    "rustchain",
}
BOUNTY_TERMS = {"bounty", "bounties", "reward", "rewards"}
FORBIDDEN_OUTPUT_KEYS = {
    "body",
    "snippet",
    "raw",
    "headers",
    "authorization",
    "api_key",
    "access_token",
    "auth_token",
    "password",
    "secret",
}

SERVICE_UNITS = (
    "apifable.service",
    "telegram-bridge.service",
    "capital-orchestrator-v4.service",
    "agentic-goal-watchdog.service",
)
TIMER_UNITS = (
    "hourly-capital-auditor.timer",
    "agentic-claude-advisor.timer",
    "auto-claim-scout.timer",
    "bughunter-autonomous-submit.timer",
    "agentic-email-outbox-dispatcher.timer",
    "agentic-ledger-proposal-gate.timer",
    "agentic-rustchain-reconciler.timer",
    "agentic-wallet-rail-audit.timer",
    "agentic-wallet-recovery-notifier.timer",
    "agentic-payout-route-planner.timer",
    "agentic-superteam-usdc-scout.timer",
    "agentic-superteam-large-bounty-scout.timer",
    "agentic-bounty-priority-queue.timer",
    "rtc-bridge-request-watcher.timer",
    "ledger-integrity-guard.timer",
    "agentic-gmail-inbox-ingestor.timer",
    "agentic-gmail-safe-consumer.timer",
    "telegram-command-dispatcher.timer",
    "telegram-general-executor.timer",
)
OPTIONAL_TIMER_UNITS = {"telegram-general-executor.timer"}

PAYOUT_ROUTE_STATE = Path("state/payout_route_map.json")
RTC_BRIDGE_REQUEST_STATE = Path("/var/lib/agentic/rtc-bridge-request/state.json")
RTC_BRIDGE_REQUEST_TEST_STATE = Path("state/rtc_bridge_request_watcher.json")
RTC_BRIDGE_TARGET_KEY = "scottcjn/rustchain#8316"
RTC_BRIDGE_REPO = "Scottcjn/Rustchain"
RTC_BRIDGE_ISSUE_NUMBER = 8316
RTC_BRIDGE_ISSUE_URL = "https://github.com/Scottcjn/Rustchain/issues/8316"
SUPERTEAM_SCOUT_STATE = Path("state/superteam_usdc_scout.json")
SUPERTEAM_LARGE_SCOUT_STATE = Path("state/superteam_large_bounty_scout.json")
BOUNTY_PRIORITY_STATE = Path("state/bounty_priority_queue.json")
MAX_ROUTE_ROWS = 8
MAX_LARGE_BOUNTY_ROWS = 3
MAX_BOUNTY_PRIORITY_ROWS = 1
MAX_BOUNTY_PRIORITY_AGE_SECONDS = 30 * 60
MAX_FUTURE_STATE_SKEW_SECONDS = 5 * 60
MAX_INBOUND_STATE_AGE_SECONDS = 15 * 60
GMAIL_INGESTOR_STATE = Path("state/gmail_inbox_ingestor_state.json")
GMAIL_SAFE_CONSUMER_STATE = Path("state/gmail_safe_consumer_state.json")
GMAIL_DECISIONS = Path("data/aro/inbox/gmail_decisions.jsonl")
GMAIL_ACTION_QUEUE = Path("data/aro/inbox/gmail_action_queue.jsonl")
GMAIL_ACTION_RESULTS = Path("data/aro/inbox/gmail_action_results.jsonl")
TELEGRAM_BRIDGE_STATE = Path("state/telegram_bridge_state.json")
TELEGRAM_GENERAL_EXECUTOR_STATE = Path("state/telegram_general_executor_state.json")
TELEGRAM_DISPATCH_RECEIPTS = Path("data/aro/inbox/telegram_command_receipts.jsonl")
TELEGRAM_GENERAL_RECEIPTS = Path("data/aro/inbox/telegram_general_execution_receipts.jsonl")
SAFE_RUNTIME_STATUSES = {
    "blocked",
    "catching_up",
    "completed",
    "degraded",
    "error",
    "failed",
    "healthy",
    "idle",
    "ok",
    "partial",
    "partial_archive_limit",
    "partial_error",
    "partial_search_limit",
    "running",
    "success",
    "unavailable",
    "blocked_orphan_queue",
}
ALLOWED_PUBLIC_STATE_HOSTS = {
    "api.dexscreener.com",
    "bottube.ai",
    "bybit-exchange.github.io",
    "github.com",
    "jup.ag",
    "rustchain.org",
    "superteam.fun",
    "wise.com",
    "www.bybit.com",
}


class ContextError(RuntimeError):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")


def material_state_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return only state whose change can justify another agentic action.

    Collection timestamps, health/PIDs and raw source cursors deliberately stay
    out: they change during healthy polling without changing financial work.
    """
    rustchain = dict(payload["rustchain"])
    rustchain.pop("observed_at", None)
    payout_routes = dict(payload["payout_routes"])
    payout_routes["routes"] = []
    for raw_route in payload["payout_routes"].get("routes") or []:
        route = dict(raw_route)
        if isinstance(route.get("market_quote"), dict):
            market_quote = dict(route["market_quote"])
            market_quote.pop("observed_at", None)
            route["market_quote"] = market_quote
        if isinstance(route.get("bridge_request"), dict):
            bridge_request = dict(route["bridge_request"])
            bridge_request.pop("last_attempt_at", None)
            bridge_request.pop("last_success_at", None)
            bridge_request.pop("last_error_at", None)
            bridge_request.pop("emitted_this_cycle", None)
            route["bridge_request"] = bridge_request
        payout_routes["routes"].append(route)
    bounty_priority = dict(payload["bounty_priority_queue"])
    bounty_priority.pop("observed_at", None)
    bounty_priority.pop("age_seconds", None)
    return {
        "schema_version": payload["schema_version"],
        "trust_boundary": payload["trust_boundary"],
        "routing": payload["routing"],
        "ledger": payload["ledger"],
        "proposal_guard": payload["proposal_guard"],
        "realized_revenue": payload["realized_revenue"],
        "payout_routes": payout_routes,
        "bounty_priority_queue": bounty_priority,
        "large_bounty_candidates": payload["large_bounty_candidates"],
        "email_collection_candidates": {
            "count": payload["email_collection_candidates"]["count"],
            "items": payload["email_collection_candidates"]["items"],
        },
        "rustchain": rustchain,
        "telegram_unprocessed": {
            "count": payload["telegram_unprocessed"]["count"],
        },
        "inbound_automation": payload["inbound_automation"],
    }


def load_json(path: Path) -> tuple[Any, bytes]:
    try:
        raw = path.read_bytes()
        return json.loads(raw), raw
    except Exception as exc:
        raise ContextError(f"invalid required JSON {path}: {type(exc).__name__}") from exc


def load_jsonl(path: Path) -> tuple[list[dict[str, Any]], bytes]:
    try:
        raw = path.read_bytes()
    except Exception as exc:
        raise ContextError(f"unreadable required JSONL {path}: {type(exc).__name__}") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception as exc:
            raise ContextError(f"invalid JSONL {path}:{line_number}: {type(exc).__name__}") from exc
        if not isinstance(row, dict):
            raise ContextError(f"non-object JSONL row {path}:{line_number}")
        rows.append(row)
    return rows, raw


def compact_amount(entry: dict[str, Any]) -> float | int | None:
    for key in ("provider_confirmed_amount", "amount_received", "expected_amount"):
        value = entry.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
    return None


def public_urls(value: Any) -> list[str]:
    found: set[str] = set()
    ordered: list[str] = []

    def add(item: Any) -> None:
        if not isinstance(item, str) or not item.startswith("https://"):
            return
        if not (item.startswith("https://github.com/") or item.startswith("https://rustchain.org/")):
            return
        if item not in found:
            found.add(item)
            ordered.append(item)

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
        elif isinstance(item, str):
            add(item)

    if isinstance(value, dict):
        add(value.get("provider_payout_url"))
        provider_evidence = [row for row in value.get("provider_evidence") or [] if isinstance(row, dict)]
        provider_evidence.sort(
            key=lambda row: (
                0 if "confirmation" in str(row.get("evidence_type") or "") else 1,
                str(row.get("source_url") or ""),
            )
        )
        for row in provider_evidence:
            add(row.get("source_url"))
        visit(value.get("blockers"))
        visit(provider_evidence)
    else:
        visit(value)
    return ordered[:3]


def blocker_types(entry: dict[str, Any]) -> list[str]:
    result = {
        str(row.get("type"))
        for row in entry.get("blockers") or []
        if isinstance(row, dict) and row.get("type")
    }
    return sorted(result)[:8]


def compact_ledger_line(entry: dict[str, Any]) -> dict[str, Any]:
    txids = sorted(
        {
            str(value)
            for value in entry.get("txids") or []
            if isinstance(value, str) and value.strip()
        }
    )[:8]
    return {
        "id": str(entry.get("ledger_id") or ""),
        "key": str(entry.get("bounty_key") or ""),
        "status": str(entry.get("status") or "unknown"),
        "repo": entry.get("repo"),
        "pr": entry.get("pr_number"),
        "asset": entry.get("reward_asset") or entry.get("expected_currency"),
        "amount": compact_amount(entry),
        "network": entry.get("network"),
        "txid": entry.get("txid"),
        "txids": txids,
        "blockers": blocker_types(entry),
        "sources": public_urls(entry),
    }


def derive_email_target(row: dict[str, Any]) -> dict[str, Any]:
    repo = str(row.get("repo") or "")
    subject = str(row.get("subject") or "")
    match = TARGET_RE.search(subject)
    kind = number = url = None
    if match and GITHUB_REPO_RE.fullmatch(repo):
        kind = "issue" if match.group(1).lower() == "issue" else "pull"
        number = int(match.group(2))
        endpoint = "issues" if kind == "issue" else "pull"
        url = f"https://github.com/{repo}/{endpoint}/{number}"
    return {
        "signal_id": str(row.get("signal_id") or ""),
        "message_timestamp": row.get("message_timestamp"),
        "provider": row.get("provider"),
        "repo": repo or None,
        "strict_state": row.get("strict_state"),
        "verified": False,
        "evidence_terms": sorted({str(term) for term in row.get("evidence_terms") or []})[:8],
        "target_type": kind,
        "target_number": number,
        "target_url": url,
    }


def persisted_email_candidate_contract(row: dict[str, Any]) -> bool:
    terms = {str(term).lower() for term in row.get("evidence_terms") or []}
    state = str(row.get("strict_state") or "")
    provider = str(row.get("provider") or "").lower()
    if state == "acceptance_candidate" and row.get("non_financial_disclaimer") is True:
        return False
    valid_envelope = (
        row.get("schema_version") == 1
        and row.get("source") == "gmail_read_only"
        and row.get("verification") == "unverified_email_signal"
        and state in EMAIL_CANDIDATE_STATES
    )
    return valid_envelope and (
        (state == "payout_confirmation_candidate" and provider in BOUNTY_PROVIDERS)
        or (bool(BOUNTY_TERMS & terms) and bool(row.get("provider") or row.get("repo")))
    )


def email_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for row in sorted(rows, key=lambda item: (str(item.get("signal_id") or ""), str(item.get("message_id") or ""))):
        computed = persisted_email_candidate_contract(row)
        if bool(row.get("collection_candidate")) != computed:
            raise ContextError(f"email candidate contract mismatch for signal {row.get('signal_id') or 'missing'}")
        if not computed:
            continue
        compact = derive_email_target(row)
        identity = compact["signal_id"]
        if not SIGNAL_ID_RE.fullmatch(identity):
            raise ContextError("email collection candidate has invalid signal_id")
        timestamp = compact.get("message_timestamp")
        try:
            datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        except Exception as exc:
            raise ContextError(f"email collection candidate {identity} has invalid timestamp") from exc
        selected.setdefault(identity, compact)
    return [selected[key] for key in sorted(selected)]


def pending_command_count(rows: list[dict[str, Any]]) -> int:
    """Count durable work without copying Telegram content or identities."""
    return sum(row.get("processed") is not True for row in rows)


def parse_systemctl_show(output: str) -> dict[str, str | int | None]:
    values: dict[str, str] = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    restarts = values.get("NRestarts")
    return {
        "load": values.get("LoadState") or "unknown",
        "active": values.get("ActiveState") or "unknown",
        "sub": values.get("SubState") or "unknown",
        "result": values.get("Result") or None,
        "pid": int(values.get("MainPID") or 0),
        "restarts": int(restarts) if restarts and restarts.isdigit() else None,
        "last_trigger": values.get("LastTriggerUSec") or None,
        "next": values.get("NextElapseUSecRealtime") or None,
    }


def systemd_health() -> dict[str, Any]:
    result: dict[str, Any] = {"services": {}, "timers": {}}
    properties = (
        "LoadState,ActiveState,SubState,Result,MainPID,NRestarts,LastTriggerUSec,NextElapseUSecRealtime"
    )
    for category, units in (("services", SERVICE_UNITS), ("timers", TIMER_UNITS)):
        for unit in units:
            completed = subprocess.run(
                ["/usr/bin/systemctl", "show", unit, f"--property={properties}"],
                text=True,
                capture_output=True,
                check=False,
                timeout=8,
            )
            if completed.returncode != 0:
                result[category][unit] = {"active": "unavailable"}
            else:
                parsed = parse_systemctl_show(completed.stdout)
                if unit in OPTIONAL_TIMER_UNITS and parsed.get("load") in {"not-found", "not-loaded"}:
                    parsed = {
                        "load": parsed.get("load"),
                        "active": "optional_unavailable",
                        "sub": "optional_unavailable",
                        "result": None,
                        "pid": 0,
                        "restarts": None,
                        "last_trigger": None,
                        "next": None,
                    }
                result[category][unit] = parsed
    return result


def compact_rustchain(sidecar: dict[str, Any]) -> dict[str, Any]:
    wallet = sidecar.get("wallet") if isinstance(sidecar.get("wallet"), dict) else {}
    return {
        "status": sidecar.get("status"),
        "observed_at": sidecar.get("observed_at"),
        "wallet": {
            "miner_id": wallet.get("miner_id"),
            "amount_rtc": wallet.get("amount_rtc"),
            "source_url": wallet.get("source_url"),
        },
        "provider_confirmed_total": sidecar.get("provider_confirmed_total"),
        "wallet_received_total": sidecar.get("wallet_received_total"),
        "settled_total": sidecar.get("settled_total"),
        "unmapped_balance_rtc": sidecar.get("balance_not_mapped_to_these_records_rtc"),
        "bybit_route": sidecar.get("bybit_route_status"),
        "wise_route": sidecar.get("wise_route_status"),
        "direct_transfer_performed": sidecar.get("direct_transfer_performed"),
        "evidence_urls": sorted(
            url for url in sidecar.get("evidence_urls") or [] if isinstance(url, str) and url.startswith("https://")
        )[:8],
    }


def finite_number(value: Any) -> float | int | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    if not math.isfinite(float(value)):
        return None
    return value


def compact_reason_codes(value: Any, *, limit: int = 12) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted(
        {
            str(item)[:96]
            for item in value
            if isinstance(item, str) and item.strip()
        }
    )[:limit]


def compact_public_state_urls(value: Any, *, limit: int = 3) -> list[str]:
    candidates: list[str] = []
    if isinstance(value, dict):
        candidates = [item for item in value.values() if isinstance(item, str)]
    elif isinstance(value, list):
        candidates = [item for item in value if isinstance(item, str)]
    elif isinstance(value, str):
        candidates = [value]

    result: list[str] = []
    for item in candidates:
        if not item.startswith("https://"):
            continue
        host = item.split("/", 3)[2].split("@")[-1].split(":", 1)[0].lower()
        if host not in ALLOWED_PUBLIC_STATE_HOSTS or item in result:
            continue
        result.append(item[:500])
    return sorted(result)[:limit]


def load_optional_object(path: Path) -> tuple[dict[str, Any] | None, bytes]:
    if not path.exists():
        return None, b""
    value, raw = load_json(path)
    if not isinstance(value, dict):
        raise ContextError(f"optional state is not an object: {path}")
    return value, raw


def nonnegative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0


def safe_runtime_status(value: Any, *, present: bool) -> str:
    if not present:
        return "unavailable"
    status = str(value or "unknown").strip().lower()
    return status if status in SAFE_RUNTIME_STATUSES else "unknown"


def parse_state_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def state_is_stale(
    state: dict[str, Any] | None,
    *,
    now: datetime,
    timestamp_fields: tuple[str, ...],
) -> bool:
    if state is None:
        return False
    observed = next(
        (
            parsed
            for field in timestamp_fields
            if (parsed := parse_state_timestamp(state.get(field))) is not None
        ),
        None,
    )
    if observed is None:
        return True
    age_seconds = math.floor((now.astimezone(timezone.utc) - observed).total_seconds())
    return age_seconds < -MAX_FUTURE_STATE_SKEW_SECONDS or age_seconds > MAX_INBOUND_STATE_AGE_SECONDS


def load_untrusted_optional_state(path: Path) -> tuple[dict[str, Any] | None, int]:
    """Load a local runtime state without letting malformed telemetry stop capital work."""
    if not path.exists():
        return None, 0
    try:
        value = json.loads(path.read_bytes())
    except Exception:
        return None, 1
    if not isinstance(value, dict):
        return None, 1
    return value, 0


def jsonl_record_stats(
    path: Path,
    *,
    key_fields: tuple[str, ...] = (),
    counted_field: str | None = None,
    counted_values: set[str] | None = None,
) -> tuple[dict[str, Any], set[tuple[str, ...]]]:
    """Count an append-only ledger while retaining no content in the output."""
    if not path.exists():
        return {
            "present": False,
            "count": 0,
            "invalid": 0,
            "missing_key": 0,
            "value_counts": {},
        }, set()
    count = 0
    invalid = 0
    missing_key = 0
    keys: set[tuple[str, ...]] = set()
    value_counts: Counter[str] = Counter()
    try:
        handle = path.open("rb")
    except OSError:
        return {
            "present": True,
            "count": 0,
            "invalid": 1,
            "missing_key": 0,
            "value_counts": {},
        }, set()
    with handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                invalid += 1
                continue
            if not isinstance(row, dict):
                invalid += 1
                continue
            count += 1
            if key_fields:
                key = tuple(str(row.get(field) or "").strip() for field in key_fields)
                if all(key):
                    keys.add(key)
                else:
                    missing_key += 1
            if counted_field and counted_values:
                value = str(row.get(counted_field) or "").strip().lower()
                if value in counted_values:
                    value_counts[value] += 1
    return {
        "present": True,
        "count": count,
        "invalid": invalid,
        "missing_key": missing_key,
        "value_counts": dict(sorted(value_counts.items())),
    }, keys


def compact_gmail_runtime(root: Path, *, now: datetime) -> dict[str, Any]:
    ingestor, ingestor_parse_errors = load_untrusted_optional_state(root / GMAIL_INGESTOR_STATE)
    consumer, consumer_parse_errors = load_untrusted_optional_state(root / GMAIL_SAFE_CONSUMER_STATE)
    decisions, _ = jsonl_record_stats(root / GMAIL_DECISIONS)
    actions, action_keys = jsonl_record_stats(
        root / GMAIL_ACTION_QUEUE,
        key_fields=("message_id", "rule_version"),
    )
    results, result_keys = jsonl_record_stats(
        root / GMAIL_ACTION_RESULTS,
        key_fields=("message_id", "rule_version"),
    )

    if action_keys or result_keys:
        record_backlog = len(action_keys - result_keys) + actions["missing_key"]
        orphan_results = len(result_keys - action_keys) + results["missing_key"]
    else:
        record_backlog = max(0, actions["count"] - results["count"])
        orphan_results = max(0, results["count"] - actions["count"])

    ingestor_backlog = nonnegative_int((ingestor or {}).get("remaining_count"))
    consumer_backlog = max(
        record_backlog,
        nonnegative_int((consumer or {}).get("remaining_count")),
    )
    ledger_errors = sum(
        nonnegative_int(stats.get("invalid"))
        for stats in (decisions, actions, results)
    ) + actions["missing_key"] + results["missing_key"]
    ingestor_errors = (
        ingestor_parse_errors
        + nonnegative_int((ingestor or {}).get("error_count"))
        + nonnegative_int((ingestor or {}).get("consecutive_failure_count"))
    )
    consumer_errors = (
        consumer_parse_errors
        + nonnegative_int((consumer or {}).get("error_count"))
        + nonnegative_int((consumer or {}).get("consecutive_failure_count"))
        + nonnegative_int((consumer or {}).get("orphan_queue_count"))
        + orphan_results
    )
    ingestor_stale = state_is_stale(
        ingestor,
        now=now,
        timestamp_fields=("completed_at", "last_success_at", "started_at"),
    )
    consumer_stale = state_is_stale(
        consumer,
        now=now,
        timestamp_fields=("completed_at", "last_success_at", "started_at"),
    ) or (consumer is None and consumer_backlog > 0)
    summary = {
        "email_is_instruction": False,
        "ingestor": {
            "present": ingestor is not None,
            "status": safe_runtime_status((ingestor or {}).get("status"), present=ingestor is not None),
            "backlog": ingestor_backlog,
            "errors": ingestor_errors,
            "stale": ingestor_stale,
            "bootstrap_complete": (ingestor or {}).get("bootstrap_complete") is True,
            "history_stale": (ingestor or {}).get("history_checkpoint_stale") is True,
        },
        "consumer": {
            "present": consumer is not None,
            "status": safe_runtime_status((consumer or {}).get("status"), present=consumer is not None),
            "backlog": consumer_backlog,
            "errors": consumer_errors,
            "stale": consumer_stale,
        },
        "records": {
            "decisions": decisions["count"],
            "actions": actions["count"],
            "results": results["count"],
            "backlog": record_backlog,
            "invalid": ledger_errors,
        },
        "backlog": ingestor_backlog + consumer_backlog,
        "errors": ingestor_errors + consumer_errors + ledger_errors,
        "stale": ingestor_stale or consumer_stale,
    }
    summary["state_id"] = sha256_bytes(canonical_bytes(summary))[:32]
    return summary


def compact_telegram_runtime(root: Path, commands: list[dict[str, Any]], *, now: datetime) -> dict[str, Any]:
    bridge, bridge_parse_errors = load_untrusted_optional_state(root / TELEGRAM_BRIDGE_STATE)
    executor, executor_parse_errors = load_untrusted_optional_state(root / TELEGRAM_GENERAL_EXECUTOR_STATE)
    dispatch_receipts, _ = jsonl_record_stats(root / TELEGRAM_DISPATCH_RECEIPTS)
    general_receipts, _ = jsonl_record_stats(
        root / TELEGRAM_GENERAL_RECEIPTS,
        counted_field="result",
        counted_values={"succeeded", "rejected"},
    )

    pending_rows = [row for row in commands if row.get("processed") is not True]
    executor_statuses = {
        "awaiting_safe_executor",
        "general_execution_response_ready",
        "delivery_ambiguous_terminal",
    }
    executor_backlog = sum(
        str(row.get("processing_status") or "") in executor_statuses
        for row in pending_rows
    )
    executor_backlog = max(
        executor_backlog,
        nonnegative_int((executor or {}).get("remaining_count")),
        nonnegative_int((executor or {}).get("backlog_count")),
        nonnegative_int((executor or {}).get("pending_count")),
    )
    delivery_unknown = sum(
        str(row.get("delivery_state") or "") in {"delivery_started", "ambiguous_terminal"}
        or str(row.get("processing_status") or "") == "delivery_ambiguous_terminal"
        for row in pending_rows
    )
    bridge_errors = (
        bridge_parse_errors
        + nonnegative_int((bridge or {}).get("consecutive_errors"))
    )
    executor_errors = (
        executor_parse_errors
        + nonnegative_int((executor or {}).get("error_count"))
        + nonnegative_int((executor or {}).get("consecutive_failure_count"))
    )
    record_errors = dispatch_receipts["invalid"] + general_receipts["invalid"]
    bridge_stale = state_is_stale(
        bridge,
        now=now,
        timestamp_fields=("last_poll_ok_at", "updated_at"),
    )
    executor_stale = state_is_stale(
        executor,
        now=now,
        timestamp_fields=("completed_at", "last_success_at", "started_at", "updated_at"),
    ) or (executor is None and executor_backlog > 0)
    rejected = nonnegative_int(general_receipts["value_counts"].get("rejected"))
    summary = {
        "pending": len(pending_rows),
        "receipts": dispatch_receipts["count"] + general_receipts["count"],
        "general_receipts": general_receipts["count"],
        "delivery_unknown": delivery_unknown,
        "rejected": rejected,
        "executor": {
            "present": executor is not None,
            "status": safe_runtime_status((executor or {}).get("status"), present=executor is not None),
            "backlog": executor_backlog,
            "errors": executor_errors,
            "stale": executor_stale,
        },
        "errors": bridge_errors + executor_errors + record_errors,
        "stale": bridge_stale or executor_stale,
    }
    summary["state_id"] = sha256_bytes(canonical_bytes(summary))[:32]
    return summary


def compact_inbound_automation(root: Path, commands: list[dict[str, Any]], *, now: datetime) -> dict[str, Any]:
    return {
        "raw_content_included": False,
        "gmail": compact_gmail_runtime(root, now=now),
        "telegram": compact_telegram_runtime(root, commands, now=now),
    }


def compact_rtc_market_quote(sidecar: dict[str, Any]) -> dict[str, Any]:
    """Whitelist the live Raydium evidence without promoting it to a route."""
    live_probes = sidecar.get("live_probes")
    if live_probes is None:
        return {
            "status": "unavailable",
            "reason_code": "rtc_market_quote_missing",
            "quote_ok": False,
            "read_only": True,
            "expiring": True,
            "post_bridge_only": True,
            "native_rtc_to_wrtc_verified": False,
            "authorizes_execution": False,
        }
    if not isinstance(live_probes, dict):
        raise ContextError("payout route live_probes is not an object")
    market = live_probes.get("wrtc_market")
    if market is None:
        return {
            "status": "unavailable",
            "reason_code": "rtc_market_quote_missing",
            "quote_ok": False,
            "read_only": True,
            "expiring": True,
            "post_bridge_only": True,
            "native_rtc_to_wrtc_verified": False,
            "authorizes_execution": False,
        }
    if not isinstance(market, dict):
        raise ContextError("payout route wRTC market probe is not an object")

    quote_ok = market.get("raydium_two_leg_quote_ok_for_14_wrtc") is True
    input_amount = finite_number(market.get("raydium_quote_input_wrtc"))
    output_sol = finite_number(market.get("raydium_wrtc_sol_output"))
    output_usdc = finite_number(market.get("raydium_estimated_usdc_output_for_14_wrtc"))
    price_impact_pct = finite_number(market.get("raydium_wrtc_sol_price_impact_pct"))
    slippage_bps = finite_number(market.get("raydium_slippage_bps"))
    required_numbers = (input_amount, output_sol, output_usdc, price_impact_pct, slippage_bps)
    if quote_ok and (
        any(value is None or float(value) < 0 for value in required_numbers)
        or float(input_amount or 0) <= 0
        or float(output_sol or 0) <= 0
        or float(output_usdc or 0) <= 0
        or str(market.get("wrapped_asset") or "") != "wRTC"
        or str(market.get("wrapped_network") or "") != "solana-mainnet"
    ):
        raise ContextError("successful RTC market quote is incomplete or inconsistent")

    return {
        "status": "live_conditional_post_bridge" if quote_ok else "unavailable",
        "observed_at": str(sidecar.get("generated_at") or "")[:64] or None,
        "venue": "Raydium_route_api_v2",
        "input_asset": str(market.get("wrapped_asset") or "")[:32] or None,
        "input_amount": input_amount,
        "intermediate_asset": "SOL",
        "intermediate_output": output_sol,
        "output_asset": "USDC",
        "estimated_output": output_usdc,
        "first_leg_price_impact_pct": price_impact_pct,
        "slippage_bps": slippage_bps,
        "quote_ok": quote_ok,
        "read_only": True,
        "expiring": True,
        "post_bridge_only": True,
        "native_rtc_to_wrtc_verified": market.get("native_rtc_to_wrtc_self_service_api_verified") is True,
        "authorizes_execution": False,
    }


def _nonnegative_int(value: Any, field: str) -> int:
    if value is None:
        return 0
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ContextError(f"RTC bridge watcher {field} is invalid")
    return value


def compact_rtc_bridge_request(sidecar: dict[str, Any] | None) -> dict[str, Any]:
    """Compact watcher state; a missing watcher is explicitly pending."""
    baseline = {
        "repo": RTC_BRIDGE_REPO,
        "issue_number": RTC_BRIDGE_ISSUE_NUMBER,
        "issue_url": RTC_BRIDGE_ISSUE_URL,
        "watcher_state_present": sidecar is not None,
        "target_state_present": False,
        "trusted_comments_seen": 0,
        "untrusted_comments_seen": 0,
        "trusted_operator_comment_seen": False,
        "operator_gate_satisfied": False,
        "execution_authorized": False,
        "funds_moved": False,
    }
    if sidecar is None:
        return {"status": "watcher_state_missing_pending", **baseline}

    targets = sidecar.get("targets")
    if not isinstance(targets, dict):
        raise ContextError("RTC bridge watcher state has invalid targets")
    target = next(
        (
            value
            for key, value in targets.items()
            if str(key).lower() == RTC_BRIDGE_TARGET_KEY
        ),
        None,
    )
    if target is None:
        return {"status": "watcher_target_missing_pending", **baseline}
    if not isinstance(target, dict):
        raise ContextError("RTC bridge watcher target is not an object")
    if str(target.get("repo") or "").lower() != RTC_BRIDGE_REPO.lower():
        raise ContextError("RTC bridge watcher target repo mismatch")
    if target.get("issue_number") != RTC_BRIDGE_ISSUE_NUMBER:
        raise ContextError("RTC bridge watcher target issue mismatch")
    if target.get("issue_url") != RTC_BRIDGE_ISSUE_URL:
        raise ContextError("RTC bridge watcher target URL mismatch")

    trusted_count = _nonnegative_int(target.get("trusted_comments_seen"), "trusted_comments_seen")
    untrusted_count = _nonnegative_int(target.get("untrusted_comments_seen"), "untrusted_comments_seen")
    emitted_count = _nonnegative_int(target.get("emitted_this_cycle"), "emitted_this_cycle")
    processed = target.get("processed_event_ids")
    if not isinstance(processed, list) or any(not isinstance(item, str) for item in processed):
        raise ContextError("RTC bridge watcher processed_event_ids is invalid")
    # The current watcher verifies author association and idempotence only. It
    # does not validate the complete bridge procedure, so it cannot satisfy the
    # operator gate by itself even if an unexpected field claims otherwise.
    operator_gate_satisfied = False
    last_error_code = str(target.get("last_error_code") or "")[:96] or None
    if last_error_code:
        status = "watcher_degraded_pending"
    elif trusted_count:
        status = "trusted_comment_seen_pending_procedure_validation"
    else:
        status = "pending_trusted_operator_response"

    return {
        "status": status,
        **baseline,
        "target_state_present": True,
        "last_attempt_at": str(target.get("last_attempt_at") or "")[:64] or None,
        "last_success_at": str(target.get("last_success_at") or "")[:64] or None,
        "last_error_at": str(target.get("last_error_at") or "")[:64] or None,
        "last_error_code": last_error_code,
        "processed_event_count": len(set(processed)),
        "trusted_comments_seen": trusted_count,
        "untrusted_comments_seen": untrusted_count,
        "emitted_this_cycle": emitted_count,
        "trusted_operator_comment_seen": trusted_count > 0,
        "operator_gate_satisfied": operator_gate_satisfied,
        "execution_authorized": False,
        "funds_moved": False,
    }


def compact_payout_routes(
    sidecar: dict[str, Any] | None,
    bridge_request: dict[str, Any],
) -> dict[str, Any]:
    if sidecar is None:
        return {
            "status": "unavailable",
            "reason_code": "payout_route_state_missing",
            "ranking_primary": "verified_expected_wise_net",
            "human_action_required": False,
            "route_pending_is_revenue": False,
            "route_pending_is_settlement": False,
            "routes": [],
            "priority_candidates": [],
        }

    raw_routes = sidecar.get("routes")
    raw_candidates = sidecar.get("priority_candidates")
    summary = sidecar.get("summary")
    policy = sidecar.get("policy")
    if not isinstance(raw_routes, list) or not isinstance(raw_candidates, list):
        raise ContextError("payout route state has invalid route/candidate shape")
    if not isinstance(summary, dict) or not isinstance(policy, dict):
        raise ContextError("payout route state has invalid summary/policy shape")
    if policy.get("human_action") != "none":
        raise ContextError("payout route state violates zero-human-action policy")

    market_quote = compact_rtc_market_quote(sidecar)
    routes: list[dict[str, Any]] = []
    complete_count = 0
    pending_count = 0
    for raw in raw_routes:
        if not isinstance(raw, dict):
            raise ContextError("payout route state contains a non-object route")
        status = str(raw.get("status") or "unknown")
        complete = raw.get("route_complete_verified") is True
        execution_enabled = raw.get("execution_enabled") is True
        if status == "route_pending":
            pending_count += 1
            if complete or execution_enabled:
                raise ContextError("route_pending cannot be complete or execution-enabled")
        if complete:
            complete_count += 1
        route = {
                "route_id": str(raw.get("route_id") or "")[:128],
                "asset": str(raw.get("asset") or "")[:32] or None,
                "network": str(raw.get("network") or "")[:64] or None,
                "status": status[:48],
                "route_complete_verified": complete,
                "execution_enabled": execution_enabled,
                "expected_wise_net_verified": finite_number(raw.get("expected_wise_net")),
                "mapped_wallet_received_amount": finite_number(raw.get("mapped_wallet_received_amount")),
                "receive_ready": raw.get("receive_ready") is True,
                "reason_codes": compact_reason_codes(raw.get("reason_codes")),
                "is_revenue": False,
                "is_settlement": False,
            }
        if route["asset"] == "RTC":
            if market_quote.get("quote_ok") is True:
                quote_input = finite_number(market_quote.get("input_amount"))
                mapped_amount = finite_number(route.get("mapped_wallet_received_amount"))
                if (
                    quote_input is None
                    or mapped_amount is None
                    or abs(float(quote_input) - float(mapped_amount)) > 0.000001
                ):
                    raise ContextError("RTC market quote input includes funds outside the mapped wallet receipts")
            route["market_quote"] = market_quote
            route["bridge_request"] = bridge_request
        routes.append(route)

    expected_count = sum(
        finite_number(raw.get("expected_wise_net")) is not None
        for raw in raw_candidates
        if isinstance(raw, dict)
    )
    try:
        if int(summary.get("route_count")) != len(raw_routes):
            raise ContextError("payout route count disagrees with routes")
        if int(summary.get("complete_verified")) != complete_count:
            raise ContextError("payout complete count disagrees with routes")
        if int(summary.get("route_pending")) != pending_count:
            raise ContextError("payout pending count disagrees with routes")
        if int(summary.get("candidate_count")) != len(raw_candidates):
            raise ContextError("payout candidate count disagrees with candidates")
        if int(summary.get("candidates_with_verified_wise_net")) != expected_count:
            raise ContextError("verified Wise-net count disagrees with candidates")
    except (TypeError, ValueError) as exc:
        raise ContextError("payout route summary contains invalid counts") from exc

    priority_candidates: list[dict[str, Any]] = []
    for raw in raw_candidates:
        if not isinstance(raw, dict):
            raise ContextError("payout route state contains a non-object candidate")
        expected_wise_net = finite_number(raw.get("expected_wise_net"))
        priority_candidates.append(
            {
                "candidate_id": str(raw.get("candidate_id") or "")[:128],
                "source": str(raw.get("source") or "")[:32] or None,
                "title": str(raw.get("title") or "")[:180] or None,
                "asset": str(raw.get("asset") or "")[:32] or None,
                "network": str(raw.get("network") or "")[:64] or None,
                "listed_face_value_unrealized": finite_number(raw.get("gross_listed_amount")),
                "expected_wise_net_verified": expected_wise_net,
                "route_status": str(raw.get("route_status") or "unknown")[:48],
                "autonomy_qualified": raw.get("autonomy_qualified") is True,
                "reason_codes": compact_reason_codes(raw.get("reason_codes")),
                "source_urls": compact_public_state_urls(raw.get("source_urls")),
                "is_revenue": False,
                "is_settlement": False,
            }
        )
    priority_candidates.sort(
        key=lambda row: (
            row["expected_wise_net_verified"] is None,
            -(float(row["expected_wise_net_verified"] or 0)),
            -(float(row["listed_face_value_unrealized"] or 0)),
            str(row["candidate_id"]),
        )
    )

    return {
        "status": str(sidecar.get("status") or "unknown")[:48],
        "ranking_primary": "verified_expected_wise_net",
        "ranking_dimensions": [
            str(item)[:64]
            for item in policy.get("ranking_dimensions") or []
            if isinstance(item, str)
        ][:8],
        "realized_only_after": str(policy.get("realized_only_after") or "")[:128] or None,
        "human_action_required": False,
        "route_pending_is_revenue": False,
        "route_pending_is_settlement": False,
        "summary": {
            "route_count": len(raw_routes),
            "complete_verified": complete_count,
            "route_pending": pending_count,
            "candidate_count": len(raw_candidates),
            "candidates_with_verified_wise_net": expected_count,
            "funds_moved": summary.get("funds_moved") is True,
        },
        "routes": sorted(routes, key=lambda row: row["route_id"])[:MAX_ROUTE_ROWS],
        "priority_candidates": priority_candidates[:MAX_LARGE_BOUNTY_ROWS],
    }


def _priority_timestamp(value: Any) -> datetime | None:
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


def _priority_row(raw: dict[str, Any], queue_name: str, *, actionable: bool) -> dict[str, Any]:
    gates = raw.get("human_gates")
    if not isinstance(gates, dict):
        gates = {}
    return {
        "queue": queue_name,
        "stable_id": str(raw.get("stable_id") or "")[:240] or None,
        "candidate_id": str(raw.get("candidate_id") or "")[:200] or None,
        "source": str(raw.get("source") or "")[:48] or None,
        "provider": str(raw.get("provider") or "")[:100] or None,
        "title": str(raw.get("title") or "")[:240] or None,
        "asset": str(raw.get("asset") or "")[:32] or None,
        "network": str(raw.get("network") or "")[:64] or None,
        "deadline": str(raw.get("deadline") or "")[:64] or None,
        "listed_face_value_unrealized": finite_number(raw.get("gross_verified")),
        "expected_wise_net_verified": finite_number(raw.get("expected_wise_net_verified")),
        "payment_confidence_lcb_ppm": finite_number(raw.get("payment_confidence_lcb_ppm")),
        "net_if_paid_verified": finite_number(raw.get("net_if_paid_verified")),
        "time_to_wise_p90_seconds": finite_number(raw.get("time_to_wise_p90_seconds")),
        "route_id": str(raw.get("route_id") or "")[:160] or None,
        "route_status": str(raw.get("route_status") or "")[:48] or None,
        "explicit_execution_contract": raw.get("explicit_execution_contract") is True,
        "human_gates": {
            str(key)[:48]: value is True
            for key, value in sorted(gates.items())
            if isinstance(key, str)
        },
        "reason_codes": compact_reason_codes(raw.get("reason_codes")),
        "actionable": actionable,
        "is_revenue": False,
        "is_settlement": False,
        "funds_moved": False,
    }


def _priority_action_contract(raw: dict[str, Any]) -> bool:
    gates = raw.get("human_gates")
    metrics = (
        finite_number(raw.get("gross_verified")),
        finite_number(raw.get("expected_wise_net_verified")),
        finite_number(raw.get("payment_confidence_lcb_ppm")),
        finite_number(raw.get("net_if_paid_verified")),
        finite_number(raw.get("time_to_wise_p90_seconds")),
    )
    return all(
        (
            raw.get("listing_verified") is True,
            raw.get("source_fresh") is True,
            raw.get("provider_verified") is True,
            raw.get("agent_access") == "AGENT_ALLOWED",
            isinstance(gates, dict) and bool(gates),
            raw.get("human_gates_complete") is True,
            isinstance(gates, dict) and all(value is False for value in gates.values()),
            raw.get("asset_network_exact") is True,
            raw.get("self_custody_rail_verified") is True,
            raw.get("route_status") == "complete_verified",
            raw.get("explicit_execution_contract") is True,
            all(value is not None for value in metrics),
            metrics[0] is not None and float(metrics[0]) > 0,
            metrics[1] is not None and float(metrics[1]) > 0,
            metrics[2] is not None and float(metrics[2]) > 0,
            metrics[3] is not None and float(metrics[3]) > 0,
            metrics[4] is not None and float(metrics[4]) >= 0,
            raw.get("financial_classification") == "unrealized_opportunity_not_revenue",
            raw.get("funds_moved") is False,
            finite_number(raw.get("realized")) == 0,
        )
    )


def compact_bounty_priority_queue(
    sidecar: dict[str, Any] | None,
    *,
    now: datetime,
) -> dict[str, Any]:
    """Whitelist the deterministic queue and suppress execution when stale.

    The queue orders work; it is not settlement evidence.  Monitor-only rows
    remain visible to the supervisor but can never set an actionable signal.
    """
    baseline = {
        "present": sidecar is not None,
        "fresh": False,
        "observed_at": None,
        "age_seconds": None,
        "precedence": ["action_queue", "research_queue", "monitor_only"],
        "monitor_only_is_actionable": False,
        "listed_face_value_is_revenue": False,
        "expected_wise_net_is_revenue": False,
        "action_queue": [],
        "research_queue": [],
        "monitor_only": [],
        "summary": {
            "candidate_count": 0,
            "raw_action_count": 0,
            "effective_action_count": 0,
            "research_count": 0,
            "monitor_only_count": 0,
            "suppressed_action_count": 0,
        },
    }
    if sidecar is None:
        return {"status": "unavailable", "reason_codes": ["priority_queue_state_missing"], **baseline}

    reasons: list[str] = []
    recorded_hash = sidecar.get("result_sha256")
    unhashed = dict(sidecar)
    unhashed.pop("result_sha256", None)
    if not isinstance(recorded_hash, str) or re.fullmatch(r"[0-9a-f]{64}", recorded_hash) is None:
        reasons.append("priority_result_hash_missing_or_invalid")
    elif sha256_bytes(canonical_bytes(unhashed)) != recorded_hash:
        reasons.append("priority_result_hash_mismatch")
    raw_queues: dict[str, list[dict[str, Any]]] = {}
    for queue_name in ("action_queue", "research_queue", "monitor_only"):
        value = sidecar.get(queue_name)
        if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
            reasons.append(f"{queue_name}_shape_invalid")
            raw_queues[queue_name] = []
        else:
            raw_queues[queue_name] = value

    summary = sidecar.get("summary")
    if not isinstance(summary, dict):
        reasons.append("summary_shape_invalid")
        summary = {}
    expected_counts = {
        "candidate_count": sum(len(rows) for rows in raw_queues.values()),
        "action_count": len(raw_queues["action_queue"]),
        "research_count": len(raw_queues["research_queue"]),
        "monitor_only_count": len(raw_queues["monitor_only"]),
    }
    for key, expected in expected_counts.items():
        value = summary.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value != expected:
            reasons.append(f"summary_{key}_mismatch")

    policy = sidecar.get("policy")
    policy_safe = isinstance(policy, dict) and all(
        (
            policy.get("human_gate_disposition") == "monitor_only",
            policy.get("gross_is_revenue") is False,
            policy.get("settlement_evidence_consumed") is False,
            policy.get("execution_performed") is False,
        )
    )
    if not policy_safe:
        reasons.append("priority_policy_invalid")
    if sidecar.get("funds_moved") is not False or finite_number(sidecar.get("realized")) != 0:
        reasons.append("priority_financial_classification_invalid")

    observed = _priority_timestamp(sidecar.get("generated_at"))
    age_seconds: int | None = None
    if observed is None:
        reasons.append("priority_timestamp_invalid")
    else:
        age_seconds = math.floor((now.astimezone(timezone.utc) - observed).total_seconds())
        if age_seconds < -MAX_FUTURE_STATE_SKEW_SECONDS:
            reasons.append("priority_timestamp_in_future")
        elif age_seconds > MAX_BOUNTY_PRIORITY_AGE_SECONDS:
            reasons.append("priority_queue_stale")
    source_status = str(sidecar.get("status") or "unknown")[:48]
    if source_status != "ok":
        reasons.append("priority_source_not_ok")

    invalid_action_count = sum(not _priority_action_contract(row) for row in raw_queues["action_queue"])
    if invalid_action_count:
        reasons.append("action_contract_invalid")
    current = not reasons
    action_rows = raw_queues["action_queue"] if current else []
    research_rows = raw_queues["research_queue"]
    monitor_rows = raw_queues["monitor_only"]
    if "priority_queue_stale" in reasons:
        status = "stale_fail_closed"
    elif source_status != "ok" and not any(reason.endswith("_shape_invalid") for reason in reasons):
        status = "degraded_fail_closed"
    elif reasons:
        status = "invalid_fail_closed"
    else:
        status = "ok"

    return {
        "status": status,
        "source_status": source_status,
        "reason_codes": sorted(set(reasons)),
        **baseline,
        "fresh": current,
        "observed_at": isoformat(observed) if observed is not None else None,
        "age_seconds": age_seconds,
        "action_queue": [
            _priority_row(row, "action_queue", actionable=True)
            for row in action_rows[:MAX_BOUNTY_PRIORITY_ROWS]
        ],
        "research_queue": [
            _priority_row(row, "research_queue", actionable=False)
            for row in research_rows[:MAX_BOUNTY_PRIORITY_ROWS]
        ],
        "monitor_only": [
            _priority_row(row, "monitor_only", actionable=False)
            for row in monitor_rows[:MAX_BOUNTY_PRIORITY_ROWS]
        ],
        "summary": {
            "candidate_count": expected_counts["candidate_count"],
            "raw_action_count": expected_counts["action_count"],
            "effective_action_count": len(action_rows),
            "research_count": expected_counts["research_count"],
            "monitor_only_count": expected_counts["monitor_only_count"],
            "suppressed_action_count": expected_counts["action_count"] - len(action_rows),
        },
    }


def compact_superteam_scout(
    sidecar: dict[str, Any] | None,
    route_candidates: list[dict[str, Any]],
    *,
    source_state: str,
) -> dict[str, Any]:
    if sidecar is None:
        return {
            "status": "unavailable",
            "source_state": source_state,
            "reason_code": f"{source_state}_state_missing",
            "listed_face_value_is_revenue": False,
            "listed_face_value_is_settlement": False,
            "human_action_required": False,
            "items": [],
            "_all_items": [],
        }
    raw_candidates = sidecar.get("candidates")
    summary = sidecar.get("summary")
    policy = sidecar.get("policy")
    if not isinstance(raw_candidates, list) or not isinstance(summary, dict) or not isinstance(policy, dict):
        raise ContextError("Superteam scout state has invalid shape")
    if policy.get("public_data_only") is not True or policy.get("read_only") is not True:
        raise ContextError("Superteam scout state is not read-only public data")

    route_by_id = {str(row.get("candidate_id") or ""): row for row in route_candidates}
    items: list[dict[str, Any]] = []
    autonomy_count = 0
    for raw in raw_candidates:
        if not isinstance(raw, dict):
            raise ContextError("Superteam scout state contains a non-object candidate")
        reward = raw.get("reward")
        if not isinstance(reward, dict):
            raise ContextError("Superteam candidate reward has invalid shape")
        classification = reward.get("classification")
        if classification not in {
            "UNREALIZED_UNAUDITED_LISTING_FACE_VALUE",
            "UNREALIZED_UNAUDITED_MAXIMUM_INDIVIDUAL_FACE_VALUE",
        }:
            raise ContextError("Superteam listing value is not explicitly unrealized")
        if (
            classification == "UNREALIZED_UNAUDITED_MAXIMUM_INDIVIDUAL_FACE_VALUE"
            and reward.get("amount_basis") != "MAXIMUM_INDIVIDUAL_REWARD"
        ):
            raise ContextError("Superteam individual reward basis is not proven")
        autonomy = raw.get("autonomy_qualified") is True
        autonomy_count += int(autonomy)
        candidate_id = str(raw.get("id") or "")[:128]
        route = route_by_id.get(candidate_id, {})
        asset = str(reward.get("token") or "")[:32] or None
        if str(route.get("asset") or "").upper() != str(asset or "").upper():
            route = {}
        items.append(
            {
                "candidate_id": candidate_id,
                "provider": "superteam",
                "source_state": source_state,
                "rank": int(raw.get("rank")) if isinstance(raw.get("rank"), int) else None,
                "title": str(raw.get("title") or "")[:180] or None,
                "deadline": str(raw.get("deadline") or "")[:64] or None,
                "asset": asset,
                "asset_exact_no_fiat_equivalence": True,
                "listed_face_value_unrealized": finite_number(reward.get("amount")),
                "listed_face_value_basis": (
                    "maximum_individual_reward"
                    if classification == "UNREALIZED_UNAUDITED_MAXIMUM_INDIVIDUAL_FACE_VALUE"
                    else "legacy_listing_value"
                ),
                "expected_wise_net_verified": route.get("expected_wise_net_verified"),
                "route_status": route.get("route_status") or "route_pending",
                "autonomy_qualified": autonomy,
                "reason_codes": compact_reason_codes(raw.get("autonomy_reason_codes")),
                "source_urls": compact_public_state_urls(raw.get("source_urls")),
                "is_revenue": False,
                "is_settlement": False,
            }
        )

    try:
        reported_candidate_count = summary.get("list_filter_candidate_count", summary.get("candidate_count"))
        if int(reported_candidate_count) != len(raw_candidates):
            raise ContextError("Superteam candidate count disagrees with candidates")
        if int(summary.get("autonomy_qualified_count")) != autonomy_count:
            raise ContextError("Superteam autonomy count disagrees with candidates")
    except (TypeError, ValueError) as exc:
        raise ContextError("Superteam summary contains invalid counts") from exc
    items.sort(
        key=lambda row: (
            row["expected_wise_net_verified"] is None,
            -(float(row["expected_wise_net_verified"] or 0)),
            -(float(row["listed_face_value_unrealized"] or 0)),
            str(row["candidate_id"]),
        )
    )
    return {
        "status": str(sidecar.get("status") or "unknown")[:48],
        "source_state": source_state,
        "candidate_count": len(raw_candidates),
        "autonomy_qualified_count": autonomy_count,
        "verified_expected_wise_net_count": sum(
            row["expected_wise_net_verified"] is not None for row in items
        ),
        "ranking_primary": "verified_expected_wise_net",
        "listed_face_value_is_revenue": False,
        "listed_face_value_is_settlement": False,
        "human_action_required": False,
        "items": items[:MAX_LARGE_BOUNTY_ROWS],
        "_all_items": items,
    }


def stable_candidate_key(row: dict[str, Any]) -> str:
    provider = str(row.get("provider") or "superteam").lower()
    candidate_id = str(row.get("candidate_id") or "").strip().lower()
    if candidate_id:
        return f"{provider}|id|{candidate_id}"
    urls = [
        str(url).strip().lower()
        for url in row.get("source_urls") or []
        if isinstance(url, str) and "/api/listings/details/" in url
    ]
    if urls:
        return f"{provider}|url|{sorted(urls)[0]}"
    fallback = canonical_bytes(
        {
            "provider": provider,
            "title": row.get("title"),
            "asset": row.get("asset"),
            "deadline": row.get("deadline"),
        }
    )
    return f"{provider}|fallback|{sha256_bytes(fallback)}"


def combine_large_bounty_candidates(*sources: dict[str, Any]) -> dict[str, Any]:
    raw_items = [
        row
        for source in sources
        for row in source.get("_all_items") or source.get("items") or []
        if isinstance(row, dict)
    ]
    unique: dict[str, dict[str, Any]] = {}
    for row in raw_items:
        key = stable_candidate_key(row)
        current = unique.get(key)
        if current is None:
            unique[key] = row
            continue
        current_general = current.get("source_state") == "superteam_large_bounty_scout"
        new_general = row.get("source_state") == "superteam_large_bounty_scout"
        if new_general and not current_general:
            unique[key] = row
    items = list(unique.values())
    items.sort(
        key=lambda row: (
            row.get("expected_wise_net_verified") is None,
            -(float(row.get("expected_wise_net_verified") or 0)),
            -(float(row.get("listed_face_value_unrealized") or 0)),
            str(row.get("candidate_id") or ""),
        )
    )
    return {
        "status": "ok" if any(source.get("status") == "ok" for source in sources) else "unavailable",
        "sources": [
            {
                "source_state": source.get("source_state"),
                "status": source.get("status"),
                "candidate_count": int(source.get("candidate_count") or 0),
            }
            for source in sources
        ],
        "raw_candidate_count": len(raw_items),
        "candidate_count": len(items),
        "overlap_duplicate_count": len(raw_items) - len(items),
        "autonomy_qualified_count": sum(row.get("autonomy_qualified") is True for row in items),
        "verified_expected_wise_net_count": sum(
            row.get("expected_wise_net_verified") is not None for row in items
        ),
        "ranking_primary": "verified_expected_wise_net",
        "asset_symbols_are_not_fiat_equivalence": True,
        "listed_face_value_is_revenue": False,
        "listed_face_value_is_settlement": False,
        "human_action_required": False,
        "items": items[:MAX_LARGE_BOUNTY_ROWS],
    }


def forbidden_key_paths(value: Any, path: str = "root") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            lower = str(key).lower()
            if lower in FORBIDDEN_OUTPUT_KEYS or any(word in lower for word in ("private_key", "mnemonic", "seed_phrase")):
                errors.append(f"{path}.{key}")
            errors.extend(forbidden_key_paths(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(forbidden_key_paths(child, f"{path}[{index}]"))
    return errors


def build_context(
    root: Path = DEFAULT_ROOT,
    *,
    now: datetime | None = None,
    health_provider: Callable[[], dict[str, Any]] = systemd_health,
    bridge_request_path: Path | None = None,
) -> dict[str, Any]:
    now = now or utcnow()
    base = root / "data/aro"
    ledger_path = base / "bounty_receive_ledger.json"
    realized_path = base / "realized_revenue_ledger.jsonl"
    signals_path = base / "proposals/email_bounty_signals.jsonl"
    commands_path = base / "inbox/user_commands.jsonl"
    rustchain_path = base / "rustchain_reconciliation.json"
    payout_route_path = root / PAYOUT_ROUTE_STATE
    if bridge_request_path is None:
        bridge_request_path = (
            RTC_BRIDGE_REQUEST_STATE
            if root.resolve() == DEFAULT_ROOT.resolve()
            else root / RTC_BRIDGE_REQUEST_TEST_STATE
        )
    superteam_scout_path = root / SUPERTEAM_SCOUT_STATE
    superteam_large_scout_path = root / SUPERTEAM_LARGE_SCOUT_STATE
    bounty_priority_path = root / BOUNTY_PRIORITY_STATE

    ledger, ledger_raw = load_json(ledger_path)
    if not isinstance(ledger, dict) or not isinstance(ledger.get("entries"), list):
        raise ContextError("canonical bounty ledger has invalid shape")
    entries = [row for row in ledger["entries"] if isinstance(row, dict)]
    if len(entries) != len(ledger["entries"]):
        raise ContextError("canonical bounty ledger contains non-object entries")
    realized, realized_raw = load_jsonl(realized_path)
    signals, signals_raw = load_jsonl(signals_path)
    commands, commands_raw = load_jsonl(commands_path)
    rustchain, rustchain_raw = load_json(rustchain_path)
    if not isinstance(rustchain, dict):
        raise ContextError("RustChain sidecar has invalid shape")
    payout_route_state, payout_route_raw = load_optional_object(payout_route_path)
    bridge_request_state, bridge_request_raw = load_optional_object(bridge_request_path)
    superteam_scout_state, superteam_scout_raw = load_optional_object(superteam_scout_path)
    superteam_large_scout_state, superteam_large_scout_raw = load_optional_object(superteam_large_scout_path)
    bounty_priority_state, bounty_priority_raw = load_optional_object(bounty_priority_path)
    ledger_sha256 = sha256_bytes(ledger_raw)
    if rustchain.get("ledger_sha256") != ledger_sha256:
        raise ContextError("RustChain sidecar references a stale canonical ledger")

    statuses = Counter(str(row.get("status") or "unknown") for row in entries)
    blocker_counts = Counter(blocker for row in entries for blocker in blocker_types(row))
    bounty_keys = [str(row.get("bounty_key") or "") for row in entries]
    if any(not key for key in bounty_keys):
        raise ContextError("canonical bounty ledger contains an entry without bounty_key")
    duplicate_keys = sorted(key for key, count in Counter(bounty_keys).items() if count > 1)
    if duplicate_keys:
        raise ContextError("canonical bounty ledger contains duplicate bounty_key values")
    provider_rows = sorted(
        (compact_ledger_line(row) for row in entries if row.get("status") == "provider_confirmed"),
        key=lambda row: row["id"],
    )
    wallet_received_rows = sorted(
        (compact_ledger_line(row) for row in entries if row.get("status") == "wallet_received"),
        key=lambda row: row["id"],
    )
    rustchain_keys = {str(key) for key in rustchain.get("canonical_bounty_keys") or []}
    rustchain_provider_entries = [
        row
        for row in entries
        if row.get("status") in {"provider_confirmed", "wallet_received"}
        and str(row.get("bounty_key") or "") in rustchain_keys
    ]
    rustchain_provider_total = rustchain.get("provider_confirmed_total") or {}
    try:
        expected_rustchain_count = int(rustchain_provider_total.get("entry_count"))
        expected_rustchain_amount = float(rustchain_provider_total.get("amount"))
        actual_rustchain_amount = sum(float(compact_amount(row) or 0) for row in rustchain_provider_entries)
    except Exception as exc:
        raise ContextError("RustChain provider-confirmed total is invalid") from exc
    if expected_rustchain_count != len(rustchain_provider_entries) or abs(expected_rustchain_amount - actual_rustchain_amount) > 0.000001:
        raise ContextError("RustChain provider-confirmed total disagrees with canonical ledger")
    rustchain_wallet_entries = [
        row
        for row in entries
        if row.get("status") == "wallet_received"
        and str(row.get("bounty_key") or "") in rustchain_keys
    ]
    rustchain_wallet_total = rustchain.get("wallet_received_total") or {}
    try:
        expected_wallet_count = int(rustchain_wallet_total.get("entry_count"))
        expected_wallet_amount = float(rustchain_wallet_total.get("amount"))
        actual_wallet_amount = sum(float(compact_amount(row) or 0) for row in rustchain_wallet_entries)
    except Exception as exc:
        raise ContextError("RustChain wallet-received total is invalid") from exc
    if expected_wallet_count != len(rustchain_wallet_entries) or abs(expected_wallet_amount - actual_wallet_amount) > 0.000001:
        raise ContextError("RustChain wallet-received total disagrees with canonical ledger")
    submitted_rows = sorted(
        (compact_ledger_line(row) for row in entries if row.get("status") == "submitted"),
        key=lambda row: row["id"],
    )
    blocked_rows = sorted(
        (compact_ledger_line(row) for row in entries if str(row.get("status") or "").startswith("blocked")),
        key=lambda row: row["id"],
    )
    candidates = email_candidates(signals)
    pending_commands = pending_command_count(commands)
    inbound_automation = compact_inbound_automation(root, commands, now=now)
    bridge_request = compact_rtc_bridge_request(bridge_request_state)
    payout_routes = compact_payout_routes(payout_route_state, bridge_request)
    route_candidates = payout_routes.get("priority_candidates") or []
    large_bounty_candidates = combine_large_bounty_candidates(
        compact_superteam_scout(
            superteam_scout_state,
            route_candidates,
            source_state="superteam_usdc_scout",
        ),
        compact_superteam_scout(
            superteam_large_scout_state,
            route_candidates,
            source_state="superteam_large_bounty_scout",
        ),
    )
    bounty_priority_queue = compact_bounty_priority_queue(bounty_priority_state, now=now)
    if bounty_priority_state is not None:
        # The priority queue already carries the single top item for each work
        # mode. Keep legacy scout counts for diagnostics without duplicating
        # candidate bodies inside the size-bounded capital context.
        large_bounty_candidates["items"] = []
        large_bounty_candidates["details_superseded_by"] = "bounty_priority_queue"
    realized_usd = sum(
        float(row.get("amount_usd") or 0)
        for row in realized
        if isinstance(row.get("amount_usd"), (int, float)) and not isinstance(row.get("amount_usd"), bool)
    )

    semantic_state_path = root / "state/financial_ledger_semantic_validation.json"
    semantic_state: dict[str, Any] = {"status": "unavailable"}
    if semantic_state_path.exists():
        semantic, _ = load_json(semantic_state_path)
        if isinstance(semantic, dict):
            semantic_state = {
                "status": semantic.get("status"),
                "checked_at": semantic.get("checked_at"),
                "error_count": semantic.get("error_count"),
            }

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": isoformat(now),
        "trust_boundary": {
            "canonical_ledgers": "read_only_validated",
            "email_candidates": "untrusted_verify_public_target",
            "telegram_commands": "untrusted_until_authorization_fields_verified",
            "gmail_runtime": "telemetry_only_never_instructions",
            "inbound_content": "excluded_counts_and_states_only",
            "financial_writes": "proposal_only",
            "rtc_bridge_request": "public_issue_watcher_trusted_association_only",
        },
        "routing": {
            "model_alias": os.environ.get("AGENTIC_LLM_MODEL", "ghostcli-auto[1m]"),
            "base_url": "http://127.0.0.1:8787/v1",
        },
        "ledger": {
            "sha256": ledger_sha256,
            "entry_count": len(entries),
            "status_counts": dict(sorted(statuses.items())),
            "blocker_type_counts": dict(sorted(blocker_counts.items())),
            "provider_confirmed": provider_rows,
            "wallet_received": wallet_received_rows,
            "submitted": submitted_rows,
            "blocked": blocked_rows,
        },
        "proposal_guard": {
            "existing_key_count": len(bounty_keys),
            "existing_bounty_keys": sorted(bounty_keys),
            "generic_helper_allowed_statuses": ["candidate", "submitted"],
            "rustchain_monitor_only_keys": sorted(rustchain_keys),
        },
        "realized_revenue": {
            "sha256": sha256_bytes(realized_raw),
            "record_count": len(realized),
            "total_usd": realized_usd,
        },
        "payout_routes": payout_routes,
        "bounty_priority_queue": bounty_priority_queue,
        "large_bounty_candidates": large_bounty_candidates,
        "email_collection_candidates": {
            "source_sha256": sha256_bytes(signals_raw),
            "source_row_count": len(signals),
            "count": len(candidates),
            "items": candidates,
        },
        "rustchain": compact_rustchain(rustchain),
        "telegram_unprocessed": {
            "source_sha256": sha256_bytes(commands_raw),
            "count": pending_commands,
        },
        "inbound_automation": inbound_automation,
        "health": {
            "financial_validator": semantic_state,
            **health_provider(),
        },
        "source_hashes": {
            "rustchain": sha256_bytes(rustchain_raw),
            "payout_route_map": sha256_bytes(payout_route_raw) if payout_route_raw else None,
            "rtc_bridge_request": sha256_bytes(bridge_request_raw) if bridge_request_raw else None,
            "superteam_usdc_scout": sha256_bytes(superteam_scout_raw) if superteam_scout_raw else None,
            "superteam_large_bounty_scout": sha256_bytes(superteam_large_scout_raw) if superteam_large_scout_raw else None,
            "bounty_priority_queue": sha256_bytes(bounty_priority_raw) if bounty_priority_raw else None,
        },
    }
    payload["material_state_id"] = sha256_bytes(canonical_bytes(material_state_payload(payload)))[:32]
    identity_payload = {key: value for key, value in payload.items() if key != "generated_at"}
    payload["context_id"] = sha256_bytes(canonical_bytes(identity_payload))[:32]

    forbidden = forbidden_key_paths(payload)
    if forbidden:
        raise ContextError("forbidden output fields: " + ", ".join(forbidden))
    encoded = canonical_bytes(payload) + b"\n"
    if len(encoded) > MAX_CONTEXT_BYTES:
        raise ContextError(f"compact context exceeds {MAX_CONTEXT_BYTES} bytes: {len(encoded)}")
    if payload["email_collection_candidates"]["count"] != len(payload["email_collection_candidates"]["items"]):
        raise ContextError("email candidate summary is inconsistent")
    if sum(payload["ledger"]["status_counts"].values()) != payload["ledger"]["entry_count"]:
        raise ContextError("ledger status summary is inconsistent")
    if payload["proposal_guard"]["existing_key_count"] != payload["ledger"]["entry_count"]:
        raise ContextError("proposal guard key summary is inconsistent")
    if payload["inbound_automation"]["raw_content_included"] is not False:
        raise ContextError("inbound runtime summary attempted to include raw content")
    if payload["telegram_unprocessed"]["count"] != payload["inbound_automation"]["telegram"]["pending"]:
        raise ContextError("Telegram backlog summaries disagree")
    if payload["inbound_automation"]["gmail"]["email_is_instruction"] is not False:
        raise ContextError("Gmail telemetry must never be treated as instructions")
    return payload


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temp, path)
    os.chmod(path, 0o600)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--max-bytes", type=int, default=MAX_CONTEXT_BYTES)
    parser.add_argument("--bridge-request-state", default=None)
    args = parser.parse_args()
    try:
        context = build_context(
            Path(args.root),
            bridge_request_path=Path(args.bridge_request_state) if args.bridge_request_state else None,
        )
        encoded = canonical_bytes(context) + b"\n"
        if len(encoded) > args.max_bytes:
            raise ContextError(f"context is {len(encoded)} bytes, limit is {args.max_bytes}")
        atomic_write(Path(args.output), encoded)
    except Exception as exc:
        print(f"CAPITAL_CONTEXT_BLOCKED {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(
        "CAPITAL_CONTEXT_READY "
        f"path={args.output} bytes={len(encoded)} id={context['context_id']} "
        f"email_candidates={context['email_collection_candidates']['count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
