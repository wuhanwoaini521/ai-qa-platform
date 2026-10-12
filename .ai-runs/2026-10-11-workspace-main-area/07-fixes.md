# Review Fixes

- run-date: 2026-10-11

## Findings fixed
- At 360px, the Explorer was about 122px wide; row actions intercepted taps on filenames. Made the <=820px Explorer a 230px overlay and close it after file selection. Verified with actual file opening at 360, 390, and 768px.
- At 360x640, embedded context plus bottom/status/editor toolbar chrome left Monaco only 14px high. Embedded context now starts closed but stays accessible in More Tools; mobile scrolling no longer reserves the obsolete 58px footer gap; toolbar is compact, status chrome is hidden, and Problems remains available from More Tools. Final Monaco height measured 169px.
- No further fix items remain.
