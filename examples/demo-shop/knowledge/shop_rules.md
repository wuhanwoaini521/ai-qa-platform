# Demo Shop QA contract

The shop runs locally through the `shop_url` fixture. Each test has a fresh browser context.
Use `ShopPage`, `shop_data` and Playwright's `expect`. Never replace business assertions to make a test pass.

- AC-001: case-insensitive search returns matching product names only.
- AC-002: product detail displays the selected product and enabled Add to cart action.
- AC-003: selectable color and size are retained when adding to the cart.
- AC-004: cart includes the selected product, variant, quantity and correct total.
- AC-005: unknown search displays a helpful empty state and no product cards.
- AC-006: adding the same variant twice merges quantities and recalculates the total.
- BR-001: product + color + size identify a cart line; identical variants merge.
- BR-002: line total = price × quantity; cart total = sum of line totals.
- BR-003: search matches product name, case-insensitively.

Known locator failure: `legacy-add-cart` was removed. The actual add action is a button with the accessible name `Add to cart` and test ID `add-to-cart`. Verify against captured DOM before proposing a change.
