---
name: framework-research
description: Research AI agent, browser automation, and engineering frameworks with source-verified releases, licenses, compatibility, costs, and fit. Use before evaluating, installing, or recommending a framework.
compatibility: Markdown workflow; requires read-only access to primary-source documentation and repository metadata for verification.
---

# Framework Research and Knowledge Reuse

## Safety

This is a read-only research workflow. Do not install packages, call paid providers, create accounts, run code from a candidate, alter repositories, or perform external writes. A separate human-authorized PoC must define environment, sample, budget, timeout, cleanup, and rollback. A researched capability is not a product acceptance result.

## Procedure

1. Read `engineering-knowledge/README.md` and `engineering-knowledge/index.md`; search prior records before opening external sources.
2. State one research question and the exact candidate/release scope. Avoid broad, unbounded browsing.
3. Prefer official GitHub release/tag metadata, source at that tag, the tag's license file, official docs, and package manifests. Record retrieval date and URLs. A moving docs page is not a version pin.
4. Record the required metadata using `engineering-knowledge/templates/research-record.md`: topic, question, URL, version, license, verified date, findings, limitations, applicability, evidence, confidence, related projects, next review, and status.
5. Distinguish: (a) source/documentation fact, (b) vendor claim, (c) inference, and (d) observed project experiment. Never treat (b) or (c) as (d).
6. Verify language/runtime/Playwright constraints from the exact manifest and dependency metadata. If transitive resolution or test execution is absent, mark compatibility UNKNOWN/NOT TESTED.
7. Identify existing-platform overlap. Prefer borrowing a pattern or writing an adapter through the existing runtime over creating a second scheduler, agent, provider, browser owner, event store, or approval system.
8. State costs only when sourced and scoped. Separate framework license, model/provider usage, hosted-browser fees, network traffic, and local infrastructure. Do not invent an estimate.
9. Update the topic record and `engineering-knowledge/index.md` together. Preserve earlier evidence and mark superseded information STALE rather than deleting it.
10. Ask a fresh independent critic for material adoption proposals. No vote can establish a technical fact or pass an architecture gate.

## Stop conditions

Stop and report UNKNOWN/BLOCKED if official sources are unavailable, license terms are ambiguous, required dependencies conflict, a paid provider is needed without explicit spend authorization, or the proposal implies replacing an existing Runtime/Provider/BrowserRuntime. Never upgrade a researched record to VERIFIED unless the exact claim has repeatable evidence.
