# 实际检查

- `mise exec -- pnpm --filter @ai-qa/web test`：初次运行 316/317，唯一失败为仍期望 v0.8.1 的版本契约；同步到用户已确认的 v0.9.0/7ae760f 后 317/317，退出码 0。
- `mise exec -- pnpm --filter @ai-qa/web exec node --experimental-strip-types --test tests/dashboard-model.test.mjs tests/design-system.test.mjs`：最终样式调整后 12/12，退出码 0。
- `mise exec -- pnpm --filter @ai-qa/web lint`：退出码 0；最终源文件版本再次运行亦为 0。
- `mise exec -- python scripts/task.py build`：最终生产构建退出码 0，TypeScript 和 Vite 完成，3,687 modules、59.18s；保留既有 Monaco chunk 大于 500kB 提示。
- `git diff --check`：无报错。
- 以上 shell 命令均以 rtk 执行。默认沙箱的 Node runner/esbuild spawn EPERM 后，在授权的沙箱外重跑成功，没有修改产品代码规避限制。
- 浏览器命令：`mise exec -- uv --cache-dir runtime/uv-cache run --no-sync python output/playwright/dashboard-review.py`。脚本开头断言 Playwright == 1.62.0，最终退出码 0。
- 浏览器脚本前两次中断来自检查本身：程序化 focus 尚未进入键盘模式、workspace 路径实际含 project ID 且参数为 nodeid；依真实交互/路由修正检查后执行成功。未因此修改产品导航或弱化断言。
