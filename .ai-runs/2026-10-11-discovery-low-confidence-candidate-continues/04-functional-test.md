# Functional Test

- `.venv/bin/pytest apps/api/tests/test_quality_discovery.py apps/api/tests/test_decision_layer.py apps/api/tests/test_browser_runtime.py -q` — 78 passed.
- After adding the explicit required-Jev fallback assertion: `.venv/bin/pytest apps/api/tests/test_quality_discovery.py::test_low_confidence_jev_candidate_is_skipped_and_discovery_continues apps/api/tests/test_quality_discovery.py::test_jev_fallback_after_real_choice_preserves_provider_and_blocks_next_candidate -q` — 2 passed.
- `.venv/bin/ruff check apps/api/app/services/quality_discovery_service.py apps/api/tests/test_quality_discovery.py` — passed.
- `git diff --check -- apps/api/app/services/quality_discovery_service.py apps/api/tests/test_quality_discovery.py` — passed.

Regression uses deterministic fixture AI/Jev and a local fixture browser. No live Jev request or new external-site exploration was triggered.
