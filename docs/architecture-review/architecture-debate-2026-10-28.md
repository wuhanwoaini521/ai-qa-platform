# Bounded Architecture Debate — Execution Core and P0 Frameworks

**Date:** 2026-10-28. **Formal round:** 1 of maximum 2. **Architecture Gate:** **DEFERRED / NOT PASSED**. This debate does not authorize a framework dependency, schema migration, production rollout, or architecture replacement.

## Question and scope

Should the platform advance the provisional Candidate B (incremental cross-lifecycle execution/event/evidence convergence around the existing Task Runtime), or stay with Candidate A and fix only demonstrated lifecycle defects? Separately, do the P0 framework sources justify production adoption or an isolated PoC?

Constraints: retain `DecisionService`, `TaskRuntimeService`, `BrowserRuntime`, existing provider abstractions, and deterministic Pytest verdicts; no parallel scheduler/browser/provider/event store; no AI-authoritative PASS/FAIL; no unattended or external write.

## Scout — source evidence

The fresh-context Technology Scout verified current official release metadata, tag licenses and manifests for LangGraph 1.2.18 (MIT; Python ≥3.10), Browser Use 0.13.14 (MIT; Python ≥3.11), and Skyvern v1.0.56 (AGPL-3.0; Python ≥3.11,<3.15). It found that Skyvern's tagged manifest declares FastAPI `<0.137`, while this platform resolves 0.141.1; Browser Use's top-level manifest does not settle its transitive Playwright compatibility. LangGraph's official interrupt docs state resumed nodes start from the beginning, so side effects before interrupts need idempotency. None was installed or run. Full details: [`framework-p0-verification-2026-10-28.md`](framework-p0-verification-2026-10-28.md).

**Evidence boundary:** source facts are verified at those tags; vendor capability descriptions are not project test results. No token cost, runtime success, or candidate comparison is claimed.

## Candidate designs (existing proposal)

### Option A — retain current architecture and patch proven behavior

Keep domain lifecycles and existing owners; fix individual incorrect transitions/events within current services/repositories. No normalized second record or event store. Use measured user-visible failures to justify any broader work. Lowest migration/compatibility risk.

### Option B — additive convergence around TaskRuntimeService

Retain all current domain tables and capabilities but introduce common lifecycle/event/evidence mappings, cross-links, lease/idempotency/recovery contracts and UI projections. Potentially improves replay/provenance and cross-domain truth; requires authoritative-source rules, migration/dual-read/write semantics, compatibility and DB/race proof before implementation.

### Option C — replace execution/browser framework

Use a third-party runtime/browser platform as the new center. Current evidence does not support it and it risks duplicate task, state, approval, browser, evidence and verdict ownership. Rejected for current evidence.

## Critic — independent counterargument

The fresh-context Architecture Critic argues Candidate B has not earned preference over A: present evidence proves separate representations, not an operational/user failure; B's additional envelopes and dual-read/write could become shadow sources of truth; orchestration cannot make browser/filesystem/Pytest effects atomic; and operational/migration costs are unmeasured. The small qualitative scoring difference in the prior report is not benchmark evidence. A should remain the operating baseline until a concrete failure demonstrates A's limits.

The Critic also challenged the proposed local recovery guard: exact status recheck and optimistic version retry do not prove multi-instance ownership/fencing; bulk SQL writers can bypass ORM versioning; status and event in separate commits can leave a missing/stale event. It proposed a disposable PostgreSQL two-session/process race and crash-injection test.

## Implementation complexity and boundaries

The localized recovery correction reuses the existing versioned ORM repository and retry policy, adds no API/schema change, and publishes live notifications only after durable success. It does not solve multi-instance startup ownership; committing status and event atomically closes the previously separate-persistence gap, not every crash/replay case. This is a narrow A-path correction, not validation of Candidate B.

## Falsifiable regression and observed result

The concurrent-scan regression selects a `RUNNING` Discovery row, transitions it to `COMPLETED` before recovery writes, then asserts no terminal regression, pause event, or recovered count. A second transaction-failure test verifies that status/event remain unmodified when persistence fails before commit. PostgreSQL must validate versioned concurrent update behavior; SQLite alone cannot establish production DB parity.

The implementation now snapshots the exact scanned status, guards the update through the existing versioned ORM, appends the pause event in the same transaction, and publishes live projections only after commit. The added concurrent-terminal test captures the previously reproduced regression; both new tests pass on the corrected code. Focused SQLite suite: **15 passed**. PostgreSQL runtime and two-process test are **BLOCKED / NOT RUN** because no local PostgreSQL/Docker tools were available; do not claim the recovery change fully verified.

## Lead synthesis (not a vote)

1. **KEEP** Candidate A as the current operating architecture; retain all existing runtime/provider/browser owners.
2. **REFACTOR** the narrow, reproduced Discovery recovery regression inside the existing repository/service boundary. No schema or API changes.
3. **DEFER** Candidate B's cross-domain normalized contracts until a measured operational consumer/failure, source-of-truth/rollback design, PostgreSQL parity, and additive migration proof exist.
4. **DEFER** LangGraph, Browser Use and Skyvern production dependencies. A same-task Browser Use/Skyvern experiment is an optional next gate only if a concrete unmet browser requirement justifies it; Skyvern additionally needs legal review and service/dependency isolation.
5. Architecture Gate remains **DEFERRED / NOT PASSED**. Source research updates a portion of the evidence but does not satisfy the comparative PoC, PostgreSQL/multi-process, real-provider/approval, legal, or human decision gates.

## Disagreement and next falsifier

The earlier provisional Candidate B recommendation is weakened by the Critic's evidence challenge; the available source assessments agree that lifecycle representation fragmentation exists, but differ on whether it warrants a broad change now. This is an unresolved product/architecture question—not a vote. The smallest next falsifier is a disposable PostgreSQL race/failure-injection test for the local recovery fix, followed by an observed user/support requirement that cannot be met by the existing domain records. Only then reopen B's design. One formal round used; no second round is currently required.
