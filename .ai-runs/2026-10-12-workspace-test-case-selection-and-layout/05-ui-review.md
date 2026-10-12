# UI Review — Workspace Test Case Selection and Layout

## Viewports and themes
- Reviewed 1524×894 desktop, 768×1024 tablet, 390×844 phone, and 360×800 narrow phone.
- Reviewed light mode at desktop/tablet/phone and dark mode at desktop.
- `document.documentElement.scrollWidth` matched viewport width at all tested sizes (1524, 768, 390, 360); no document-level horizontal overflow.

## Findings
- The toolbar now identifies the current case by ID and title and exposes all project cases without requiring the user to expand the context rail. The create action remains visible and moves below the selector on narrow layouts.
- Case details retain their full-width workspace presentation. At phone widths, action controls wrap without obscuring the selected case or detail.
- Native selector is announced as a combobox named `当前用例`; its focus-visible style is present (2px blue outline plus focus shadow).
- Scoped axe-core 4.12.1 check on `.workspace-case-toolbar`: **0 violations**, 12 passes, 0 incomplete. This is a scoped control check, not a complete WCAG audit.

## Severity and conclusion
- P0: none.
- P1: none.
- P2: none.
- Review conclusion: toolbar hierarchy, selection affordance, responsive wrapping, and light/dark presentation are acceptable for this change.
