# Code review and safety pass

## Review method

Same-agent second pass over the complete scoped diff and connected callers/tests; **not an independent review**. Checked `resolveStudioRunTarget` callers and precedence, all run request fields and retry construction, embedded/standalone selector props, stage rail CSS breakpoints, timestamp callers/tests, and the existing human approval boundary.

## Findings

- No blocking correctness or source-write issue found in the scoped changes.
- Run target remains deterministic: explicit Test Explorer node → selected case binding → active file. `nodeids` stays a singleton for a selected test; the existing no-target guard remains.
- Run configuration is optional for standalone callers. Only ordinary configured runs add the workspace fields; retries omit the current dock settings and retain the original run's configuration/parent/failure context.
- The project selector's select is hidden only when `embedded` is true; Quick Open is still a real labeled button. No action was added that applies a repair or writes a source file.
- Timestamp validation is a small formatter with missing, invalid, and valid cases covered. CSS changes are constrained to the existing workspace rail and Studio controls; real-browser checks cover the narrow layout and toolbar geometry.
- No API/worker/backend implementation, new runtime/provider/agent, or new AI decision path was introduced.

## Non-blocking observations

- The visible Python language service-unavailable message remains; debugging itself is confirmed paused and usable. This local service issue is outside the diff.
- `pnpm build` still warns that the existing Monaco/editor chunks exceed 500 kB; no bundling change was requested.
- This pass cannot substitute for the unavailable Orca independent review; see `08-independent-review.md`.
