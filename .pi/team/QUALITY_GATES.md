# Quality Gates

Mark each gate `PASS`, `FAIL`, `SKIP`, `BLOCKED`, `NOT TESTED`, or `N/A`, with command/evidence. A skipped, unavailable, or untested gate is never a pass.

## Product / acceptance gate

- User, pain, value, existing capability, MVP boundary, explicit non-goals and falsifiable criteria recorded.
- No unapproved product direction, scope expansion, external write, or production action.
- Backlog status advances only after its actual stage gate; implementation alone is not `DONE`.

## Frontend gate (when applicable)

- Relevant `pnpm --filter @ai-qa/web test` tests.
- `pnpm --filter @ai-qa/web typecheck`, `pnpm --dir apps/web lint`, and `pnpm --filter @ai-qa/web build` for changed UI or shared front-end code.
- i18n and `git diff --check` when relevant.
- Real browser interaction on desktop at 1440×900; also 1280×800 and 1920×1080 when layout changes. Use named `agent-browser` session or pinned Playwright 1.62.0. Browser screenshots prove rendered state only; click/keyboard/API observations prove separate behavior.
- Review Graphite design fidelity where that direction is active, states, keyboard focus, labels, and no document overflow. Design Director sign-off is independent from functional QA.

## Backend / API gate (when applicable)

- Contract/OpenAPI check, relevant Pytest, authorization/negative access, error path, persistence/transaction consistency, and integration smoke.
- Reuse existing services/repositories. No UI-driven semantic changes or fabricated success.

## Runtime / asynchronous task gate (when applicable)

- Real state transitions, timeout, cancellation, retry/recovery, resource cleanup, SSE/event truth, and a real isolated execution artifact.
- Use a disposable isolated fixture/database; never treat static fixture or fake run as real execution evidence.

## AI repair gate (when applicable)

- Real failure context and actual provider availability; explicitly label any mock/offline result.
- Analysis and proposal remain separate; patch preview/diff before application; explicit human approval before any code mutation.
- Exact test/node verification and durable evidence after approval. AI never changes deterministic test verdicts.

## Review / integration gate

- Independent reviewer uses a different fresh context, receives original task + acceptance + diff + results, and reports severity/evidence.
- Release Engineer confirms changed-file scope and protects existing user changes; checks build/regression evidence and rollback risk. No commit/push/merge/deploy without separate authorization.

## Design gate

- Graphite Developer Studio remains the approved direction on Dashboard and Workspace Debug/Explore. For the user-authorized task `.ai-runs/2026-10-27-graphite-fidelity-recovery/00-request.md`, it also applies to Projects, Requirements, Test Explorer, Write Tests, Results, AI Repair, and Quality; other routes remain out of scope. Use existing page content/actions and tokens without inventing IA.
- Desktop-first only: 1280×800, 1440×900, 1920×1080. Mobile-specific work/checks are OUT OF SCOPE.
- Before/after desktop screenshots and actual interaction evidence are distinct. Review hierarchy, text, density, panel allocation, focus, and loading/empty/error/ready states.
- Visual PASS does not imply functional PASS, and functional test PASS does not imply visual PASS.
