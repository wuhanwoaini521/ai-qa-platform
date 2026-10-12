# Regression Summary

- Final source version verified after extracting the selection model.
- `pnpm --filter @ai-qa/web test`: 117 passed, 0 failed.
- `pnpm --filter @ai-qa/web lint`: passed.
- `pnpm --filter @ai-qa/web typecheck`: passed.
- `pnpm --filter @ai-qa/web build`: passed; Vite emitted the repository's existing Monaco large-chunk warning.
- `git diff --check`: passed.
- Live browser: actual single-requirement state stayed visible with the context rail collapsed. A temporary mocked multi-requirement response proved option choice updates requirement ID, detail title, and URL. Mock route was removed; real state restored.
- Responsive checks: 1280×900, 768×1024, and 390×844. Document width matched viewport at each size; actions remained available.
- Light and dark theme inspected. Real restored page reported no page errors.
- No backend tests run; no backend/API code changed.
