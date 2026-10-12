# Request

让 Locator Repair 的 Verification 能恢复失败时的页面状态：先审查当前失败采集；增加 `FailureSnapshotBundle`（URL、storage_state、a11y 树、脱敏 DOM、失败 locator、上次通过元素基线指纹，缺失基线明确标注）；在 pytest/live-browser 插件采集，经 `SensitiveRedactor` 后落盘；storage_state 加密并设 TTL。Verification Browser 优先恢复 storage_state，恢复失败说明原因，不得伪称已回放。有副作用步骤不可自动重放，DTO 说明只恢复到最近安全点。验收包含登录保护页面 fixture 修复流程和现场缺失时“证据不足”。

保护已有工作区改动；不引入平行执行路径；提交与否由用户后续决定，本次不提交其他文件。
