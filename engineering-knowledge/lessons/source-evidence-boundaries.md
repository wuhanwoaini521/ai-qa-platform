# Lesson: Separate Source Verification from Runtime Compatibility

- **Knowledge Status:** DOCUMENTED.
- **Topic:** Evidence provenance in framework evaluation.
- **Research Question:** What can official release/tag/license/manifest and documentation checks prove, and what still requires a platform PoC?
- **Source URL(s):** [GitHub REST releases API](https://docs.github.com/en/rest/releases/releases); [GitHub repository contents API](https://docs.github.com/en/rest/repos/contents); [LangGraph release](https://github.com/langchain-ai/langgraph/releases/tag/1.2.18); [Browser Use release](https://github.com/browser-use/browser-use/releases/tag/0.13.14); [Skyvern release](https://github.com/Skyvern-AI/skyvern/releases/tag/v1.0.56).
- **Source Version:** Official source pages retrieved 2026-10-28; each framework record pins its own tag.
- **License:** N/A to this general process; candidate licenses recorded per framework.
- **Verified Date:** 2026-10-28.

## Findings

A pinned source file can verify what that release declares (for example, Python range or license text). Official docs can verify what the vendor documents/claims. Neither proves actual dependency resolution, local deployment success, Playwright compatibility, behavior against the platform, token cost, deterministic evidence, or lifecycle recovery. Those require a bounded experiment and exact environment/test evidence. State the scope of each `VERIFIED` label in the record.

## Limitations

This lesson summarizes this research batch; independent cross-project replication has not been performed. Tool responses and moving documentation can change; pinned tags are preferable for reproducibility.

## Applicability

Use in OSS/framework selection, dependency review, competitive analysis and architecture gate discussions. Keep provider cost, hosted browser pricing, local compute, license and platform integration as separate questions.

- **Evidence:** three release metadata results; tagged LICENSE and pyproject/README files; official documentation pages; no candidate package installed or executed.
- **Confidence:** High for the evidence-method distinction; no claim that any candidate is technically compatible.
- **Related Projects:** AI QA Platform and any project performing framework due diligence.
- **Next Review Condition:** Review after a framework research/PoC finds a case where official source claims were insufficient or misleading.
