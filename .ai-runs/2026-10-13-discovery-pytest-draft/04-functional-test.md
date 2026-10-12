# Functional test

## Milestone 1 — Discovery service split

The same focused test set produced **129 passed before and after** the behavior-preserving split. See the regression and architecture notes in `03-implementation.md`.

## Milestone 2 — Discovery journey pytest draft

- `test_quality_discovery.py`, `test_agent_tasks.py`, and `test_recorder_service.py`: focused coverage passed throughout implementation.
- API integration exercises a locally hosted, deterministic page and a completed synthetic Discovery run. The draft task reaches `WAITING`; `inspect`, `decide`, and `act` are skipped; generated pytest contains the observed text assertion; no top-level `url` is supplied; workspace remains unchanged before approval and after rejection.
- A second draft is explicitly approved via the existing Task Runtime API. The generated file is written only after approval and its pytest run passes against the local page.
- Negative coverage rejects missing assertion evidence, non-replayable/failed transitions, a search action mapped to a non-text control, malformed observed controls, and generated constant-true assertions.
- Recorder regression confirms Discovery can select a captured `<option>` by value while older label-based recordings still emit label selection.

## Final regression

`python scripts/task.py test` — **738 passed, 8 skipped** (backend); frontend **138 passed**; typecheck, lint, and production build passed.

The 8 skips include opt-in live-browser/provider cases and the PostgreSQL lane. PostgreSQL was not configured (`AI_QA_TEST_DATABASE_URL` absent). The Vite build emitted only its existing large-chunk advisory.
