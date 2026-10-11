# Accessibility and UI Review — Nightly Platform Improvement

**Date:** 2026-10-11
**Scope:** Authenticated local web app, Chrome, 11 representative desktop route states plus a dark-theme Workspace check. This is targeted browser validation, not a complete WCAG audit or screen-reader/cross-browser certification.

## Changes reviewed

- Added a bilingual skip-to-content link and one shared `main#main-content`; route-level nested `<main>` elements were replaced with ordinary containers.
- Named the primary navigation and previously unnamed selects; repaired invalid/misapplied ARIA labels by using appropriate landmark, group, list, and image roles.
- Corrected heading hierarchy in Workspace run results; provided a single H2 for the run title, H3 panel headings, and H4 subsections.
- Improved light-theme muted/accent tokens while retaining separate dark-theme tokens and existing route, localization, responsive, and reduced-motion behavior.
- Kept the Workspace five-stage navigation and existing content organization.

## axe-core results

Ran **axe-core 4.12.1** against the rendered DOM in Chrome after waiting for each route to settle. The result page initially exposed one `heading-order` violation; the heading hierarchy was corrected and that route was rescanned.

| Route state | axe violations after fixes | axe incomplete notes |
|---|---:|---|
| Dashboard | 0 | `color-contrast` marks SVG chart text for manual review because it cannot determine the chart background. |
| Settings | 0 | None reported. |
| Projects | 0 | None reported. |
| Runs | 0 | `color-contrast` marks 20 status/row text nodes for manual review. |
| Quality | 0 | None reported. |
| Workspace — Requirement | 0 | `color-contrast` marks four stage-number indicators for manual review. |
| Workspace — Cases | 0 | Same four stage-number indicators. |
| Workspace — Discovery | 0 | Stage indicators and Discovery content produce `color-contrast` incomplete nodes requiring manual review. |
| Workspace — Studio | 0 | Stage indicators and a view count require manual review. |
| Workspace — Results | 0 after heading correction | Stage-number indicators require manual review. |
| Workspace — Failure | 0 | Stage-number indicators require manual review. |
| Workspace — Cases, dark theme | 0 | Four `color-contrast` incomplete nodes require manual review. |

**Interpretation:** no confirmed axe violations remained on these sampled route states. `incomplete` is not a pass for those individual contrast checks; it requires human review. A separate custom computed-text contrast check previously found no confirmed low-contrast text on the sampled core pages. This does not replace manual review of the axe-incomplete nodes or a full WCAG audit.

## Browser interaction and responsive checks

- The skip link is keyboard-focusable, becomes visible when focused, and points to `#main-content`.
- Sampled core routes expose one main landmark, have no unnamed `<select>` controls, and have no heading-level skips after the result-page fix.
- Workspace Cases and Discovery were captured at **390×844**. `document.documentElement.scrollWidth` and body width matched the 390px viewport; no document-level horizontal overflow was observed.
- Workspace Cases was also captured at **1480×900** in dark theme. Dark-theme contrast variables and the active stage styling were verified with a settled DOM; the sampled dark route had zero axe violations.
- Desktop after-state captures are in [`screenshots/after/`](screenshots/after/); mobile evidence is `workspace-cases-390x844.png` and `workspace-discovery-390x844.png`; dark evidence is `workspace-cases-dark-1480x900.png`.

## Remaining limits

- No screen-reader-only review, full keyboard journey, touch-target audit, or complete axe sweep of every route/modal/error state was performed.
- Axe `color-contrast` incomplete findings remain for manual review as listed above.
- The current browser checks do not establish behavior in Firefox, WebKit, Windows, or Linux.
- Existing workflow coverage gaps (human rejection and retry-failure) remain outside the UI accessibility pass.
