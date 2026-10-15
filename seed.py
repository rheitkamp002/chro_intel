"""`run.py seed` -- load award programs (programs.py) and the seed workbook into the database.

Re-runnable. What a re-run does, by table:
  recognition_program / program_criterion / program_category   OVERWRITTEN from programs.py
      (that file is the source of record; edit it, then re-run seed to change a weight)
  recognition_cycle, company, executive, recognition_event      INSERT-ONLY
      (status updates, research and history are never clobbered by a re-seed)

DEDUPLICATION (spec section 23): a workbook row joins an existing executive only when the
normalized NAME and the normalized COMPANY both match. Same name at a different company
creates a new executive, which `checkup` then lists as a possible duplicate for a person to
decide. Never merge on name alone.

NOT LOADED: the workbook's "Why recognized" column. It repeats each program's methodology
text on every row (one sentence per organization), so it says nothing about the person. The
program's criteria summary carries it; per-person accomplishments come from research.
The "Curated CHROs" and "Scoring Notes" tabs are derived from the others and recomputed.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import openpyxl

import config
import metrics
import programs
from db import connect, fetch_all, upsert

HERE = Path(__file__).resolve().parent

# Broad industry per company at recognition. ANALYST-ASSIGNED 2026-10-15 from general
# knowledge, for the comparison filter only; `industry_source='analyst'` marks them, and a
# company left out stays NULL ("not classified") rather than guessed.
INDUSTRY_SEED: dict[str, str] = {
    "Apollo Global Management": "Financial Services", "Cardinal Health": "Healthcare & Life Sciences",
    "Walmart": "Retail", "UPS": "Transportation & Logistics", "IBM": "Technology",
    "Bank of America": "Financial Services", "Seacoast Bank": "Financial Services",
    "Synopsys": "Technology", "Cisco": "Technology",
    "Polaris Transportation Group": "Transportation & Logistics", "Pittsburgh Water": "Utilities",
    "Memorial Hermann Health System": "Healthcare & Life Sciences",
    "American Express": "Financial Services", "Securonix": "Technology",
    "GlobalFoundries": "Technology", "PandaDoc": "Technology",
    "Hartford HealthCare": "Healthcare & Life Sciences",
    "Guardant Health": "Healthcare & Life Sciences", "Citizens First Bank": "Financial Services",
    "Guild": "Technology", "Labcorp": "Healthcare & Life Sciences",
    "Altria Group": "Consumer Goods", "Caterpillar": "Industrials & Manufacturing",
    "Synchrony Financial": "Financial Services",
    "International Flavors & Fragrances": "Chemicals & Materials",
    "The Campbell's Company": "Consumer Goods", "Misk Foundation": "Non-Profit",
    "Stanford University": "Education", "Philip Morris International": "Consumer Goods",
    "S&P Global": "Financial Services", "Reliance Industries": "Conglomerate",
    "AGCO": "Industrials & Manufacturing", "General Mills": "Consumer Goods",
    "DXC Technology": "Technology", "Included Health": "Healthcare & Life Sciences",
    "Union Pacific": "Transportation & Logistics", "Gilead Sciences": "Healthcare & Life Sciences",
    "Grupo Salinas": "Conglomerate", "Access Holdings": "Financial Services",
    "Merck KGaA": "Healthcare & Life Sciences", "VSP Vision": "Healthcare & Life Sciences",
    "WTW": "Professional Services", "Vialto Partners": "Professional Services",
    "The Coca-Cola Company": "Consumer Goods", "AutoNation": "Retail",
    "Moody's": "Financial Services", "PwC": "Professional Services",
    "Medtronic": "Healthcare & Life Sciences", "Tractor Supply Company": "Retail",
    "MacArthur Foundation": "Non-Profit", "Dentons": "Professional Services",
    "PPG Industries": "Chemicals & Materials", "JPMorganChase": "Financial Services",
    "Verizon": "Telecommunications", "Alcoa": "Chemicals & Materials",
    "LyondellBasell": "Chemicals & Materials", "University of South Carolina": "Education",
    "Blackstone": "Financial Services", "HiBob": "Technology",
    "Unifi Aviation": "Transportation & Logistics", "Basis Technologies": "Technology",
    "St. Luke's Hospital": "Healthcare & Life Sciences",
    "Port of New Orleans": "Transportation & Logistics", "Choctaw Nation of Oklahoma": "Public Sector",
    "Mothers Against Drunk Driving": "Non-Profit", "Delta Dental of Virginia": "Insurance",
    "Madison Logic": "Technology", "GAT - Airline Ground Support": "Transportation & Logistics",
    "Blackbaud": "Technology", "MedeAnalytics": "Technology",
    "Inotiv": "Healthcare & Life Sciences", "Coast Mental Health": "Healthcare & Life Sciences",
    "Integral Ad Science": "Technology", "Fortitude Re": "Insurance",
    "EyeCare Partners": "Healthcare & Life Sciences", "OpSec Security": "Technology",
    "MODE Global": "Transportation & Logistics", "embecta": "Healthcare & Life Sciences",
    "Community Options": "Non-Profit", "Seagate Technology": "Technology",
    "Persistent": "Technology", "Wizeline": "Technology", "Meridian Credit Union": "Financial Services",
    "Employ.": "Technology", "Zinnov": "Professional Services",
    "University Medical Center": "Healthcare & Life Sciences", "LHH": "Professional Services",
    "Perceptyx": "Technology", "Children's Home Society of North Carolina": "Non-Profit",
    "Acosta Group": "Professional Services", "Dayforce": "Technology",
}

_ACADEMIC = re.compile(r"\b(professor|scholar)\b", re.I)


def read_workbook(path: Path) -> list[dict]:
    """Rows from the 'Core Recognition Events' and 'Secondary Recognition' tabs, normalized."""
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    out: list[dict] = []
    for tab in ("Core Recognition Events", "Secondary Recognition"):
        rows = wb[tab].iter_rows(values_only=True)
        header = [str(h).strip() if h is not None else "" for h in next(rows)]
        for r in rows:
            if not any(r):
                continue
            d = dict(zip(header, r))
            out.append({
                "executive": str(d["Executive"]).strip(),
                "title": (str(d["Title at recognition"]).strip()
                          if d.get("Title at recognition") else None),
                "company": (str(d["Company at recognition"]).strip()
                            if d.get("Company at recognition") else None),
                "year": int(d["Year"]),
                "organization": str(d["Organization"]).strip(),
                "recognition": str(d["Recognition"]).strip(),
                "category": str(d.get("Category / rank") or "").strip(),
                "source_url": d.get("Source URL"),
                "tab": tab,
            })
    return out


def plan_executives(rows: list[dict], existing: list[dict]) -> dict[int, str]:
    """Pure. Map each row index to an executive identity key '<name_key>|<n>'.

    `existing` holds {"executive_id", "name_key", "company_keys"} for executives already in
    the database; their identity key is their executive_id. A row joins an identity only
    when name_key AND company_key both match.
    """
    known: list[tuple[str, str, set[str]]] = [
        (e["executive_id"], e["name_key"], set(e["company_keys"])) for e in existing]
    assignment: dict[int, str] = {}
    counter = 0
    for i, r in enumerate(rows):
        nk, ck = metrics.name_key(r["executive"]), metrics.company_key(r["company"])
        match = next((ident for ident, k, cks in known if k == nk and ck in cks), None)
        if match is None:
            counter += 1
            match = f"new:{nk}|{counter}"
            known.append((match, nk, {ck}))
        assignment[i] = match
    return assignment


def run() -> None:
    config.SETTINGS.require("database_url")
    path = (HERE / config.SEED_WORKBOOK).resolve()
    if not path.exists():
        raise SystemExit(f"Seed workbook not found: {path}")
    rows = read_workbook(path)
    unmapped = {(r["organization"], r["recognition"]) for r in rows} - set(
        programs.WORKBOOK_PROGRAM_MAP)
    if unmapped:
        raise SystemExit(f"Workbook programs not in programs.WORKBOOK_PROGRAM_MAP: {unmapped}")
    print(f"Workbook: {len(rows)} recognition rows from {path.name}")

    with connect() as conn:
        _seed_programs(conn)
        prog = {r["program_key"]: r["program_id"] for r in
                fetch_all(conn, "select program_key, program_id from recognition_program")}
        _seed_companies(conn, rows)
        comp = {r["name"]: r["company_id"] for r in
                fetch_all(conn, "select name, company_id from company")}
        exec_ids = _seed_executives(conn, rows)
        events = []
        today = date.today()
        for i, r in enumerate(rows):
            events.append({
                "executive_id": exec_ids[i],
                "program_id": prog[programs.WORKBOOK_PROGRAM_MAP[(r["organization"], r["recognition"])]],
                "recognition_year": r["year"],
                "category": r["category"],
                "published_rank": metrics.parse_rank(r["category"]),
                "title_at_recognition": r["title"],
                "company_at_recognition": r["company"],
                "company_id": comp.get(metrics.clean_company(r["company"])),
                "source_url": r["source_url"],
                "date_ingested": today,
                "notes": f"Seed workbook, tab '{r['tab']}'",
            })
        n = upsert(conn, "recognition_event", events,
                   ["executive_id", "program_id", "recognition_year", "category"], update_cols=[])
        total = fetch_all(conn, "select count(*) as n from recognition_event")[0]["n"]
        print(f"recognition_event: {n} submitted (insert-only); {total} in table")


def _seed_programs(conn) -> None:
    cols = [k for k in programs.PROGRAMS[0] if k not in ("criteria", "categories")]
    upsert(conn, "recognition_program",
           [{**{k: p[k] for k in cols}} for p in programs.PROGRAMS], ["program_key"])
    prog = {r["program_key"]: r["program_id"] for r in
            fetch_all(conn, "select program_key, program_id from recognition_program")}
    crit, cats = [], []
    for p in programs.PROGRAMS:
        pid = prog[p["program_key"]]
        for order, (key, label, desc) in enumerate(p["criteria"]):
            crit.append({"program_id": pid, "criterion_key": key, "label": label,
                         "description": desc, "display_order": order})
        for cat, weight, standing in p["categories"]:
            cats.append({"program_id": pid, "category": cat, "analyst_weight": weight,
                         "is_standing_honor": standing})
    upsert(conn, "program_criterion", crit, ["program_id", "criterion_key"])
    upsert(conn, "program_category", cats, ["program_id", "category"])
    as_of = date.fromisoformat(programs.CYCLES_AS_OF)
    upsert(conn, "recognition_cycle", [
        {"program_id": prog[k], "cycle_year": y, "status": s, "last_checked": as_of,
         "next_expected_period": programs.PENDING_EXPECTED_PERIOD if s == "pending" else None}
        for k, y, s in programs.CYCLES], ["program_id", "cycle_year"], update_cols=[])
    print(f"Programs: {len(programs.PROGRAMS)}, criteria: {len(crit)}, "
          f"categories: {len(cats)}, cycles: {len(programs.CYCLES)}")


def _seed_companies(conn, rows: list[dict]) -> None:
    names = sorted({metrics.clean_company(r["company"]) for r in rows} - {None})
    ad = {metrics.company_key(n) for n in config.AD_COMPANIES}
    upsert(conn, "company", [{
        "name": n,
        "industry": INDUSTRY_SEED.get(n),
        "industry_source": "analyst" if n in INDUSTRY_SEED else None,
        "is_aerospace_defense": metrics.company_key(n) in ad,
    } for n in names], ["name"], update_cols=[])
    missing = [n for n in names if n not in INDUSTRY_SEED]
    print(f"Companies: {len(names)} named in workbook"
          + (f"; {len(missing)} without an industry: {missing}" if missing else ""))


def _seed_executives(conn, rows: list[dict]) -> dict[int, str]:
    existing = fetch_all(conn, """
        select x.executive_id::text as executive_id, x.name_key,
               coalesce(array_agg(distinct e.company_at_recognition)
                        filter (where e.company_at_recognition is not null), '{}') as companies
        from executive x left join recognition_event e using (executive_id)
        group by x.executive_id, x.name_key""")
    for e in existing:
        e["company_keys"] = {metrics.company_key(c) for c in e["companies"]}
    plan = plan_executives(rows, existing)

    resolved: dict[str, str] = {}
    created = 0
    for i, ident in plan.items():
        if not ident.startswith("new:") or ident in resolved:
            continue
        group = [rows[j] for j, g in plan.items() if g == ident]
        name = group[0]["executive"]
        alts = sorted({r["executive"] for r in group} - {name})
        academic = any(_ACADEMIC.search(r["title"] or "") for r in group)
        with conn.cursor() as cur:
            cur.execute(
                "insert into executive (canonical_name, name_key, alternate_names, "
                "executive_type) values (%s, %s, %s, %s) returning executive_id::text",
                (name, metrics.name_key(name), alts,
                 "academic" if academic else "practitioner"))
            resolved[ident] = cur.fetchone()[0]
        created += 1
    print(f"Executives: {created} created, {len(existing)} already present")
    return {i: resolved.get(ident, ident) for i, ident in plan.items()}
