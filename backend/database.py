import asyncio
import json
import os
import sqlite3
import threading
from collections import deque

import backend.config as _cfg

_DB_PATH = os.path.join(os.path.dirname(__file__), "crowdlens.db")

_thread_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    if not hasattr(_thread_local, "conn") or _thread_local.conn is None:
        try:
            conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            _thread_local.conn = conn
        except sqlite3.DatabaseError:
            # DB file is corrupt — remove and recreate
            try:
                import os
                for suffix in ("", "-shm", "-wal"):
                    p = _DB_PATH + suffix
                    if os.path.exists(p):
                        os.unlink(p)
            except OSError:
                pass
            conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            _thread_local.conn = conn
    return _thread_local.conn


def _init_db_sync():
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_id    INTEGER NOT NULL,
            anomaly     TEXT    NOT NULL,
            timestamp   REAL    NOT NULL,
            iso         TEXT    NOT NULL,
            source      TEXT    NOT NULL DEFAULT '',
            snapshot_url TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp DESC)")

    # Forward-migration for DBs created before snapshot_url existed.
    # Without this, a user upgrading from an older build hits
    # `sqlite3.OperationalError: no such column: snapshot_url` on the very
    # first alert insert, because CREATE TABLE IF NOT EXISTS only runs when
    # the table is missing and never adds columns to an existing table.
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(alerts)").fetchall()}
    if "snapshot_url" not in cols:
        try:
            conn.execute("ALTER TABLE alerts ADD COLUMN snapshot_url TEXT")
        except sqlite3.OperationalError as e:
            # If the column races in (multiple processes, very unlikely on
            # local single-user) just log and continue.
            print(f"[database] ALTER TABLE add snapshot_url skipped: {e}")
    if "source" not in cols:
        try:
            conn.execute("ALTER TABLE alerts ADD COLUMN source TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError as e:
            print(f"[database] ALTER TABLE add source skipped: {e}")

    conn.commit()


def _insert_alert_sync(entry: dict):
    try:
        conn = _get_conn()
        conn.execute(
            """
            INSERT INTO alerts (alert_id, anomaly, timestamp, iso, source, snapshot_url)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                entry["id"],
                json.dumps(entry["anomaly"]),
                entry["timestamp"],
                entry["iso"],
                entry.get("source", ""),
                entry.get("snapshot_url"),
            ),
        )
        # Bound DB size on a long-running single-user session. Without this,
        # months of operation accumulate hundreds of MB of alert rows that
        # the UI never displays (it caps at 200 in the request and 500 in
        # the deque). Trim only when over the cap and only once per insert
        # to keep this cheap; SQLite handles the index rewrite efficiently.
        retention = int(getattr(_cfg, "DB_ALERT_RETENTION", 5000))
        if retention > 0:
            cur = conn.execute("SELECT COUNT(*) AS n FROM alerts").fetchone()
            count = int(cur["n"]) if cur else 0
            if count > retention:
                # Delete the oldest (count - retention) rows. Index on
                # timestamp DESC keeps this O(log n) seek.
                excess = count - retention
                conn.execute(
                    "DELETE FROM alerts WHERE id IN ("
                    "  SELECT id FROM alerts ORDER BY timestamp ASC LIMIT ?"
                    ")",
                    (excess,),
                )
        conn.commit()
    except (sqlite3.DatabaseError, sqlite3.OperationalError) as e:
        # Log but don't crash the background thread on DB write failures
        print(f"[database] Insert alert failed: {e}")


def _load_alerts_sync(limit: int = 500) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM alerts ORDER BY timestamp DESC LIMIT ?", (limit,)
    ).fetchall()
    results = []
    for row in rows:
        results.append({
            "id": row["alert_id"],
            "anomaly": json.loads(row["anomaly"]),
            "timestamp": row["timestamp"],
            "iso": row["iso"],
            "source": row["source"],
            "snapshot_url": row["snapshot_url"],
        })
    return results


def _clear_alerts_sync():
    conn = _get_conn()
    conn.execute("DELETE FROM alerts")
    conn.commit()


async def init_db():
    await asyncio.to_thread(_init_db_sync)


async def insert_alert(entry: dict):
    await asyncio.to_thread(_insert_alert_sync, entry)


async def load_alerts(limit: int = 500) -> list[dict]:
    return await asyncio.to_thread(_load_alerts_sync, limit)


async def clear_alerts():
    await asyncio.to_thread(_clear_alerts_sync)


def load_into_deque(dq: deque):
    """Synchronously populate an existing deque from the DB (called at startup)."""
    rows = _load_alerts_sync(dq.maxlen or 500)
    for row in reversed(rows):
        dq.append(row)
