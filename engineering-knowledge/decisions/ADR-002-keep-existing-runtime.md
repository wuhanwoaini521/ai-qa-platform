# ADR-002: Keep Existing Execution Owners; Defer Framework Integration

- **Status:** PROPOSED / DEFERRED — not a passed architecture gate.
- **Date:** 2026-10-28.
- **Decision owner:** Human platform owner retains architecture-gate authority; this record is a research/development proposal only.
- **Context and evidence:** Current source has a persisted TaskRuntimeService, TestRun/WorkerDaemon/PytestRunner, BrowserRuntime, DecisionService, and a Discovery domain lifecycle. Prior architecture review found state/event/evidence fragmentation, but no comparative candidate PoC or cross-process PostgreSQL acceptance. Official P0 releases, licenses and manifests were subsequently verified; platform compatibility remains untested. A narrow Quality Discovery recovery bug was reproduced and fixed locally without a migration.
- **Decision:** **KEEP** existing Runtime/BrowserRuntime/DecisionService/provider ownership. **REFACTOR** only the localized, evidence-backed Discovery recovery status/event transition using existing versioned ORM state. **DEFER** cross-domain schema/event convergence and all LangGraph/Browser Use/Skyvern production integration pending the existing Architecture Gate.

## Alternatives

1. **A — Keep current architecture and fix local lifecycle defects.** Lowest migration risk; keeps existing single owners; does not claim normalized cross-workflow replay.
2. **B — Additive lifecycle/event/evidence convergence around TaskRuntimeService.** Potentially improves cross-domain consistency, but risks introducing parallel authoritative state and dual-write/reconciliation complexity. Remains a conditional design proposal; no implementation approval from this ADR.
3. **C — Replace orchestration/browser lifecycle with a framework/service.** No evidence supports this, and it risks data/workflow regressions and duplicate ownership. Not recommended.

## Independent challenge and response

The independent Architecture Critic argued that current evidence proves representation mismatch, not user-visible failure; B's normalized envelopes may become shadow state; cross-process/browser/Pytest effects are not atomic; and operational/migration cost is unmeasured. It recommended retaining A until PostgreSQL race tests and a concrete consumer/incident justify B. The challenge is accepted as an evidence limitation. The existing `docs/architecture-review/architecture-decisions.md` gate remains DEFERRED / NOT PASSED.

For the local recovery change, the Critic also noted remaining multi-instance startup ownership risk and potential gaps outside ORM versioned writers. The implementation limits its claim to a stale-row status transition and atomic persisted event on the existing versioned ORM; it does not claim fencing, multi-process ownership, or exactly-once stream delivery.

## Consequences, acceptance, rollback

- No framework dependency, migration, new runtime, or new state store is introduced.
- Test verdicts remain sourced only from Pytest exit codes and persisted executions.
- The recovery change must pass focused SQLite tests and a real disposable PostgreSQL regression before it can be called fully verified; PostgreSQL setup/verification is currently **BLOCKED**.
- Rollback is a code revert of the local guard/event transaction; database schema is unchanged.

## Open evidence / approval

- Real PostgreSQL status-race/transaction test and any multi-process recovery acceptance.
- Browser Use/Skyvern same-page comparison and complete candidate dependency resolution.
- Real provider and human approval acceptance remains separate; no provider spend or real approval occurred.
- Human architecture-gate decision remains pending.

- **Related records:** `docs/architecture-review/architecture-decisions.md`; `engineering-knowledge/frameworks/{langgraph,browser-use,skyvern}.md`; `engineering-knowledge/patterns/conditional-recovery.md`.
