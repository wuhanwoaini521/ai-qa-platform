# Analysis

## Architecture and impact

`PlaywrightBrowserRuntime.create_session()` creates the browser context for quality discovery and browser-task inspection. It defaults to `BrowserSettings.headless`, currently `true`; the context was created without a User-Agent override. The same adapter is used by multiple browser workflows, so a focused fix here covers the shared behavior.

## Evidence and root cause

- The project runtime in headless mode reproduced `Page.goto: net::ERR_HTTP2_PROTOCOL_ERROR` for `https://www.uniqlo.com.hk/zh_HK/`.
- Headless Chrome exposed a `HeadlessChrome/...` User-Agent; headed Chrome on the same host reached the page with HTTP 200.
- Headless Chrome with a standard Chrome User-Agent (same browser version/platform) also reached the page with HTTP 200. This isolates the cause to the headless User-Agent being rejected by the target edge, rather than URL validation, exploration policy, or general network connectivity.
- The project already supports headless execution and must not require a visible GUI. Setting `headless=False` globally is therefore not an acceptable fix.

## Decision and risk

For headless Chromium contexts, supply a normal Chrome User-Agent derived from the running browser version and host platform. Keep headed contexts unchanged. Do not change webdriver signals, add retries, disable HTTP/2, or configure a proxy; those are unnecessary for the reproduced cause. Risk is MEDIUM because the adapter is shared across browser workflows.
