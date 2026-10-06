# Development

实现阶段的约束。目标是边界清晰的正确改动，不是"最小可能 diff"或大规模重写。

## 核心原则

- **Understand before modify**：没读懂调用方、数据流与现有约定之前不要动手。
- **Reuse before create**：仓库里已有能力（工具函数、组件、hook、中间件）先复用，不要顺手再造一套。
- **Smallest coherent solution**：改动足以解决根因并形成完整行为；不做掩盖问题的最小补丁，也不扩大成无关重写。
- **Preserve behavior unless requested**：没被要求改的行为不要改（重构任务里这是硬约束）。
- **Follow repository conventions**：命名、分层、目录、错误处理、提交信息风格都跟仓库走，仓库指令优先于本流程。
- **Avoid speculative abstractions**：不为"以后可能用到"提前抽象。抽象的门槛是"已经有两个以上真实重复点"。
- **Avoid unrelated cleanup**：不改与本次任务无关的代码。发现的问题记进报告的遗留项，不顺手清。
- **Prefer existing modules**：扩展现有 service、page、hook、component 和 abstractions；先查重，避免新增重复实现或无必要 wrapper。

## Bug 根因策略

Bug 修复遵循：

```text
Symptom → Evidence → Hypothesis → Validation → Root Cause → Fix → Retest → Regression
```

先取得可复查证据，再验证假设并定位根因。不得默认通过增加 timeout/retry、吞掉异常、删除断言、跳过/xfail 测试或 mock 掉真实行为来消除失败。只有证据表明这些是正确设计时才采用，并说明其如何解决根因。

## 具体禁令

- 禁止吞异常、静默失败、扩大 catch 范围、把错误变成默认值来"让测试变绿"。
- 禁止为了让旧代码不改而加适配层，除非适配层本身就是被请求的交付物。
- 禁止修改测试来迁就实现，除非测试断言的是被明确废弃的行为（并在报告中说明）。
- 禁止改动无关文件：格式化了整个目录、批量替换了全仓、顺手升了无关依赖。
- 禁止留下调试残留：`console.log`、临时注释、`TODO` 占位、注释掉的旧实现、生成的临时产物。
- 禁止写入密钥、凭据、真实环境地址到源码或日志。

## 需要停下来问的情况

只有这几种情况才回头找用户：

- 两种合理方案会导致返工，且仓库里找不到判断依据。
- 必须破坏兼容性，但用户没有授权破坏。
- 需要删除用户现有数据或撤销他们的未提交改动。
- 需要外部凭据或外部系统配合。

其余情况自己决策，并在日志里写下决策与理由。

## 与其它阶段的衔接

- 实现中发现的计划偏差：更新 `02-plan.md` 并记 `Scope Change` / 计划修正，不要默默换方向。
- 实现中新发现的既有 bug：记进 `09-final-report.md` 的遗留项，不在本任务里顺手修（除非它直接阻塞本次改动）。
- 完成后立刻进入 functional test，不要用"看起来对"替代验证。
