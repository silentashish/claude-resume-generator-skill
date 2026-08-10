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
# These are the levers that control page count. Raise them only if the verify
# step says there is room; lower them when a document overflows.
MAX_BULLETS_PER_ROLE = 4
MAX_BULLET_CHARS = 120
MAX_SKILL_GROUPS = 6


class Contact(BaseModel):
    """Plain-text contact fields.

    Deliberately strings, not icons. Icons in a resume header are images, and
    image-based contact info is one of the most common reasons an ATS returns a
    blank phone/email field.
    """

    name: str = Field(min_length=2, max_length=60)
    location: str = Field(max_length=60)
    email: str
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    website: Optional[str] = None

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
    name: str = Field(max_length=60)
    tech: Optional[str] = Field(default=None, max_length=90)
    bullets: List[str] = Field(default_factory=list, max_length=3)

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
    detail: Optional[str] = Field(default=None, max_length=140)


class SkillGroup(BaseModel):
    """One labelled row of skills, e.g. 'Languages: Python, Go, Java'.

    Grouped rows read better than one undifferentiated blob and still keep every
    keyword in extractable plain text.
    """

    label: str = Field(max_length=28)
    items: str = Field(max_length=200)


class ResumeData(BaseModel):
    contact: Contact
    summary: Optional[str] = Field(default=None, max_length=400)
    experience: List[Role] = Field(min_length=1)
    education: List[Education] = Field(min_length=1)
    skills: List[SkillGroup] = Field(min_length=1, max_length=MAX_SKILL_GROUPS)
    projects: List[Project] = Field(default_factory=list)
    target_pages: int = Field(default=2, ge=1, le=2)
    date_style: str = Field(
        default="right",
        pattern="^(right|inline)$",
        description=(
            "'right' flush-rights dates with \\hfill and looks better. 'inline' puts "
            "them on the same line after a pipe. Raw-mode PDF text extractors split "
            "on wide whitespace gaps and relocate flush-right dates to the end of the "
            "stream, detaching them from their employer; use 'inline' when ATS "
            "parsing matters more than appearance."
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
        if "\u2014" in t or "\u2013" in t:
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
