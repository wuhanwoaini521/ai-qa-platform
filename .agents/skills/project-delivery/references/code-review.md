# Code Review

每次交付任务都要做，且必须**独立于实现过程**。Review 以本次 diff 和实际行为为证据，不复述实现者的意图。

## 独立性要求

- 环境提供独立 reviewer 且委派已获授权时，优先由不同 reviewer 执行；否则实现者串行切换视角，重新读 diff 并做结构化 second pass。
- prompt 用挑战式措辞，逼迫 reviewer 找问题：

```text
Find concrete reasons this implementation should not be accepted yet.
```

- 不接受"看起来没问题"、"格式良好"、"已经加了注释"这类结论。
- 没有 subagent 时，串行执行，但 review 阶段要显式切换视角：重新读 diff，而不是回忆刚才写了什么。

## 检查维度

- **Correctness**：逻辑是否正确，边界与异常路径是否成立。
- **Behavior changes**：实际行为有没有超出请求范围。
- **Edge cases**：空值、边界值、并发、重复调用、失败重试。
- **Error handling**：错误是否被正确传播；有没有吞异常、静默失败、宽泛 catch。
- **Duplication**：是否复制了仓库里已有的能力。
- **Complexity**：是否引入了不必要的抽象层或状态。
- **Maintainability**：半年后的人能不能读懂；命名、注释与结构是否一致。
- **Test coverage**：新增逻辑有没有对应验证，bug 有没有被锁住。
- **API compatibility**：签名、返回值、异常契约、序列化格式有没有被破坏。
- **Security-sensitive behavior**：鉴权、输入校验、注入、路径处理、密钥处理。

## Reviewer 不该做的事

- 只看格式不看逻辑。
- 要求与仓库约定无关的"更好写法"。
- 把个人风格偏好升格为阻断项。
- 在没读调用方的情况下断言兼容性安全。

## 分级与出口

- **P0 / Critical**：可能导致数据损坏、严重安全影响或核心功能不可用。必须修复；未解决阻断 `PASS`。
- **P1 / High**：真实正确性、兼容性、回归、安全问题，或本次范围内的重要测试缺口。属于正确性/安全/兼容/回归阻断的问题必须修复；未解决阻断 `PASS`。
- **P2 / Medium**：非阻断的可维护性、韧性或测试改进。结合范围处理；未处理时记录理由和风险。
- **P3 / Low**：风格、偏好或纯未来建议。可记录，不阻断。

范围外或其他非阻断的 P1 改进可以留作 remaining risk，但必须明确 scope、影响和 disposition。不能把未解决的正确性或安全问题降级为"建议"来通过验收。Review blocker = 未解决 P0，以及正确性/安全/兼容/回归类 P1。

出口条件：review blockers 清零；其他保留项有明确记录。P2/P3 不驱动无限打磨。

## 记录位置

写进 `06-code-review.md`：正确性、可维护性、复杂度、重复、错误处理、兼容性、测试覆盖、问题清单。
