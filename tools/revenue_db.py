"""Revenue Manager v2 — SQLite persistence layer.

Single source of truth for identities, opportunities, work orders, events, and settlements.
Uses WAL mode and CAS (Compare-And-Swap) transitions for deterministic state management.
"""

import sqlite3
import json
import os
from datetime import datetime, timezone
from typing import Optional


DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "aro", "revenue_v2.db")


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Get a connection with WAL mode enabled."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: Optional[sqlite3.Connection] = None) -> None:
    """Create tables if they do not exist."""
    if conn is None:
        conn = get_connection()
        close = True
    else:
        close = False

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS identities (
            identity_id TEXT PRIMARY KEY,
            alias TEXT NOT NULL,
            provider TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        );

        CREATE TABLE IF NOT EXISTS opportunities (
            opportunity_id TEXT PRIMARY KEY,
            repo TEXT NOT NULL,
            issue_number INTEGER,
            title TEXT,
            bounty_amount REAL,
            currency TEXT DEFAULT 'USD',
            ev_net_per_hour REAL,
            claim_path TEXT,
            evidence_url TEXT,
            status TEXT NOT NULL DEFAULT 'discovered',
            verified_at TEXT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        );

        CREATE TABLE IF NOT EXISTS repo_health (
            repo TEXT PRIMARY KEY,
            last_checked TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            is_active INTEGER NOT NULL DEFAULT 1,
            health_score REAL
        );

        CREATE TABLE IF NOT EXISTS work_orders (
            work_order_id TEXT PRIMARY KEY,
            opportunity_id TEXT NOT NULL REFERENCES opportunities(opportunity_id),
            assigned_to TEXT REFERENCES identities(identity_id),
            status TEXT NOT NULL DEFAULT 'queued',
            started_at TEXT,
            completed_at TEXT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        );

        CREATE TABLE IF NOT EXISTS events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            from_state TEXT,
            to_state TEXT,
            metadata TEXT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        );

        CREATE TABLE IF NOT EXISTS settlements (
            settlement_id TEXT PRIMARY KEY,
            work_order_id TEXT NOT NULL REFERENCES work_orders(work_order_id),
            provider TEXT NOT NULL,
            transaction_id TEXT NOT NULL,
            gross_amount REAL NOT NULL,
            fee_amount REAL NOT NULL DEFAULT 0,
            net_amount REAL NOT NULL,
            currency TEXT NOT NULL DEFAULT 'USD',
            settled_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            UNIQUE(provider, transaction_id)
        );

        CREATE INDEX IF NOT EXISTS idx_opportunities_status ON opportunities(status);
        CREATE INDEX IF NOT EXISTS idx_work_orders_status ON work_orders(status);
        CREATE INDEX IF NOT EXISTS idx_events_entity ON events(entity_type, entity_id);
    """)

    conn.commit()
    if close:
        conn.close()


def upsert_identity(conn: sqlite3.Connection, identity_id: str, alias: str, provider: str) -> None:
    """Insert or update an identity."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO identities (identity_id, alias, provider, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(identity_id) DO UPDATE SET
               alias = excluded.alias,
               provider = excluded.provider,
               updated_at = excluded.updated_at""",
        (identity_id, alias, provider, now),
    )
    conn.commit()


def upsert_opportunity(conn: sqlite3.Connection, opp: dict) -> None:
    """Insert or update an opportunity."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO opportunities
           (opportunity_id, repo, issue_number, title, bounty_amount, currency,
            ev_net_per_hour, claim_path, evidence_url, status, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(opportunity_id) DO UPDATE SET
               repo = excluded.repo,
               issue_number = excluded.issue_number,
               title = excluded.title,
               bounty_amount = excluded.bounty_amount,
               currency = excluded.currency,
               ev_net_per_hour = excluded.ev_net_per_hour,
               claim_path = excluded.claim_path,
               evidence_url = excluded.evidence_url,
               status = excluded.status,
               updated_at = excluded.updated_at""",
        (
            opp["opportunity_id"],
            opp.get("repo", ""),
            opp.get("issue_number"),
            opp.get("title"),
            opp.get("bounty_amount"),
            opp.get("currency", "USD"),
            opp.get("ev_net_per_hour"),
            opp.get("claim_path"),
            opp.get("evidence_url"),
            opp.get("status", "discovered"),
            now,
        ),
    )
    conn.commit()


def cas_transition_opportunity(
    conn: sqlite3.Connection,
    opportunity_id: str,
    expected_state: str,
    new_state: str,
    metadata: Optional[dict] = None,
) -> bool:
    """CAS transition for opportunity state. Returns True if transition succeeded."""
    valid_states = {
        "discovered", "verified", "claimed", "implementing", "reviewed",
        "submitted", "feedback", "accepted", "payment_pending", "settled",
    }
    if new_state not in valid_states:
        raise ValueError(f"Invalid state: {new_state}")

    now = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        """UPDATE opportunities
           SET status = ?, updated_at = ?,
               verified_at = CASE WHEN ? = 'verified' AND verified_at IS NULL THEN ? ELSE verified_at END
           WHERE opportunity_id = ? AND status = ?""",
        (new_state, now, new_state, now, opportunity_id, expected_state),
    )
    if cursor.rowcount > 0:
        log_event(
            conn,
            "opportunity",
            opportunity_id,
            "state_transition",
            from_state=expected_state,
            to_state=new_state,
            metadata=metadata,
        )
        conn.commit()
        return True
    return False


def create_work_order(
    conn: sqlite3.Connection,
    opportunity_id: str,
    assigned_to: Optional[str] = None,
) -> str:
    """Create a work order for an opportunity."""
    import uuid
    wo_id = f"wo-{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO work_orders (work_order_id, opportunity_id, assigned_to, status, created_at, updated_at)
           VALUES (?, ?, ?, 'queued', ?, ?)""",
        (wo_id, opportunity_id, assigned_to, now, now),
    )
    log_event(conn, "work_order", wo_id, "created", metadata={"opportunity_id": opportunity_id})
    conn.commit()
    return wo_id


def log_event(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: str,
    event_type: str,
    from_state: Optional[str] = None,
    to_state: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Log an event."""
    conn.execute(
        """INSERT INTO events (entity_type, entity_id, event_type, from_state, to_state, metadata)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (entity_type, entity_id, event_type, from_state, to_state, json.dumps(metadata) if metadata else None),
    )


def upsert_settlement(
    conn: sqlite3.Connection,
    work_order_id: str,
    provider: str,
    transaction_id: str,
    gross_amount: float,
    fee_amount: float,
    net_amount: float,
    currency: str = "USD",
) -> str:
    """Upsert a settlement record. Deduplicates by provider + transaction_id."""
    settlement_id = f"stl-{provider}-{transaction_id}"
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO settlements
           (settlement_id, work_order_id, provider, transaction_id, gross_amount, fee_amount, net_amount, currency, settled_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(settlement_id) DO UPDATE SET
               gross_amount = excluded.gross_amount,
               fee_amount = excluded.fee_amount,
               net_amount = excluded.net_amount,
               currency = excluded.currency,
               settled_at = excluded.settled_at""",
        (settlement_id, work_order_id, provider, transaction_id, gross_amount, fee_amount, net_amount, currency, now),
    )
    log_event(conn, "settlement", settlement_id, "recorded", metadata={"work_order_id": work_order_id})
    conn.commit()
    return settlement_id


def import_verified_candidates(conn: sqlite3.Connection, candidates_path: str) -> int:
    """Import verified revenue candidates from JSON into opportunities table."""
    with open(candidates_path, "r") as f:
        candidates = json.load(f)

    count = 0
    for c in candidates:
        opp_id = c.get("opportunity_id") or f"opp-{c.get('repo', '')}-{c.get('issue_number', '')}"
        opp = {
            "opportunity_id": opp_id,
            "repo": c.get("repo", ""),
            "issue_number": c.get("issue_number"),
            "title": c.get("title"),
            "bounty_amount": c.get("bounty_amount"),
            "currency": c.get("currency", "USD"),
            "ev_net_per_hour": c.get("ev_net_per_hour"),
            "claim_path": c.get("claim_path"),
            "evidence_url": c.get("evidence_url"),
            "status": "verified",
        }
        upsert_opportunity(conn, opp)
        # Log the import
        log_event(conn, "opportunity", opp_id, "imported", metadata={"source": "verified_candidates"})
        count += 1

    conn.commit()
    return count


if __name__ == "__main__":
    conn = get_connection()
    init_schema(conn)
    print(f"Schema initialized at {DB_PATH}")

    # Import verified candidates if file exists
    candidates_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "aro", "verified_revenue_candidates.json")
    if os.path.exists(candidates_path):
        count = import_verified_candidates(conn, candidates_path)
        print(f"Imported {count} verified candidates")

    conn.close()
