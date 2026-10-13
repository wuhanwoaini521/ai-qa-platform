# UI review — night round 4

## Outcome

The former local-only **Ignore** control is now an explicit persisted **Reject proposal** action. The proposal remains visible for audit/history, clearly shows **Rejected**, states that no source changed, and offers a fresh analysis rather than Apply. The Apply control remains hidden after rejection.

## Browser evidence

- Actual Vite + FastAPI UI, system Chrome, synthetic failure in a disposable SQLite instance.
- Clicked Reject, observed the real POST response 200, then reloaded and confirmed the persisted rejection and absence of Apply/Reject actions.
- Tested 1440×900, 768×1024, and 360×800; document/body widths equalled each viewport (no horizontal overflow).
- `axe-core 4.12.1` scoped to the proposal card at 360 px: 0 violations, 0 incomplete.
- Browser page-error output was empty. A live network check showed the reject request succeeded.

Visual evidence: `evidence/proposal-before.png`, `evidence/proposal-rejected-before-reload.png`, `evidence/rejection-persisted-desktop-1440.png`, `evidence/rejection-persisted-tablet-768.png`, and `evidence/rejection-persisted-mobile-360.png`.

This is a focused workflow/UI check, not a full application UX audit or WCAG conformance claim. The axe run was scoped to the changed proposal card; pre-existing whole-page contrast coverage remains carried forward from round 3.
