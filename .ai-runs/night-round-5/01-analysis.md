# Analysis — night round 5

## Starting point

- Round-four source commit: `652736b`; round-four evidence commit: `b88bead`.
- No paths were staged at the start of round five.
- The worktree contains inherited tracked and untracked modifications across API, web, CI, configuration, docs, generated contracts, and run logs. `mise.toml` is modified and must remain untouched. Those changes are not round-five scope and will not be staged.
- `AI_QA_TEST_DATABASE_URL` and live AI/Jev acceptance flags are unset. The existing local API (8001) and web server (5174) are not ours and will not be used or stopped.

## Validation scope

This is a high-risk final regression because the sequence spans backend state/persistence, generated contracts, the frontend, browser behavior, and an explicit source-write approval boundary. Official project entry points are `pnpm lint`, `pnpm test`, and `pnpm build`; CI additionally checks generated OpenAPI types and has PostgreSQL/Windows lanes.

Golden Journey for this remediation: open a persisted failure proposal, reject it, reload, confirm the stored rejection and reanalysis availability, then confirm Apply is denied and source bytes remain unchanged. This verifies the newly completed critical approval boundary; it does not claim the entire requirement-to-release product workflow was exercised in round five.
