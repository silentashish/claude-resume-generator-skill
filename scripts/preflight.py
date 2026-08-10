"""Check every dependency up front and report all problems at once.

Failing early with a complete list beats discovering a missing package after
the model has already written a full payload.
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
import sys

BINARIES = {
    "pdflatex": "LaTeX compiler (TeX Live / MiKTeX)",
    "pdftoppm": "poppler-utils, for page JPEGs",
    "pdftotext": "poppler-utils, for raw-mode extraction checks",
}
MODULES = {
    "pydantic": "schema validation",
    "jinja2": "template rendering",
    "pymupdf": "PDF text and coordinate extraction",
}
OPTIONAL = {"docx": "python-docx, only needed for --docx output"}

# carlito (with its fontaxes dependency) is the Calibri-metric font the design
# is built around; extsizes provides extarticle for real 9pt; ulem provides
# breakable underlined links; microtype disables ATS-hostile ligatures.
LATEX_PACKAGES = ["geometry", "enumitem", "titlesec", "hyperref", "xcolor",
                  "ulem", "carlito", "fontaxes", "microtype"]
LATEX_CLASSES = ["extarticle"]


def main() -> int:
    problems, notes = [], []

    for exe, why in BINARIES.items():
        if shutil.which(exe):
            notes.append(f"ok    {exe}")
        else:
            problems.append(f"MISSING {exe} - {why}")

    for mod, why in MODULES.items():
        try:
            importlib.import_module(mod)
            notes.append(f"ok    {mod}")
        except ImportError:
            problems.append(f"MISSING python module {mod} - {why} "
                            f"(pip install {mod})")

    for mod, why in OPTIONAL.items():
        try:
            importlib.import_module(mod)
            notes.append(f"ok    {mod} (optional)")
        except ImportError:
            notes.append(f"--    {mod} not installed - {why}")

    if shutil.which("kpsewhich"):
        for name, ext in ([(p, "sty") for p in LATEX_PACKAGES]
                          + [(c, "cls") for c in LATEX_CLASSES]):
            r = subprocess.run(["kpsewhich", f"{name}.{ext}"],
                               capture_output=True, text=True)
            if r.stdout.strip():
                notes.append(f"ok    LaTeX package {name}")
            else:
                problems.append(f"MISSING LaTeX package {name}.{ext} "
                                f"(tlmgr install {'extsizes' if name == 'extarticle' else name})")

    print("\n".join(notes))
    if problems:
        print("\n" + "\n".join(problems))
        print("\nInstall the above, then re-run preflight.")
        return 1
    print("\nAll dependencies present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
