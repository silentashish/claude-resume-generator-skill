# Job description analysis and gap bridging

Read this when working through steps 1-4 of the skill.

## Extracting requirements

Job descriptions are written by several people and mix hard requirements with
aspirations. Sort the text into four buckets and keep the posting's own wording,
since keyword matching compares against their vocabulary, not yours:

- **Mandatory** - anything under "requirements"/"must have", or stated with
  "required", a year count, or a degree. These drive filtering.
- **Preferred** - "nice to have", "bonus", "familiarity with". Worth matching
  when honest, never worth stretching for.
- **Responsibilities** - what the person will actually do. This is the most
  useful section for choosing which experience to lead with, and the most
  ignored.
- **Seniority and context** - team size, ownership language, whether they say
  "ship" or "research", regulated industry, on-call. Sets the register.

Two signals worth noting in the delivery message because they change whether
applying is worth the effort: a stack with no overlap at all, and phrasing
that implies a much higher (or lower) level than the user is targeting.
Note them and build anyway; the decision to apply is the user's, made after
seeing the finished document.

## Ranking what to include

Rank each candidate bullet by:

1. Does it use a term that appears in the mandatory list?
2. Does it demonstrate the core responsibility rather than an adjacent skill?
3. Is there a defensible number attached?
4. Is it recent?

Lead each role with its highest-ranked bullet. Screeners read the first bullet
of the first role and skim from there, so burying the most relevant work in
position four wastes it.

Ranking decides *order*, not *inclusion*. The page budget decides inclusion:
keep adding ranked bullets until the target pages are full (see "Filling the
page budget" in SKILL.md), and only cut when the densest typography still
overflows.

## Bridging gaps honestly

The useful move is translation: the same work, described in the vocabulary the
posting uses. The underlying claim must stay true.

**Legitimate:**

| JD asks for | Profile contains | Honest bridge |
|---|---|---|
| "high-throughput backend services" | PHP-to-Node.js migration | Describe the migration in throughput and latency terms, since that is what it was |
| "observability at scale" | Grafana/Prometheus/Loki work | Name the stack and the cluster count |
| "LLM evaluation" | RAG pipeline with measured retrieval quality | Describe the metric and how it was measured |
| "model efficiency" | DoRA/LoRA fine-tuning research | Frame as parameter-efficient adaptation with the measured delta |

**Not legitimate:** adding a technology the user has not used, inventing a
number, promoting a contribution to ownership ("led"/"owned" when they did not),
or listing a skill because it appears in the posting.

The test: could the user talk for five minutes about this bullet under a
follow-up question from someone who does the job? If not, it does not go in.

When a bridge is borderline, the five-minute test decides: if the user could
hold that conversation, use the bridge in the posting's words and list it in
the notes; if not, leave the gap open and list it. Do not water a passing
bridge down out of caution, and do not stretch a failing one.

## Recording decisions

`tailoring-notes.md` goes in the output folder next to the PDF and is the
record of every call the run made. It replaces the approval round-trip, so it
has to be complete enough that the user can disagree with a decision after
the fact. A program parses it too, so keep SKILL.md's structure exactly (the
`<!-- resume-tailor notes v2 -->` marker and the four `##` headings), one line
per entry:

- **Direct hits** - requirement and the profile evidence used.
- **Reframings used** - one `###` per requirement, with `Source fact:` (verbatim
  from the profile) and `Wording:` (as written in the resume).
- **Gaps left open** - requirement and why nothing honest fit.
- **Decisions** - date style and why; which roles got all their bullets and
  which were trimmed; projects, publications or certifications included or
  dropped; what filled the page budget; any `min_fill` or `target_pages`
  change; judgement calls on honesty.

Write it before the payload so the payload follows the plan, and update it if
the build loop changes a decision.

## Cover letter research

Look for the company's engineering blog, public repositories, or a recent
technical talk. What you want is the problem they talk about having, phrased the
way they phrase it, so the letter can connect one specific piece of the user's
experience to it.

Structure that works: what you are applying for and one sentence of who you are;
one paragraph of concrete evidence aimed at their actual problem; a short close.
Cut any sentence that would still make sense with a different company name
substituted in - that sentence is filler, and it is the reason most cover
letters are ignored.
