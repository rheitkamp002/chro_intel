"""Review-queue writes: approve or reject research drafts. Called from the dashboard.

Approving a CURRENT role demotes any other approved current role for the same executive
(is_current -> false) in the same transaction, so `ux_role_one_current` can never fire and
an executive never shows two current jobs. Nothing is deleted: a rejected draft stays in the
table as 'rejected', so re-running `roster` cannot resurrect it (roster skips rows it has).
"""
from __future__ import annotations

from db import connect, fetch_all


def draft_roles() -> list[dict]:
    with connect() as conn:
        return fetch_all(conn, """
            select r.role_id::text as role_id, r.executive_id::text as executive_id,
                   x.canonical_name, r.company_name_stated, r.title, r.role_level, r.function,
                   r.end_date,
                   r.start_date, r.start_precision, r.is_current, r.hire_type,
                   r.source_url, r.source_type, r.second_source_url, r.confidence,
                   r.research_batch, r.notes, c.fortune_rank
            from executive_role r
            join executive x using (executive_id)
            left join company c using (company_id)
            where r.review_status = 'draft'
            order by r.is_current desc, c.fortune_rank nulls last, x.canonical_name""")


def group_duplicates(rows: list[dict]) -> dict[str, list[dict]]:
    """Pure. Group executives whose name_key OR alt_name_key coincide (any pairing).

    Returns {group key: [rows]} for groups of 2+. Grouping is transitive (union-find).
    """
    parent = list(range(len(rows)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    first_with: dict[str, int] = {}
    for i, r in enumerate(rows):
        for k in (r.get("name_key"), r.get("alt_name_key")):
            if not k:
                continue
            if k in first_with:
                parent[find(i)] = find(first_with[k])
            else:
                first_with[k] = i
    groups: dict[int, list[dict]] = {}
    for i, r in enumerate(rows):
        groups.setdefault(find(i), []).append(r)
    return {min(g, key=lambda r: r["name_key"])["name_key"]: g
            for g in groups.values() if len(g) > 1}


def possible_duplicates() -> list[dict]:
    """Executives who may be the same person (matching name keys), with their employers."""
    with connect() as conn:
        rows = fetch_all(conn, """
            select x.name_key, x.alt_name_key, x.executive_id::text as executive_id,
                   x.canonical_name,
                   coalesce((select string_agg(distinct c, ', ') from (
                       select e.company_at_recognition as c from recognition_event e
                       where e.executive_id = x.executive_id
                       union select r.company_name_stated from executive_role r
                       where r.executive_id = x.executive_id) s), '') as companies
            from executive x""")
    out = []
    for key, group in sorted(group_duplicates(rows).items()):
        out += [{**r, "name_key": key} for r in sorted(group, key=lambda r: r["canonical_name"])]
    return out


def merge_executives(keep_id: str, drop_id: str) -> None:
    """A person decided these are the same individual. Move everything to `keep_id`.

    Recognition events keep their own title/company AT recognition -- history is not
    rewritten, only re-attached. The dropped name is kept as an alternate name.
    """
    if keep_id == drop_id:
        return
    with connect() as conn:
        with conn.cursor() as cur:
            merge_in(cur, keep_id, drop_id)


def merge_in(cur, keep_id: str, drop_id: str) -> None:
    """The merge, inside the caller's transaction (so a test can roll it back)."""
    # coalesce: identical names leave NO alternates, and array_agg over zero rows is NULL,
    # which the NOT NULL column rejects. MEASURED 2026-10-15 on the first real merge.
    cur.execute("""
        update executive k set alternate_names = coalesce((
            select array_agg(distinct n) from unnest(
                k.alternate_names || d.alternate_names || array[d.canonical_name]) n
            where n <> k.canonical_name), '{}'), refreshed_at = now()
        from executive d where k.executive_id = %s and d.executive_id = %s""",
                (keep_id, drop_id))
    # Two approved CURRENT roles would collide on ux_role_one_current once both belong to
    # one person. Keep the most recent (latest start, then latest verification) as current.
    cur.execute("""
        update executive_role set is_current = false, refreshed_at = now()
        where role_id in (
            select role_id from executive_role
            where executive_id in (%s, %s) and is_current and review_status = 'approved'
            order by start_date desc nulls last, verified_date desc nulls last
            offset 1)""", (keep_id, drop_id))
    for table in ("recognition_event", "executive_role", "accomplishment"):
        cur.execute(f"update {table} set executive_id = %s where executive_id = %s",
                    (keep_id, drop_id))
    cur.execute("delete from executive where executive_id = %s", (drop_id,))


def draft_boards() -> list[dict]:
    with connect() as conn:
        return fetch_all(conn, """
            select b.seat_id::text as seat_id, x.canonical_name, b.organization,
                   b.organization_type, b.seat_role, b.start_year, b.end_year, b.is_current,
                   b.source_url
            from board_seat b join executive x using (executive_id)
            where b.review_status = 'draft'
            order by x.canonical_name, b.organization""")


def set_board_status(ids: list[str], status: str) -> int:
    if status not in ("approved", "rejected") or not ids:
        return 0
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""update board_seat set review_status = %s, refreshed_at = now()
                           where seat_id = any(%s::uuid[]) and review_status = 'draft'""",
                        (status, ids))
            return cur.rowcount


def draft_accomplishments() -> list[dict]:
    with connect() as conn:
        return fetch_all(conn, """
            select a.accomplishment_id::text as accomplishment_id, x.canonical_name,
                   p.badge_label, e.recognition_year, a.headline, a.what_they_did,
                   a.quantified_outcomes, a.evidence_quality, a.source_url, a.source_quote,
                   coalesce((select string_agg(pc.label, '; ')
                             from accomplishment_criterion ac
                             join program_criterion pc using (criterion_id)
                             where ac.accomplishment_id = a.accomplishment_id), '') as criteria,
                   coalesce((select string_agg(t.theme, ', ') from accomplishment_theme t
                             where t.accomplishment_id = a.accomplishment_id), '') as themes
            from accomplishment a
            join executive x using (executive_id)
            left join recognition_event e using (event_id)
            left join recognition_program p using (program_id)
            where a.review_status = 'draft'
            order by x.canonical_name, a.headline""")


def set_accomplishment_status(ids: list[str], status: str) -> int:
    if status not in ("approved", "rejected") or not ids:
        return 0
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                update accomplishment set review_status = %s, reviewed_at = now(),
                       refreshed_at = now()
                where accomplishment_id = any(%s::uuid[]) and review_status = 'draft'""",
                        (status, ids))
            return cur.rowcount


_HR_LEVELS = ("CHRO", "HR leader below CHRO")


def resolve_current(rows: list[dict], batch_ids: set[str]) -> tuple[set[str], set[str]]:
    """Pure. Make approval leave each executive with AT MOST ONE current role.

    rows: every CURRENT role that is approved or in this batch, for the executives the batch
    touches -- dicts with role_id, executive_id, company, role_level, start_date,
    review_status. Returns (duplicate_ids, demote_ids):
      * duplicate_ids -- batch drafts that repeat another current role at the SAME company
        (a name/title variant of one job). They are set aside, never approved twice.
      * demote_ids    -- current roles that stop being current because the person would
        otherwise hold two (different employers): the HR role wins, then the latest start.
    MEASURED 2026-10-15: a batch approval failed on exactly these cases.
    """
    from metrics import company_key
    dup: set[str] = set()
    demote: set[str] = set()
    by_exec: dict[str, list[dict]] = {}
    for r in rows:
        by_exec.setdefault(r["executive_id"], []).append(r)
    for rs in by_exec.values():
        # Approved rows first, then dated before undated: the first of each company stays.
        rs = sorted(rs, key=lambda r: (r["review_status"] != "approved",
                                       r["start_date"] is None))
        kept: list[dict] = []
        for r in rs:
            if any(company_key(k["company"]) == company_key(r["company"]) for k in kept):
                if r["role_id"] in batch_ids and r["review_status"] != "approved":
                    dup.add(r["role_id"])
                continue
            kept.append(r)
        if len(kept) > 1:
            def rank(r):
                d = r["start_date"]
                return (r["role_level"] in _HR_LEVELS, d is not None, d.toordinal() if d else 0)
            winner = max(kept, key=rank)
            demote |= {r["role_id"] for r in kept if r is not winner}
    return dup, demote


def set_status(role_ids: list[str], status: str) -> dict:
    """Approve or reject roles. Returns counts: approved/rejected, duplicates, demoted."""
    out = {"changed": 0, "duplicates": 0, "demoted": 0}
    if status not in ("approved", "rejected") or not role_ids:
        return out
    ids = set(role_ids)
    with connect() as conn:
        with conn.cursor() as cur:
            if status == "approved":
                cur.execute("""
                    select role_id::text as role_id, executive_id::text as executive_id,
                           company_name_stated as company, role_level, start_date,
                           review_status
                    from executive_role
                    where is_current
                      and (role_id = any(%s::uuid[]) or review_status = 'approved')
                      and executive_id in (select executive_id from executive_role
                                           where role_id = any(%s::uuid[]) and is_current)""",
                            (list(ids), list(ids)))
                cols = [d.name for d in cur.description]
                dup, demote = resolve_current([dict(zip(cols, r)) for r in cur.fetchall()], ids)
                if dup:
                    cur.execute("""
                        update executive_role set review_status = 'rejected',
                               notes = 'Duplicate of another current role at the same '
                                       || 'company (set aside on approval). '
                                       || coalesce(notes, ''),
                               refreshed_at = now()
                        where role_id = any(%s::uuid[])""", (list(dup),))
                    out["duplicates"] = len(dup)
                    ids -= dup
                if demote:
                    cur.execute("""update executive_role set is_current = false,
                                   refreshed_at = now() where role_id = any(%s::uuid[])""",
                                (list(demote),))
                    out["demoted"] = len(demote)
            cur.execute("""
                update executive_role set review_status = %s, refreshed_at = now()
                where role_id = any(%s::uuid[]) and review_status = 'draft'""",
                        (status, list(ids)))
            out["changed"] = cur.rowcount
    return out
