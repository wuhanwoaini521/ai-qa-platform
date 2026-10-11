# Northstar Demo Shop

A self-contained local e-commerce system under test for the platform's Golden Demo lifecycle. The existing application is reused rather than introduced as a separate execution framework. It serves a real catalog, case-insensitive search, category/maximum-price filters, product details, variant selection, cart quantity updates/removal, and calculated totals. Each Playwright test owns a fresh browser context and cart.

## Run the browser suite

```bash
cd examples/demo-shop
uv run pytest
```

`tests/test_known_locator.py::test_known_locator_change` is intentionally red before repair: its Page Object calls a removed `legacy-add-cart` selector while the actual button remains available as `Add to cart` / `add-to-cart`. Use its screenshot, DOM and trace through the platform's Failure workflow; do not change the business assertions to hide the failure.

The fixture serves the shop on an ephemeral loopback port, launches real Chromium, and captures screenshots, HTML and Playwright traces. `QA_ARTIFACT_DIR` can point evidence to an isolated run directory. The platform's Golden Demo seed copies this checked-in project to its project workspace once; do not reset a populated project to refresh it.

## Business contract

- AC-001: case-insensitive name search returns matching products only.
- AC-002: product detail shows name, price and an enabled add action.
- AC-003: selected color and size are retained in the cart.
- AC-004: cart quantity and totals use the independent oracle `unit price × quantity`.
- AC-005: unmatched searches have an accessible empty state and no product cards.
- AC-006: adding the same variant twice merges the line and recalculates the total.
- AC-007: category and maximum-price filters intersect; the price boundary is inclusive.
- AC-008: quantity changes/removal update line totals, cart total and the empty state.

Cart state is intentionally in-memory and per browser context: no account, external service, network dependency, or shared mutable data is required.
