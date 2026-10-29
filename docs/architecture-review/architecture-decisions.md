# Architecture Decisions and Gate

**As of:** 2026-10-28<br>
**Decision state:** **PROVISIONAL / GATE DEFERRED**. The later bounded source pass verified release/license/manifest metadata for the three P0 candidates, but not their runtime compatibility, comparative PoCs, or legal applicability. No candidate is selected or approved for production. See [`framework-p0-verification-2026-10-28.md`](framework-p0-verification-2026-10-28.md) and the independent challenge in [`architecture-debate-2026-10-28.md`](architecture-debate-2026-10-28.md). A local Discovery recovery bug fix does not pass this architecture gate.

## ADR-001 — Evolve the existing platform toward candidate B incrementally

- **Status:** Proposed; not closed at Phase 5 gate.
- **Context:** The repository already has React/FastAPI, repository and provider seams, persisted `TaskRuntimeService`, `BrowserRuntime`, `DecisionService`, deterministic Pytest execution, WorkerDaemon, approval, evidence, and desktop workflow. Material gaps are lifecycle/event/evidence fragmentation and conservative recovery, not a demonstrated inability of the underlying stack to scale. Discovery has a persisted domain row and live implementation but still carries process-local execution/session/event state. The initial comparison was blocked; a later source pass verified P0 tag/license/manifest metadata only. No candidate runtime comparison, platform compatibility test, or legal applicability review is complete.
- **Decision proposal:** Retain the current stack (candidate A as the immediate operating baseline) and target candidate B only through additive redesign of event/evidence contracts, task ownership/recovery, and adapter boundaries. Keep `TaskRuntimeService` as the single workflow/scheduler owner; keep `BrowserRuntime` as the sole Playwright owner; keep `DecisionService` and existing provider registries. Do not directly introduce LangGraph, Browser Use, Skyvern, Stagehand, Midscene.js, OpenAI Agents SDK, CrewAI, Microsoft Agent Framework, Dify, n8n, or LiteLLM now.
- **Consequences:** Smaller migration surface and deterministic local execution remain. Reliability improvements still require schema/API compatibility, worker lease/recovery tests, per-job security isolation and real DB parity validation. Framework-level interruption/checkpointing may be revisited only if an existing-contract PoC demonstrates a measurable unmet need.
- **Rejected alternative:** Replace the system or orchestration core wholesale because a framework is popular or offers a visual workflow. There is no evidence of a feature or reliability gap that requires that cost.
- **Revisit when:** the remaining eight framework records are source-checked if they remain candidates; the P0 dependency graphs are resolved against Python 3.13/FastAPI/Playwright 1.62.0; comparative browser and real restart/approval behavior are tested; and target contracts/migration/rollback receive human approval.

## Three target architecture candidates

### A — Retain current architecture and optimize locally (baseline)

- Keep current React/FastAPI service boundaries, SQLAlchemy persistence, `TaskRuntimeService`, Discovery service, `TestRunService`/WorkerDaemon, `BrowserRuntime`, `DecisionService`, providers and Pytest/Playwright paths.
- Improve each existing module in place; retain task cursor/events and Discovery's current persisted result/live route. Do not add a common execution envelope, new orchestration service, framework, queue, or new browser owner.
- **Advantages:** lowest immediate migration and deployment risk; preserves proven workflows and data; least added runtime/token cost.
- **Trade-offs:** lifecycle/recovery semantics remain inconsistent across Task, TestRun/Worker and Discovery; cross-workflow event/evidence queries and replay remain adapters; scaling/removing process-local Discovery state requires local bespoke changes.
- **Use when:** keeping change small is more important than cross-workflow consistency, or B's contract parity/rollback cannot be proven.

### B — Preserve the stack; converge execution lifecycle and evidence contracts (recommended, conditional)

- Retain all existing components and assign `TaskRuntimeService` the single durable workflow/scheduler ownership boundary. Keep Discovery, browser, generation, failure-repair and test-run capabilities as bounded services/tools; no second Runtime/Agent/Provider.
- Add an additive versioned execution/event/evidence mapping, explicit child-run links, idempotent claims/leases and effect-aware recovery. Keep existing tables/API fields as compatibility readers/writers until parity is proven. `BrowserRuntime` remains the only Playwright owner; deterministic Pytest remains verdict authority.
- **Advantages:** addresses the observed mismatch at the lifecycle boundary, enables consistent replay/provenance and safer recovery without replacing frontend, APIs or execution engines; local mode stays available.
- **Trade-offs:** requires careful multi-database migration, compatibility adapters, scheduler race/crash tests and security work; may add complexity before it reduces duplication. Does not itself make external/browser side effects atomic.
- **Use when:** Phase 5 contract/PoC evidence confirms that state/recovery fragmentation is a meaningful problem and additive migration is reversible.

### C — Replace orchestration and browser/test lifecycle with a new agent/workflow platform

- Establish a new orchestration center, e.g. a graph/role framework plus a browser-agent service and separate event/checkpoint store; bridge or gradually replace current Task Runtime, Discovery scheduler, worker jobs, browser adapter and workflow projections.
- This is a **class of architecture**, not an approved specific stack. LangGraph, Browser Use, and Skyvern release/license metadata are now verified at the cited tags; they are not selected, compatibility-tested, or legally assessed for a specific use. Other candidates remain unverified. React/FastAPI could remain as UI/API façade, or a selected platform could own workflow authoring and execution; that ownership would require a separate gate before implementation.
- **Advantages:** clean-slate opportunity to align orchestration and agent abstractions; may accelerate capabilities unavailable in current services if a pinned stack proves fit.
- **Trade-offs:** highest migration, data and runtime risk; can create two sources of task, approval, event, evidence, browser session and verdict state; remote/model/vendor coupling, deployment/security burden, and loss of deterministic local test behavior must be measured. A framework checkpoint cannot atomically commit Playwright, filesystem, Pytest, and DB effects.
- **Use only when:** measured user/scale requirements cannot be met by B; complete comparative PoCs, legal approval, API/data migration and fallback plan exist. Current evidence does not justify C.

### Relative boundary summary

| Concern | A | B | C |
|---|---|---|---|
| Workflow owner | Existing per-domain services, Task Runtime for registered tasks | One platform-owned Task Runtime; domain services are tools/children | New external/third-party orchestrator or replacement runtime (not selected) |
| Browser owner | Existing `BrowserRuntime` | Existing `BrowserRuntime` behind a stable capability contract | Candidate browser-agent stack may own sessions unless an adapter proves otherwise |
| Test verdict | Pytest execution records | Pytest execution records | Must remain Pytest/human-evidence based; agent output cannot be verdict authority |
| State/evidence | Existing domain schemas | Additive normalized mapping plus legacy compatibility | New platform store and data synchronization/migration |
| Deployment | Current local/API/worker profile | Current profile plus DB-level claims/contracts | Additional services/queues/stores possible; exact stack unknown |
| Change posture | Optimize in place | Incremental refactor | Broad replacement/rewrite |

## Candidate scoring

Scale: **1 = poor, 5 = strong**. For maintenance cost, development cost, resource/token cost, and migration risk, a higher score means lower cost/risk. Scores are qualitative architecture judgments from current source, not measurements; equal weighting is used to make trade-offs visible.

| Dimension | A — retain and optimize | B — keep stack, redesign core lifecycle | C — whole-system redesign | Evidence/rationale |
|---|---:|---:|---:|---|
| Functional completeness | 3.8 | 4.3 | 3.5 | Existing product paths cover most workflows; B can close cross-lifecycle consistency. C risks feature regression during rebuild. |
| Reliability / recoverability | 3.3 | 4.4 | 4.2 | Task recovery is conservative and events durable; Discovery/browser/session recovery is weaker. B targets that seam without replacing execution. C could improve in theory, not evidenced. |
| Extensibility | 3.2 | 4.5 | 4.6 | Current fixed tools/service surface is broad but extensible at ports. B formalizes contracts; C could maximize clean-slate flexibility. |
| Maintenance cost | 3.1 | 3.7 | 3.0 | A leaves lifecycle mismatch and large services. B adds contracts/migration complexity before reducing duplication. C creates two systems during migration. |
| Development cost | 4.7 | 3.2 | 1.8 | A is incremental; B needs tests/backward compatibility; C requires broad reimplementation and migration. |
| Runtime / Token cost | 4.8 | 4.3 | 2.2 | A/B can retain local execution and make model calls optional/advisory. C adds infrastructure/framework/model costs unless proven otherwise. |
| Migration risk | 4.9 | 3.6 | 1.0 | A minimizes data/API change. B is manageable if additive. C touches all workflows and existing data. |
| Test reproducibility | 4.5 | 4.7 | 3.4 | Existing local SQLite, Pytest and BrowserRuntime fixture seams are strong. B can standardize evidence and recovery. C risks nondeterministic agent/infra behavior. |
| **Equal-weight mean (descriptive)** | **4.04** | **4.09** | **2.96** | B leads narrowly and is conditional; A remains the current safest implementation baseline. |

### Score interpretation

The 0.05-point difference between A and B is not a statistical result. If migration/API compatibility evidence cannot support B cheaply, remain at A. Candidate C is not recommended without a business driver that current modules cannot meet.

## Architecture gate choices

These are provisional disposition labels, not code-change approval.

| Area | Gate proposal | Evidence / boundary |
|---|---|---|
| React, FastAPI, SQLAlchemy, shared project models/config | **KEEP** | Existing working boundaries, no comparative evidence favors replacement. |
| `TaskRuntimeService` and registered task workflows | **KEEP / REFACTOR** | Persisted tasks/steps/events/approval exist; improve cross-run ownership, leases, idempotency and recovery without a second scheduler. |
| `TestRunService`, `PytestRunner`, `WorkerDaemon` | **KEEP / REFACTOR** | Deterministic exit-code verdict and distributed execution are core; strengthen sandbox/lease/recovery after security design. |
| `BrowserRuntime` / Playwright adapter | **KEEP** | It is the existing port and the only application-owned Playwright lifecycle. No competing browser adapter passed a PoC. |
| `DecisionService`, `AIService`, current provider registries | **KEEP** | Separate capability contracts already exist; custom OpenAI-compatible URL is supported. Do not add a third provider layer. |
| Recorder, debugpy debugger, failure/locator repair | **KEEP** | Existing user behavior and approval/proposal state are valuable; preserve until alternate path meets same acceptance. |
| Quality Discovery | **KEEP / LOCAL FIX ONLY; DEFER convergence** | The reproduced startup-recovery race is fixed locally using existing versioned ORM state and no schema change. Broader execution ownership/event/evidence convergence remains Candidate B and is not authorized by the deferred gate. |
| Task / TestRun / Discovery event and Evidence representations | **DEFER normalization** | Candidate B proposal only; no versioned cross-domain contract/schema change until a measured consumer/failure, PostgreSQL/multi-process parity, compatibility and rollback evidence, and human gate decision exist. |
| `packages/qa-core/qa_core/explorer/BrowserExplorer` | **DEFER removal** | Source is hard-coded, unused internally, and exported. Confirm package consumers and deprecation policy before any removal. |
| Candidate third-party frameworks | **DEFER** | P0 tag/license/manifest metadata is now source-verified; no runtime compatibility, legal-use review, or candidate benchmark has passed. Other eight candidates remain unverified. |
| Full-system rewrite / new queue broker / new workflow service | **REJECT for current evidence** | Adds migration/operational complexity without proven requirements. Revisit only with measured need. |
| Destructive schema changes/removal of legacy states/features | **DEFER** | Preserve user data and compatibility; no proven migration/rollback evidence. |

## Gate status and unresolved conditions

**Phase 5: DEFERRED / NOT PASSED.** Reasons:

1. Official source metadata is verified for the three P0 candidates only; eight other candidates remain unverified. Metadata and MIT/AGPL license identifiers do not establish project dependency compatibility or legal applicability.
2. PoC B only exercised the existing Playwright adapter on a controlled loopback site; Browser Use and Skyvern were not installed/run. No comparative locator success, failure recovery, token cost, or timing data exists.
3. PoC C did not complete AI-generated scenario -> real human approval -> generated test -> deterministic Pytest -> evidence. It only verifies existing isolated deterministic execution/approval controls.
4. Existing isolated test evidence does not validate PostgreSQL/multi-instance recovery, full worker crash recovery, real provider behavior, or production security isolation. The new local recovery regression has SQLite evidence only; PostgreSQL remains outstanding.

The gate can be reopened after those evidence gaps are addressed. The qualitative A/B scoring remains a hypothesis, not benchmark evidence; the independent critic recommends keeping A as the operating baseline until a measured consumer/failure establishes B's value. No large-scale production code change, new framework, schema replacement, feature removal, or external provider spend follows automatically from this provisional ADR.
