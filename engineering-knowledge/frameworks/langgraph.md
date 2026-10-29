# LangGraph — P0 framework record

- **Knowledge Status:** VERIFIED for tag/release/license/manifest/docs metadata only; platform behavior and compatibility are NOT TESTED.
- **Topic:** Stateful graph orchestration, checkpoint persistence, interruption and human input.
- **Research Question:** Does a graph framework close a proven durability/approval gap beyond this platform's existing Task Runtime, and what version/license constraints apply?
- **Source URL(s):** [latest release metadata](https://api.github.com/repos/langchain-ai/langgraph/releases/latest); [release 1.2.18](https://github.com/langchain-ai/langgraph/releases/tag/1.2.18); [tagged README](https://github.com/langchain-ai/langgraph/blob/1.2.18/README.md); [tagged package manifest](https://github.com/langchain-ai/langgraph/blob/1.2.18/libs/langgraph/pyproject.toml); [tagged LICENSE](https://github.com/langchain-ai/langgraph/blob/1.2.18/LICENSE); [official persistence docs](https://docs.langchain.com/oss/python/langgraph/persistence); [official interrupts docs](https://docs.langchain.com/oss/python/langgraph/interrupts).
- **Source Version:** 1.2.18, published 2026-10-26 (GitHub latest-release endpoint, retrieved 2026-10-28).
- **License:** MIT at tag 1.2.18. This is source identification, not a repository-wide legal opinion.
- **Verified Date:** 2026-10-28.

## Findings

- The tagged manifest declares Python `>=3.10` and depends on `langgraph-checkpoint>=4.3.0,<5.0.0`; its package set includes checkpoint integrations for SQLite and PostgreSQL. This makes Python 3.13 a declared version-range fit, not a tested project integration.
- The official persistence docs describe thread-scoped graph checkpoints, separate cross-thread stores, PostgreSQL and SQLite savers, and warn that in-memory savers do not survive process restart.
- Official interrupt docs describe pausing at `interrupt()` with a durable checkpointer and thread ID, then resuming with `Command(resume=...)`. Critically, resumption restarts the containing node from its beginning; side effects before an interrupt must be idempotent or moved after the interrupt.
- LangGraph is an orchestration library; model charges, checkpoint storage/operations, and any hosted LangSmith services are separate cost centers. No measured cost is available here.

## Limitations

No package was installed, no project dependency resolution or test ran, and no Python 3.13/PostgreSQL/process-restart behavior was independently exercised. Documentation claims do not establish atomicity with Playwright, filesystem changes, Pytest subprocesses, or this project's DB. No token cost, throughput, or reliability comparison exists.

## Applicability

The checkpoint/interrupt design is a useful reference for the existing `TaskRuntimeService` approval, pause, persisted step, and recovery semantics. Directly embedding it would create a second orchestration/checkpoint owner unless an approved adapter proves one durable source of truth. Current recommendation: **DEFER adoption; borrow patterns only**. Existing Candidate A remains the safe implementation baseline; Candidate B is still provisional and the Architecture Gate remains DEFERRED / NOT PASSED.

- **Evidence:** GitHub API release/license metadata and files at tag 1.2.18; official docs pages read on 2026-10-28; existing source review [`docs/architecture-review/current-state.md`](../../docs/architecture-review/current-state.md); no executable LangGraph PoC.
- **Confidence:** High for release tag, license file, declared `requires-python` and cited docs text; Low for practical platform compatibility/value.
- **Related Projects:** AI QA Platform; Python agent/orchestration systems.
- **Next Review Condition:** Recheck the latest release/tag before any PoC or dependency decision; only PoC if a measured Task Runtime recovery/approval gap cannot be closed locally; require restart/duplicate-side-effect tests and legal/dependency review.
