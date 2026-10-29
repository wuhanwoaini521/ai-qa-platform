# Engineering Knowledge Index

Updated: 2026-10-28. Search this index before opening a research task.

## Frameworks — P0

| Topic | Status | Source version verified | License at tag | Applies to | Record |
|---|---|---:|---|---|---|
| LangGraph persistence, interrupts, human approval | VERIFIED (release metadata/manifest/docs only) | 1.2.18 | MIT | Design comparison only; no platform integration or runtime PoC | [langgraph.md](frameworks/langgraph.md) |
| Browser Use browser agent | VERIFIED (release metadata/manifest/docs only) | 0.13.14 | MIT | Isolated comparison candidate; no platform compatibility or benchmark established | [browser-use.md](frameworks/browser-use.md) |
| Skyvern browser automation | VERIFIED (release metadata/manifest/docs only) | v1.0.56 | AGPL-3.0 | Isolated architecture/deployment comparison only; legal review needed before distribution/embedding | [skyvern.md](frameworks/skyvern.md) |

“VERIFIED” here is intentionally limited to the release/tag/license/manifest/source claims cited by each file. No candidate has been installed, benchmarked, or approved for production. Research was captured 2026-10-28; review if a newer relevant release appears or before any PoC/dependency decision.

## Engineering patterns and experience

| Topic | Status | Applicability | Record |
|---|---|---|---|
| Conditional recovery with optimistic version checks; state/event atomicity | EXPERIMENTAL | Existing SQLAlchemy versioned row; bounded SQLite and PostgreSQL 18.6 service/repository tests; not multi-process or production PG16 evidence | [conditional-recovery.md](patterns/conditional-recovery.md) |
| Distinguish source metadata, vendor claims, and platform execution evidence | DOCUMENTED | All framework research and QA acceptance | [source-evidence-boundaries.md](lessons/source-evidence-boundaries.md) |

## Decisions and experiments

- [ADR-002 — Keep existing execution owners; defer framework integration](decisions/ADR-002-keep-existing-runtime.md) — proposed local disposition only; **Architecture Gate remains DEFERRED / NOT PASSED**.
- [Browser agent comparison protocol](experiments/browser-agent-comparison.md) — protocol ready; Browser Use/Skyvern comparison **NOT RUN**.
- Project-specific architecture evidence is under [`docs/architecture-review/`](../docs/architecture-review/) and [`projects/ai-qa-platform/`](projects/ai-qa-platform/README.md).

## Skills

- [Reusable research workflow](skills/README.md) → [`.agents/skills/framework-research/SKILL.md`](../.agents/skills/framework-research/SKILL.md).
