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
                   x.canonical_name, r.company_name_stated, r.title, r.role_level,
                   r.start_date, r.start_precision, r.is_current, r.hire_type,
                   r.source_url, r.source_type, r.second_source_url, r.confidence,
                   r.research_batch, r.notes, c.fortune_rank
            from executive_role r
            join executive x using (executive_id)
            left join company c using (company_id)
            where r.review_status = 'draft'
            order by r.is_current desc, c.fortune_rank nulls last, x.canonical_name""")


def possible_duplicates() -> list[dict]:
    """Executives sharing a normalized name, with the employers each is known by."""
    with connect() as conn:
        return fetch_all(conn, """
            select x.name_key, x.executive_id::text as executive_id, x.canonical_name,
                   coalesce(string_agg(distinct coalesce(e.company_at_recognition,
                                                         r.company_name_stated), ', '), '')
                     as companies
            from executive x
            left join recognition_event e using (executive_id)
            left join executive_role r using (executive_id)
            where x.name_key in (select name_key from executive
                                 group by name_key having count(*) > 1)
            group by x.name_key, x.executive_id, x.canonical_name
            order by x.name_key, x.canonical_name""")


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


def set_status(role_ids: list[str], status: str) -> int:
    """Approve or reject roles. Returns how many rows changed."""
    if status not in ("approved", "rejected") or not role_ids:
        return 0
    with connect() as conn:
        with conn.cursor() as cur:
            if status == "approved":
                cur.execute("""
                    update executive_role o set is_current = false, refreshed_at = now()
                    from executive_role n
                    where n.role_id = any(%s::uuid[]) and n.is_current
                      and o.executive_id = n.executive_id and o.role_id <> n.role_id
                      and o.is_current and o.review_status = 'approved'""", (role_ids,))
            cur.execute("""
                update executive_role set review_status = %s, refreshed_at = now()
                where role_id = any(%s::uuid[]) and review_status = 'draft'""",
                        (status, role_ids))
            return cur.rowcount
