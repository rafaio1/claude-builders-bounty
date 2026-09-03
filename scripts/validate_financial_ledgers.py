#!/usr/bin/env python3
"""Fail-closed structural and semantic validator for Agentic financial artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_ROOT = Path(os.environ.get("AGENTIC_ROOT", "/Agentic"))
PRODUCTION_ROOT = Path("/Agentic")
PRODUCTION_AUTHORITY_DIR = Path("/var/lib/agentic/ledger-authority")
FUTURE_SKEW_SECONDS = int(os.environ.get("AGENTIC_FINANCIAL_FUTURE_SKEW_SECONDS", "300"))
REPORT_MAX_AGE_SECONDS = int(os.environ.get("AGENTIC_FINANCIAL_REPORT_MAX_AGE_SECONDS", "1200"))
RUSTCHAIN_WALLET = "RTC1e9bf7a2a60aac9bcbc5a0df0c65e9501e932861"
RUSTCHAIN_EXPECTED = {
    "github|Scottcjn/rustchain-bounties|254": 4.0,
    "github|Scottcjn/Rustchain|8295": 5.0,
    "github|Scottcjn/Rustchain|8289": 5.0,
}
HEX_TXID_RE = re.compile(r"^[0-9a-f]{32}$", re.I)
HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.I)
RUSTCHAIN_AUTHORITY = "rustchain-public-evidence-v2"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def authority_directory(root: Path) -> Path:
    configured = os.environ.get("AGENTIC_LEDGER_AUTHORITY_DIR", "").strip()
    if configured:
        return Path(configured)
    if root.resolve() == PRODUCTION_ROOT:
        return PRODUCTION_AUTHORITY_DIR
    return root / "var/lib/agentic/ledger-authority"


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def transaction_ids(row: dict[str, Any]) -> list[str]:
    values: list[str] = []
    if str(row.get("txid") or "").strip():
        values.append(str(row["txid"]).strip())
    if isinstance(row.get("txids"), list):
        values.extend(str(value).strip() for value in row["txids"] if str(value).strip())
    return list(dict.fromkeys(values))


def wallet_history_evidence(row: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in row.get("provider_evidence") or []:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source_url") or "")
        evidence_type = str(item.get("evidence_type") or "").lower()
        if source.startswith("https://") and "wallet" in evidence_type and "history" in evidence_type:
            result.append(item)
    return result


def iter_timestamps(value: Any, path: str = "root") -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            lower = str(key).lower()
            if isinstance(child, str) and (lower in {"timestamp", "created_at", "updated_at", "observed_at", "generated_at", "reconciled_at"} or lower.endswith("_at")):
                yield child_path, child
            yield from iter_timestamps(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_timestamps(child, f"{path}[{index}]")


def evidence(row: dict[str, Any]) -> bool:
    provider = row.get("provider_evidence")
    return bool(
        str(row.get("txid") or "").strip()
        or str(row.get("provider_confirmation") or "").strip()
        or (isinstance(provider, list) and any(isinstance(item, dict) and item.get("source_url") for item in provider))
    )


def load_receive(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, [f"receive ledger invalid: {type(exc).__name__}"]
    if not isinstance(payload, dict):
        return None, ["receive ledger root must be an object"]
    return payload, []


def realized_records(path: Path, errors: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="strict").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            errors.append(f"realized line {line_no} is invalid JSON")
            continue
        if not isinstance(row, dict):
            errors.append(f"realized line {line_no} is not an object")
            continue
        rows.append(row)
    return rows


def validate_receive(
    receive: dict[str, Any],
    *,
    now: datetime,
    future_skew: timedelta,
) -> tuple[list[str], list[dict[str, Any]]]:
    errors: list[str] = []
    entries = receive.get("entries")
    if not isinstance(entries, list):
        return ["receive ledger entries must be a list"], []
    ids: set[str] = set()
    keys: set[str] = set()
    valid_rows: list[dict[str, Any]] = []
    for index, row in enumerate(entries):
        if not isinstance(row, dict):
            errors.append(f"receive[{index}] is not an object")
            continue
        valid_rows.append(row)
        ledger_id = str(row.get("ledger_id") or "").strip()
        bounty_key = str(row.get("bounty_key") or "").strip()
        if not ledger_id or ledger_id in ids:
            errors.append(f"receive[{index}] missing or duplicate ledger_id")
        if not bounty_key or bounty_key in keys:
            errors.append(f"receive[{index}] missing or duplicate bounty_key")
        ids.add(ledger_id)
        keys.add(bounty_key)
        status = str(row.get("status") or "")
        if status == "blocked_missing_receive_rail":
            steps = row.get("recovery_steps")
            if not isinstance(steps, list) or not steps or not all(isinstance(step, str) and step.strip() for step in steps):
                errors.append(f"receive[{index}] missing actionable recovery_steps")
        if status == "provider_confirmed":
            try:
                confirmed_amount = float(row.get("provider_confirmed_amount") or row.get("expected_amount") or 0)
            except Exception:
                confirmed_amount = 0
            if confirmed_amount <= 0 or not evidence(row):
                errors.append(f"receive[{index}] provider_confirmed without positive amount and public evidence")
        if status == "wallet_received":
            try:
                received_amount = float(row.get("amount_received") or 0)
            except Exception:
                received_amount = 0
            txids = transaction_ids(row)
            if received_amount <= 0 or not txids or not all(HEX_TXID_RE.fullmatch(txid) for txid in txids):
                errors.append(f"receive[{index}] wallet_received without positive amount and valid transaction ids")
            if row.get("confirmation_status") != "confirmed_immutable_ledger":
                errors.append(f"receive[{index}] wallet_received lacks immutable-ledger confirmation")
            if not str(row.get("wallet_history_url") or "").startswith("https://"):
                errors.append(f"receive[{index}] wallet_received lacks public wallet history URL")
            if not HEX_SHA256_RE.fullmatch(str(row.get("wallet_history_sha256") or "")):
                errors.append(f"receive[{index}] wallet_received lacks wallet history digest")
            if len(wallet_history_evidence(row)) < len(txids):
                errors.append(f"receive[{index}] wallet_received lacks evidence for every transaction")
        if status == "settled":
            try:
                amount = float(row.get("amount_received") or 0)
                confirmations = int(row.get("confirmations"))
            except Exception:
                amount = 0
                confirmations = -1
            if amount <= 0 or confirmations < 0 or not str(row.get("txid") or "").strip() or not evidence(row):
                errors.append(f"receive[{index}] settled without positive amount, txid, confirmations and evidence")
        for field_path, timestamp in iter_timestamps(row, f"receive[{index}]"):
            parsed = parse_timestamp(timestamp)
            if parsed is None:
                errors.append(f"{field_path} is not a valid timezone-aware timestamp")
            elif parsed > now + future_skew:
                errors.append(f"{field_path} is in the future")

    for field_path, timestamp in iter_timestamps({k: v for k, v in receive.items() if k != "entries"}, "receive"):
        parsed = parse_timestamp(timestamp)
        if parsed is None:
            errors.append(f"{field_path} is not a valid timezone-aware timestamp")
        elif parsed > now + future_skew:
            errors.append(f"{field_path} is in the future")
    return errors, valid_rows


def validate_rustchain(entries: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    by_key = {str(row.get("bounty_key") or ""): row for row in entries}
    legacy = [
        row for row in entries
        if str(row.get("bounty_key") or "") == "unknown|rustchain/rustchain|254|idx21"
        or (str(row.get("repo") or "").lower() == "rustchain/rustchain" and str(row.get("issue_or_pr") or "") == "254")
    ]
    if legacy:
        errors.append("legacy RustChain USD/Polygon entry still exists")
    all_transaction_ids: list[str] = []
    for bounty_key, amount in RUSTCHAIN_EXPECTED.items():
        row = by_key.get(bounty_key)
        if not row:
            errors.append(f"missing canonical RustChain entry {bounty_key}")
            continue
        try:
            recorded = float(row.get("provider_confirmed_amount") or 0)
        except Exception:
            recorded = 0
        try:
            received_amount = float(row.get("amount_received") or 0)
        except Exception:
            received_amount = 0
        if (
            row.get("reward_asset") != "RTC"
            or row.get("expected_currency") != "RTC"
            or row.get("chain") != "rustchain"
            or row.get("network") != "rustchain-native"
            or row.get("receive_address") != RUSTCHAIN_WALLET
            or row.get("status") != "wallet_received"
            or abs(recorded - amount) > 0.0000001
            or abs(received_amount - amount) > 0.0000001
            or row.get("financial_write_authority") != RUSTCHAIN_AUTHORITY
            or row.get("confirmation_status") != "confirmed_immutable_ledger"
            or row.get("bybit_route_status") != "conversion_pending"
            or row.get("wise_route_status") != "conversion_pending"
        ):
            errors.append(f"canonical RustChain semantics disagree for {bounty_key}")
        txids = transaction_ids(row)
        expected_count = 4 if bounty_key.endswith("|254") else 1
        if len(txids) != expected_count or not all(HEX_TXID_RE.fullmatch(txid) for txid in txids):
            errors.append(f"RustChain {bounty_key} transaction evidence count is invalid")
        if bounty_key.endswith("|254"):
            if row.get("txid") not in {None, ""}:
                errors.append(f"RustChain {bounty_key} must keep scalar txid empty for multi-transaction receipt")
        elif row.get("txid") != txids[0] if txids else True:
            errors.append(f"RustChain {bounty_key} scalar txid disagrees with transaction list")
        if len(wallet_history_evidence(row)) < expected_count:
            errors.append(f"RustChain {bounty_key} lacks public wallet-history evidence")
        if not str(row.get("wallet_history_url") or "").startswith("https://rustchain.org/wallet/history"):
            errors.append(f"RustChain {bounty_key} does not use the official wallet history endpoint")
        if any(not str(item.get("source_url") or "").startswith("https://rustchain.org/wallet/history") for item in wallet_history_evidence(row)):
            errors.append(f"RustChain {bounty_key} contains non-official wallet-history evidence")
        all_transaction_ids.extend(txids)
    if len(all_transaction_ids) != 6 or len(set(all_transaction_ids)) != 6:
        errors.append("RustChain wallet receipts do not contain exactly six unique transactions")
    return errors


def validate_write_authority(entries: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for index, row in enumerate(entries):
        key = str(row.get("bounty_key") or "")
        authority = str(row.get("financial_write_authority") or "")
        status = str(row.get("status") or "")
        if "merged_pending" in status:
            errors.append(f"receive[{index}] uses non-canonical merged_pending status")
        if not authority:
            continue
        expected_id = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        if str(row.get("ledger_id") or "") != expected_id:
            errors.append(f"receive[{index}] authoritative ledger_id is not deterministic")
        provider = row.get("provider_evidence")
        if not isinstance(provider, list) or any(not isinstance(item, dict) for item in provider):
            errors.append(f"receive[{index}] authoritative provider_evidence is not structured")
        if status in {"provider_confirmed", "wallet_received", "settled"} and authority not in {RUSTCHAIN_AUTHORITY}:
            errors.append(f"receive[{index}] unsupported writer promoted financial state")
    return errors


def validate_realized(
    rows: list[dict[str, Any]],
    *,
    now: datetime,
    future_skew: timedelta,
) -> list[str]:
    errors: list[str] = []
    for index, row in enumerate(rows, 1):
        if str(row.get("type") or "settlement") != "settlement":
            errors.append(f"realized line {index} is not a settlement")
        try:
            amount = float(row.get("amount_usd") or 0)
        except Exception:
            amount = 0
        if amount <= 0:
            errors.append(f"realized line {index} has non-positive amount_usd")
        if not str(row.get("txid") or "").strip() or not evidence(row):
            errors.append(f"realized line {index} lacks transaction/provider evidence")
        if str(row.get("currency") or "").upper() == "RTC" and not row.get("conversion_evidence"):
            errors.append(f"realized line {index} treats RTC as USD without conversion evidence")
        for field_path, timestamp in iter_timestamps(row, f"realized[{index}]"):
            parsed = parse_timestamp(timestamp)
            if parsed is None:
                errors.append(f"{field_path} is not a valid timezone-aware timestamp")
            elif parsed > now + future_skew:
                errors.append(f"{field_path} is in the future")
    return errors


def numeric_values(value: Any, keys: set[str]) -> Iterable[tuple[str, float]]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in keys and isinstance(child, (int, float)) and not isinstance(child, bool):
                yield key, float(child)
            yield from numeric_values(child, keys)
    elif isinstance(value, list):
        for child in value:
            yield from numeric_values(child, keys)


def recent_reports(root: Path, now: datetime, max_age: timedelta) -> list[Path]:
    paths: list[Path] = []
    for directory in (root / "logs/capital_cycles", root / "data/aro/reports", root / "data/orchestrator"):
        if not directory.exists():
            continue
        for path in directory.glob("*.json"):
            try:
                modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
            age = now - modified
            if -timedelta(minutes=5) <= age <= max_age:
                paths.append(path)
    return sorted(paths, key=lambda path: path.stat().st_mtime, reverse=True)[:40]


def validate_reports(
    root: Path,
    entries: list[dict[str, Any]],
    realized: list[dict[str, Any]],
    *,
    now: datetime,
    future_skew: timedelta,
    max_age: timedelta,
    receive_mtime: float,
) -> list[str]:
    errors: list[str] = []
    status_counts = Counter(str(row.get("status") or "unknown") for row in entries)
    blocked_count = sum(count for status, count in status_counts.items() if status.startswith("blocked"))
    realized_usd = sum(float(row.get("amount_usd") or 0) for row in realized)
    expected_counts = {
        "total_entries": float(len(entries)),
        "entry_count": float(len(entries)),
        "realized_records_count": float(len(realized)),
        "settled_count": float(status_counts.get("settled", 0)),
        "active_submitted_prs": float(status_counts.get("submitted", 0)),
        "blocked_candidates": float(blocked_count),
    }
    for path in recent_reports(root, now, max_age):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            errors.append(f"recent financial report {path.name} is invalid JSON")
            continue
        if not isinstance(payload, dict):
            continue
        for key in ("timestamp", "generated_at", "created_at", "updated_at"):
            if key not in payload:
                continue
            parsed = parse_timestamp(payload[key])
            if parsed is None:
                errors.append(f"recent report {path.name} has invalid {key}")
            elif parsed > now + future_skew:
                errors.append(f"recent report {path.name} has future {key}")
        for key, value in numeric_values(payload, {"realized_revenue_usd"}):
            if abs(value - realized_usd) > 0.000001:
                errors.append(f"recent report {path.name} {key} disagrees with realized ledger")
        try:
            report_after_ledger = path.stat().st_mtime >= receive_mtime
        except OSError:
            report_after_ledger = False
        if report_after_ledger:
            for key, value in numeric_values(payload, set(expected_counts)):
                if abs(value - expected_counts[key]) > 0.000001:
                    errors.append(f"recent report {path.name} {key}={value:g} disagrees with canonical ledger {expected_counts[key]:g}")
    return errors


def validate_sidecar(root: Path, ledger_path: Path, entries: list[dict[str, Any]]) -> list[str]:
    path = root / "data/aro/rustchain_reconciliation.json"
    try:
        sidecar = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"RustChain reconciliation sidecar invalid: {type(exc).__name__}"]
    errors: list[str] = []
    if sidecar.get("status") != "verified_wallet_history" or sidecar.get("source_revision") != RUSTCHAIN_AUTHORITY:
        errors.append("RustChain reconciliation is not verified wallet history v2")
    rustchain_rows = [row for row in entries if str(row.get("bounty_key") or "") in RUSTCHAIN_EXPECTED]
    rustchain_rows.sort(key=lambda row: str(row.get("bounty_key") or ""))
    actual_hash = hashlib.sha256(json.dumps(rustchain_rows, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    if sidecar.get("rustchain_entries_sha256") != actual_hash:
        errors.append("RustChain reconciliation entry hash is stale")
    provider = sidecar.get("provider_confirmed_total") or {}
    received = sidecar.get("wallet_received_total") or {}
    settled = sidecar.get("settled_total") or {}
    try:
        provider_amount = float(provider.get("amount"))
        provider_count = int(provider.get("entry_count"))
        received_amount = float(received.get("amount"))
        received_count = int(received.get("entry_count"))
        received_transactions = int(received.get("transaction_count"))
        settled_amount = float(settled.get("amount"))
        settled_count = int(settled.get("entry_count"))
    except Exception:
        errors.append("RustChain sidecar totals are invalid")
    else:
        if provider.get("asset") != "RTC" or abs(provider_amount - 14.0) > 0.000001 or provider_count != 3:
            errors.append("RustChain provider-confirmed sidecar total disagrees with evidence")
        if received.get("asset") != "RTC" or abs(received_amount - 14.0) > 0.000001 or received_count != 3 or received_transactions != 6:
            errors.append("RustChain wallet-received sidecar total disagrees with wallet history")
        if settled.get("asset") != "RTC" or settled_amount != 0 or settled_count != 0:
            errors.append("RustChain sidecar incorrectly reports settlement")
    if sidecar.get("bybit_route_status") != "conversion_pending" or sidecar.get("wise_route_status") != "conversion_pending":
        errors.append("RustChain sidecar incorrectly treats a conversion route as receipt eligibility")
    if sidecar.get("realized_revenue_written") is not False or sidecar.get("direct_transfer_performed") is not False:
        errors.append("RustChain sidecar claims an unverified realization or transfer")
    canonical_rows = rustchain_rows
    if len(canonical_rows) != 3:
        errors.append("RustChain sidecar does not map to exactly three canonical entries")
    return errors


def validate_authoritative_manifest(root: Path, ledger_path: Path, realized_path: Path) -> list[str]:
    authority = authority_directory(root)
    manifest_path = authority / "authoritative_manifest.json"
    ledger_snapshot = authority / "authoritative_bounty_receive_ledger.json"
    realized_snapshot = authority / "authoritative_realized_revenue_ledger.jsonl"
    if not manifest_path.exists():
        return ["authoritative manifest missing"] if root.resolve() == PRODUCTION_ROOT else []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"authoritative manifest invalid: {type(exc).__name__}"]
    try:
        ledger_snapshot_bytes = ledger_snapshot.read_bytes()
        realized_snapshot_bytes = realized_snapshot.read_bytes()
    except Exception as exc:
        return [f"authoritative snapshot missing or unreadable: {type(exc).__name__}"]
    expected_ledger = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
    expected_realized = hashlib.sha256(realized_path.read_bytes() if realized_path.exists() else b"").hexdigest()
    saved_ledger = hashlib.sha256(ledger_snapshot_bytes).hexdigest()
    saved_realized = hashlib.sha256(realized_snapshot_bytes).hexdigest()
    errors: list[str] = []
    if manifest.get("bounty_receive_ledger_sha256") != saved_ledger:
        errors.append("authoritative bounty snapshot hash disagrees with manifest")
    if manifest.get("realized_revenue_ledger_sha256") != saved_realized:
        errors.append("authoritative realized snapshot hash disagrees with manifest")
    if manifest.get("bounty_receive_ledger_sha256") != expected_ledger:
        errors.append("canonical bounty ledger differs from authoritative snapshot")
    if manifest.get("realized_revenue_ledger_sha256") != expected_realized:
        errors.append("realized revenue ledger differs from authoritative snapshot")
    return errors


def write_state(root: Path, errors: list[str], now: datetime) -> None:
    path = root / "state/financial_ledger_semantic_validation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "checked_at": now.isoformat(),
        "status": "invalid_fail_closed" if errors else "valid",
        "error_count": len(errors),
        "errors": errors[:200],
    }
    temp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    os.chmod(temp, 0o600)
    os.replace(temp, path)


def validate(
    root: Path = DEFAULT_ROOT,
    *,
    now: datetime | None = None,
    future_skew_seconds: int = FUTURE_SKEW_SECONDS,
    report_max_age_seconds: int = REPORT_MAX_AGE_SECONDS,
) -> list[str]:
    now = now or utcnow()
    future_skew = timedelta(seconds=future_skew_seconds)
    ledger_path = root / "data/aro/bounty_receive_ledger.json"
    realized_path = root / "data/aro/realized_revenue_ledger.jsonl"
    receive, errors = load_receive(ledger_path)
    if receive is None:
        return errors
    receive_errors, entries = validate_receive(receive, now=now, future_skew=future_skew)
    errors.extend(receive_errors)
    errors.extend(validate_rustchain(entries))
    errors.extend(validate_write_authority(entries))
    realized = realized_records(realized_path, errors)
    errors.extend(validate_realized(realized, now=now, future_skew=future_skew))
    try:
        receive_mtime = ledger_path.stat().st_mtime
    except OSError:
        receive_mtime = 0
    errors.extend(
        validate_reports(
            root,
            entries,
            realized,
            now=now,
            future_skew=future_skew,
            max_age=timedelta(seconds=report_max_age_seconds),
            receive_mtime=receive_mtime,
        )
    )
    errors.extend(validate_sidecar(root, ledger_path, entries))
    errors.extend(validate_authoritative_manifest(root, ledger_path, realized_path))
    return list(dict.fromkeys(errors))


def notify(errors: list[str]) -> None:
    os.environ["AGENTIC_NOTIFY_TEXT"] = "Ledger financeiro bloqueado: " + "; ".join(errors[:5])
    sys.path[:0] = ["/Agentic/internal", "/Agentic/scripts", "/usr/local/lib/agentic"]
    try:
        import telegram_bridge as bridge

        state = bridge.load_state()
        bridge.maybe_critical(state, "financial_ledger_invalid", os.environ["AGENTIC_NOTIFY_TEXT"], 21600)
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--notify", action="store_true")
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--authority-dir", default=os.environ.get("AGENTIC_LEDGER_AUTHORITY_DIR"))
    parser.add_argument("--future-skew-seconds", type=int, default=FUTURE_SKEW_SECONDS)
    parser.add_argument("--report-max-age-seconds", type=int, default=REPORT_MAX_AGE_SECONDS)
    args = parser.parse_args()
    if args.authority_dir:
        os.environ["AGENTIC_LEDGER_AUTHORITY_DIR"] = args.authority_dir
    now = utcnow()
    errors = validate(
        Path(args.root),
        now=now,
        future_skew_seconds=args.future_skew_seconds,
        report_max_age_seconds=args.report_max_age_seconds,
    )
    try:
        write_state(Path(args.root), errors, now)
    except Exception as exc:
        errors.append(f"semantic validation state could not be written: {type(exc).__name__}")
    if errors:
        for error in errors:
            print(f"LEDGER_INVALID {error}", file=sys.stderr)
        if args.notify:
            notify(errors)
        return 1
    print("LEDGER_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
