# AI QA Platform V2 overhaul — UI review

## Browser and viewports

Real Chrome via CDP; `agent-browser` bundled Chrome is incompatible with this macOS host. Desktop/tablet/mobile viewports were checked; these are emulated browser widths, not physical-device or cross-browser certification.

| Surface | Widths / theme / language | Review result | Evidence |
|---|---|---|---|
| Projects and duplicate labels | 1440, 768, 390; light theme; Chinese and English labels | Names are distinguishable. Table scroll remains within a 390px document; 762px table has a 418px internal range. Mobile swipe hint appears at <=768px. Keyboard arrows scroll by 80px; Home/End reach both limits. | `project-names-after-desktop-final.png`, `project-names-after-tablet-final.png`, `project-names-after-mobile-final-light.png` |
| Workspace task Run Dock | 1440, 768, 390; dark theme; Chinese and English | Task completion is not green/pass; case suffix remains visible; copy explicitly says no TestRun was created. No overlap observed at these widths. | `task-complete-status-dock-final-dark-desktop.png`, `task-complete-status-dock-final-dark-tablet.png`, `task-complete-status-dock-final-dark-mobile.png` |
| Dashboard | 1440; dark theme | Skeleton visible at 800ms; content visible at 3s. Stats API was 1.48s / 126,750 bytes; tasks API 141ms. Root cause beyond data wait not isolated; no Dashboard redesign made. | `dashboard-after-retest-800ms.png`, `dashboard-after-retest-3s.png` |

## Accessibility

- Projects axe: 0 violations, 1 incomplete contrast item (project swipe hint/table header, due background inference). Computed project header text against white is 5.4:1; hint uses the same muted token.
- Workspace axe: 0 violations, 1 incomplete contrast group (9 nodes, pseudo-element/overlap prevents automated background inference). Sampled dark-theme ratios: muted stage number 6.49:1, strong label 16.42:1, muted small text 8.37:1.
- Keyboard tested on the Projects scroll region, including visible focus and ArrowRight/Home/End. Run Dock dialog open/close and controls observed. Full screen-reader testing was not performed.
- No axe violation was found. Incomplete automated contrast results are recorded rather than presented as full WCAG certification.

## Review outcome

No P0 or P1 visual/accessibility defect remains in the changed surfaces. The project table has a mobile scroll hint and keyboard operation. Dashboard loading and language-service availability remain documented risks rather than silently claimed fixes.
