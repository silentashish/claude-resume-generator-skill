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

When a bridge is borderline, pick the more conservative wording and write
one line in the notes saying what the bolder wording would have been and why
it was not used. The user can promote it themselves; they cannot un-send a
claim that was never theirs.

## Recording decisions

`tailoring-notes.md` goes in the output folder next to the PDF and is the
record of every call the run made. It replaces the approval round-trip, so it
has to be complete enough that the user can disagree with a decision after
the fact. Sections, each a short list:

- **Direct hits** - requirement, the profile evidence used, where it landed.
- **Bridges** - requirement, the underlying experience, the exact wording
  used, and the bolder wording rejected if there was one.
- **Gaps left open** - requirement and why nothing honest fit.
- **Content choices** - which roles got all their bullets, which were trimmed
  and to how many, which projects/publications/certifications were included
  or dropped, and what filled the page budget.
- **Layout** - date style and why, target pages, final fill, and any
  `min_fill` or `target_pages` change with its justification.

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
