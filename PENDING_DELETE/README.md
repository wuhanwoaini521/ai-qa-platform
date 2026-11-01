# 待删除区

清单记录：本批暂存内容已于 2026-10-30 按用户授权删除，约 2.1 GiB；此文件保留作为清理审计记录。

## 2026-10-30：生成式测试临时产物

已删除 24 个旧临时目录。删除前内容包括 pytest 临时数据库、一次性测试 workspace、临时测试日志、缓存和旧 Playwright 浏览器 profile。项目 `.gitignore` 已将 `test-work` 视为 scratch；相关验收已结束。清理前对文档做过路径检索，没有发现对这些临时目录的直接引用。

### 旧 Discovery 测试工作区

- `.ai-runs/2026-10-09-quality-discovery/test-work/`

### 2026-10-24 UX 验收的 baseline 临时区

- `.ai-runs/2026-10-24-ux-redesign/second-round-acceptance/baseline/tmp/`
- `.ai-runs/2026-10-24-ux-redesign/second-round-acceptance/baseline/test-tmp/`
- `.ai-runs/2026-10-24-ux-redesign/second-round-acceptance/baseline/security-tmp/`
- `.ai-runs/2026-10-24-ux-redesign/second-round-acceptance/baseline/targeted-tmp/`

### 2026-10-24 UX 验收的 evidence 临时区

- `.ai-runs/2026-10-24-ux-redesign/second-round-acceptance/evidence/tmp/`
- `.ai-runs/2026-10-24-ux-redesign/second-round-acceptance/evidence/discovery-test-tmp/`
- `.ai-runs/2026-10-24-ux-redesign/second-round-acceptance/evidence/discovery-test-tmp2/`
- `.ai-runs/2026-10-24-ux-redesign/second-round-acceptance/evidence/focused-api-tmp/`
- `.ai-runs/2026-10-24-ux-redesign/second-round-acceptance/evidence/focused-api-tmp2/`
- `.ai-runs/2026-10-24-ux-redesign/second-round-acceptance/evidence/full-api-test-tmp/`
- `.ai-runs/2026-10-24-ux-redesign/second-round-acceptance/evidence/security-test-tmp/`
- `.ai-runs/2026-10-24-ux-redesign/second-round-acceptance/evidence/test-tmp/`
- `.ai-runs/2026-10-24-ux-redesign/second-round-acceptance/evidence/test-tmp2/` through `test-tmp11/`
- `.ai-runs/2026-10-24-ux-redesign/second-round-acceptance/evidence/workflow-test-tmp/`

删除前，每个原始路径都曾镜像保存在 `PENDING_DELETE/2026-10-30-generated-test-scratch/` 下；本批内容现已删除，不能再从待删除区恢复。

## 保留范围

正式测试日志、最终验收报告、截图与浏览器证据均留在原位置；也未移动 `docs/audits/`、`reports/`、`docs/agent-handoff.md`、架构文档、项目源码/测试，或 `runtime/` 的项目运行数据与产物。2026-10-24 验收结论仍见 `.ai-runs/2026-10-24-ux-redesign/second-round-acceptance/02-final-report.md`。
