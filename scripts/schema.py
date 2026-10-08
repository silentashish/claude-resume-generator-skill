"""Pydantic models for resume/cover-letter payloads, plus LaTeX escaping.

The schema mirrors the LaTeX templates exactly. Its job is to make overflow
impossible *before* a compile is attempted -- a bullet that is too long or a
role with too many bullets will push the document onto a third page, and it is
much cheaper to catch that here than after render + verify.
"""

from __future__ import annotations

import re
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

# --- Layout budget -----------------------------------------------------------
# These caps exist to stop a runaway payload, not to ration content. The
# renderer's autofit absorbs length by moving typography, and the verify step
# measures how full the last page actually is, so the right amount of content
# is "enough to fill the target page count", not "as little as possible".
# Calibrated against the dense two-page reference layout (Carlito ~10pt,
# 0.5in margins): a 400-char bullet wraps to three or four lines there.
MAX_BULLETS_PER_ROLE = 8
MAX_BULLET_CHARS = 400
MAX_PROJECT_BULLETS = 4
MAX_SKILL_GROUPS = 10
# Fraction of the last page's text area that must be used before a build is
# accepted. Below this the document reads as thin, and almost always the
# master profile had more to give.
DEFAULT_MIN_FILL = 0.85


class Contact(BaseModel):
    """Plain-text contact fields, optionally hyperlinked.

    Deliberately strings, not icons. Icons in a resume header are images, and
    image-based contact info is one of the most common reasons an ATS returns a
    blank phone/email field.

    `linkedin`/`github`/`website` hold the *display* text (a readable URL like
    'linkedin.com/in/ashish-...'). The matching `*_url` field holds the full
    https:// target for the clickable link. If the `*_url` is omitted the
    display text is printed without a link. Because the display text is itself
    the URL, a parser that drops link annotations still reads the address.
    """

    name: str = Field(min_length=2, max_length=60)
    location: str = Field(max_length=60)
    email: str
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    linkedin_url: Optional[str] = None
    github: Optional[str] = None
    github_url: Optional[str] = None
    website: Optional[str] = None
    website_url: Optional[str] = None

    @field_validator("name")
    @classmethod
    def title_case_not_shouted(cls, v: str) -> str:
        if v.isupper() and len(v) > 3:
            raise ValueError(
                "Name is ALL CAPS. Some ATS name-parsers treat all-caps tokens as "
                "acronyms and drop them. Use title case."
            )
        return v


class Role(BaseModel):
    company: str = Field(max_length=60)
    title: str = Field(max_length=70)
    location: Optional[str] = Field(default=None, max_length=40)
    dates: str = Field(max_length=30, description="e.g. 'Jan 2024 - Present'")
    bullets: List[str] = Field(min_length=1, max_length=MAX_BULLETS_PER_ROLE)
    project_name: Optional[str] = Field(
        default=None, max_length=80,
        description="shipped product/site to cite under the role, e.g. 'Houzz Moodboard'")
    project_url: Optional[str] = Field(
        default=None, max_length=200,
        description="link target for project_name; rendered as 'Project: <name>'")

    @field_validator("bullets")
    @classmethod
    def bullets_fit(cls, v: List[str]) -> List[str]:
        for i, b in enumerate(v):
            if len(b) > MAX_BULLET_CHARS:
                raise ValueError(
                    f"bullet {i} is {len(b)} chars (limit {MAX_BULLET_CHARS}): "
                    f"{b[:60]}... -- tighten it rather than letting the page overflow"
                )
            if not b.strip():
                raise ValueError(f"bullet {i} is empty")
        return v


class Project(BaseModel):
    name: str = Field(max_length=80)
    tech: Optional[str] = Field(default=None, max_length=120)
    url: Optional[str] = Field(default=None, max_length=200,
                               description="GitHub/demo link; shown as 'GitHub: <short url>'")
    bullets: List[str] = Field(default_factory=list, max_length=MAX_PROJECT_BULLETS)

    @field_validator("bullets")
    @classmethod
    def bullets_fit(cls, v: List[str]) -> List[str]:
        for b in v:
            if len(b) > MAX_BULLET_CHARS:
                raise ValueError(f"project bullet exceeds {MAX_BULLET_CHARS} chars: {b[:60]}...")
        return v


class Education(BaseModel):
    institution: str = Field(max_length=80)
    degree: str = Field(max_length=90)
    dates: str = Field(max_length=30)
    location: Optional[str] = Field(default=None, max_length=40)
    detail: Optional[str] = Field(default=None, max_length=200,
                                  description="thesis, GPA, honours, relevant coursework")


class Certification(BaseModel):
    """A credential the user actually holds.

    Kept to one line each: name, issuer, year. A certification is a keyword an
    ATS looks for by exact string ('AWS Certified Solutions Architect'), so the
    name must match the issuer's official wording rather than a paraphrase.
    """

    name: str = Field(max_length=100)
    issuer: Optional[str] = Field(default=None, max_length=80)
    year: Optional[str] = Field(default=None, max_length=12)
    url: Optional[str] = Field(default=None, max_length=250,
                               description="verification link, e.g. the Coursera certificate URL")


class Publication(BaseModel):
    """One published work: paper, article, patent, or talk.

    Single line each. The title carries the keywords; venue and year establish
    that it is real and locatable. Do not pad with an abstract -- a resume lists
    publications, it does not reproduce them.
    """

    title: str = Field(max_length=180)
    venue: Optional[str] = Field(default=None, max_length=120,
                                 description="journal, conference, or publisher")
    year: Optional[str] = Field(default=None, max_length=12)
    url: Optional[str] = Field(default=None, max_length=250,
                               description="DOI or link; rendered as a labelled hyperlink")
    link_label: Optional[str] = Field(default=None, max_length=20,
                                      description="display text for the url, e.g. 'arXiv'; defaults to 'Link'")
    note: Optional[str] = Field(default=None, max_length=400,
                                description="one-sentence result summary; supports **bold** on the key metric")


class SkillGroup(BaseModel):
    """One labelled row of skills, e.g. 'Languages: Python, Go, Java'.

    Grouped rows read better than one undifferentiated blob and still keep every
    keyword in extractable plain text.
    """

    label: str = Field(max_length=40)
    items: str = Field(max_length=400)


class ResumeData(BaseModel):
    contact: Contact
    summary: Optional[str] = Field(default=None, max_length=900)
    experience: List[Role] = Field(min_length=1)
    education: List[Education] = Field(min_length=1)
    skills: List[SkillGroup] = Field(min_length=1, max_length=MAX_SKILL_GROUPS)
    projects: List[Project] = Field(default_factory=list)
    certifications: List[Certification] = Field(default_factory=list)
    publications: List[Publication] = Field(default_factory=list)
    publications_suffix: Optional[str] = Field(
        default=None, max_length=30,
        description="appended to the Publications header, e.g. ' (70+ Citations)'")
    target_pages: int = Field(default=2, ge=1, le=2)
    min_fill: float = Field(
        default=DEFAULT_MIN_FILL, ge=0.0, le=1.0,
        description=(
            "Fraction of the last page's text area that must be used. The build "
            "fails below it. Lower it only when the master profile is genuinely "
            "exhausted, and say so in the tailoring notes."
        ),
    )
    date_style: str = Field(
        default="inline",
        pattern="^(right|inline)$",
        description=(
            "'inline' (default) puts bold dates after the italic title, separated "
            "by a bar, so employer and dates cannot be separated by extraction. "
            "'right' flush-rights dates with \\hfill; raw-mode PDF text extractors "
            "split on wide whitespace gaps and can relocate flush-right dates to the "
            "end of the stream, so use it only when a human reads the PDF first."
        ),
    )


class CoverLetterData(BaseModel):
    contact: Contact
    company: str = Field(max_length=80)
    role_title: str = Field(max_length=80)
    date: str = Field(max_length=30)
    salutation: str = Field(default="Dear Hiring Manager,", max_length=80)
    paragraphs: List[str] = Field(min_length=2, max_length=5)
    closing: str = Field(default="Sincerely,", max_length=40)

    @field_validator("paragraphs")
    @classmethod
    def keep_it_to_one_page(cls, v: List[str]) -> List[str]:
        total = sum(len(p) for p in v)
        if total > 2600:
            raise ValueError(
                f"cover letter body is {total} chars; over ~2600 it spills to a "
                "second page. Cut the weakest paragraph."
            )
        return v


# --- LaTeX escaping ----------------------------------------------------------
# Tech resumes are full of characters that are LaTeX control sequences. Missing
# even one of these crashes the compiler, so escaping happens centrally here
# rather than being re-implemented per template.

_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

# Typographic characters that copy-paste in from job descriptions and Word docs.
_UNICODE_FIXES = {
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2013": "--", "\u2014": "---", "\u2026": "...", "\u00a0": " ",
    "\u2022": "-", "\u00ad": "",
}


def escape_latex(text: str) -> str:
    """Make an arbitrary string safe to inject into a LaTeX template."""
    if text is None:
        return ""
    for bad, good in _UNICODE_FIXES.items():
        text = text.replace(bad, good)
    out = []
    for ch in text:
        out.append(_ESCAPES.get(ch, ch))
    return "".join(out)


# Inline emphasis: the master profile marks the impact phrase of a bullet with
# **double asterisks** (markdown-style). Asterisks survive escape_latex
# untouched, so conversion happens after escaping and cannot be injected around.
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)


def apply_bold(text: str) -> str:
    """Convert **marked** phrases into \\textbf{...}."""
    return _BOLD_RE.sub(r"\\textbf{\1}", text)


def escape_url(url: str) -> str:
    """Escape a raw URL for use as an \\href target.

    Only % and # are special inside hyperref's link argument; running a URL
    through escape_latex instead would corrupt underscores and tildes in the
    link target.
    """
    return url.replace("\\", "").replace("%", r"\%").replace("#", r"\#")


def escape_model(obj):
    """Recursively escape every string in a validated model / dict / list."""
    if isinstance(obj, BaseModel):
        return escape_model(obj.model_dump())
    if isinstance(obj, dict):
        return {k: escape_model(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [escape_model(v) for v in obj]
    if isinstance(obj, str):
        return escape_latex(obj)
    return obj


# --- Style linting -----------------------------------------------------------
# These are warnings, not errors. They flag writing that tends to read as
# machine-generated or that the candidate cannot defend in a live interview.

_HEDGES = [
    "responsible for", "helped with", "worked on", "assisted in",
    "participated in", "involved in", "duties included",
]
_FLUFF = [
    "passionate", "results-driven", "team player", "self-starter",
    "detail-oriented", "synergy", "go-getter", "thought leader",
    "leverage synergies", "dynamic professional",
]


def lint_style(data: dict) -> List[str]:
    """Return human-readable style warnings for a resume payload."""
    warnings: List[str] = []
    texts: List[tuple] = []

    for role in data.get("experience", []):
        for b in role.get("bullets", []):
            texts.append((f"{role.get('company')} bullet", b))
    for proj in data.get("projects", []):
        for b in proj.get("bullets", []):
            texts.append((f"project {proj.get('name')}", b))
    if data.get("summary"):
        texts.append(("summary", data["summary"]))

    for where, t in texts:
        low = t.lower()
        if t.count("**") % 2 != 0:
            warnings.append(f"{where}: unbalanced ** bold marker; it will print literally")
        if "\u2014" in t or "\u2013" in t or " -- " in t or " --- " in t:
            warnings.append(f"{where}: contains an em/en dash; rewrite as plain speech")
        for h in _HEDGES:
            if h in low:
                warnings.append(f"{where}: hedging phrase '{h}' -- state what you built instead")
        for f in _FLUFF:
            if f in low:
                warnings.append(f"{where}: filler phrase '{f}' -- cut it or replace with evidence")
        if not re.search(r"\d", t):
            warnings.append(f"{where}: no number in this bullet -- add scale, delta, or duration if honest")

    return warnings
