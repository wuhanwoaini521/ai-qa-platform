# Regression

- Frontend suite, lint, and production build passed after the changes; targeted API stream and AI trace tests passed (20).
- Browser regression covered automation direct links, workspace stage navigation, the existing context toggle, desktop/tablet/phone layouts, file-tree toggle, live viewport threshold changes, and both provider/non-provider failure badges.
- Existing project data was read only for UI verification. The automation SSE was intercepted in-browser; no automation draft, binding, or run was created.
- Not covered: broader backend/API regression (no backend source changed), full keyboard/accessibility audit, and installing/starting the Python LSP because dependency compilation failed.
