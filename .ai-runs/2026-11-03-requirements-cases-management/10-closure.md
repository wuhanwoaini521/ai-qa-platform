# 10 — 收尾验证：隔离环境中的真实业务闭环

日期：2026-11-03
环境：隔离（详见下文），不使用共享开发栈的数据

## 1. 为什么用隔离环境

共享栈（`:8000` + `:5173`，seeded 项目 `proj_golden_shop_v1`）不适合做写入型闭环验证：
需求标题、验收标准、用例关联都会被真实修改，而平台明文规定不得"自动删除或覆盖数据"。

隔离环境（`/tmp/aiqa-isolated`，**不入库**）：

| 组件 | 地址 | 数据 |
|---|---|---|
| API（uvicorn，独立进程） | `127.0.0.1:8010` | `/tmp/aiqa-isolated/closure.db`（SQLite，干净） |
| 前端（Vite，复用仓库 `:5173` 实例） | `127.0.0.1:5173` | 浏览器侧 `/api/*` 请求经 Playwright `route.fetch()` 转发到 `:8010`；前端代码保持仓库 `:5173` 原样 |
| 管理员账号 | `admin@ai-qa.local` | 由 API 启动时初始化（`/tmp/aiqa-isolated/start.sh`） |

每个 API 进程各自接线，**用前必须确认端口只有一个监听者**（`lsof -ti tcp:8010 | wc -l` 应为 1）。
本轮曾出现"脏结果后被第二实例复用"的情况：端口被占用时 `start.sh` 新进程启动失败，但旧进程续跑旧库，
导致截图能看到新记录的标题、API 却查不到该 id。判定为环境问题（不是产品缺陷），处置见 §4。

## 2. 验证脚本

`.ai-runs/2026-11-03-requirements-cases-management/evidence/closure-check.py`

- 只经 API 建种子（把一个需求和几个用例隔离到独立项目 `Closure Isolated Project`），其余全部走真实 UI 操作；
- 失败注入用 `page.route(..., abort)` 覆盖 PATCH `/api/requirements/*`、`/api/test-cases/*`、`GET /api/requirements?*`、`GET /api/dashboard/stats*`；
- 执行：`uv run python .ai-runs/2026-11-03-requirements-cases-management/evidence/closure-check.py`
- 结果文件：`evidence/closure-result.json`（46 项，2026-11-03 14:38 全绿）

## 3. 结果（46/46 PASS）

### CRUD 与校验

| 检查 | 证据 |
|---|---|
| `create_validation_blocks_empty` | 空标题点"新建需求"，提交前拦截，记录数不变 |
| `create_requirement_success` | 弹窗关闭、需求出现在列表（1 条） |
| `requirement_persisted` | 重新拉取 `/api/requirements?project_id=…` 命中新标题 |
| `create_duplicate_submit_guard` | 双击提交只发出 1 次 `POST /api/requirements` |
| `create_failure_shows_error` / `create_failure_keeps_input` / `create_retry_after_failure` | 注入 500 后弹窗显示"创建失败，请重试。"且保留已填标题；恢复后重试成功、只出现 1 条 |
| `drawer_matches_row` | 抽屉标题含超长需求标题，与行内一致 |

### 验收标准（状态机 + 编号保留）

| 检查 | 证据 |
|---|---|
| `criteria_saved_feedback` | 保存后出现成功提示，`qa_model.criteria` = AC-001/002/003 |
| `criteria_ids_created` | 首次保存生成稳定编号 `AC-001…003` |
| `criteria_ids_preserved_on_edit` | 第二次编辑（3→4 条并改文案）后编号仍为 `AC-001…004`，未重排、未重复 |
| `criteria_text_updated` | 被改文案读回为"叠加优惠券后总价按最优方案计算（含会员价与新人券）" |
| `deep_link_criteria_persisted` | 刷新深链 `?detail=<id>` 后抽屉里验收标准仍为最新 4 条 |

### 用例关联（含失败回滚）

| 检查 | 证据 |
|---|---|
| `case_form_requirement_context` / `case_created_from_drawer_linked` | 在需求抽屉里"新建用例"，弹窗带上所属需求上下文，创建后立即关联（关联数 1） |
| `drawer_fact_count_matches` | 抽屉事实区"关联情况：已关联 1 个用例"与列表真实计数一致 |
| `link_failure_shows_error` / `link_failure_keeps_selection` | 注入 PATCH 失败 → 提示"关联失败，请重试。"，下拉选择保持，可重试 |
| `link_failure_no_false_relation` / `link_failure_count_unchanged` | 失败后需求关联数不变，用例仍为独立用例（无假成功） |
| `link_success_feedback` / `link_success_persisted` / `drawer_linked_three` | 恢复后关联成功并持久化，抽屉显示 3 个关联用例 |
| `cases_filter_rows_match_linked` / `cases_filter_summary_matches` | 用例页按该需求筛选得 3 行，"显示 3 / 3 条记录。"，筛选芯片显示 `所属需求: 395C54` |

### 追踪表一致性

| 检查 | 证据 |
|---|---|
| `trace_rows_match` / `trace_count_matches` | 追踪表该需求行展开 3 个关联用例，与用例页筛选结果、抽屉计数三方一致 |

### 状态与错误态

| 检查 | 证据 |
|---|---|
| `empty_project_requirements` | 空项目显示空态，不伪造记录 |
| `load_failure_not_empty` / `load_failure_offers_retry` | 注入 `GET /api/requirements` 500 → "项目记录加载失败。" + 重试，而不是空态 |
| `load_retry_recovers` | 恢复后重试成功，表格回填 |
| `console_errors` | 全程 0 个 console error（`page_errors` 为空） |

### 桌面视口 1280 / 1440 / 1920

每档均验证 `page_no_horizontal_overflow`、`drawer_no_horizontal_overflow`、`long_title_row_readable`：
超长需求标题在表格与抽屉中都完整可见，页面横向溢出 0。截图：
`evidence/closure-{requirements,cases,traceability,drawer}-{1280,1440,1920}.png`（12 张）。

## 4. 本轮期间发现与处置

| # | 现象 | 定性 | 处置 |
|---|---|---|---|
| C1 | 保存后提示一闪而过 | 前端缺陷 | 已修（`detailCriteriaRef`，07-fixes.md #1） |
| C2 | 用列表异常排到表格下方 | 前端缺陷 | 已修（移到关系提示下方，07-fixes.md #3） |
| C3 | 用例表 `<th>`/`<td>` 数量不一致 | 前端缺陷 | 已修（拆列，07-fixes.md #4） |
| C4 | 用例表在 1280 横向溢出 454px、编号列 799px | 前端缺陷（`white-space:nowrap` 泄漏到全表） | 已修（仅追踪表保留 nowrap，07-fixes.md #5） |
| C5 | 表格行高 / 名称列过宽导致可读性差 | 前端缺陷 | 已修（名称列 200px 起、400px 封顶；需求/追踪行高 87→68px；用例表单独豁免） |
| C6 | 注入 500 时创建/关联弹窗无错误提示 | 前端缺陷（错误被吞） | 已修（`error` prop + `role="alert"`） |
| C7 | 空态"清除筛选"重复出现两个 | 前端缺陷 | 已修（`visibleCount === 0` 时隐藏芯片行清除按钮） |
| C8 | 键盘左右方向键行为相同（← 也前进） | 前端缺陷 | 已修（`moveTab` 方向参数） |
| C9 | 连续提交可产生重复记录 | 前端缺陷（无进行中守卫） | 已修（`createRequirement`/`createTestCase` 进行中守卫；`create_duplicate_submit_guard` 验证只发 1 次请求） |
| E1 | 脚本读到"新记录存在 UI、API 却查不到" | **环境**，非产品缺陷 | 端口 8010 有多个 uvicorn 进程 / 旧进程占端口导致新旧库混读；改为"kill 后确认唯一监听者再启动"，重跑 46/46 全绿 |

E1 排除过程记录：先用纯 API 脚本（PATCH → GET 轮询 10 轮）确认单实例下写入可见延迟为 0.01s；
再用 `pgrep -af uvicorn` 发现同一端口上残留多个进程，确认是环境串线。产品侧无读写不一致缺陷。

## 5. 仍然未验证（如实列出）

1. 真实浏览器执行/运行结果关联展示：模块没有可靠的 project/binding/nodeid/run/execution 映射，
   按约定不伪造，故未验证"执行结果"列（本轮也未实现）。
2. 需求与用例的"删除"流程：平台未提供该 UI 入口，未验证。
3. 并发多用户同时编辑同一需求验收标准：无锁设计，未做并发压测。
4. 移动端：按项目规定不在范围内，未验证。
