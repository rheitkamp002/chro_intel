"""Award programs: what each recognition IS, how it is decided, and what it is worth here.

This file is the source of record for `recognition_program`, `program_category`,
`program_criterion` and `recognition_cycle`; `run.py seed` upserts it into the database.

PROVENANCE. Descriptions are drawn from the spec (sections 3-7, 19-20) and the seed
workbook's Methodology tab, both dated 2026-10-15. `last_verified` stays None until a person
or the research step has re-read the source page; the dashboard shows that state rather than
implying the text is current.

ANALYST WEIGHTS ARE JUDGEMENTS, NOT PUBLISHED FACTS. The spec's defaults are kept except
where the 2026-10-15 review changed them (owner-approved):
  * HRO Today weights vary by CATEGORY -- about six winners a year across very different
    populations, versus one HR Executive of the Year. The split below is PROPOSED.
  * NAHR Fellowship and HRO Lifetime Achievement are STANDING honors: they count in the
    score whatever year they were awarded, not only inside the rolling window.

`scoring_role`: 'core' counts in the score; 'secondary' is shown and counted separately
(finalist-level); 'unscored' is shown as a signal only.
"""
from __future__ import annotations

PROGRAMS: list[dict] = [
    {
        "program_key": "NAHR_FELLOW",
        "organization": "National Academy of Human Resources (NAHR)",
        "organization_short": "NAHR",
        "recognition_name": "Fellow of the NAHR",
        "badge_label": "NAHR Fellow",
        "recognition_type": "Professional honor",
        "recognition_tier": 1,
        "scoring_role": "core",
        "is_standing_honor": True,
        "analyst_weight": 5,
        "source_quality": "Very High",
        "award_frequency": "Annually: a new class of Fellows is elected each year",
        "criteria_summary": (
            "A career honor, not an annual prize. Existing Fellows (senior HR leaders and "
            "scholars) elect new Fellows after a multi-stage peer review. They look for "
            "sustained, nationally recognized achievement: impact on the candidate's own "
            "organization, on the HR profession, and on society, including shaping HR "
            "thinking or policy."),
        "eligibility": "Senior HR executives, scholars and other leaders with a sustained, "
                       "nationally or globally recognized record in the profession.",
        "nominated_by": "Nomination, reviewed by the Academy.",
        "judged_by": "Existing Fellows; the Board recommends candidates for ratification by "
                     "the Fellowship.",
        "selection_process": (
            "Candidates are nominated and elected by existing Fellows through a multi-layer "
            "peer-review process. The Board recommends qualified candidates for ratification "
            "by the Fellowship."),
        "what_it_does_not_measure": (
            "Recent or single-year results; it rewards a career. It also requires being "
            "known to existing Fellows, which favors leaders active in the national HR "
            "community."),
        "peer_elected": True, "nomination_based": True, "self_nomination_allowed": None,
        "editorial_panel": False, "judging_panel": True,
        "quantitative_impact_considered": None, "business_impact_considered": True,
        "employee_outcomes_considered": None, "industry_influence_considered": True,
        "notes": "NAHR describes Fellowship as the highest honor granted in the HR "
                 "profession. 2026 class not announced as of 2026-10-15.",
        "source_url": "https://nationalacademyhr.org/fellowship-requirements",
        "criteria": [
            ("org_impact", "Contribution to their organization",
             "Sustained achievement in the organizations the candidate has led or served."),
            ("profession", "Contribution to the HR profession",
             "Advancing HR practice, mentoring, professional leadership."),
            ("society", "Contribution to society",
             "Impact beyond the employer: policy, community, public good."),
            ("thought_leadership", "Shaping HR thinking or policy",
             "Recognized influence on how HR is practiced or regulated."),
        ],
        "categories": [],
    },
    {
        "program_key": "HRE_EOY",
        "organization": "HR Executive",
        "organization_short": "HR Executive",
        "recognition_name": "HR Executive of the Year",
        "badge_label": "HR Executive of the Year",
        "recognition_type": "Industry award",
        "recognition_tier": 1,
        "scoring_role": "core",
        "is_standing_honor": False,
        "analyst_weight": 4,
        "source_quality": "High",
        "award_frequency": "Annually: one HR Executive of the Year",
        "criteria_summary": (
            "One winner a year. Open only to an organization's top HR executive who runs the "
            "whole HR function, has held the role at least three years, works for an employer "
            "of 500+ people, and is recommended by the CEO. Judged on strategic contribution "
            "to the business, innovation and transformation, and contribution to the HR "
            "profession."),
        "eligibility": "The organization's senior HR executive, overseeing the full HR "
                       "function; at least 3 years in the role at the current employer; "
                       "employer of at least 500 employees.",
        "nominated_by": "Nomination, with a CEO recommendation required.",
        "judged_by": "HR Executive (editorial / judging process).",
        "selection_process": (
            "Nomination-based award for the senior HR executive. Eligibility includes at "
            "least three years as the senior HR executive at the current organization and a "
            "CEO recommendation."),
        "what_it_does_not_measure": (
            "Leaders who are not the top HR executive, or who are new in role. Depends on "
            "the organization choosing to nominate."),
        "peer_elected": False, "nomination_based": True, "self_nomination_allowed": None,
        "editorial_panel": True, "judging_panel": None,
        "quantitative_impact_considered": None, "business_impact_considered": True,
        "employee_outcomes_considered": None, "industry_influence_considered": True,
        "notes": "One principal winner annually. HR Leaders of Distinction tracked "
                 "separately as secondary recognition.",
        "source_url": "https://hrexecutive.com/hr-executive-of-the-year/",
        "criteria": [
            ("strategic_impact", "Strategic organizational impact",
             "Measurable contribution to business strategy and results."),
            ("transformation", "Transformation and innovation",
             "Leading significant change in how the organization or HR operates."),
            ("profession", "Contribution to the HR profession",
             "Influence beyond the employer."),
        ],
        "categories": [],
    },
    {
        "program_key": "HRE_LOD",
        "organization": "HR Executive",
        "organization_short": "HR Executive",
        "recognition_name": "HR Leader of Distinction",
        "badge_label": "Leader of Distinction",
        "recognition_type": "Finalist",
        "recognition_tier": 3,
        "scoring_role": "secondary",
        "is_standing_honor": False,
        "analyst_weight": 2.5,
        "source_quality": "High",
        "award_frequency": "Annually, alongside HR Executive of the Year",
        "criteria_summary": (
            "Honorees recognized alongside the HR Executive of the Year, judged on the "
            "same criteria. Secondary to the annual winner."),
        "eligibility": "As HR Executive of the Year.",
        "nominated_by": "As HR Executive of the Year.",
        "judged_by": "As HR Executive of the Year.",
        "selection_process": "Selected in the same process as HR Executive of the Year.",
        "what_it_does_not_measure": "As HR Executive of the Year.",
        "peer_elected": False, "nomination_based": True, "self_nomination_allowed": None,
        "editorial_panel": True, "judging_panel": None,
        "quantitative_impact_considered": None, "business_impact_considered": True,
        "employee_outcomes_considered": None, "industry_influence_considered": True,
        "notes": None,
        "source_url": "https://hrexecutive.com/hr-executive-of-the-year/",
        "criteria": [],
        "categories": [],
    },
    {
        "program_key": "HRO_COY",
        "organization": "HRO Today",
        "organization_short": "HRO Today",
        "recognition_name": "CHRO of the Year",
        "badge_label": "HRO Today CHRO of the Year",
        "recognition_type": "Industry award",
        "recognition_tier": 1,
        "scoring_role": "core",
        "is_standing_honor": False,
        "analyst_weight": 4,
        "source_quality": "High",
        "award_frequency": "Annually: one winner in each category (about six per year)",
        "criteria_summary": (
            "Winners named in several categories each year (large, mid and small market, "
            "non-profit, sustainable workforce, lifetime achievement). Judged on outcomes, "
            "mostly from the prior year: the scope and preferably quantified impact of what "
            "changed, how much the nominee personally drove it, and the professional or "
            "reputational risk they took."),
        "eligibility": "CHROs and senior HR leaders; category depends on organization size "
                       "and type.",
        "nominated_by": "Nomination.",
        "judged_by": "HRO Today with previous award winners / judges.",
        "selection_process": (
            "Nominees are reviewed by HRO Today and previous award winners/judges. Finalists "
            "are named Leaders of Distinction; winners are selected by category."),
        "what_it_does_not_measure": (
            "Comparability across categories: a small-market winner competes in a very "
            "different field from a large-market winner, which is why weights vary by "
            "category here."),
        "peer_elected": False, "nomination_based": True, "self_nomination_allowed": None,
        "editorial_panel": False, "judging_panel": True,
        "quantitative_impact_considered": True, "business_impact_considered": True,
        "employee_outcomes_considered": None, "industry_influence_considered": False,
        "notes": "Outcome-focused criteria make this the most useful source for 'what did "
                 "they do'.",
        "source_url": "https://www.hrotoday.com/chro-of-the-year-award/"
                      "chro-of-the-year-award-nomination-criteria/",
        "criteria": [
            ("scope_impact", "Scope and measurable impact",
             "What changed, how large the impact was, and whether it can be quantified."),
            ("personal_leadership", "Personal leadership",
             "How far the nominee personally drove the initiative."),
            ("risk", "Professional or reputational risk",
             "Whether the leader took meaningful risk to achieve the result."),
        ],
        # (category, weight, is_standing_honor). PROPOSED 2026-10-15; edit and re-run seed.
        "categories": [
            ("Large Market", 4, False),
            ("Mid-Market", 3.5, False),
            ("Sustainable Workforce", 3.5, False),
            ("Small Market", 3, False),
            ("Non-Profit", 3, False),
            ("Lifetime Achievement", 4, True),
        ],
    },
    {
        "program_key": "HRO_LOD",
        "organization": "HRO Today",
        "organization_short": "HRO Today",
        "recognition_name": "Leader of Distinction",
        "badge_label": "Leader of Distinction",
        "recognition_type": "Finalist",
        "recognition_tier": 3,
        "scoring_role": "secondary",
        "is_standing_honor": False,
        "analyst_weight": 2,
        "source_quality": "High",
        "award_frequency": "Annually: finalists named before the category winners",
        "criteria_summary": "Finalists for HRO Today CHRO of the Year, judged on the same "
                            "criteria. Finalist-level recognition.",
        "eligibility": "As CHRO of the Year.",
        "nominated_by": "As CHRO of the Year.",
        "judged_by": "As CHRO of the Year.",
        "selection_process": "Named as finalists before category winners are selected.",
        "what_it_does_not_measure": "As CHRO of the Year.",
        "peer_elected": False, "nomination_based": True, "self_nomination_allowed": None,
        "editorial_panel": False, "judging_panel": True,
        "quantitative_impact_considered": True, "business_impact_considered": True,
        "employee_outcomes_considered": None, "industry_influence_considered": False,
        "notes": None,
        "source_url": "https://www.hrotoday.com/na-chro-winners-and-lods/",
        "criteria": [],
        "categories": [],
    },
    {
        "program_key": "N2_L40",
        "organization": "N2Growth",
        "organization_short": "N2Growth",
        "recognition_name": "Leaders40 Top CHRO",
        "badge_label": "N2Growth Leaders40",
        "recognition_type": "Executive ranking",
        "recognition_tier": 2,
        "scoring_role": "core",
        "is_standing_honor": False,
        "analyst_weight": 3,
        "source_quality": "Moderate-High",
        "award_frequency": "Annually: a ranked list of 40",
        "criteria_summary": (
            "A ranked list of 40 people leaders chosen by a panel of academic and industry "
            "experts. Assessed on organizational design and change, leadership development, "
            "business acumen and impact, culture and engagement, industry influence, "
            "people-centered leadership, workforce innovation and employee satisfaction."),
        "eligibility": "Senior people leaders; includes roles below CHRO and non-US leaders.",
        "nominated_by": "Nomination.",
        "judged_by": "Panel of academic and industry experts.",
        "selection_process": "A panel of academic and industry experts evaluates nominees "
                             "against published criteria and selects/ranks 40 honorees.",
        "what_it_does_not_measure": (
            "Rank precision: the published rank is captured, but the score treats #1 and "
            "#40 alike. Mixes CHROs with leaders below CHRO level."),
        "peer_elected": False, "nomination_based": True, "self_nomination_allowed": None,
        "editorial_panel": False, "judging_panel": True,
        "quantitative_impact_considered": None, "business_impact_considered": True,
        "employee_outcomes_considered": True, "industry_influence_considered": True,
        "notes": "2026 list not published as of 2026-10-15. Watchlist tracked separately.",
        "source_url": "https://www.n2growth.com/top-chro-list-the-people-leaders-to-watch/",
        "criteria": [
            ("org_design", "Organizational design and change", None),
            ("leadership_dev", "Leadership development", None),
            ("business_impact", "Business acumen and impact", None),
            ("culture", "Culture and employee engagement", None),
            ("influence", "Industry influence", None),
            ("people_centered", "People-centered leadership", None),
            ("workforce_innovation", "Workforce innovation", None),
            ("employee_satisfaction", "Employee satisfaction", None),
        ],
        "categories": [],
    },
    {
        "program_key": "N2_WATCH",
        "organization": "N2Growth",
        "organization_short": "N2Growth",
        "recognition_name": "Top CHRO Watchlist",
        "badge_label": "Watchlist",
        "recognition_type": "Watchlist",
        "recognition_tier": 4,
        "scoring_role": "unscored",
        "is_standing_honor": False,
        "analyst_weight": 1,
        "source_quality": "Moderate",
        "award_frequency": "Annually, alongside Leaders40",
        "criteria_summary": "A broader list published alongside Leaders40. Not equivalent to "
                            "Leaders40; shown as a signal only.",
        "eligibility": "As Leaders40.",
        "nominated_by": "As Leaders40.",
        "judged_by": "As Leaders40.",
        "selection_process": "Published alongside the Leaders40 list.",
        "what_it_does_not_measure": "Selectivity comparable to the ranked 40.",
        "peer_elected": False, "nomination_based": True, "self_nomination_allowed": None,
        "editorial_panel": False, "judging_panel": True,
        "quantitative_impact_considered": None, "business_impact_considered": None,
        "employee_outcomes_considered": None, "industry_influence_considered": None,
        "notes": "No watchlist entries in the seed workbook.",
        "source_url": "https://www.n2growth.com/top-chro-list-the-people-leaders-to-watch/",
        "criteria": [],
        "categories": [],
    },
]

# Publication status per program-year, spec section 25 (as of 2026-10-15).
# NEVER infer recipients for a 'pending' year.
CYCLES: list[tuple[str, int, str]] = [
    ("NAHR_FELLOW", 2025, "available"), ("NAHR_FELLOW", 2026, "pending"),
    ("HRE_EOY", 2025, "available"), ("HRE_EOY", 2026, "available"),
    ("HRE_LOD", 2025, "available"), ("HRE_LOD", 2026, "available"),
    ("HRO_COY", 2025, "available"), ("HRO_COY", 2026, "available"),
    ("HRO_LOD", 2025, "available"), ("HRO_LOD", 2026, "available"),
    ("N2_L40", 2025, "available"), ("N2_L40", 2026, "pending"),
]
CYCLES_AS_OF = "2026-10-15"
PENDING_EXPECTED_PERIOD = "September-November (spec default; verify)"

# Workbook (organization, recognition) -> program_key. COPIED from the workbook's values.
WORKBOOK_PROGRAM_MAP: dict[tuple[str, str], str] = {
    ("National Academy of Human Resources (NAHR)", "Fellow of the NAHR"): "NAHR_FELLOW",
    ("HR Executive", "HR Executive of the Year"): "HRE_EOY",
    ("HR Executive", "HR Leader of Distinction"): "HRE_LOD",
    ("HRO Today", "CHRO of the Year"): "HRO_COY",
    ("HRO Today", "Leader of Distinction"): "HRO_LOD",
    ("N2Growth", "Leaders40 Top CHRO"): "N2_L40",
}

# Recognitions that exist but are NOT scored here, and why. ANALYST ASSESSMENT 2026-10-15,
# grouped by the reason for exclusion (spec sections 27-28: memberships, speaking and
# company-level honors are different signals and must not be weighted like awards).
# Shown at the bottom of the Award criteria tab and in the PDF brief.
EXCLUDED_RECOGNITIONS: list[tuple[str, str, str]] = [
    # (group, examples, why not included)
    ("Employer / company-level lists",
     "Fortune 100 Best Companies to Work For (Great Place to Work), Gallup Exceptional "
     "Workplace Award, LinkedIn Top Companies",
     "They recognize the organization, not the CHRO personally. They are worth tracking later "
     "as a separate company signal, not counted as a CHRO award."),
    ("HR program and practice awards",
     "Brandon Hall Group HCM Excellence Awards, ATD BEST Awards",
     "They honor a specific program or team, often entered by vendors or teams. They are hard "
     "to attribute to the top HR executive."),
    ("Emerging-leader and HR-technology lists",
     "HR Executive's HR's Rising Awards and Top 100 HR Tech Influencers",
     "They target early-career professionals or HR-technology influence, a different "
     "population from enterprise CHROs."),
    ("Memberships and leadership roles",
     "CHRO Association, HR Policy Association, The Conference Board HR councils, "
     "association board seats",
     "Membership or service, not a selective external judgement. The spec says to track these "
     "later as a separate influence signal, never as awards."),
    ("Media 'influencer' lists",
     "Assorted publication and social-media influencer rankings",
     "Selection is usually editorial and driven by visibility, with little published method, "
     "so they mostly measure media presence."),
    ("Candidate sources not yet assessed",
     "SHRM, WorldatWork, Business Group on Health, ATD individual honors",
     "Named in the spec as possible additions. Each needs its method reviewed before it can "
     "be given a weight."),
]

# How nomination works -- VERIFIED 2026-10-15 from each award body's own pages
# (../research/nomination_rules.json holds sources and quotes). Merged into PROGRAMS below,
# so every program carries the same keys. None = the source does not say.
_NOMINATION: dict[str, dict] = {
    "NAHR_FELLOW": {
        "nominated_by": "Existing NAHR Fellows only. Fellows identify and nominate candidates "
                        "through a Fellows-only page; there is no public or self-nomination "
                        "route.",
        "judged_by": "Multi-layer peer review: candidate reviewers chosen by the Academy "
                     "President support the Board, the Board recommends candidates, and the "
                     "Fellows vote to elect them.",
        "nomination_requirements": (
            "Not published (materials are Fellows-only). Public criteria: leadership and "
            "impact, scope of role and recognition, competencies comparable to current "
            "Fellows, external influence (associations, civic work, public policy), knowledge "
            "development, character and integrity."),
        "nomination_timing": "Nomination window not public. New Fellows are inducted each "
                             "November (2026 induction: Nov 12, 2026).",
        "entry_fee": "None stated",
        "last_verified": "2026-10-15",
    },
    "HRE_EOY": {
        "criteria_summary": (
            "One winner a year, for organizations with more than 10,000 employees (mid-size "
            "organizations compete for HR Leader of Distinction). Open only to the top HR "
            "executive running the whole HR function, at least three years in the role, with "
            "a CEO recommendation. Judged on strategic contribution to the business, "
            "innovation and transformation, and contribution to the HR profession."),
        "eligibility": ("The organization's highest-ranking HR leader, with the full span of "
                        "HR including compensation; at least 3 years in the current role and "
                        "5+ years in HR. HR Executive of the Year is for organizations with "
                        "more than 10,000 employees (500-10,000 compete for HR Leader of "
                        "Distinction)."),
        "nominated_by": ("A company official of the nominee's own organization submits it, "
                         "and a letter of recommendation from the CEO is required. Outsiders "
                         "cannot nominate. In practice the nominee's own team often prepares "
                         "the entry; self-nomination is not addressed."),
        "judged_by": "HR Executive editorial staff, with outside judges.",
        "nomination_requirements": (
            "Online portal only: five data-backed essays (a major problem handled in the past "
            "2-3 years; innovative programs and measured results; how HR supports business "
            "objectives; leadership within HR; contributions to the profession), CEO letter, "
            "resume and headshot; optional supporting PDF."),
        "nomination_timing": ("2026 cycle: deadline June 12; selected people notified in "
                              "August; winner announced Sept 9 and honored at HR Tech in "
                              "October."),
        "entry_fee": "None stated",
        "last_verified": "2026-10-15",
    },
    "HRE_LOD": {
        # Owner decision 2026-10-15: a mid-size WINNER, not a finalist, so it counts as core
        # at weight 3 -- consistent with HRO Today's small/mid-market winners (3-3.5).
        "scoring_role": "core",
        "analyst_weight": 3,
        "recognition_tier": 2,
        "recognition_type": "Industry award (mid-size organizations)",
        "badge_label": "HR Leader of Distinction",
        "criteria_summary": (
            "HR Executive's award for the top HR leader at a MID-SIZE organization (500 to "
            "10,000 employees), judged on the same criteria as HR Executive of the Year, which "
            "is for organizations above 10,000. It is a size category, not a finalist list."),
        "eligibility": ("The highest-ranking HR leader at an organization with 500-10,000 "
                        "employees; at least 3 years in role and 5+ years in HR."),
        "nominated_by": ("As HR Executive of the Year: a company official of the nominee's "
                         "organization submits it, with a required CEO letter."),
        "judged_by": "HR Executive editorial staff, with outside judges.",
        "selection_process": ("Same process and criteria as HR Executive of the Year, for "
                              "mid-size organizations."),
        "what_it_does_not_measure": ("Leaders at organizations above 10,000 employees (they "
                                     "compete for HR Executive of the Year)."),
        "nomination_requirements": "As HR Executive of the Year.",
        "nomination_timing": "As HR Executive of the Year (2026 honoree announced Sept 9).",
        "entry_fee": "None stated",
        "last_verified": "2026-10-15",
    },
    "HRO_COY": {
        "nominated_by": ("Anyone, typically a colleague or someone at the nominee's company "
                         "(\"Nominate your CHRO or a colleague\"). Vendors cannot nominate "
                         "directly; they must have the client's team submit. The nominee "
                         "must be told of the nomination. Self-nomination is not addressed."),
        "judged_by": ("HRO Today's editorial board reviews nominees; a judging panel of "
                      "previous winners scores them; finalists are named Leaders of "
                      "Distinction and winners are revealed at the awards gala."),
        "nomination_requirements": (
            "Online form: a narrative of the key initiative(s) the nominee led, quantified "
            "impact (people affected, profit or cost impact), a 1-10 rating of how far the "
            "nominee personally drove it, CHRO tenure, bio and headshot. Finalists must "
            "attend the gala."),
        "nomination_timing": ("2027 cycle: opened Sept 1, 2026, closes Dec 11, 2026; "
                              "finalists contacted March 2027; winners announced "
                              "May 13, 2027."),
        "entry_fee": "None stated",
        "what_it_does_not_measure": (
            "Comparability across categories: a small-market winner competes in a very "
            "different field from a large-market winner, which is why weights vary by "
            "category here. Finalists must attend the gala, which can exclude some leaders."),
        "last_verified": "2026-10-15",
    },
    "HRO_LOD": {
        "nominated_by": ("As CHRO of the Year: anyone, typically a colleague; vendors must "
                         "have the client's team submit."),
        "judged_by": "HRO Today editorial board and a panel of previous winners.",
        "nomination_requirements": "As CHRO of the Year.",
        "nomination_timing": ("Leaders of Distinction are announced about a month before the "
                              "winners (April for the North America cycle)."),
        "entry_fee": "None stated",
        "last_verified": "2026-10-15",
    },
    "N2_L40": {
        "nominated_by": ("Anyone, by emailing N2Growth (topchrolist@n2growth.com) or using "
                         "its contact page. There is no form, deadline or stated restriction; "
                         "self-nomination is not addressed."),
        "judged_by": ("A panel of academic and industry experts led by N2Growth's chairman "
                      "(the list launched with Stanford GSB in 2020). N2Growth is an "
                      "executive search firm; whether its own research feeds selection is "
                      "not stated."),
        "nomination_requirements": "None published: an informal email nomination.",
        "nomination_timing": ("List published each fall; no nomination window stated. The "
                              "2026 list had not appeared as of Oct 15, 2026."),
        "entry_fee": "None stated",
        "last_verified": "2026-10-15",
    },
    "N2_WATCH": {
        "nominated_by": "Not stated. N2Growth does not explain how the Watchlist is chosen.",
        "judged_by": "Not stated.",
        "nomination_requirements": "Not stated.",
        "nomination_timing": "Published alongside Leaders40.",
        "entry_fee": "None stated",
        "last_verified": "2026-10-15",
    },
}

_NOMINATION_KEYS = ("nomination_requirements", "nomination_timing", "entry_fee",
                    "last_verified")
for _p in PROGRAMS:
    for _k in _NOMINATION_KEYS:
        _p.setdefault(_k, None)
    _p.update(_NOMINATION.get(_p["program_key"], {}))
