# Functional Testing

验证用户要求的行为是否真正可用。先从仓库配置与 CI 发现项目自己的命令；不要对所有项目固定运行同一套工具或只靠静态检查。

## 验证顺序

```text
existing targeted checks → new targeted checks → relevant integration checks
→ real functional check → risk-appropriate regression
```

从最相关的测试开始，保留清晰的失败定位，再按调用链和影响面扩展。依据项目实际配置发现 `pytest`、`npm/pnpm`、Vitest、Playwright、typecheck、lint、build、Cargo、Make 等命令；不要假设工具链。

## 必须覆盖

- 每次实际代码改动都要验证；风险等级决定验证深度，不决定是否验证。
- 正常行为和至少一个相关边界/失败行为都要覆盖。
- 新功能的每条关键验收标准都要有证据。Bug 修复应有能锁住根因的回归用例。
- 如果功能可以真实运行，验证实际行为：CLI 执行命令、API 请求和响应/失败状态、脚本真实运行、UI 真实交互。
- UI 变更按 `ui-review.md` 执行真实浏览器检查。没有浏览器能力时明确报告 `Browser verification: NOT AVAILABLE`，不伪称完成。
- 记录实际命令、通过/失败数量、手工验证观察及未覆盖部分。不要把计划执行的命令写成已完成。

依赖或环境阻止必须验证时，报告具体失败和已尝试的替代方式；不得把未运行的验证标为通过。若核心行为已实现但必需证据不可获得，验收通常为 `PARTIAL`；按 `final-acceptance.md` 判定。

## 失败循环

```text
Failure → evidence and root cause → source fix → rerun affected checks → regression
```

不要为让测试变绿而放宽断言或隐藏失败状态。测试/验证结果记录在 `04-functional-test.md`，修复记录在 `07-fixes.md`。
