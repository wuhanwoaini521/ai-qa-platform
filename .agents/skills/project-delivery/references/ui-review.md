# UI Review

对 `ui-feature`、`ui-redesign`、视觉回归和用户可见交互改动启用。纯后端改动不启动 UI review；若任务混合 UI 与非 UI 风险，保留 UI 门禁并同时覆盖其他受影响路径。

## 前置条件

UI review 必须基于**真实运行的应用**，不是代码推测：

1. 启动应用（用仓库既有的 run/dev 命令）。
2. 打开目标页面（用浏览器或真实视口）。
3. 截图或实际观察，记录视口宽度。

如果环境有浏览器能力，必须运行页面并进行真实浏览器验证。无法运行时，明确标记 `Browser verification: NOT AVAILABLE`，说明原因，不要用代码检查或"应该没问题"代替。若真实 UI 行为仍未被其他证据覆盖，不能给 `PASS`，通常给 `PARTIAL`。

## 检查维度

逐项过，不要只看第一眼：

- **Layout**：结构、对齐、栅格、留白节奏。
- **Hierarchy**：视觉优先级是否清晰，主要动作是否突出。
- **Spacing**：间距是否成体系，内边距与外边距是否一致。
- **Typography**：字号层级、行高、字重、换行与截断。
- **Contrast**：文字与背景对比度，弱化文本是否过度。
- **Interaction states**：默认、hover、focus、active、disabled、loading、error、empty。
- **Responsive**：桌面 / 平板 / 手机宽度下的布局行为。
- **Overflow**：横向溢出、文字截断、容器撑破、长内容。
- **Accessibility**：键盘可达、focus 可见、语义标签、aria、点击目标尺寸。
- **Consistency**：与既有页面、设计系统、组件库是否同源。

## 分级

- **P0 / Critical**：核心功能不可用、严重布局崩坏、关键操作不可达或内容丢失。必须修；未解决阻断 `PASS`。
- **P1 / High**：明显影响可用性、可访问性或一致性的问题。正确性、安全、关键交互或响应式回归类 P1 必须修；未解决阻断 `PASS`。范围外或非阻断改进可以记录为 remaining risk 并说明 disposition。
- **P2 / Medium**：细节打磨（次要间距、轻微视觉偏好）。记录即可，不驱动继续打磨。
- **P3 / Low**：纯偏好或未来建议。可选记录。

## Review loop

```text
Implement
   ↓
Run app
   ↓
Open UI
   ↓
Screenshot / inspect
   ↓
Independent review     —— 与实现者分离的视角或独立 agent
   ↓
Fix blocking P0 and correctness/safety P1
   ↓
Review again           —— 修复后必须再看一遍
```

**不允许**"review 报告写完 → 任务结束"。修复后要有第二轮确认，否则"已修复"只是声明不是证据。

## 响应式验证

至少覆盖：

- 桌面宽度（目标主力宽度）。
- 平板宽度。
- 手机宽度（360px 左右）。

记录每个宽度下的观察结果。响应式验证是 UI 任务的硬门禁，不是可选项。

## 设计能力组合

需要设计方向时主动发现可用 skill（例如 `ui-ux-pro-max`），不要等用户点名；不存在时用内置判断继续，并在报告中记录"专用设计 skill 不可用"。

不要把某个设计 skill 的数据库、清单或设计稿复制进本 skill，只调用它。

## 记录位置

写进 `05-ui-review.md`：视口、截图 / 视觉观察、P0、P1、P2、修复建议、review 结论。
