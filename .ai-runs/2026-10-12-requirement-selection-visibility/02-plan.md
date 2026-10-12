# Implementation Plan — Requirement Selection Visibility

## Design direction
- **Palette:** reuse existing `--surface`, `--line`, `--ink`, and `--accent-blue` theme tokens; add no new colors.
- **Typography:** preserve the Workspace toolbar's existing compact 11–12px label/control hierarchy.
- **Layout:** add a left-aligned “Current requirement” scope to the existing toolbar row. Show a static ID + title for a single-item project; use a native select with ID + title options for multiple items. Keep existing actions right-aligned; stack scope and actions on narrow screens.
- **Principles:** make active scope apparent without expanding the context rail; use the existing requirement ID and title rather than invented copy; keep the implementation quiet and consistent with current Workspace controls.

## Self-review
This is intentionally a small information-hierarchy change, not a new visual component system. Reusing the toolbar, current display IDs, theme tokens, and standard select behavior better fits this QA workspace than adding a card, new color treatment, or decorative badge. The label and full title are included to avoid making users infer scope from the details panel.

## Steps
1. Add localized label text and render the active requirement identity in `RequirementsPage` workspace mode.
2. For multiple requirements, wire the native select to the existing `handleSelectRequirement` callback.
3. Add responsive toolbar styles using existing design tokens.
4. Run frontend targeted tests, lint, typecheck/build, then inspect the live page at desktop/tablet/mobile and light/dark modes; verify keyboard focus and switching if a safe multi-requirement fixture is available.
5. Review the final diff and report any verification limitation.
