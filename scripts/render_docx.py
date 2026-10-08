"""Optional Word rendering from the same validated payload.

Some application portals only accept .docx, and a few older ATS parse Word more
reliably than PDF. This renders from resume_data.json directly rather than
converting the PDF -- PDF-to-Word conversion produces text boxes and floating
frames, which is exactly the structure that breaks ATS extraction.

Mirrors the LaTeX template: Calibri, uppercase name, ruled uppercase section
headings, the same two-line entry header in every section, blue underlined
hyperlinks, **bold** markers converted to bold runs, the same section order
(Summary, Skills, Work Experience, Projects, Publications, Education,
Certifications), and a name/page footer on every page after the first.

With "date_style": "right", dates sit on a real right tab stop set to
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


def _add_hyperlink(p, url, text, bold=False):
    """A real clickable link (blue, underlined) -- python-docx has no API for
    this, so build the w:hyperlink element directly."""
    r_id = p.part.relate_to(
        url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(ns.qn("r:id"), r_id)
    run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    if bold:
        rpr.append(OxmlElement("w:b"))
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


def _bottom_border(p):
    """Hairline under a heading paragraph, the Word equivalent of \\titlerule."""
    ppr = p._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(ns.qn("w:val"), "single")
    bottom.set(ns.qn("w:sz"), "6")
    bottom.set(ns.qn("w:space"), "1")
    bottom.set(ns.qn("w:color"), "464646")
    borders.append(bottom)
    ppr.append(borders)


def _heading(doc, text, section):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(9)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text.upper())
    r.bold = True
    r.font.size = Pt(doc.styles["Normal"].font.size.pt + 1.5)
    _bottom_border(p)
    return p


def _tight(p):
    p.paragraph_format.space_after = Pt(0)
    return p


def _entry_gap(doc):
    """Even vertical rhythm between entries, mirroring \\entryskip."""
    g = doc.add_paragraph()
    g.paragraph_format.space_after = Pt(0)
    g.paragraph_format.line_spacing = Pt(4)
    return g


def _right_tab(p, section):
    width = section.page_width - section.left_margin - section.right_margin
    ppr = p._p.get_or_add_pPr()
    tabs = OxmlElement("w:tabs")
    tab = OxmlElement("w:tab")
    tab.set(ns.qn("w:val"), "right")
    tab.set(ns.qn("w:pos"), str(int(width / 635)))  # EMU -> twips
    tabs.append(tab)
    ppr.append(tabs)


def _entry_header(doc, primary, dates, secondary, location, date_style):
    """The same two-line header the LaTeX template uses in every section:
    bold primary [| location] [dates], then italic secondary [| bold dates]."""
    section = doc.sections[0]
    p1 = _tight(doc.add_paragraph())
    p1.paragraph_format.keep_with_next = True
    r = p1.add_run(primary)
    r.bold = True
    if location:
        p1.add_run(f" | {location}")
    if date_style == "right":
        _right_tab(p1, section)
        p1.add_run("\t")
        dr = p1.add_run(dates)
        dr.bold = True
    p2 = _tight(doc.add_paragraph())
    p2.paragraph_format.keep_with_next = True
    p2.paragraph_format.space_after = Pt(1)
    sr = p2.add_run(secondary)
    sr.italic = True
    if date_style != "right":
        p2.add_run(" | ")
        dr = p2.add_run(dates)
        dr.bold = True


def _footer(doc, name):
    """Name and page number on every page but the first, as in the PDF."""
    section = doc.sections[0]
    section.different_first_page_header_footer = True
    p = section.footer.paragraphs[0]
    p.alignment = 1
    r = p.add_run(f"{name} | Page ")
    r.font.size = Pt(8)
    r.font.color.rgb = RGBColor(0x78, 0x78, 0x78)
    run = p.add_run()
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(0x78, 0x78, 0x78)
    for tag, text in (("begin", None), (None, "PAGE"), ("end", None)):
        if tag:
            el = OxmlElement("w:fldChar")
            el.set(ns.qn("w:fldCharType"), tag)
        else:
            el = OxmlElement("w:instrText")
            el.set(ns.qn("xml:space"), "preserve")
            el.text = text
        run._r.append(el)


def build_docx(raw: dict, out_path: Path, settings: dict | None = None) -> Path:
    """Render the payload to Word.

    `settings` is the typography the PDF autofit chose (font_size, margin,
    item_sep), so the Word file follows the same density. Word has no autofit
    of its own and renders Calibri with slightly different metrics, so its
    page count is close to the PDF's rather than guaranteed equal.
    """
    settings = settings or {}
    font_pt = float(settings.get("font_size", 10))
    margin_in = float(settings.get("margin", 0.6))
    item_sep = float(settings.get("item_sep", 1.5))

    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = sec.bottom_margin = Inches(margin_in)
    sec.left_margin = sec.right_margin = Inches(margin_in)
    date_style = raw.get("date_style", "inline")

    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(font_pt)
    normal.paragraph_format.space_after = Pt(0)
    bullets = doc.styles["List Bullet"]
    bullets.font.name = "Calibri"
    bullets.font.size = Pt(font_pt)
    bullets.paragraph_format.space_after = Pt(item_sep)

    c = raw["contact"]
    p = doc.add_paragraph()
    p.alignment = 1
    r = p.add_run(c["name"].upper())
    r.bold = True
    r.font.size = Pt(font_pt + 7)

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
        sp = doc.add_paragraph()
        sp.paragraph_format.space_after = Pt(1.5)
        sr = sp.add_run(g["label"] + ": ")
        sr.bold = True
        _add_runs(sp, g["items"])

    _heading(doc, "Work Experience", sec)
    for i, role in enumerate(raw["experience"]):
        if i:
            _entry_gap(doc)
        _entry_header(doc, role["company"], role["dates"], role["title"],
                      role.get("location"), date_style)
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
        for i, pr in enumerate(raw["projects"]):
            if i:
                _entry_gap(doc)
            hp = _tight(doc.add_paragraph())
            hp.paragraph_format.keep_with_next = True
            hr = hp.add_run(pr["name"])
            hr.bold = True
            if pr.get("url"):
                hp.add_run(" | GitHub: ")
                _add_hyperlink(hp, pr["url"], _short_url(pr["url"]))
            if pr.get("tech"):
                tp = _tight(doc.add_paragraph())
                tp.paragraph_format.keep_with_next = True
                tr = tp.add_run(pr["tech"])
                tr.italic = True
            for b in pr.get("bullets", []):
                bp = _tight(doc.add_paragraph(style="List Bullet"))
                _add_runs(bp, b)

    if raw.get("publications"):
        _heading(doc, "Publications" + (raw.get("publications_suffix") or ""), sec)
        for pub in raw["publications"]:
            pp = _tight(doc.add_paragraph(style="List Bullet"))
            tr = pp.add_run(pub["title"])
            tr.bold = True
            meta = ", ".join(x for x in (pub.get("venue"), pub.get("year")) if x)
            if meta:
                pp.add_run(f" ({meta})")
            if pub.get("note"):
                pp.add_run(". ")
                _add_runs(pp, pub["note"])
            if pub.get("url"):
                pp.add_run(" ")
                _add_hyperlink(pp, pub["url"], pub.get("link_label") or "Link")

    _heading(doc, "Education", sec)
    for i, e in enumerate(raw["education"]):
        if i:
            _entry_gap(doc)
        _entry_header(doc, e["institution"], e["dates"], e["degree"],
                      e.get("location"), date_style)
        if e.get("detail"):
            _tight(doc.add_paragraph(e["detail"]))

    if raw.get("certifications"):
        _heading(doc, "Certifications", sec)
        for cert in raw["certifications"]:
            cp = _tight(doc.add_paragraph(style="List Bullet"))
            if cert.get("url"):
                _add_hyperlink(cp, cert["url"], cert["name"], bold=True)
            else:
                nr = cp.add_run(cert["name"])
                nr.bold = True
            if cert.get("issuer"):
                cp.add_run(f", {cert['issuer']}")
            if cert.get("year"):
                cp.add_run(f", {cert['year']}")

    _footer(doc, c["name"])
    doc.save(str(out_path))
    return out_path


if __name__ == "__main__":
    raw = json.loads(Path(sys.argv[1]).read_text())
    settings = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
    print(build_docx(raw, Path(sys.argv[2]), settings))
