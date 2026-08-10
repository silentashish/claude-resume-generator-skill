---
name: resume-tailor
description: Generate an ATS-verified, job-description-tailored resume and matching cover letter as compiled PDFs, organized into a per-application folder. Use this whenever the user is applying to a specific job and wants a resume or cover letter tailored to it - including when they paste a job description or a job posting URL, say things like "tailor my CV for this role", "make a resume for this Stripe posting", "write a cover letter for this", ask to angle their resume toward a particular stack or seniority, or ask whether a resume will pass ATS screening. Also use it to re-verify or re-cut an existing resume that is overflowing to an extra page, failing ATS parsing, or losing its date alignment. Do not use it for general resume-writing advice with no target job, or for interview preparation.
---

# Resume Tailor

Turn a job description plus a master profile into a compiled, verified resume
and cover letter, filed at `$CV_HOME/<role>/<company>/<job-id>/`.

The core idea: **an LLM writes the content, but code decides whether the
artifact is acceptable.** Page count, alignment, and text extraction are
measured on the compiled PDF, never estimated. Everything the model produces
passes through a schema that makes overflow structurally impossible.

## The honesty constraint

This is the one rule that outranks every other goal here.

The user has to sit in a room and defend every line of this document. A bullet
that overstates gets them caught, and a fabricated skill gets them hired into a
job they cannot do. So when the job description asks for something the master
profile does not contain, **never invent it.** Instead:

- Find genuinely adjacent experience and describe it in the JD's vocabulary.
  A PHP-to-Node migration is real evidence for "scalable backend architecture"
  and can be framed that way. That is translation, not fabrication.
- If there is no adjacent experience, leave the gap open and say so. A missing
  keyword costs one screening filter; an invented one costs the offer.
- Every number must trace to something in the master profile. If the profile
  says "reduced latency", do not promote it to "reduced latency 40%".

When you are unsure whether a reframing is honest, ask the user. They know what
they did.

## Prerequisites

Check these once and tell the user what is missing rather than failing mid-run:

```bash
python3 scripts/preflight.py
```

Needs `pdflatex`, `pdftoppm`, and Python `pydantic`, `jinja2`, `pymupdf`
(`python-docx` only for the optional Word output), plus the LaTeX packages
`carlito`, `extsizes`, `ulem`, `fontaxes`, and `microtype` (one
`tlmgr install` away on TinyTeX; preflight names any that are missing). It
also needs a master profile markdown file - the single source of truth for
everything the user has actually done. See `assets/master_profile.example.md`
for the expected shape. `$CV_HOME` sets the output root and defaults to `~/cv`.

The design is deliberate: Carlito (a metric clone of Calibri, the same face
LibreOffice ships) at high density, uppercase name, blue underlined hyperlinks,
bold inline metrics. It reproduces the user's approved reference resume; do not
swap fonts or drift back toward the default LaTeX serif look.

## Workflow

### 1. Get the job description

Fetch the URL or take the pasted text. Save it verbatim as `job-description.md`
in the output folder - postings get taken down, and six weeks later the user
will want to know what they actually applied to.

Extract and show: mandatory technical skills, preferred skills, core
responsibilities, and seniority signals. Keep the JD's own vocabulary; matching
its wording is most of what keyword screening measures.

### 2. Gap analysis against the master profile

Read the master profile and compare it against the extracted requirements.
Produce three lists: **direct hits** (profile evidence that uses the JD's own
terms), **bridgeable** (real experience that maps if reframed - name the
specific reframing), and **genuine gaps** (nothing honest to say).

If the company has an engineering blog or a public tech stack, a quick look
gives you the vocabulary they use internally, which is often more specific than
the posting. Use it for framing, never as a source of claims about the user.

### 3. Stop and get approval

**Pause here and show the user the bridgeable reframings and the proposed
bullets before generating anything.** This is the step most worth protecting.
The user is the only one who knows whether "led the migration" overstates their
role, and every downstream step is cheap to redo while this one is not.

Present the reframings concretely - "your Houzz PHP-to-Node work becomes
evidence for their 'high-throughput services' requirement, worded as X" - and
wait for an explicit go-ahead. Note the genuine gaps here too, so the decision
to apply anyway is one they make with open eyes.

### 4. Write the payload

Write `resume_data.json` matching `scripts/schema.py`. The schema caps bullets
at 6 per role and 350 characters each - sized so a full master-profile bullet
fits without compression. **Carry bullets over from the master profile
near-verbatim.** Rewriting a rich 300-character bullet down to a 110-character
stub loses the metrics, the technology names, and the ATS keywords all at once;
that over-summarization is the single most common way a build of this skill has
gone wrong. Select which bullets to include and reorder them for the role, but
do not compress the ones you keep. The autofit ladder absorbs length; a
two-page target at 9pt Carlito holds every role at full richness.

Preserve the profile's `**bold**` markers on the impact phrase of each bullet -
they render as real bold in the PDF and are part of the approved design. Carry
the links too: each role's `project_name`/`project_url`, each project's GitHub
`url`, each certification's `url`, and each publication's `url` + `link_label`
(plus its one-sentence `note`). Contact links use paired fields: `linkedin` is
the display text, `linkedin_url` the target (same for `github`/`website`). The
name stays title-case in the data; the template renders it in caps.

Pull the whole master profile, not just the jobs. Personal/open-source
`projects`, `certifications`, and `publications` are separate schema fields, and
each is real evidence the paid roles may not show - a certification is an exact
keyword an ATS looks for, and a publication or side project often carries the
one term the JD wants. Include the entries relevant to this posting; on a tight
one-pager, drop the least-relevant of these before you cut a job bullet. Match a
certification's name to the issuer's official string, and never list one the
user does not hold - the honesty constraint covers these fields too.

Bullets should lead with the outcome and name the technology, in plain speech.
No em dashes, no "responsible for", no adjectives doing work that a number
should do. `lint_style()` flags these and runs automatically in the build.

Set `"date_style"` deliberately - see the trade-off below.

### 5. Build

```bash
python3 scripts/build.py resume_data.json \
  --role ml-engineer --company stripe --job-id 4821 \
  --jd job-description.md [--cover cover_data.json] [--docx]
```

This validates, escapes LaTeX, compiles, extracts text, checks layout, and
writes everything to `$CV_HOME/<role>/<company>/<job-id>/`: `resume.pdf`,
`resume.tex`, `resume_data.json`, page JPEGs, `job-description.md`, and
`build-report.json`. Exit code is non-zero when a hard check fails.

Autofit is on by default: because a compile takes about 0.15s, the renderer
tries progressively denser typography and keeps the first setting that hits the
target page count. It only moves font size, margins, and spacing - it never
drops content, so if it exhausts the ladder the honest answer is that there is
too much text and the user should cut a bullet.

### 6. Read the report, then look at the pages

Fix every hard failure and re-run. `references/troubleshooting.md` maps each
check to its cause and fix.

Then **actually look at the page JPEGs.** The automated checks catch structural
problems, not every problem - during development, a template bug printed
`built-in method items of dict object at 0x7f92...` into the Skills section and
passed every text check, because it was extractable text in the right place. It
was obvious on sight. View the images before you call a document done.

### 7. Cover letter

Same track, driven by `cover_data.json`. Research the company's engineering
writing for what they actually care about, then write three or four paragraphs:
why this role, one concrete piece of evidence that maps to their problem, and a
close. Technical and specific; cut anything that would survive a find-replace of
the company name, because that sentence is not doing any work.

## The date alignment trade-off

Worth understanding, because the two goals genuinely conflict.

Flush-right dates via `\hfill` look right and satisfy the layout check. But
raw-mode PDF text extractors break lines on wide whitespace gaps, so a
flush-right date can migrate to the end of the extracted text stream, detached
from its employer. A parser pairing them positionally then records the wrong
dates. `verify.py` detects this as `dates_stay_with_employer`.

- `"date_style": "right"` - flush-right dates, adjacency warning expected.
- `"date_style": "inline"` - bold dates after the italic title
  (`Title | Dates`), which is also how the approved reference resume lays out
  dates. Employer and date cannot be separated under extraction.

Choose `inline` when the application funnels through a large-company ATS and
`right` when a human reads it first; `inline` matches the reference design, so
it is the usual pick. Tell the user which one you picked and why.

## Bundled files

- `scripts/schema.py` - Pydantic models, LaTeX escaping, style linting
- `scripts/render.py` - JSON to LaTeX to PDF, autofit, page JPEGs
- `scripts/render_docx.py` - optional Word output from the same payload
- `scripts/verify.py` - ATS extraction and layout checks (run standalone on any PDF)
- `scripts/build.py` - the orchestrator; this is the normal entry point
- `scripts/preflight.py` - dependency check
- `assets/resume.tex.j2`, `assets/cover_letter.tex.j2` - templates
- `assets/master_profile.example.md` - master profile shape
- `references/workflow.md` - JD extraction and gap analysis in depth
- `references/troubleshooting.md` - each failed check, its cause, its fix

`verify.py` works on any PDF, including one this skill did not produce, which
makes it useful for auditing a resume the user already has.
