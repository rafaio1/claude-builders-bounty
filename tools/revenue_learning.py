"""Outcome-driven strategy learning for the revenue control plane.

Only terminal observations from allowlisted official adapters and confirmed
control-plane settlements are learnable. Opportunity estimates, opened PRs,
pending payments, and other nominal values never enter realized revenue.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

import revenue_db


OUTCOME_TYPES = frozenset(
    {"paid", "settled", "accepted", "merged", "duplicate", "informative", "rejected"}
)
ADAPTER_OUTCOMES = frozenset(
    {"accepted", "merged", "duplicate", "informative", "rejected"}
)
POSITIVE_OUTCOMES = frozenset({"paid", "settled", "accepted", "merged"})
SETTLEMENT_OUTCOMES = frozenset({"paid", "settled"})
REQUIRED_COST_CATEGORIES = frozenset({"compute", "api", "server"})
DEFAULT_LANES = frozenset({"build", "receivable"})
MIN_TERMINAL_OUTCOMES = 3
MAX_EXPLORATION_FRACTION = 0.20
MAX_CLOCK_SKEW = timedelta(minutes=5)

SAFE_AUTONOMOUS_ACTIONS = frozenset(
    {
        "discovery",
        "qualification",
        "code_prep",
        "test_prep",
        "pr_prep",
        "monitoring",
        "platform_submission",
    }
)
HUMAN_REQUIRED_CONDITIONS = frozenset(
    {
        "kyc",
        "legal_terms",
        "captcha",
        "mfa",
        "identity_account_creation",
        "spending",
        "withdrawal",
        "transfer",
        "live_trading_promotion",
    }
)
OFFICIAL_ADAPTER_HOSTS = {
    "github_api": frozenset({"api.github.com", "github.com", "www.github.com"}),
    "hackerone_api": frozenset(
        {"api.hackerone.com", "hackerone.com", "www.hackerone.com"}
    ),
    "official_platform_api": frozenset(
        host for hosts in revenue_db.OFFICIAL_PLATFORM_HOSTS.values() for host in hosts
    ),
}
ADAPTER_OUTCOME_ALLOWLIST = {
    "github_api": frozenset({"accepted", "merged", "rejected"}),
    "hackerone_api": frozenset({"accepted", "duplicate", "informative", "rejected"}),
    "official_platform_api": ADAPTER_OUTCOMES,
}
LANE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).astimezone(timezone.utc).isoformat()


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _lane(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not LANE_PATTERN.fullmatch(normalized):
        raise ValueError("invalid strategy lane")
    return normalized


def _digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _valid_digest(value: str) -> bool:
    return bool(SHA256_PATTERN.fullmatch(str(value or "").lower()))


def init_learning_schema(db_path: str | os.PathLike[str] | None = None) -> Path:
    """Create learning tables without changing the base revenue schema."""
    path = revenue_db.init_db(db_path)
    with revenue_db.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS strategy_outcomes (
                event_key TEXT PRIMARY KEY,
                lane TEXT NOT NULL,
                subject_key TEXT NOT NULL,
                outcome_type TEXT NOT NULL CHECK(outcome_type IN (
                    'paid', 'settled', 'accepted', 'merged',
                    'duplicate', 'informative', 'rejected'
                )),
                source_kind TEXT NOT NULL,
                source_event_id TEXT NOT NULL,
                evidence_url TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                realized_net_usd REAL CHECK(realized_net_usd IS NULL OR realized_net_usd >= 0),
                currency TEXT,
                details_json TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(source_kind, source_event_id, outcome_type)
            );

            CREATE INDEX IF NOT EXISTS idx_strategy_outcomes_lane_subject
            ON strategy_outcomes(lane, subject_key, observed_at);

            CREATE TABLE IF NOT EXISTS strategy_cost_events (
                event_key TEXT PRIMARY KEY,
                measurement_id TEXT NOT NULL UNIQUE,
                lane TEXT NOT NULL,
                category TEXT NOT NULL CHECK(category IN ('compute', 'api', 'server')),
                amount_usd REAL NOT NULL CHECK(amount_usd >= 0),
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                source_kind TEXT NOT NULL CHECK(source_kind IN (
                    'local_meter', 'provider_invoice', 'billing_api'
                )),
                evidence_ref TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                measured_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_strategy_costs_lane_period
            ON strategy_cost_events(lane, category, period_start, period_end);

            CREATE TABLE IF NOT EXISTS strategy_lane_stats (
                lane TEXT PRIMARY KEY,
                terminal_outcomes INTEGER NOT NULL,
                accepted_outcomes INTEGER NOT NULL,
                merged_outcomes INTEGER NOT NULL,
                settled_outcomes INTEGER NOT NULL,
                duplicate_outcomes INTEGER NOT NULL,
                informative_outcomes INTEGER NOT NULL,
                rejected_outcomes INTEGER NOT NULL,
                acceptance_conversion REAL NOT NULL,
                settlement_conversion REAL NOT NULL,
                realized_settlement_net_usd REAL NOT NULL,
                measured_cost_usd REAL NOT NULL,
                realized_profit_usd REAL,
                costs_known INTEGER NOT NULL CHECK(costs_known IN (0, 1)),
                profitable INTEGER CHECK(profitable IN (0, 1)),
                profitability_status TEXT NOT NULL,
                unknown_cost_categories_json TEXT NOT NULL,
                unconverted_currencies_json TEXT NOT NULL,
                decision TEXT NOT NULL,
                rationale TEXT NOT NULL,
                rank INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
    return path


def gate_action(
    action: str,
    *,
    conditions: Iterable[str] = (),
    official_scope_authorized: bool = False,
) -> dict[str, Any]:
    """Return an explicit autonomous/human gate; unknowns fail closed."""
    normalized_action = str(action or "").strip().lower()
    normalized_conditions = {str(item or "").strip().lower() for item in conditions}
    unknown_conditions = normalized_conditions - HUMAN_REQUIRED_CONDITIONS
    blockers = sorted(normalized_conditions & HUMAN_REQUIRED_CONDITIONS)
    if unknown_conditions:
        blockers.extend(f"unknown_condition:{item}" for item in sorted(unknown_conditions))
    if normalized_action not in SAFE_AUTONOMOUS_ACTIONS:
        blockers.append("unknown_action")
    if normalized_action == "platform_submission" and not official_scope_authorized:
        blockers.append("official_scope_authorization_missing")
    blockers = sorted(set(blockers))
    return {
        "action": normalized_action,
        "allowed": not blockers,
        "status": "autonomous" if not blockers else "human_required",
        "reasons": blockers,
    }


def _official_evidence_allowed(source_kind: str, outcome_type: str, evidence_url: str) -> bool:
    if outcome_type not in ADAPTER_OUTCOME_ALLOWLIST.get(source_kind, frozenset()):
        return False
    parsed = urlparse(evidence_url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    hostname = parsed.hostname.lower()
    hosts = OFFICIAL_ADAPTER_HOSTS.get(source_kind, frozenset())
    return any(hostname == host or hostname.endswith(f".{host}") for host in hosts)


def _insert_outcome(conn: Any, values: Mapping[str, Any]) -> bool:
    comparable = (
        "lane",
        "subject_key",
        "outcome_type",
        "source_kind",
        "source_event_id",
        "evidence_url",
        "payload_sha256",
        "observed_at",
        "realized_net_usd",
        "currency",
        "details_json",
    )
    existing = conn.execute(
        "SELECT * FROM strategy_outcomes WHERE event_key=?", (values["event_key"],)
    ).fetchone()
    if existing:
        if all(existing[key] == values.get(key) for key in comparable):
            return False
        raise ValueError(f"outcome idempotency conflict: {values['event_key']}")
    conn.execute(
        """INSERT INTO strategy_outcomes
           (event_key, lane, subject_key, outcome_type, source_kind,
            source_event_id, evidence_url, payload_sha256, observed_at,
            realized_net_usd, currency, details_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            values["event_key"],
            values["lane"],
            values["subject_key"],
            values["outcome_type"],
            values["source_kind"],
            values["source_event_id"],
            values["evidence_url"],
            values["payload_sha256"],
            values["observed_at"],
            values.get("realized_net_usd"),
            values.get("currency"),
            values.get("details_json"),
            _iso(),
        ),
    )
    return True


def record_verified_outcome(
    *,
    lane: str,
    subject_key: str,
    outcome_type: str,
    source_kind: str,
    source_event_id: str,
    evidence_url: str,
    payload_sha256: str,
    observed_at: str,
    db_path: str | os.PathLike[str] | None = None,
    details: Mapping[str, Any] | None = None,
) -> bool:
    """Record an official terminal observation, never a revenue amount.

    Paid/settled observations are deliberately rejected here; realized money
    can enter only through :func:`sync_confirmed_settlements`.
    """
    init_learning_schema(db_path)
    normalized_lane = _lane(lane)
    outcome = str(outcome_type or "").strip().lower()
    source = str(source_kind or "").strip().lower()
    subject = str(subject_key or "").strip()
    source_id = str(source_event_id or "").strip()
    digest = str(payload_sha256 or "").lower()
    observed = _parse_time(observed_at)
    if outcome not in ADAPTER_OUTCOMES:
        raise ValueError("paid and settled outcomes require confirmed settlement evidence")
    if not subject or not source_id:
        raise ValueError("subject_key and source_event_id are required")
    if not _valid_digest(digest):
        raise ValueError("payload_sha256 must be a lowercase SHA-256 digest")
    if observed is None or observed > _now() + MAX_CLOCK_SKEW:
        raise ValueError("invalid or future outcome timestamp")
    if not _official_evidence_allowed(source, outcome, evidence_url):
        raise ValueError("outcome evidence is not from an allowlisted official adapter")
    event_key = hashlib.sha256(f"{source}:{source_id}:{outcome}".encode()).hexdigest()
    values = {
        "event_key": event_key,
        "lane": normalized_lane,
        "subject_key": subject,
        "outcome_type": outcome,
        "source_kind": source,
        "source_event_id": source_id,
        "evidence_url": evidence_url,
        "payload_sha256": digest,
        "observed_at": _iso(observed),
        "realized_net_usd": 0.0,
        "currency": None,
        "details_json": json.dumps(dict(details or {}), sort_keys=True),
    }
    with revenue_db.connect(db_path, immediate=True) as conn:
        return _insert_outcome(conn, values)


def sync_confirmed_settlements(db_path: str | os.PathLike[str] | None = None) -> int:
    """Idempotently consume only fully confirmed, still-valid settlements."""
    init_learning_schema(db_path)
    with revenue_db.connect(db_path) as conn:
        rows = conn.execute(
            """SELECT s.*, w.lane, w.status AS work_order_status,
                      w.collector_alias AS work_order_collector,
                      w.opportunity_id, o.status AS opportunity_status
               FROM settlements AS s
               JOIN work_orders AS w ON w.id=s.work_order_id
               JOIN opportunities AS o ON o.id=w.opportunity_id
               WHERE s.status='confirmed'
                 AND w.status='completed'
                 AND o.status='settled'"""
        ).fetchall()
    inserted = 0
    for raw_row in rows:
        row = dict(raw_row)
        if not revenue_db._is_realized_settlement(row):
            continue
        currency = str(row.get("currency") or "").upper()
        net_amount = float(row["net_amount"])
        safe_payload = {
            "settlement_id": row["id"],
            "work_order_id": row["work_order_id"],
            "opportunity_id": row["opportunity_id"],
            "provider": row["provider"],
            "provider_verification_id": row["provider_verification_id"],
            "currency": currency,
            "net_amount": net_amount,
            "received_at": row["received_at"],
        }
        received = _parse_time(row["received_at"])
        if received is None:
            continue
        values = {
            "event_key": hashlib.sha256(f"settlement:{row['id']}".encode()).hexdigest(),
            "lane": _lane(row["lane"]),
            "subject_key": str(row["opportunity_id"]),
            "outcome_type": "settled",
            "source_kind": "control_plane_settlement",
            "source_event_id": str(row["id"]),
            "evidence_url": str(row["provider_verification_url"]),
            "payload_sha256": _digest(safe_payload),
            "observed_at": _iso(received),
            "realized_net_usd": net_amount if currency == "USD" else None,
            "currency": currency,
            "details_json": json.dumps(safe_payload, sort_keys=True),
        }
        with revenue_db.connect(db_path, immediate=True) as conn:
            inserted += int(_insert_outcome(conn, values))
    return inserted


def _cost_evidence_valid(source_kind: str, evidence_ref: str, digest: str) -> bool:
    if not _valid_digest(digest):
        return False
    if source_kind == "local_meter":
        path = Path(evidence_ref)
        if not path.is_absolute() or not path.is_file():
            return False
        return hashlib.sha256(path.read_bytes()).hexdigest() == digest
    if source_kind in {"provider_invoice", "billing_api"}:
        parsed = urlparse(evidence_ref)
        return parsed.scheme == "https" and bool(parsed.hostname)
    return False


def record_measured_cost(
    *,
    measurement_id: str,
    lane: str,
    category: str,
    amount_usd: float,
    period_start: str,
    period_end: str,
    source_kind: str,
    evidence_ref: str,
    payload_sha256: str,
    measured_at: str,
    db_path: str | os.PathLike[str] | None = None,
) -> bool:
    """Persist one measured USD cost period with overlap and replay guards."""
    init_learning_schema(db_path)
    normalized_lane = _lane(lane)
    normalized_category = str(category or "").strip().lower()
    normalized_source = str(source_kind or "").strip().lower()
    measurement = str(measurement_id or "").strip()
    start = _parse_time(period_start)
    end = _parse_time(period_end)
    measured = _parse_time(measured_at)
    try:
        amount = float(amount_usd)
    except (TypeError, ValueError) as error:
        raise ValueError("amount_usd must be numeric") from error
    if not measurement or normalized_category not in REQUIRED_COST_CATEGORIES:
        raise ValueError("measurement_id and a known cost category are required")
    if not math.isfinite(amount) or amount < 0:
        raise ValueError("amount_usd must be finite and non-negative")
    if start is None or end is None or measured is None or end <= start:
        raise ValueError("cost period and measurement timestamps are invalid")
    if measured < end - MAX_CLOCK_SKEW or measured > _now() + MAX_CLOCK_SKEW:
        raise ValueError("measured_at must be at or after the cost period")
    digest = str(payload_sha256 or "").lower()
    if not _cost_evidence_valid(normalized_source, evidence_ref, digest):
        raise ValueError("cost evidence is missing, untrusted, or does not match its digest")
    event_key = hashlib.sha256(f"cost:{measurement}".encode()).hexdigest()
    values = {
        "event_key": event_key,
        "measurement_id": measurement,
        "lane": normalized_lane,
        "category": normalized_category,
        "amount_usd": amount,
        "period_start": _iso(start),
        "period_end": _iso(end),
        "source_kind": normalized_source,
        "evidence_ref": evidence_ref,
        "payload_sha256": digest,
        "measured_at": _iso(measured),
    }
    comparable = tuple(values)
    with revenue_db.connect(db_path, immediate=True) as conn:
        existing = conn.execute(
            "SELECT * FROM strategy_cost_events WHERE event_key=?", (event_key,)
        ).fetchone()
        if existing:
            if all(existing[key] == values[key] for key in comparable):
                return False
            raise ValueError(f"cost idempotency conflict: {event_key}")
        overlap = conn.execute(
            """SELECT measurement_id FROM strategy_cost_events
               WHERE lane=? AND category=?
                 AND period_start < ? AND period_end > ?
               LIMIT 1""",
            (normalized_lane, normalized_category, values["period_end"], values["period_start"]),
        ).fetchone()
        if overlap:
            raise ValueError(f"overlapping cost measurement: {overlap['measurement_id']}")
        conn.execute(
            """INSERT INTO strategy_cost_events
               (event_key, measurement_id, lane, category, amount_usd,
                period_start, period_end, source_kind, evidence_ref,
                payload_sha256, measured_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            tuple(values[key] for key in comparable) + (_iso(),),
        )
    return True


def _interval_covers(rows: list[Mapping[str, Any]], start: datetime, end: datetime) -> bool:
    intervals = sorted(
        (_parse_time(row["period_start"]), _parse_time(row["period_end"])) for row in rows
    )
    cursor = start
    for interval_start, interval_end in intervals:
        if interval_start is None or interval_end is None or interval_end < cursor:
            continue
        if interval_start > cursor:
            return False
        cursor = max(cursor, interval_end)
        if cursor >= end:
            return True
    return False


def _decision(stats: Mapping[str, Any]) -> tuple[str, str]:
    terminal = int(stats["terminal_outcomes"])
    acceptance = float(stats["acceptance_conversion"])
    settlement = float(stats["settlement_conversion"])
    profitability = stats["profitability_status"]
    if profitability == "profitable":
        return "active", "realized USD settlement net exceeds complete measured costs"
    if terminal >= MIN_TERMINAL_OUTCOMES and acceptance == 0:
        return "pause", "minimum sample reached with zero verified conversion"
    if terminal >= MIN_TERMINAL_OUTCOMES and (
        settlement == 0 or profitability == "not_profitable"
    ):
        return "pivot", "verified conversion or realized profit is insufficient"
    if int(stats["settled_outcomes"]) > 0 and profitability != "profitable":
        return "measure_costs", "settlement exists but profitability is not provable"
    return "explore", "insufficient verified terminal evidence"


def _compute_lane_stats(conn: Any, lane: str) -> dict[str, Any]:
    outcomes = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM strategy_outcomes WHERE lane=? ORDER BY observed_at, event_key",
            (lane,),
        ).fetchall()
    ]
    costs = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM strategy_cost_events WHERE lane=? ORDER BY period_start, event_key",
            (lane,),
        ).fetchall()
    ]
    precedence = {
        "rejected": 1,
        "informative": 2,
        "duplicate": 3,
        "accepted": 4,
        "merged": 5,
        "paid": 6,
        "settled": 7,
    }
    by_subject: dict[str, dict[str, Any]] = {}
    for outcome in outcomes:
        current = by_subject.get(outcome["subject_key"])
        key = (outcome["observed_at"], precedence[outcome["outcome_type"]])
        current_key = (
            (current["observed_at"], precedence[current["outcome_type"]])
            if current
            else None
        )
        if current is None or key > current_key:
            by_subject[outcome["subject_key"]] = outcome
    final_outcomes = list(by_subject.values())
    counts = {name: 0 for name in OUTCOME_TYPES}
    for outcome in final_outcomes:
        counts[outcome["outcome_type"]] += 1
    terminal = len(final_outcomes)
    accepted = sum(counts[name] for name in POSITIVE_OUTCOMES)
    settled = sum(counts[name] for name in SETTLEMENT_OUTCOMES)
    acceptance_conversion = round(accepted / terminal, 6) if terminal else 0.0
    settlement_conversion = round(settled / terminal, 6) if terminal else 0.0
    realized_revenue = round(
        sum(
            float(row["realized_net_usd"])
            for row in outcomes
            if row["realized_net_usd"] is not None
        ),
        6,
    )
    unconverted = sorted(
        {
            str(row["currency"])
            for row in outcomes
            if row["outcome_type"] in SETTLEMENT_OUTCOMES
            and row["realized_net_usd"] is None
            and row["currency"]
        }
    )
    measured_cost = round(sum(float(row["amount_usd"]) for row in costs), 6)
    unknown_categories = set(REQUIRED_COST_CATEGORIES)
    if outcomes:
        parsed_times = [_parse_time(row["observed_at"]) for row in outcomes]
        if any(value is None for value in parsed_times):
            raise ValueError(f"invalid learned outcome timestamp in lane {lane}")
        start = min(value for value in parsed_times if value is not None)
        end = max(value for value in parsed_times if value is not None)
        for category in REQUIRED_COST_CATEGORIES:
            category_rows = [row for row in costs if row["category"] == category]
            if category_rows and _interval_covers(category_rows, start, end):
                unknown_categories.discard(category)
    costs_known = bool(outcomes) and not unknown_categories
    realized_profit: float | None = None
    profitable: bool | None = None
    if unconverted:
        profitability_status = "unknown_currency_conversion"
    elif not costs_known:
        profitability_status = "unknown_costs"
    else:
        realized_profit = round(realized_revenue - measured_cost, 6)
        profitable = realized_revenue > measured_cost
        profitability_status = "profitable" if profitable else "not_profitable"
    stats = {
        "lane": lane,
        "terminal_outcomes": terminal,
        "accepted_outcomes": counts["accepted"],
        "merged_outcomes": counts["merged"],
        "settled_outcomes": settled,
        "duplicate_outcomes": counts["duplicate"],
        "informative_outcomes": counts["informative"],
        "rejected_outcomes": counts["rejected"],
        "acceptance_conversion": acceptance_conversion,
        "settlement_conversion": settlement_conversion,
        "realized_settlement_net_usd": realized_revenue,
        "measured_cost_usd": measured_cost,
        "realized_profit_usd": realized_profit,
        "costs_known": costs_known,
        "profitable": profitable,
        "profitability_status": profitability_status,
        "unknown_cost_categories": sorted(unknown_categories),
        "unconverted_currencies": unconverted,
    }
    stats["decision"], stats["rationale"] = _decision(stats)
    return stats


def refresh_strategy_stats(
    db_path: str | os.PathLike[str] | None = None,
) -> list[dict[str, Any]]:
    """Synchronize trusted outcomes and atomically rebuild persistent lane stats."""
    init_learning_schema(db_path)
    sync_confirmed_settlements(db_path)
    with revenue_db.connect(db_path, immediate=True) as conn:
        lanes = set(DEFAULT_LANES)
        lanes.update(row[0] for row in conn.execute("SELECT DISTINCT lane FROM opportunities"))
        lanes.update(
            row[0] for row in conn.execute("SELECT DISTINCT lane FROM strategy_outcomes")
        )
        lanes.update(
            row[0] for row in conn.execute("SELECT DISTINCT lane FROM strategy_cost_events")
        )
        stats = [_compute_lane_stats(conn, lane) for lane in sorted(lanes)]
        priority = {"active": 0, "measure_costs": 1, "explore": 2, "pivot": 3, "pause": 4}
        stats.sort(
            key=lambda item: (
                priority[item["decision"]],
                -float(item["realized_settlement_net_usd"]),
                -float(item["settlement_conversion"]),
                -float(item["acceptance_conversion"]),
                item["lane"],
            )
        )
        for rank, item in enumerate(stats, 1):
            item["rank"] = rank
            conn.execute(
                """INSERT INTO strategy_lane_stats
                   (lane, terminal_outcomes, accepted_outcomes, merged_outcomes,
                    settled_outcomes, duplicate_outcomes, informative_outcomes,
                    rejected_outcomes, acceptance_conversion, settlement_conversion,
                    realized_settlement_net_usd, measured_cost_usd,
                    realized_profit_usd, costs_known, profitable,
                    profitability_status, unknown_cost_categories_json,
                    unconverted_currencies_json, decision, rationale, rank, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(lane) DO UPDATE SET
                     terminal_outcomes=excluded.terminal_outcomes,
                     accepted_outcomes=excluded.accepted_outcomes,
                     merged_outcomes=excluded.merged_outcomes,
                     settled_outcomes=excluded.settled_outcomes,
                     duplicate_outcomes=excluded.duplicate_outcomes,
                     informative_outcomes=excluded.informative_outcomes,
                     rejected_outcomes=excluded.rejected_outcomes,
                     acceptance_conversion=excluded.acceptance_conversion,
                     settlement_conversion=excluded.settlement_conversion,
                     realized_settlement_net_usd=excluded.realized_settlement_net_usd,
                     measured_cost_usd=excluded.measured_cost_usd,
                     realized_profit_usd=excluded.realized_profit_usd,
                     costs_known=excluded.costs_known,
                     profitable=excluded.profitable,
                     profitability_status=excluded.profitability_status,
                     unknown_cost_categories_json=excluded.unknown_cost_categories_json,
                     unconverted_currencies_json=excluded.unconverted_currencies_json,
                     decision=excluded.decision,
                     rationale=excluded.rationale,
                     rank=excluded.rank,
                     updated_at=excluded.updated_at""",
                (
                    item["lane"],
                    item["terminal_outcomes"],
                    item["accepted_outcomes"],
                    item["merged_outcomes"],
                    item["settled_outcomes"],
                    item["duplicate_outcomes"],
                    item["informative_outcomes"],
                    item["rejected_outcomes"],
                    item["acceptance_conversion"],
                    item["settlement_conversion"],
                    item["realized_settlement_net_usd"],
                    item["measured_cost_usd"],
                    item["realized_profit_usd"],
                    int(item["costs_known"]),
                    None if item["profitable"] is None else int(item["profitable"]),
                    item["profitability_status"],
                    json.dumps(item["unknown_cost_categories"]),
                    json.dumps(item["unconverted_currencies"]),
                    item["decision"],
                    item["rationale"],
                    rank,
                    _iso(),
                ),
            )
    return stats


def exploration_slot_limit(max_orders: int) -> int:
    requested = max(0, min(int(max_orders), revenue_db.MAX_ACTIVE_WORK_ORDERS))
    return min(requested, math.ceil(requested * MAX_EXPLORATION_FRACTION)) if requested else 0


def _read_stats(db_path: str | os.PathLike[str] | None = None) -> list[dict[str, Any]]:
    with revenue_db.connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM strategy_lane_stats ORDER BY rank, lane").fetchall()
    result = []
    for raw in rows:
        item = dict(raw)
        item["costs_known"] = bool(item["costs_known"])
        item["profitable"] = None if item["profitable"] is None else bool(item["profitable"])
        item["unknown_cost_categories"] = json.loads(
            item.pop("unknown_cost_categories_json")
        )
        item["unconverted_currencies"] = json.loads(item.pop("unconverted_currencies_json"))
        result.append(item)
    return result


def strategy_snapshot(
    db_path: str | os.PathLike[str] | None = None,
    *,
    max_orders: int = revenue_db.MAX_ACTIVE_WORK_ORDERS,
    refresh: bool = True,
) -> dict[str, Any]:
    if refresh:
        refresh_strategy_stats(db_path)
    else:
        init_learning_schema(db_path)
    return {
        "generated_at": _iso(),
        "profitability_gate": (
            "realized confirmed USD settlement net must exceed fully covered measured "
            "compute, API, and server costs"
        ),
        "exploration_cap_fraction": MAX_EXPLORATION_FRACTION,
        "exploration_slots": exploration_slot_limit(max_orders),
        "lanes": _read_stats(db_path),
        "safe_autonomous_actions": sorted(SAFE_AUTONOMOUS_ACTIONS),
        "human_required_conditions": sorted(HUMAN_REQUIRED_CONDITIONS),
    }


def build_ranked_work_orders(
    db_path: str | os.PathLike[str] | None = None,
    *,
    max_orders: int = revenue_db.MAX_ACTIVE_WORK_ORDERS,
    build_alias: str = "revenue_generator",
    receivable_alias: str = "contador",
    supported_payout_methods: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Schedule proven lanes first and cap all unproven exploration globally."""
    refresh_strategy_stats(db_path)
    requested = max(0, min(int(max_orders), revenue_db.MAX_ACTIVE_WORK_ORDERS))
    supported = tuple(supported_payout_methods) if supported_payout_methods is not None else None
    stats = _read_stats(db_path)
    policy = {item["lane"]: item for item in stats}
    rank = {item["lane"]: item["rank"] for item in stats}
    placeholders = ",".join("?" for _ in revenue_db.ACTIVE_WORK_ORDER_STATES)
    with revenue_db.connect(db_path) as conn:
        active = conn.execute(
            f"""SELECT w.*, o.lane AS opportunity_lane
                FROM work_orders AS w
                JOIN opportunities AS o ON o.id=w.opportunity_id
                WHERE w.status IN ({placeholders})""",
            revenue_db.ACTIVE_WORK_ORDER_STATES,
        ).fetchall()
        candidates = [
            dict(row)
            for row in conn.execute(
                "SELECT id, lane, ev_net_per_hour FROM opportunities WHERE status='verified'"
            ).fetchall()
        ]
    slots = max(0, requested - len(active))
    exploration_limit = exploration_slot_limit(requested)
    exploration_active = sum(
        1
        for row in active
        if policy.get(row["opportunity_lane"], {}).get("decision", "explore") == "explore"
    )
    candidates.sort(
        key=lambda row: (
            rank.get(row["lane"], 999),
            -float(row["ev_net_per_hour"]),
            row["id"],
        )
    )
    for candidate in candidates:
        if slots <= 0:
            break
        lane_policy = policy.get(candidate["lane"], {"decision": "explore"})
        decision = lane_policy["decision"]
        if decision == "active":
            allowed = True
        elif decision == "explore" and exploration_active < exploration_limit:
            allowed = True
        else:
            allowed = False
        if not allowed:
            continue
        alias = build_alias if candidate["lane"] == "build" else receivable_alias
        created = revenue_db.create_work_order(
            candidate["id"],
            alias,
            db_path,
            supported_payout_methods=supported,
        )
        if created:
            slots -= 1
            if decision == "explore":
                exploration_active += 1
    with revenue_db.connect(db_path) as conn:
        rows = conn.execute(
            f"""SELECT * FROM work_orders
                WHERE status IN ({placeholders})
                ORDER BY ev_net_per_hour DESC, created_at ASC""",
            revenue_db.ACTIVE_WORK_ORDER_STATES,
        ).fetchall()
    return [dict(row) for row in rows]
