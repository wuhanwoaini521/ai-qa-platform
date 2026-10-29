# Browser Use — P0 framework record

- **Knowledge Status:** VERIFIED for tag/release/license/manifest/docs metadata only; platform behavior and compatibility are NOT TESTED.
- **Topic:** Python browser agent, local/hosted browser use, and model-provider integrations.
- **Research Question:** Does Browser Use improve autonomous page exploration over the current BrowserRuntime path without creating a second browser owner, and what version/license/cost applies?
- **Source URL(s):** [latest release metadata](https://api.github.com/repos/browser-use/browser-use/releases/latest); [release 0.13.14](https://github.com/browser-use/browser-use/releases/tag/0.13.14); [tagged README](https://github.com/browser-use/browser-use/blob/0.13.14/README.md); [tagged pyproject.toml](https://github.com/browser-use/browser-use/blob/0.13.14/pyproject.toml); [tagged LICENSE](https://github.com/browser-use/browser-use/blob/0.13.14/LICENSE); [official open-source quickstart](https://docs.browser-use.com/open-source/quickstart); [official supported models](https://docs.browser-use.com/open-source/supported-models).
- **Source Version:** 0.13.14, published 2026-10-26 (GitHub latest-release endpoint, retrieved 2026-10-28).
- **License:** MIT at tag 0.13.14.
- **Verified Date:** 2026-10-28.

## Findings

- The tagged manifest declares Python `>=3.11,<4.0`, which includes 3.13 as a declared range. The same manifest's optional `core` extra pins `browser-use-core==0.13.3` for listed platforms and includes `browser-use-sdk>=3.10.0,<4.0` in base dependencies. It does not declare a Playwright version in the inspected top-level manifest; transitive browser dependencies and Playwright 1.62.0 compatibility remain UNKNOWN.
- The tagged README and moving official quickstart describe a locally run Python agent that can use a local browser and multiple model integrations; hosted Browser Use browser/agent offerings are optional paths. The quickstart example creates a Python 3.12 environment; this is a documented example, not proof that 3.13 is unsupported (the pinned manifest declares `>=3.11,<4.0`). The official docs list examples for OpenAI, Anthropic, Gemini, Azure, Bedrock, Ollama, LangChain, LiteLLM and other OpenAI-compatible providers. This does not prove all custom endpoints work with this platform's structured request contract.
- The tagged README advertises hosted browser pricing “$0.02 per browser-hour plus network traffic.” This is an upstream published claim, not a quote or measured total cost. Model-provider charges and local-model compute are separate; no project cost was measured.

## Limitations

No install, dependency-resolution, local browser run, same-site benchmark, recovery experiment, model call, token measurement, or evidence comparison occurred. Docs are moving sources; tagged README/manifest are the version-pinned evidence. Browser Use agent reasoning would overlap current `TaskRuntimeService`, `BrowserRuntime`, action policy, evidence, and `DecisionService` provider/decision paths.

## Applicability

Only an isolated, same-task comparison is potentially useful if the current BrowserRuntime demonstrably cannot meet a real page-reasoning requirement. Keep BrowserRuntime as the sole platform browser owner; do not introduce Browser Use as an independent production agent loop. Current recommendation: **DEFER adoption; PoC not run**.

- **Evidence:** release metadata, tagged README/pyproject/license, official docs quickstart and models index read on 2026-10-28; existing baseline and its fixture limitations in [`docs/architecture-review/poc-results.md`](../../docs/architecture-review/poc-results.md); no Browser Use execution.
- **Confidence:** High for tag/license/manifest and published pricing claim; Medium for upstream-described capabilities; Low for local platform compatibility, performance and value.
- **Related Projects:** AI QA Platform; BrowserRuntime/Playwright; Browser Use open-source and cloud products.
- **Next Review Condition:** Before a PoC, verify the full dependency graph and Playwright 1.62.0 under a disposable env; compare identical loopback pages/tasks, bounded retries, deterministic assertions, cleanup and evidence; no paid browser/model usage without an explicit cap.
