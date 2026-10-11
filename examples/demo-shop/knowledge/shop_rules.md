# Demo Shop QA contract

The shop runs locally through the `shop_url` fixture. Each test has a fresh browser context. Use `ShopPage`, `shop_data` and Playwright's independent `expect` assertions. Never weaken business assertions to make a test pass.

- AC-001: case-insensitive name search returns matching products only.
- AC-002: product detail displays the selected product and enabled Add to cart action.
- AC-003: selected color and size are retained when adding to the cart.
- AC-004: cart includes product, variant and quantity; line total = price × quantity; cart total = sum of line totals.
- AC-005: an unknown search displays an accessible empty state and no product cards.
- AC-006: adding the same variant twice merges quantities and recalculates the total.
- AC-007: category and maximum-price filters intersect; the maximum price is inclusive.
- AC-008: quantity increase/decrease and removal update the line, total, cart count and empty state.
- BR-001: product + color + size identify a cart line; identical variants merge.
- BR-002: line total = price × quantity; cart total = sum of line totals.
- BR-003: name search uses case-insensitive substring matching.
- BR-004: category and maximum price are combined with AND semantics.
- BR-005: a zero-quantity or removed line is absent from the cart.

Known locator failure: `legacy-add-cart` was removed. The real control is a button with accessible name `Add to cart` and test ID `add-to-cart`. The intentionally stale locator is isolated in `ShopPage.add_with_legacy_locator`; use the captured DOM and trace to diagnose it, and preserve the cart assertions.
