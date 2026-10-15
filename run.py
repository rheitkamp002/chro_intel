"""Entry point for the CHRO External Recognition app's data steps.

Usage:
    python run.py schema     # create any missing tables from schema.sql (safe to re-run)
    python run.py seed       # load award programs + the seed workbook (safe to re-run)
    python run.py roster     # load Fortune 100 / A&D CHRO research as DRAFTS (safe to re-run)
    python run.py accomplishments  # load "what they did" research as DRAFTS (safe to re-run)
    python run.py career     # load career-history + board-seat research as DRAFTS
    python run.py checkup    # read-only wrap-up checks

Launch the dashboard with:  streamlit run app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import config

HERE = Path(__file__).resolve().parent


def apply_schema() -> None:
    """Run schema.sql. Every statement is `if not exists`, so this only ever ADDS.

    It never drops or alters an existing table: a column change still has to be written as
    an explicit ALTER, applied deliberately, and written back to schema.sql.
    """
    from db import connect
    config.SETTINGS.require("database_url")
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute((HERE / "schema.sql").read_text(encoding="utf-8"))
    print("schema.sql applied.")


def _steps() -> dict:
    import accomplishments
    import career
    import checkup
    import roster
    import seed
    return {"schema": apply_schema, "seed": seed.run, "roster": roster.run,
            "accomplishments": accomplishments.run, "career": career.run,
            "checkup": checkup.run}


def main(argv: list[str]) -> int:
    steps = _steps()
    if len(argv) != 2 or argv[1] not in steps:
        print(__doc__)
        return 2
    url = config.SETTINGS.database_url
    host = url.split("@")[-1].split("/")[0] if "@" in url else "(not set)"
    print(f"CHRO Recognition — database host: {host}")
    step = argv[1]
    try:
        steps[step]()
    except BaseException as exc:            # SystemExit included: a refusal ran
        _record_run(step, ok=False, note=type(exc).__name__)
        raise
    _record_run(step, ok=True)
    return 0


def _record_run(step: str, ok: bool, note: str | None = None) -> None:
    """Note that a step ran. Never fails a run: bookkeeping, not the work itself."""
    try:
        from db import connect
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO ingest_run (step, ran_at, ok, note) "
                    "VALUES (%s, now(), %s, %s) ON CONFLICT (step) DO UPDATE SET "
                    "ran_at = excluded.ran_at, ok = excluded.ok, note = excluded.note",
                    (step, ok, note))
    except Exception:
        pass


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
