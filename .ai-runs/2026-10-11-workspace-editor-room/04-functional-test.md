# Functional Tests

- `pnpm --filter @ai-qa/web test` — PASS, 109 tests.
- `pnpm --filter @ai-qa/web lint` — PASS.
- `pnpm --filter @ai-qa/web build` — PASS (`tsc -b` + Vite). Existing chunk-size warning remains for the large Monaco bundle.
- `uv run --no-sync --project apps/api pytest -q apps/api/tests/test_runtime_operation_stream.py apps/api/tests/test_ai_execution_trace.py` — PASS, 20 tests.
- Live Playwright UI against the running app (Chrome; 1524×906, 1024×768, 390×844, 360×800): automation context collapses, existing toggle reopens it, other stages retain context, phone file explorer defaults closed and can be reopened, and no horizontal document overflow was observed.
- Live Playwright with an intercepted automation SSE (no generation request or data mutation): post-model `ValueError` remains labeled as an execution failure with a real-provider badge; an explicit `provider_unavailable` failure receives the unavailable badge. No browser page errors or failed requests.
- `/api/ai/settings` and `/api/ai/status`: configured DeepSeek model and synthetic streaming health probe are currently READY.
- `uv sync --all-packages --locked` — BLOCKED: building declared `basedpyright` dependency `nodejs-wheel-binaries` fails on this macOS toolchain (`std::vector` compile errors). The current `.venv` still cannot import `basedpyright`; API health continues to report Python language service missing. No dependency or lockfile changes were made.
