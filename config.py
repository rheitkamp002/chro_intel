"""Static configuration for the CHRO External Recognition app.

WHAT THIS APP IS. A benchmark of the external professional recognition of CHROs and senior
HR leaders: who has been recognized, by whom, under what criteria -- and above all WHAT EACH
LEADER DID to earn it. Spec: `../CHRO Recognition Benchmark_MD_ChatGPT.docx`. Seed data:
`../CHRO_Recognition_Benchmark_2025_2026.xlsx`.

WHAT IT IS NOT. A ranking of CHRO quality. Recognition measures visibility, peer reputation
and recognized impact; a lack of awards is never evidence of weak leadership.

A SEPARATE CODEBASE (2026-10-15). Standalone from the A&D Intelligence Workbench and the S&P
200 App, with its own folder, .env and database. The only overlap is that some CHROs of A&D
companies appear here as members of the Fortune 100 peer set. `db.py` was copied
BYTE-IDENTICAL from `S&P200_App/sp200_intel` on 2026-10-15; nothing here imports from there.

Award-program definitions, criteria summaries and analyst weights live in `programs.py`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.environ.get("DATABASE_URL", "")
    # Needed ONLY by the research steps. Seeding and the dashboard run without it.
    anthropic_api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
    # Hosted instance only. Empty => no login screen (local use).
    app_password: str = os.environ.get("APP_PASSWORD", "")

    def require(self, *names: str) -> None:
        missing = [n for n in names if not getattr(self, n)]
        if missing:
            raise SystemExit(
                f"Missing required env var(s): {', '.join(missing)}. See .env.example.")


SETTINGS = Settings()


# ----- Analysis window -----
# Rolling: the current calendar year and the one before. A year whose awards are not yet
# published is shown as PENDING (recognition_cycle.status), never inferred.
WINDOW_YEARS = 2


def analysis_window(today: date | None = None) -> tuple[int, ...]:
    """Pure. The years in the rolling window, oldest first."""
    end = (today or date.today()).year
    return tuple(range(end - WINDOW_YEARS + 1, end + 1))


# ----- Seed workbook -----
SEED_WORKBOOK = "../CHRO_Recognition_Benchmark_2025_2026.xlsx"


# ----- Vocabularies (stored as text; the schema CHECKs mirror these) -----
EXECUTIVE_TYPES = ("practitioner", "academic", "consultant", "other")
ROLE_LEVELS = ("CHRO", "HR leader below CHRO", "Non-HR executive", "Academic", "Other")
FUNCTIONS = ("HR", "Finance", "Operations", "Legal", "Sales & Marketing", "General Management",
             "Consulting", "Technology", "Communications", "Other")
BOARD_ORG_TYPES = ("public company", "private company", "non-profit", "association",
                   "government/academic")
# Spec section 22 verification hierarchy, strongest first.
ROLE_SOURCE_TYPES = ("company_bio", "leadership_page", "sec_filing", "press_release",
                     "business_publication", "linkedin", "recognition_source")
EVIDENCE_QUALITY = ("award_body_writeup", "independent_press", "company_statement",
                    "self_reported")

# Spec section 14 taxonomy -- COPIED from the spec, not retyped from memory.
THEMES = (
    "AI & Automation", "Workforce Transformation", "Operating Model",
    "Organizational Design", "Culture", "Employee Engagement", "Leadership Development",
    "Succession", "Talent Acquisition", "Skills / Reskilling",
    "Strategic Workforce Planning", "Total Rewards", "Benefits", "Employee Experience",
    "HR Technology", "People Analytics", "M&A Integration", "Productivity",
    "Frontline Workforce", "Future of Work", "DEI", "Labor Relations", "Change Management",
    "Global Workforce",
)

# Broad industry labels for the comparison filter. ANALYST-ASSIGNED at seed time.
INDUSTRIES = (
    "Aerospace & Defense", "Chemicals & Materials", "Conglomerate", "Consumer Goods",
    "Education", "Energy", "Financial Services", "Healthcare & Life Sciences",
    "Industrials & Manufacturing", "Insurance", "Non-Profit", "Professional Services",
    "Public Sector", "Retail", "Technology", "Telecommunications",
    "Transportation & Logistics", "Utilities",
)

# The 8 companies the A&D app tracks (`ad_intel/config.py` COMPANIES, read 2026-10-15).
# Their CHROs are FORCE-ADDED as the 'AD_TRACKED' peer set, whatever their Fortune rank.
# Copied by hand: this app never imports from ad_intel. If A&D's list changes, update here.
AD_TRACKED = ("Lockheed Martin", "RTX", "Northrop Grumman", "General Dynamics", "Boeing",
              "L3Harris Technologies", "Huntington Ingalls Industries",
              "Palantir Technologies")

# Companies flagged is_aerospace_defense. The A&D overlap is a FILTER here, nothing more.
AD_COMPANIES = (
    "Lockheed Martin", "RTX", "Northrop Grumman", "General Dynamics", "Boeing", "L3Harris",
    "BAE Systems", "Huntington Ingalls Industries", "Leidos", "SAIC", "Booz Allen Hamilton",
    "CACI", "Parsons", "Amentum", "KBR", "Anduril", "Palantir", "Kratos", "Mercury Systems",
    "BWX Technologies",
)


# ----- Models (research steps) -----
RESEARCH_MODEL = "claude-sonnet-5-5"
