"""`run.py career` -- load career-history and board-seat research as DRAFTS.

Input: `../research/career_*.json` (outside the public repo), each
    {"people": [{executive_id, name, roles: [...], board_seats: [...], confidence, notes}],
     "not_found": [{executive_id, name, note}]}

Roles already on file are recognized with `metrics.same_role` (same company, and the same
start year or matching title words) and are NOT duplicated; the only thing a re-found role
may add is its `function` where that is still empty. Everything new lands as 'draft' and
appears in the Review tab. A new CURRENT role at a different employer is how a job change
surfaces: approving it demotes the old current role (see review.set_status).

Off-vocabulary values are dropped to NULL and counted out loud -- never coerced to a guess.
Re-runnable: nothing already present is inserted twice.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import config
import metrics
from db import connect, fetch_all

RESEARCH = Path(__file__).resolve().parent.parent / "research"
BATCH = "CAREER_2026_10"


def to_date(year, month) -> tuple[date | None, str | None]:
    """Pure. (2021, 3) -> (2021-03-01, 'month'); (2021, None) -> (2021-01-01, 'year')."""
    if not year:
        return None, None
    try:
        y = int(year)
        m = int(month) if month else None
        if m and 1 <= m <= 12:
            return date(y, m, 1), "month"
        return date(y, 1, 1), "year"
    except (TypeError, ValueError):
        return None, None


def _vocab(value, allowed, dropped: list, what: str):
    if value in (None, ""):
        return None
    if value in allowed:
        return value
    dropped.append(f"{what}={value!r}")
    return None


def run() -> None:
    config.SETTINGS.require("database_url")
    files = sorted(RESEARCH.glob("career_[0-9]*.json"))
    if not files:
        raise SystemExit(f"No career_*.json in {RESEARCH}")
    people, not_found = [], []
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        people += data.get("people") or []
        not_found += data.get("not_found") or []
    print(f"Career research: {len(people)} people, {len(not_found)} not found, "
          f"from {[f.name for f in files]}")

    with connect() as conn:
        execs = {r["executive_id"] for r in fetch_all(
            conn, "select executive_id::text as executive_id from executive")}
        companies = fetch_all(conn, "select company_id::text as company_id, name from company")
        comp_by_key = {}
        for c in companies:
            comp_by_key.setdefault(metrics.company_key(c["name"]), c["company_id"])
        existing: dict[str, list[dict]] = {}
        for r in fetch_all(conn, """
                select role_id::text as role_id, executive_id::text as executive_id,
                       company_name_stated as company, title, function,
                       extract(year from start_date)::int as start_year
                from executive_role"""):
            existing.setdefault(r["executive_id"], []).append(r)

        added = filled = dup = seats = bad = 0
        dropped: list[str] = []
        for p in people:
            xid = p.get("executive_id")
            if xid not in execs:
                bad += 1
                print(f"  SKIPPED unknown executive_id for {p.get('name')!r}")
                continue
            conf = p.get("confidence") if p.get("confidence") in ("high", "medium", "low") else None
            for r in p.get("roles") or []:
                if not (r.get("title") and r.get("company") and r.get("source_url")):
                    bad += 1
                    continue
                cand = {"company": r["company"], "title": r["title"],
                        "start_year": r.get("start_year")}
                match = next((e for e in existing.get(xid, []) if metrics.same_role(e, cand)), None)
                func = _vocab(r.get("function"), config.FUNCTIONS, dropped, "function")
                if match:
                    dup += 1
                    if func and not match["function"]:
                        with conn.cursor() as cur:
                            cur.execute("update executive_role set function = %s, "
                                        "refreshed_at = now() where role_id = %s",
                                        (func, match["role_id"]))
                        match["function"] = func
                        filled += 1
                    continue
                start, sp = to_date(r.get("start_year"), r.get("start_month"))
                end, ep = to_date(r.get("end_year"), r.get("end_month"))
                with conn.cursor() as cur:
                    cur.execute("""
                        insert into executive_role (executive_id, company_id,
                            company_name_stated, title, role_level, function, start_date,
                            start_precision, end_date, end_precision, is_current, hire_type,
                            source_url, source_type, confidence, verified_date,
                            review_status, research_batch, notes)
                        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,current_date,
                                'draft',%s,%s)""",
                        (xid, comp_by_key.get(metrics.company_key(r["company"])), r["company"],
                         r["title"], _vocab(r.get("role_level"), config.ROLE_LEVELS, dropped,
                                            "role_level"),
                         func, start, sp, end, ep, bool(r.get("is_current")),
                         _vocab(r.get("hire_type"), ("internal", "external"), dropped,
                                "hire_type") if r.get("is_current") else None,
                         r["source_url"], _vocab(r.get("source_type"), config.ROLE_SOURCE_TYPES,
                                                 dropped, "source_type"),
                         conf, BATCH, p.get("notes") or None))
                existing.setdefault(xid, []).append({**cand, "role_id": None, "function": func})
                added += 1
            for s in p.get("board_seats") or []:
                if not (s.get("organization") and s.get("source_url")):
                    bad += 1
                    continue
                with conn.cursor() as cur:
                    cur.execute("""
                        insert into board_seat (executive_id, organization, organization_type,
                            seat_role, start_year, end_year, is_current, source_url,
                            research_batch)
                        values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        on conflict (executive_id, organization) do nothing""",
                        (xid, s["organization"].strip(),
                         _vocab(s.get("organization_type"), config.BOARD_ORG_TYPES, dropped,
                                "organization_type"),
                         s.get("role") or None, s.get("start_year") or None,
                         s.get("end_year") or None, s.get("is_current"), s["source_url"],
                         BATCH))
                    seats += cur.rowcount
    print(f"Roles: {added} new drafts, {dup} already on file ({filled} given a function); "
          f"board seats: {seats} new drafts; {bad} items skipped (no source/unknown person)")
    if dropped:
        print(f"Off-vocabulary values set to NULL ({len(dropped)}): {sorted(set(dropped))[:15]}")
    for n in not_found:
        print(f"  not found: {n.get('name')} -- {n.get('note')}")
