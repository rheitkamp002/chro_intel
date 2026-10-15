"""CHRO External Recognition -- Streamlit dashboard.

    .venv\\Scripts\\streamlit.exe run app.py

Five tabs: Overview, Compare, CHRO profile, Award criteria, Data status. Read-only: data
changes go through `run.py` steps (and, later, the research review queue).

Wording rules (spec section 30): never "best", "top performing" or "quality score". The
score is a recognition signal; a lack of awards is never evidence of weak leadership.
"""
from __future__ import annotations

import hmac
import os
from collections import defaultdict

import pandas as pd
import streamlit as st

import config
import metrics
from db import connect, fetch_all

st.set_page_config(page_title="CHRO External Recognition", layout="wide")

CAVEAT = ("External recognition indicates professional visibility, peer reputation, industry "
          "influence and/or recognized leadership impact. **It is not a measure of CHRO "
          "performance**, and a lack of awards is never evidence of weak leadership. Award "
          "programs favor large, visible companies, leaders who are nominated, and US-based "
          "networks. Weights are analyst judgements, not published by the award bodies.")

TIER_STYLE = {1: ("#b8860b", "rgba(218,165,32,.18)"), 2: ("#3b6fb6", "rgba(59,111,182,.16)"),
              3: ("#6b7280", "rgba(107,114,128,.16)"), 4: ("#6b7280", "rgba(107,114,128,.06)")}

st.markdown("""<style>
.badge{display:inline-block;padding:2px 10px;margin:2px 6px 2px 0;border-radius:999px;
       font-size:.82rem;font-weight:600;border:1px solid;white-space:nowrap}
.muted{opacity:.7;font-size:.9rem}
.crit{margin:0 0 .25rem 0}
</style>""", unsafe_allow_html=True)


# ----------------------------------------------------------------------------- access
def _secret(name: str) -> str:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.environ.get(name, "")


def _gate() -> None:
    """Password screen for the hosted app. No password configured => open (local use)."""
    pw = _secret("APP_PASSWORD")
    if not pw or st.session_state.get("authed"):
        return
    st.title("CHRO External Recognition")
    entered = st.text_input("Password", type="password", key="pw")
    if entered:
        if hmac.compare_digest(entered.encode(), pw.encode()):
            st.session_state["authed"] = True
            st.rerun()
        st.error("Incorrect password.")
    st.stop()


_gate()


# ----------------------------------------------------------------------------- loaders
@st.cache_data(ttl=600, show_spinner=False)
def load_events() -> list[dict]:
    with connect() as conn:
        rows = fetch_all(conn, """
            select e.event_id::text as event_id, e.executive_id::text as executive_id,
                   e.recognition_year, e.category, e.published_rank, e.title_at_recognition,
                   e.company_at_recognition, e.status, e.source_url, e.analyst_weight_override,
                   x.canonical_name, x.executive_type,
                   p.program_key, p.organization, p.organization_short, p.recognition_name,
                   p.badge_label, p.recognition_type, p.recognition_tier, p.scoring_role,
                   p.is_standing_honor as program_standing, p.analyst_weight as program_weight,
                   pc.analyst_weight as category_weight, pc.is_standing_honor as category_standing,
                   c.name as company_name, c.industry, c.is_aerospace_defense
            from recognition_event e
            join executive x using (executive_id)
            join recognition_program p using (program_id)
            left join program_category pc
                   on pc.program_id = e.program_id and pc.category = e.category
            left join company c on c.company_id = e.company_id
            order by e.recognition_year, p.recognition_tier""")
    for r in rows:
        for k in ("analyst_weight_override", "program_weight", "category_weight"):
            if r[k] is not None:
                r[k] = float(r[k])
        r["weight"] = metrics.effective_weight(r)
    return rows


@st.cache_data(ttl=600, show_spinner=False)
def load_programs() -> list[dict]:
    with connect() as conn:
        # The text cast comes LAST so it replaces the uuid in the row dict (last key wins).
        progs = fetch_all(conn, """select *, program_id::text as program_id from
                                   recognition_program order by recognition_tier, badge_label""")
        crits = fetch_all(conn, """select program_id::text as program_id, criterion_id::text
                                   as criterion_id, label, description, display_order
                                   from program_criterion order by display_order""")
        cats = fetch_all(conn, """select program_id::text as program_id, category,
                                  analyst_weight, is_standing_honor from program_category
                                  order by analyst_weight desc, category""")
        cycles = fetch_all(conn, """select program_id::text as program_id, cycle_year, status,
                                    last_checked, next_expected_period
                                    from recognition_cycle order by cycle_year""")
    for p in progs:
        p["criteria"] = [c for c in crits if c["program_id"] == p["program_id"]]
        p["categories"] = [c for c in cats if c["program_id"] == p["program_id"]]
        p["cycles"] = [c for c in cycles if c["program_id"] == p["program_id"]]
    return progs


@st.cache_data(ttl=600, show_spinner=False)
def load_roles() -> dict[str, list[dict]]:
    with connect() as conn:
        rows = fetch_all(conn, """
            select r.executive_id::text as executive_id, x.canonical_name, x.executive_type,
                   r.company_id::text as company_id, r.title, r.company_name_stated,
                   r.role_level, r.start_date, r.start_precision, r.end_date, r.is_current,
                   r.hire_type, r.source_url, r.source_type, r.verified_date, r.confidence,
                   c.industry, c.is_aerospace_defense
            from executive_role r
            join executive x using (executive_id)
            left join company c using (company_id)
            where r.review_status = 'approved'
            order by r.is_current desc, r.start_date desc nulls last""")
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[r["executive_id"]].append(r)
    return out


@st.cache_data(ttl=600, show_spinner=False)
def load_accomplishments() -> dict[str, list[dict]]:
    with connect() as conn:
        rows = fetch_all(conn, """
            select a.accomplishment_id::text as accomplishment_id,
                   a.executive_id::text as executive_id, a.event_id::text as event_id,
                   a.headline, a.what_they_did, a.scale_and_results, a.quantified_outcomes,
                   a.timeframe, a.evidence_quality, a.source_url, a.source_title, a.source_quote,
                   coalesce((select array_agg(t.theme order by t.theme)
                             from accomplishment_theme t
                             where t.accomplishment_id = a.accomplishment_id), '{}') as themes,
                   coalesce((select array_agg(pc.label || ' — ' || coalesce(ac.rationale, ''))
                             from accomplishment_criterion ac
                             join program_criterion pc using (criterion_id)
                             where ac.accomplishment_id = a.accomplishment_id), '{}') as criteria
            from accomplishment a where a.review_status = 'approved'""")
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[r["executive_id"]].append(r)
    return out


@st.cache_data(ttl=600, show_spinner=False)
def load_research_state() -> tuple[dict[str, list[dict]], dict[str, int]]:
    """Per executive: recorded research gaps, and how many accomplishment drafts await review."""
    with connect() as conn:
        gaps = fetch_all(conn, """
            select e.executive_id::text as executive_id, p.badge_label, e.recognition_year,
                   g.note, g.searched_at
            from accomplishment_gap g join recognition_event e using (event_id)
            join recognition_program p using (program_id)""")
        drafts = fetch_all(conn, """select executive_id::text as executive_id, count(*) as n
                                    from accomplishment where review_status = 'draft'
                                    group by executive_id""")
    out: dict[str, list[dict]] = defaultdict(list)
    for g in gaps:
        out[g["executive_id"]].append(g)
    return out, {d["executive_id"]: d["n"] for d in drafts}


@st.cache_data(ttl=600, show_spinner=False)
def load_peer_sets() -> tuple[list[dict], list[dict]]:
    with connect() as conn:
        sets = fetch_all(conn, "select * from peer_set order by peer_set_key desc")
        members = fetch_all(conn, """
            select m.peer_set_key, m.rank_in_set, c.company_id::text as company_id, c.name,
                   c.industry, c.revenue_usd_m, c.employees, c.is_aerospace_defense,
                   (select count(*) from executive_role r where r.company_id = c.company_id
                      and r.is_current and r.review_status = 'draft') as drafts
            from company_peer_set m join company c using (company_id)
            order by m.peer_set_key, m.rank_in_set nulls last, c.name""")
    return sets, members


@st.cache_data(ttl=600, show_spinner=False)
def load_status() -> dict:
    with connect() as conn:
        runs = fetch_all(conn, "select step, ran_at, ok, note from ingest_run order by ran_at desc")
        counts = fetch_all(conn, """
            select (select count(*) from executive) as executives,
                   (select count(*) from company) as companies,
                   (select count(*) from recognition_event) as events,
                   (select count(*) from executive_role where review_status='approved') as roles,
                   (select count(*) from accomplishment where review_status='approved') as accomplishments,
                   (select count(*) from accomplishment where review_status='draft') as drafts""")[0]
    return {"runs": runs, "counts": counts}


# ----------------------------------------------------------------------------- shaping
WINDOW = config.analysis_window()


def badge(label: str, tier: int, suffix: str = "") -> str:
    fg, bg = TIER_STYLE.get(tier, TIER_STYLE[4])
    return (f'<span class="badge" style="color:{fg};background:{bg};border-color:{fg}">'
            f'{label}{suffix}</span>')


def event_label(e: dict) -> str:
    extra = f" #{e['published_rank']}" if e["published_rank"] else (
        f" — {e['category']}" if e["category"] and e["category"] not in ("Winner",) else "")
    return f"{e['badge_label']}{extra}"


def build_rows(events: list[dict], window: tuple[int, ...], include_secondary: bool,
               roles: dict, accomplishments: dict) -> list[dict]:
    """One row per executive -- recognized, or with an approved role -- with metrics and the
    current employer (verified role) or else the last employer stated at recognition."""
    by_exec: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        by_exec[e["executive_id"]].append(e)
    for xid in roles:
        by_exec.setdefault(xid, [])
    rows = []
    for xid, evs in by_exec.items():
        s = metrics.summarize(evs, window, include_secondary)
        current = next((r for r in roles.get(xid, []) if r["is_current"]), None)
        latest_ev = max(evs, key=lambda e: e["recognition_year"]) if evs else {
            "canonical_name": roles[xid][0]["canonical_name"],
            "executive_type": roles[xid][0]["executive_type"],
            "company_at_recognition": None, "title_at_recognition": None,
            "industry": None, "is_aerospace_defense": False}
        if current:                       # the verified employer decides industry and A&D
            latest_ev = {**latest_ev, "industry": current["industry"],
                         "is_aerospace_defense": current["is_aerospace_defense"]}
        keys = {e["program_key"] for e in evs if e["status"] == "published"
                and (e["recognition_year"] in window or metrics.is_standing(e))}
        l40 = [e for e in evs if e["program_key"] == "N2_L40" and e["recognition_year"] in window]
        themes = sorted({t for a in accomplishments.get(xid, []) for t in a["themes"]})
        rows.append({
            "executive_id": xid,
            "company_id": current["company_id"] if current else None,
            "Executive": latest_ev["canonical_name"],
            "executive_type": latest_ev["executive_type"],
            "Company": current["company_name_stated"] if current else (
                metrics.clean_company(latest_ev["company_at_recognition"]) or "—"),
            "Title": current["title"] if current else (latest_ev["title_at_recognition"] or "—"),
            "Role verified": bool(current),
            "Industry": latest_ev["industry"] or "Not classified",
            "A&D": bool(latest_ev["is_aerospace_defense"]),
            "NAHR Fellow": "NAHR_FELLOW" in keys,
            "HR Exec of Year": "HRE_EOY" in keys,
            "HRO CHRO of Year": "HRO_COY" in keys,
            "Leaders40": f"#{min(e['published_rank'] or 99 for e in l40)}" if l40 else "",
            "Secondary": s["secondary_count"],
            "Strength": s["strength"],
            "Breadth": s["breadth"],
            "Events": s["frequency"],
            "Composite": s["composite"],
            "Latest": event_label(s["latest"]) + f" ({s['latest_year']})" if s["latest"] else "—",
            "Most prestigious": event_label(s["top"]) if s["top"] else "—",
            "Themes": ", ".join(themes),
            "orgs": {e["organization_short"] for e in evs},
            "types": {e["recognition_type"] for e in evs},
            "years": {e["recognition_year"] for e in evs},
        })
    rows.sort(key=lambda r: (-r["Strength"], -r["Breadth"], -r["Composite"], r["Executive"]))
    return rows


# ----------------------------------------------------------------------------- page
st.title("CHRO External Recognition")
st.caption(f"Analysis window: {WINDOW[0]}–{WINDOW[-1]} (rolling). "
           "NAHR Fellowship and HRO Today Lifetime Achievement count whenever awarded.")

try:
    EVENTS = load_events()
    PROGRAMS = load_programs()
    ROLES = load_roles()
    ACCOMPLISHMENTS = load_accomplishments()
except Exception as exc:                     # a paused/unreachable database is not a crash
    st.error(f"Could not reach the database ({type(exc).__name__}). If it has been idle, "
             "it may be waking up — reload in a few seconds.")
    st.stop()

SETS, MEMBERS = load_peer_sets()
GAPS, ACC_DRAFTS = load_research_state()
_SET_LABEL = {s["peer_set_key"]: s["label"] for s in SETS}
PEER_LABELS = [s["label"] for s in SETS]
PEERS_BY_COMPANY: dict[str, set[str]] = defaultdict(set)
for _m in MEMBERS:
    PEERS_BY_COMPANY[_m["company_id"]].add(_SET_LABEL[_m["peer_set_key"]])
PROG_BY_KEY = {p["program_key"]: p for p in PROGRAMS}
ALL_ROWS = build_rows(EVENTS, WINDOW, False, ROLES, ACCOMPLISHMENTS)
NAME_BY_ID = {r["executive_id"]: r["Executive"] for r in ALL_ROWS}

_TABS = [("Overview", "overview"), ("Compare", "compare"), ("Peer sets", "peers"),
         ("CHRO profile", "profile"), ("Award criteria", "criteria"), ("Review", "review"),
         ("Data status", "status")]
_T = dict(zip([k for _, k in _TABS], st.tabs([lbl for lbl, _ in _TABS])))


# ----- Overview
with _T["overview"]:
    st.info(CAVEAT)
    practitioners = [r for r in ALL_ROWS if r["executive_type"] == "practitioner"]
    recognized = [r for r in practitioners if r["Strength"] > 0]
    multi = [r for r in recognized if r["Breadth"] >= 2]
    c = st.columns(5)
    c[0].metric("HR leaders tracked", len(practitioners),
                help="Every practitioner in the app: award recipients plus verified CHROs of "
                     "peer-set companies, recognized or not.")
    c[1].metric("With core recognition", len(recognized),
                help="At least one qualifying core recognition.")
    c[2].metric("Recognized by 2+ organizations", len(multi))
    c[3].metric("NAHR Fellows", sum(r["NAHR Fellow"] for r in recognized))
    c[4].metric("Finalist-level only", sum(1 for r in practitioners
                                           if r["Strength"] == 0 and r["Secondary"] > 0),
                help="Leaders of Distinction with no core recognition in the window.")
    unrec = [r for r in practitioners if r["Strength"] == 0 and r["Secondary"] == 0]
    st.caption(f"{len(unrec)} tracked leaders have no recognition in the window. That "
               "reflects external visibility, not leadership quality — see Compare or Peer "
               "sets for the full list.")

    st.subheader("Recognized by multiple independent organizations")
    st.caption("Strength = most selective single recognition. Breadth = number of distinct "
               "organizations. Both are shown because neither alone tells the story.")
    if multi:
        st.dataframe(pd.DataFrame([{k: r[k] for k in (
            "Executive", "Company", "Strength", "Breadth", "Composite", "Most prestigious",
            "Latest")} for r in multi]), hide_index=True, width="stretch")
    else:
        st.write("No leader is recognized by more than one organization in this window.")

    st.subheader("Strength vs breadth")
    st.caption("Each dot is a leader. Up = a more selective recognition; right = more "
               "independent sources.")
    import plotly.express as px
    df = pd.DataFrame([r for r in recognized])
    if not df.empty:
        df["n"] = 1
        agg = (df.groupby(["Breadth", "Strength"])
                 .agg(Leaders=("n", "sum"),
                      Names=("Executive", lambda s: ", ".join(sorted(s)[:6])
                             + (f" +{len(s) - 6} more" if len(s) > 6 else "")))
                 .reset_index())
        fig = px.scatter(agg, x="Breadth", y="Strength", size="Leaders", hover_data=["Names"],
                         size_max=48)
        fig.update_traces(marker=dict(color="#3b6fb6", opacity=.75))
        fig.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10),
                          xaxis=dict(dtick=1, title="Breadth (distinct organizations)"),
                          yaxis=dict(title="Strength (max weight)"))
        st.plotly_chart(fig, width="stretch")


# ----- Compare
with _T["compare"]:
    f = st.columns([1.2, 1.6, 1.6, 1.2])
    year_opts = ["Whole window"] + [str(y) for y in WINDOW]
    year_sel = f[0].selectbox("Year", year_opts, key="cmp_year")
    industries = sorted({r["Industry"] for r in ALL_ROWS})
    ind_sel = f[1].multiselect("Industry", industries, key="cmp_ind")
    orgs = sorted({p["organization_short"] for p in PROGRAMS})
    org_sel = f[2].multiselect("Recognized by", orgs, key="cmp_org")
    search = f[3].text_input("Name or company contains", key="cmp_q")
    g = st.columns([1.4, 1, 1, 1, 1, 1.2, 1.2])
    peer_sel = g[0].multiselect("Peer set", PEER_LABELS, key="cmp_peer")
    min_strength = g[1].selectbox("Min strength", [0, 2, 3, 4, 5], key="cmp_ms")
    min_breadth = g[2].selectbox("Min breadth", [0, 1, 2, 3], key="cmp_mb")
    ad_only = g[3].checkbox("A&D only", key="cmp_ad")
    recog_only = g[4].checkbox("Recognized only", key="cmp_recog",
                               help="Hide CHROs with no recognition of any kind in the window.")
    incl_sec = g[5].checkbox("Include finalists in score", key="cmp_sec",
                             help="Adds Leaders of Distinction to strength/breadth/composite. "
                                  "Off by default (spec: secondary recognition excluded).")
    incl_acad = g[6].checkbox("Include academics", key="cmp_acad")

    window = WINDOW if year_sel == "Whole window" else (int(year_sel),)
    rows = build_rows(EVENTS, window, incl_sec, ROLES, ACCOMPLISHMENTS)
    q = search.strip().lower()
    rows = [r for r in rows
            if (incl_acad or r["executive_type"] == "practitioner")
            and (not recog_only or r["Strength"] > 0 or r["Secondary"] > 0)
            and (not peer_sel or PEERS_BY_COMPANY.get(r["company_id"], set()) & set(peer_sel))
            and r["Strength"] >= min_strength and r["Breadth"] >= min_breadth
            and (not ind_sel or r["Industry"] in ind_sel)
            and (not org_sel or r["orgs"] & set(org_sel))
            and (not ad_only or r["A&D"])
            and (not q or q in r["Executive"].lower() or q in r["Company"].lower())]
    st.caption(f"{len(rows)} leaders, recognized or not. Sorted by strength, then breadth, "
               "then composite. A strength of 0 means no core recognition in the window — "
               "not weaker leadership. Company/title are the verified current role, or else "
               "as stated at the latest recognition.")
    cols = ["Executive", "Company", "Title", "Industry", "Role verified", "NAHR Fellow", "HR Exec of Year",
            "HRO CHRO of Year", "Leaders40", "Secondary", "Strength", "Breadth", "Composite",
            "Latest", "Themes"]
    st.dataframe(pd.DataFrame([{k: r[k] for k in cols} for r in rows], columns=cols),
                 hide_index=True, width="stretch", height=560,
                 column_config={
                     "Strength": st.column_config.NumberColumn(format="%g"),
                     "Composite": st.column_config.NumberColumn(format="%g"),
                     "Secondary": st.column_config.NumberColumn(
                         help="Finalist-level recognitions (Leaders of Distinction) in window"),
                 })


# ----- Peer sets
def _tenure(start) -> str:
    if not start:
        return "—"
    from datetime import date
    years = (date.today() - start).days / 365.25
    return f"{years:.1f} yrs (since {start:%b %Y})"


with _T["peers"]:
    if not SETS:
        st.write("No peer sets loaded yet — run `run.py roster`.")
    else:
        ALL_KEY = "__all__"
        key_by_label = {"All HR leaders tracked": ALL_KEY}
        key_by_label.update({s["label"]: s["peer_set_key"] for s in SETS})
        ps = key_by_label[st.selectbox("Peer set", list(key_by_label), key="peer_set")]
        by_company = {r["company_id"]: r for r in ALL_ROWS if r["company_id"]}
        roles_by_company = {r["company_id"]: r for rs in ROLES.values() for r in rs
                            if r["is_current"]}
        current_role = {xid: next((r for r in rs if r["is_current"]), None)
                        for xid, rs in ROLES.items()}
        out = []
        if ps == ALL_KEY:
            meta = {"is_complete": False}
            st.caption("Every HR leader in the app — award recipients and verified peer-set "
                       "CHROs — whatever their recognition. Sorted by name.")
            for row in sorted((r for r in ALL_ROWS if r["executive_type"] == "practitioner"),
                              key=lambda r: r["Executive"].lower()):
                role = current_role.get(row["executive_id"])
                sets = ", ".join(sorted(PEERS_BY_COMPANY.get(row["company_id"], set())))
                out.append({
                    "Rank": None, "Company": row["Company"], "Industry": row["Industry"],
                    "CHRO": row["Executive"], "Title": row["Title"],
                    "Tenure": _tenure(role["start_date"]) if role else "—",
                    "Hire": (role["hire_type"] or "—") if role else "—",
                    "Strength": row["Strength"], "Breadth": row["Breadth"],
                    "Latest": row["Latest"],
                    "Note": (f"In: {sets}. " if sets else "")
                            + ("Role verified." if row["Role verified"]
                               else "Role as stated at recognition (not yet verified)."),
                })
        else:
            meta = next(s for s in SETS if s["peer_set_key"] == ps)
            st.caption(meta["description"] or "")
        for m in [m for m in MEMBERS if m["peer_set_key"] == ps]:
            row = by_company.get(m["company_id"])
            role = roles_by_company.get(m["company_id"])
            if row:
                if row["Strength"] > 0:
                    note = (f"Recognized by {row['Breadth']} organization"
                            f"{'s' if row['Breadth'] > 1 else ''}; most selective: "
                            f"{row['Most prestigious']}.")
                else:
                    note = ("No core recognition in the window. This is not evidence of "
                            "weak leadership — it indicates lower external visibility.")
            else:
                note = ("CHRO identified — awaiting review." if m["drafts"]
                        else "CHRO not yet researched.")
            out.append({
                "Rank": m["rank_in_set"], "Company": m["name"],
                "Industry": m["industry"] or "Not classified",
                "CHRO": row["Executive"] if row else "—",
                "Title": role["title"] if role else "—",
                "Tenure": _tenure(role["start_date"]) if role else "—",
                "Hire": (role["hire_type"] or "—") if role else "—",
                "Strength": row["Strength"] if row else None,
                "Breadth": row["Breadth"] if row else None,
                "Latest": row["Latest"] if row else "—",
                "Note": note,
            })
        verified = sum(1 for o in out if o["CHRO"] != "—")
        recognized = sum(1 for o in out if (o["Strength"] or 0) > 0)
        k = st.columns(3)
        k[0].metric("Leaders" if ps == ALL_KEY else "Companies", len(out))
        k[1].metric("CHRO verified", f"{verified} / {len(out)}")
        k[2].metric("With core recognition", recognized)
        if not meta["is_complete"] and ps != ALL_KEY:
            st.caption("This peer set is not yet complete, so recognition rates and "
                       "percentiles are withheld — they would be biased by who has been "
                       "verified so far.")
        st.dataframe(pd.DataFrame(out), hide_index=True, width="stretch", height=560,
                     column_config={"Strength": st.column_config.NumberColumn(format="%g")})


# ----- Review
with _T["review"]:
    import review
    st.caption("Research drafts wait here until approved. Only approved rows appear "
               "elsewhere in the app. Check the source link before approving.")
    dupes = review.possible_duplicates()
    if dupes:
        st.subheader("Possible duplicates")
        st.caption("Same name, different employer. Merge only if you are sure it is the same "
                   "person (e.g. they changed jobs). Recognition history keeps the employer "
                   "at the time.")
        groups: dict[str, list[dict]] = defaultdict(list)
        for d in dupes:
            groups[d["name_key"]].append(d)
        for nk, ds in groups.items():
            with st.container(border=True):
                for d in ds:
                    st.markdown(f"**{d['canonical_name']}** — {d['companies'] or 'no employer'}")
                if len(ds) == 2 and st.button("Same person — merge", key=f"merge_{nk}"):
                    keep, drop = ds
                    review.merge_executives(keep["executive_id"], drop["executive_id"])
                    st.cache_data.clear()
                    st.rerun()
        st.subheader("Draft roles")

    acc_drafts = review.draft_accomplishments()
    if acc_drafts:
        st.subheader("Draft accomplishments — what they did")
        st.caption("Drafted by research agents from the cited source. Check that the source "
                   "supports the claim (the quote is there to make that quick), then decide.")
        adf = pd.DataFrame([{
            "Decision": "", "Executive": a["canonical_name"],
            "Recognition": f"{a['badge_label'] or '—'} {a['recognition_year'] or ''}".strip(),
            "Headline": a["headline"], "What they did": a["what_they_did"],
            "Stated outcomes": a["quantified_outcomes"] or "",
            "Criteria met": a["criteria"], "Themes": a["themes"],
            "Evidence": (a["evidence_quality"] or "").replace("_", " "),
            "Quote": a["source_quote"] or "", "Source": a["source_url"],
            "accomplishment_id": a["accomplishment_id"],
        } for a in acc_drafts])
        aed = st.data_editor(
            adf, key="acc_editor", hide_index=True, width="stretch", height=480,
            disabled=[c for c in adf.columns if c != "Decision"],
            column_order=[c for c in adf.columns if c != "accomplishment_id"],
            column_config={
                "Decision": st.column_config.SelectboxColumn(
                    options=["", "Approve", "Reject"], width="small"),
                "Source": st.column_config.LinkColumn(display_text="open"),
            })
        a1, a2 = st.columns(2)
        if a1.button("Apply accomplishment decisions", key="acc_apply", type="primary"):
            ok = review.set_accomplishment_status(
                list(aed.loc[aed["Decision"] == "Approve", "accomplishment_id"]), "approved")
            no = review.set_accomplishment_status(
                list(aed.loc[aed["Decision"] == "Reject", "accomplishment_id"]), "rejected")
            st.cache_data.clear()
            st.success(f"{ok} approved, {no} rejected.")
            st.rerun()
        body = [a["accomplishment_id"] for a in acc_drafts
                if a["evidence_quality"] == "award_body_writeup"]
        if a2.button(f"Approve all {len(body)} sourced to the award body's own write-up",
                     key="acc_body", disabled=not body):
            n = review.set_accomplishment_status(body, "approved")
            st.cache_data.clear()
            st.success(f"{n} approved.")
            st.rerun()
        st.subheader("Draft roles")

    drafts = review.draft_roles()
    if not drafts:
        st.write("Nothing awaiting review.")
    else:
        r1, r2 = st.columns([1, 2])
        conf_sel = r1.multiselect("Confidence", ["high", "medium", "low", "unrated"],
                                  default=["high", "medium", "low", "unrated"], key="rv_conf")
        shown = [d for d in drafts if (d["confidence"] or "unrated") in conf_sel]
        r2.caption(f"{len(shown)} of {len(drafts)} drafts shown. Current roles first, by "
                   "Fortune rank. A prior role is the job before the current one.")
        df = pd.DataFrame([{
            "Decision": "", "Company": d["company_name_stated"],
            "Rank": d["fortune_rank"], "Executive": d["canonical_name"], "Title": d["title"],
            "Kind": "current" if d["is_current"] else "prior",
            "Since": d["start_date"], "Hire": d["hire_type"] or "",
            "Confidence": d["confidence"] or "unrated", "Notes": d["notes"] or "",
            "Source": d["source_url"], "Second source": d["second_source_url"],
            "role_id": d["role_id"],
        } for d in shown])
        edited = st.data_editor(
            df, key="rv_editor", hide_index=True, width="stretch", height=520,
            disabled=[c for c in df.columns if c != "Decision"],
            column_order=[c for c in df.columns if c != "role_id"],
            column_config={
                "Decision": st.column_config.SelectboxColumn(
                    options=["", "Approve", "Reject"], width="small"),
                "Source": st.column_config.LinkColumn(display_text="open"),
                "Second source": st.column_config.LinkColumn(display_text="open"),
            })
        b1, b2 = st.columns(2)
        if b1.button("Apply decisions", key="rv_apply", type="primary"):
            ok = review.set_status(
                list(edited.loc[edited["Decision"] == "Approve", "role_id"]), "approved")
            no = review.set_status(
                list(edited.loc[edited["Decision"] == "Reject", "role_id"]), "rejected")
            st.cache_data.clear()
            st.success(f"{ok} approved, {no} rejected.")
            st.rerun()
        high = [d["role_id"] for d in shown if d["confidence"] == "high"]
        if b2.button(f"Approve all {len(high)} high-confidence drafts shown", key="rv_high",
                     disabled=not high):
            n = review.set_status(high, "approved")
            st.cache_data.clear()
            st.success(f"{n} approved.")
            st.rerun()


# ----- Profile
with _T["profile"]:
    ids = sorted(NAME_BY_ID, key=lambda i: NAME_BY_ID[i].lower())
    xid = st.selectbox("Executive", ids, format_func=lambda i: NAME_BY_ID[i], key="prof_exec")
    row = next(r for r in ALL_ROWS if r["executive_id"] == xid)
    evs = sorted([e for e in EVENTS if e["executive_id"] == xid],
                 key=lambda e: (-e["recognition_year"], e["recognition_tier"]))
    current = next((r for r in ROLES.get(xid, []) if r["is_current"]), None)

    st.header(row["Executive"])
    if current:
        st.markdown(f"**{current['title']}**, {current['company_name_stated']}  \n"
                    f"<span class='muted'>Current role verified {current['verified_date']} "
                    f"({current['source_type']})</span>", unsafe_allow_html=True)
    elif not evs:
        st.markdown("<span class='muted'>No current role verified and no recognitions.</span>",
                    unsafe_allow_html=True)
    else:
        latest = evs[0]
        st.markdown(f"**{latest['title_at_recognition'] or 'Title not stated'}**, "
                    f"{latest['company_at_recognition'] or 'company not stated'}  \n"
                    f"<span class='muted'>As stated at the {latest['recognition_year']} "
                    "recognition. Current role not yet verified.</span>",
                    unsafe_allow_html=True)
    if row["executive_type"] != "practitioner":
        st.caption(f"Executive type: {row['executive_type']} — excluded from the "
                   "practitioner comparison by default.")

    st.markdown("".join(badge(event_label(e), e["recognition_tier"], f" · {e['recognition_year']}")
                        for e in evs if e["status"] == "published"), unsafe_allow_html=True)

    m = st.columns(4)
    m[0].metric("Recognition strength", metrics.fmt_weight(row["Strength"]),
                help="Highest analyst weight among qualifying core recognitions.")
    m[1].metric("Recognition breadth", row["Breadth"],
                help="Distinct organizations recognizing this leader.")
    m[2].metric("Events in window", row["Events"])
    m[3].metric("Composite", metrics.fmt_weight(row["Composite"]),
                help="Sum of core weights. A screening signal, not a ranking.")

    left, right = st.columns([1.15, 1])
    with left:
        st.subheader("What they did")
        accs = ACCOMPLISHMENTS.get(xid, [])
        gaps, pending_n = GAPS.get(xid, []), ACC_DRAFTS.get(xid, 0)
        if not accs:
            if pending_n:
                st.write(f"Research drafted — {pending_n} accomplishment(s) awaiting review "
                         "in the Review tab.")
            elif not gaps:
                st.write("Not yet researched.")
        for g in gaps:
            st.markdown(f"<span class='muted'>{g['badge_label']} {g['recognition_year']}: "
                        f"researched {g['searched_at']}, no specific accomplishment found in "
                        f"public sources. {g['note']}</span>", unsafe_allow_html=True)
        for a in accs:
            with st.container(border=True):
                st.markdown(f"**{a['headline']}**")
                st.write(a["what_they_did"])
                if a["scale_and_results"]:
                    st.markdown(f"*Scale and results:* {a['scale_and_results']}")
                if a["quantified_outcomes"]:
                    st.markdown(f"*Stated outcomes:* {a['quantified_outcomes']}")
                for c in a["criteria"]:
                    st.markdown(f"<p class='crit'>✓ {c}</p>", unsafe_allow_html=True)
                st.caption(f"{', '.join(a['themes'])} · Evidence: "
                           f"{a['evidence_quality'].replace('_', ' ')} · "
                           f"[{a['source_title'] or 'source'}]({a['source_url']})")

        st.subheader("Recognition timeline")
        pending: dict[int, list[str]] = defaultdict(list)
        for p in PROGRAMS:
            for c in p["cycles"]:
                if c["status"] == "pending":
                    pending[c["cycle_year"]].append(p["badge_label"])
        years = sorted(set(WINDOW) | {e["recognition_year"] for e in evs}, reverse=True)
        for y in years:
            ye = [e for e in evs if e["recognition_year"] == y]
            body = "<br>".join(f"└ {event_label(e)}"
                               + (" <span class='muted'>(finalist)</span>"
                                  if e["scoring_role"] == "secondary" else "") for e in ye)
            if not ye:
                body = "<span class='muted'>No recognition"
                body += (f" — still pending: {', '.join(pending.get(y, []))}"
                         if pending.get(y) else "") + "</span>"
            st.markdown(f"**{y}**<br>{body}", unsafe_allow_html=True)

    with right:
        st.subheader("Why these awards matter")
        for key in dict.fromkeys(e["program_key"] for e in evs):
            p = PROG_BY_KEY[key]
            with st.expander(f"{p['badge_label']} — {p['organization_short']}", expanded=True):
                st.write(p["criteria_summary"])
                parent = p if p["criteria"] else PROG_BY_KEY.get(
                    {"HRE_LOD": "HRE_EOY", "HRO_LOD": "HRO_COY"}.get(key, ""), p)
                for c in parent["criteria"]:
                    st.markdown(f"<p class='crit'>• <b>{c['label']}</b>"
                                + (f" — {c['description']}" if c["description"] else "")
                                + "</p>", unsafe_allow_html=True)

        st.subheader("Career & tenure")
        roles = ROLES.get(xid, [])
        if not roles:
            st.write("Not yet researched.")
        for r in roles:
            span = f"{r['start_date'] or '?'} – {r['end_date'] or ('present' if r['is_current'] else '?')}"
            st.markdown(f"**{r['title']}**, {r['company_name_stated']}  \n"
                        f"<span class='muted'>{span}"
                        + (f" · {r['hire_type']} hire" if r["hire_type"] else "")
                        + "</span>", unsafe_allow_html=True)

    st.subheader("Recognitions and sources")
    st.dataframe(pd.DataFrame([{
        "Year": e["recognition_year"], "Organization": e["organization_short"],
        "Recognition": e["recognition_name"], "Category / rank": e["category"] or "—",
        "Title at recognition": e["title_at_recognition"] or "—",
        "Company at recognition": e["company_at_recognition"] or "—",
        "Weight": e["weight"], "Counts as": e["scoring_role"], "Source": e["source_url"],
    } for e in evs]), hide_index=True, width="stretch",
        column_config={"Source": st.column_config.LinkColumn(display_text="open"),
                       "Weight": st.column_config.NumberColumn(format="%g")})


# ----- Award criteria
with _T["criteria"]:
    st.caption("How each recognition is decided, in plain language. Weights, tiers and "
               "source-quality ratings are ANALYST assessments, not published by the award "
               "bodies.")
    recipients = defaultdict(lambda: defaultdict(int))
    for e in EVENTS:
        recipients[e["program_key"]][e["recognition_year"]] += 1
    for p in PROGRAMS:
        with st.container(border=True):
            st.markdown(badge(p["badge_label"], p["recognition_tier"])
                        + f" <b>{p['organization']}</b> · {p['recognition_name']}",
                        unsafe_allow_html=True)
            st.write(p["criteria_summary"])
            a, b, c = st.columns(3)
            a.markdown(f"**Who is eligible**  \n{p['eligibility'] or 'Not stated'}")
            b.markdown(f"**Who nominates**  \n{p['nominated_by'] or 'Not stated'}")
            c.markdown(f"**Who decides**  \n{p['judged_by'] or 'Not stated'}")
            if p["criteria"]:
                st.markdown("**Published criteria**")
                for cr in p["criteria"]:
                    st.markdown(f"<p class='crit'>• <b>{cr['label']}</b>"
                                + (f" — {cr['description']}" if cr["description"] else "")
                                + "</p>", unsafe_allow_html=True)
            st.markdown(f"**What it does not measure:** {p['what_it_does_not_measure']}")
            flags = [lbl for k, lbl in (
                ("peer_elected", "Peer-elected"), ("nomination_based", "Nomination-based"),
                ("judging_panel", "Judging panel"), ("editorial_panel", "Editorial selection"),
                ("quantitative_impact_considered", "Quantified impact"),
                ("business_impact_considered", "Business impact"),
                ("employee_outcomes_considered", "Employee outcomes"),
                ("industry_influence_considered", "Industry influence")) if p[k]]
            st.caption("Method: " + (", ".join(flags) or "not stated"))
            years = ", ".join(
                f"{c['cycle_year']}: "
                + (f"{recipients[p['program_key']].get(c['cycle_year'], 0)} in dataset"
                   if c["status"] == "available" else "pending — not yet published")
                for c in p["cycles"]) or "no editions tracked"
            st.markdown(
                f"<span class='muted'>Tier {p['recognition_tier']} · weight "
                f"{metrics.fmt_weight(float(p['analyst_weight']))} · counts as "
                f"{p['scoring_role']}"
                + (" · standing honor (counts whenever awarded)" if p["is_standing_honor"] else "")
                + f" · source quality {p['source_quality']} (analyst) · {years} · "
                f"text last verified {p['last_verified'] or 'not yet'} · "
                f"<a href='{p['source_url']}' target='_blank'>source</a></span>",
                unsafe_allow_html=True)
            if p["categories"]:
                st.markdown("Category weights: " + ", ".join(
                    f"{c['category']} {metrics.fmt_weight(float(c['analyst_weight']))}"
                    + (" (standing)" if c["is_standing_honor"] else "")
                    for c in p["categories"]))


# ----- Data status
with _T["status"]:
    status = load_status()
    cnt = status["counts"]
    s = st.columns(5)
    s[0].metric("Executives", cnt["executives"])
    s[1].metric("Companies", cnt["companies"])
    s[2].metric("Recognition events", cnt["events"])
    s[3].metric("Verified roles", cnt["roles"])
    s[4].metric("Reviewed accomplishments", cnt["accomplishments"],
                help=f"{cnt['drafts']} drafts awaiting review")
    st.subheader("Award editions")
    st.dataframe(pd.DataFrame([{
        "Recognition": p["badge_label"], "Year": c["cycle_year"],
        "Status": "Available" if c["status"] == "available" else "Pending / not yet published",
        "Last checked": c["last_checked"], "Expected": c["next_expected_period"] or "",
    } for p in PROGRAMS for c in p["cycles"]]), hide_index=True, width="stretch")
    st.subheader("Last data runs")
    st.dataframe(pd.DataFrame(status["runs"]), hide_index=True, width="stretch")
    if st.button("Refresh data from database", key="refresh"):
        st.cache_data.clear()
        st.rerun()
