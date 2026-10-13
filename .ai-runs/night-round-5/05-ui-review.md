# UI review — night round 5

## Golden Journey

On the isolated local app: sign in → open the synthetic failed run's failure workspace → review the locator proposal → reject → reload → confirm the rejected state and reanalysis action → verify Apply is denied and the workspace source is unchanged. The browser never invoked AI/Jev or ran tests.

## Coverage matrix

| Route / feature | Priority | Load / action | Result |
|---|---:|---|---|
| Login | P0 | Submit seeded disposable admin login | Passed; API returned 200 |
| QA workspace / failure review | P0 | Open failure, reject, reload, inspect actions | Passed; rejection persisted, Apply/Reject absent, reanalysis present |
| Dashboard | P1 | Navigate and render | Loaded. Aggregate counters were not asserted because the synthetic run bypassed normal terminal aggregation. |
| Projects | P1 | Navigate and render seeded project | Passed |
| Runs | P1 | Navigate and render seeded run | Passed; same fixture-counter limitation applies |
| Other product routes (Studio, Requirements, Quality, Settings, integrations) | P1–P2 | Not exercised in this scoped browser pass | Not verified |

## Browser evidence

- System Google Chrome attached to a private agent-browser session over CDP. The bundled Chrome failed to start because of a macOS VideoToolbox symbol mismatch; system Chrome worked. No user Chrome profile or data was used.
- The Reject request returned 200; page reload showed the persistent rejection message/event. Apply and Reject buttons were absent, and the reanalysis control remained available.
- API verification returned `BLOCKED / HUMAN_REJECTED`, only `START_ANALYSIS`, Apply **422**, and unchanged source bytes.
- Scoped axe 4.12.1 audit of `.failure-repair-proposal`: **0 violations, 0 incomplete**.
- At 1440×900, 768×1024, and 360×800, document/body widths equalled viewport widths; no horizontal overflow.
- Browser page-error output was empty. API page requests after login succeeded; Apply's 422 was expected.

Screenshots, snapshots, axe output, network evidence, and runtime logs are in `evidence/`. This is focused route/flow coverage, not an exhaustive page audit or full WCAG conformance claim.
