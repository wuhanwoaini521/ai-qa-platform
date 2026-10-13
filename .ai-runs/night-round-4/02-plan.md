# Plan

1. Add regression tests for `PATCH_READY → BLOCKED(HUMAN_REJECTED)`, legal action changes, durable API behavior, no source mutation, and refusal of Apply after rejection.
2. Extend the existing repair state machine and workflow service using existing `BLOCKED`/`block_reason`; prevent trusted-proposal reconciliation from reopening a rejected state. Revalidate transitions under a row lock.
3. Add the API command and additive response contract, regenerate OpenAPI/TypeScript with the existing exporter, and centralize the web request in `api/client.ts`.
4. Replace the local-only Ignore button with a persistent Reject action, show the stored decision in the proposal and failure overview, and retain reanalysis as the recovery path.
5. Run focused backend/API and web checks, export/contract checks, lint/build, then exercise a safe isolated reject→reload→Apply-denied browser journey. Do not modify formal source, create a TestRun, call AI/Jev, or touch existing app data.
6. Independently review if Orca is runnable; otherwise explicitly record the exact blocker and keep the verdict non-PASS. Commit the tested source and this round's evidence separately without broad staging.

Acceptance: rejection survives refresh; `APPLY` and `REJECT` are absent after rejection; exact source bytes remain unchanged; apply endpoint rejects; reanalysis remains available; explicit Apply still works on non-rejected `PATCH_READY`; generated API contract is current.
