# Functional Test Evidence

## Automated checks

| Command | Result |
|---|---|
| `pnpm --filter @ai-qa/web test` | PASS — 117 passed, 0 failed (includes 4 requirement-selection model tests) |
| `pnpm --filter @ai-qa/web lint` | PASS |
| `pnpm --filter @ai-qa/web typecheck` | PASS |
| `pnpm --filter @ai-qa/web build` | PASS — TypeScript and Vite production build completed. Existing Monaco chunk-size warning remains. |
| `git diff --check` | PASS |

## Live browser interaction

- Opened the running app at `http://127.0.0.1:5173/workspace/proj_golden_shop_v1?...stage=requirement&view=requirement`, authenticated in an isolated browser session, and tested with the context rail collapsed.
- Actual Golden Demo Shop state has one requirement. The toolbar visibly shows `当前需求`, `REQ-001`, and `商品搜索、规格选择与购物车验证`; the single-item state does not present an inert dropdown.
- To test the multiple-item interaction without creating or changing project data, temporarily mocked the read-only requirements response in the isolated browser session with a second requirement. The selector exposed both `REQ-001 · 商品搜索、规格选择与购物车验证` and `REQ-002 · 结账与订单确认流程`. Selecting the second option updated the control, detail heading, and URL `requirementId` to `req_ui_selection_test`, while the context rail remained collapsed.
- Repeated the selection at 390px; `document.documentElement.scrollWidth` stayed 390px. The unpersisted mock naturally caused a related knowledge request to report that the mock requirement does not belong to the project; this was fixture-only. Removed the route, restored the real project page, and confirmed the real one-requirement state and zero page errors.
- The selector is a native `<select>` with the accessible name `当前需求`; its focus ring is visible. Screen-reader testing was not performed.

## Responsive/theme evidence

- 1280×900 light: scope and identity remain left-aligned; Jira import, create, and AI analysis actions remain available on the right. No document-level horizontal overflow.
- 768×1024 light: scope occupies a dedicated row above actions. Document width 768px.
- 390×844 light: scope and wrapped actions remain reachable; document width 390px.
- 1280×900 dark: the identity retains readable theme-token colors (background `rgb(28, 33, 41)`, title text `rgb(237, 241, 247)`). Document width 1280px.

Screenshots observed:
- `/tmp/requirement-final-light-1280.png`
- `/tmp/requirement-final-light-768.png`
- `/tmp/requirement-final-light-390.png`
- `/tmp/requirement-final-dark-1280.png`
- `/tmp/requirement-final-multi-390.png` (mock data; see fixture note above)
