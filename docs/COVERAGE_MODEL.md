# Quality Coverage Model & Formulation

## 1. Principles of Deterministic Coverage

In the AI QA Platform, test coverage is formulated beyond traditional line/branch code coverage to ensure end-to-end alignment between product specifications and test automation.

```
Requirement
    ↓ (30% weight)
Test Design Dimensions
    ↓ (40% weight)
Structured Test Cases
    ↓ (30% weight)
Automation Binding (Playwright / Pytest)
```

## 2. Formulation

For each requirement $R_i$:
$$\text{Score}(R_i) = \min\left(100.0, 30 \cdot \mathbb{I}(\text{Designs} > 0) + 40 \cdot \mathbb{I}(\text{Cases} > 0) + 30 \cdot \mathbb{I}(\text{Automated} > 0)\right)$$

A requirement is considered **covered** if $\text{Score}(R_i) \ge 70\%$.

Overall Requirement Coverage is defined as:
$$\text{Cov}_{\text{req}} = \frac{\sum_{i=1}^{N} \mathbb{I}(\text{Score}(R_i) \ge 70\%)}{N} \times 100\%$$

## 3. Automation Coverage

$$\text{Cov}_{\text{auto}} = \frac{\text{Count}(\text{Cases with status AUTOMATED})}{\text{Total Test Cases}} \times 100\%$$

## 4. Execution Coverage

$$\text{Cov}_{\text{exec}} = \frac{\text{Count}(\text{Cases with executions in recent runs})}{\text{Total Test Cases}} \times 100\%$$
