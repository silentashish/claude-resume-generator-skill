"""Render a validated JSON payload into a compiled PDF (and optional DOCX).

Usage:
    python3 render.py resume_data.json --outdir OUT [--kind resume|cover] [--autofit] [--docx]

Why autofit exists: a compile is cheap, so it is cheaper to try every
typographic density and keep the best one than to hand-tune the payload.
Content is never dropped -- only font size, margins, leading, and spacing move.

"Best" has two parts, in order: the document must land on the target page
count, and among the settings that do, the one that leaves the least empty
space on the last page wins. A resume that fits in 1.6 pages at the loosest
setting is not a success; the fill number comes back in the result so the
caller can see that the payload is short of content rather than guess.

Where the time goes, and what is done about it: a cold pdflatex run on this
document is about 0.55s, and roughly 0.5s of that is loading the preamble
(hyperref, microtype, the Carlito font). The body itself is nearly free. So:
  - the preamble is dumped once per font size into a precompiled format
    (mylatexformat) and cached across builds; a compile with it is ~0.35s;
  - every autofit attempt is independent, so the ladder sweep and the
    leading fine-tune each run as one parallel batch across the CPU cores;
  - attempts compile with a single pass (page breaks do not depend on the
    second pass; nothing here cross-references), and only the final render
    gets two passes.
Set RESUME_TAILOR_JOBS to cap the parallelism and RESUME_TAILOR_CACHE to move
the format cache (default ~/.cache/resume-tailor).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
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
ENDOFDUMP_MARKER = r"\endofdump"
# The marker is split on as a whole line so a mention of it inside a comment
# can never truncate the static preamble.
_ENDOFDUMP_LINE = "\n" + ENDOFDUMP_MARKER + "\n"


def _jobs() -> int:
    """Parallel compile slots: RESUME_TAILOR_JOBS, else the CPU count."""
    try:
        n = int(os.environ.get("RESUME_TAILOR_JOBS", "0"))
    except ValueError:
        n = 0
    return n if n > 0 else max(1, os.cpu_count() or 1)


def _env() -> Environment:
    """Jinja environment with LaTeX-safe delimiters.

    LaTeX uses {} and {{ }} constantly, so the Jinja delimiters are moved out
    of the way rather than forcing every template line to be escaped.
    """
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


# --- Precompiled preamble ----------------------------------------------------

class FormatCache:
    """Precompiled LaTeX formats, one per distinct static preamble.

    The static preamble (everything above the \\endofdump marker in the
    template) depends only on the font size, so three formats cover the whole
    ladder. They are keyed by a hash of that text plus the pdflatex version and
    kept under RESUME_TAILOR_CACHE (default ~/.cache/resume-tailor), so the
    first build pays ~0.7s per font size and every later build pays nothing.
    Disabled transparently when mylatexformat is not installed.
    """

    def __init__(self):
        root = os.environ.get("RESUME_TAILOR_CACHE") or str(Path.home() / ".cache" / "resume-tailor")
        self.dir = Path(root).expanduser() / "fmt"
        self.enabled = self._available()
        self._version = None

    @staticmethod
    def _available() -> bool:
        if os.environ.get("RESUME_TAILOR_NO_FORMAT_CACHE"):
            return False
        if not shutil.which("kpsewhich"):
            return False
        r = subprocess.run(["kpsewhich", "mylatexformat.ltx"], capture_output=True, text=True)
        return bool(r.stdout.strip())

    def version(self) -> str:
        if self._version is None:
            r = subprocess.run(["pdflatex", "--version"], capture_output=True, text=True)
            self._version = r.stdout.splitlines()[0] if r.stdout else "unknown"
        return self._version

    def name_for(self, static_preamble: str) -> str:
        key = hashlib.sha256((static_preamble + "\n" + self.version()).encode()).hexdigest()[:16]
        return f"rt-{key}"

    def ensure(self, static_preamble: str) -> str | None:
        """Return the format name for this preamble, building it if needed."""
        if not self.enabled:
            return None
        name = self.name_for(static_preamble)
        fmt = self.dir / f"{name}.fmt"
        if fmt.exists():
            return name
        self.dir.mkdir(parents=True, exist_ok=True)
        build = self.dir / f"build-{name}-{os.getpid()}"
        build.mkdir(exist_ok=True)
        # mylatexformat ties the format to the dumped file's name, so the
        # source is named like the documents that will use it.
        src = build / "resume.tex"
        src.write_text(static_preamble + _ENDOFDUMP_LINE
                       + r"\begin{document}\end{document}" + "\n")
        proc = subprocess.run(
            ["pdflatex", "-ini", "-interaction=nonstopmode", f"-jobname={name}",
             "-output-directory", str(build), "&pdflatex", "mylatexformat.ltx", str(src)],
            capture_output=True, text=True, cwd=str(build),
        )
        built = build / f"{name}.fmt"
        if proc.returncode != 0 or not built.exists():
            shutil.rmtree(build, ignore_errors=True)
            self.enabled = False  # fall back to cold compiles for this run
            return None
        os.replace(built, fmt)  # atomic: concurrent builds of the same key are safe
        shutil.rmtree(build, ignore_errors=True)
        return name

    def env(self) -> dict:
        """Environment for pdflatex so it finds the cached formats."""
        e = dict(os.environ)
        if self.enabled:
            e["TEXFORMATS"] = f"{self.dir}{os.pathsep}" + e.get("TEXFORMATS", "")
        return e


def compile_pdf(tex_path: Path, workdir: Path, passes: int = 2,
                fmt: str | None = None, env: dict | None = None) -> Path:
    """Compile `tex_path` into `workdir`.

    Two passes let \\hfill positions and page totals settle in the final
    render; a single pass is enough during the autofit search because page
    breaks do not depend on the second pass and nothing cross-references.
    """
    cmd = ["pdflatex", "-interaction=nonstopmode", "-halt-on-error",
           "-output-directory", str(workdir)]
    if fmt:
        cmd += ["-fmt", fmt]
    cmd.append(str(tex_path))
    proc = None
    for _ in range(passes):
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    pdf = workdir / (tex_path.stem + ".pdf")
    if proc.returncode != 0 or not pdf.exists():
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
    """Number of pages in a compiled PDF."""
    with pymupdf.open(pdf) as d:
        return d.page_count


def _build_context(raw: dict, kind: str) -> dict:
    """Validate the payload and produce the escaped, linkified template context."""
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
    ctx["endofdump"] = ""
    return ctx


class Compiler:
    """Renders a template context at a given setting and compiles it.

    Owns the format cache lookup: the rendered source is split at the
    \\endofdump marker, the static half is turned into (or found as) a cached
    format, and pdflatex is pointed at it.
    """

    def __init__(self, template, ctx: dict, workdir: Path, kind: str):
        self.template, self.ctx, self.workdir, self.kind = template, ctx, workdir, kind
        self.cache = FormatCache() if kind == "resume" else None
        self._formats: dict = {}

    def prepare(self, settings_list: list) -> None:
        """Build (or find) the format for every font size in `settings_list`.

        Done up front and in parallel across font sizes, so the attempt threads
        never race to build the same format.
        """
        if not (self.cache and self.cache.enabled):
            return
        todo = {}
        for s in settings_list:
            fs = s.get("font_size")
            if fs not in self._formats and fs not in todo:
                tex = self.template.render(**{**self.ctx, **s, "endofdump": ENDOFDUMP_MARKER})
                if _ENDOFDUMP_LINE not in tex:
                    self.cache.enabled = False  # template lost its marker line
                    return
                todo[fs] = tex.split(_ENDOFDUMP_LINE, 1)[0]
        if not todo:
            return
        with ThreadPoolExecutor(max_workers=min(_jobs(), len(todo))) as pool:
            futs = {fs: pool.submit(self.cache.ensure, static) for fs, static in todo.items()}
            for fs, f in futs.items():
                self._formats[fs] = f.result()

    def source(self, settings: dict) -> tuple:
        """(tex source, format name or None) for one setting."""
        if self.cache and self.cache.enabled:
            self.prepare([settings])
        fmt = self._formats.get(settings.get("font_size"))
        marker = ENDOFDUMP_MARKER if fmt else ""
        return self.template.render(**{**self.ctx, **settings, "endofdump": marker}), fmt

    def run(self, settings: dict, subdir: str | None = None, passes: int = 1) -> tuple:
        """Compile one attempt; returns (pdf path, pages, fill)."""
        tex, fmt = self.source(settings)
        wd = self.workdir / subdir if subdir else self.workdir
        wd.mkdir(parents=True, exist_ok=True)
        tex_path = wd / f"{self.kind}.tex"
        tex_path.write_text(tex)
        pdf = compile_pdf(tex_path, wd, passes=passes, fmt=fmt,
                          env=self.cache.env() if self.cache else None)
        pages, fill = measure(pdf, settings["margin"])
        return pdf, pages, fill

    def run_many(self, settings_list: list, prefix: str) -> list:
        """Compile several attempts in parallel; returns [(settings, pages, fill)]."""
        self.prepare(settings_list)
        jobs = min(_jobs(), max(1, len(settings_list)))
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futs = [pool.submit(self.run, s, f"{prefix}{i}") for i, s in enumerate(settings_list)]
            out = []
            for s, f in zip(settings_list, futs):
                _, pages, fill = f.result()
                out.append((s, pages, fill))
        return out


def autofit(comp: Compiler, target: int) -> tuple:
    """Sweep the ladder, then fine-tune leading, keeping the fullest fitting layout.

    Returns (settings, pages, fill, attempts). `attempts` records every try so
    the build report can show why a setting was chosen. Both the sweep and the
    fine-tune are one parallel batch each.
    """
    attempts = []
    best = None  # (key, settings, pages, fill)
    for i, (rung, pages, fill) in enumerate(comp.run_many(FIT_LADDER, "rung")):
        attempts.append({**rung, "pages": pages, "fill": round(fill, 3)})
        if pages <= target:
            key = (pages == target, fill, -i)
            if best is None or key > best[0]:
                best = (key, rung, pages, fill)

    if best is None:
        # Nothing fits even at the densest rung. Return it so the caller sees
        # the overflow; the honest fix is editorial, not typographic.
        densest = FIT_LADDER[-1]
        _, pages, fill = comp.run(densest, "final", passes=2)
        return densest, pages, fill, attempts

    _, chosen, pages, fill = best
    if fill < 0.995:
        # Fine-tune: every candidate leading at once; keep the largest that
        # holds the page count without losing fill.
        steps = int(round(LEADING_MAX_EXTRA / LEADING_STEP))
        cands = [{**chosen, "linespread": round(chosen["linespread"] + LEADING_STEP * k, 3)}
                 for k in range(1, steps + 1)]
        for cand, p2, f2 in comp.run_many(cands, "lead"):
            attempts.append({**cand, "pages": p2, "fill": round(f2, 3), "fine_tune": True})
            if p2 == pages and f2 >= fill:
                chosen, fill = cand, f2

    # Final render with two passes so the .tex/.pdf on disk match the report.
    _, pages, fill = comp.run(chosen, None, passes=2)
    return chosen, pages, fill, attempts


def render(data_path: Path, outdir: Path, kind: str = "resume",
           autofit_enabled: bool = False, make_docx: bool = False) -> dict:
    """Render one payload to <outdir>/<kind>.pdf (+ .tex, page JPEGs, optional .docx).

    Returns pages, fill, the chosen settings, `fits`, and every autofit attempt.
    """
    raw = json.loads(Path(data_path).read_text())
    ctx = _build_context(raw, kind)

    outdir.mkdir(parents=True, exist_ok=True)
    workdir = outdir / ".build"
    workdir.mkdir(exist_ok=True)

    template = _env().get_template(
        "resume.tex.j2" if kind == "resume" else "cover_letter.tex.j2"
    )
    comp = Compiler(template, ctx, workdir, kind)

    if kind == "resume":
        target = int(raw.get("target_pages", 2))
        if autofit_enabled:
            chosen, pages, fill, attempts = autofit(comp, target)
        else:
            chosen = DEFAULT_SETTINGS
            _, pages, fill = comp.run(chosen, None, passes=2)
            attempts = [{**chosen, "pages": pages, "fill": round(fill, 3)}]
    else:
        target = 1
        chosen = {"margin": 1.0}
        _, pages, fill = comp.run(chosen, None, passes=2)
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
              "fits": pages <= target, "attempts": attempts,
              "format_cache": bool(comp.cache and comp.cache.enabled)}

    if make_docx and kind == "resume":
        from render_docx import build_docx
        result["docx"] = str(build_docx(raw, outdir / f"{kind}.docx", chosen))

    return result


def main() -> int:
    """CLI wrapper around render(); prints a JSON result."""
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
