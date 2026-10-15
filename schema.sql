-- CHRO External Recognition -- database schema (Postgres / Supabase).
--
-- Apply by hand: Supabase -> SQL Editor -> paste this whole file -> Run. Every statement is
-- "if not exists", so re-running it is safe. CHECK THE PROJECT before you run it: this app
-- has its own Supabase project, separate from the A&D workbench and the S&P 200 App.
--
-- Conventions (inherited from the sibling apps):
--   * NULL means "not stated", never zero / false.
--   * Historical recognition records are never rewritten. Company/title AT recognition live
--     on recognition_event; current and past roles live on executive_role.
--   * refreshed_at is stamped explicitly by writers (a DEFAULT only fires on INSERT).

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------------------
-- Companies: the employer context. Industry and the A&D flag live HERE, not on executives.
-- ---------------------------------------------------------------------------------------
create table if not exists company (
  company_id            uuid primary key default gen_random_uuid(),
  name                  text not null unique,
  ticker                text,
  industry              text,                 -- config.INDUSTRIES; analyst-assigned
  industry_source       text,                 -- 'analyst' | 'research' | ...
  hq_country            text,
  ownership             text,                 -- 'public' | 'private' | 'non-profit' | 'public sector'
  fortune_rank          int,                  -- Fortune 500 rank, when on the list
  fortune_list_year     int,
  revenue_usd_m         numeric,
  employees             int,
  size_as_of            date,                 -- fiscal year / date the size figures describe
  size_source_url       text,
  is_aerospace_defense  boolean not null default false,
  in_peer_set           boolean not null default false,  -- member of the census peer set (Fortune 100)
  notes                 text,
  refreshed_at          timestamptz not null default now()
);

-- ---------------------------------------------------------------------------------------
-- Executives. Deduplicated on name AND context, never on name alone (spec section 23).
-- ---------------------------------------------------------------------------------------
create table if not exists executive (
  executive_id     uuid primary key default gen_random_uuid(),
  canonical_name   text not null,
  name_key         text not null,             -- normalized name; NOT unique by design
  alternate_names  text[] not null default '{}',
  executive_type   text not null default 'practitioner'
                   check (executive_type in ('practitioner','academic','consultant','other')),
  linkedin_url     text,
  company_bio_url  text,
  notes            text,
  refreshed_at     timestamptz not null default now()
);
create index if not exists ix_executive_name_key on executive (name_key);

-- Career & tenure: one row per role held. The current role is the row with is_current.
create table if not exists executive_role (
  role_id               uuid primary key default gen_random_uuid(),
  executive_id          uuid not null references executive(executive_id) on delete cascade,
  company_id            uuid references company(company_id),
  company_name_stated   text not null,        -- as the source wrote it
  title                 text not null,
  role_level            text check (role_level in
                          ('CHRO','HR leader below CHRO','Non-HR executive','Academic','Other')),
  start_date            date,
  start_precision       text check (start_precision in ('day','month','year')),
  end_date              date,
  end_precision         text check (end_precision in ('day','month','year')),
  is_current            boolean not null default false,
  hire_type             text check (hire_type in ('internal','external')),
  source_url            text,
  source_type           text check (source_type in ('company_bio','leadership_page',
                          'sec_filing','press_release','business_publication','linkedin',
                          'recognition_source')),
  verified_date         date,
  review_status         text not null default 'draft'
                        check (review_status in ('draft','approved','rejected')),
  notes                 text,
  refreshed_at          timestamptz not null default now()
);
create index if not exists ix_role_exec on executive_role (executive_id);
-- At most one APPROVED current role per executive.
create unique index if not exists ux_role_one_current on executive_role (executive_id)
  where is_current and review_status = 'approved';

-- ---------------------------------------------------------------------------------------
-- Award programs (seeded from programs.py), their categories, criteria and yearly cycles.
-- ---------------------------------------------------------------------------------------
create table if not exists recognition_program (
  program_id                     uuid primary key default gen_random_uuid(),
  program_key                    text not null unique,
  organization                   text not null,
  organization_short             text not null,
  recognition_name               text not null,
  badge_label                    text not null,
  recognition_type               text not null,
  recognition_tier               int  not null,
  scoring_role                   text not null check (scoring_role in ('core','secondary','unscored')),
  is_standing_honor              boolean not null default false,
  analyst_weight                 numeric not null,
  source_quality                 text,
  criteria_summary               text,
  eligibility                    text,
  nominated_by                   text,
  judged_by                      text,
  selection_process              text,
  what_it_does_not_measure       text,
  peer_elected                   boolean,
  nomination_based               boolean,
  self_nomination_allowed        boolean,
  editorial_panel                boolean,
  judging_panel                  boolean,
  quantitative_impact_considered boolean,
  business_impact_considered     boolean,
  employee_outcomes_considered   boolean,
  industry_influence_considered  boolean,
  notes                          text,
  source_url                     text,
  last_verified                  date,
  refreshed_at                   timestamptz not null default now()
);

create table if not exists program_category (
  program_id         uuid not null references recognition_program(program_id) on delete cascade,
  category           text not null,
  analyst_weight     numeric not null,
  is_standing_honor  boolean not null default false,
  primary key (program_id, category)
);

create table if not exists program_criterion (
  criterion_id   uuid primary key default gen_random_uuid(),
  program_id     uuid not null references recognition_program(program_id) on delete cascade,
  criterion_key  text not null,
  label          text not null,
  description    text,
  display_order  int not null default 0,
  unique (program_id, criterion_key)
);

create table if not exists recognition_cycle (
  program_id            uuid not null references recognition_program(program_id) on delete cascade,
  cycle_year            int  not null,
  status                text not null check (status in ('available','pending')),
  announced_date        date,
  last_checked          date,
  last_updated          date,
  next_expected_period  text,
  source_url            text,
  notes                 text,
  primary key (program_id, cycle_year)
);

-- ---------------------------------------------------------------------------------------
-- Recognition events: who received what, when -- as stated AT THE TIME. Never rewritten.
-- ---------------------------------------------------------------------------------------
create table if not exists recognition_event (
  event_id                  uuid primary key default gen_random_uuid(),
  executive_id              uuid not null references executive(executive_id) on delete cascade,
  program_id                uuid not null references recognition_program(program_id),
  recognition_year          int  not null,
  category                  text not null default '',   -- '' when none (keeps the unique key exact)
  published_rank            int,
  title_at_recognition      text,
  company_at_recognition    text,                       -- as stated by the source
  company_id                uuid references company(company_id),
  analyst_weight_override   numeric,
  status                    text not null default 'published'
                            check (status in ('published','needs_verification','retracted')),
  recognition_date          date,
  source_url                text,
  source_title              text,
  source_publish_date       date,
  date_ingested             date not null default current_date,
  date_last_verified        date,
  notes                     text,
  refreshed_at              timestamptz not null default now(),
  unique (executive_id, program_id, recognition_year, category)
);
create index if not exists ix_event_exec on recognition_event (executive_id);

-- ---------------------------------------------------------------------------------------
-- What they did: accomplishments behind a recognition, each cited and reviewed.
-- ---------------------------------------------------------------------------------------
create table if not exists accomplishment (
  accomplishment_id    uuid primary key default gen_random_uuid(),
  executive_id         uuid not null references executive(executive_id) on delete cascade,
  event_id             uuid references recognition_event(event_id) on delete set null,
  headline             text not null,
  what_they_did        text not null,
  scale_and_results    text,
  quantified_outcomes  text,                -- only figures the source states
  timeframe            text,
  evidence_quality     text not null check (evidence_quality in
                         ('award_body_writeup','independent_press','company_statement','self_reported')),
  source_url           text not null,
  source_title         text,
  source_quote         text,
  review_status        text not null default 'draft'
                       check (review_status in ('draft','approved','rejected')),
  drafted_by           text not null default 'analyst',  -- 'analyst' | 'llm'
  model                text,
  reviewed_at          timestamptz,
  refreshed_at         timestamptz not null default now()
);
create index if not exists ix_accomplishment_exec on accomplishment (executive_id);

-- Which award criteria an accomplishment speaks to, and why.
create table if not exists accomplishment_criterion (
  accomplishment_id  uuid not null references accomplishment(accomplishment_id) on delete cascade,
  criterion_id       uuid not null references program_criterion(criterion_id) on delete cascade,
  rationale          text,
  primary key (accomplishment_id, criterion_id)
);

create table if not exists accomplishment_theme (
  accomplishment_id  uuid not null references accomplishment(accomplishment_id) on delete cascade,
  theme              text not null,            -- config.THEMES
  primary key (accomplishment_id, theme)
);

-- Last time each run.py step ran (distinct from how fresh the newest row is).
create table if not exists ingest_run (
  step     text primary key,
  ran_at   timestamptz not null,
  ok       boolean not null,
  note     text
);
