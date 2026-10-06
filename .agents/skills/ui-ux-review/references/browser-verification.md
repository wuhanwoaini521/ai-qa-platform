# Browser Verification and Accessibility

## Real UI Evidence

When the product can run and a reliable browser or existing E2E capability is available, inspect the actual product in the browser. Exercise the in-scope Golden Journey and representative primary interactions. Check rendering at the supported viewport, navigation, resulting state, visible errors, relevant console errors, and failed requests that affect the flow. Source and DOM inspection help explain behavior but do not replace interaction evidence.

If browser capability or a safe runnable environment is unavailable, report `Browser verification: NOT AVAILABLE` and identify the missing interaction evidence. A screenshot supports visual findings only; it does not prove that navigation, controls, persistence, or a workflow works. Distinguish **visual evidence** from **interaction evidence** in the report.

For responsive products, check key supported desktop and mobile/tablet breakpoints rather than every size. Look for clipped content, broken grids, unreachable controls, modal overflow, and unusable density.

## Basic Accessibility Review

As relevant to the observed flow, check keyboard access, visible focus, semantic labels and accessible names, text contrast, form labels and associated errors, and dialog focus behavior. Report concrete blockers and the tested scope. This is a practical accessibility review, not a formal WCAG certification or conformance audit.
