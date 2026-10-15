"""`run.py roster` -- load peer-set research (company context + current CHRO) as DRAFTS.

Inputs, in `../research/` (OUTSIDE the repo -- the repo is public, research never goes in it):
  fortune100_companies.csv    2026 Fortune 500 ranks 1-100 (fortune.com, fetched 2026-10-15)
  f100_chro_*.csv             current CHRO per Fortune 100 company
  ad_extra_chro.csv           current CHRO for A&D-tracked companies outside the Fortune 100

What it writes:
  company            context columns UPDATED from the Fortune file (rank, revenue, employees,
                     HQ, ownership, ticker). Industry only where still NULL.
  peer_set           F100_2026 and AD_TRACKED, with company_peer_set membership
  executive          matched on name AND company (never name alone), else created
  executive_role     the current role (is_current) and, when stated, the prior role --
                     review_status 'draft'. Nothing shows in the dashboard until approved.

Re-runnable: a role already present for the same executive, company and title is skipped,
so re-running never duplicates drafts and never touches a reviewed row.
"""
from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path

import config
import metrics
from db import connect, fetch_all, upsert

RESEARCH = Path(__file__).resolve().parent.parent / "research"
FORTUNE_URL = "https://fortune.com/ranking/fortune500/"

# Fortune's name -> the name this database already uses for the same company.
COMPANY_ALIASES = {
    "Verizon Communications": "Verizon",
    "International Business Machines": "IBM",
    "Cisco Systems": "Cisco",
    "JPMorgan Chase": "JPMorganChase",
    "Coca-Cola": "The Coca-Cola Company",
}

# Broad industry, ANALYST-ASSIGNED 2026-10-15 from general knowledge (industry_source
# 'analyst'). Only fills companies whose industry is still NULL.
INDUSTRY_F100: dict[str, str] = {
    "Amazon": "Retail", "Walmart": "Retail", "UnitedHealth Group": "Healthcare & Life Sciences",
    "Apple": "Technology", "Alphabet": "Technology", "CVS Health": "Healthcare & Life Sciences",
    "Berkshire Hathaway": "Conglomerate", "McKesson": "Healthcare & Life Sciences",
    "Exxon Mobil Holdings": "Energy", "Cencora": "Healthcare & Life Sciences",
    "Microsoft": "Technology", "JPMorgan Chase": "Financial Services", "Costco Wholesale": "Retail",
    "Cigna Group": "Healthcare & Life Sciences", "Cardinal Health": "Healthcare & Life Sciences",
    "Nvidia": "Technology", "Meta Platforms": "Technology",
    "Elevance Health": "Healthcare & Life Sciences", "Centene": "Healthcare & Life Sciences",
    "Bank of America": "Financial Services", "Chevron": "Energy",
    "Ford Motor": "Industrials & Manufacturing", "General Motors": "Industrials & Manufacturing",
    "Citigroup": "Financial Services", "Home Depot": "Retail", "Fannie Mae": "Financial Services",
    "Kroger": "Retail", "Verizon Communications": "Telecommunications", "Phillips 66": "Energy",
    "Marathon Petroleum": "Energy", "StoneX Group": "Financial Services",
    "State Farm Insurance": "Insurance", "Freddie Mac": "Financial Services",
    "Humana": "Healthcare & Life Sciences", "AT&T": "Telecommunications",
    "Goldman Sachs Group": "Financial Services", "Comcast": "Telecommunications",
    "Wells Fargo": "Financial Services", "Morgan Stanley": "Financial Services",
    "Valero Energy": "Energy", "Dell Technologies": "Technology", "Target": "Retail",
    "Tesla": "Industrials & Manufacturing", "Walt Disney": "Telecommunications",
    "Johnson & Johnson": "Healthcare & Life Sciences", "PepsiCo": "Consumer Goods",
    "Boeing": "Aerospace & Defense", "UPS": "Transportation & Logistics",
    "RTX": "Aerospace & Defense", "FedEx": "Transportation & Logistics",
    "Progressive": "Insurance", "Lowe's": "Retail", "Energy Transfer": "Energy",
    "Procter & Gamble": "Consumer Goods", "Sysco": "Transportation & Logistics",
    "American Express": "Financial Services", "Albertsons": "Retail",
    "Archer Daniels Midland": "Consumer Goods", "MetLife": "Insurance",
    "HCA Healthcare": "Healthcare & Life Sciences", "Lockheed Martin": "Aerospace & Defense",
    "New York Life Insurance": "Insurance", "Capital One Financial": "Financial Services",
    "Allstate": "Insurance", "Caterpillar": "Industrials & Manufacturing",
    "International Business Machines": "Technology", "Eli Lilly": "Healthcare & Life Sciences",
    "Merck": "Healthcare & Life Sciences", "Nationwide": "Insurance", "Broadcom": "Technology",
    "Delta Air Lines": "Transportation & Logistics", "Publix Super Markets": "Retail",
    "Pfizer": "Healthcare & Life Sciences", "TD Synnex": "Technology",
    "ConocoPhillips": "Energy", "Galaxy Digital": "Financial Services",
    "AbbVie": "Healthcare & Life Sciences", "Prudential Financial": "Insurance",
    "TJX": "Retail", "Performance Food Group": "Transportation & Logistics",
    "United Airlines Holdings": "Transportation & Logistics", "Oracle": "Technology",
    "Cisco Systems": "Technology", "HP": "Technology",
    "Charter Communications": "Telecommunications",
    "American Airlines Group": "Transportation & Logistics", "Tyson Foods": "Consumer Goods",
    "Intel": "Technology", "Enterprise Products Partners": "Energy",
    "Ingram Micro Holding": "Technology", "General Dynamics": "Aerospace & Defense",
    "Uber Technologies": "Technology", "United Services Automobile Assn.": "Insurance",
    "TIAA": "Financial Services", "Liberty Mutual Insurance Group": "Insurance",
    "Travelers": "Insurance", "Bristol-Myers Squibb": "Healthcare & Life Sciences",
    "Coca-Cola": "Consumer Goods", "Nike": "Consumer Goods",
    "Massachusetts Mutual Life Insurance": "Insurance",
    "Northrop Grumman": "Aerospace & Defense", "L3Harris Technologies": "Aerospace & Defense",
    "Huntington Ingalls Industries": "Aerospace & Defense",
    "Palantir Technologies": "Technology",
}

ROLE_COLS = ("executive_id", "company_id", "company_name_stated", "title", "role_level",
             "start_date", "start_precision", "is_current", "hire_type", "source_url",
             "source_type", "second_source_url", "confidence", "verified_date",
             "review_status", "research_batch", "notes")


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return [{k.strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(fh)]


def _int(s: str) -> int | None:
    s = s.replace(",", "").strip()
    return int(float(s)) if s else None


def db_name(fortune_name: str) -> str:
    """Pure. The company name to store, honoring aliases to existing rows."""
    return COMPANY_ALIASES.get(fortune_name, fortune_name)


def split_prior(prior: str) -> tuple[str, str] | None:
    """Pure. 'SVP HR, Acme Corp' -> ('SVP HR', 'Acme Corp'). Splits on the LAST comma."""
    if not prior or "," not in prior:
        return None
    title, company = prior.rsplit(",", 1)
    return (title.strip(), company.strip()) if title.strip() and company.strip() else None


def run() -> None:
    config.SETTINGS.require("database_url")
    fortune = _read(RESEARCH / "fortune100_companies.csv")
    chro_files = sorted(RESEARCH.glob("f100_chro_*.csv")) + sorted(RESEARCH.glob("ad_extra_chro.csv"))
    chros = [r for f in chro_files for r in _read(f)]
    print(f"Fortune rows: {len(fortune)}; CHRO rows: {len(chros)} from "
          f"{[f.name for f in chro_files]}")

    with connect() as conn:
        _companies(conn, fortune)
        comp = {r["name"]: r["company_id"] for r in
                fetch_all(conn, "select name, company_id from company")}
        _peer_sets(conn, fortune, comp)
        _roles(conn, chros, comp)


def _companies(conn, fortune: list[dict]) -> None:
    existing = {r["name"] for r in fetch_all(conn, "select name from company")}
    ad = {metrics.company_key(n) for n in config.AD_COMPANIES + config.AD_TRACKED}
    rows = []
    for f in fortune:
        name = db_name(f["company"])
        rows.append({
            "name": name, "ticker": f["ticker"] or None,
            "fortune_rank": _int(f["fortune_rank"]), "fortune_list_year": _int(f["list_year"]),
            "revenue_usd_m": _int(f["revenue_usd_m"]), "employees": _int(f["employees"]),
            "hq_country": "United States", "ownership": f["ownership"] or None,
            "size_source_url": FORTUNE_URL,
            "is_aerospace_defense": metrics.company_key(name) in ad,
        })
    upsert(conn, "company", rows, ["name"])
    extra = [n for n in config.AD_TRACKED if n not in {r["name"] for r in rows}]
    upsert(conn, "company", [{"name": n, "is_aerospace_defense": True} for n in extra],
           ["name"], update_cols=["is_aerospace_defense"])
    with conn.cursor() as cur:
        for fname, ind in INDUSTRY_F100.items():
            cur.execute("update company set industry = %s, industry_source = 'analyst' "
                        "where name = %s and industry is null", (ind, db_name(fname)))
    new = len({r["name"] for r in rows} - existing)
    print(f"Companies: {len(rows)} Fortune rows upserted ({new} new); "
          f"{len(extra)} A&D-only ensured: {extra}")


def _peer_sets(conn, fortune: list[dict], comp: dict) -> None:
    upsert(conn, "peer_set", [
        {"peer_set_key": "F100_2026", "label": "Fortune 100 (2026 list)",
         "description": "Ranks 1-100 of the 2026 Fortune 500 (fiscal-2025 revenue). A census: "
                        "every company's CHRO, recognized or not.",
         "source_url": FORTUNE_URL, "as_of": date(2026, 10, 15), "is_complete": False},
        {"peer_set_key": "AD_TRACKED", "label": "A&D tracked companies",
         "description": "The 8 companies tracked by the A&D Intelligence Workbench, force-added "
                        "whatever their Fortune rank.",
         "source_url": None, "as_of": date(2026, 10, 15), "is_complete": False},
    ], ["peer_set_key"], update_cols=["label", "description", "source_url", "as_of"])
    members = [{"company_id": comp[db_name(f["company"])], "peer_set_key": "F100_2026",
                "rank_in_set": _int(f["fortune_rank"])} for f in fortune]
    members += [{"company_id": comp[n], "peer_set_key": "AD_TRACKED", "rank_in_set": None}
                for n in config.AD_TRACKED]
    upsert(conn, "company_peer_set", members, ["company_id", "peer_set_key"])
    print(f"Peer sets: F100_2026 {len(fortune)} members, AD_TRACKED {len(config.AD_TRACKED)}")


def strip_ticker(name: str) -> str:
    """Pure. 'Northrop Grumman (NOC)' -> 'Northrop Grumman'."""
    return re.sub(r"\s*\([A-Z.\-]{1,6}\)\s*$", "", name or "").strip()


def _resolve_company(name: str, comp: dict) -> str | None:
    n = db_name(strip_ticker(name))
    if n in comp:
        return comp[n]
    key = metrics.company_key(n)
    hits = [cid for cname, cid in comp.items() if metrics.company_key(cname) == key]
    return hits[0] if len(hits) == 1 else None


def _roles(conn, chros: list[dict], comp: dict) -> None:
    people = fetch_all(conn, """
        select x.executive_id::text as executive_id, x.name_key,
               array_remove(array_agg(distinct e.company_id::text), null)
               || array_remove(array_agg(distinct r.company_id::text), null) as company_ids
        from executive x
        left join recognition_event e using (executive_id)
        left join executive_role r using (executive_id)
        group by x.executive_id, x.name_key""")
    have = {(r["executive_id"], r["company_id"], r["title"]) for r in fetch_all(conn, """
        select executive_id::text as executive_id, company_id::text as company_id, title
        from executive_role""")}
    today = date.today()
    created_x = added = skipped = blank = 0
    for c in chros:
        if not c.get("chro_name"):
            blank += 1
            continue
        cid = _resolve_company(c["company"], comp)
        if cid is None:
            raise SystemExit(f"roster: company not found for CHRO row: {c['company']!r}")
        cid = str(cid)
        nk = metrics.name_key(c["chro_name"])
        match = next((p for p in people if p["name_key"] == nk and cid in p["company_ids"]), None)
        if match is None:
            with conn.cursor() as cur:
                cur.execute("insert into executive (canonical_name, name_key) values (%s, %s) "
                            "returning executive_id::text", (c["chro_name"], nk))
                xid = cur.fetchone()[0]
            people.append({"executive_id": xid, "name_key": nk, "company_ids": [cid]})
            created_x += 1
        else:
            xid = match["executive_id"]
        batch = "AD_TRACKED" if not c.get("fortune_rank") else "F100_2026"
        roles = [_role(xid, cid, db_name(strip_ticker(c["company"])), c, today, batch)]
        prior = split_prior(c.get("prior_role", ""))
        if prior:
            pcid = _resolve_company(prior[1], comp)
            roles.append({**_role(xid, str(pcid) if pcid else None, prior[1], c, today, batch),
                          "title": prior[0], "role_level": None, "start_date": None,
                          "start_precision": None, "is_current": False, "hire_type": None,
                          "notes": "Prior role as stated by the research source."})
        for r in roles:
            if (xid, r["company_id"], r["title"]) in have:
                skipped += 1
                continue
            _insert_role(conn, r)
            have.add((xid, r["company_id"], r["title"]))
            added += 1
    print(f"Roles: {added} draft rows added, {skipped} already present; "
          f"{created_x} new executives; {blank} companies with no CHRO identified")


def _role(xid, cid, cname, c, today, batch) -> dict:
    level = c.get("role_level") or None
    return {
        "executive_id": xid, "company_id": cid, "company_name_stated": cname,
        "title": c["title"] or "Title not stated",
        "role_level": level if level in config.ROLE_LEVELS else None,
        "start_date": date.fromisoformat(c["start_date"]) if c.get("start_date") else None,
        "start_precision": c.get("start_precision") or None,
        "is_current": True,
        "hire_type": c.get("hire_type") or None,
        "source_url": c.get("source_url") or None,
        "source_type": c.get("source_type") if c.get("source_type") in config.ROLE_SOURCE_TYPES else None,
        "second_source_url": c.get("second_source_url") or None,
        "confidence": c.get("confidence") if c.get("confidence") in ("high", "medium", "low") else None,
        "verified_date": today, "review_status": "draft", "research_batch": batch,
        "notes": c.get("notes") or None,
    }


def _insert_role(conn, r: dict) -> None:
    cols = list(ROLE_COLS)
    with conn.cursor() as cur:
        cur.execute(f"insert into executive_role ({', '.join(cols)}) values "
                    f"({', '.join(['%s'] * len(cols))})", [r[k] for k in cols])
