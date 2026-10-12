# Code Review — Structured Second Pass

## Scope and method

Reviewed the final diff and exercised high-risk boundaries across Jev parsing, DecisionService, Discovery ordering, Locator Apply eligibility, telemetry, migrations, and offline evaluation. A separate reviewer was not available in this environment; this is the required structured second-pass review, not a claim of independent sign-off.

## Findings and dispositions

1. **Discovery score could consume the daily call needed for action choice.** Fixed by reserving one daily request for the required choice; budget-exhaustion tests assert no browser action occurs.
2. **Fallback, low-confidence, malformed, or out-of-range values could be confused with usable advice.** Trust checks now require a Jev result, finite in-range scalar and confidence meeting the effective configured minimum. Locator blocks Apply only for a trusted below-threshold probability; unavailable/fallback values remain unavailable. Discovery preserves its previous order unless trusted scores exist.
3. **Offline samples from run event objects were not directly consumable.** The evaluator now normalizes flat samples and nested event metadata, with a regression test.
4. **Decision samples needed usable per-candidate performance context.** Discovery events and Locator summaries include decision point, provider/fallback, latency, and available token counts. Sensitive request content is not added to these events. Telemetry write failure is non-blocking.
5. **Safety and scope boundary.** Discovery scores only already-filtered candidates and do not replace the mandatory choice or browser guard. No decision signal changes test PASS/FAIL. The evaluator is local computation only.

No unresolved blocking findings. Focused and full regression evidence is in `04-functional-test.md` and `08-regression.md`.
