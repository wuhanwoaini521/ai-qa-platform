# 需求与用例页面完整性改进

- run-date: 2026-11-03
- task-type: ui-feature
- scale: standard

## Original Request

用户 m01924 要求完成现有“需求与用例”页面的实现、验证和证据交付，保留“需求 / 测试用例 / 需求追踪”三个视图。主要目标：修复表格列宽和标题可读性；统一中英文标题/导航/面包屑；明确分离需求状态、用例关联、自动化状态、执行结果；让未关联需求与独立用例卡片提供准确筛选；补齐详情、关联已有用例、新建用例、验收标准编辑等实际流程；保存/刷新后状态同步，失败保留输入并可重试；收紧顶部布局和提供真正可用的主操作。

必须遵循：已有需求标题不得批量重写；不从标题相似度合并；不把关系等同于验收点覆盖、自动化或执行通过；没有可靠来源字段不伪造 Discovery 来源；没有显式验收点映射不得显示覆盖率；无可靠执行映射时显示“暂无执行数据”；不升级多对多、不加无用字段/迁移、不引入新工作流或 AI 链路。复用现有接口、表单、详情逻辑和 i18n。

真实浏览器验收视口：1280×800、1440×900、1920×1080。场景包括三标签、搜索/筛选/清除、统计卡路由、展开/折叠、详情打开关闭、关联已有用例并刷新、新建带需求上下文/取消无残留、验收标准编辑并刷新、长标题/零关联/空列表/加载失败/保存失败、键盘/可见焦点/无障碍名称。保存默认列表、需求详情、关联操作三种关键状态的截图。运行相关测试、类型检查、lint、build、i18n 检查。最终 PASS/PARTIAL/BLOCKED 必须与证据一致；不提交、不推送、不部署。

## Resolved Scope

仅扩展现有 `ProjectManagementPage` 和现有接口/字段。优先修复现有布局与关联失败状态；使用现有 `RequirementFormModal` / `TestCaseFormModal` 创建；为需求详情增加页面内抽屉并复用现有验收标准 ID 保留逻辑。只在字段真实存在时展示来源/更新时间；不添加需求优先级、负责人、模块字段，因为当前模型没有这些字段。执行结果只在准确的用例绑定、项目、运行、执行映射及环境/时间/运行入口可确认时呈现，否则显示“暂无执行数据”。

## Repository / Branch / Initial Git Status

- Repository: `/home/hans/self-github/ai-qa-platform`
- Branch: `feat/project-requirements-navigation`
- Base/HEAD at task start: `941823433d57a745aaacf6e73fccdffb085fb5d0`
- Existing uncommitted user/project work: seven tracked changes from the preceding project-navigation task; preserve them. Existing untracked `.ai-runs/**` and `runtime/backups/**` are also protected.
- No changes for this task at initial status. No staging/commit/push/deploy authorized.
