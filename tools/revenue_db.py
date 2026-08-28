"""Durable, fail-closed persistence for Revenue Control Plane v2.

The database is the only source used to create work orders.  Candidate files
may be imported explicitly, but imports always create unverified ``lead``
records.  A separate official-source validation step is required before a
lead can become eligible for work.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping
from urllib.parse import urlparse

import revenue_evidence
import revenue_settlement_evidence


DEFAULT_DB_PATH = Path("/Agentic/data/aro/revenue_control_plane_v2.db")
MAX_ACTIVE_WORK_ORDERS = 3
MAX_IMPORT_ITEMS = 100
MAX_REASONABLE_BOUNTY_USD = 100_000.0
MIN_REPO_HEALTH_SCORE = 0.50
MAX_EVIDENCE_AGE = timedelta(hours=24)
MAX_REPO_HEALTH_AGE = timedelta(days=7)
DEFAULT_MAX_AUTONOMOUS_BUILD_HOURS = 8.0
DEFAULT_MAX_RECEIVABLE_HOURS = 2.0
DEFAULT_MIN_EV_PER_HOUR_USD = 5.0
DEFAULT_EFFORT_OVERHEAD_MULTIPLIER = 1.5
DEFAULT_FIXED_OVERHEAD_HOURS = 1.0
MAX_SETTLEMENT_VERIFICATION_AGE = timedelta(hours=24)
MAX_ACTION_RECEIPT_AGE = timedelta(minutes=10)
MONETIZABLE_GITHUB_LOGIN = "rafaio1"
OWNERSHIP_EVIDENCE_KINDS = frozenset(
    {"github_assignment", "maintainer_assignment", "official_transfer"}
)

ALLOWED_IDENTITIES = frozenset(
    {"revenue_generator", "reviewer", "integrator", "contador", "collector"}
)
OFFICIAL_PLATFORM_HOSTS = {
    "algora": frozenset({"algora.io", "console.algora.io"}),
    "opire": frozenset({"opire.dev", "app.opire.dev"}),
}
DEFAULT_SUPPORTED_PAYOUT_METHODS = frozenset({"stripe"})
COLLECTOR_IDENTITIES = frozenset({"contador", "collector"})
SETTLEMENT_PROVIDER_HOSTS = {
    "stripe": frozenset({"stripe.com"}),
    "wise": frozenset({"wise.com"}),
    "bybit": frozenset({"bybit.com"}),
    "binance": frozenset({"binance.com"}),
    "paypal": frozenset({"paypal.com"}),
    "coinbase": frozenset({"coinbase.com"}),
}
ACTIVE_WORK_ORDER_STATES = (
    "queued",
    "in_progress",
    "under_review",
    "integration_ready",
    "published",
    "collection",
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def resolve_db_path(db_path: str | os.PathLike[str] | None = None) -> Path:
    """Return an absolute database path and reject relative runtime paths."""
    raw = db_path
    if raw is None:
        raw = os.environ.get("REVENUE_V2_DB_PATH") or DEFAULT_DB_PATH
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise ValueError("REVENUE_V2_DB_PATH must be absolute")
    return path.resolve()


@contextmanager
def connect(
    db_path: str | os.PathLike[str] | None = None,
    *,
    immediate: bool = False,
) -> Iterator[sqlite3.Connection]:
    path = resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    try:
        if immediate:
            conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: str | os.PathLike[str] | None = None) -> Path:
    """Create the v2 schema and DB-level concurrency guards idempotently."""
    path = resolve_db_path(db_path)
    active = ", ".join(f"'{state}'" for state in ACTIVE_WORK_ORDER_STATES)
    with connect(path) as conn:
        conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS identities (
                alias TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS repo_health (
                repo_key TEXT PRIMARY KEY,
                is_active INTEGER NOT NULL DEFAULT 0 CHECK(is_active IN (0, 1)),
                maintainer_active INTEGER NOT NULL DEFAULT 0 CHECK(maintainer_active IN (0, 1)),
                health_score REAL NOT NULL DEFAULT 0,
                checked_at TEXT,
                evidence_url TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS opportunities (
                id TEXT PRIMARY KEY,
                lane TEXT NOT NULL CHECK(lane IN ('build', 'receivable')),
                repo_key TEXT NOT NULL REFERENCES repo_health(repo_key),
                title TEXT NOT NULL,
                source_url TEXT NOT NULL UNIQUE,
                platform TEXT,
                official_reward_id TEXT,
                official_evidence_url TEXT,
                official_evidence_kind TEXT,
                evidence_checked_at TEXT,
                platform_state TEXT,
                linked_state TEXT,
                bounty_amount_usd REAL,
                currency TEXT,
                claim_path TEXT,
                payout_method TEXT,
                payer_identity TEXT,
                pr_author TEXT,
                ownership_assignee TEXT,
                ownership_evidence_url TEXT,
                ownership_evidence_kind TEXT,
                ownership_verified INTEGER NOT NULL DEFAULT 0 CHECK(ownership_verified IN (0, 1)),
                payout_eligible INTEGER NOT NULL DEFAULT 0 CHECK(payout_eligible IN (0, 1)),
                eligibility_verified INTEGER NOT NULL DEFAULT 0 CHECK(eligibility_verified IN (0, 1)),
                official_evidence_verified INTEGER NOT NULL DEFAULT 0 CHECK(official_evidence_verified IN (0, 1)),
                automation_eligible INTEGER NOT NULL DEFAULT 0 CHECK(automation_eligible IN (0, 1)),
                human_action_required INTEGER NOT NULL DEFAULT 1 CHECK(human_action_required IN (0, 1)),
                feasibility_verified INTEGER NOT NULL DEFAULT 0 CHECK(feasibility_verified IN (0, 1)),
                competition_checked INTEGER NOT NULL DEFAULT 0 CHECK(competition_checked IN (0, 1)),
                active_competitors INTEGER,
                estimated_hours REAL,
                conservative_hours REAL,
                payout_probability REAL,
                ev_net_per_hour REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'lead' CHECK(status IN (
                    'lead', 'verified', 'claimed', 'implementing', 'reviewed',
                    'submitted', 'accepted', 'payment_pending', 'settled',
                    'rejected', 'abandoned'
                )),
                metadata_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(platform, official_reward_id)
            );

            CREATE TABLE IF NOT EXISTS work_orders (
                id TEXT PRIMARY KEY,
                opportunity_id TEXT NOT NULL REFERENCES opportunities(id),
                lane TEXT NOT NULL CHECK(lane IN ('build', 'receivable')),
                actor_alias TEXT NOT NULL REFERENCES identities(alias),
                reviewer_alias TEXT REFERENCES identities(alias),
                integrator_alias TEXT REFERENCES identities(alias),
                collector_alias TEXT REFERENCES identities(alias),
                status TEXT NOT NULL CHECK(status IN (
                    'queued', 'in_progress', 'under_review', 'integration_ready',
                    'published', 'collection', 'completed', 'failed', 'cancelled'
                )),
                version INTEGER NOT NULL DEFAULT 0,
                ev_net_per_hour REAL NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT
            );

            CREATE UNIQUE INDEX IF NOT EXISTS uq_active_order_per_opportunity
            ON work_orders(opportunity_id)
            WHERE status IN ({active});

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                from_state TEXT,
                to_state TEXT,
                actor_alias TEXT,
                details_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settlements (
                id TEXT PRIMARY KEY,
                work_order_id TEXT NOT NULL REFERENCES work_orders(id),
                provider TEXT NOT NULL,
                transaction_id TEXT NOT NULL,
                provider_verification_url TEXT NOT NULL,
                provider_verification_id TEXT NOT NULL,
                provider_verified_at TEXT NOT NULL,
                verification_source TEXT,
                provider_payload_sha256 TEXT,
                provider_status TEXT,
                collector_alias TEXT NOT NULL REFERENCES identities(alias),
                currency TEXT NOT NULL,
                gross_amount REAL NOT NULL,
                fee_amount REAL NOT NULL,
                net_amount REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'confirmed', 'failed')),
                received_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(provider, transaction_id),
                UNIQUE(provider, provider_verification_id)
            );

            CREATE INDEX IF NOT EXISTS idx_opportunity_status_ev
            ON opportunities(status, ev_net_per_hour DESC);
            CREATE INDEX IF NOT EXISTS idx_work_order_status
            ON work_orders(status);
            CREATE INDEX IF NOT EXISTS idx_event_entity
            ON events(entity_type, entity_id);

            CREATE TRIGGER IF NOT EXISTS max_three_active_work_orders_insert
            BEFORE INSERT ON work_orders
            WHEN NEW.status IN ({active})
             AND (SELECT COUNT(*) FROM work_orders WHERE status IN ({active})) >= {MAX_ACTIVE_WORK_ORDERS}
            BEGIN
                SELECT RAISE(ABORT, 'maximum active work orders reached');
            END;

            CREATE TRIGGER IF NOT EXISTS max_three_active_work_orders_update
            BEFORE UPDATE OF status ON work_orders
            WHEN NEW.status IN ({active})
             AND OLD.status NOT IN ({active})
             AND (SELECT COUNT(*) FROM work_orders WHERE status IN ({active})) >= {MAX_ACTIVE_WORK_ORDERS}
            BEGIN
                SELECT RAISE(ABORT, 'maximum active work orders reached');
            END;
            """
        )
        existing_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(opportunities)").fetchall()
        }
        ownership_columns = {
            "pr_author": "TEXT",
            "ownership_assignee": "TEXT",
            "ownership_evidence_url": "TEXT",
            "ownership_evidence_kind": "TEXT",
            "ownership_verified": "INTEGER NOT NULL DEFAULT 0 CHECK(ownership_verified IN (0, 1))",
        }
        for column, declaration in ownership_columns.items():
            if column not in existing_columns:
                conn.execute(f"ALTER TABLE opportunities ADD COLUMN {column} {declaration}")
        work_order_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(work_orders)").fetchall()
        }
        if "version" not in work_order_columns:
            conn.execute(
                "ALTER TABLE work_orders ADD COLUMN version INTEGER NOT NULL DEFAULT 0"
            )
        settlement_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(settlements)").fetchall()
        }
        for column in (
            "verification_source",
            "provider_payload_sha256",
            "provider_status",
        ):
            if column not in settlement_columns:
                conn.execute(f"ALTER TABLE settlements ADD COLUMN {column} TEXT")

        action_columns = {
            "idempotency_key",
            "work_order_id",
            "action_type",
            "evidence_url",
            "receipt_id",
            "payload_sha256",
            "observed_at",
            "actor_alias",
            "expected_from_status",
            "work_order_version",
            "repo_key",
            "issue_number",
            "pr_number",
            "head_sha",
            "metadata_json",
            "consumed_at",
            "created_at",
        }
        action_table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='work_order_actions'"
        ).fetchone()
        if action_table_exists:
            actual_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(work_order_actions)").fetchall()
            }
            if actual_columns != action_columns:
                raise RuntimeError(
                    "work_order_actions schema mismatch; explicit migration required"
                )
        else:
            conn.execute(
                """CREATE TABLE work_order_actions (
                    idempotency_key TEXT PRIMARY KEY,
                    work_order_id TEXT NOT NULL REFERENCES work_orders(id),
                    action_type TEXT NOT NULL CHECK(action_type IN (
                        'claim_confirmed', 'tests_passed', 'review_approved',
                        'pr_published', 'delivery_accepted'
                    )),
                    evidence_url TEXT NOT NULL,
                    receipt_id TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    actor_alias TEXT NOT NULL REFERENCES identities(alias),
                    expected_from_status TEXT NOT NULL,
                    work_order_version INTEGER NOT NULL,
                    repo_key TEXT NOT NULL,
                    issue_number INTEGER,
                    pr_number INTEGER,
                    head_sha TEXT,
                    metadata_json TEXT NOT NULL,
                    consumed_at TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(action_type, receipt_id, work_order_id),
                    UNIQUE(work_order_id, action_type, work_order_version)
                )"""
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_woa_wo_id ON work_order_actions(work_order_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_woa_receipt ON work_order_actions(receipt_id)"
        )
        conn.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_woa_action_receipt
               ON work_order_actions(action_type, receipt_id, work_order_id)"""
        )
    return path


_WORK_ORDER_ACTION_ALLOWLIST = frozenset({
    "claim_confirmed",
    "tests_passed",
    "review_approved",
    "pr_published",
    "delivery_accepted",
})

def _action_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    result = dict(row)
    try:
        result["metadata"] = json.loads(result.get("metadata_json") or "{}")
    except json.JSONDecodeError:
        result["metadata"] = {}
    return result


def _prior_action_rows(
    conn: sqlite3.Connection,
    work_order_id: str,
 ) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """SELECT * FROM work_order_actions
           WHERE work_order_id=? AND consumed_at IS NOT NULL
           ORDER BY work_order_version ASC""",
        (work_order_id,),
    ).fetchall()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        action = _action_row(row)
        if action:
            result[str(action["action_type"])] = action
    return result


def verify_and_record_work_order_action(
    work_order_id: str,
    action_type: str,
    evidence_url: str,
    db_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Fetch official evidence and persist only the canonical verified facts."""
    if action_type not in _WORK_ORDER_ACTION_ALLOWLIST:
        raise ValueError("unsupported work-order action")
    if not isinstance(evidence_url, str) or not evidence_url.startswith("https://"):
        raise ValueError("evidence_url must use https")
    init_db(db_path)
    path = resolve_db_path(db_path)
    with connect(path) as conn:
        row = conn.execute(
            """SELECT w.id, w.status AS work_order_status,
                      w.version AS work_order_version, w.lane,
                      o.repo_key, o.source_url
               FROM work_orders AS w
               JOIN opportunities AS o ON o.id=w.opportunity_id
               WHERE w.id=?""",
            (work_order_id,),
        ).fetchone()
        if row is None:
            raise ValueError("work_order not found")
        context = dict(row)
        if context["lane"] != "build":
            raise ValueError("official action receipts apply only to build work orders")
        context["monetizable_login"] = MONETIZABLE_GITHUB_LOGIN
        prior_actions = _prior_action_rows(conn, work_order_id)

    verified = revenue_evidence.verify_github_evidence(
        action_type,
        evidence_url,
        context,
        prior_actions,
    )
    record = verified.record()
    expected_actor = revenue_evidence.ACTION_ACTORS[action_type]
    if record["actor_alias"] != expected_actor:
        raise ValueError("verified evidence actor mismatch")
    metadata_json = json.dumps(record["metadata"], sort_keys=True, separators=(",", ":"))
    idempotency_key = hashlib.sha256(
        (
            f"{work_order_id}:{action_type}:{record['work_order_version']}:"
            f"{record['payload_sha256']}"
        ).encode("utf-8")
    ).hexdigest()
    now = iso_now()

    with connect(path, immediate=True) as conn:
        current = conn.execute(
            """SELECT w.status, w.version, o.repo_key
               FROM work_orders AS w
               JOIN opportunities AS o ON o.id=w.opportunity_id
               WHERE w.id=?""",
            (work_order_id,),
        ).fetchone()
        if current is None:
            raise ValueError("work_order not found")
        if (
            current["status"] != record["expected_from_status"]
            or int(current["version"]) != int(record["work_order_version"])
            or str(current["repo_key"]).casefold() != str(record["repo_key"]).casefold()
        ):
            raise ValueError("work order changed while evidence was verified")
        if not conn.execute(
            "SELECT 1 FROM identities WHERE alias=?", (expected_actor,)
        ).fetchone():
            raise ValueError("derived actor identity is not bootstrapped")

        existing = conn.execute(
            """SELECT * FROM work_order_actions
               WHERE work_order_id=? AND action_type=? AND work_order_version=?""",
            (work_order_id, action_type, record["work_order_version"]),
        ).fetchone()
        if existing is not None:
            existing_action = _action_row(existing)
            if existing_action is None or existing_action["consumed_at"] is not None:
                raise ValueError("work-order action version already consumed")
            observed = _parse_timestamp(existing_action["observed_at"])
            if existing_action["payload_sha256"] != record["payload_sha256"]:
                if observed and utc_now() - observed <= MAX_ACTION_RECEIPT_AGE:
                    raise ValueError("conflicting official evidence for work-order version")
                conn.execute(
                    "DELETE FROM work_order_actions WHERE idempotency_key=?",
                    (existing_action["idempotency_key"],),
                )
            else:
                conn.execute(
                    """UPDATE work_order_actions
                       SET observed_at=?, created_at=?
                       WHERE idempotency_key=? AND consumed_at IS NULL""",
                    (record["observed_at"], now, existing_action["idempotency_key"]),
                )
                refreshed = conn.execute(
                    "SELECT * FROM work_order_actions WHERE idempotency_key=?",
                    (existing_action["idempotency_key"],),
                ).fetchone()
                result = _action_row(refreshed) or {}
                result["created"] = False
                return result

        conn.execute(
            """INSERT INTO work_order_actions
               (idempotency_key, work_order_id, action_type, evidence_url,
                receipt_id, payload_sha256, observed_at, actor_alias,
                expected_from_status, work_order_version, repo_key,
                issue_number, pr_number, head_sha, metadata_json,
                consumed_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)""",
            (
                idempotency_key,
                work_order_id,
                action_type,
                record["evidence_url"],
                record["receipt_id"],
                record["payload_sha256"],
                record["observed_at"],
                record["actor_alias"],
                record["expected_from_status"],
                record["work_order_version"],
                record["repo_key"],
                record["issue_number"],
                record["pr_number"],
                record["head_sha"],
                metadata_json,
                now,
            ),
        )
        result = _action_row(
            conn.execute(
                "SELECT * FROM work_order_actions WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
        ) or {}
        result["created"] = True
        return result


def get_work_order_action(
    idempotency_key: str,
    db_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any] | None:
    with connect(resolve_db_path(db_path)) as conn:
        row = conn.execute(
            "SELECT * FROM work_order_actions WHERE idempotency_key=?",
            (idempotency_key,),
        ).fetchone()
        return _action_row(row)


def find_work_order_action(
    work_order_id: str,
    action_type: str,
    actor_alias: str,
    db_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any] | None:
    """Return a fresh, unconsumed receipt bound to the current state/version."""
    if action_type not in _WORK_ORDER_ACTION_ALLOWLIST:
        return None
    if actor_alias not in ALLOWED_IDENTITIES:
        return None
    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute(
            """SELECT a.* FROM work_order_actions AS a
               JOIN work_orders AS w ON w.id=a.work_order_id
               WHERE a.work_order_id=? AND a.action_type=? AND a.actor_alias=?
                 AND a.expected_from_status=w.status
                 AND a.work_order_version=w.version
                 AND a.consumed_at IS NULL
               ORDER BY a.created_at DESC
               LIMIT 1""",
            (work_order_id, action_type, actor_alias),
        ).fetchone()
        action = _action_row(row)
        if action is None:
            return None
        observed = _parse_timestamp(action["observed_at"])
        if observed is None or not (
            timedelta(minutes=-5)
            <= utc_now() - observed
            <= MAX_ACTION_RECEIPT_AGE
        ):
            return None
        return action


def _event(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: str,
    event_type: str,
    from_state: str | None,
    to_state: str | None,
    actor_alias: str | None,
    details: Mapping[str, Any] | None = None,
) -> None:
    conn.execute(
        """INSERT INTO events
           (entity_type, entity_id, event_type, from_state, to_state,
            actor_alias, details_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            entity_type,
            entity_id,
            event_type,
            from_state,
            to_state,
            actor_alias,
            json.dumps(details, sort_keys=True) if details else None,
            iso_now(),
        ),
    )


def upsert_identity(
    alias: str,
    provider: str,
    db_path: str | os.PathLike[str] | None = None,
) -> bool:
    """Store an identity only when the alias is explicitly allowlisted."""
    if alias not in ALLOWED_IDENTITIES or not provider.strip():
        return False
    init_db(db_path)
    now = iso_now()
    with connect(db_path) as conn:
        conn.execute(
            """INSERT INTO identities(alias, provider, created_at, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(alias) DO UPDATE SET
                 provider=excluded.provider, updated_at=excluded.updated_at""",
            (alias, provider.strip(), now, now),
        )
    return True


def record_repo_health(
    repo_key: str,
    *,
    is_active: bool,
    maintainer_active: bool,
    health_score: float,
    checked_at: str,
    evidence_url: str,
    db_path: str | os.PathLike[str] | None = None,
) -> None:
    init_db(db_path)
    now = iso_now()
    with connect(db_path) as conn:
        conn.execute(
            """INSERT INTO repo_health
               (repo_key, is_active, maintainer_active, health_score, checked_at,
                evidence_url, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(repo_key) DO UPDATE SET
                 is_active=excluded.is_active,
                 maintainer_active=excluded.maintainer_active,
                 health_score=excluded.health_score,
                 checked_at=excluded.checked_at,
                 evidence_url=excluded.evidence_url,
                 updated_at=excluded.updated_at""",
            (
                repo_key,
                int(is_active),
                int(maintainer_active),
                float(health_score),
                checked_at,
                evidence_url,
                now,
            ),
        )


def create_lead(
    candidate: Mapping[str, Any],
    db_path: str | os.PathLike[str] | None = None,
) -> str:
    """Insert an unverified lead; candidate-provided verification is ignored."""
    init_db(db_path)
    opportunity_id = str(candidate.get("id") or "").strip()
    repo_key = str(candidate.get("repo_key") or candidate.get("repo") or "").strip()
    lane = str(candidate.get("lane") or "build").strip().lower()
    title = str(candidate.get("title") or "").strip()
    source_url = str(candidate.get("source_url") or candidate.get("url") or "").strip()
    if not opportunity_id or not repo_key or lane not in {"build", "receivable"}:
        raise ValueError("lead requires id, repo_key and a valid lane")
    if not title or not source_url:
        raise ValueError("lead requires title and source_url")
    now = iso_now()
    with connect(db_path) as conn:
        conn.execute(
            """INSERT INTO repo_health
               (repo_key, is_active, maintainer_active, health_score, updated_at)
               VALUES (?, 0, 0, 0, ?)
               ON CONFLICT(repo_key) DO NOTHING""",
            (repo_key, now),
        )
        conn.execute(
            """INSERT INTO opportunities
               (id, lane, repo_key, title, source_url, status, metadata_json,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'lead', ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 title=excluded.title,
                 metadata_json=excluded.metadata_json,
                 updated_at=excluded.updated_at""",
            (
                opportunity_id,
                lane,
                repo_key,
                title,
                source_url,
                json.dumps(dict(candidate), sort_keys=True),
                now,
                now,
            ),
        )
        _event(conn, "opportunity", opportunity_id, "lead_imported", None, "lead", None)
    return opportunity_id


def import_candidates(
    candidates_path: str | os.PathLike[str],
    db_path: str | os.PathLike[str] | None = None,
) -> int:
    """Explicit bounded import.  No default/global candidate file is read."""
    path = Path(candidates_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError("candidate import must be a JSON list")
    if len(payload) > MAX_IMPORT_ITEMS:
        raise ValueError(f"candidate import exceeds {MAX_IMPORT_ITEMS} items")
    count = 0
    for candidate in payload:
        if not isinstance(candidate, dict):
            raise ValueError("every imported candidate must be an object")
        create_lead(candidate, db_path)
        count += 1
    return count


VALIDATION_FIELDS = frozenset(
    {
        "platform",
        "official_reward_id",
        "official_evidence_url",
        "official_evidence_kind",
        "evidence_checked_at",
        "platform_state",
        "linked_state",
        "bounty_amount_usd",
        "currency",
        "claim_path",
        "payout_method",
        "payer_identity",
        "pr_author",
        "ownership_assignee",
        "ownership_evidence_url",
        "ownership_evidence_kind",
        "ownership_verified",
        "payout_eligible",
        "eligibility_verified",
        "official_evidence_verified",
        "automation_eligible",
        "human_action_required",
        "feasibility_verified",
        "competition_checked",
        "active_competitors",
        "estimated_hours",
        "payout_probability",
    }
)
BOOLEAN_VALIDATION_FIELDS = frozenset(
    {
        "payout_eligible",
        "eligibility_verified",
        "official_evidence_verified",
        "automation_eligible",
        "human_action_required",
        "feasibility_verified",
        "competition_checked",
    }
)


def record_official_validation(
    opportunity_id: str,
    validation: Mapping[str, Any],
    db_path: str | os.PathLike[str] | None = None,
) -> bool:
    """Record bounded official-source observations without changing status."""
    unknown = set(validation) - VALIDATION_FIELDS
    if unknown:
        raise ValueError(f"unknown validation fields: {sorted(unknown)}")
    assignments: list[str] = []
    values: list[Any] = []
    for key, value in validation.items():
        assignments.append(f"{key}=?")
        values.append(int(bool(value)) if key in BOOLEAN_VALIDATION_FIELDS else value)
    if not assignments:
        return False
    assignments.append("updated_at=?")
    values.append(iso_now())
    with connect(db_path, immediate=True) as conn:
        current = conn.execute(
            "SELECT status FROM opportunities WHERE id=?", (opportunity_id,)
        ).fetchone()
        if not current or current["status"] not in {"lead", "verified"}:
            return False
        status = current["status"]
        values.extend([opportunity_id, status])
        cursor = conn.execute(
            f"UPDATE opportunities SET {', '.join(assignments)} WHERE id=? AND status=?",
            values,
        )
        if cursor.rowcount:
            _event(
                conn,
                "opportunity",
                opportunity_id,
                "official_validation_recorded",
                status,
                status,
                None,
            )
            return True
    return False


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _host_matches_platform(platform: str, url: str) -> bool:
    hosts = OFFICIAL_PLATFORM_HOSTS.get(platform.lower())
    parsed = urlparse(url)
    if not hosts or parsed.scheme != "https" or not parsed.hostname:
        return False
    hostname = parsed.hostname.lower()
    return any(hostname == host or hostname.endswith(f".{host}") for host in hosts)


def _is_github_issue_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"github.com", "www.github.com"}:
        return False
    parts = [part for part in parsed.path.split("/") if part]
    return len(parts) == 4 and parts[2] == "issues" and parts[3].isdigit()


def _is_github_pull_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"github.com", "www.github.com"}:
        return False
    parts = [part for part in parsed.path.split("/") if part]
    return len(parts) == 4 and parts[2] == "pull" and parts[3].isdigit()


def _ownership_evidence_matches(opportunity: Mapping[str, Any]) -> bool:
    evidence_url = str(opportunity.get("ownership_evidence_url") or "")
    parsed = urlparse(evidence_url)
    parts = [part for part in parsed.path.split("/") if part]
    repo_key = str(opportunity.get("repo_key") or "").casefold()
    if parsed.scheme == "https" and parsed.hostname in {"github.com", "www.github.com"}:
        return (
            len(parts) >= 4
            and "/".join(parts[:2]).casefold() == repo_key
            and parts[2] in {"issues", "pull"}
            and parts[3].isdigit()
        )
    return (
        str(opportunity.get("ownership_evidence_kind") or "") == "official_transfer"
        and _host_matches_platform(str(opportunity.get("platform") or ""), evidence_url)
    )


def ownership_validation_reasons(opportunity: Mapping[str, Any]) -> list[str]:
    """Require our PR authorship or an explicit, officially verified transfer."""
    author = str(opportunity.get("pr_author") or "").casefold()
    if author == MONETIZABLE_GITHUB_LOGIN.casefold():
        return []
    kind = str(opportunity.get("ownership_evidence_kind") or "").lower()
    if kind in {"claim_comment", "slash_claim_comment"}:
        return ["claim_comment_not_ownership", "claimant_ownership_unverified"]
    explicitly_assigned = (
        bool(opportunity.get("ownership_verified"))
        and str(opportunity.get("ownership_assignee") or "").casefold()
        == MONETIZABLE_GITHUB_LOGIN.casefold()
        and kind in OWNERSHIP_EVIDENCE_KINDS
        and _ownership_evidence_matches(opportunity)
    )
    if explicitly_assigned:
        return []
    reasons = ["claimant_ownership_unverified"]
    if _is_github_pull_url(str(opportunity.get("source_url") or "")) and author:
        reasons.append("third_party_pr_author")
    return reasons


def _supported_payout_methods(methods: Iterable[str] | None) -> frozenset[str]:
    if methods is None:
        configured = os.environ.get("REVENUE_SUPPORTED_PAYOUT_METHODS")
        if configured:
            return frozenset(item.strip().lower() for item in configured.split(",") if item.strip())
        return DEFAULT_SUPPORTED_PAYOUT_METHODS
    return frozenset(str(item).strip().lower() for item in methods if str(item).strip())


PROFITABILITY_DEFAULTS = {
    "max_build_hours": DEFAULT_MAX_AUTONOMOUS_BUILD_HOURS,
    "max_receivable_hours": DEFAULT_MAX_RECEIVABLE_HOURS,
    "min_ev_per_hour_usd": DEFAULT_MIN_EV_PER_HOUR_USD,
    "overhead_multiplier": DEFAULT_EFFORT_OVERHEAD_MULTIPLIER,
    "fixed_overhead_hours": DEFAULT_FIXED_OVERHEAD_HOURS,
}
PROFITABILITY_ENV = {
    "max_build_hours": "REVENUE_MAX_AUTONOMOUS_BUILD_HOURS",
    "max_receivable_hours": "REVENUE_MAX_RECEIVABLE_HOURS",
    "min_ev_per_hour_usd": "REVENUE_MIN_EV_PER_HOUR_USD",
    "overhead_multiplier": "REVENUE_EFFORT_OVERHEAD_MULTIPLIER",
    "fixed_overhead_hours": "REVENUE_FIXED_OVERHEAD_HOURS",
}


def _profitability_config(overrides: Mapping[str, float] | None = None) -> dict[str, float]:
    unknown = set(overrides or {}) - set(PROFITABILITY_DEFAULTS)
    if unknown:
        raise ValueError(f"unknown profitability settings: {sorted(unknown)}")
    config: dict[str, float] = {}
    for key, default in PROFITABILITY_DEFAULTS.items():
        raw: Any = (overrides or {}).get(key)
        if raw is None:
            raw = os.environ.get(PROFITABILITY_ENV[key], default)
        try:
            value = float(raw)
        except (TypeError, ValueError) as error:
            raise ValueError(f"invalid profitability setting: {key}") from error
        if key == "fixed_overhead_hours":
            if value < 0:
                raise ValueError(f"profitability setting must be non-negative: {key}")
        elif value <= 0:
            raise ValueError(f"profitability setting must be positive: {key}")
        config[key] = value
    return config


def validate_opportunity(
    opportunity: Mapping[str, Any],
    repo_health: Mapping[str, Any] | None,
    *,
    supported_payout_methods: Iterable[str] | None = None,
    profitability: Mapping[str, float] | None = None,
    now: datetime | None = None,
) -> tuple[bool, list[str], float, float]:
    """Apply all scheduling gates and compute conservative hours/EV."""
    reasons: list[str] = []
    current = (now or utc_now()).astimezone(timezone.utc)
    lane = str(opportunity.get("lane") or "")
    profitability_settings = _profitability_config(profitability)

    if lane not in {"build", "receivable"}:
        reasons.append("invalid_lane")
    reasons.extend(ownership_validation_reasons(opportunity))
    if not repo_health:
        reasons.append("repo_health_missing")
    else:
        if not bool(repo_health.get("is_active")):
            reasons.append("repo_inactive")
        if not bool(repo_health.get("maintainer_active")):
            reasons.append("maintainer_inactive")
        try:
            score = float(repo_health.get("health_score") or 0)
        except (TypeError, ValueError):
            score = 0
        if score < MIN_REPO_HEALTH_SCORE:
            reasons.append("repo_health_below_threshold")
        repo_checked = _parse_timestamp(repo_health.get("checked_at"))
        if repo_checked is None or current - repo_checked > MAX_REPO_HEALTH_AGE:
            reasons.append("repo_health_stale")

    platform = str(opportunity.get("platform") or "").lower()
    evidence_url = str(opportunity.get("official_evidence_url") or "")
    source_url = str(opportunity.get("source_url") or "")
    if not bool(opportunity.get("official_evidence_verified")):
        reasons.append("official_evidence_unverified")
    if opportunity.get("official_evidence_kind") != "official_reward":
        reasons.append("official_reward_evidence_missing")
    if not evidence_url or evidence_url == source_url:
        reasons.append("evidence_not_distinct_from_source")
    elif not _host_matches_platform(platform, evidence_url):
        reasons.append("evidence_host_not_official")
    if not str(opportunity.get("official_reward_id") or "").strip():
        reasons.append("official_reward_id_missing")
    evidence_checked = _parse_timestamp(opportunity.get("evidence_checked_at"))
    if evidence_checked is None or current - evidence_checked > MAX_EVIDENCE_AGE:
        reasons.append("official_evidence_stale")
    if str(opportunity.get("platform_state") or "").lower() not in {"open", "active"}:
        reasons.append("platform_not_open")

    linked_state = str(opportunity.get("linked_state") or "").lower()
    if not bool(opportunity.get("automation_eligible")):
        reasons.append("automation_ineligible")
    if bool(opportunity.get("human_action_required")):
        reasons.append("human_action_required")
    if lane == "build":
        if not _is_github_issue_url(source_url):
            reasons.append("build_source_not_github_issue")
        if linked_state != "open":
            reasons.append("linked_issue_not_open")
        if not bool(opportunity.get("feasibility_verified")):
            reasons.append("feasibility_unverified")
        if not bool(opportunity.get("competition_checked")):
            reasons.append("competition_unchecked")
        try:
            competitors = int(opportunity.get("active_competitors"))
        except (TypeError, ValueError):
            competitors = -1
        if competitors != 0:
            reasons.append("active_or_unknown_competition")
    elif lane == "receivable" and linked_state not in {"merged", "accepted"}:
        reasons.append("delivery_not_accepted")

    if not bool(opportunity.get("eligibility_verified")):
        reasons.append("claimant_eligibility_unverified")
    if not bool(opportunity.get("payout_eligible")):
        reasons.append("payout_eligibility_unverified")
    if not str(opportunity.get("claim_path") or "").strip():
        reasons.append("claim_path_missing")
    if not str(opportunity.get("payer_identity") or "").strip():
        reasons.append("payer_identity_missing")
    payout_method = str(opportunity.get("payout_method") or "").lower()
    if payout_method not in _supported_payout_methods(supported_payout_methods):
        reasons.append("unsupported_payout_method")

    try:
        amount = float(opportunity.get("bounty_amount_usd") or 0)
    except (TypeError, ValueError):
        amount = 0
    if amount <= 0 or amount > MAX_REASONABLE_BOUNTY_USD:
        reasons.append("implausible_bounty_amount")
    if str(opportunity.get("currency") or "").upper() not in {"USD", "USDT", "USDC"}:
        reasons.append("unsupported_ev_currency")
    try:
        entered_hours = float(opportunity.get("estimated_hours") or 0)
    except (TypeError, ValueError):
        entered_hours = 0
    if entered_hours <= 0:
        reasons.append("estimated_hours_must_be_positive")
        conservative_hours = 0.0
    else:
        conservative_hours = round(
            entered_hours * profitability_settings["overhead_multiplier"]
            + profitability_settings["fixed_overhead_hours"],
            4,
        )
        effort_limit = (
            profitability_settings["max_build_hours"]
            if lane == "build"
            else profitability_settings["max_receivable_hours"]
        )
        if conservative_hours > effort_limit:
            reasons.append("autonomous_effort_exceeds_limit")
    try:
        probability = float(opportunity.get("payout_probability") or 0)
    except (TypeError, ValueError):
        probability = 0
    probability_cap = 0.50 if lane == "build" else 0.90
    probability = min(max(probability, 0), probability_cap)
    if probability <= 0:
        reasons.append("payout_probability_missing")
    ev_per_hour = (
        round(amount * probability / conservative_hours, 4)
        if amount > 0 and conservative_hours > 0
        else 0.0
    )
    if ev_per_hour < profitability_settings["min_ev_per_hour_usd"]:
        reasons.append("ev_below_floor")
    return not reasons, sorted(set(reasons)), conservative_hours, ev_per_hour


def get_opportunity(
    opportunity_id: str,
    db_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM opportunities WHERE id=?", (opportunity_id,)).fetchone()
        return dict(row) if row else None


def verify_opportunity(
    opportunity_id: str,
    db_path: str | os.PathLike[str] | None = None,
    *,
    supported_payout_methods: Iterable[str] | None = None,
    profitability: Mapping[str, float] | None = None,
) -> tuple[bool, list[str]]:
    """CAS-promote a lead only when every current hard gate passes."""
    init_db(db_path)
    with connect(db_path, immediate=True) as conn:
        row = conn.execute("SELECT * FROM opportunities WHERE id=?", (opportunity_id,)).fetchone()
        if not row:
            return False, ["opportunity_not_found"]
        opportunity = dict(row)
        repo_row = conn.execute(
            "SELECT * FROM repo_health WHERE repo_key=?", (opportunity["repo_key"],)
        ).fetchone()
        valid, reasons, hours, ev = validate_opportunity(
            opportunity,
            dict(repo_row) if repo_row else None,
            supported_payout_methods=supported_payout_methods,
            profitability=profitability,
        )
        if not valid:
            return False, reasons
        if opportunity["status"] == "verified":
            conn.execute(
                """UPDATE opportunities
                   SET conservative_hours=?, ev_net_per_hour=?, updated_at=?
                   WHERE id=? AND status='verified'""",
                (hours, ev, iso_now(), opportunity_id),
            )
            return True, []
        if opportunity["status"] != "lead":
            return False, ["invalid_verification_state"]
        cursor = conn.execute(
            """UPDATE opportunities
               SET status='verified', conservative_hours=?, ev_net_per_hour=?, updated_at=?
               WHERE id=? AND status='lead'""",
            (hours, ev, iso_now(), opportunity_id),
        )
        if cursor.rowcount != 1:
            return False, ["cas_conflict"]
        _event(
            conn,
            "opportunity",
            opportunity_id,
            "verified",
            "lead",
            "verified",
            None,
            {"conservative_hours": hours, "ev_net_per_hour": ev},
        )
        return True, []


def create_work_order(
    opportunity_id: str,
    actor_alias: str,
    db_path: str | os.PathLike[str] | None = None,
    *,
    supported_payout_methods: Iterable[str] | None = None,
    profitability: Mapping[str, float] | None = None,
) -> str | None:
    """Create one gated order atomically; DB triggers enforce the global cap."""
    if actor_alias not in ALLOWED_IDENTITIES:
        return None
    init_db(db_path)
    with connect(db_path, immediate=True) as conn:
        identity = conn.execute(
            "SELECT alias FROM identities WHERE alias=?", (actor_alias,)
        ).fetchone()
        if not identity:
            return None
        row = conn.execute("SELECT * FROM opportunities WHERE id=?", (opportunity_id,)).fetchone()
        if not row or row["status"] != "verified":
            return None
        opportunity = dict(row)
        repo_row = conn.execute(
            "SELECT * FROM repo_health WHERE repo_key=?", (opportunity["repo_key"],)
        ).fetchone()
        valid, reasons, hours, ev = validate_opportunity(
            opportunity,
            dict(repo_row) if repo_row else None,
            supported_payout_methods=supported_payout_methods,
            profitability=profitability,
        )
        if not valid:
            _event(
                conn,
                "opportunity",
                opportunity_id,
                "scheduling_rejected",
                "verified",
                "verified",
                actor_alias,
                {"reasons": reasons},
            )
            return None
        digest = hashlib.sha256(f"{opportunity['lane']}:{opportunity_id}".encode()).hexdigest()[:16]
        work_order_id = f"wo-{digest}"
        existing = conn.execute("SELECT id FROM work_orders WHERE id=?", (work_order_id,)).fetchone()
        if existing:
            return work_order_id
        initial_status = "queued" if opportunity["lane"] == "build" else "collection"
        try:
            conn.execute(
                """INSERT INTO work_orders
                   (id, opportunity_id, lane, actor_alias, collector_alias,
                    status, ev_net_per_hour, created_at, updated_at, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    work_order_id,
                    opportunity_id,
                    opportunity["lane"],
                    actor_alias,
                    actor_alias if opportunity["lane"] == "receivable" else None,
                    initial_status,
                    ev,
                    iso_now(),
                    iso_now(),
                    json.dumps({"conservative_hours": hours}, sort_keys=True),
                ),
            )
        except sqlite3.IntegrityError:
            return None
        next_opportunity_status = (
            "claimed" if opportunity["lane"] == "build" else "payment_pending"
        )
        cursor = conn.execute(
            "UPDATE opportunities SET status=?, updated_at=? WHERE id=? AND status='verified'",
            (next_opportunity_status, iso_now(), opportunity_id),
        )
        if cursor.rowcount != 1:
            raise sqlite3.IntegrityError("opportunity CAS conflict")
        _event(
            conn,
            "work_order",
            work_order_id,
            "created",
            None,
            initial_status,
            actor_alias,
            {"lane": opportunity["lane"], "opportunity_id": opportunity_id},
        )
        return work_order_id


def build_work_orders(
    db_path: str | os.PathLike[str] | None = None,
    *,
    max_orders: int = MAX_ACTIVE_WORK_ORDERS,
    build_alias: str = "revenue_generator",
    receivable_alias: str = "contador",
    supported_payout_methods: Iterable[str] | None = None,
    profitability: Mapping[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Read only verified SQLite rows, revalidate, and fill at most three slots."""
    init_db(db_path)
    requested = max(0, min(int(max_orders), MAX_ACTIVE_WORK_ORDERS))
    with connect(db_path) as conn:
        active_count = conn.execute(
            f"SELECT COUNT(*) FROM work_orders WHERE status IN ({','.join('?' for _ in ACTIVE_WORK_ORDER_STATES)})",
            ACTIVE_WORK_ORDER_STATES,
        ).fetchone()[0]
        candidates = conn.execute(
            """SELECT id, lane FROM opportunities
               WHERE status='verified'
               ORDER BY ev_net_per_hour DESC, created_at ASC"""
        ).fetchall()
    slots = max(0, min(requested, MAX_ACTIVE_WORK_ORDERS - int(active_count)))
    for candidate in candidates:
        if slots <= 0:
            break
        alias = build_alias if candidate["lane"] == "build" else receivable_alias
        if create_work_order(
            candidate["id"],
            alias,
            db_path,
            supported_payout_methods=supported_payout_methods,
            profitability=profitability,
        ):
            slots -= 1
    with connect(db_path) as conn:
        rows = conn.execute(
            f"""SELECT * FROM work_orders
                WHERE status IN ({','.join('?' for _ in ACTIVE_WORK_ORDER_STATES)})
                ORDER BY ev_net_per_hour DESC, created_at ASC""",
            ACTIVE_WORK_ORDER_STATES,
        ).fetchall()
        return [dict(row) for row in rows]


WORK_ORDER_TRANSITIONS = {
    "queued": frozenset({"in_progress", "cancelled"}),
    "in_progress": frozenset({"under_review", "failed", "cancelled"}),
    "under_review": frozenset({"integration_ready", "failed"}),
    "integration_ready": frozenset({"published", "failed"}),
    "published": frozenset({"completed", "failed"}),
    "collection": frozenset({"completed", "failed"}),
}

WORK_ORDER_RECEIPT_GATES = {
    ("queued", "in_progress"): (
        "claim_confirmed",
        frozenset({"revenue_generator"}),
    ),
    ("in_progress", "under_review"): (
        "tests_passed",
        frozenset({"revenue_generator"}),
    ),
    ("under_review", "integration_ready"): (
        "pr_published",
        frozenset({"integrator"}),
    ),
    ("integration_ready", "published"): (
        "review_approved",
        frozenset({"reviewer"}),
    ),
    ("published", "completed"): (
        "delivery_accepted",
        frozenset({"contador"}),
    ),
}

WORK_ORDER_OPPORTUNITY_TRANSITIONS = {
    ("queued", "in_progress"): ("claimed", "implementing"),
    ("under_review", "integration_ready"): ("implementing", "submitted"),
    ("integration_ready", "published"): ("submitted", "reviewed"),
    ("published", "completed"): ("reviewed", "accepted"),
}


def cas_transition_work_order(
    work_order_id: str,
    expected_status: str,
    new_status: str,
    actor_alias: str,
    db_path: str | os.PathLike[str] | None = None,
) -> bool:
    if actor_alias not in ALLOWED_IDENTITIES:
        return False
    if new_status not in WORK_ORDER_TRANSITIONS.get(expected_status, frozenset()):
        return False
    init_db(db_path)
    transition = (expected_status, new_status)
    with connect(db_path, immediate=True) as conn:
        if not conn.execute(
            "SELECT 1 FROM identities WHERE alias=?", (actor_alias,)
        ).fetchone():
            return False
        current = conn.execute(
            """SELECT w.status AS work_order_status, w.version AS work_order_version,
                      w.opportunity_id, w.lane,
                      o.status AS opportunity_status
               FROM work_orders AS w
               JOIN opportunities AS o ON o.id=w.opportunity_id
               WHERE w.id=?""",
            (work_order_id,),
        ).fetchone()
        if not current or current["work_order_status"] != expected_status:
            return False

        receipt_gate = WORK_ORDER_RECEIPT_GATES.get(transition)
        if receipt_gate:
            action_type, allowed_actors = receipt_gate
            if actor_alias not in allowed_actors:
                return False
            receipt = conn.execute(
                """SELECT * FROM work_order_actions
                   WHERE work_order_id=? AND action_type=? AND actor_alias=?
                     AND expected_from_status=? AND work_order_version=?
                     AND consumed_at IS NULL
                   LIMIT 1""",
                (
                    work_order_id,
                    action_type,
                    actor_alias,
                    expected_status,
                    current["work_order_version"],
                ),
            ).fetchone()
            if not receipt:
                return False
            observed = _parse_timestamp(receipt["observed_at"])
            if observed is None or not (
                timedelta(minutes=-5)
                <= utc_now() - observed
                <= MAX_ACTION_RECEIPT_AGE
            ):
                return False

        opportunity_transition = WORK_ORDER_OPPORTUNITY_TRANSITIONS.get(transition)
        if opportunity_transition:
            expected_opportunity_status, new_opportunity_status = opportunity_transition
            if current["opportunity_status"] != expected_opportunity_status:
                return False

        now = iso_now()
        cursor = conn.execute(
            """UPDATE work_orders
               SET status=?, version=version+1, updated_at=?
               WHERE id=? AND status=? AND version=?""",
            (
                new_status,
                now,
                work_order_id,
                expected_status,
                current["work_order_version"],
            ),
        )
        if cursor.rowcount != 1:
            return False
        if opportunity_transition:
            expected_opportunity_status, new_opportunity_status = opportunity_transition
            opportunity_cursor = conn.execute(
                """UPDATE opportunities SET status=?, updated_at=?
                   WHERE id=? AND status=?""",
                (
                    new_opportunity_status,
                    now,
                    current["opportunity_id"],
                    expected_opportunity_status,
                ),
            )
            if opportunity_cursor.rowcount != 1:
                raise sqlite3.IntegrityError("opportunity CAS conflict")
        if receipt_gate:
            consumed = conn.execute(
                """UPDATE work_order_actions SET consumed_at=?
                   WHERE idempotency_key=? AND consumed_at IS NULL""",
                (now, receipt["idempotency_key"]),
            )
            if consumed.rowcount != 1:
                raise sqlite3.IntegrityError("receipt consumption CAS conflict")
        if transition == ("published", "completed"):
            _event(
                conn,
                "opportunity",
                current["opportunity_id"],
                "platform_revalidation_required",
                "reviewed",
                "accepted",
                "contador",
                {
                    "acceptance_receipt_id": receipt["receipt_id"],
                    "acceptance_evidence_url": receipt["evidence_url"],
                    "reason": "merge_is_not_platform_payment_obligation",
                },
            )
        _event(
            conn,
            "work_order",
            work_order_id,
            "state_transition",
            expected_status,
            new_status,
            actor_alias,
        )
        return True


def get_work_order(
    work_order_id: str,
    db_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM work_orders WHERE id=?", (work_order_id,)).fetchone()
        return dict(row) if row else None


ALLOWED_SETTLEMENT_CURRENCIES = frozenset({"USD", "USDT", "USDC", "EUR", "GBP"})


def _provider_url_matches(provider: str, verification_url: str) -> bool:
    hosts = SETTLEMENT_PROVIDER_HOSTS.get(provider)
    parsed = urlparse(verification_url)
    if not hosts or parsed.scheme != "https" or not parsed.hostname:
        return False
    hostname = parsed.hostname.lower()
    return any(hostname == host or hostname.endswith(f".{host}") for host in hosts)


def _valid_provider_verification(
    provider: str,
    transaction_id: str,
    verification_url: str,
    verification_id: str,
    verified_at: str,
    *,
    reference_time: datetime | None = None,
) -> bool:
    provider = provider.lower()
    if provider not in SETTLEMENT_PROVIDER_HOSTS:
        return False
    if not transaction_id or not verification_id or verification_id != transaction_id:
        return False
    if not _provider_url_matches(provider, verification_url):
        return False
    parsed_url = urlparse(verification_url)
    if verification_id not in parsed_url.path and verification_id not in parsed_url.query:
        return False
    observed = _parse_timestamp(verified_at)
    reference = (reference_time or utc_now()).astimezone(timezone.utc)
    if observed is None:
        return False
    age = reference - observed
    return timedelta(minutes=-5) <= age <= MAX_SETTLEMENT_VERIFICATION_AGE


def verify_and_record_settlement(
    work_order_id: str,
    provider: str,
    transaction_id: str,
    db_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Confirm or revalidate live provider money against one collection lane."""
    init_db(db_path)
    path = resolve_db_path(db_path)
    normalized_provider = str(provider or "").casefold()
    normalized_transaction = str(transaction_id or "").strip()
    with connect(path) as conn:
        existing = conn.execute(
            "SELECT * FROM settlements WHERE provider=? AND transaction_id=?",
            (normalized_provider, normalized_transaction),
        ).fetchone()
        if existing is not None:
            if existing["work_order_id"] != work_order_id or existing["status"] != "confirmed":
                raise ValueError("provider transaction already bound elsewhere")
        row = conn.execute(
            """SELECT w.id, w.status AS work_order_status, w.lane,
                      w.collector_alias, w.version AS work_order_version,
                      o.id AS opportunity_id, o.status AS opportunity_status,
                      o.payout_method, o.currency, o.bounty_amount_usd,
                      o.official_reward_id, o.payer_identity
               FROM work_orders AS w
               JOIN opportunities AS o ON o.id=w.opportunity_id
               WHERE w.id=?""",
            (work_order_id,),
        ).fetchone()
        if row is None:
            raise ValueError("collection work order not found")
        context = dict(row)
        is_new_collection = (
            existing is None
            and context["work_order_status"] == "collection"
            and context["opportunity_status"] == "payment_pending"
        )
        is_confirmed_revalidation = (
            existing is not None
            and context["work_order_status"] == "completed"
            and context["opportunity_status"] == "settled"
        )
        if (
            context["lane"] != "receivable"
            or context["collector_alias"] != "contador"
            or str(context["payout_method"] or "").casefold() != normalized_provider
            or not (is_new_collection or is_confirmed_revalidation)
        ):
            raise ValueError("work order is not an eligible collection lane")

    destination_account = str(
        os.environ.get("STRIPE_DESTINATION_ACCOUNT_ID") or ""
    ).strip()
    verification_context = {
        "work_order_id": work_order_id,
        "official_reward_id": context["official_reward_id"],
        "payer_identity": context["payer_identity"],
        "expected_amount": context["bounty_amount_usd"],
        "expected_currency": context["currency"],
        "expected_destination": destination_account,
    }
    try:
        verified = revenue_settlement_evidence.verify_provider_settlement(
            normalized_provider,
            normalized_transaction,
            verification_context,
        ).record()
    except revenue_settlement_evidence.SettlementReversedError:
        if existing is None:
            raise
        now = iso_now()
        with connect(path, immediate=True) as conn:
            current = conn.execute(
                "SELECT * FROM settlements WHERE id=?", (existing["id"],)
            ).fetchone()
            if current is None or current["status"] != "confirmed":
                result = dict(current) if current is not None else {}
                result.update({"created": False, "reversed": True})
                return result
            active_count = int(
                conn.execute(
                    f"SELECT COUNT(*) FROM work_orders WHERE status IN ({','.join('?' for _ in ACTIVE_WORK_ORDER_STATES)})",
                    ACTIVE_WORK_ORDER_STATES,
                ).fetchone()[0]
            )
            reopened_status = (
                "collection" if active_count < MAX_ACTIVE_WORK_ORDERS else "failed"
            )
            conn.execute(
                """UPDATE settlements
                   SET status='failed', provider_status='reversed',
                       provider_verified_at=?, updated_at=?
                   WHERE id=? AND status='confirmed'""",
                (now, now, current["id"]),
            )
            conn.execute(
                """UPDATE work_orders
                   SET status=?, version=version+1, updated_at=?
                   WHERE id=? AND status='completed'""",
                (reopened_status, now, work_order_id),
            )
            conn.execute(
                """UPDATE opportunities SET status='payment_pending', updated_at=?
                   WHERE id=? AND status='settled'""",
                (now, context["opportunity_id"]),
            )
            _event(
                conn,
                "settlement",
                current["id"],
                "settlement_reversal_adjustment",
                "confirmed",
                "failed",
                "contador",
                {
                    "currency": current["currency"],
                    "net_adjustment": -float(current["net_amount"]),
                    "work_order_status": reopened_status,
                },
            )
            result = dict(
                conn.execute(
                    "SELECT * FROM settlements WHERE id=?", (current["id"],)
                ).fetchone()
            )
            result.update({"created": False, "revalidated": True, "reversed": True})
            return result
    if verified["currency"] != str(context["currency"] or "").upper():
        raise ValueError("provider payout currency does not match receivable")
    if (
        verified["gross_amount"] <= 0
        or verified["fee_amount"] < 0
        or verified["net_amount"] <= 0
        or abs(
            verified["gross_amount"]
            - verified["fee_amount"]
            - verified["net_amount"]
        )
        > 0.000001
    ):
        raise ValueError("provider payout amounts do not reconcile")
    settlement_id = "settlement-" + hashlib.sha256(
        f"{verified['provider']}:{verified['transaction_id']}".encode("utf-8")
    ).hexdigest()[:24]
    now = iso_now()
    with connect(path, immediate=True) as conn:
        existing = conn.execute(
            "SELECT * FROM settlements WHERE provider=? AND transaction_id=?",
            (verified["provider"], verified["transaction_id"]),
        ).fetchone()
        if existing is not None:
            if existing["work_order_id"] != work_order_id or existing["status"] != "confirmed":
                raise ValueError("provider transaction already bound elsewhere")
            conn.execute(
                """UPDATE settlements
                   SET provider_verification_url=?, provider_verification_id=?,
                       provider_verified_at=?, verification_source=?,
                       provider_payload_sha256=?, provider_status=?, currency=?,
                       gross_amount=?, fee_amount=?, net_amount=?, received_at=?,
                       updated_at=?
                   WHERE id=? AND status='confirmed'""",
                (
                    verified["verification_url"],
                    verified["verification_id"],
                    verified["verified_at"],
                    verified["verification_source"],
                    verified["provider_payload_sha256"],
                    verified["provider_status"],
                    verified["currency"],
                    verified["gross_amount"],
                    verified["fee_amount"],
                    verified["net_amount"],
                    verified["received_at"],
                    now,
                    existing["id"],
                ),
            )
            result = dict(existing)
            result = dict(
                conn.execute(
                    "SELECT * FROM settlements WHERE id=?", (existing["id"],)
                ).fetchone()
            )
            result.update({"created": False, "revalidated": True, "reversed": False})
            return result
        current = conn.execute(
            """SELECT w.status AS work_order_status, w.version AS work_order_version,
                      w.collector_alias, o.status AS opportunity_status
               FROM work_orders AS w
               JOIN opportunities AS o ON o.id=w.opportunity_id
               WHERE w.id=? AND w.opportunity_id=?""",
            (work_order_id, context["opportunity_id"]),
        ).fetchone()
        if (
            current is None
            or current["work_order_status"] != "collection"
            or int(current["work_order_version"])
            != int(context["work_order_version"])
            or current["opportunity_status"] != "payment_pending"
            or current["collector_alias"] != "contador"
        ):
            raise ValueError("collection changed while payout was verified")
        conn.execute(
            """INSERT INTO settlements
               (id, work_order_id, provider, transaction_id,
                provider_verification_url, provider_verification_id,
                provider_verified_at, verification_source,
                provider_payload_sha256, provider_status, collector_alias,
                currency, gross_amount, fee_amount, net_amount, status,
                received_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'contador', ?, ?, ?,
                       ?, 'confirmed', ?, ?, ?)""",
            (
                settlement_id,
                work_order_id,
                verified["provider"],
                verified["transaction_id"],
                verified["verification_url"],
                verified["verification_id"],
                verified["verified_at"],
                verified["verification_source"],
                verified["provider_payload_sha256"],
                verified["provider_status"],
                verified["currency"],
                verified["gross_amount"],
                verified["fee_amount"],
                verified["net_amount"],
                verified["received_at"],
                now,
                now,
            ),
        )
        work_cursor = conn.execute(
            """UPDATE work_orders
               SET status='completed', version=version+1, updated_at=?
               WHERE id=? AND status='collection' AND version=?""",
            (now, work_order_id, context["work_order_version"]),
        )
        opportunity_cursor = conn.execute(
            """UPDATE opportunities SET status='settled', updated_at=?
               WHERE id=? AND status='payment_pending'""",
            (now, context["opportunity_id"]),
        )
        if work_cursor.rowcount != 1 or opportunity_cursor.rowcount != 1:
            raise sqlite3.IntegrityError("official settlement CAS conflict")
        _event(
            conn,
            "settlement",
            settlement_id,
            "official_provider_confirmed",
            None,
            "confirmed",
            "contador",
            {
                "provider": verified["provider"],
                "transaction_id": verified["transaction_id"],
                "payload_sha256": verified["provider_payload_sha256"],
            },
        )
        result = dict(
            conn.execute("SELECT * FROM settlements WHERE id=?", (settlement_id,)).fetchone()
        )
        result["created"] = True
        result["revalidated"] = False
        result["reversed"] = False
        return result


def revalidate_confirmed_settlements(
    db_path: str | os.PathLike[str] | None = None,
    *,
    max_items: int = 20,
) -> list[dict[str, Any]]:
    """Refresh official evidence and remove reversed money idempotently."""
    init_db(db_path)
    bounded = max(0, min(int(max_items), 100))
    with connect(db_path) as conn:
        rows = conn.execute(
            """SELECT work_order_id, provider, transaction_id
               FROM settlements WHERE status='confirmed'
               ORDER BY provider_verified_at ASC, id ASC LIMIT ?""",
            (bounded,),
        ).fetchall()
    results: list[dict[str, Any]] = []
    for row in rows:
        try:
            result = verify_and_record_settlement(
                row["work_order_id"], row["provider"], row["transaction_id"], db_path
            )
            results.append(
                {
                    "work_order_id": row["work_order_id"],
                    "status": "reversed" if result.get("reversed") else "confirmed",
                }
            )
        except (OSError, ValueError) as error:
            results.append(
                {
                    "work_order_id": row["work_order_id"],
                    "status": "unverified",
                    "reason": type(error).__name__,
                }
            )
    return results


def create_settlement(
    settlement_id: str,
    work_order_id: str,
    provider: str,
    transaction_id: str,
    currency: str,
    gross_amount: float,
    fee_amount: float,
    net_amount: float,
    db_path: str | os.PathLike[str] | None = None,
    *,
    collector_alias: str | None = None,
    provider_verification_url: str | None = None,
    provider_verification_id: str | None = None,
    provider_verified_at: str | None = None,
) -> bool:
    """Deprecated unsafe assertion API; callers must use official verification."""
    return False


def confirm_settlement(
    settlement_id: str,
    collector_alias: str,
    db_path: str | os.PathLike[str] | None = None,
) -> bool:
    """Deprecated unsafe confirmation API; official verifier settles atomically."""
    return False


def _realized_revenue_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT s.*, w.lane, w.status AS work_order_status,
                  w.collector_alias AS work_order_collector,
                  o.status AS opportunity_status
           FROM settlements AS s
           JOIN work_orders AS w ON w.id=s.work_order_id
           JOIN opportunities AS o ON o.id=w.opportunity_id
           WHERE s.status='confirmed'
             AND w.lane='receivable'
             AND w.status='completed'
             AND o.status='settled'"""
    ).fetchall()


def _is_realized_settlement(row: Mapping[str, Any]) -> bool:
    if row.get("collector_alias") not in COLLECTOR_IDENTITIES:
        return False
    if row.get("work_order_collector") != row.get("collector_alias"):
        return False
    received_at = _parse_timestamp(row.get("received_at"))
    payload_sha = str(row.get("provider_payload_sha256") or "")
    try:
        gross_amount = float(row.get("gross_amount"))
        fee_amount = float(row.get("fee_amount"))
        net_amount = float(row.get("net_amount"))
    except (TypeError, ValueError):
        return False
    if (
        received_at is None
        or received_at > utc_now() + timedelta(minutes=5)
        or str(row.get("provider") or "").casefold() != "stripe"
        or not str(row.get("transaction_id") or "").startswith("tr_")
        or row.get("verification_source") != "stripe_transfer_api_v1"
        or row.get("provider_status") != "succeeded"
        or str(row.get("currency") or "").upper() not in ALLOWED_SETTLEMENT_CURRENCIES
        or gross_amount <= 0
        or fee_amount < 0
        or net_amount <= 0
        or abs(gross_amount - fee_amount - net_amount) > 0.000001
        or len(payload_sha) != 64
        or any(character not in "0123456789abcdef" for character in payload_sha)
    ):
        return False
    return _valid_provider_verification(
        str(row.get("provider") or ""),
        str(row.get("transaction_id") or ""),
        str(row.get("provider_verification_url") or ""),
        str(row.get("provider_verification_id") or ""),
        str(row.get("provider_verified_at") or ""),
        reference_time=utc_now(),
    )


def _canonical_realized_revenue(
    conn: sqlite3.Connection,
    recognized_currencies: Iterable[str] | None = None,
) -> dict[str, Any]:
    recognized = (
        {str(currency).upper() for currency in recognized_currencies}
        if recognized_currencies is not None
        else set(ALLOWED_SETTLEMENT_CURRENCIES)
    )
    confirmed_count = int(
        conn.execute(
            "SELECT COUNT(*) FROM settlements WHERE status='confirmed'"
        ).fetchone()[0]
    )
    rows = _realized_revenue_rows(conn)
    if confirmed_count != len(rows):
        return {
            "realized_revenue": {},
            "verified": False,
            "reason": "unverified_confirmed_settlement",
        }
    revenue: dict[str, float] = {}
    for settlement_row in rows:
        settlement = dict(settlement_row)
        currency = str(settlement.get("currency") or "").upper()
        if currency not in recognized:
            return {
                "realized_revenue": {},
                "verified": False,
                "reason": f"unsupported_revenue_currency:{currency}",
            }
        if not _is_realized_settlement(settlement):
            return {
                "realized_revenue": {},
                "verified": False,
                "reason": "unverified_confirmed_settlement",
            }
        revenue[currency] = round(
            revenue.get(currency, 0.0) + float(settlement["net_amount"]), 6
        )
    return {
        "realized_revenue": revenue,
        "verified": True,
        "reason": (
            "confirmed_settlements_reconciled"
            if revenue
            else "no_confirmed_settlements"
        ),
    }


def read_realized_revenue(
    db_path: str | os.PathLike[str] | None = None,
    recognized_currencies: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Read the sole canonical revenue predicate without mutating the database."""
    path = resolve_db_path(db_path)
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        return _canonical_realized_revenue(conn, recognized_currencies)
    finally:
        conn.close()


def status_snapshot(db_path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    init_db(db_path)
    with connect(db_path) as conn:
        lanes = {
            row["lane"]: row["count"]
            for row in conn.execute(
                f"""SELECT lane, COUNT(*) AS count FROM work_orders
                    WHERE status IN ({','.join('?' for _ in ACTIVE_WORK_ORDER_STATES)})
                    GROUP BY lane""",
                ACTIVE_WORK_ORDER_STATES,
            ).fetchall()
        }
        revenue_truth = _canonical_realized_revenue(conn)
        leads = conn.execute("SELECT COUNT(*) FROM opportunities WHERE status='lead'").fetchone()[0]
        verified = conn.execute("SELECT COUNT(*) FROM opportunities WHERE status='verified'").fetchone()[0]
    return {
        "generated_at": iso_now(),
        "active_work_orders_by_lane": {"build": lanes.get("build", 0), "receivable": lanes.get("receivable", 0)},
        "lead_count": int(leads),
        "verified_unscheduled_count": int(verified),
        "realized_revenue": revenue_truth["realized_revenue"],
        "revenue_verified": revenue_truth["verified"],
        "revenue_reason": revenue_truth["reason"],
    }


if __name__ == "__main__":
    print(init_db())
