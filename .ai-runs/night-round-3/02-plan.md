# Plan

1. Make the existing horizontally scrollable ordered list keyboard-focusable without changing its visual layout or workflow behavior.
2. Recheck the real app at desktop (1440px), tablet (768px), and mobile (360px); verify keyboard focus and arrow-key horizontal scrolling, axe findings, and document overflow.
3. Run relevant frontend tests, typecheck, lint, and production build; review only this round's source diff while preserving existing changes.
4. Record evidence and classify only the passing round-three source change; do not stage prior work or `mise.toml`.

Acceptance: the list is in sequential keyboard tab order and can be scrolled with the keyboard when overflowing; no new axe violations or layout overflow; all affected checks pass. Human approval behavior and source-write boundary remain unchanged.
