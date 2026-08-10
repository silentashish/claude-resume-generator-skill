"""Optional Word rendering from the same validated payload.

Some application portals only accept .docx, and a few older ATS parse Word more
reliably than PDF. This renders from resume_data.json directly rather than
converting the PDF -- PDF-to-Word conversion produces text boxes and floating
frames, which is exactly the structure that breaks ATS extraction.

Mirrors the LaTeX template: Calibri, uppercase name, blue underlined
hyperlinks, **bold** markers converted to bold runs, and the same section
order (Summary, Skills, Work Experience, Projects, Publications, Education,
Certifications).

Dates are right-aligned with a real right tab stop set to
(page width - left margin - right margin), not TabStopPosition.MAX, which
overshoots and wraps the date to the next line.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import docx.oxml.ns as ns
from docx import Document
from docx.oxml import OxmlElement
from docx.shared import Inches, Pt, RGBColor

LINK_BLUE = RGBColor(0x05, 0x63, 0xC1)
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)


def _short_url(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url or "").rstrip("/")


def _add_runs(p, text, italic=False):
    """Add text to a paragraph, converting **markers** into bold runs."""
    pos = 0
    for m in _BOLD_RE.finditer(text):
        if m.start() > pos:
            r = p.add_run(text[pos:m.start()])
            r.italic = italic
        r = p.add_run(m.group(1))
        r.bold = True
        r.italic = italic
        pos = m.end()
    if pos < len(text):
        r = p.add_run(text[pos:])
        r.italic = italic


def _add_hyperlink(p, url, text):
    """A real clickable link (blue, underlined) -- python-docx has no API for
    this, so build the w:hyperlink element directly."""
    r_id = p.part.relate_to(
        url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(ns.qn("r:id"), r_id)
    run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(ns.qn("w:val"), "0563C1")
    u = OxmlElement("w:u")
    u.set(ns.qn("w:val"), "single")
    rpr.append(color)
    rpr.append(u)
    run.append(rpr)
    t = OxmlElement("w:t")
    t.text = text
    run.append(t)
    link.append(run)
    p._p.append(link)


def _heading(doc, text, section):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run(text.upper())
    r.bold = True
    r.font.size = Pt(11)
    return p


def _tight(p):
    p.paragraph_format.space_after = Pt(0)
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
    r = p.add_run(c["name"].upper())
    r.bold = True
    r.font.size = Pt(16)

    line1 = _tight(doc.add_paragraph())
    line1.alignment = 1
    parts1 = [c.get("location"),
              f"Phone: {c['phone']}" if c.get("phone") else None,
              f"Email: {c['email']}" if c.get("email") else None]
    line1.add_run(" | ".join(x for x in parts1 if x))

    line2 = _tight(doc.add_paragraph())
    line2.alignment = 1
    first = True
    for key, label in (("linkedin", "LinkedIn"), ("github", "GitHub"),
                       ("website", "Portfolio")):
        disp = c.get(key)
        if not disp:
            continue
        if not first:
            line2.add_run(" | ")
        first = False
        line2.add_run(f"{label}: ")
        url = c.get(f"{key}_url")
        if url:
            _add_hyperlink(line2, url, disp)
        else:
            line2.add_run(disp)

    if raw.get("summary"):
        _heading(doc, "Summary", sec)
        _add_runs(doc.add_paragraph(), raw["summary"])

    _heading(doc, "Skills", sec)
    for g in raw["skills"]:
        sp = _tight(doc.add_paragraph(style="List Bullet"))
        sr = sp.add_run(g["label"] + ": ")
        sr.bold = True
        _add_runs(sp, g["items"])

    _heading(doc, "Work Experience", sec)
    for role in raw["experience"]:
        left = role["company"] + (f" - {role['location']}" if role.get("location") else "")
        rp = _tight(doc.add_paragraph())
        rr = rp.add_run(left)
        rr.bold = True
        tp = doc.add_paragraph()
        tp.paragraph_format.space_after = Pt(1)
        tr = tp.add_run(role["title"])
        tr.italic = True
        tp.add_run(" | ")
        dr = tp.add_run(role["dates"])
        dr.bold = True
        for b in role["bullets"]:
            bp = _tight(doc.add_paragraph(style="List Bullet"))
            _add_runs(bp, b)
        if role.get("project_name"):
            pp = _tight(doc.add_paragraph())
            pp.paragraph_format.left_indent = Inches(0.25)
            pp.add_run("Project: ")
            if role.get("project_url"):
                _add_hyperlink(pp, role["project_url"], role["project_name"])
            else:
                pp.add_run(role["project_name"])

    if raw.get("projects"):
        _heading(doc, "Projects", sec)
        for pr in raw["projects"]:
            hp = _tight(doc.add_paragraph())
            hr = hp.add_run(pr["name"])
            hr.bold = True
            if pr.get("url"):
                hp.add_run(" | GitHub: ")
                _add_hyperlink(hp, pr["url"], _short_url(pr["url"]))
            for b in pr.get("bullets", []):
                bp = _tight(doc.add_paragraph(style="List Bullet"))
                _add_runs(bp, b)

    if raw.get("publications"):
        _heading(doc, "Publications", sec)
        for pub in raw["publications"]:
            pp = _tight(doc.add_paragraph(style="List Bullet"))
            tr = pp.add_run(pub["title"])
            tr.bold = True
            meta = ", ".join(x for x in (pub.get("venue"), pub.get("year")) if x)
            if meta:
                pp.add_run(f" ({meta})")
            if pub.get("note"):
                pp.add_run(": ")
                _add_runs(pp, pub["note"])
            if pub.get("url"):
                pp.add_run(" ")
                _add_hyperlink(pp, pub["url"], pub.get("link_label") or "Link")

    _heading(doc, "Education", sec)
    for e in raw["education"]:
        ip = _tight(doc.add_paragraph())
        ir = ip.add_run(e["institution"])
        ir.bold = True
        dp = _tight(doc.add_paragraph())
        degr = dp.add_run(e["degree"])
        degr.italic = True
        dp.add_run(" | ")
        ddr = dp.add_run(e["dates"])
        ddr.bold = True
        if e.get("detail"):
            _tight(doc.add_paragraph(e["detail"]))

    if raw.get("certifications"):
        _heading(doc, "Certifications", sec)
        cp = _tight(doc.add_paragraph())
        for i, cert in enumerate(raw["certifications"]):
            if i:
                cp.add_run(" | ")
            if cert.get("url"):
                _add_hyperlink(cp, cert["url"], cert["name"])
            else:
                nr = cp.add_run(cert["name"])
                nr.bold = True
            rest = ""
            if cert.get("issuer"):
                rest += f" ({cert['issuer']})"
            if cert.get("year"):
                rest += f" {cert['year']}"
            if rest:
                cp.add_run(rest)

    doc.save(str(out_path))
    return out_path


if __name__ == "__main__":
    raw = json.loads(Path(sys.argv[1]).read_text())
    print(build_docx(raw, Path(sys.argv[2])))
