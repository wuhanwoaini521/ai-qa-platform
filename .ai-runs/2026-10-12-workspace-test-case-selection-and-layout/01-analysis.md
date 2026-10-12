# Workspace Test Case Selection and Layout

- run-date: 2026-10-12
- task-type: ui-feature
- risk: MEDIUM
- scale: standard

## User Goal and Root Cause
The QA user needs to review one case and move to other cases in the same project without losing the Workspace workflow. In Workspace mode, `TestCasesPage` intentionally omits `TestCaseList`, and the embedded grid becomes one column. The remaining case navigator lives only in the context rail, which is collapsed in the supplied screenshot. The case toolbar hides its title and contains only the right-aligned create button, so it leaves no indication of the active case or an in-page way to switch.

Live evidence at 1524×894: the collapsed-rail page showed `TC-002 · happy_path` detail and only the “New Test Case” toolbar action. The project API returned 11 cases; with the rail expanded it showed only 10 related case buttons (`relatedCases.slice(0, 10)`). At 1280×633 the same page had no visible case selection control and the context rail was collapsed.

There is already a supported selection path in `TestCasesPage.handleSelectCase`, and `WorkspacePage.selectCase(item)` updates case, requirement, design, binding, and clears stale run/debug context. However, the `onSelectTestCase` prop currently accepts only an ID and the Workspace callback updates only `testCaseId`, so the new visible switch should pass the selected `TestCase` through the existing full-context helper.

## Scope and Acceptance Criteria
1. Workspace mode visibly identifies the selected case by stable case ID and title; when multiple cases exist, all project cases are available in an accessible in-page selector.
2. When no case is selected but cases exist, the user can choose one from the same control. A single already-selected case renders identity without an inert dropdown.
3. Choosing another case updates the case detail and URL/context. When its requirement/design differs, that context follows the chosen case and stale execution/debug IDs are cleared.
4. The toolbar has a clear left-side case scope and preserves the existing create action; the full-width detail remains readable.
5. The standalone non-Workspace TestCasesPage keeps its existing list/detail behavior. Empty/loading states and direct case links remain valid.
6. Layout remains usable at desktop, tablet, and phone widths without document-level horizontal overflow; existing light/dark styling is preserved.

## Constraints and Impact
- Reuse existing `TestCase`, selection handler, `selectCase`, and design tokens; no new backend API or persistent data.
- Preserve the previously existing uncommitted requirement-page changes and untracked data.
- No new requirement/case records or AI tasks will be created during verification; read-only live Golden Demo case records may be selected.
- A small selection view model + tests will cover option labels and empty/single/multiple states; live browser will verify the actual route/context transition.
- Risk is MEDIUM because the user-visible selector drives shared Workspace context, although persistence and execution behavior are unchanged.
