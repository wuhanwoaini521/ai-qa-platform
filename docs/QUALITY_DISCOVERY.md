# Quality Discovery — Live Exploration Engine

`[CURRENT]`

Quality Discovery (质量发现) explores a running web application with a real Chromium browser, records what
it observes, and turns the observation into findings that enter the normal QA workflow. This document covers
the live engine added on the `agent/discovery-live-engine` branch: how the browser is watched in real time, how
element geometry and highlights reach the UI, the event contract, AI degradation behaviour, and the security
boundary.

---

## 1. Scope and non-goals

In scope:

- Watch a discovery run while it happens: real page frames, current URL, observed element inventory, actions,
  AI decisions, evidence and findings.
- On-page highlight boxes drawn from **measured DOM geometry**.
- One typed event contract shared by the persisted run history and the live view.
- Honest degradation when the AI provider is unavailable.

Out of scope (deliberately rejected, see `docs/ROADMAP.md` §0):

- No second browser lifecycle. Discovery reuses `BrowserRuntime` and the platform's existing session registry.
- No second agent/provider. Discovery plans with the configured AI provider and makes the decision with the
  existing `DecisionService` (Jev).
- No video recording and no frame persistence. Frames are transient viewport images for the viewer.
- No unattended autonomous loop and no automatic code/business-data mutation.

---

## 2. Architecture

```
POST /api/discovery/runs
        │
        ▼
QualityDiscoveryService            apps/api/app/services/quality_discovery_service.py
  ├─ _execute (exploration loop)   apps/api/app/services/quality_discovery_execution.py
  │     ├─ BrowserRuntime          apps/api/app/adapters/playwright/browser_runtime.py
  │     │     create_session / navigate / snapshot / collect_controls
  │     │     capture_frame (viewport JPEG) / paint_highlights (in-page overlay)
  │     ├─ AIProviderRegistry      packages/qa-core         (planning only)
  │     └─ DecisionService         apps/api/app/services/decision_service.py (Jev: choose/score)
  ├─ result["events"]              persisted, capped by discovery.max_events
  └─ DiscoveryLiveHub              apps/api/app/services/quality_discovery_live.py
        └─ GET /api/discovery/runs/{run_id}/stream   (SSE, live only)
                 │
                 ▼
        DiscoveryLiveView          apps/web/src/features/workspace/DiscoveryLiveView.tsx
          └─ foldLiveEvent         apps/web/src/features/workspace/discoveryLive.ts
```

### Reused platform capability (no new machinery)

| Concern | Reused component |
|---|---|
| Browser session, navigation, screenshots | `BrowserRuntime` port (`apps/api/app/ports/browser_runtime.py`) |
| In-page instrumentation precedent | `RECORDER_INIT_SCRIPT` (`apps/api/app/services/recorder_service.py`) |
| SSE envelope | `app/event_stream.py::event_frame` |
| Stream authorisation | stream tickets in `apps/api/app/api/auth.py` + `apps/api/app/api/authz.py` |
| Evidence storage | `ArtifactStorageService` (PNG screenshot + JSON evidence bundle per observed state) |
| Decision + scoring | `DecisionService` (Jev) and `AIProviderRegistry` |
| Frontend stream transport | `apps/web/src/api/eventStream.ts` (ticket auth, reconnect, duplicate suppression) |

The discovery exploration itself runs as an in-process `asyncio` task created by
`QualityDiscoveryService._schedule`. This is a **known deviation** from the roadmap rule that long-running work
belongs to `TaskRuntimeService`; it is recorded as open work, not as a design goal (see §10).

### Two data paths, one source of truth

- **Persisted**: `result["events"]` inside the run row, written by `QualityDiscoveryService._event`. This is the
  authoritative history and what `GET /api/discovery/runs/{run_id}/events` returns.
- **Live**: the same `_event` call also publishes a payload to `DiscoveryLiveHub`, a fan-out with
  per-subscriber bounded queues (a slow viewer drops its own oldest items and can never stall the run).

Frames are the single exception: they are **live only** (`browser.frame`) and stored in a latest-only slot,
because persisting a screenshot stream would bloat the database without adding evidence — one screenshot per
observed state is already saved as an artifact.

---

## 3. Live view

- Transport: `GET /api/discovery/runs/{run_id}/stream`, `text/event-stream`, authorised by the normal router
  guards (`discovery_run_access` verifies project ACL) for both stream-ticket and bearer callers.
- The stream opens with a `snapshot` frame (status, progress, last 100 persisted events) so a page refresh
  rebuilds the view from history, then streams live events until `run.finished`.
- Frames come from `BrowserRuntime.capture_frame`: a **viewport** JPEG (quality 55, 1 s timeout) — never a full
  page, never in the action path. A frame is produced only while at least one viewer is attached
  (`live_frame_interval_ms`, default 1000 ms). No viewer ⇒ no screenshots ⇒ no cost.
- If a paint is not ready (page mid-navigation, browser closed) the capture returns nothing and the pump retries
  sooner (min(interval, 250 ms)); the run is never blocked or failed by a slow frame.
- On viewer disconnect the pump stops; on cancellation/stop/exit the hub is flushed and frames dropped.

---

## 4. Element geometry and highlights

Every control collected during exploration now carries measured geometry:

| Field | Meaning |
|---|---|
| `bounding_box` | `{x, y, width, height}` in CSS pixels, viewport-relative (`getBoundingClientRect()`), rounded |
| `in_viewport` | Whether the element box intersects the current viewport |
| `visible_ratio` | Visible (clipped) area ÷ element area, 2 decimals |

The same values are attached to candidates and published in `element.inventory`, so the UI draws boxes that
match the real page instead of guessing. The viewer scales percent-of-viewport using the frame metadata
(`viewport`), so a resized pane or a non-1280-wide viewport still aligns.

In-page highlight: `BrowserRuntime.paint_highlights` injects the `HIGHLIGHT_SCRIPT` overlay
(`#__qaDiscoveryHighlights`, `position: fixed`, `pointer-events: none`, up to 50 boxes) and draws the boxes for
the candidates currently being considered. Colours used by the engine:

- `#22d3ee` (cyan) — candidate actions observed on the current page.
- `#f59e0b` (amber) — the candidate Jev selected, i.e. the action about to run.

When a highlight cannot be painted the reason is kept; no placeholder box is ever drawn.

---

## 5. Event contract

Envelope (`event_payload` in `apps/api/app/services/quality_discovery_live.py`):

```json
{ "type": "element.inventory", "seq": 7, "message": "…", "metadata": { }, "at": "2026-10-18T01:02:03.123456+00:00" }
```

`seq` is a per-run monotonic counter (shared with the persisted history, so the live view can de-duplicate on
reconnect), `at` is UTC. `metadata` is event-specific.

| Event | Live | Meaning |
|---|:--:|---|
| `snapshot` | ✔ | Stream opener: `{status, progress, events[]}` replay of persisted history |
| `run.status` | ✔ | Pause / resume / stop transitions (live-only; the persisted event carries the run status) |
| `page.opened` / `page.state` | ✔ | Navigation and observed-state boundaries |
| `element.inventory` | ✔ | Up to 60 observed elements with role, name, actionability, geometry, locator |
| `action.planned` | ✔ | Chosen candidate plus the intended action and its highlight reason |
| `action.executed` | ✔ | Applied action and its outcome |
| `ai.decision` | ✔ | AI/Jev decision, provider, model, confidence and reason |
| `ai.unavailable` | ✔ | AI provider failed; the run continues on deterministic guidance |
| `finding` | ✔ | A quality finding produced from observations |
| `evidence.captured` | ✔ | Screenshot/DOM bundle artifact id for the current state |
| `coverage.updated` | ✔ | Coverage refresh completed |
| `browser.frame` | ✔ | Live viewport JPEG (base64) + `url`, `mime_type`, `viewport` |
| `error` | ✔ | Recoverable error surfaced to the viewer |
| `run.finished` | ✔ | Terminal payload; the subscriber generator ends on it |

`browser.frame` and `run.status` are live-only. Everything else is also persisted in `result["events"]`, so
history and live view never disagree.

---

## 6. AI availability and degradation

The browser and the AI are separate layers. When the configured provider fails
(`AIProviderError`, e.g. a timeout) or Jev is unavailable:

- the failure is recorded as `ai.unavailable` and surfaced in the UI, with the real reason;
- requirement analysis degrades to an empty structured requirement instead of inventing one;
- planning degrades to a neutral plan, and **Jev still chooses** from the candidates the browser actually
  observed;
- pages, elements, geometry, screenshots and evidence remain available, and the run is not marked FAILED.

There is no silent fallback to the Fake provider for a run that claims to be real, and no fabricated AI result
is ever written. A run that requires AI can still refuse to start (`require_ai`) — that refusal is reported as
`BLOCKED`, not silently downgraded.

---

## 7. Security and threat model

Discovery drives a real browser against a URL supplied by a user, so it is a trust boundary.

Enforced today:

- **Host allowlist on both layers.** `restrict_navigation` installs route guards in the browser context
  (HTTP/HTTPS only, host must be allowlisted, credentials in the URL rejected; WebSocket likewise), and
  `_allowed_hosts` = start-URL host ∪ run `allowed_domains` ∪ `config.discovery.allowed_domains` with
  `_host_allowed` re-checking scheme/userinfo before each navigation.
- **No destructive actions by default.** `safe_mode: true`; cart/checkout/payment-like mutations are blocked
  unless the run's requirement explicitly allows them (`_is_cart_mutation_label`,
  `_requirement_allows_cart_mutation`).
- **Bounded runs.** `max_actions`, `max_failures`, `max_depth`, `max_states`, `max_runtime_minutes`,
  `max_candidates`, `max_screenshots`, `max_evidence_chars`, `max_events`.
- **Redaction.** Sensitive values are redacted before they reach an event, an evidence bundle or the UI
  (`SensitiveRedactor`, recorder `describe()`/`safeText` precedent).
- **Artifact confinement.** Evidence paths are resolved and must stay inside the configured artifact root.
- **Authorisation.** All discovery routes carry the project ACL guard (`project_access`): a caller who neither
  owns nor shares the project gets 404, and the live stream requires the same access as the run itself.

Known gaps (open, tracked — do not read this section as "solved"):

1. The host allowlist matches **host names only**: no private-IP / link-local / CIDR blocking and no port
   restriction, so an internal host name that a user is allowed to name is not blocked by policy.
2. The exploration loop is an in-process task and not tracked by `TaskRuntimeService`, so it is not visible in
   the Task Runtime view and does not survive a process restart.
3. Discovery findings do not yet carry a per-finding provenance object into Requirement / Test Case /
   Automation runs; the linkage is by id and is asserted in tests, not schema-enforced.

---

## 8. UI guide

The Quality Discovery workbench (`apps/web/src/features/workspace/DiscoveryLiveView.tsx`, mounted from
`QualityDiscoveryPanel.tsx`):

- **Left — live browser.** The real exploration session's viewport, the current URL, connection state
  (connecting / live / reconnecting / ended), and the element boxes with a category toggle. Box selection shows
  role, name, locator and geometry.
- **Right — live intelligence.** Current action, the Jev decision with provider/model/confidence/reason, the
  observed element inventory, and evidence links.
- **Bottom — event timeline.** The DevTools-style ordered stream (page, element, action, AI, evidence, error
  entries) with `seq`, timestamp and jump-to-evidence.
- **Historical vs live.** Once a run ends the timeline keeps the persisted history and the last captured frame
  is labelled as the last evidence frame — the view never pretends an ended run is still live.

All strings are bilingual: add keys to both `apps/web/src/i18n/locales/en/qualityDiscovery.json` and
`.../zh-CN/qualityDiscovery.json`, then run `uv run python scripts/i18n_check.py`.

---

## 9. Configuration

`DiscoverySettings` (`packages/platform-config/platform_config/models.py`), documented in
`config/config.example.yaml` under `discovery:`:

- `live_frame_interval_ms` (default `1000`, 100–10 000): live frame cadence while a viewer is attached.
- plus the existing bounds and flags: `enabled`, `require_ai`, `require_jev`, `max_actions`, `max_failures`,
  `max_depth`, `max_states`, `max_runtime_minutes`, `max_candidates`, `screenshot`, `capture_console`,
  `capture_network`, `safe_mode`, `state_similarity_threshold`, `max_events`, `max_evidence_chars`,
  `max_screenshots`, `allowed_domains`.

---

## 10. Verification

```bash
uv run --no-sync pytest apps/api/tests/test_quality_discovery.py \
  apps/api/tests/test_quality_discovery_live.py \
  apps/api/tests/test_quality_discovery_live_e2e.py \
  apps/api/tests/test_discovery_coverage_e2e.py -q
uv run --no-sync ruff check apps/api packages
pnpm --filter @ai-qa/web test
```

Evidence of record:

- `apps/api/tests/test_quality_discovery_live.py` — event contract, hub fan-out/drop-oldest, stream ticket scope,
  frame pump, SSE replay, and AI-degradation without FAILED status.
- `apps/api/tests/test_quality_discovery_live_e2e.py` — **real Chromium**: serves a page whose controls sit at
  known coordinates, asserts the live inventory's `bounding_box` matches the page within 8 px, asserts streamed
  frames are the real adapter's JPEG bytes, and asserts the in-page highlight was actually painted.

Open work (next rounds): private-IP/CIDR policy for the allowlist, moving the run loop onto `TaskRuntimeService`,
provenance linking into Requirement → Case → Automation, richer AI failure UX, and the two-way pagination of
very long histories.
