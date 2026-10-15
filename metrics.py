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


def name_key(name: str | None) -> str:
    """Pure. Normalized person name for duplicate detection. Never used ALONE to merge."""
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    # Apostrophes join, not split: "O'Gorman" must not leave an "o" that reads as an initial.
    s = re.sub(r"['’]", "", s.lower())
    s = re.sub(r"[^\w\s-]", " ", s)
    parts = [p for p in re.split(r"[\s-]+", s) if p]
    while parts and parts[0] in _HONORIFICS:
        parts = parts[1:]
    # Drop single-letter middle initials: "Daniel G. Chappell" == "Daniel Chappell".
    if len(parts) > 2:
        parts = [parts[0]] + [p for p in parts[1:-1] if len(p) > 1] + [parts[-1]]
    return " ".join(parts)


def clean_company(name: str | None) -> str | None:
    """Pure. The company a source names, without a 'Formerly ' prefix. None if blank."""
    s = (name or "").strip()
    s = re.sub(r"^formerly\s+", "", s, flags=re.I)
    return s or None


def company_key(name: str | None) -> str:
    """Pure. Normalized company name for matching."""
    s = (clean_company(name) or "").lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\b(the|inc|corp|corporation|co|company|llc|plc|ltd|group)\b", " ", s)
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


def fmt_weight(x: float | int | None) -> str:
    """Pure. 5.0 -> '5', 2.5 -> '2.5', None -> '—'."""
    if x is None:
        return "—"
    return f"{x:g}"
