"""One-shot build: validate -> render -> verify -> write the output tree.

Usage:
    python3 build.py resume_data.json \
        --role ml-engineer --company stripe --job-id 4821 \
        [--cv-home ~/cv] [--jd job-description.md] [--cover cover_data.json] \
        [--notes tailoring-notes.md] [--docx]

Produces $CV_HOME/<role>/<company>/<job-id>/ containing resume.pdf, resume.tex,
resume_data.json, page JPEGs, job-description.md, tailoring-notes.md,
build-report.json, and optionally resume.docx and cover.pdf.

Run this rather than calling render and verify separately -- it keeps the
payload, the artifact, and the verification report in one directory, so a later
"what exactly did I send Stripe?" question has a single answer.

Exit code is 0 only when the PDF hits its page target, fills it, and passes
every hard ATS and layout check. The console summary names what to do next
when it does not.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from render import render  # noqa: E402
from schema import DEFAULT_MIN_FILL, lint_style  # noqa: E402

HERE = Path(__file__).parent


def _copy(src, dst) -> None:
    """shutil.copy that tolerates re-building from files already in outdir."""
    if Path(src).resolve() != Path(dst).resolve():
        shutil.copy(src, dst)


def slug(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s.strip().lower())
    return re.sub(r"-+", "-", s).strip("-") or "unknown"


def next_step(res: dict, verify: dict, min_fill: float) -> str:
    """One sentence telling the caller what the build needs, if anything."""
    failed = {r["check"] for r in verify.get("results", []) if r["hard"] and not r["passed"]}
    if not res["fits"]:
        return ("Content overflows the target even at the densest typography: "
                "trim the weakest bullet from the oldest role, or raise target_pages.")
    if "page_fill" in failed:
        short = max(0.0, min_fill - res["fill"])
        fallback = ("set target_pages to 1" if res["fill"] < 0.5 and res["target_pages"] > 1
                    else "lower min_fill and record why in the tailoring notes")
        return (f"Last page is {res['fill'] * 100:.0f}% full, about {short * 100:.0f}% short: "
                "add real content from the master profile (more bullets on recent "
                "roles, a project, a publication, certifications, a summary) and rebuild. "
                f"Only if the profile is genuinely exhausted, {fallback}.")
    if failed:
        return f"Fix hard failures {sorted(failed)}; see references/troubleshooting.md."
    return "Build is clean. Open the page JPEGs and review them before delivering."


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("--role", required=True)
    ap.add_argument("--company", required=True)
    ap.add_argument("--job-id", required=True)
    ap.add_argument("--cv-home", default=os.environ.get("CV_HOME", str(Path.home() / "cv")))
    ap.add_argument("--jd", help="path to the saved job description markdown")
    ap.add_argument("--cover", help="path to cover letter JSON")
    ap.add_argument("--notes", help="path to tailoring notes markdown (decisions, bridges, gaps)")
    ap.add_argument("--docx", action="store_true")
    ap.add_argument("--no-autofit", action="store_true")
    a = ap.parse_args()

    outdir = Path(a.cv_home).expanduser() / slug(a.role) / slug(a.company) / slug(a.job_id)
    outdir.mkdir(parents=True, exist_ok=True)

    raw = json.loads(Path(a.data).read_text())
    min_fill = float(raw.get("min_fill", DEFAULT_MIN_FILL))

    try:
        res = render(Path(a.data), outdir, "resume",
                     autofit_enabled=not a.no_autofit, make_docx=a.docx)
    except Exception as e:
        print(json.dumps({"ok": False, "stage": "render", "error": str(e)}, indent=2))
        return 1

    _copy(a.data, outdir / "resume_data.json")
    if a.jd:
        _copy(a.jd, outdir / "job-description.md")
    if a.notes:
        _copy(a.notes, outdir / "tailoring-notes.md")

    cmd = [sys.executable, str(HERE / "verify.py"), str(outdir / "resume.pdf"),
           "--data", str(outdir / "resume_data.json")]
    if a.jd:
        cmd += ["--jd", str(outdir / "job-description.md"), "--company", a.company]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    verify = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {
        "ok": False, "error": proc.stderr[-800:]
    }

    cover = None
    if a.cover:
        try:
            cover = render(Path(a.cover), outdir, "cover")
            _copy(a.cover, outdir / "cover_data.json")
        except Exception as e:
            cover = {"ok": False, "error": str(e)}

    ok = bool(verify.get("ok")) and res["fits"] and (cover is None or cover.get("ok", True))
    report = {
        "ok": ok,
        "outdir": str(outdir),
        "next_step": next_step(res, verify, min_fill),
        "render": res,
        "style_warnings": lint_style(raw),
        "verify": verify,
        "cover": cover,
        "pages_rendered": sorted(p.name for p in outdir.glob("*-page*.jpg")),
    }
    (outdir / "build-report.json").write_text(json.dumps(report, indent=2))

    # Drop the LaTeX scratch dir once the build succeeds. On failure it stays,
    # because the .log inside it is the only way to diagnose a compile error.
    if report["ok"]:
        shutil.rmtree(outdir / ".build", ignore_errors=True)

    # Console summary stays short; the full report is on disk.
    print(json.dumps({
        "ok": report["ok"],
        "outdir": report["outdir"],
        "pages": res["pages"],
        "target_pages": res["target_pages"],
        "fill": res["fill"],
        "min_fill": min_fill,
        "settings": res["settings"],
        "failed_checks": [r["check"] for r in verify.get("results", [])
                          if r["hard"] and not r["passed"]],
        "warnings": [r["check"] for r in verify.get("results", [])
                     if not r["hard"] and not r["passed"]],
        "style_warnings": report["style_warnings"][:8],
        "cover": None if cover is None else {"ok": cover.get("ok", True),
                                             "pages": cover.get("pages"),
                                             "error": cover.get("error")},
        "pages_rendered": report["pages_rendered"],
        "next_step": report["next_step"],
    }, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
