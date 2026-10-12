# Implementation

- `apps/api/app/services/quality_discovery_service.py`: before treating a fallback as a fatal run error, check whether Jev returned a valid attempted candidate rejected specifically for `below_minimum_confidence` or `confidence_missing`. Mark only that option `SKIPPED`, record why, emit an activity event, and continue the bounded loop. Do not execute the rejected option or lower the minimum-confidence threshold. Provider fallbacks without a valid attempted candidate remain blocked when `require_jev=true`.
- `apps/api/tests/test_quality_discovery.py`: added an API-level regression proving a low-confidence candidate is skipped, a later confident Jev decision can execute, and provider fallback without an attempted candidate remains blocked.
- The previously blocked persisted user run was not rewritten or resumed; it is terminal and remains intact.
