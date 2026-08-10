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
    leaks = [m for m in ("built-in method", "object at 0x", "<bound method",
                         "Undefined", "None") if m in text]
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
        ok = all(part in first_page for part in name.split())
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
                ci, di = raw_text.find(comp), raw_text.find(r["dates"])
                if ci >= 0 and di >= 0 and abs(di - ci) > 400:
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
            found = YEAR_RE.findall(r["dates"])
            m = re.findall(r"(19|20)\d{2}", r["dates"])
            if m:
                years.append(int(re.search(r"(19|20)\d{2}", r["dates"]).group()))
        ordered = years == sorted(years, reverse=True)
        results.append(_check("reverse_chronological", ordered,
                              f"start years {years}" if ordered
                              else f"experience not newest-first: {years}"))
    return results


def check_layout(doc, target_pages, date_style="right"):
    results = []
    results.append(_check("page_count", doc.page_count == target_pages,
                          f"{doc.page_count} page(s), target {target_pages}"))

    page = doc[0]
    # Infer the text block's right edge from the body, then confirm date tokens
    # land on it. A drifting date means the \hfill collapsed.
    all_right = [w[2] for w in page.get_text("words")]
    if not all_right:
        return results + [_check("dates_right_aligned", False, "no words on page 1")]
    right_edge = max(all_right)

    date_rights, strays = [], []
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
            "dates_right_aligned", ratio >= 0.5,
            f"{len(aligned)}/{len(date_rights)} date tokens end at the right margin "
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

    # An orphan page holding a few lines looks careless and wastes a page.
    last = doc[doc.page_count - 1]
    blocks = [b for b in last.get_text("blocks") if b[4].strip()]
    fill = (max(b[3] for b in blocks) / last.rect.height) if blocks else 0
    results.append(_check("no_orphan_page", doc.page_count == 1 or fill > 0.25,
                          f"last page is {fill * 100:.0f}% filled",
                          hard=False))
    return results


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
    a = ap.parse_args()

    data = json.loads(Path(a.data).read_text()) if a.data else None
    doc, text = extract(Path(a.pdf))
    target = data.get("target_pages", a.target_pages) if data else a.target_pages

    date_style = (data or {}).get("date_style", "right")
    results = check_ats(doc, text, data) + check_layout(doc, target, date_style)
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
