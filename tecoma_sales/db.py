"""SQLite persistence for the sales desk.

Three things live here:

  * the CRM core (customers, enquiries, proposals),
  * the *customizable seeding schema* — `seed_fields` defines what the intake
    form asks and `seed_values` holds the answers, so a new question can be
    added at runtime without a migration or a redeploy,
  * the agent transcript (`agent_messages`), which is the audit trail of every
    envelope that crossed the bus.

Connections are opened per call. SQLite in WAL mode handles the concurrency this
app produces (one writer, a handful of readers) without a pool.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import DB_PATH

# SQLite serialises writers itself, but two concurrent writers still surface as
# "database is locked" under WAL. One process-wide write lock is cheaper than
# retry logic and this app has exactly one writer path.
_WRITE_LOCK = threading.RLock()

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS customers (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    company       TEXT NOT NULL,
    country       TEXT,
    city          TEXT,
    industry      TEXT,
    contact_name  TEXT,
    contact_email TEXT,
    contact_phone TEXT,
    website       TEXT,
    account_owner TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    UNIQUE (company, country)
);

-- The customizable part of the seeding data. Rows here ARE the intake form:
-- the UI renders one input per active row, the API validates against them, and
-- the agents read them by key. Adding a row adds a question, everywhere.
CREATE TABLE IF NOT EXISTS seed_fields (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    key          TEXT NOT NULL UNIQUE,
    label        TEXT NOT NULL,
    group_name   TEXT NOT NULL DEFAULT 'General',
    field_type   TEXT NOT NULL DEFAULT 'text',   -- text|number|select|textarea|bool
    unit         TEXT,
    required     INTEGER NOT NULL DEFAULT 0,
    options_json TEXT,                            -- JSON array for select
    default_value TEXT,
    help_text    TEXT,
    position     INTEGER NOT NULL DEFAULT 100,
    active       INTEGER NOT NULL DEFAULT 1,
    system       INTEGER NOT NULL DEFAULT 0,      -- 1 = the engineering agents rely on it
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS enquiries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ref         TEXT NOT NULL UNIQUE,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'received',
    stage       TEXT NOT NULL DEFAULT 'intake',
    score       INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS seed_values (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    enquiry_id  INTEGER NOT NULL REFERENCES enquiries(id) ON DELETE CASCADE,
    field_key   TEXT NOT NULL,
    value_text  TEXT,
    value_num   REAL,
    UNIQUE (enquiry_id, field_key)
);

CREATE TABLE IF NOT EXISTS agent_messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    enquiry_id   INTEGER REFERENCES enquiries(id) ON DELETE CASCADE,
    seq          INTEGER NOT NULL,
    ts           TEXT NOT NULL,
    sender       TEXT NOT NULL,
    recipient    TEXT NOT NULL,
    intent       TEXT NOT NULL,
    kind         TEXT NOT NULL DEFAULT 'request',  -- request|reply|broadcast|challenge
    body         TEXT NOT NULL,
    payload_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_msg_enquiry ON agent_messages(enquiry_id, seq);

CREATE TABLE IF NOT EXISTS proposals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    enquiry_id      INTEGER NOT NULL REFERENCES enquiries(id) ON DELETE CASCADE,
    technology      TEXT NOT NULL,
    model_code      TEXT,
    evaporation_kgh REAL,
    thermal_kw      REAL,
    electrical_kw   REAL,
    capex_eur       REAL,
    opex_eur_year   REAL,
    payback_years   REAL,
    confidence      REAL,
    summary         TEXT,
    payload_json    TEXT,
    created_at      TEXT NOT NULL,
    UNIQUE (enquiry_id)
);

CREATE TABLE IF NOT EXISTS follow_ups (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    enquiry_id INTEGER NOT NULL REFERENCES enquiries(id) ON DELETE CASCADE,
    due_date   TEXT NOT NULL,
    owner      TEXT NOT NULL,
    action     TEXT NOT NULL,
    done       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path | None = None) -> sqlite3.Connection:
    target = Path(path or DB_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target, check_same_thread=False, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def write(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """A serialised write transaction."""
    with _WRITE_LOCK:
        conn = connect(path)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


@contextmanager
def read(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
    finally:
        conn.close()


def init_db(path: Path | None = None) -> None:
    with write(path) as conn:
        conn.executescript(SCHEMA)


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


def loads(blob: str | None, fallback: Any = None) -> Any:
    if not blob:
        return fallback
    try:
        return json.loads(blob)
    except (TypeError, ValueError):
        return fallback


# --------------------------------------------------------------------------
# Seed-field helpers — the customizable schema
# --------------------------------------------------------------------------

def list_seed_fields(include_inactive: bool = False,
                     path: Path | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM seed_fields"
    if not include_inactive:
        sql += " WHERE active = 1"
    sql += " ORDER BY position, id"
    with read(path) as conn:
        fields = rows_to_dicts(conn.execute(sql).fetchall())
    for f in fields:
        f["options"] = loads(f.pop("options_json"), [])
        f["required"] = bool(f["required"])
        f["active"] = bool(f["active"])
        f["system"] = bool(f["system"])
    return fields


def upsert_seed_field(field: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    """Create or update one intake question. `key` is the identity."""
    key = field["key"].strip().lower().replace(" ", "_")
    options = field.get("options") or []
    with write(path) as conn:
        existing = conn.execute(
            "SELECT id, system FROM seed_fields WHERE key = ?", (key,)
        ).fetchone()
        params = (
            field.get("label") or key.replace("_", " ").title(),
            field.get("group_name") or "Custom",
            field.get("field_type") or "text",
            field.get("unit"),
            1 if field.get("required") else 0,
            json.dumps(options) if options else None,
            field.get("default_value"),
            field.get("help_text"),
            int(field.get("position") or 500),
            1 if field.get("active", True) else 0,
        )
        if existing:
            conn.execute(
                """UPDATE seed_fields SET label=?, group_name=?, field_type=?, unit=?,
                   required=?, options_json=?, default_value=?, help_text=?,
                   position=?, active=? WHERE key=?""",
                (*params, key),
            )
        else:
            conn.execute(
                """INSERT INTO seed_fields
                   (label, group_name, field_type, unit, required, options_json,
                    default_value, help_text, position, active, system, key, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (*params, 1 if field.get("system") else 0, key, utcnow()),
            )
    return next(f for f in list_seed_fields(include_inactive=True, path=path)
                if f["key"] == key)


def delete_seed_field(key: str, path: Path | None = None) -> bool:
    """Retire a question. System fields are deactivated, never dropped — the
    engineering agents read them by key and would fail closed without them."""
    with write(path) as conn:
        row = conn.execute("SELECT system FROM seed_fields WHERE key=?", (key,)).fetchone()
        if row is None:
            return False
        if row["system"]:
            conn.execute("UPDATE seed_fields SET active=0 WHERE key=?", (key,))
        else:
            conn.execute("DELETE FROM seed_fields WHERE key=?", (key,))
    return True


def seed_values_for(enquiry_id: int, path: Path | None = None) -> dict[str, Any]:
    with read(path) as conn:
        rows = conn.execute(
            "SELECT field_key, value_text, value_num FROM seed_values WHERE enquiry_id=?",
            (enquiry_id,),
        ).fetchall()
    out: dict[str, Any] = {}
    for r in rows:
        out[r["field_key"]] = r["value_num"] if r["value_num"] is not None else r["value_text"]
    return out
