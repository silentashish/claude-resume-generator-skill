"""Optional Word rendering from the same validated payload.

Some application portals only accept .docx, and a few older ATS parse Word more
reliably than PDF. This renders from resume_data.json directly rather than
converting the PDF -- PDF-to-Word conversion produces text boxes and floating
frames, which is exactly the structure that breaks ATS extraction.

Dates are right-aligned with a real right tab stop set to
(page width - left margin - right margin), not TabStopPosition.MAX, which
overshoots and wraps the date to the next line.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_TAB_ALIGNMENT
from docx.shared import Inches, Pt


def _right_tab_dxa(section) -> int:
    return section.page_width - section.left_margin - section.right_margin


def _heading(doc, text, section):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run(text.upper())
    r.bold = True
    r.font.size = Pt(11)
    return p


def _row(doc, left_bold, left_rest, right, section):
    """One line with bold left text and a right-aligned date."""
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.tab_stops.add_tab_stop(
        _right_tab_dxa(section), WD_TAB_ALIGNMENT.RIGHT
    )
    r = p.add_run(left_bold)
    r.bold = True
    if left_rest:
        p.add_run(left_rest)
    p.add_run("\t" + right)
    return p


def build_docx(raw: dict, out_path: Path) -> Path:
    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = sec.bottom_margin = Inches(0.5)
    sec.left_margin = sec.right_margin = Inches(0.6)

    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10)

    c = raw["contact"]
    p = doc.add_paragraph()
    p.alignment = 1
    r = p.add_run(c["name"])           # title case, not all caps
    r.bold = True
    r.font.size = Pt(18)

    parts = [c.get(k) for k in ("location", "phone", "email", "linkedin", "github", "website")]
    p2 = doc.add_paragraph(" | ".join(x for x in parts if x))
    p2.alignment = 1

    if raw.get("summary"):
        _heading(doc, "Summary", sec)
        doc.add_paragraph(raw["summary"])

    _heading(doc, "Experience", sec)
    for role in raw["experience"]:
        left = role["company"] + (f", {role['location']}" if role.get("location") else "")
        _row(doc, role["company"], left[len(role["company"]):], role["dates"], sec)
        tp = doc.add_paragraph()
        tp.paragraph_format.space_after = Pt(1)
        tr = tp.add_run(role["title"])
        tr.italic = True
        for b in role["bullets"]:
            bp = doc.add_paragraph(b, style="List Bullet")
            bp.paragraph_format.space_after = Pt(0)

    if raw.get("projects"):
        _heading(doc, "Projects", sec)
        for pr in raw["projects"]:
            _row(doc, pr["name"], "", pr.get("tech") or "", sec)
            for b in pr.get("bullets", []):
                bp = doc.add_paragraph(b, style="List Bullet")
                bp.paragraph_format.space_after = Pt(0)

    _heading(doc, "Education", sec)
    for e in raw["education"]:
        _row(doc, e["institution"], "", e["dates"], sec)
        doc.add_paragraph(e["degree"] + (f" -- {e['detail']}" if e.get("detail") else ""))

    _heading(doc, "Skills", sec)
    for g in raw["skills"]:
        sp = doc.add_paragraph()
        sp.paragraph_format.space_after = Pt(0)
        sr = sp.add_run(g["label"] + ": ")
        sr.bold = True
        sp.add_run(g["items"])

    if raw.get("certifications"):
        _heading(doc, "Certifications", sec)
        for cert in raw["certifications"]:
            cp = doc.add_paragraph(style="List Bullet")
            cp.paragraph_format.space_after = Pt(0)
            nr = cp.add_run(cert["name"])
            nr.bold = True
            rest = ""
            if cert.get("issuer"):
                rest += f", {cert['issuer']}"
            if cert.get("year"):
                rest += f" ({cert['year']})"
            if rest:
                cp.add_run(rest)

    if raw.get("publications"):
        _heading(doc, "Publications", sec)
        for pub in raw["publications"]:
            line = pub["title"]
            if pub.get("venue"):
                line += f". {pub['venue']}"
            if pub.get("year"):
                line += f", {pub['year']}"
            if pub.get("url"):
                line += f". {pub['url']}"
            pp = doc.add_paragraph(line, style="List Bullet")
            pp.paragraph_format.space_after = Pt(0)

    doc.save(str(out_path))
    return out_path


if __name__ == "__main__":
    raw = json.loads(Path(sys.argv[1]).read_text())
    print(build_docx(raw, Path(sys.argv[2])))
