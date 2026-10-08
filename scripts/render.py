"""Render a validated JSON payload into a compiled PDF (and optional DOCX).

Usage:
    python3 render.py resume_data.json --outdir OUT [--kind resume|cover] [--autofit] [--docx]

Why autofit exists: pdflatex compiles this document in about 0.15s, so it is
cheaper to try every typographic density and keep the best one than to
hand-tune the payload. Content is never dropped -- only font size, margins,
leading, and spacing move.

"Best" has two parts, in order: the document must land on the target page
count, and among the settings that do, the one that leaves the least empty
space on the last page wins. A resume that fits in 1.6 pages at the loosest
setting is not a success; the fill number comes back in the result so the
caller can see that the payload is short of content rather than guess.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pymupdf  # noqa: E402
from jinja2 import Environment, FileSystemLoader, StrictUndefined  # noqa: E402

from schema import (CoverLetterData, ResumeData, apply_bold, escape_latex,  # noqa: E402
                    escape_model, escape_url)

ASSETS = Path(__file__).parent.parent / "assets"

# Typographic settings from loosest to densest. Every rung is a complete,
# good-looking design on its own; the walk only decides how much air the
# content gets. Keys (all consumed by resume.tex.j2):
#   font_size       pt, extarticle sizes only (9/10/11)
#   margin          inches, all four sides
#   linespread      leading multiplier
#   item_sep        pt between bullets
#   entry_skip      pt after each role / project / degree
#   section_before  ex above a section heading
# The leading rung is deliberately not airy: 11pt at 0.75in with 1.08 leading
# is the most a two-page resume can stretch before it reads as padded. If the
# content does not fill the target at that setting, the fix is more content.
FIT_LADDER = [
    {"font_size": 11, "margin": 0.75, "linespread": 1.08, "item_sep": 3.0, "entry_skip": 6.0, "section_before": 1.8},
    {"font_size": 11, "margin": 0.70, "linespread": 1.05, "item_sep": 2.5, "entry_skip": 5.0, "section_before": 1.6},
    {"font_size": 11, "margin": 0.65, "linespread": 1.02, "item_sep": 2.0, "entry_skip": 4.0, "section_before": 1.4},
    {"font_size": 11, "margin": 0.60, "linespread": 1.00, "item_sep": 1.5, "entry_skip": 3.5, "section_before": 1.2},
    {"font_size": 10, "margin": 0.70, "linespread": 1.06, "item_sep": 2.5, "entry_skip": 5.0, "section_before": 1.5},
    {"font_size": 10, "margin": 0.65, "linespread": 1.03, "item_sep": 2.0, "entry_skip": 4.0, "section_before": 1.3},
    {"font_size": 10, "margin": 0.60, "linespread": 1.00, "item_sep": 1.5, "entry_skip": 3.5, "section_before": 1.2},
    {"font_size": 10, "margin": 0.55, "linespread": 1.00, "item_sep": 1.0, "entry_skip": 3.0, "section_before": 1.0},
    {"font_size": 10, "margin": 0.50, "linespread": 0.98, "item_sep": 1.0, "entry_skip": 2.5, "section_before": 0.9},
    {"font_size": 9, "margin": 0.60, "linespread": 1.03, "item_sep": 1.5, "entry_skip": 3.5, "section_before": 1.1},
    {"font_size": 9, "margin": 0.55, "linespread": 1.00, "item_sep": 1.0, "entry_skip": 3.0, "section_before": 1.0},
    {"font_size": 9, "margin": 0.50, "linespread": 1.00, "item_sep": 1.0, "entry_skip": 2.5, "section_before": 0.9},
    {"font_size": 9, "margin": 0.45, "linespread": 0.98, "item_sep": 0.5, "entry_skip": 2.0, "section_before": 0.8},
]
# Used when autofit is off: the reference design's density.
DEFAULT_SETTINGS = FIT_LADDER[7]

# After the best rung is found, leading is nudged up in these steps while the
# page count still holds, so the last page ends as close to the margin as the
# content allows. Capped so the result never looks double-spaced.
LEADING_STEP = 0.01
LEADING_MAX_EXTRA = 0.08

POINTS_PER_INCH = 72.0


def _env() -> Environment:
    # LaTeX uses {} and {{ }} constantly, so the Jinja delimiters are moved out
    # of the way rather than forcing every template line to be escaped.
    return Environment(
        loader=FileSystemLoader(str(ASSETS)),
        block_start_string="<%", block_end_string="%>",
        variable_start_string="<<", variable_end_string=">>",
        comment_start_string="<#", comment_end_string="#>",
        trim_blocks=True, lstrip_blocks=True, undefined=StrictUndefined,
    )


def _href(url: str, display: str) -> str:
    """A breakable underlined hyperlink whose display text is readable on paper.

    The display text is always the human-readable address or label, so a parser
    that strips link annotations still reads the URL as plain text. \\uline
    (ulem) rather than \\underline so long links can wrap.
    """
    return rf"\href{{{escape_url(url)}}}{{\uline{{{display}}}}}"


def short_url(url: str) -> str:
    """github.com/user/repo from https://github.com/user/repo/ -- display form."""
    return re.sub(r"^https?://(www\.)?", "", url or "").rstrip("/")


def contact_lines(contact: dict, raw_contact: dict) -> tuple:
    """Two centered header rows matching the approved reference layout.

    Row 1: location | Phone: ... | Email: <mailto link>
    Row 2: LinkedIn: <link> | GitHub: <link> | Portfolio: <link>

    `contact` is the LaTeX-escaped copy (display text), `raw_contact` the
    unescaped original (link targets). Labelled links keep both goals: the
    label is the keyword an ATS greps for, the display text is the address.
    """
    line1 = [contact.get("location"),
             f"Phone: {contact['phone']}" if contact.get("phone") else None]
    if contact.get("email"):
        line1.append("Email: " + _href("mailto:" + raw_contact["email"], contact["email"]))

    line2 = []
    for key, label in (("linkedin", "LinkedIn"), ("github", "GitHub"),
                       ("website", "Portfolio")):
        disp = contact.get(key)
        if not disp:
            continue
        url = raw_contact.get(f"{key}_url")
        line2.append(f"{label}: " + (_href(url, disp) if url else disp))

    sep = r" \textbar{} "
    return sep.join(p for p in line1 if p), sep.join(line2)


_URL_KEY = re.compile(r"(^url$|_url$)")


def _linkify(obj, raw):
    """Post-escape fix-up pass, walking the escaped tree alongside the raw one.

    Two jobs: URL fields get href-escaping instead of LaTeX text escaping
    (escape_latex corrupts underscores in a link target), and every other
    string gets its **bold** markers converted to \\textbf.
    """
    if isinstance(obj, dict):
        return {
            k: (escape_url(raw[k]) if isinstance(v, str) and _URL_KEY.search(k)
                else _linkify(v, raw[k]))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_linkify(v, r) for v, r in zip(obj, raw)]
    if isinstance(obj, str):
        return apply_bold(obj)
    return obj


def compile_pdf(tex_path: Path, workdir: Path) -> Path:
    """Compile twice so \\hfill positions, page totals, and references settle."""
    for _ in range(2):
        proc = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error",
             "-output-directory", str(workdir), str(tex_path)],
            capture_output=True, text=True,
        )
    pdf = workdir / (tex_path.stem + ".pdf")
    if not pdf.exists():
        log = workdir / (tex_path.stem + ".log")
        tail = ""
        if log.exists():
            lines = log.read_text(errors="ignore").splitlines()
            tail = "\n".join(l for l in lines if l.startswith("!") or "Error" in l)[-1500:]
        raise RuntimeError(f"pdflatex failed.\n{tail or proc.stdout[-1500:]}")
    return pdf


def measure(pdf: Path, margin_in: float) -> tuple:
    """(page count, fill of the last page's text area, 0..1).

    Fill is the lowest body text edge on the last page relative to the text
    area between the margins. The running footer lives inside the bottom
    margin and is excluded, otherwise every page would measure as full.
    """
    with pymupdf.open(pdf) as d:
        n = d.page_count
        last = d[n - 1]
        top = margin_in * POINTS_PER_INCH
        bottom_limit = last.rect.height - top
        usable = bottom_limit - top
        body = [b for b in last.get_text("blocks")
                if b[4].strip() and b[1] < bottom_limit - 2]
        if not body or usable <= 0:
            return n, 0.0
        fill = (max(b[3] for b in body) - top) / usable
        return n, max(0.0, min(1.0, fill))


def page_count(pdf: Path) -> int:
    with pymupdf.open(pdf) as d:
        return d.page_count


def _build_context(raw: dict, kind: str) -> dict:
    model = ResumeData(**raw) if kind == "resume" else CoverLetterData(**raw)
    dump = model.model_dump()
    ctx = _linkify(escape_model(model), dump)
    ctx["contact_line1"], ctx["contact_line2"] = contact_lines(
        ctx["contact"], dump["contact"])
    if kind == "resume":
        # Readable display text for project links (github.com/user/repo).
        for esc_p, raw_p in zip(ctx.get("projects", []), dump.get("projects", [])):
            if raw_p.get("url"):
                esc_p["url_display"] = escape_latex(short_url(raw_p["url"]))
        # Optional strings default to "" so the template never prints "None".
        ctx["publications_suffix"] = ctx.get("publications_suffix") or ""
        ctx["summary"] = ctx.get("summary") or ""
    return ctx


def _try(template, ctx: dict, settings: dict, workdir: Path, kind: str) -> tuple:
    ctx = {**ctx, **settings}
    tex = workdir / f"{kind}.tex"
    tex.write_text(template.render(**ctx))
    pdf = compile_pdf(tex, workdir)
    pages, fill = measure(pdf, settings["margin"])
    return pdf, pages, fill


def autofit(template, ctx: dict, workdir: Path, target: int, kind: str) -> tuple:
    """Walk the ladder, then nudge leading, keeping the fullest fitting layout.

    Returns (settings, pages, fill, attempts). `attempts` records every try so
    the build report can show why a setting was chosen.
    """
    attempts = []
    best = None  # (fill, -index, settings, pages)
    for i, rung in enumerate(FIT_LADDER):
        _, pages, fill = _try(template, ctx, rung, workdir, kind)
        attempts.append({**rung, "pages": pages, "fill": round(fill, 3)})
        if pages <= target:
            key = (pages == target, fill, -i)
            if best is None or key > best[0]:
                best = (key, rung, pages, fill)

    if best is None:
        # Nothing fits even at the densest rung. Return it so the caller sees
        # the overflow; the honest fix is editorial, not typographic.
        densest = FIT_LADDER[-1]
        _, pages, fill = _try(template, ctx, densest, workdir, kind)
        return densest, pages, fill, attempts

    _, chosen, pages, fill = best
    # Fine-tune: add leading in small steps while the page count holds. This
    # closes the gap between "fits" and "fills" without changing font or margin.
    extra = LEADING_STEP
    while extra <= LEADING_MAX_EXTRA + 1e-9 and fill < 0.995:
        cand = {**chosen, "linespread": round(chosen["linespread"] + extra, 3)}
        _, p2, f2 = _try(template, ctx, cand, workdir, kind)
        attempts.append({**cand, "pages": p2, "fill": round(f2, 3), "fine_tune": True})
        if p2 != pages or f2 < fill:
            break
        chosen, fill = cand, f2
        extra += LEADING_STEP

    # Re-render the winner so the .tex/.pdf on disk match the reported settings.
    _try(template, ctx, chosen, workdir, kind)
    return chosen, pages, fill, attempts


def render(data_path: Path, outdir: Path, kind: str = "resume",
           autofit_enabled: bool = False, make_docx: bool = False) -> dict:
    raw = json.loads(Path(data_path).read_text())
    ctx = _build_context(raw, kind)

    outdir.mkdir(parents=True, exist_ok=True)
    workdir = outdir / ".build"
    workdir.mkdir(exist_ok=True)

    template = _env().get_template(
        "resume.tex.j2" if kind == "resume" else "cover_letter.tex.j2"
    )

    if kind == "resume":
        target = int(raw.get("target_pages", 2))
        if autofit_enabled:
            chosen, pages, fill, attempts = autofit(template, ctx, workdir, target, kind)
        else:
            chosen = DEFAULT_SETTINGS
            _, pages, fill = _try(template, ctx, chosen, workdir, kind)
            attempts = [{**chosen, "pages": pages, "fill": round(fill, 3)}]
    else:
        target = 1
        chosen = {"margin": 1.0}
        _, pages, fill = _try(template, ctx, chosen, workdir, kind)
        attempts = []

    final_pdf = outdir / f"{kind}.pdf"
    shutil.copy(workdir / f"{kind}.pdf", final_pdf)
    shutil.copy(workdir / f"{kind}.tex", outdir / f"{kind}.tex")

    # Page images for visual review. JPEG at 110 DPI is legible in-chat and small.
    for old in outdir.glob(f"{kind}-page*.jpg"):
        old.unlink()
    subprocess.run(["pdftoppm", "-jpeg", "-r", "110", str(final_pdf),
                    str(outdir / f"{kind}-page")], capture_output=True)

    result = {"pdf": str(final_pdf), "pages": pages, "target_pages": target,
              "fill": round(fill, 3), "settings": chosen,
              "fits": pages <= target, "attempts": attempts}

    if make_docx and kind == "resume":
        from render_docx import build_docx
        result["docx"] = str(build_docx(raw, outdir / f"{kind}.docx", chosen))

    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--kind", choices=["resume", "cover"], default="resume")
    ap.add_argument("--autofit", action="store_true")
    ap.add_argument("--docx", action="store_true")
    a = ap.parse_args()
    try:
        res = render(Path(a.data), Path(a.outdir), a.kind, a.autofit, a.docx)
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, indent=2))
        return 1
    print(json.dumps({"ok": True, **res}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
