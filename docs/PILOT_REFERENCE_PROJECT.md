# Pilot Reference Project — `playwright-test`

Phase 14 pilots the platform against a real QA repository on this machine. The platform's own docs
already designate it: `docs/QA_CORE_MIGRATION_AUDIT.md` audits "the legacy QA framework located at
`../playwright-test`".

> **Read-only.** The reference repository is never modified, never committed to and never executed in
> place. The pilot imports a copy into an isolated workspace and runs everything there. Verified by
> hashing the source tree before and after the import (identical aggregate SHA-256).

---

## 1. Discovered candidates

| Repository | Verdict |
|---|---|
| `/Users/hans/Code/github/playwright-test` | **selected** — mature pytest + Playwright POM framework, uv-managed, 21 commits |
| `/Users/hans/Code/github/ai-qa-platform` | this platform (the pilot *subject*, not a reference) |
| `/Users/hans/Code/github/geo-explorer` | TypeScript miniprogram, vitest — not pytest |
| `/Users/hans/Code/github/self-tools` | Rust cargo workspace — not pytest |

## 2. Reference project profile (as detected by the platform)

| Property | Value | Evidence |
|---|---|---|
| Framework | `pytest_playwright` | `pyproject.toml` deps: `pytest`, `pytest-playwright`, `playwright` |
| Package manager | `uv` (`uv.lock`) | `pyproject.toml`, `uv.lock` |
| Python | `>=3.9` (CI pins 3.12) | `pyproject.toml:6` |
| Test roots | `tests` | `[tool.pytest.ini_options] testpaths` |
| Layout | `pages/`, `flows/`, `components/`, `locators/`, `knowledge/`, `api/`, `utils/` | directory scan |
| Plugins | xdist, rerunfailures, allure, playwright | declared deps + `addopts` (`-n`, `--reruns`, `--alluredir`) |
| Markers | `smoke`, `regression`, `slow` (declared twice: pyproject + `tests/markers.py`) | marker declarations |
| Case-id convention | TestRail `C####` via marker regex, function-name heuristic and an explicit map | `integrations/test_management/mapping.py` |
| Tests | 14 collected files, **71 collected logical tests** (5 UI + 66 unit) | pytest collection |
| Allure | `allure-results/` produced by `--alluredir` in `addopts` | `pyproject.toml` |
| Detection confidence | 1.0, no warnings | `POST /api/onboarding/preview` |

## 3. Safety classification

Executed during the pilot:

- `tests/unit/**` — 69 offline tests: no `page`/`browser` fixture, no live HTTP (outbound calls are
  patched), explorer defaults to a fake browser adapter, provider health is `DISABLED` without a key.

Never executed (and refused by the platform's `SafetyPolicy`, not merely skipped by convention):

| Target | Why |
|---|---|
| `tests/test_baidu_search.py` | drives a live public website (`page.goto`, `https://…`) |
| `tests/test_search_flow.py` | requires the real `page` fixture |
| `examples/test_example.py` | real browser against a live site |
| `examples/codegen_test.py` | records a **write** action on a third-party site |
| anything under `-m slow` | that is what un-gates the live search tests |

The policy decides from the test's own AST — required fixtures, network/subprocess calls and marker
decorators — not from marker names, because in this repository the `smoke` marker selects the *live*
tests. Each refusal is reported with its reasons, e.g.
`requires the 'page' fixture`, `contains 'https://'` → reported as `calls page.goto()`.

## 4. How the pilot is driven

Through the platform API (not a bespoke script):

```
POST /api/onboarding/preview        → detection + import plan (read-only)
POST /api/onboarding/import         → isolated copy + project/workspace records
POST /api/onboarding/{id}/runtime   → project-owned virtualenv (uv sync)
POST /api/onboarding/{id}/collect   → structured collection (COLLECTED / COLLECTION_ERROR)
POST /api/onboarding/{id}/run       → safety-checked, bounded selection; persists a run
POST /api/onboarding/{id}/allure    → import the run's Allure results
```

Numbers and commands are recorded in `docs/PHASE_14_PILOT_REPORT.md`.
