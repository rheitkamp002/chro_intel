"""`run.py checkup` -- read-only wrap-up checks. Run at the end of every piece of work.

Exits non-zero when it finds something a person must decide, so it fails loudly rather than
asking anyone to remember.
"""
from __future__ import annotations

import sys

import config
from db import connect, fetch_all

TABLES = ("company", "peer_set", "company_peer_set", "executive", "executive_role", "recognition_program", "program_category",
          "program_criterion", "recognition_cycle", "recognition_event", "accomplishment",
          "accomplishment_criterion", "accomplishment_theme", "accomplishment_gap",
          "ingest_run")


def run() -> None:
    config.SETTINGS.require("database_url")
    findings = 0
    with connect() as conn:
        live = {r["table_name"] for r in fetch_all(conn, """
            select table_name from information_schema.tables where table_schema = 'public'""")}
        missing = [t for t in TABLES if t not in live]
        print("1. Schema: " + ("all tables present" if not missing
                               else f"MISSING {missing} -- run `run.py schema`"))
        if missing:
            sys.exit(1)

        print("2. Row counts:")
        for t in TABLES:
            n = fetch_all(conn, f"select count(*) as n from {t}")[0]["n"]
            print(f"     {t:<26} {n:>6}")

        dupes = fetch_all(conn, """
            select name_key, array_agg(canonical_name) as names, count(*) as n
            from executive group by name_key having count(*) > 1""")
        print(f"3. Possible duplicate executives (same name, different employer): {len(dupes)}")
        for d in dupes:
            print(f"     {d['names']} -- decide: same person or not")
        findings += len(dupes)

        unclassified = fetch_all(conn, "select name from company where industry is null "
                                       "order by name")
        print(f"4. Companies without an industry: {len(unclassified)}"
              + (f" {[c['name'] for c in unclassified]}" if unclassified else ""))

        window = config.analysis_window()
        pending = fetch_all(conn, """
            select p.badge_label, c.cycle_year from recognition_cycle c
            join recognition_program p using (program_id)
            where c.status = 'pending' and c.cycle_year = any(%s) order by 1, 2""", (list(window),))
        print(f"5. Pending (not yet published) in window {window[0]}-{window[-1]}: "
              + (", ".join(f"{p['badge_label']} {p['cycle_year']}" for p in pending) or "none"))

        drafts = fetch_all(conn, """
            select (select count(*) from accomplishment where review_status = 'draft') as a,
                   (select count(*) from executive_role where review_status = 'draft') as r""")[0]
        print(f"6. Awaiting review: {drafts['a']} accomplishments, {drafts['r']} roles")

        orphans = fetch_all(conn, """
            select count(*) as n from recognition_event e
            where e.company_at_recognition is not null and e.company_id is null""")[0]["n"]
        print(f"7. Events whose company is not linked: {orphans}")
        findings += orphans

    print("\ncheckup: " + ("clean" if not findings else f"{findings} finding(s) to review"))
    if findings:
        sys.exit(1)
