# UX review — overnight batch

范围：Dashboard / Requirements / Assertions / Run Results / Recorder，桌面 1280×800、1440×900、1920×1080。

## 修复的用户断点

| 断点 | 现状（改后） | 证据 |
|---|---|---|
| 断言卡看不到运行状态 | 每条断言显示真实状态徽标（已通过/未通过/未执行/阻塞/记录不可访问/取消/运行中）与「查看运行结果」链接 | `assertion-run-state.png` |
| 流程条第 4 步永远未完成 | 绑定真实执行数；未采纳断言不再计数 | 同上（第 4 步实心） |
| 结果页回不到需求 | run 链接携带 requirementId；工作区头部显示「返回需求」 | `run-result-back-link.png`、`run-result-context.png` |
| 保存冲突只有原始报错 | 明确说明「已有内容不同的脚本，未覆盖」，给出重新生成/编辑器查看两条路径 | `conflict-ui.png` |
| 录制脚本数据写死 | 生成结果上方显示参数列表（QA_BASE_URL / QA_DATA_*），说明可用环境变量覆盖 | 代码 + i18n（未做浏览器会话截图） |

## 三档桌面布局

9 张截图（dashboard / requirement / run-result × 3 视口），全部 `horizontal_overflow=False`，且均为**已登录后**的真实产品页面（首轮截图误落在登录页，已用 `#login-email/#login-password` 登录后重拍覆盖）。见 `evidence/*-1280x800.png` 等。

另修复断言行布局：`lc-gap` 改为 flex-wrap，状态徽标 / 「查看运行结果」/ 采纳按钮不再被拉成高胶囊。

## 仍存在的体验问题

1. 断言与执行仍是**文件级**关联：同一文件内两个测试函数时，断言只能显示该文件最近一次执行（服务端取最新）。
2. 流程条第 3 步（脚本）只反映本会话内生成/保存，刷新后依赖 `doc.scripts` 是否已绑定。
3. Recorder 参数面板未做浏览器端截图（需要活动录制会话）。
4. Dashboard 计数仍受探针项目影响（清单已给出，未删）。
