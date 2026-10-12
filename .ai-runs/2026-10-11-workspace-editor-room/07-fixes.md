# Fixes

- Browser inspection at 390px found the fixed-width Studio explorer left the editor 8px wide. The embedded explorer now defaults closed on phones and is capped when reopened; verified editor width is 312px with the tree closed and 167px with it open at 390px.
- The provided timeline showed `AI Provider 不可用` even though model completion occurred and the health probe passed; its generic error advice also pointed to provider health. Root cause: `AIExecutionTimeline` treated any `run.failed` with model metadata as provider outage, and generic operation errors recommended checking the provider. Replaced the badge inference with explicit provider failure reasons and made generic advice provider-neutral; tested both generic ValueError and explicit provider-unavailable cases.
- Python language-service warning was not source-fixed: dependency is declared but the local native build of `nodejs-wheel-binaries` failed. No unsafe source workaround or lockfile edit was made.
