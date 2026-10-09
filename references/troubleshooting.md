# Troubleshooting

Each check from `verify.py`, what causes it, and how to fix it. The build's
console output ends with a `next_step` line that points at the first of these
that applies.

## Hard failures

**`page_count`** - The document missed its target. Autofit already tried the
densest typography (9pt, 0.45in margins), so the fix is editorial: cut the
weakest bullet from the oldest role, drop the least relevant project, or
shorten the summary. Do not lower the margin further; it looks cramped and
some printers clip it. If everything must stay, raise `target_pages`.

**`page_fill`** - The last page is under `min_fill` (default 85%) used.
Autofit already tried the loosest typography (11pt, 0.75in margins, 1.16
leading), so the fix is content: add bullets to recent roles at full master-
profile length, a summary, projects, publications, certifications, education
detail, then older-role bullets, in that order. See "Filling the page budget"
in SKILL.md. Only if the profile is genuinely exhausted: set `target_pages: 1`
when fill is under 50%, or lower `min_fill` when it is close, and record why
in the tailoring notes. The report's `render.attempts` lists every setting
tried with its page count and fill, which shows how far off the content is.

**`no_unresolved_placeholders`** - A template variable resolved to a Python
object or `None` and printed into the PDF. Usually a key name that collides
with a dict method (`items`, `keys`, `values`); use subscript access in the
template (`<< g["items"] >>`) instead of dot access. Optional strings are
coerced to `""` in `render._build_context`; a new optional field needs the
same treatment. Always a template bug, never a content bug.

**`text_extractable`** - Under 120 words came out of the PDF. Almost always
bitmap fonts: if the LaTeX run generated `.pk` fonts, glyphs have no text
layer. Ensure `carlito` is installed, or let the template's `\IfFileExists`
guard fall back to Helvetica.

**`section_headers_intact`** - A standard heading is missing or renamed.
Creative headings ("Where I've Worked") are not recognized by section
classifiers. Use Experience, Education, Skills, Projects.

**`email_extractable` / `name_on_first_page` / `employers_extractable`** -
Contact or employer text did not survive extraction. Check that nothing was
rendered as an image and that the name is title case in the payload.

**`single_column_reading_order`** - Two text blocks sit side by side, so linear
extraction interleaves them into nonsense. The bundled template is single-column
by construction; this only fires if the template was modified.

**`reverse_chronological`** - Roles are not newest-first in the payload. Reorder
`experience`. Parsers infer recency from order and some infer employment gaps
from it.

**`no_margin_overflow`** - Text runs past the margin, usually an unbreakable
token (a long URL or `some_very_long_identifier`). Shorten it or add a break
opportunity.

**`dates_right_aligned`** - Only with `"date_style": "right"`. An entry's
date line does not end at the right margin, which means the `\hfill`
collapsed; usually a company or location string so long that the header
wrapped. Shorten it, or switch to `inline`.

## Warnings

**`dates_stay_with_employer`** - Expected with `"date_style": "right"`. Raw-mode
extractors relocate flush-right dates to the end of the text stream. Switch to
`"inline"` if this application goes through a large-company ATS. See the
trade-off section in SKILL.md.

**`no_orphan_headers`** - A section heading or an entry header (company,
institution, project name) is the last thing on a page, with its content on
the next. The template guards against this with `\Needspace`; if it fires,
`needspace.sty` is probably not installed (preflight reports it). Otherwise
add or remove one bullet nearby to move the break.

**`jd_keyword_coverage`** - Advisory. Lists frequent JD terms absent from the
resume. Treat each one as a question: *is there real experience that should be
described using this word?* If yes, rewrite the bullet. If no, leave it out.
Never add a term to satisfy this list.

## Style warnings

From `lint_style()`. None block a build.

- **em/en dash** - Rewrite as plain speech. Two clauses joined by a dash usually
  want to be two sentences or a comma.
- **hedging phrase** ("responsible for", "worked on") - Describes assignment
  rather than accomplishment. State what was built and what changed.
- **filler phrase** ("passionate", "detail-oriented") - Unverifiable. Cut it or
  replace with the evidence that would make someone conclude it.
- **no number in this bullet** - Advisory, and a false positive on genuinely
  qualitative work. Add scale, delta, or duration only if a real one exists.

## Build errors

**`pdflatex failed`** - The report includes the log tail. An unescaped special
character is the usual cause, which means something bypassed `escape_latex`.
Check that new template fields go through `escape_model`.

**Missing `.sty`** - Run `scripts/preflight.py`. On Debian/Ubuntu,
`texlive-latex-extra` covers `titlesec`, `enumitem`, `extsizes`, `needspace`,
and `fancyhdr`; `texlive-fonts-extra` carries `carlito`;
`texlive-plain-generic` carries `ulem`. On TinyTeX, `tlmgr install` each name.

**Slow build** - A cold pdflatex run on this document costs about 0.55s,
almost all of it loading the preamble (hyperref, microtype, Carlito). Three
things keep a full autofit build around 3.5s on four cores: the preamble is
precompiled once per font size into `~/.cache/resume-tailor/fmt` (set
`RESUME_TAILOR_CACHE` to move it, `RESUME_TAILOR_NO_FORMAT_CACHE=1` to disable
it) and reused across builds; the ladder sweep and the leading fine-tune each
run as one parallel batch (`RESUME_TAILOR_JOBS` caps the width); and search
attempts compile with a single pass, with two passes only for the final
render. A build that takes 15s or more means the format cache is off, usually
because `mylatexformat` is not installed (preflight reports it; it ships with
`texlive-latex-extra`), or the machine has one core. The report's
`render.format_cache` says whether the cache was used.

**Word output is a page longer than the PDF** - `--docx` follows the PDF's
font size and margins but Word has no autofit and slightly different Calibri
metrics. The PDF is the verified artifact; treat the `.docx` as a convenience
for portals that refuse PDFs.
