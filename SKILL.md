---
name: resume-tailor
description: Generate an ATS-verified, job-description-tailored resume and matching cover letter as compiled PDFs, organized into a per-application folder. Use this whenever the user is applying to a specific job and wants a resume or cover letter tailored to it - including when they paste a job description or a job posting URL, say things like "tailor my CV for this role", "make a resume for this Stripe posting", "write a cover letter for this", ask to angle their resume toward a particular stack or seniority, or ask whether a resume will pass ATS screening. Also use it to re-verify or re-cut an existing resume that is overflowing to an extra page, failing ATS parsing, or losing its date alignment. Do not use it for general resume-writing advice with no target job, or for interview preparation.
---

# Resume Tailor

Turn a job description plus a master profile into a compiled, verified resume
and cover letter, filed at `$CV_HOME/<role>/<company>/<job-id>/`.

The core idea: **an LLM writes the content, but code decides whether the
artifact is acceptable.** Page count, page fill, alignment, and text
extraction are measured on the compiled PDF, never estimated. Everything the
model produces passes through a schema, a build, and a verifier, and the run
is not finished until the verifier says so.

## Three rules that outrank everything else

**1. Run to completion without asking.** This skill is autonomous end to
end. Do not pause for approval, do not ask which reframing the user prefers,
do not ask which date style to use, do not ask whether to include a project.
Make the call, record it in `tailoring-notes.md`, and keep going. The user
reviews the finished PDF and the notes, not a plan. The only reason to stop
early is a missing prerequisite (no master profile, no job description, or a
failed preflight), and even then say exactly what is missing in one message.

**2. Never fabricate.** The user has to defend every line in an interview.
When the posting asks for something the master profile does not contain,
describe genuinely adjacent experience in the posting's vocabulary (a
PHP-to-Node migration is real evidence for "scalable backend architecture"),
or leave the gap open and note it. Every number traces to the profile. When
unsure whether a reframing is honest, choose the more conservative wording
and note the judgement call, rather than asking.

**3. Fill the target pages.** Two pages means two full pages. The master
profile is deliberately exhaustive, and a two-page resume that stops two
thirds of the way down page 2 reads as thin. The build fails (`page_fill`)
when the last page is under 85% used, and the fix is always more real
content from the profile, never padding. See "Filling the page budget".

## Prerequisites

Check once and name anything missing rather than failing mid-run:

```bash
python3 scripts/preflight.py
```

Needs `pdflatex`, `pdftoppm`, `pdftotext`, Python `pydantic`, `jinja2`,
`pymupdf` (`python-docx` only for optional Word output), and the LaTeX
packages `carlito`, `extsizes`, `ulem`, `fontaxes`, `microtype`
(`needspace` and `fancyhdr` are optional and improve the layout). Preflight
names any that are missing. It also needs the master profile markdown file,
the single source of truth for everything the user has done. See
`assets/master_profile.example.md`. `$CV_HOME` sets the output root and
defaults to `~/cv`; look there for `master-profile.md` first.

## Workflow

### 1. Get the job description

Fetch the URL or take the pasted text. Save it verbatim as
`job-description.md`; postings get taken down. Extract mandatory skills,
preferred skills, core responsibilities, and seniority signals, keeping the
posting's own wording. `references/workflow.md` covers this in depth.

### 2. Gap analysis

Read the whole master profile. Sort the posting's requirements into **direct
hits** (profile evidence in the posting's own terms), **bridgeable** (real
experience that maps if reframed; decide the reframing now), and **genuine
gaps** (nothing honest to say). A quick look at the company's engineering
blog or public stack gives vocabulary for framing, never claims.

### 3. Decide and record

Write `tailoring-notes.md` before the payload. It holds: the direct hits,
each bridge with the exact wording used, each gap left open, the date style
chosen, which bullets were cut or trimmed and why, and any judgement call on
honesty. This file replaces the approval round-trip: the user reads it next
to the PDF. Then proceed; do not wait.

### 4. Write the payload

Write `resume_data.json` matching `scripts/schema.py`. Bullets are capped at
8 per role and 400 characters, large enough to carry a master-profile bullet
intact. **Carry bullets over near-verbatim.** Rewriting a rich 300-character
bullet down to a 110-character stub loses the metrics, the technology names,
and the ATS keywords at once; that over-summarization is the most common way
a run of this skill has gone wrong. Select and reorder for the role; do not
compress what you keep.

Pull from the whole profile, not just jobs: `projects` (with `tech`),
`certifications`, `publications`, and a `summary` are separate schema fields
and each is evidence the paid roles may not show. Preserve `**bold**` markers
on the impact phrase of each bullet. Carry links: each role's
`project_name`/`project_url`, each project's `url`, each certification's
`url`, each publication's `url` + `link_label` + one-sentence `note`. Contact
links use paired fields (`linkedin` display text, `linkedin_url` target).
Education entries take a `location` and a `detail` (thesis, GPA, honours).
The name stays title case in the data; the template renders it in caps.

Bullets lead with the outcome and name the technology, in plain speech. No
em dashes, no "responsible for", no adjective doing a number's job.
`lint_style()` flags these in the build report.

Set `"date_style": "inline"` (the default) unless a human will read the PDF
before any ATS does; see the trade-off below.

### 5. Build

```bash
python3 scripts/build.py resume_data.json \
  --role ml-engineer --company stripe --job-id 4821 \
  --jd job-description.md --notes tailoring-notes.md \
  [--cover cover_data.json] [--docx]
```

This validates, escapes LaTeX, compiles, extracts text, checks layout, and
writes everything to `$CV_HOME/<role>/<company>/<job-id>/`: `resume.pdf`,
`resume.tex`, `resume_data.json`, page JPEGs, `job-description.md`,
`tailoring-notes.md`, and `build-report.json`. Exit code is non-zero when any
hard check fails, and the console `next_step` says what to do.

Autofit is on by default. A compile takes about 0.15s, so the renderer tries
every density on its ladder (11pt to 9pt, 0.75in to 0.45in margins, leading,
bullet and entry spacing), keeps the setting that lands on the target page
count with the fullest last page, then nudges leading up until the last
page ends as close to the margin as the content allows. It never drops
content. The chosen settings and the `fill` fraction come back in the report.

### 6. Filling the page budget

If the build fails `page_fill`, the last page is under 85% used. Add real
content and rebuild, in this order of preference:

1. More bullets on the most recent roles, taken from the master profile at
   full length (up to 8 per role).
2. A `summary` of three or four sentences if there is none.
3. Projects, publications, and certifications not yet included, most
   relevant first; each carries keywords the paid roles may not.
4. Education `detail`: thesis title, relevant coursework, honours.
5. Bullets on older roles.

Only when the master profile is genuinely exhausted, and say so in the
notes: set `target_pages` to 1 if the content fills under half of page 2,
or lower `min_fill` in the payload if it is close. Never add filler, never
widen a bullet with adjectives, never invent a project to fill space.

Conversely, if the build reports more pages than the target even at the
densest setting, cut the weakest bullet from the oldest role first.

### 7. Read the report, then look at the pages

Loop on build until `ok` is true: fix every hard failure
(`references/troubleshooting.md` maps each check to its fix) and rebuild.
Then **open the page JPEGs and look at them.** The automated checks catch
structural problems, not every problem; a template bug once printed
`built-in method items of dict object at 0x7f92...` into the Skills section
and passed every text check. Check for: a stranded header at a page foot,
a wrapped line that looks wrong, a link that extracted as the wrong text,
visible rivers in a justified paragraph. Fix and rebuild. A run is done only
when the build is clean and the pages have been looked at.

### 8. Cover letter

Same track, driven by `cover_data.json`, built in the same `build.py` call
via `--cover`. Research the company's engineering writing for what they
actually care about, then write three or four paragraphs: why this role, one
concrete piece of evidence that maps to their problem, and a close.
Technical and specific; cut anything that would survive a find-replace of
the company name. The letter shares the resume's header and typography so
the two read as one application.

### 9. Deliver

One message: where the files are, the page count and fill, the date style
chosen, the bridges used, the gaps left open, and any warning from the
report worth the user's attention. Point them at `tailoring-notes.md` for
the full record.

## Design

Carlito (metric clone of Calibri) with uppercase name, two centred contact
lines, ruled uppercase section headings, and the same two-line entry header
in every section: bold primary line (company, institution, project) with the
location after a bar, italic secondary line (title, degree, tech stack), bold
dates. Bullets are a small round mark with a hanging indent and even
spacing. Skills are label/value rows without bullets. Hyperlinks are blue and
underlined with the readable address as display text. Body text is justified
with hyphenation discouraged. Page 2 carries the name and page number in a
small grey footer; page 1 does not. An entry header is never left alone at
the foot of a page. Every spacing value comes from one autofit rung so the
rhythm is consistent top to bottom. Do not swap fonts, add colour beyond
link blue, or introduce columns, icons, or images; those break extraction.

## The date alignment trade-off

Flush-right dates via `\hfill` look traditional. But raw-mode PDF text
extractors break lines on wide whitespace gaps, so a flush-right date can
migrate to the end of the extracted text stream, detached from its employer,
and a parser pairing them positionally records the wrong dates. `verify.py`
detects this as `dates_stay_with_employer`.

- `"date_style": "inline"` (default): bold dates after the italic title
  (`Title | Dates`). Employer and date cannot be separated under extraction.
- `"date_style": "right"`: flush-right dates; the adjacency warning is
  expected. Choose it only when a human reads the PDF before any ATS.

Record the choice in the notes; do not ask.

## Bundled files

- `scripts/schema.py` - Pydantic models, LaTeX escaping, style linting
- `scripts/render.py` - JSON to LaTeX to PDF, fill-maximizing autofit, page JPEGs
- `scripts/render_docx.py` - optional Word output from the same payload and settings
- `scripts/verify.py` - ATS extraction, page fill, and layout checks (runs on any PDF)
- `scripts/build.py` - the orchestrator; this is the normal entry point
- `scripts/preflight.py` - dependency check
- `assets/resume.tex.j2`, `assets/cover_letter.tex.j2` - templates
- `assets/master_profile.example.md` - master profile shape
- `references/workflow.md` - JD extraction, gap analysis, recording decisions
- `references/troubleshooting.md` - each failed check, its cause, its fix

`verify.py` works on any PDF, including one this skill did not produce, which
makes it useful for auditing a resume the user already has.
