# Northstar Demo Shop

Run with the platform's Python environment: `pytest tests/test_shop.py`.
`tests/test_known_locator.py` intentionally fails on an obsolete locator. Use the platform's failure workflow to analyze, review, apply and verify a scoped repair.

`conftest.py` serves the shop from a random loopback port, launches real Chromium, isolates test data and captures PNG, DOM and Playwright trace evidence. The platform's live-browser plugin observes that same browser. No external site or login is needed.
