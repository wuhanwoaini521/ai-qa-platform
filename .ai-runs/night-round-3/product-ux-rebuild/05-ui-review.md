# Real-browser UX review

## Scope and verdict

Reviewed Northstar's connected workspace journey at 1440px desktop, 768px tablet, and 360px narrow mobile: case/workspace → Automation Studio → configured run → results/logs → live browser evidence → existing failure/repair → paused debugger. The issues found here are fixed in this continuation; no second runtime, run page, or repair path was added. Review used actual Chrome/Playwright interaction and before/after screenshots rather than mock layouts.

## Findings and disposition

| Priority | Finding | Disposition |
|---|---|---|
| P1 | The editor's quick run used an active-file target/config that could differ from the case and Run Controls shown by the shared workspace. | Fixed: case binding is the default editor target, explicit Test Explorer targets still win, and embedded Studio sends the shared dock's environment/region/browser/workers. Retry keeps the original run's historical settings. Button copy distinguishes case from file. |
| P2 | Embedded Studio repeated the app-level project selector and left Quick Open as an unlabeled icon. | Fixed: hide the duplicate selector only in embedded mode, retain Quick Open with visible text and an accessible name. |
| P2 | Five workspace stages overflowed/required horizontal scrolling on tablet/mobile. | Fixed: five equal columns at 768px and a compact five-stage rail at 360px. Real browser measured no page overflow and equal nav `clientWidth` / `scrollWidth`; Tab advances between stage buttons at desktop, tablet, and narrow widths. |
| P2 | Invalid browser evidence timestamps could display `Invalid Date`. | Fixed: empty, missing, or invalid values render as `—`; valid times retain local-time formatting. |
| P2 | Paused debugger toolbar text actions had collapsed padding and looked clipped/overcrowded. | Fixed: preserve normal padding for `.studio-tool` buttons. At 1440px the smallest control is 44px and no button boxes overlap. |

## Screenshots

Baseline and final screenshots are under `evidence/before/` and `evidence/after/`. The after set includes Studio at 1440/768/360, the Run Controls configuration, result, live Runtime Browser, existing failure/repair view, and paused debugger. `interaction-results.json` records the measured run payload and responsive/toolbar geometry; `stage-navigation-1440.json` records the desktop keyboard/layout check.

## Remaining observations

- The paused editor still reports **Python 语言服务不可用**. The real debug session did pause and expose stack/local-variable/step controls; the language-service issue is not caused by these UX changes and was not repaired here.
- The demo site emits `GET /favicon.ico` 404; reproduced against the isolated demo fixture. Not a platform API defect.
- Keyboard movement within the stage rail was verified, but no axe/automated accessibility audit was available in this scoped pass. Do not interpret this as a full accessibility certification.
- Seven passed diagnostic TestRun records were left in the Northstar demo project to preserve execution evidence; source file hash is unchanged.
