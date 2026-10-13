# Night round 4 — repair workflow completion

Continue from the prior AI + Jev, API/frontend decoupling, and UI/UX work. Complete the known missing human-rejection path for a locator repair proposal, without allowing any source write or test execution on rejection. Preserve all existing local changes and approvals.

## Scope

- Replace the proposal card's transient “Ignore” action with a persisted, explicit human rejection.
- Record the rejection in the existing repair state/workflow, make the rejected proposal non-applicable, and permit a later new analysis.
- Keep explicit Apply as the only source-write path; verify a rejected proposal cannot be applied through the API.
- Preserve existing runtime, service, provider, transaction, test-verdict, and rollback boundaries. Do not remove dependencies or tests without evidence.
