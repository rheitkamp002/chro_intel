# CLAUDE.md — CHRO External Recognition

Guidance for any future session working on this project. Read this first.
Created **2026-10-15**.

## What this is

A benchmark of the **external professional recognition** of CHROs and senior HR leaders:
who was recognized, by which organization, under what criteria — and above all **what each
leader did** to earn it. Five tabs: **Overview, Compare, CHRO profile, Award criteria, Data
status.**

- Spec: `../CHRO Recognition Benchmark_MD_ChatGPT.docx`
- Seed data: `../CHRO_Recognition_Benchmark_2025_2026.xlsx`

**Owner:** Robert Heitkamp. Windows 11, PowerShell + VS Code. **Not a software engineer** —
spell steps out literally, give the exact command to paste, say which folder, and say what a
good result looks like.

**It is NOT a CHRO quality ranking.** Never label anything "best", "top performing" or
"quality score" (spec section 30). A lack of awards is never evidence of weak leadership.

## Separate from the sibling apps

`../../A&D_App/ad_intel` and `../../S&P200_App/sp200_intel` are separate codebases with
separate databases. Never change a file there for this app's benefit. `db.py` was copied
BYTE-IDENTICAL from `sp200_intel` on 2026-10-15; nothing here imports from either app. The
only overlap is that CHROs of some A&D companies will appear here as members of the
Fortune 100 peer set (A&D is a filter, `company.is_aerospace_defense`).

## Infrastructure

- **Database: Neon Postgres** (free tier, AWS us-east-1), NOT Supabase — the owner's two
  free Supabase slots are taken by A&D and S&P. Direct (non-pooled) connection string in
  `.env` as `DATABASE_URL`. `run.py` prints the host: it must end in `neon.tech`.
  Neon suspends after ~5 idle minutes; the first query after that is a little slower.
- **Hosting: Streamlit Community Cloud as a PUBLIC app behind a password** (`APP_PASSWORD`
  secret). The account's one private-app slot is used by A&D. No password set => no gate,
  which is how it runs locally. VERIFIED LIVE 2026-10-15: deployed, password screen shown
  first, tabs render after it. Secrets (`DATABASE_URL`, `APP_PASSWORD`) live in the
  Streamlit app's Secrets box only.
- **GitHub: `rheitkamp002/chro_intel` is a PUBLIC repo** — Community Cloud would not deploy
  a public app from a private repo while the private slot is taken. So: **never commit data,
  research CSVs, `.env` or anything secret.** The data's only protection is the password.
  Commits use the GitHub noreply email (set in this repo's git config) so the owner's Gmail
  is not exposed; history was rewritten once on 2026-10-15 for this.

## Commands (PowerShell, from this folder)

```powershell
.venv\Scripts\python.exe run.py <command>
```

| Command | What it does |
|---|---|
| `schema` | Run `schema.sql`. Every statement is `if not exists` — it only ever ADDS |
| `seed` | Load `programs.py` + the seed workbook. Safe to re-run (see below) |
| `roster` | Load `../research/` Fortune 100 + A&D CHRO research as DRAFTS. Safe to re-run |
| `checkup` | Read-only wrap-up checks. Run at the end of every piece of work |

**Roster research (2026-10-15).** Done by Claude agents with web search, written as CSVs to
`../research/` (outside the public repo). Peer sets: `F100_2026` (2026 Fortune 500 ranks
1-100, fortune.com) and `AD_TRACKED` (the 8 companies in `ad_intel/config.py`, copied into
`config.AD_TRACKED` — update by hand if A&D's list changes). MEASURED after load: 95 CHROs
identified, 174 draft roles (current + prior), 7 companies with no CHRO identified
(Alphabet, Berkshire, Verizon, Tesla, TJX, General Dynamics, Palantir). Drafts become
visible only after approval in the **Review** tab; the Review tab also merges duplicates
that a person confirms are the same individual (e.g. a CHRO who changed employers).

**Launch the dashboard:** `.venv\Scripts\streamlit.exe run app.py`

**What a re-seed does:** `recognition_program`, `program_criterion`, `program_category` are
OVERWRITTEN from `programs.py` (the source of record — change a weight there, then re-seed).
`recognition_cycle`, `company`, `executive`, `recognition_event` are INSERT-ONLY, so research,
status updates and history are never clobbered.

## Tests

No pytest — each file is a script with its own runner.

```powershell
$env:PYTHONPATH="."; .venv\Scripts\python.exe tests\test_core.py         # 24 offline
$env:PYTHONPATH="."; .venv\Scripts\python.exe tests\test_app_render.py   # 5 — NEEDS THE LIVE DB
```

MEASURED 2026-10-15: 24/24 and 5/5 pass. The render test is the only check that catches
UI-only errors; it also proves the password gate blocks content.

## Methodology decisions (owner-approved 2026-10-15)

These changed the spec; keep them unless the owner says otherwise.

- **Standing honors.** NAHR Fellowship and HRO Today Lifetime Achievement count in the score
  whenever awarded, not only inside the rolling 2-year window. They count toward strength,
  breadth and composite, NOT toward "events in window".
- **HRO Today weights vary by category** (`program_category`): Large 4, Mid 3.5, Sustainable
  Workforce 3.5, Small 3, Non-Profit 3, Lifetime 4. PROPOSED values, analyst judgement.
- **Lead with strength and breadth**; composite is a secondary sort/column.
- **HR Leader of Distinction is CORE, weight 3, tier 2** (owner decision 2026-10-15). It is
  HR Executive's award for mid-size organizations (500-10,000 employees), not a finalist
  list; HR Executive of the Year is for organizations above 10,000. Verified from HR
  Executive's own nomination pages (`../research/nomination_rules.json`).
- **Peer set = Fortune 100 CHROs, as a census** (recognized or not), so A&D vs cross-industry
  comparisons are not biased by only counting winners. Percentiles stay hidden until that
  peer set is complete.
- **Monitoring writes to a review queue**, never straight into published data.
- **v1 extra data: career/tenure and company context only.** 10-K human-capital disclosures
  and company/influence signals are deferred.

## Known constraints

- **Streamlit Cloud keeps imported modules cached across a redeploy**, so a new `app.py`
  can call a function an OLD `metrics.py` lacks (MEASURED 2026-10-15: AttributeError on
  `metrics.recipient_profile`). `app.py` therefore reloads `config`, `programs`, `metrics`,
  `review` and `brief` every run. Never reload `db` (it holds the connection pool). After
  adding a new helper module, add it to that reload list. If the hosted app still shows a
  stale error: share.streamlit.io → My apps → ⋮ → Reboot.
- **Approval must never leave two current roles for one person** (`ux_role_one_current`).
  `review.resolve_current` sets same-company duplicates aside and demotes the losing
  current role across employers; keep its tests passing.

## Data rules

- **Never rewrite history.** Title/company AT recognition live on `recognition_event` and are
  never updated. Current and past roles live on `executive_role`.
- **Never merge executives on name alone** — `seed.plan_executives` needs name AND company.
  Same name at a different employer creates a second executive; `checkup` lists it.
- **The workbook's "Why recognized" column is NOT loaded.** It repeats each program's
  methodology sentence on every row and says nothing about the person.
- `NULL` means "not stated", never zero/false (e.g. `self_nomination_allowed` is NULL for
  every program until someone checks).
- Every accomplishment needs a `source_url` and an `evidence_quality`; only `approved` rows
  show in the dashboard.
- Label claims **MEASURED / VERIFIED / ESTIMATED / PROPOSED**, with dates.
- **Streamlit:** a widget's options and labels must be constant across reruns. Use
  `width="stretch"`, never `use_container_width`. Never import `app.py` in a test.

## Measured facts (2026-10-15, after the first seed)

94 executives (93 practitioners + Rob Ployhart, academic), 94 companies (3 without an
industry: BVI, Calcium+Company, UCS Forest Group), 103 recognition events, 7 programs,
18 criteria, 12 cycles. Pending in window: NAHR 2026, N2Growth Leaders40 2026. No duplicate
executives. 9 people appear more than once and were merged correctly.

## Still to build

1. ~~Publish~~ — DONE 2026-10-15.
2. **Research: accomplishments** — per recognition, from the award body's own write-up;
   Claude drafts with citations, mapped to `program_criterion`, analyst approves.
3. **Research: Fortune 100 CHRO roster** — current CHRO per company with a verified source,
   plus company context (Fortune rank, revenue, employees, HQ).
4. **Research: career & tenure** for recognized leaders (`executive_role`).
5. **Review queue tab** for drafts, and a weights editor.
6. Backfill earlier NAHR Fellow classes (standing honor).
7. Monitoring of award sources (monthly; Sep–Nov more often) into the review queue.
