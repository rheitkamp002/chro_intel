"""Pure scoring and matching logic. No database, no I/O -- everything here is unit-tested.

THE SCORE IS A RECOGNITION SIGNAL, NOT A QUALITY RANKING (spec sections 9, 29-30).

Definitions, over QUALIFYING events (status 'published', scoring_role 'core', and either
inside the rolling window or a standing honor such as NAHR Fellowship):
  strength   max effective weight
  breadth    count of distinct organizations
  frequency  count of qualifying events INSIDE the window (standing honors from earlier
             years count toward strength/breadth/composite, not frequency)
  composite  sum of effective weights -- shown, but secondary to strength and breadth

Effective weight = event override, else category weight, else program weight.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable

_HONORIFICS = ("dr", "mr", "mrs", "ms", "prof")
_SUFFIXES = ("jr", "sr", "ii", "iii", "iv", "phd", "md")


def name_key(name: str | None) -> str:
    """Pure. Normalized person name for duplicate detection. Never used ALONE to merge."""
    return name_keys(name)[0]


def name_keys(name: str | None) -> tuple[str, str | None]:
    """Pure. (formal key, parenthetical-variant key or None).

    "Christine M. (Christy) Pambianchi" -> ("christine pambianchi", "christy pambianchi").
    The parenthesis may hold a nickname (Christy) OR a former surname ("Darcie (Henry)
    Cakaric"), so it is never trusted alone: duplicate detection matches on EITHER key and
    a person decides. MEASURED 2026-10-15: the Pambianchi pair had been split in two.
    """
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    nick = re.search(r"\(([^)]+)\)", s)
    s = re.sub(r"\([^)]*\)", " ", s)
    # Apostrophes join, not split: "O'Gorman" must not leave an "o" that reads as an initial.
    s = re.sub(r"['’]", "", s.lower())
    s = re.sub(r"[^\w\s-]", " ", s)
    parts = [p for p in re.split(r"[\s-]+", s) if p]
    while parts and parts[0] in _HONORIFICS:
        parts = parts[1:]
    while len(parts) > 2 and parts[-1] in _SUFFIXES:
        parts = parts[:-1]
    # Drop single-letter middle initials: "Daniel G. Chappell" == "Daniel Chappell".
    if len(parts) > 2:
        parts = [parts[0]] + [p for p in parts[1:-1] if len(p) > 1] + [parts[-1]]
    formal = " ".join(parts)
    alt = None
    if nick and parts:
        n = re.sub(r"[^a-z]", "", nick.group(1).lower())
        if len(n) > 1:
            alt = " ".join([n] + parts[1:])
    return formal, alt if alt != formal else None


def clean_company(name: str | None) -> str | None:
    """Pure. The company a source names, without a 'Formerly ' prefix. None if blank."""
    s = (name or "").strip()
    s = re.sub(r"^formerly\s+", "", s, flags=re.I)
    return s or None


def company_key(name: str | None) -> str:
    """Pure. Normalized company name for matching."""
    s = (clean_company(name) or "").lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\b(the|inc|corp|corporation|co|company|companies|llc|plc|ltd|group|holding|"
               r"holdings)\b", " ", s)
    return " ".join(s.split())


def says_former(*texts: str | None) -> bool:
    """Pure. Does the source say the person has left this role?"""
    return any(re.match(r"\s*formerly\b", t or "", flags=re.I) for t in texts)


def parse_rank(category: str | None) -> int | None:
    """Pure. 'Rank #7' -> 7; anything else -> None."""
    m = re.search(r"rank\s*#?\s*(\d+)", category or "", flags=re.I)
    return int(m.group(1)) if m else None


def effective_weight(event: dict) -> float:
    """Pure. Override > category weight > program weight."""
    for k in ("analyst_weight_override", "category_weight", "program_weight"):
        if event.get(k) is not None:
            return float(event[k])
    raise ValueError(f"event has no weight: {event}")


def is_standing(event: dict) -> bool:
    """Pure. Category-level standing flag wins when the category row exists."""
    if event.get("category_standing") is not None:
        return bool(event["category_standing"])
    return bool(event.get("program_standing"))


def qualifies(event: dict, window: Iterable[int], roles: Iterable[str] = ("core",)) -> bool:
    """Pure. Does this event count toward the score?"""
    if event.get("status") != "published" or event.get("scoring_role") not in tuple(roles):
        return False
    return event["recognition_year"] in tuple(window) or is_standing(event)


def summarize(events: list[dict], window: Iterable[int],
              include_secondary: bool = False) -> dict:
    """Pure. Strength / breadth / frequency / composite plus the headline events."""
    window = tuple(window)
    roles = ("core", "secondary") if include_secondary else ("core",)
    q = [e for e in events if qualifies(e, window, roles)]
    secondary = [e for e in events if e.get("status") == "published"
                 and e.get("scoring_role") == "secondary" and e["recognition_year"] in window]
    if not q:
        return {"strength": 0.0, "breadth": 0, "frequency": 0, "composite": 0.0,
                "top": None, "latest": None, "latest_year": None,
                "secondary_count": len(secondary)}
    w = {id(e): effective_weight(e) for e in q}
    top = max(q, key=lambda e: (w[id(e)], e["recognition_year"]))
    in_window = [e for e in q if e["recognition_year"] in window]
    latest = max(q, key=lambda e: (e["recognition_year"], w[id(e)]))
    return {
        "strength": max(w.values()),
        "breadth": len({e["organization"] for e in q}),
        "frequency": len(in_window),
        "composite": sum(w.values()),
        "top": top,
        "latest": latest,
        "latest_year": latest["recognition_year"],
        "secondary_count": len(secondary),
    }


_TITLE_STOP = {"and", "of", "the", "&", "officer", "chief", "vice", "president", "senior",
               "executive", "evp", "svp", "vp", "global", "group", "head"}


def title_key(title: str | None) -> frozenset[str]:
    """Pure. Distinctive words of a title, for 'is this the same role?' comparisons."""
    words = re.findall(r"[a-z]+", (title or "").lower())
    return frozenset(w for w in words if w not in _TITLE_STOP)


def same_role(a: dict, b: dict) -> bool:
    """Pure. Two role rows describe the same job: same company, and the same start year
    when both state one, else overlapping distinctive title words (or both empty)."""
    if company_key(a.get("company")) != company_key(b.get("company")):
        return False
    ya, yb = a.get("start_year"), b.get("start_year")
    if ya and yb:
        return ya == yb
    ka, kb = title_key(a.get("title")), title_key(b.get("title"))
    if not ka or not kb:
        return ka == kb
    return len(ka & kb) / len(ka | kb) >= 0.5


def _years(start, end) -> float:
    return max(0.0, (end - start).days / 365.25)


def career_summary(roles: list[dict], today=None) -> dict:
    """Pure. Derived career measures from APPROVED roles.

    roles: dicts with start_date, end_date, is_current, role_level, function.
    Years as CHRO merges overlapping CHRO roles (no double counting). A CHRO role without a
    start date is counted in `chro_roles` but adds no years -- stated as a lower bound.
    """
    from datetime import date as _d
    today = today or _d.today()
    chro = [r for r in roles if r.get("role_level") == "CHRO"]
    # Drop open-ended spans BEFORE sorting: two roles with the same start where one has no
    # end would compare a date with None and raise. MEASURED 2026-10-15 in production.
    spans = sorted(
        (s, e) for s, e in (
            (r["start_date"], r["end_date"] or (today if r.get("is_current") else None))
            for r in chro if r.get("start_date"))
        if e)
    merged: list[list] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    starts = [r["start_date"] for r in roles if r.get("start_date")]
    chro_starts = [r["start_date"] for r in chro if r.get("start_date")]
    functions = {r.get("function") for r in roles if r.get("function")}
    non_hr = sorted(functions - {"HR", "Other"})
    return {
        "years_as_chro": round(sum(_years(s, e) for s, e in merged), 1) if merged else None,
        "years_as_chro_is_lower_bound": any(not r.get("start_date") for r in chro),
        "chro_roles": len(chro),
        "first_chro_year": min(chro_starts).year if chro_starts else None,
        "years_to_chro": (round(_years(min(starts), min(chro_starts)), 1)
                          if starts and chro_starts else None),
        "non_hr_functions": non_hr,
        "has_non_hr_experience": bool(non_hr) if functions else None,
        "employers": len({company_key(r.get("company_name_stated") or r.get("company"))
                          for r in roles}),
    }


def recipient_profile(people: list[dict]) -> dict:
    """Pure. The 'typical recipient' of an award, from per-person facts.

    people: one dict per recipient with keys (None = not known):
      tenure_years, years_as_chro, chro_roles, hire_type, other_awards, boards_on_record,
      non_hr, industry, has_career
    Every statistic carries `n` -- how many recipients it rests on -- because career data
    is incomplete and a median of 3 must not read like a median of 30.
    """
    from collections import Counter
    from statistics import median

    def med(key):
        vals = [p[key] for p in people if p.get(key) is not None]
        return {"value": round(median(vals), 1) if vals else None, "n": len(vals)}

    def share(key, pred):
        vals = [p[key] for p in people if p.get(key) is not None]
        return {"value": round(100 * sum(1 for v in vals if pred(v)) / len(vals))
                if vals else None, "n": len(vals)}

    with_career = [p for p in people if p.get("has_career")]
    inds = Counter(p["industry"] for p in people if p.get("industry")
                   and p["industry"] != "Not classified")
    return {
        "recipients": len(people),
        "tenure_years": med("tenure_years"),
        "years_as_chro": med("years_as_chro"),
        "chro_roles": med("chro_roles"),
        "internal_hire_pct": share("hire_type", lambda v: v == "internal"),
        "other_awards_pct": share("other_awards", lambda v: v > 0),
        # Seats are only knowable for people whose career was researched; the share says
        # "on record", never "holds none".
        "boards_pct": {"value": round(100 * sum(1 for p in with_career
                                                if (p.get("boards_on_record") or 0) > 0)
                                      / len(with_career)) if with_career else None,
                       "n": len(with_career)},
        "non_hr_pct": share("non_hr", lambda v: bool(v)),
        "top_industries": inds.most_common(3),
    }


def fmt_weight(x: float | int | None) -> str:
    """Pure. 5.0 -> '5', 2.5 -> '2.5', None -> '—'."""
    if x is None:
        return "—"
    return f"{x:g}"
