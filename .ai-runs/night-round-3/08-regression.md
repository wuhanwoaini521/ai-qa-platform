# Regression — night round 3

- Web suite: 146 passed.
- TypeScript: passed using the package's direct pnpm command after RTK incorrectly routed the filtered command.
- ESLint and production build: passed; existing Monaco chunk advisory remains.
- Real browser: failure/results workspace verified at 1440×900, 768×1024, 360×800; document widths matched viewports; target axe violation absent at all three sizes; keyboard arrow scrolling verified at mobile and tablet.
- No backend or OpenAPI behavior changed, so API suites were not repeated in this UI-only round. The final round must run the complete regression after all planned modifications.
- Inherited blockers remain carried forward: PostgreSQL lane unavailable in earlier rounds; Orca independent review currently unavailable; full cross-platform/browser matrix is not evidenced.
