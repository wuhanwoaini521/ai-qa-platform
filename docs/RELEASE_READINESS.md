# Release Readiness

Assessment at the end of Phase 13.5 (architecture stabilization) and Phase 14 (real-project pilot).
Evidence: `docs/ARCHITECTURE_STABILIZATION_AUDIT.md`, `docs/PHASE_14_PILOT_REPORT.md`,
`docs/PILOT_GAP_ANALYSIS.md`.

---

## 1. Verdict

```text
RC READY   (v1.0.0-rc.1)
```

**Not V1-ready.** Release-candidate criteria (§2) are met; three criteria that would justify calling
this "production proven" are explicitly **not** met (§4) — no real Jira/TestRail/Jenkins write, no
production identity provider, and no browser-driven execution on this machine.

## 2. Release candidate criteria

| Criterion | Status | Evidence |
|---|---|---|
| Real project detected | ✅ | `playwright-test`: `pytest_playwright`, uv, 3 markers, 5 plugins, confidence 1.0, no warnings |
| Real project imported | ✅ | 146 files / 947 KB into an isolated workspace; source tree hash identical before/after |
| Real pytest collected | ✅ | 71 tests / 14 files, `COLLECTED`; broken projects yield `COLLECTION_ERROR`, never "0 tests" |
| Real test identity modelled | ✅ | 71 logical tests mapped; unmapped tests reported, not dropped; 1-function-to-N-cases supported |
| xdist modelled | ✅ | `-n 2` run parsed (68 passed / 1 real failure in the reference project's own test) |
| rerun modelled | ✅ | 2 logical / 4 physical / 2 reruns on a controlled rerun run |
| Allure modelled | ✅ | 4 real result files imported with historyId/labels/parameters |
| Failure pipeline works | ✅ | controller failure → `LOCATOR_CHANGED` + suggestion → AI diagnosis (0.92) → proposal with `applied: false` |
| History works | ✅ | per-test executions with `retry_count`, trend and score components |
| Flaky works | ✅ | 71 scored entries; classification (`STABLE` / `INSUFFICIENT_DATA`) and failure categories |
| Workspace source isolation works | ✅ | read-only source, isolated runtime, isolated artifacts |
| P0 = 0, P1 = 0 | ✅ | Phase 13.5 review findings closed (§3) |
| GitHub Actions green | ✅ | `Backend Lint & Test`, `Backend Tests (PostgreSQL 16)`, `Frontend Lint & Build` |

## 3. Defects closed before this assessment

Phase 13.5 review (P1): SSE stream had no way to send credentials after authorization was enabled;
Projects row actions opened the previously selected project; the `AutomationBinding` contract
divergence made binding saves and every "run test" action fail.

Pilot (P0/P1): `risk-matrix` returned HTTP 500 for any project with flaky tests; the flaky query was
N+1 and made the dashboard 5.5 s at moderate scale; a crashed run stayed `RUNNING` forever; test
selection could inject pytest flags.

## 4. Why this is not "V1 production proven"

1. **No live external write.** Jira bug creation, TestRail result publishing, GitHub PR creation and
   Jenkins triggering were verified only in preview/dry-run or against a fake server. The platform
   refuses to claim otherwise (`docs/PILOT_GAP_ANALYSIS.md` §4).
2. **No production identity provider.** Sessions are HMAC-signed bearer tokens with expiry; there is
   no SSO/OIDC/SAML integration, and multi-tenancy does not exist.
3. **No browser execution verified.** Every Playwright test in the pilot was refused by safety policy
   (correctly — they drive live websites). Browser execution is therefore unproven on this machine.
4. **Object storage, migrations and multi-process SSE are absent** (gap analysis O3, O5, O6). A
   production deployment must either run a single API instance with local storage, or wait for those.

## 5. What a production operator must configure

| Setting | Why |
|---|---|
| `APP_SECRET_KEY` | signs session tokens; the default must never be used |
| `AUTH_REQUIRED=true` | the default; `false` impersonates the seeded admin and is development-only |
| `DATABASE_URL` (PostgreSQL) | SQLite is for development; the suite is verified on both (`backend-postgres` CI job) |
| `AI_QA_AUTH_TOKEN` (worker) | workers must present an API key; without it they receive 401 |
| Change the seeded `admin@ai-qa.local` password | it is created on first login |
| Backups of `runtime/artifacts` | artifacts are local files; see `docs/BACKUP_RESTORE.md` |

## 6. Recommended before a v1 tag

1. Wire the job queue to a producer and let the worker report per-test results (gap O1) — this is the
   single largest functional gap.
2. Adopt Alembic before the first schema change (O5).
3. Vendor Monaco instead of loading it from a CDN (O8).
4. Validate one real Jira/TestRail/Jenkins write against a non-production instance.
5. Add an OIDC provider if the platform will face more than one team.
