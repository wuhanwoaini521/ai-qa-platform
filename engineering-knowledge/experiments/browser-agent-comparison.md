# Browser Agent Comparison — Bounded PoC Protocol

- **Knowledge Status:** DOCUMENTED (protocol and existing-platform baseline recorded; candidate comparison NOT RUN).
- **Topic:** Compare existing BrowserRuntime against Browser Use and Skyvern without replacing the production browser owner.
- **Research Question:** Do either candidates improve deterministic task success, locator stability, failure recovery or evidence completeness on the same controlled page enough to justify adapter work?
- **Source URL(s):** [Browser Use 0.13.14 record](../frameworks/browser-use.md); [Skyvern v1.0.56 record](../frameworks/skyvern.md); existing baseline report [`docs/architecture-review/poc-results.md`](../../docs/architecture-review/poc-results.md).
- **Source Version:** Candidate tags above; platform baseline Playwright 1.62.0. Candidate dependencies remain uninstalled.
- **License:** Browser Use MIT at tag; Skyvern AGPL-3.0 at tag (legal review required before adoption).
- **Verified Date:** 2026-10-28.

## Existing baseline (not a comparative benchmark)

A prior isolated test used a controlled `127.0.0.1` QA Shop fixture with real Chromium/Playwright 1.62.0 and fixture AI/decision. It passed once (1/1, 16.78s process-level test time) and asserted JPEG/frame provenance, geometry, inventory, highlight, persisted state and cleanup. It made zero model calls. This is a real-browser integration test but not an AI-provider success, action success rate, per-action latency, cost measure, or repeated reliability estimate. See `docs/architecture-review/poc-results.md` and `experiments/architecture-review/poc/evidence-2026-10-28.md`.

## Protocol and stop gates

1. **Preflight:** verify pinned candidate version, complete dependency/license graph, Playwright 1.62.0 compatibility and Skyvern legal review. If resolution conflicts, stop; do not install in the product environment.
2. **Isolation:** use a temporary virtual environment/container, disposable loopback-only site and test-only project data. No third-party sites, customer data, production browser profile, remote browser, or default external mutation.
3. **Sample:** identical three deterministic read-only tasks against the same fixture, including navigation/observation, stable locator interaction and evidence capture. The assertion oracle must be deterministic and identical; do not use model judgement for PASS/FAIL.
4. **Systems:** current `BrowserRuntime`; Browser Use local agent + local browser if supported; Skyvern only in an isolated local SDK/server profile. Every system must use the same browser/version and equivalent model/provider or local model. If equivalent model/backend is unavailable, label comparison confounded and do not rank.
5. **Bounds:** max 3 tasks/system, max 2 attempts/task, max 60s/task, one browser session/task; explicit human-approved provider spend cap before any external call. Default is no paid/provider calls; if no shared local model is feasible, defer rather than substitute different models.
6. **Measure:** deterministic assertions passed/failed; wall-clock task time; model/provider identity; prompt/completion tokens and actual billed cost when available; browser start overhead; locator changes across repeated DOM variants; recovery after a forced navigation/browser failure; evidence IDs/files/hash/source linkage; process/resource cleanup.
7. **Report:** exact environment, commands/exit codes, raw non-sensitive outputs, fixture commit/hash, version/license, deviations and unknowns. Do not report a success percentage from one attempt or claim model success from a fixture.
8. **Decision:** compare against pre-declared thresholds and current baseline. Any proposed adapter remains behind existing `BrowserRuntime`/`TaskRuntimeService` boundaries and requires independent review plus architecture/legal gates.

**Current status:** candidate comparison NOT RUN. No packages installed, no cost incurred. The architecture gate remains DEFERRED / NOT PASSED.

- **Limitations:** current baseline is a single fixture test with fixture decisions; no repeated samples. Skyvern license/legal obligations and runtime compatibility are not approved. Browser Use transitive browser dependency is not established.
- **Applicability:** research only; never a production BrowserRuntime replacement by this protocol.
- **Evidence:** existing baseline source/output as linked above; protocol is not itself experiment evidence.
- **Confidence:** High that the existing test asserts the listed fixture behaviors (source/test record); Low for all candidate comparison outcomes.
- **Related Projects:** AI QA Platform; BrowserRuntime; Browser Use; Skyvern.
- **Next Review Condition:** Run only after dependency and legal preflight passes and an explicit bounded provider/resource cap is recorded.
