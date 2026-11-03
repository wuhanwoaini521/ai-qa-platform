# 05 — UI review

Independent review performed by the `design-director` subagent (read-only, separate agent) against `docs/UI_DESIGN_SYSTEM.md`, using the 1280/1440/1920 screenshots of all three tabs plus drawer, active-chip and no-match states.

Verdict at review time: **FAIL** — 1 blocker + 5 should-fix. Direction itself accepted (Warm Light Editorial: near-black single primary, white cards, 1px dividers, pill statuses, mono IDs, orange reserved for gap/independent links); all findings were execution-level.

## Blockers / should-fix and resolution

| id | Finding | Resolution |
|---|---|---|
| B1 | Cases table header had 7 `<th>` but rows emitted 6 `<td>` (identity cell merged 编号+名称), so 独立用例/P2/手动/date/打开工作台 sat under the wrong headings at all three widths | **Fixed** — cases row now emits a separate `<code>` ID cell + name cell, matching the requirements and traceability templates. Re-verified cell counts: requirements 6/6, cases 7/7, traceability 5/5 |
| S1 | Filter-summary/chips row had no padding and broke the card's 16px rhythm | **Fixed** — `padding:12px 16px;border-bottom:1px solid var(--line)` |
| S2 | 清除筛选 rendered twice in the no-match state (chips-row link + empty-state button) | **Fixed** — chips-row clear hides while `visibleCount === 0` |
| S3 | Cases toolbar wrapped raggedly at 1440 (排序方式 orphaned on its own row) because the 所属需求 select sized to its longest option | **Fixed** — `.project-management-filter{max-width:200px}`; all four filters now sit on one row at 1440 and 1920 |
| S4a | 关联用例 used twice in the drawer (facts `dt` and section `h4`) | **Fixed** — facts label now 关联情况 / `relationshipFilter` |
| S4b | Link-case label and empty option used the same sentence | **Fixed** — new `selectCaseLabel` key (用例 / Case) |
| S5 | Dialog took programmatic focus with `outline:none`, no focus return, no containment | **Partially fixed** — focus now returns to the triggering 详情 button on close (`lastTriggerRef`). Focus containment inside the drawer is **not implemented** (non-modal by design, `aria-modal="false"`) → accepted limitation |
| N1 | Chip focus ring used `--accent-blue` instead of the page's `--graphite-focus` | **Fixed** |
| N3 | Facts grid 2×2 with 3 items left a hole | **Fixed** — flex-wrap row of `flex:1 1 130px` cells |
| N2, N6 | Drawer `h4` at 13px (hierarchy by weight only); disabled 关联 button carries no reason text | **Not fixed** — cosmetic/low impact, recorded as accepted nits |
| N7 | Cases row density (~1.5 rows visible at 1280×800) | **Accepted** — inline association is the feature |
| N4, N5 | Pre-existing: counts duplicated in cards and tab badges; drawer covers the top toolbar | **Out of scope** — pre-existing, not introduced here |

## Post-fix visual state

Re-shot from one build: `evidence/v2-requirements-{1280,1440,1920}.png`, `v2-cases-*`, `v2-traceability-*`, `v3-drawer-*`, `v2-chips-search-1440.png`, `v3-nomatch-1440.png`. All three tabs: page `scrollWidth - clientWidth = 0` and table wrapper overflow 0 at 1280, 1440 and 1920.

Residual designer nits not re-reviewed after the fixes (no second review pass was requested): drawer `h4` size, disabled-action reason, density at 1280.
