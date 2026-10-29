# Engineering Knowledge Base

A portable, repository-native engineering knowledge base: Markdown, Git, and a searchable index. This directory is deliberately independent of Pi, a specific model provider, vector databases, or hosted knowledge services.

## Reuse before research

Before starting research or implementation:

1. Search [`index.md`](index.md) and the relevant topic files.
2. Check each record's status, source version, verified date, evidence, and review condition.
3. Reuse a current reliable record; add only missing facts or changed evidence.
4. Update the index in the same change as a new or materially updated record.
5. Preserve disagreements and unknowns; do not rewrite historical evidence as if it were always known.

Search with standard tools (`rg`, editor search, or GitHub code search). No service/database is required.

## Record status

Use exactly one status per record:

- **UNVERIFIED** — assertion or lead without reliable primary-source evidence.
- **DOCUMENTED** — supported by source/documentation, not independently executed here.
- **EXPERIMENTAL** — tested in a bounded experiment; results are limited to its stated setup.
- **VERIFIED** — the specific claim is backed by reproducible evidence. Name the exact claim; source metadata verification does not imply runtime compatibility.
- **STALE** — a prior record whose version, source, or review condition is outdated.

A document can contain both verified metadata and unverified capabilities. State the boundary explicitly; never let a high-confidence source citation imply a successful platform PoC.

## Required record metadata

Every research, pattern, decision, experiment, and lesson record must state:

- Topic
- Research Question
- Source URL(s)
- Source Version (tag/commit or `NOT VERSIONED`)
- License (or `UNKNOWN / NOT REVIEWED`)
- Verified Date (YYYY-MM-DD)
- Findings
- Limitations
- Applicability
- Evidence (commands, source locations, test results, or artifact path)
- Confidence and what the confidence applies to
- Related Projects
- Next Review Condition
- Knowledge Status

Start with [`templates/research-record.md`](templates/research-record.md) or the matching template. Label vendor documentation as a vendor claim until independently tested.

## Trust, privacy, and scope

- Prefer official release metadata, tagged source, license files, and official documentation. Cite URLs and exact versions.
- Do not fabricate release dates, versions, license rights, compatibility, prices, or benchmark results. If unavailable, say `UNKNOWN`.
- Do not install every candidate, invoke paid providers, create accounts, or access remote/customer systems merely to fill a report. Define a bounded PoC and explicit cost/environment gate first.
- Keep generic cross-project patterns here. Project-specific source observations, test provenance, private paths, and run results belong under `projects/<project-id>/` or the project's existing docs/experiment locations, with links—not copied private source.
- Never store credentials, tokens, cookies, customer data, sensitive logs, or unauthorized source copies.
- Skills are operating procedures, not factual authority. Only turn repeatable, safety-reviewed practices into skills; keep unverified research advisory and low privilege.

## Structure

- `frameworks/` — versioned framework research
- `patterns/` — reusable engineering patterns
- `decisions/` — portable ADRs or links to canonical project ADRs
- `experiments/` — bounded protocols and results
- `lessons/` — verified operational learnings
- `skills/` — index of validated reusable workflows
- `templates/` — reusable record templates
- `projects/` — project-specific evidence separated from shared knowledge

The portable team definition is [`team-definition.md`](team-definition.md); Pi profiles are adapters under `.pi/agents/`.
