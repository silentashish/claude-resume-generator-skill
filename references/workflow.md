# Job description analysis and gap bridging

Read this when working through steps 1-3 of the skill.

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

Two signals worth surfacing to the user because they change whether applying is
worth the effort: a stack with no overlap at all, and phrasing that implies a
much higher (or lower) level than they are targeting.

## Ranking what to include

The resume is a fixed-size container, so including something means excluding
something else. Rank each candidate bullet by:

1. Does it use a term that appears in the mandatory list?
2. Does it demonstrate the core responsibility rather than an adjacent skill?
3. Is there a defensible number attached?
4. Is it recent?

Lead each role with its highest-ranked bullet. Screeners read the first bullet
of the first role and skim from there, so burying the most relevant work in
position four wastes it.

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

## Presenting for approval

Show the user a compact table - requirement, proposed evidence, and the exact
bullet you intend to write - plus the list of gaps you are leaving open. Ask
directly about anything where the framing could be read as overstating.

This step exists because the user is the only source of truth about what they
actually did, and because a resume they did not sanction is worse than no
resume. Do not skip it to save a round trip.

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
