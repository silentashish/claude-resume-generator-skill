"""Render a validated JSON payload into a compiled PDF (and optional DOCX).

Usage:
    python3 render.py resume_data.json --outdir OUT [--kind resume|cover] [--autofit] [--docx]

Why autofit exists: pdflatex compiles this document in about 0.15s, so it is
cheaper to try several typographic densities and keep the one that lands on the
target page count than to hand-tune the payload. Content is never dropped --
only font size, margins, and section spacing move.
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

# Progressively denser typography. The renderer walks this list and stops at the
# first setting that fits the target page count. The template uses extarticle,
# so 9pt is a real font size rather than a scaled hack. The approved reference
# layout sits around 10pt Carlito with 0.5in margins.
FIT_LADDER = [
    {"font_size": 11, "margin": 0.65, "section_before": 1.3},
    {"font_size": 10, "margin": 0.6, "section_before": 1.2},
    {"font_size": 10, "margin": 0.5, "section_before": 1.0},
    {"font_size": 9, "margin": 0.5, "section_before": 0.9},
    {"font_size": 9, "margin": 0.45, "section_before": 0.8},
]


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

    sep = " $|$ "
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
    """Compile twice so \\hfill positions and any references settle."""
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


def page_count(pdf: Path) -> int:
    with pymupdf.open(pdf) as d:
        return d.page_count


def render(data_path: Path, outdir: Path, kind: str = "resume",
           autofit: bool = False, make_docx: bool = False) -> dict:
    raw = json.loads(Path(data_path).read_text())
    model = ResumeData(**raw) if kind == "resume" else CoverLetterData(**raw)

    outdir.mkdir(parents=True, exist_ok=True)
    workdir = outdir / ".build"
    workdir.mkdir(exist_ok=True)

    dump = model.model_dump()
    ctx = _linkify(escape_model(model), dump)
    ctx["contact_line1"], ctx["contact_line2"] = contact_lines(
        ctx["contact"], dump["contact"])
    # Readable display text for project links (github.com/user/repo).
    for esc_p, raw_p in zip(ctx.get("projects", []), dump.get("projects", [])):
        if raw_p.get("url"):
            esc_p["url_display"] = escape_latex(short_url(raw_p["url"]))
    ctx.setdefault("date_style", raw.get("date_style", "right"))

    template = _env().get_template(
        "resume.tex.j2" if kind == "resume" else "cover_letter.tex.j2"
    )

    target = raw.get("target_pages", 2) if kind == "resume" else 1
    settings_list = FIT_LADDER if (autofit and kind == "resume") else [FIT_LADDER[2]]

    chosen, pdf, pages = None, None, None
    for settings in settings_list:
        ctx.update(settings)
        tex = workdir / f"{kind}.tex"
        tex.write_text(template.render(**ctx))
        pdf = compile_pdf(tex, workdir)
        pages = page_count(pdf)
        chosen = settings
        if pages <= target:
            break

    final_pdf = outdir / f"{kind}.pdf"
    shutil.copy(pdf, final_pdf)
    shutil.copy(workdir / f"{kind}.tex", outdir / f"{kind}.tex")

    # Page images for visual review. JPEG at 110 DPI is legible in-chat and small.
    subprocess.run(["pdftoppm", "-jpeg", "-r", "110", str(final_pdf),
                    str(outdir / f"{kind}-page")], capture_output=True)

    result = {"pdf": str(final_pdf), "pages": pages, "target_pages": target,
              "settings": chosen, "fits": pages <= target}

    if make_docx and kind == "resume":
        from render_docx import build_docx
        result["docx"] = str(build_docx(raw, outdir / f"{kind}.docx"))

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
