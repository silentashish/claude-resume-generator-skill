"""Verify a compiled resume PDF: ATS extraction plus physical layout.

Usage:
    python3 verify.py resume.pdf [--data resume_data.json] [--jd job-description.md]
                                 [--target-pages 2]

Everything here reads the *compiled artifact*, not the source. That is the
point: the payload can be perfect and the PDF still extract as scrambled text.
Coordinates come from PyMuPDF, so alignment and margin checks are measured in
points rather than guessed from a page image.

Exit code is 0 when every hard check passes, 1 otherwise, so a build loop can
branch on it.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pymupdf

REQUIRED_SECTIONS = ["experience", "education", "skills"]
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
YEAR_RE = re.compile(r"(19|20)\d{2}")
DATE_TOKEN_RE = re.compile(
    r"^(19|20)\d{2}$|^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r"|Present$|^(19|20)\d{2}[-\u2013]"
)


def _raw_extract(pdf_path) -> str:
    """Text as a naive, layout-unaware parser would see it."""
    import subprocess
    try:
        r = subprocess.run(["pdftotext", str(pdf_path), "-"],
                           capture_output=True, text=True, timeout=30)
        return r.stdout
    except Exception:
        return ""


def _check(name, passed, detail, hard=True):
    return {"check": name, "passed": bool(passed), "detail": detail, "hard": hard}


def extract(pdf_path: Path):
    doc = pymupdf.open(pdf_path)
    pages = [p.get_text() for p in doc]
    return doc, "\n".join(pages)


def check_ats(doc, text, data=None):
    results = []
    words = len(text.split())
    results.append(_check("text_extractable", words > 120,
                          f"{words} words extracted from the PDF"))

    low = text.lower()
    missing = [s for s in REQUIRED_SECTIONS if s not in low]
    results.append(_check("section_headers_intact", not missing,
                          "all standard headers found" if not missing
                          else f"missing section headers: {missing}"))

    # A template variable that silently resolved to a Python object prints its
    # repr into the PDF. It reads as gibberish to a human and poisons the
    # keyword text for a parser, so treat any repr fragment as a hard failure.
    # Matched case-insensitively on word boundaries: section headings render in
    # caps, so a leaked None once hid inside "PUBLICATIONSNONE".
    leak_patterns = [r"built-in method", r"object at 0x", r"<bound method",
                     r"\bUndefined\b", r"\bNone\b", r"(?<=[A-Z])NONE\b"]
    leaks = [p for p in leak_patterns if re.search(p, text)]
    results.append(_check("no_unresolved_placeholders", not leaks,
                          "no template leakage" if not leaks
                          else f"template variable leaked into the PDF: {leaks}"))

    emails = EMAIL_RE.findall(text)
    results.append(_check("email_extractable", bool(emails),
                          f"found {emails[0]}" if emails else "no email in extracted text"))

    if data:
        name = data["contact"]["name"]
        first_page = doc[0].get_text()
        # Extraction can split a name across whitespace; compare token by token.
        # Case-insensitive because the template renders the name in caps.
        fp_low = first_page.lower()
        ok = all(part.lower() in fp_low for part in name.split())
        results.append(_check("name_on_first_page", ok,
                              f"'{name}' present" if ok else f"'{name}' not found on page 1"))

        companies = [r["company"] for r in data.get("experience", [])]
        miss = [c for c in companies if c.split(",")[0] not in text]
        results.append(_check("employers_extractable", not miss,
                              "all employers present" if not miss else f"missing: {miss}"))

    # Raw-mode extractors (no layout analysis) break lines on wide whitespace
    # gaps, which is exactly what \hfill creates. The date then migrates to the
    # end of the text stream, detached from its employer, and a parser that
    # pairs them positionally records the wrong dates or none at all. This is
    # the single most common way a good-looking resume parses badly.
    if data:
        raw_text = _raw_extract(doc.name)
        if raw_text:
            detached = []
            for r in data.get("experience", []):
                comp = r["company"].split(",")[0]
                # A company can also appear in the summary, so measure the
                # closest company/date occurrence pair, not the first ones.
                cis = [m.start() for m in re.finditer(re.escape(comp), raw_text)]
                dis = [m.start() for m in re.finditer(re.escape(r["dates"]), raw_text)]
                if cis and dis and min(abs(d - c) for c in cis for d in dis) > 400:
                    detached.append(comp)
            results.append(_check(
                "dates_stay_with_employer", not detached,
                "employer and dates stay adjacent under raw extraction"
                if not detached else
                f"raw extraction detaches dates from {detached}; set "
                '"date_style": "inline" if this application is ATS-critical',
                hard=False))

    # Column scrambling: two blocks that share vertical space but sit in
    # different horizontal halves indicate a multi-column layout, which linear
    # extractors interleave into nonsense.
    # Detect by disjoint horizontal spans rather than a page-midpoint split,
    # because sidebar layouts are commonly 30/70 and would sail past a midpoint
    # test. Both blocks must be multi-line and share real vertical extent, which
    # is what separates a true column from a flush-right date sitting alone on
    # one line.
    scrambled = []
    for pno, page in enumerate(doc):
        blocks = [b for b in page.get_text("blocks") if b[4].strip()]
        for i, a in enumerate(blocks):
            for b in blocks[i + 1:]:
                v_overlap = min(a[3], b[3]) - max(a[1], b[1])
                h_gap = max(a[0], b[0]) - min(a[2], b[2])
                both_tall = (a[3] - a[1]) > 14 and (b[3] - b[1]) > 14
                if v_overlap > 12 and h_gap > 8 and both_tall:
                    scrambled.append(pno + 1)
    results.append(_check("single_column_reading_order", not scrambled,
                          "linear reading order confirmed" if not scrambled
                          else f"side-by-side text blocks on page(s) {sorted(set(scrambled))}"))

    if data:
        years = []
        for r in data.get("experience", []):
            m = YEAR_RE.search(r["dates"])
            if m:
                years.append(int(m.group()))
        ordered = years == sorted(years, reverse=True)
        results.append(_check("reverse_chronological", ordered,
                              f"start years {years}" if ordered
                              else f"experience not newest-first: {years}"))
    return results


def page_fill(doc) -> float:
    """How much of the last page's text area is used, 0..1.

    The text area is inferred rather than read from the source: the top margin
    is where the first text on page 1 starts, and margins are assumed
    symmetric, which holds for every template this skill ships and for most
    resumes in the wild. Anything sitting inside the bottom margin (a running
    footer with the name and page number) is excluded, otherwise every page
    would measure as full.
    """
    first_blocks = [b for b in doc[0].get_text("blocks") if b[4].strip()]
    if not first_blocks:
        return 0.0
    top = min(b[1] for b in first_blocks)
    last = doc[doc.page_count - 1]
    bottom_limit = last.rect.height - top
    usable = bottom_limit - top
    body = [b for b in last.get_text("blocks")
            if b[4].strip() and b[1] < bottom_limit - 2]
    if not body or usable <= 0:
        return 0.0
    return max(0.0, min(1.0, (max(b[3] for b in body) - top) / usable))


def _date_line_edges(doc, date_strings):
    """Right edge (x1) of every line that ends with one of the entry dates.

    Lines are rebuilt from PyMuPDF words (block, line numbers) so a date like
    'Jan 2024 - Present' is matched whole, rather than counting every
    year-shaped token on the page, most of which are not dates at all
    (certification years, a '2M+' metric, a paper's year).
    """
    edges = []
    wanted = [d.strip() for d in date_strings if d and d.strip()]
    for page in doc:
        lines = {}
        for w in page.get_text("words"):
            lines.setdefault((w[5], w[6]), []).append(w)
        for ws in lines.values():
            ws.sort(key=lambda w: w[0])
            text_ = " ".join(w[4] for w in ws)
            if any(text_.endswith(d) for d in wanted):
                edges.append(ws[-1][2])
    return edges


def check_layout(doc, target_pages, date_style="inline", min_fill=0.85, data=None):
    results = []
    results.append(_check("page_count", doc.page_count == target_pages,
                          f"{doc.page_count} page(s), target {target_pages}"))

    # A resume that stops two-thirds of the way down its last page reads as
    # thin, and the master profile almost always had more to give. This is a
    # hard check so the build loop treats "add content" as a real failure
    # rather than a suggestion. Lower min_fill in the payload only when the
    # profile is genuinely exhausted.
    fill = page_fill(doc)
    results.append(_check(
        "page_fill", fill >= min_fill,
        f"last page is {fill * 100:.0f}% filled (minimum {min_fill * 100:.0f}%)"
        if fill >= min_fill else
        f"last page is only {fill * 100:.0f}% filled (minimum {min_fill * 100:.0f}%); "
        "pull more bullets, projects, publications, or certifications from the "
        "master profile, or lower min_fill if it is genuinely exhausted"))

    page = doc[0]
    # Infer the text block's right edge from the body, then confirm date tokens
    # land on it. A drifting date means the \hfill collapsed.
    all_right = [w[2] for w in page.get_text("words")]
    if not all_right:
        return results + [_check("dates_right_aligned", False, "no words on page 1")]
    right_edge = max(all_right)

    date_rights = []
    if data:
        entries = data.get("experience", []) + data.get("education", [])
        date_rights = _date_line_edges(doc, [e.get("dates", "") for e in entries])
    if not date_rights:
        for pno, p in enumerate(doc):
            for w in p.get_text("words"):
                if DATE_TOKEN_RE.search(w[4]):
                    date_rights.append(w[2])
    if date_style == "inline":
        # Inline mode deliberately trades flush-right dates for guaranteed
        # employer/date adjacency, so alignment is not a defect here.
        results.append(_check("dates_right_aligned", True,
                              "skipped: date_style is 'inline' by choice"))
    elif date_rights:
        aligned = [r for r in date_rights if abs(r - right_edge) < 2.0]
        ratio = len(aligned) / len(date_rights)
        results.append(_check(
            "dates_right_aligned", ratio >= (0.9 if data else 0.5),
            f"{len(aligned)}/{len(date_rights)} entry dates end at the right margin "
            f"(x={right_edge:.1f})"))
    else:
        results.append(_check("dates_right_aligned", False, "no date tokens detected"))

    # Overfull boxes push text past the margin; catch it in points.
    over = []
    for pno, p in enumerate(doc):
        limit = p.rect.width - 18
        for w in p.get_text("words"):
            if w[2] > limit:
                over.append((pno + 1, w[4]))
    results.append(_check("no_margin_overflow", not over,
                          "all text inside margins" if not over
                          else f"{len(over)} token(s) past the margin, e.g. {over[:3]}"))

    # A section heading as the last thing on a page, or an employer name with
    # its bullets on the next page, is the most visible defect a two-page
    # resume can have. The template guards against it with \Needspace; this
    # confirms the guard held.
    orphans = []
    for pno in range(doc.page_count - 1):
        last_line = _last_body_line(doc[pno])
        if last_line is None:
            continue
        text_, bold, size = last_line
        stripped = text_.strip()
        if not stripped or stripped.startswith(("•", "-", "*")):
            continue  # a bullet that wraps onto the next page is fine
        is_heading = stripped.isupper() and len(stripped) < 40
        is_entry_header = bold and len(stripped) < 90 and not stripped.endswith(".")
        if is_heading or is_entry_header:
            orphans.append((pno + 1, stripped[:40]))
    results.append(_check("no_orphan_headers", not orphans,
                          "no heading or entry header stranded at a page foot"
                          if not orphans else f"stranded at page foot: {orphans}",
                          hard=False))
    return results


def _last_body_line(page):
    """(text, starts_bold, font_size) of the lowest line above the footer zone."""
    best = None
    footer_zone = page.rect.height - 40
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = [s for s in line.get("spans", []) if s["text"].strip()]
            if not spans or line["bbox"][1] > footer_zone:
                continue
            if best is None or line["bbox"][3] > best[0]:
                text_ = "".join(s["text"] for s in spans)
                bold = bool(spans[0]["flags"] & 16) or "bold" in spans[0]["font"].lower()
                best = (line["bbox"][3], text_, bold, spans[0]["size"])
    return None if best is None else best[1:]


def check_keywords(text, jd_path, company=None):
    """Report job-description terms absent from the resume.

    The goal is a short list worth acting on. Generic English and the company's
    own name are not skills, and surfacing them trains you to ignore the whole
    list. So a term has to look like it carries technical signal: repeated in
    the posting, or capitalized/punctuated the way tool names are.

    Advisory only. A missing keyword is a prompt to surface real experience that
    uses that term, never a licence to insert a skill the candidate lacks.
    """
    jd = Path(jd_path).read_text(errors="ignore")
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9+#./-]{2,}", jd)

    stop = set("""
    the and for with you our are that this will have from your work team role job
    about who what when they their has been more can all who use used using
    experience years strong excellent ability including etc across able also any
    both each into its may most much new now off out over own same some such than
    then them there these those through under very well were which while would
    should could must need needs want wants like other others per
    senior junior staff principal lead level position posting apply applying
    candidate candidates applicant hiring recruiter company companies business
    organization opportunity opportunities benefits salary compensation equity
    remote hybrid onsite office contract requirements
    required preferred responsibilities qualifications description overview
    summary bonus plus nice good great best help helps helping join
    joining build building builds design designs designing develop developing
    work working works run runs running own owns owning drive drives driving
    support supports partner partners collaborate collaborating ensure ensuring
    deliver delivering maintain maintaining improve improving create creating
    million millions billion thousand daily people person engineer engineers
    engineering software developer development technical technology technologies
    similar production behind another every participate participating track
    tracks record proven demonstrated familiarity knowledge understanding
    rotation critical path years year
    """.split())

    if company:
        stop.update(re.findall(r"[a-z]+", company.lower()))

    freq = {}
    for t in tokens:
        k = t.lower().strip(".")
        if k in stop or len(k) < 3:
            continue
        # Original casing/punctuation is evidence of a proper noun or tool name
        # ("Kubernetes", "Node.js", "C++"), which is what we actually care about.
        looks_technical = (
            t[0].isupper()
            or any(c in t for c in "+#./-")
            or any(ch.isdigit() for ch in t)
        )
        e = freq.setdefault(k, {"n": 0, "tech": False, "display": t.strip(".,;:")})
        e["n"] += 1
        e["tech"] = e["tech"] or looks_technical

    # Keep terms either emphasized by repetition or shaped like a tool name.
    candidates = [k for k, e in freq.items() if e["n"] >= 2 or e["tech"]]
    candidates.sort(key=lambda k: (-freq[k]["n"], k))
    candidates = candidates[:40]

    low = text.lower()
    missing = [freq[k]["display"] for k in candidates if k not in low]
    return _check("jd_keyword_coverage", True,
                  f"{len(candidates) - len(missing)}/{len(candidates)} substantive JD "
                  f"terms appear in the resume. Absent: {missing[:15]}", hard=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--data")
    ap.add_argument("--jd")
    ap.add_argument("--company")
    ap.add_argument("--target-pages", type=int, default=2)
    ap.add_argument("--min-fill", type=float, default=None,
                    help="override the payload's min_fill (0..1)")
    a = ap.parse_args()

    data = json.loads(Path(a.data).read_text()) if a.data else None
    doc, text = extract(Path(a.pdf))
    target = data.get("target_pages", a.target_pages) if data else a.target_pages

    date_style = (data or {}).get("date_style", "inline")
    min_fill = a.min_fill if a.min_fill is not None else (data or {}).get("min_fill", 0.85)
    results = check_ats(doc, text, data) + check_layout(doc, target, date_style, min_fill, data)
    if a.jd:
        results.append(check_keywords(text, a.jd, a.company))

    failures = [r for r in results if r["hard"] and not r["passed"]]
    warnings = [r for r in results if not r["hard"] and not r["passed"]]
    report = {"ok": not failures, "failures": len(failures), "warnings": len(warnings),
              "results": results}
    print(json.dumps(report, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
