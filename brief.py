"""The downloadable PDF award brief (Award criteria tab). Pure: data in, PDF bytes out.

No database access here -- the app passes in what it already loaded, so the brief always
matches the screen. Built with reportlab (pure Python; runs on Streamlit Cloud).
"""
from __future__ import annotations

import io
from datetime import date
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

NAVY = colors.HexColor("#1f2a44")
ACCENT = colors.HexColor("#3b6fb6")
GOLD = colors.HexColor("#b8860b")
RULE = colors.HexColor("#d5dae3")
SHADE = colors.HexColor("#f3f5f9")
MUTED = colors.HexColor("#5b6475")

CAVEAT = ("External recognition indicates professional visibility, peer reputation, industry "
          "influence and/or recognized leadership impact. It is not a measure of CHRO "
          "performance, and a lack of awards is never evidence of weak leadership. Weights, "
          "tiers and source-quality ratings are analyst judgements, not published by the award "
          "bodies.")


def _styles() -> dict:
    base = getSampleStyleSheet()
    s = {
        "title": ParagraphStyle("t", parent=base["Title"], fontName="Helvetica-Bold",
                                fontSize=20, leading=24, textColor=NAVY, alignment=TA_LEFT,
                                spaceAfter=2),
        "sub": ParagraphStyle("s", parent=base["Normal"], fontSize=10, textColor=MUTED,
                              spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName="Helvetica-Bold",
                             fontSize=13, leading=16, textColor=NAVY, spaceBefore=10,
                             spaceAfter=4),
        "h3": ParagraphStyle("h3", parent=base["Heading3"], fontName="Helvetica-Bold",
                             fontSize=9, leading=11, textColor=ACCENT, spaceBefore=5,
                             spaceAfter=1),
        "body": ParagraphStyle("b", parent=base["Normal"], fontSize=9, leading=12.5),
        "small": ParagraphStyle("sm", parent=base["Normal"], fontSize=7.5, leading=10,
                                textColor=MUTED),
        "cell": ParagraphStyle("c", parent=base["Normal"], fontSize=8, leading=10),
        "cellb": ParagraphStyle("cb", parent=base["Normal"], fontName="Helvetica-Bold",
                                fontSize=8, leading=10, textColor=colors.white),
        "caveat": ParagraphStyle("cv", parent=base["Normal"], fontSize=8.5, leading=11.5,
                                 textColor=NAVY, backColor=SHADE, borderPadding=7,
                                 spaceBefore=4, spaceAfter=10),
    }
    return s


def _p(text, style) -> Paragraph:
    return Paragraph(escape(str(text or "—")), style)


def _w(x) -> str:
    return f"{float(x):g}" if x is not None else "—"


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.line(0.75 * inch, 0.6 * inch, letter[0] - 0.75 * inch, 0.6 * inch)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.75 * inch, 0.45 * inch,
                      "CHRO External Recognition · Award brief · analyst assessment")
    canvas.drawRightString(letter[0] - 0.75 * inch, 0.45 * inch, f"Page {doc.page}")
    canvas.restoreState()


def build_award_brief(programs: list[dict], recipients: dict[str, list[str]],
                      excluded: list[tuple[str, str, str]], window: tuple[int, ...],
                      as_of: date | None = None,
                      profiles: dict[str, list[tuple[str, str, str]]] | None = None,
                      examples: dict[str, list[dict]] | None = None) -> bytes:
    """programs: rows as the app loads them (with 'criteria' lists), ALREADY in display order.
    recipients: program_key -> ['Name (Company, Year)', ...] most recent first.
    profiles: program_key -> [(measure, typical, based on), ...] (app.profile_lines).
    examples: program_key -> [{name, company, year, headline, what, evidence}, ...]."""
    profiles = profiles or {}
    examples = examples or {}
    s = _styles()
    as_of = as_of or date.today()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.75 * inch,
                            rightMargin=0.75 * inch, topMargin=0.7 * inch,
                            bottomMargin=0.8 * inch, title="CHRO Recognition — Award Brief",
                            author="CHRO External Recognition")
    story = [
        _p("CHRO Recognition: Award Brief", s["title"]),
        _p(f"How each recognition is decided and weighted · Analysis window "
           f"{window[0]}–{window[-1]} · Prepared {as_of:%B %d, %Y}", s["sub"]),
        _p(CAVEAT, s["caveat"]),
        _p("At a glance", s["h2"]),
    ]

    head = ["Recognition", "Awarded by", "Type", "Tier", "Weight", "Counts as", "How often"]
    rows = [[_p(h, s["cellb"]) for h in head]]
    for p in programs:
        rows.append([_p(p["badge_label"], s["cell"]), _p(p["organization_short"], s["cell"]),
                     _p(p["recognition_type"], s["cell"]), _p(p["recognition_tier"], s["cell"]),
                     _p(_w(p["analyst_weight"]), s["cell"]),
                     _p(p["scoring_role"] + (" · standing" if p["is_standing_honor"] else ""),
                        s["cell"]),
                     _p(p.get("award_frequency"), s["cell"])])
    t = Table(rows, colWidths=[1.35 * inch, 0.9 * inch, 0.95 * inch, 0.38 * inch,
                               0.6 * inch, 0.85 * inch, 1.97 * inch], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SHADE]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story += [t, Spacer(1, 4),
              _p("Standing honors count whenever awarded; other recognitions count inside the "
                 "rolling window. Secondary (finalist) recognition is shown but excluded from "
                 "the core score.", s["small"]),
              _p("Award definitions", s["h2"])]

    for p in programs:
        # Only the colored header and the summary are kept together; the rest flows, so a
        # long section never leaves half a page blank before it.
        head_block = [
            Table([[_p(f"{p['badge_label']} · {p['organization']}", ParagraphStyle(
                "bh", parent=s["body"], fontName="Helvetica-Bold", textColor=colors.white))]],
                colWidths=[7.0 * inch],
                style=[("BACKGROUND", (0, 0), (-1, -1), GOLD if p["recognition_tier"] == 1
                        else ACCENT if p["recognition_tier"] == 2 else MUTED),
                       ("TOPPADDING", (0, 0), (-1, -1), 4),
                       ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]),
            Spacer(1, 3),
            _p(p["criteria_summary"], s["body"]),
        ]
        block = [
            _p("How often", s["h3"]), _p(p.get("award_frequency"), s["body"]),
            _p("Who is eligible", s["h3"]), _p(p["eligibility"] or "Not stated", s["body"]),
            _p("Who can nominate", s["h3"]), _p(p["nominated_by"] or "Not stated", s["body"]),
            _p("Who decides", s["h3"]), _p(p["judged_by"] or "Not stated", s["body"]),
            _p("What a nomination requires · timing · fee", s["h3"]),
            _p(f"{p.get('nomination_requirements') or 'Not stated.'} Timing: "
               f"{(p.get('nomination_timing') or 'not stated').rstrip('.')}. Entry fee: "
               f"{(p.get('entry_fee') or 'not stated').rstrip('.')}. Self-nomination: "
               + ("allowed." if p.get("self_nomination_allowed") is True else
                  "not allowed." if p.get("self_nomination_allowed") is False else
                  "not addressed by the award body."), s["body"]),
        ]
        if p["criteria"]:
            block.append(_p("Published criteria", s["h3"]))
            block += [_p(f"• {c['label']}" + (f": {c['description']}" if c["description"]
                                               else ""), s["body"]) for c in p["criteria"]]
        block += [_p("What it does not measure", s["h3"]),
                  _p(p["what_it_does_not_measure"], s["body"])]
        recent = recipients.get(p["program_key"], [])
        block += [_p("Recent recipients (in this dataset)", s["h3"]),
                  _p("; ".join(recent) if recent else "None recorded yet.", s["body"])]
        prof = profiles.get(p["program_key"])
        if prof:
            prow = [[_p(h, s["cellb"]) for h in ("Typical recipient", "Typical", "Based on")]]
            prow += [[_p(a, s["cell"]), _p(b, s["cell"]), _p(c, s["cell"])]
                     for a, b, c in prof]
            pt = Table(prow, colWidths=[3.0 * inch, 2.5 * inch, 1.5 * inch])
            pt.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SHADE]),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, RULE),
                ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            block += [Spacer(1, 4), pt,
                      _p("'Based on' = recipients with that fact verified so far. Board "
                         "seats are those on record, not a confirmed absence.", s["small"])]
        ex = examples.get(p["program_key"], [])
        block.append(_p("Recent examples, and why they won", s["h3"]))
        if not ex:
            block.append(_p("None yet: examples appear once recipients' accomplishments are "
                            "approved.", s["body"]))
        for x in ex:
            block.append(Paragraph(
                f"<b>{escape(x['name'])}</b> ({escape(x['company'])}, {x['year']}): "
                f"<i>{escape(x['headline'])}</i>. {escape(x['what'])} "
                f"<font color='#5b6475'>[evidence: {escape(x['evidence'])}]</font>",
                s["body"]))
        block += [
                  _p(f"Analyst weight {_w(p['analyst_weight'])} · tier "
                     f"{p['recognition_tier']} · source quality {p['source_quality']} "
                     f"(analyst) · nomination details verified "
                     f"{p.get('last_verified') or 'not yet'} · source: {p['source_url']}",
                     s["small"]),
                  Spacer(1, 8)]
        story.append(KeepTogether(head_block))
        story += block

    story.append(_p("Recognitions considered but not included", s["h2"]))
    ex_rows = [[_p(h, s["cellb"]) for h in ("Group", "Examples", "Why not included")]]
    ex_rows += [[_p(g, s["cell"]), _p(e, s["cell"]), _p(w, s["cell"])] for g, e, w in excluded]
    ex = Table(ex_rows, colWidths=[1.45 * inch, 2.35 * inch, 3.2 * inch], repeatRows=1)
    ex.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SHADE]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(ex)
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
