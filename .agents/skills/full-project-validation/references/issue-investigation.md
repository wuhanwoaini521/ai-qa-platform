# Issue Investigation

## Classify Findings

Use one primary category: Build, Dependency, Test, Runtime, API, Network, Browser, UI, Data, Integration, Environment, Configuration, or Unknown. Keep classification simple; add detail in the evidence rather than inventing a new taxonomy.

| Severity | Meaning |
| --- | --- |
| P0 | Core application unavailable, data corruption/loss, or severe system-wide blocker. |
| P1 | Core Golden Journey fails or a high-impact primary capability is unavailable. |
| P2 | A non-core feature fails or a clear but contained user-facing problem exists. |
| P3 | Minor polish or low-impact issue with a practical workaround. |

## Preserve Evidence and Find Cause

For each real failure, record its request/route/command, expected versus observed behavior, relevant logs or output, environment, and reproduction steps. Follow:

```text
Symptom → Evidence → Reproduction → Hypothesis → Validation → Root Cause
```

Validate the hypothesis before calling it a root cause. In Audit Mode, investigation may end at a well-supported `Probable root cause`; label uncertainty clearly. Do not imply a repair occurred.

## Product Failure vs Environment Blocker

- **PRODUCT FAILURE:** the project violates expected behavior in a supported, correctly configured test/runtime environment.
- **ENVIRONMENT BLOCKER:** a required external condition is unavailable, such as credentials, browser support, database/service, network access, or a test-only dependency.

An obsolete test or broken fixture may explain a test failure without proving product failure; preserve evidence and verify it. Do not label an environment blocker as a product defect or dismiss a reproducible product failure as environmental. If an environment blocker prevents a critical validation, the final verdict cannot be `PASS` solely because the checks that did run passed.
