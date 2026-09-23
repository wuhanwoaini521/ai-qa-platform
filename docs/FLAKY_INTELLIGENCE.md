# Flaky Test Intelligence & Scoring Model

## 1. Deterministic Flaky Scoring Formula
The platform computes a deterministic instability score $S \in [0.0, 1.0]$ based on historical runs:

$$S = 0.45 \cdot \text{alternation\_rate} + 0.35 \cdot \text{rerun\_recovery\_rate} + 0.20 \cdot \text{recent\_instability}$$

### Metrics
1. **Alternation Rate**: Frequency of status flips ($P \leftrightarrow F$) between consecutive runs.
2. **Rerun Recovery Rate**: Ratio of tests that failed on first attempt but passed on immediate retry within the same run.
3. **Recent Instability**: Weighted failure rate over the most recent 5 executions.

---

## 2. Minimum Sample Protection
To prevent 1 failed execution from flagging a test as 100% flaky:
- If total sample count $< 3$: The score returns classification `INSUFFICIENT_DATA`.
- Confidence is calculated as:
  $$\text{confidence} = \min\left(1.0, \frac{\text{sample\_count}}{10}\right)$$

---

## 3. Classifications
- `STABLE`: Score $< 0.15$ with adequate sample count.
- `LIKELY_FLAKY`: Score $\ge 0.15$ with alternation or rerun recovery.
- `PERSISTENT_FAILURE`: High failure rate without recovery/alternation.
- `INSUFFICIENT_DATA`: Sample count below minimum threshold.

---

## 4. No Auto-Skip Policy
The platform **never** modifies tests with `@pytest.mark.skip` automatically when flaky. Flakiness is surfaced via intelligence dashboards (`/flaky`) and test detail badges, empowering engineers to fix race conditions without hiding defects.
