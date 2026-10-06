# Browser Verification and Golden Journey

## Browser Verification

For a Web application, use an existing E2E suite or reliable browser capability when available. Launch the app in the repository's supported local/test environment and exercise real pages and interactions; reading JSX, HTML, or CSS is not browser verification.

Check the routes and interactions relevant to scope: page load, primary navigation and actions, forms/dialogs/menus, loading/empty/error states, persisted result where relevant, obvious layout breakage, console errors, and failed requests that affect the flow. Avoid mechanically clicking every DOM element. Do not clear or alter real user data to create a test case.

If the application has UI but browser capability is unavailable, record exactly `Browser verification: NOT AVAILABLE` and why. For a UI-heavy product this usually means `PARTIAL`, unless existing executed E2E evidence provides an adequate equivalent for the critical UI behavior. If the project has no UI, mark browser verification `NOT APPLICABLE`.

For broad multi-page requests, use a coverage matrix instead of claiming exhaustive button coverage:

| Page / feature | Priority | Load | Primary action | Navigation / result | Error state | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| Example | P0–P3 | result | result | result | result / N/A | command, route, or trace |

Choose P0 for the core value path, P1 for frequent major functions, P2 for secondary pages, and P3 for low-risk auxiliary areas. Include every page the user explicitly requested or list it as unverified.

## Golden Journey

Identify the project's Golden Journey: the end-to-end workflow that best represents its core user value. Infer it from the README, navigation/routes, existing E2E tests, product documentation, main workflow, and recent changes. Prefer the core value chain over the easiest automation target. Do not copy generic examples from another product.

State the chosen journey as concrete user-visible steps, then identify, execute, and report it. Record the observed result at each important boundary, including persisted state, service response, or visible outcome as applicable. If the journey cannot be run, give the blocker and mark it `NOT AVAILABLE`; do not infer success from unrelated tests.
