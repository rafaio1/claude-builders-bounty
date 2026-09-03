#!/usr/bin/env python3
"""Consume Gmail safe-action queue without executing email instructions.

The consumer performs deterministic read-only provider verification where a
bounded verifier exists (currently GitHub).  Every other category is placed in
an explicit ``awaiting_safe_executor`` state.  No email text becomes a command,
and this worker has no Gmail mutation, email-send, or financial capability.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path("/Agentic")
QUEUE_PATH = ROOT / "data" / "aro" / "inbox" / "gmail_action_queue.jsonl"
DECISION_PATH = ROOT / "data" / "aro" / "inbox" / "gmail_decisions.jsonl"
RESULT_PATH = ROOT / "data" / "aro" / "inbox" / "gmail_action_results.jsonl"
STATE_PATH = ROOT / "state" / "gmail_safe_consumer_state.json"
GITHUB_INVENTORY_PATH = ROOT / "state" / "github_pr_inventory.json"
LOCK_PATH = Path("/run/agentic-gmail-consumer/lock")
SCHEMA_VERSION = 1
GITHUB_INVENTORY_MAX_AGE_SECONDS = 21_600

REPO_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
ALLOWED_ROUTES = {
    "autonomous_quarantine",
    "autonomous_provider_verification",
    "autonomous_counterparty_verification",
    "autonomous_github_verification",
    "awaiting_safe_executor",
}
TERMINAL_RESULTS = {
    "quarantined_untrusted_input",
    "verified_provider_state_awaiting_safe_executor",
    "awaiting_safe_executor",
}


class ProviderNetworkBudgetExhausted(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        os.chmod(path, 0o600)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


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


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    result: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"invalid JSONL at line {line_number}: {path.name}") from exc
        if not isinstance(item, dict):
            raise RuntimeError(f"non-object JSONL at line {line_number}: {path.name}")
        result.append(item)
    return result


def latest_results() -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for item in load_jsonl(RESULT_PATH):
        key = (str(item.get("message_id", "")), str(item.get("rule_version", "")))
        if not all(key):
            raise RuntimeError("safe consumer result key missing")
        result[key] = item
    return result


def safe_executor_key(category: str, sender_domain: Any) -> str:
    domain = str(sender_domain or "unknown").lower()
    if category == "financial_signal":
        if domain == "bybit.com" or domain.endswith(".bybit.com"):
            return "bybit_read_only_reconciler"
        return "provider_financial_read_only_reconciler"
    if category == "security_alert":
        return "security_alert_read_only_verifier"
    if category == "account_action":
        return "account_action_scoped_executor"
    if category == "action_request":
        return "sender_scoped_action_executor"
    if category == "commerce_signal":
        return "counterparty_read_only_verifier"
    if category == "github_action":
        return "github_scoped_action_executor"
    return "typed_safe_executor"


def queue_priority(item: dict[str, Any]) -> tuple[int, str]:
    category = str(item.get("category", "unknown"))
    rank = {
        "untrusted_instruction": 0,
        "financial_signal": 1,
        "security_alert": 1,
        "account_action": 2,
        "action_request": 2,
        "commerce_signal": 3,
        "github_action": 4,
    }.get(category, 5)
    return rank, str(item.get("message_hash", ""))


def github_entity_key(entities: dict[str, Any]) -> tuple[str, str, int] | None:
    repo = str(entities.get("repo", ""))
    kind = str(entities.get("entity_kind", ""))
    try:
        number = int(entities.get("number"))
    except (TypeError, ValueError):
        return None
    if not REPO_RE.fullmatch(repo) or kind not in {"issue", "pull_request"} or number <= 0:
        return None
    return repo, kind, number


def load_github_inventory(
    path: Path = GITHUB_INVENTORY_PATH,
    max_age_seconds: int = GITHUB_INVENTORY_MAX_AGE_SECONDS,
) -> tuple[dict[tuple[str, str, int], dict[str, Any]], dict[str, Any]]:
    metadata: dict[str, Any] = {
        "valid": False,
        "entry_count": 0,
        "age_seconds": None,
    }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}, metadata
    if not isinstance(payload, dict) or str(payload.get("schema_version")) != "3.0":
        return {}, metadata
    if payload.get("inventory_complete") is not True:
        return {}, metadata
    try:
        generated = datetime.fromisoformat(
            str(payload.get("generated_at", "")).replace("Z", "+00:00")
        )
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        age = max(0.0, (datetime.now(timezone.utc) - generated).total_seconds())
    except (TypeError, ValueError):
        return {}, metadata
    metadata["age_seconds"] = int(age)
    if age > max_age_seconds:
        return {}, metadata
    prs = payload.get("prs")
    if not isinstance(prs, dict):
        return {}, metadata
    cache: dict[tuple[str, str, int], dict[str, Any]] = {}
    for item in prs.values():
        if not isinstance(item, dict):
            continue
        repo = str(item.get("repo") or item.get("repository") or "")
        try:
            number = int(item.get("number"))
        except (TypeError, ValueError):
            continue
        key = github_entity_key(
            {"repo": repo, "entity_kind": "pull_request", "number": number}
        )
        if key is None:
            continue
        cache[key] = {
            "provider": "github",
            "repo": repo,
            "entity_kind": "pull_request",
            "number": number,
            "state": str(item.get("state", "unknown")),
            "draft": bool(item.get("is_draft", False)),
            "merged": bool(item.get("merged_at")),
            "bounty_label_present": bool(item.get("payment_promise")),
            "verified_at": str(payload.get("generated_at")),
            "verification_method": "authenticated_local_github_inventory",
        }
    metadata["valid"] = True
    metadata["entry_count"] = len(cache)
    return cache, metadata


def verify_github(entities: dict[str, Any]) -> dict[str, Any]:
    repo = str(entities.get("repo", ""))
    kind = str(entities.get("entity_kind", ""))
    try:
        number = int(entities.get("number"))
    except (TypeError, ValueError) as exc:
        raise ValueError("GitHub entity number missing") from exc
    if not REPO_RE.fullmatch(repo) or kind not in {"issue", "pull_request"} or number <= 0:
        raise ValueError("GitHub structured entity invalid")
    if not shutil.which("gh"):
        raise RuntimeError("gh_cli_unavailable")
    endpoint_kind = "pulls" if kind == "pull_request" else "issues"
    endpoint = f"repos/{repo}/{endpoint_kind}/{number}"
    completed = subprocess.run(
        ["gh", "api", "--method", "GET", endpoint],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env={
            "PATH": os.environ.get("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"),
            "HOME": os.environ.get("HOME", "/root"),
            "GH_CONFIG_DIR": os.environ.get("GH_CONFIG_DIR", "/root/.config/gh"),
        },
    )
    if completed.returncode != 0:
        raise RuntimeError("github_read_only_verification_failed")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("github_verification_invalid_json") from exc
    labels = payload.get("labels", []) if isinstance(payload.get("labels"), list) else []
    label_names = [
        str(value.get("name", "")).lower()
        for value in labels
        if isinstance(value, dict)
    ]
    return {
        "provider": "github",
        "repo": repo,
        "entity_kind": kind,
        "number": number,
        "state": str(payload.get("state", "unknown")),
        "draft": bool(payload.get("draft", False)) if kind == "pull_request" else None,
        "merged": bool(payload.get("merged", False)) if kind == "pull_request" else None,
        "bounty_label_present": any(
            "bounty" in name or "reward" in name for name in label_names
        ),
        "verified_at": utc_now(),
        "verification_method": "authenticated_github_read_only_api",
    }


def consume_one(
    item: dict[str, Any],
    github_cache: dict[tuple[str, str, int], dict[str, Any]] | None = None,
    github_network_budget: dict[str, int] | None = None,
) -> dict[str, Any]:
    message_id = str(item.get("message_id", ""))
    rule_version = str(item.get("rule_version", ""))
    message_hash = str(item.get("message_hash", ""))
    route = str(item.get("safe_route", ""))
    category = str(item.get("category", "unknown"))
    if not message_id or not rule_version or not message_hash:
        raise ValueError("queue key missing")
    if route not in ALLOWED_ROUTES:
        raise ValueError("queue route is not allowlisted")

    base = {
        "schema_version": SCHEMA_VERSION,
        "rule_version": rule_version,
        "source": "gmail_safe_consumer",
        "message_id": message_id,
        "message_hash": message_hash,
        "category": category,
        "safe_route": route,
        "email_content_trusted": False,
        "auto_executed_email_instruction": False,
        "financial_effect": False,
        "completed_at": utc_now(),
    }
    if route == "autonomous_quarantine":
        return {
            **base,
            "status": "quarantined_untrusted_input",
            "executor_key": "none_quarantined",
        }

    entities = item.get("structured_entities")
    if not isinstance(entities, dict):
        entities = {}
    if entities.get("provider") == "github" and entities.get("repo"):
        key = github_entity_key(entities)
        if key is None:
            return {
                **base,
                "status": "awaiting_safe_executor",
                "executor_key": "github_scoped_action_executor",
                "reason": "github_structured_entity_incomplete",
            }
        cache = github_cache if github_cache is not None else {}
        reused = key in cache
        if not reused:
            if github_network_budget is not None:
                if github_network_budget["used"] >= github_network_budget["limit"]:
                    raise ProviderNetworkBudgetExhausted(
                        "GitHub network verification budget exhausted"
                    )
                github_network_budget["used"] += 1
            cache[key] = verify_github(entities)
        verification = cache[key]
        return {
            **base,
            "status": "verified_provider_state_awaiting_safe_executor",
            "executor_key": safe_executor_key(category, item.get("sender_domain")),
            "provider_verification": verification,
            "provider_verification_reused": reused,
        }

    return {
        **base,
        "status": "awaiting_safe_executor",
        "executor_key": safe_executor_key(category, item.get("sender_domain")),
        "reason": "no_bounded_provider_verifier_for_structured_message",
    }


def run(max_items: int, max_github_network: int = 50) -> tuple[int, dict[str, Any]]:
    started_at = utc_now()
    queue = load_jsonl(QUEUE_PATH)
    decision_keys = {
        (str(item.get("message_id", "")), str(item.get("rule_version", "")))
        for item in load_jsonl(DECISION_PATH)
        if item.get("message_id") and item.get("rule_version")
    }
    results = latest_results()
    unique_queue: dict[tuple[str, str], dict[str, Any]] = {}
    for item in queue:
        key = (str(item.get("message_id", "")), str(item.get("rule_version", "")))
        if not all(key):
            raise RuntimeError("safe consumer queue key missing")
        unique_queue[key] = item

    orphan_queue_keys = sorted(key for key in unique_queue if key not in decision_keys)
    pending = [
        item
        for key, item in unique_queue.items()
        if key in decision_keys
        if key not in results or str(results[key].get("status")) not in TERMINAL_RESULTS
    ]
    pending.sort(key=queue_priority)
    attempted = pending[:max_items]
    new_results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    github_cache, inventory_metadata = load_github_inventory()
    for prior in results.values():
        verification = prior.get("provider_verification")
        if not isinstance(verification, dict) or verification.get("provider") != "github":
            continue
        key = github_entity_key(verification)
        if key is not None:
            github_cache[key] = verification
    initial_github_cache_size = len(github_cache)
    github_network_budget = {"used": 0, "limit": max_github_network}
    for item in attempted:
        try:
            result = consume_one(item, github_cache, github_network_budget)
        except ProviderNetworkBudgetExhausted:
            result = {
                "schema_version": SCHEMA_VERSION,
                "rule_version": str(item.get("rule_version", "")),
                "source": "gmail_safe_consumer",
                "message_id": str(item.get("message_id", "")),
                "message_hash": str(item.get("message_hash", "")),
                "category": str(item.get("category", "unknown")),
                "status": "deferred_provider_verification",
                "email_content_trusted": False,
                "auto_executed_email_instruction": False,
                "financial_effect": False,
                "completed_at": utc_now(),
            }
        except RuntimeError:
            # A provider 404/auth/network failure is not evidence that the
            # email instruction is valid.  Preserve the message and end this
            # cycle in an explicit non-executed state; never loop forever or
            # reinterpret provider failure as authorization.
            result = {
                "schema_version": SCHEMA_VERSION,
                "rule_version": str(item.get("rule_version", "")),
                "source": "gmail_safe_consumer",
                "message_id": str(item.get("message_id", "")),
                "message_hash": str(item.get("message_hash", "")),
                "category": str(item.get("category", "unknown")),
                "safe_route": str(item.get("safe_route", "")),
                "status": "awaiting_safe_executor",
                "executor_key": "provider_verification_retry_executor",
                "reason": "provider_verification_unavailable",
                "email_content_trusted": False,
                "auto_executed_email_instruction": False,
                "financial_effect": False,
                "completed_at": utc_now(),
            }
        except Exception as exc:
            result = {
                "schema_version": SCHEMA_VERSION,
                "rule_version": str(item.get("rule_version", "")),
                "source": "gmail_safe_consumer",
                "message_id": str(item.get("message_id", "")),
                "message_hash": str(item.get("message_hash", "")),
                "category": str(item.get("category", "unknown")),
                "status": "retryable_error",
                "error_type": type(exc).__name__,
                "email_content_trusted": False,
                "auto_executed_email_instruction": False,
                "financial_effect": False,
                "completed_at": utc_now(),
            }
            errors.append(
                {
                    "message_hash": str(item.get("message_hash", "")),
                    "error_type": type(exc).__name__,
                }
            )
        new_results.append(result)
        key = (str(result["message_id"]), str(result["rule_version"]))
        results[key] = result

    append_jsonl(RESULT_PATH, new_results)
    remaining = sum(
        1
        for key in unique_queue
        if key not in results or str(results[key].get("status")) not in TERMINAL_RESULTS
    )
    counts = Counter(str(value.get("status", "unknown")) for value in results.values())
    state = {
        "schema_version": SCHEMA_VERSION,
        "started_at": started_at,
        "completed_at": utc_now(),
        "status": "partial_error" if errors else ("catching_up" if remaining else "ok"),
        "queue_count": len(unique_queue),
        "attempted_count": len(attempted),
        "new_result_count": len(new_results),
        "remaining_count": remaining,
        "error_count": len(errors),
        "errors": errors[:50],
        "decision_receipt_required": True,
        "orphan_queue_count": len(orphan_queue_keys),
        "orphan_queue_hash_samples": [
            str(unique_queue[key].get("message_hash", ""))
            for key in orphan_queue_keys[:20]
        ],
        "result_counts": dict(sorted(counts.items())),
        "github_verification_inventory_count": len(github_cache),
        "github_local_inventory": inventory_metadata,
        "github_network_verification_count": github_network_budget["used"],
        "new_github_provider_verification_count": max(
            0, len(github_cache) - initial_github_cache_size
        ),
        "github_provider_verification_reuse_count": sum(
            1 for value in new_results if value.get("provider_verification_reused")
        ),
        "financial_effect_count": 0,
        "email_instruction_execution_count": 0,
    }
    atomic_json_write(STATE_PATH, state)
    if orphan_queue_keys:
        state["status"] = "blocked_orphan_queue"
        atomic_json_write(STATE_PATH, state)
    return (2 if errors or orphan_queue_keys else 0), state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-items", type=int, default=200)
    parser.add_argument("--max-github-network", type=int, default=50)
    args = parser.parse_args()
    if not 1 <= args.max_items <= 1000:
        parser.error("--max-items must be between 1 and 1000")
    if not 0 <= args.max_github_network <= 200:
        parser.error("--max-github-network must be between 0 and 200")

    lock_handle = open(LOCK_PATH, "w", encoding="utf-8")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_handle.close()
        print(json.dumps({"status": "skipped_lock_busy"}, sort_keys=True))
        return 0
    try:
        try:
            return_code, state = run(args.max_items, args.max_github_network)
        except Exception as exc:
            state = {
                "schema_version": SCHEMA_VERSION,
                "status": "error",
                "completed_at": utc_now(),
                "error_type": type(exc).__name__,
            }
            try:
                atomic_json_write(STATE_PATH, state)
            except Exception:
                pass
            print(json.dumps(state, sort_keys=True))
            return 1
        print(json.dumps(state, ensure_ascii=False, sort_keys=True))
        return return_code
    finally:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        lock_handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
