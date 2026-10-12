# overall product UI redesign

- run-date: 2026-10-11
- task-type: ui-redesign
- scale: standard

## Implementation plan
1. **Design tokens and shell** — gently narrow the desktop navigation rail, reduce excess corner/spacing weight, use a token-based pale selected state, and keep the shell surfaces consistent with both themes.
2. **Shared primitives** — slightly compact shared cards and data presentation; replace hard-coded skeleton colors with theme-aware tokens; preserve existing focus treatment and modal action semantics while aligning backdrop/shape with the focused-dialog reference.
3. **Representative Dashboard** — compact the KPI stack and use restrained semantic icon tiles while preserving labels, values, supplementary metrics and existing navigation buttons.
4. **Broader UI review** — use screenshots and route inspection to decide whether shared changes generalize cleanly to Workspace, Projects, Runs, Quality, and Settings; adjust only clearly inconsistent surfaces, not workflow logic.
5. **Verification** — targeted web tests, lint, typecheck/build; browser-check representative light/dark routes at desktop/tablet/mobile, accessibility affordances, overflow, console and request failures. Capture after evidence and record any residual limitations.

## Safety / review gates
- Do not modify `package.json`, lockfiles, runtime data, route definitions or API contracts.
- Do not stage or commit. Do not operate AI providers, recorder, debugger, test execution workflows, job queues or repair actions.
- At each review, compare actual browser state to the screenshot references at the level of hierarchy and visual language; do not claim a complete redesign from dashboard-only evidence.
- If global CSS affects a unique feature view, revert or scope the styling rather than layering compensating overrides broadly.
