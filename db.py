"""Thin Postgres/Supabase access layer built on psycopg 3.

Exposes a connection context manager and a generic `upsert` that does
INSERT ... ON CONFLICT DO UPDATE, which is what makes every ingest re-runnable.
"""
from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Any, Iterable, Sequence

import psycopg
from psycopg import sql

from config import SETTINGS

# A transient failure to REACH Supabase must not take down a whole page render.
# MEASURED 2026-08-17 over 40 sequential connects from the owner's machine: 40/40
# succeeded, median 731ms — but the slowest took 7,885ms against a 10s connect_timeout,
# so the path routinely runs close to the ceiling and occasionally crosses it. app.py
# opens 53 separate connections (13 on the Profile tab alone), so one blip anywhere
# raised ConnectionTimeout out of a cached loader and killed the entire script run —
# which is exactly how it was reported: the Profile tab dying inside load_leadership.
#
# THE COST OF THIS TRADE, stated rather than buried: a genuinely unreachable database
# (a paused Supabase project) now takes ~24s to report instead of ~10s. That is the
# price of surviving a blip, and it is worth it for an interactive dashboard.
_CONNECT_ATTEMPTS = 3
_CONNECT_BACKOFF_S = (1.0, 3.0)


def _is_transient(exc: BaseException) -> bool:
    """Pure. Is this a failure to ESTABLISH a connection, worth retrying?

    Deliberately narrow. A bad password, a missing database or a query error is
    PERMANENT: retrying it burns 24 seconds and then reports the same thing, while
    hiding the real message behind a delay. Only the reach-the-server case retries.
    """
    if not isinstance(exc, psycopg.OperationalError):
        return False
    text = str(exc).lower()
    permanent = ("password", "authentication", "does not exist", "role ",
                 "no pg_hba.conf", "ssl error")
    return not any(p in text for p in permanent)


# ---------------------------------------------------------------------------------------
# CONNECTION REUSE (2026-09-01). Recorded as an option since 2026-08-17 and taken now,
# because hosting the dashboard on a phone made it the difference between usable and not.
#
# THE COST IT REMOVES, MEASURED 2026-09-01 against the live database:
#   opening a fresh connection   513 ms
#   a round trip on an open one   88 ms
# `app.py` calls `connect()` 53 times per render, so connecting alone was ~27 seconds of
# every page load. Reuse turns that into a health check at worst, and usually nothing.
#
# WHY A SMALL POOL AND NOT A THREAD-LOCAL. Streamlit runs each script execution on a NEW
# thread, so a per-thread cache would open a fresh connection on every rerun — worse than
# today, and it would leak the old ones. A shared pool guarded by a lock is reused across
# reruns, which is the whole point.
#
# WHY NOT `psycopg_pool`. It is the right tool for a server with real concurrency. This is
# a single-user dashboard; a list, a lock and a health check are the whole requirement, and
# adding a dependency to a hosted app is a cost of its own.
#
# SAFETY IS PRESERVED EXACTLY. The health check and any reconnect happen BEFORE the
# context manager yields, so — as before — a retry can never re-run statements that already
# executed. A connection that errors is closed rather than returned to the pool.
_POOL: list = []
_POOL_LOCK = threading.Lock()
_MAX_IDLE = 4                  # a single-user dashboard never needs more
# Skip the health check on a connection handed back within this window. Inside one page
# render the 53 calls happen seconds apart, so the check runs once and the rest are free.
# The risk it accepts is a connection dying mid-window, which surfaces as an error the
# caller sees — never as a partial write, because the failure still triggers a rollback.
_HEALTH_CHECK_AFTER_S = 20.0


def _new_connection():
    """A fresh connection, with the transient-failure retry. Never yields."""
    for attempt in range(_CONNECT_ATTEMPTS):
        try:
            return psycopg.connect(
                SETTINGS.database_url,
                connect_timeout=10,
                keepalives=1,
                keepalives_idle=30,
                # Disabled deliberately. This URL is Supabase's pooler in SESSION mode
                # (port 5432), where prepared statements are safe — but the same host on
                # port 6543 is TRANSACTION mode, where a prepared statement raises. The
                # gain here is negligible (every dashboard query is cached by Streamlit
                # and runs once), so the robustness is free.
                prepare_threshold=None,
            )
        except Exception as exc:
            if attempt == _CONNECT_ATTEMPTS - 1 or not _is_transient(exc):
                raise
            time.sleep(_CONNECT_BACKOFF_S[attempt])


def _usable(conn, idle_since: float) -> bool:
    """Pure-ish. Is this pooled connection safe to hand out? Never raises."""
    if conn is None or conn.closed:
        return False
    if time.monotonic() - idle_since < _HEALTH_CHECK_AFTER_S:
        return True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except Exception:
        return False


def _discard(conn) -> None:
    try:
        conn.close()
    except Exception:
        pass


def close_pool() -> None:
    """Close every idle connection. For tests and orderly shutdown."""
    with _POOL_LOCK:
        while _POOL:
            _discard(_POOL.pop()[0])


@contextmanager
def connect():
    SETTINGS.require("database_url")
    conn = None
    while True:                                   # take the newest idle connection
        with _POOL_LOCK:
            if not _POOL:
                break
            candidate, since = _POOL.pop()
        if _usable(candidate, since):
            conn = candidate
            break
        _discard(candidate)                       # stale: drop it and try the next
    if conn is None:
        conn = _new_connection()

    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass                                  # a dead connection cannot roll back
        _discard(conn)                            # never return a failed one to the pool
        raise
    else:
        with _POOL_LOCK:
            if len(_POOL) < _MAX_IDLE and not conn.closed:
                _POOL.append((conn, time.monotonic()))
                return
        _discard(conn)


def upsert(
    conn: psycopg.Connection,
    table: str,
    rows: Sequence[dict[str, Any]],
    conflict_cols: Iterable[str],
    update_cols: Iterable[str] | None = None,
) -> int:
    """Bulk upsert. `rows` must share the same keys.

    conflict_cols: the unique/PK columns to resolve conflicts on.
    update_cols:   columns to overwrite on conflict (default: all non-conflict columns).
    Returns the number of rows submitted.
    """
    rows = list(rows)
    if not rows:
        return 0

    # THE FIRST ROW DEFINES THE COLUMN LIST, so a row with extra keys has them SILENTLY
    # DROPPED. MEASURED 2026-08-18: profiles.py's private-company stub carries 21 keys
    # while a full public row carries 32. Issuers are ordered by name, a private company
    # sorted first, and all 11 UB-23 multiples columns were dropped for all 9 filers —
    # the step reported success, checkup was clean, and the columns were simply NULL.
    # The docstring already required matching keys; now the requirement is enforced
    # rather than trusted, because the failure is otherwise invisible.
    cols = list(rows[0].keys())
    first = set(cols)
    for i, r in enumerate(rows[1:], start=1):
        if set(r.keys()) != first:
            missing = sorted(first - set(r.keys()))
            extra = sorted(set(r.keys()) - first)
            raise ValueError(
                f"upsert('{table}'): row {i} has different keys from row 0, so columns "
                f"would be silently dropped. missing={missing} extra={extra}")
    conflict_cols = list(conflict_cols)
    if update_cols is None:
        update_cols = [c for c in cols if c not in conflict_cols]
    update_cols = list(update_cols)

    col_ids = sql.SQL(", ").join(map(sql.Identifier, cols))
    placeholders = sql.SQL(", ").join(sql.Placeholder() * len(cols))
    conflict_ids = sql.SQL(", ").join(map(sql.Identifier, conflict_cols))

    if update_cols:
        set_clause = sql.SQL(", ").join(
            sql.SQL("{c} = EXCLUDED.{c}").format(c=sql.Identifier(c)) for c in update_cols
        )
        conflict_action = sql.SQL("DO UPDATE SET {}").format(set_clause)
    else:
        conflict_action = sql.SQL("DO NOTHING")

    stmt = sql.SQL(
        "INSERT INTO {table} ({cols}) VALUES ({ph}) "
        "ON CONFLICT ({conflict}) {action}"
    ).format(
        table=sql.Identifier(table),
        cols=col_ids,
        ph=placeholders,
        conflict=conflict_ids,
        action=conflict_action,
    )

    with conn.cursor() as cur:
        cur.executemany(stmt, [[r[c] for c in cols] for r in rows])
    return len(rows)


def fetch_all(conn: psycopg.Connection, query: str, params: Sequence[Any] = ()) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(query, params)
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]