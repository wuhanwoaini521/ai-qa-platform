# QA Core Contracts & Protocols

`packages/qa-core` is the core domain engine of the platform, independent of web frameworks and database implementations.

## Key Protocols

| Protocol | Responsibility | Inputs | Outputs |
| -------- | -------------- | ------ | ------- |
| `TestRunner` | Cross-framework test execution | `ExecutionRequest` | `ExecutionReport` |
| `FailureAnalyzer` | Root-cause diagnosis & failure taxonomy | `FailureContext` | `FailureAnalysis` |
| `TestAuthor` | Automated test script generation | `AuthoringRequest` | `AuthoringResult` |
| `LocatorHealer` | Locator repair proposal (never mutates code) | `HealingRequest` | `HealingResult` |
| `BrowserExplorer` | Bounded UI exploration session | `url` | `ExplorationSession` |
| `QAOrchestrator` | Coordinated run, diagnosis, and healing | `ExecutionRequest` | `(ExecutionReport, list[FailureAnalysis])` |

---

## Deterministic Fake Implementations

For local platform development, CI workflows, and frontend simulation, `qa-core` provides full fake implementations:
- `FakeTestRunner`
- `FakeFailureAnalyzer`
- `FakeTestAuthor`
- `FakeLocatorHealer`
- `FakeBrowserExplorer`
- `FakeQAOrchestrator`

These fakes allow testing of complete end-to-end flows without external dependencies on browser binaries, CI servers, or live LLM APIs.
