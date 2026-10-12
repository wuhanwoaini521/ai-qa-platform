# Code review — second pass

## Method

No independent reviewer executable (`orca-cli`) is available in this environment. Following the delivery review protocol, I switched to a serial reviewer perspective and re-read the final diff, draft transformer, endpoint, Recorder generator, Task code-generation validators, UI callback, and integration tests after implementation. Challenge prompt: **“Find concrete reasons this implementation should not be accepted yet.”**

## Findings and dispositions

1. **P1 found and fixed — search action could silently degrade to a click.** A Discovery `search` mapped to a non-text control would have produced an incomplete replay rather than being rejected. Changed this to fail closed, added malformed observed-controls validation, and added rejection assertions. Re-ran Discovery tests and the full suite afterward.
2. **No remaining P0/P1 blockers.** The draft transformer requires a completed run, unique graph edge, a unique successfully executed/state-changing action, target fingerprint match, persisted source/destination evidence, and a stable visible/enabled observed control. It rejects unsupported transitions and requires an observed, safe final heading/title assertion.
3. **Security and write boundary.** The endpoint explicitly requires `AUTOMATION_EDIT`; it derives project/workspace from the persisted run and calls existing `TaskCommandService`, which verifies the project/workspace relationship and assigns the current user as task owner. Generated steps carry no top-level URL or recorder session and set `max_ai_calls=0`; the existing task approval gate remains the only workspace-write path. Tests verify no file before approval or after rejection, then a successful write/run after explicit approval. No browser action policy or execution kernel was relaxed.
4. **Assertion policy.** The explicit internal `assertion_bypass_check` marker invokes the existing goal-test validator both before artifact creation and during source validation; a constant-true assertion is rejected. The marker is set only by the Discovery draft constructor.
5. **Compatibility and duplication.** `quality_discovery_service.py` remains the composition/import compatibility surface. The proposal uses existing `RecorderStep` generation and Task Runtime; `select_by_value` defaults false, preserving older label-based recordings.
6. **Error handling and limits.** User-selectable missing/unsafe/non-replayable evidence is returned as a 422; malformed observed controls fail closed. Query/fragment/credential-bearing or non-allowlisted start URLs and unsupported action types are intentionally refused rather than guessed.
7. **Authorization model note (P2 / existing platform boundary).** The repository's authorization is global role-permission RBAC; it does not implement per-project membership authorization. This route adds no broader permission than `AUTOMATION_EDIT`, and the Task Runtime validates project/workspace existence and association. Per-project tenancy enforcement would be a platform-wide policy change, not added only for this endpoint.

## Review result

The one replay-fidelity blocker found in review was fixed and verified. No unresolved correctness, safety, compatibility, regression, or security blocker remains. Non-blocking limitations: conservative refusal of some URLs/actions; global role-level RBAC follows the existing platform model; no independent reviewer process was available.
