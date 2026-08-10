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
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pymupdf  # noqa: E402
from jinja2 import Environment, FileSystemLoader, StrictUndefined  # noqa: E402

from schema import CoverLetterData, ResumeData, escape_model  # noqa: E402

ASSETS = Path(__file__).parent.parent / "assets"

# Progressively denser typography. The renderer walks this list and stops at the
# first setting that fits the target page count.
FIT_LADDER = [
    {"font_size": 11, "margin": 0.75, "section_before": 1.6},
    {"font_size": 11, "margin": 0.6, "section_before": 1.4},
    {"font_size": 10, "margin": 0.6, "section_before": 1.3},
    {"font_size": 10, "margin": 0.5, "section_before": 1.1},
    {"font_size": 10, "margin": 0.45, "section_before": 0.9},
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


def contact_line(contact: dict) -> str:
    """Pipe-separated plain-text contact row.

    Plain text with pipe separators survives every extractor tested. Icons are
    images and extract as nothing; \\href links have been observed to lose their
    display text in some parsers, so URLs are printed literally.
    """
    parts = [contact.get("location"), contact.get("phone"), contact.get("email"),
             contact.get("linkedin"), contact.get("github"), contact.get("website")]
    return " $|$ ".join(p for p in parts if p)


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

    ctx = escape_model(model)
    ctx["contact_line"] = contact_line(ctx["contact"])
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
