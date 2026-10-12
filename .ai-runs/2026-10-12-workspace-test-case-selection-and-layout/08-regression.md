# Regression — Workspace Test Case Selection and Layout

## Coverage
- Full Web unit suite (122 tests) passed, including existing Workspace context and runtime models.
- Lint and TypeScript checks passed; production Web build completed.
- Live Workspace flow selected two real project cases in succession and restored the original case. URL, case detail, test-design ID, and automation-binding ID stayed synchronized.
- A direct legacy test-case URL still redirects to Workspace with the requested case selected.
- Verified collapsed context rail, case selector visibility, create action, responsive wrapping, light/dark themes, focus-visible state, and no document-level overflow at desktop/tablet/phone widths.
- Scoped axe check of the changed toolbar found zero violations. No API/backend/data model/persistence code was changed.

## Outcome
No regression observed. The available live project has 11 cases, all under the same requirement; cross-requirement switching was not exercised with separate live records. The code uses the existing full-context `selectCase` path, and design/binding changes were confirmed live. Single/empty case boundary states are covered by automated model tests.
