# Troubleshooting

Each check from `verify.py`, what causes it, and how to fix it.

## Hard failures

**`page_count`** - The document missed its target. Autofit already tried the
densest typography, so the fix is editorial: cut the weakest bullet from the
oldest role, drop a project, or shorten the summary. Do not lower the margin
below 0.45in - it starts looking cramped and some printers clip it. If the user
insists everything stays, change `target_pages` rather than shrinking further.

**`no_unresolved_placeholders`** - A template variable resolved to a Python
object and printed its repr into the PDF. Usually a key name that collides with
a dict method (`items`, `keys`, `values`); use subscript access in the template
(`<< g["items"] >>`) instead of dot access. Always a template bug, never a
content bug.

**`text_extractable`** - Under 120 words came out of the PDF. Almost always
bitmap fonts: if the LaTeX run generated `.pk` fonts, glyphs have no text layer.
Ensure `lmodern` is installed, or let the template's `\IfFileExists` guard fall
back to the default Type 1 fonts.

**`section_headers_intact`** - A standard heading is missing or renamed.
Creative headings ("Where I've Worked") are not recognized by section
classifiers. Use Experience, Education, Skills, Projects.

**`email_extractable` / `name_on_first_page` / `employers_extractable`** -
Contact or employer text did not survive extraction. Check that nothing was
rendered as an image and that the name is not all caps.

**`single_column_reading_order`** - Two text blocks sit side by side, so linear
extraction interleaves them into nonsense. The bundled template is single-column
by construction; this only fires if the template was modified.

**`reverse_chronological`** - Roles are not newest-first in the payload. Reorder
`experience`. Parsers infer recency from order and some infer employment gaps
from it.

**`no_margin_overflow`** - Text runs past the margin, usually an unbreakable
token (a long URL or `some_very_long_identifier`). Shorten it or add a break
opportunity.

## Warnings

**`dates_stay_with_employer`** - Expected with `"date_style": "right"`. Raw-mode
extractors relocate flush-right dates to the end of the text stream. Switch to
`"inline"` if this application goes through a large-company ATS. See the
trade-off section in SKILL.md.

**`no_orphan_page`** - The final page is under a quarter full, which reads as
careless. Either tighten to the previous page or add substance to justify it.

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
`texlive-latex-extra` covers `titlesec` and `enumitem`; `lmodern` is its own
package.

**Slow first compile** - LaTeX may generate bitmap fonts on the very first run.
Subsequent compiles use the cache and take roughly 0.15s.
