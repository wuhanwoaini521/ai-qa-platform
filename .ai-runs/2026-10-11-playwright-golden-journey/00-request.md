# Request

Deliver a real, repeatable e-commerce Playwright QA journey using the existing Northstar Demo Shop and platform lifecycle. Create platform-backed project/requirement/test-case records through the API/UI, use the configured real AI and Jev providers, generate automation, execute it with a Worker, retain browser evidence, exercise failure analysis/approval/repair/retest branches, run a genuine AI+Jev browser task, validate the platform UI, run regression checks, and publish `docs/audits/playwright-golden-journey-acceptance.md`.

## Constraints
- Preserve all existing database records, credentials, queue jobs, runtime workspaces/artifacts, and uncommitted user changes.
- Never reset the DB or run a Worker against jobs with unknown intent. Do not delete acceptance data.
- Do not fabricate AI/Jev outputs. Report unavailable providers or incomplete checks accurately.
- Keep the existing Northstar Demo Shop and platform as the system under test; no unrelated backend/UI redesign.
- Do not stage, commit, or push.
