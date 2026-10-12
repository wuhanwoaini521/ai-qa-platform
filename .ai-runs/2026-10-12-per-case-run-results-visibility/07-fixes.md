# Fixes — Per-Case Run Results Visibility

- Replaced `aria-label` on a generic duration span (axe `aria-prohibited-attr` incomplete) with a visible translated duration label. Recheck: 0 violations and 0 incomplete items.
- Lowered the threshold for progressive full-error disclosure and enabled it for multiline messages so CSS line clamping never hides the remaining error without an expansion control.
- Changed ambiguous case-label separation to language-neutral punctuation.
- Removed the temporary browser network route and reloaded the real Run; verified the source still reports 7 passed / 1 failed. No persistent records were changed.
