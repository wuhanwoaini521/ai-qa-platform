# Plan

1. Collapse the existing workspace context panel when the current stage is automation; keep the header toggle usable and leave other stages unchanged.
2. At narrow phone widths, collapse the embedded Studio file explorer by default and cap its width when reopened; keep the existing file toggle available.
3. Make the AI timeline label provider unavailability only for structured provider-failure reasons, make generic operation-failure advice provider-neutral, and cover both cases in tests.
4. Confirm the Python language server warning against the declared API dependency and current runtime.
5. Run the focused frontend tests, typecheck, lint, and build as available.
6. Inspect the diff independently and verify the running UI at desktop, tablet, and phone widths, including the failure badge.
7. Record verification and acceptance evidence without altering pre-existing user changes.
