# Failure Intelligence & Locator Self-Healing

The Failure Intelligence system automates test failure taxonomy classification, sensitive data redaction, and human-in-the-loop locator healing.

---

## 1. Failure Taxonomy Classification

Upon test failure, `FailureClassifier` analyzes pytest output and stack traces into structured categories:

| Category | Typical Signatures | Automatic Action |
|---|---|---|
| `LOCATOR_CHANGED` | `TimeoutError: waiting for locator(...)`, `Element not found` | Trigger `LocatorHealer` candidate proposal |
| `TIMING_ISSUE` | `TimeoutError: locator.to_be_visible() exceeded 5000ms`, `race condition` | Suggest explicit state waiting / auto-retry |
| `ASSERTION_FAILURE` | `AssertionError: assert actual == expected` | Flag business logic regression |
| `ENVIRONMENT_ERROR` | `ConnectionRefusedError`, `502 Bad Gateway`, `Database error` | Flag infrastructure dependency outage |
| `UNKNOWN` | Unmatched stack trace pattern | Route to generic root-cause diagnosis |

---

## 2. Sensitive Data Redaction

Before failure artifacts and logs are persisted or passed to AI models, `SensitiveRedactor` strips confidential data:
- Passwords (`password: "***"`, `pwd=***`)
- Bearer tokens (`Bearer eyJ...` → `Bearer [REDACTED]`)
- API keys (`AKIA...`, `sk-live-...` → `[REDACTED_API_KEY]`)
- Private secrets and Authorization headers

---

## 3. Human-in-the-Loop Locator Repair Workflow

```text
[ Test Execution Fails with TimeoutError ]
                  ↓
[ FailureClassifier captures broken locator: "#old-btn-id" ]
                  ↓
[ LocatorHealer scans Page Object files & proposes ranked candidates:
    1. data-testid="checkout-btn" (95% confidence)
    2. role="button", name="Checkout" (85% confidence)
    3. css=".checkout-submit" (70% confidence) ]
                  ↓
[ Generates Code Diff Preview:
    - self.submit_btn = page.locator("#old-btn-id")
    + self.submit_btn = page.locator("[data-testid='checkout-btn']") ]
                  ↓
[ User Reviews & Clicks "Apply Repair to Code" ]
                  ↓
[ Platform safely updates workspace Page Object file ]
                  ↓
[ User Clicks "Re-run Test Case" to verify fix passes ]
```

---

## 4. Strict Safety Principle: Proposal-Only

AI self-healing **NEVER** silently modifies code or alters test verdicts in the background:
- All repair proposals require explicit user inspection and approval (`POST /api/failures/{id}/apply-repair`).
- Re-run verification confirms fix correctness via standard pytest assertion.
