"""`run.py accomplishments` -- load "what they did" research as DRAFT accomplishments.

Input: `../research/accomplishments_*.json` (outside the public repo), each
    {"accomplishments": [{event_id, headline, what_they_did, scale_and_results,
      quantified_outcomes, timeframe, evidence_quality, source_url, source_title,
      source_quote, criteria: [{criterion_key, rationale}], themes: [...]}],
     "gaps": [{event_id, executive, note}]}

Written by research agents. Validation is strict and LOUD: an unknown event, an
off-vocabulary theme or evidence label, or a criterion that does not belong to the event's
award is reported and that item is skipped -- never silently coerced (an off-list theme
dropped quietly is exactly how a vocabulary bug hides).

Re-runnable: an accomplishment with the same event and headline is skipped, so reviewed
rows are never duplicated or reset.
"""
from __future__ import annotations

import json
from pathlib import Path

import config
from db import connect, fetch_all

RESEARCH = Path(__file__).resolve().parent.parent / "research"
MODEL_LABEL = "claude research agent (web search), 2026-10"


def validate(item: dict, events: dict, criteria: dict) -> list[str]:
    """Pure. Problems with one research item; empty list means loadable."""
    problems = []
    ev = events.get(item.get("event_id"))
    if ev is None:
        return [f"unknown event_id {item.get('event_id')!r}"]
    for k in ("headline", "what_they_did", "source_url", "evidence_quality"):
        if not (item.get(k) or "").strip():
            problems.append(f"missing {k}")
    if item.get("evidence_quality") and item["evidence_quality"] not in config.EVIDENCE_QUALITY:
        problems.append(f"evidence_quality {item['evidence_quality']!r} not in vocabulary")
    bad_themes = [t for t in item.get("themes") or [] if t not in config.THEMES]
    if bad_themes:
        problems.append(f"themes not in vocabulary: {bad_themes}")
    allowed = criteria.get(ev["program_key"], {})
    bad_crit = [c.get("criterion_key") for c in item.get("criteria") or []
                if c.get("criterion_key") not in allowed]
    if bad_crit:
        problems.append(f"criteria not defined for {ev['program_key']}: {bad_crit}")
    return problems


def run() -> None:
    config.SETTINGS.require("database_url")
    files = sorted(RESEARCH.glob("accomplishments_*.json"))
    if not files:
        raise SystemExit(f"No accomplishments_*.json in {RESEARCH}")
    with connect() as conn:
        events = {r["event_id"]: r for r in fetch_all(conn, """
            select e.event_id::text as event_id, e.executive_id::text as executive_id,
                   p.program_key, x.canonical_name
            from recognition_event e join recognition_program p using (program_id)
            join executive x using (executive_id)""")}
        criteria: dict[str, dict[str, str]] = {}
        for r in fetch_all(conn, """select p.program_key, c.criterion_key,
                                    c.criterion_id::text as criterion_id
                                    from program_criterion c
                                    join recognition_program p using (program_id)"""):
            criteria.setdefault(r["program_key"], {})[r["criterion_key"]] = r["criterion_id"]
        have = {(r["event_id"], r["headline"]) for r in fetch_all(conn, """
            select event_id::text as event_id, headline from accomplishment""")}

        added = skipped = rejected = 0
        gaps = []
        for f in files:
            data = json.loads(f.read_text(encoding="utf-8"))
            gaps += data.get("gaps") or []
            for item in data.get("accomplishments") or []:
                problems = validate(item, events, criteria)
                if problems:
                    rejected += 1
                    print(f"  SKIPPED ({f.name}) {item.get('headline')!r}: {'; '.join(problems)}")
                    continue
                if (item["event_id"], item["headline"].strip()) in have:
                    skipped += 1
                    continue
                ev = events[item["event_id"]]
                with conn.cursor() as cur:
                    cur.execute("""
                        insert into accomplishment (executive_id, event_id, headline,
                            what_they_did, scale_and_results, quantified_outcomes, timeframe,
                            evidence_quality, source_url, source_title, source_quote,
                            review_status, drafted_by, model)
                        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'draft','llm',%s)
                        returning accomplishment_id::text""",
                        (ev["executive_id"], item["event_id"], item["headline"].strip(),
                         item["what_they_did"].strip(), item.get("scale_and_results") or None,
                         item.get("quantified_outcomes") or None, item.get("timeframe") or None,
                         item["evidence_quality"], item["source_url"],
                         item.get("source_title") or None, item.get("source_quote") or None,
                         MODEL_LABEL))
                    aid = cur.fetchone()[0]
                    for c in item.get("criteria") or []:
                        cur.execute("""insert into accomplishment_criterion
                                       (accomplishment_id, criterion_id, rationale)
                                       values (%s, %s, %s) on conflict do nothing""",
                                    (aid, criteria[ev["program_key"]][c["criterion_key"]],
                                     c.get("rationale")))
                    for t in dict.fromkeys(item.get("themes") or []):
                        cur.execute("""insert into accomplishment_theme (accomplishment_id, theme)
                                       values (%s, %s) on conflict do nothing""", (aid, t))
                have.add((item["event_id"], item["headline"].strip()))
                added += 1
        with conn.cursor() as cur:
            for g in gaps:
                if g.get("event_id") in events and g.get("note"):
                    cur.execute("""insert into accomplishment_gap (event_id, note)
                                   values (%s, %s) on conflict (event_id) do update
                                   set note = excluded.note, searched_at = current_date""",
                                (g["event_id"], g["note"]))
    print(f"Accomplishments: {added} drafts added, {skipped} already present, "
          f"{rejected} skipped for validation problems (listed above)")
    print(f"Research gaps (no substantive source found): {len(gaps)}")
    for g in gaps:
        print(f"  - {g.get('executive')}: {g.get('note')}")
