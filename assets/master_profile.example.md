# Master Profile - Example

The single source of truth. Every tailored resume is a *selection* from this
file, never an addition to it. Keep it exhaustive and unpolished: include work
that will not fit on any resume, because the whole point is having material to
choose from when a posting asks for something unexpected.

Record numbers here with their provenance, so a bullet can be defended later.

---

## Contact

- Name: Ashish G
- Location: Atlanta, GA
- Email: you@example.com
- Phone: 555-0100
- LinkedIn: linkedin.com/in/yourhandle
- GitHub: github.com/yourhandle
- Website: yoursite.com
- Work authorization: requires sponsorship (note it here so cover letters can
  address it when the posting raises it)

## Experience

### NASA IMPACT - Research Engineer (part-time)
2024 - Present | Huntsville, AL

Everything done here, one line each. More detail than any resume will hold.

- Fixed a silent data-loss bug in the Airbus Optical expand step
  (`dags/vendors/airbus_optical/expand.py`) with a two-pass extraction approach;
  `unzip_files()` now returns `status: error` on dropped entries.
  *Provenance: PR #— ; before/after entry counts in the run log.*
- Built RAG pipelines with LangGraph over a ~2M document corpus; p95 latency
  down 40% by routing low-complexity queries away from the large model.
  *Provenance: Grafana dashboard, week of —.*
- Ran the observability stack (Grafana, Prometheus, Loki) across 3 clusters.
- Thesis work: DoRA applied to neural codecs, mIoU 0.643 to 0.723 (+8.04 pp) on
  FLAIR without retraining the codec or adding bits.
  *Provenance: thesis Table 4.*

**Technologies:** Python, Airflow, LangGraph, PyTorch, Grafana, Prometheus, AWS

### Houzz - Software Engineer
2021 - 2023

- Migrated legacy PHP services to Node.js; p95 latency down 35%.
- Built the Moodboard canvas on Paper.js and Three.js, used by 2M+ users.

**Technologies:** PHP, Node.js, React, TypeScript, Paper.js, Three.js

## Education

### University of Alabama in Huntsville
M.S. Computer Science, expected 2026
Thesis: Mitigating Reconstruction Loss in Neural Compression for Downstream
Tasks Using Weight-Decomposed Low-Rank Adaptation (DoRA)

## Skills

Group by category, honestly. Mark anything rusty so it is not surfaced for a
role that centers on it.

- **Languages:** Python, Go, Java, TypeScript, PHP, C# *(rusty)*
- **ML:** PyTorch, LangGraph, RAG, PEFT (LoRA/DoRA), Weaviate, pgvector
- **Infra:** AWS, Kubernetes, Terraform, Airflow, Spark, Grafana

## Projects

### opensearch-local MCP server
Claude Desktop integration with local OpenSearch and Grafana. Agentic tools
require the MCP `sampling` capability advertised during the `initialize`
handshake.
**Tech:** Python, MCP, OpenSearch, Grafana

## Gaps and constraints

Being explicit here keeps the generator from quietly papering over them.

- No production Rust or Scala.
- No formal people-management experience.
- Requires visa sponsorship.
