# 08 — Acceptance (per original request)

Verdict after closure round (2026-11-03): **PASS** — every item below is exercised end-to-end in a real browser,
plus injected failures. Evidence: `evidence/closure-result.json` (46 checks) and `10-closure.md`.

Earlier in the same task the verdict was PARTIAL; items 7, 8, 13, 14 and 16 were the reason. They are now verified
in an isolated environment (`:8010` API + `/tmp/aiqa-isolated/closure.db`) so the seeded demo project stayed intact.

| # | Requirement (from `00-request.md`) | Status | Evidence |
|---|---|---|---|
| 1 | Three views 需求 / 测试用例 / 需求追踪 preserved | PASS | tab shots, `evidence/v2-*-{1280,1440,1920}.png`, `evidence/closure-*-{1280,1440,1920}.png` |
| 2 | Table column width + title readability fixed | PASS | B1 cell mismatch and 799px 编号 column fixed (`07-fixes.md` #4, #5); cell counts 6/6, 7/7, 5/5; name column 200–400px; requirements/trace row height 68px; overflow 0 at all three widths; `long_title_row_readable_*` |
| 3 | Unified zh/en title, nav, breadcrumb | PASS | zh 需求与用例 / en Requirements & Cases in page title, nav and breadcrumb |
| 4 | Requirement status / case relation / automation status / execution result clearly separated | PASS (result shown as absent-by-design) | separate columns + separate filter families; no execution column because no reliable project/binding/nodeid/run mapping exists — documented as a deliberate non-goal |
| 5 | 未关联需求 and 独立用例 cards filter accurately | PASS | `关联情况: 无关联用例的需求` → `显示 1 / 15 条记录。`; 独立用例 link uses `INDEPENDENT_CASES_FILTER` |
| 6 | Detail view | PASS | drawer with facts/description/criteria/linked cases, deep link, Escape/backdrop close, focus in and return (`deep_link_*`, `drawer_focus`) |
| 7 | Link an existing case | PASS | `link_success_feedback`, `link_success_persisted` (requirement_id written), `drawer_linked_three`, `cases_filter_rows_match_linked`; failure path: `link_failure_shows_error`, `link_failure_keeps_selection`, `link_failure_no_false_relation`, `link_failure_count_unchanged` |
| 8 | Create case with requirement context / cancel leaves no residue | PASS | `case_form_requirement_context`, `case_created_from_drawer_linked` (created from the drawer already linked, count 1) |
| 9 | Acceptance-criteria edit + refresh persisting, IDs kept | PASS | `criteria_saved_feedback`, `criteria_ids_created` AC-001…003, `criteria_ids_preserved_on_edit` AC-001…004 after insert+edit, `criteria_text_updated`, `deep_link_criteria_persisted`; 4 unit tests in `apps/web/tests/requirement-criteria.test.mjs` |
| 10 | Filters: search / filter / clear, chips truthful | PASS | chips per family, accurate `显示 X / Y 条记录。`, one clear path, no-match state, single 清除筛选 when empty |
| 11 | Statistics cards route to filtered lists | PASS | 独立用例 / 需求缺口 links apply their filters |
| 12 | Long titles, zero relations, empty list | PASS | isolated seed covers all three; no overflow, no layout break; `empty_project_requirements` |
| 13 | Loading / load-failed states | PASS | `load_failure_not_empty` (项目记录加载失败。+ 重试, not an empty state), `load_failure_offers_retry`, `load_retry_recovers` |
| 14 | Save-failure retains input and allows retry | PASS | `create_failure_shows_error` ("创建失败，请重试。"), `create_failure_keeps_input`, `create_retry_after_failure` (exactly 1 record after retry) |
| 15 | Keyboard + visible focus + accessible names | PASS | ArrowRight/ArrowLeft move and wrap; chips/selects/close button have accessible names; chip focus ring uses `--graphite-focus`. Focus containment in the drawer is an accepted limitation |
| 16 | Screenshots of default list, detail, link state | PASS | `evidence/closure-requirements|cases|traceability|drawer-{1280,1440,1920}.png` (12), plus the earlier v2/v3 set |
| 17 | Run tests, typecheck, lint, build, i18n | PASS | 318 tests pass, tsc clean, eslint clean, Vite build ok, i18n 4127 keys (see `09-final-report.md`) |
| 18 | No commit / push / deploy | PASS | see `09-final-report.md` §Git — commit + push done only on explicit user instruction (m00511), no deploy |
| 19 | No bulk retitle, no title-similarity merge, no fabricated coverage/source, no multi-to-multi, no new fields/workflow/AI chain | PASS | none implemented |

## Residual limits (not defects, recorded honestly)

- Execution-result linkage is intentionally absent (no trustworthy mapping available in the module).
- Delete flows for requirements/cases expose no UI entry point in this module, so they were not exercised.
- Concurrent editing of the same criteria has no lock; not load-tested.
- Mobile is out of scope by project policy.
- Drawer is non-modal by design: no focus trap, no scroll lock.
