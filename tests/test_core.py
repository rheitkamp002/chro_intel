"""Offline tests: scoring, matching, the seed plan and programs.py integrity.

No pytest -- run as a script, like the sibling apps:
    $env:PYTHONPATH="."; .venv\\Scripts\\python.exe tests\\test_core.py
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

import config
import metrics
import programs
import seed

WINDOW = (2025, 2026)


def ev(org="NAHR", year=2025, weight=5, role="core", status="published", standing=False,
       cat_weight=None, cat_standing=None, override=None):
    return {"organization": org, "recognition_year": year, "program_weight": weight,
            "category_weight": cat_weight, "analyst_weight_override": override,
            "scoring_role": role, "status": status, "program_standing": standing,
            "category_standing": cat_standing}


# ----- name / company matching -----
def test_name_key_strips_honorific_and_initial():
    assert metrics.name_key("Dr. Nabil Batawi") == metrics.name_key("Nabil Batawi")
    assert metrics.name_key("Daniel G. Chappell") == "daniel chappell"
    assert metrics.name_key("Jim O'Gorman") == "jim ogorman"
    assert metrics.name_key("Jim O’Gorman") == metrics.name_key("Jim O'Gorman")


def test_name_key_keeps_hyphenated_surnames_distinct_from_first_names():
    assert metrics.name_key("Kristi Cappelletti-Matthews") == "kristi cappelletti matthews"


def test_company_key_formerly_and_suffixes():
    assert metrics.company_key("Formerly Delta Dental of Virginia") == "delta dental of virginia"
    assert metrics.company_key("The Coca-Cola Company") == metrics.company_key("Coca-Cola")
    assert metrics.clean_company("  ") is None


def test_says_former():
    assert metrics.says_former("Formerly CHRO", None)
    assert not metrics.says_former("CHRO", "Acme")


def test_parse_rank():
    assert metrics.parse_rank("Rank #7") == 7
    assert metrics.parse_rank("Class of 2025") is None
    assert metrics.parse_rank(None) is None


# ----- scoring -----
def test_weight_precedence():
    assert metrics.effective_weight(ev(weight=4)) == 4
    assert metrics.effective_weight(ev(weight=4, cat_weight=3)) == 3
    assert metrics.effective_weight(ev(weight=4, cat_weight=3, override=2)) == 2


def test_spec_example_breitfelder():
    s = metrics.summarize([ev("NAHR", 2025, 5, standing=True), ev("N2Growth", 2025, 3)], WINDOW)
    assert (s["strength"], s["breadth"], s["frequency"], s["composite"]) == (5, 2, 2, 8)


def test_secondary_excluded_unless_requested():
    evs = [ev("N2Growth", 2025, 3), ev("HRO Today", 2026, 2, role="secondary")]
    s = metrics.summarize(evs, WINDOW)
    assert (s["breadth"], s["composite"], s["secondary_count"]) == (1, 3, 1)
    s2 = metrics.summarize(evs, WINDOW, include_secondary=True)
    assert (s2["breadth"], s2["composite"]) == (2, 5)


def test_standing_honor_counts_outside_window_but_not_in_frequency():
    s = metrics.summarize([ev("NAHR", 2019, 5, standing=True)], WINDOW)
    assert (s["strength"], s["breadth"], s["frequency"]) == (5, 1, 0)


def test_annual_award_outside_window_does_not_count():
    s = metrics.summarize([ev("HR Executive", 2022, 4)], WINDOW)
    assert s["strength"] == 0 and s["top"] is None


def test_category_standing_overrides_program():
    lifetime = ev("HRO Today", 2018, 4, cat_weight=4, cat_standing=True)
    assert metrics.summarize([lifetime], WINDOW)["strength"] == 4


def test_unscored_and_unpublished_never_count():
    evs = [ev(role="unscored"), ev(status="needs_verification")]
    assert metrics.summarize(evs, WINDOW, include_secondary=True)["composite"] == 0


def test_window_is_rolling():
    from datetime import date
    assert config.analysis_window(date(2026, 10, 15)) == (2025, 2026)
    assert config.analysis_window(date(2027, 1, 2)) == (2026, 2027)


def test_fmt_weight():
    assert metrics.fmt_weight(5.0) == "5" and metrics.fmt_weight(2.5) == "2.5"


# ----- seed plan -----
def _row(name, company, year=2025):
    return {"executive": name, "company": company, "year": year}


def test_plan_never_merges_on_name_alone():
    plan = seed.plan_executives([_row("Robert Smith", "A"), _row("Robert Smith", "B")], [])
    assert plan[0] != plan[1]


def test_plan_merges_name_and_company():
    plan = seed.plan_executives(
        [_row("Riya Sood", "OpSec Security"), _row("Riya Sood", "OpSec Security", 2026)], [])
    assert plan[0] == plan[1]


def test_plan_joins_existing_executive():
    existing = [{"executive_id": "abc", "name_key": "ola snow",
                 "company_keys": {metrics.company_key("Cardinal Health")}}]
    assert seed.plan_executives([_row("Ola Snow", "Cardinal Health")], existing)[0] == "abc"


def test_workbook_plan_matches_known_overlaps():
    path = (Path(seed.HERE) / config.SEED_WORKBOOK).resolve()
    if not path.exists():
        print("  (skipped: workbook not present)")
        return
    rows = seed.read_workbook(path)
    plan = seed.plan_executives(rows, [])
    ident = {r["executive"]: plan[i] for i, r in enumerate(rows)}
    by_ident: dict[str, list[str]] = {}
    for i, r in enumerate(rows):
        by_ident.setdefault(plan[i], []).append(r["executive"])
    # People recognized more than once in the workbook, each at one employer.
    for name, times in [("Matthew Breitfelder", 2), ("Ola Snow", 2), ("Donna Morris", 2),
                        ("Paul Gregory", 2), ("Logan Carmichael", 2), ("Ivory Harris", 2),
                        ("Garri Brown", 2), ("Deborah Maynard", 2), ("Riya Sood", 2)]:
        assert len(by_ident[ident[name]]) == times, name
    assert all(k in programs.WORKBOOK_PROGRAM_MAP
               for k in {(r["organization"], r["recognition"]) for r in rows})


# ----- programs.py integrity -----
def test_programs_have_identical_keys():
    keys = set(programs.PROGRAMS[0])
    for p in programs.PROGRAMS:
        assert set(p) == keys, p["program_key"]


def test_programs_unique_and_cycles_reference_them():
    ks = [p["program_key"] for p in programs.PROGRAMS]
    assert len(ks) == len(set(ks))
    assert {k for k, _, _ in programs.CYCLES} <= set(ks)
    assert set(programs.WORKBOOK_PROGRAM_MAP.values()) <= set(ks)


def test_program_vocabularies_match_schema():
    for p in programs.PROGRAMS:
        assert p["scoring_role"] in ("core", "secondary", "unscored")
        assert all(s in ("available", "pending") for _, _, s in programs.CYCLES)


def test_nahr_and_lifetime_are_standing():
    by = {p["program_key"]: p for p in programs.PROGRAMS}
    assert by["NAHR_FELLOW"]["is_standing_honor"]
    assert ("Lifetime Achievement", 4, True) in by["HRO_COY"]["categories"]


def test_industry_seed_uses_vocabulary():
    assert set(seed.INDUSTRY_SEED.values()) <= set(config.INDUSTRIES)


def test_themes_are_the_spec_24():
    assert len(config.THEMES) == 24 == len(set(config.THEMES))


def main() -> int:
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
