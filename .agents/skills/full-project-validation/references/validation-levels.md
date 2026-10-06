# Validation Levels

## Project Discovery Gate

Before choosing commands, inspect repository guidance such as `AGENTS.md`, the README, layout, and the files that actually define the project: package manifests and locks, runtime versions, build/test scripts, CI workflows, backend/frontend boundaries, service configuration, migrations, browser tooling, and external dependencies. Examples include `pyproject.toml`, `package.json`, `pnpm-workspace.yaml`, `Cargo.toml`, `go.mod`, `Makefile`, and Compose files; inspect only those present. Record the starting Git status so existing user changes remain distinguishable.

Do not assume a language, package manager, executable service, or validation command. Prefer scripts and checks already documented by the repository. Do not add tools or invent health rules just to fill a matrix cell.

Inspect recent commits and the current working-tree diff. Map recently changed modules, routes, and workflows into the validation matrix according to their impact; recent changes are risk evidence, not proof of a defect.

## Build the Validation Matrix

Plan applicable rows for the user's requested scope. Record command or action, result, evidence, and status. Use:

- `NOT APPLICABLE` when the project genuinely has no such layer or capability.
- `NOT AVAILABLE` when a relevant layer exists but this environment cannot run it, such as an unavailable browser, database, credential, or external service.
- `PASS` / `FAIL` only for checks that actually ran and produced evidence.

An unavailable required check is not a pass. Distinguish a product failure from an environment blocker in the finding and final verdict.

## Levels

1. **Repository / static health:** Run existing dependency-integrity, lint, formatting, type, build/compile, configuration/schema, generated-file, and doctor checks that apply. Capture actual commands and exit results.
2. **Automated tests:** Start with targeted fast suites, then integration and broader suites. Run the full suite when requested and feasible. Report exact suites and pass/fail/skip counts; never describe partial execution as full-suite success.
3. **Runtime health:** For runnable applications, start the relevant backend, frontend, worker, and safe local dependencies. Record startup commands, readiness, fatal errors, dependency connection, and migration state where applicable. A successful build alone is not runtime evidence. Never run migrations or writes against production data as a health check.
4. **API / service behavior:** Where APIs exist and the environment is safe, exercise representative success and error paths, response shape, and major integrations without mutating production data. Otherwise mark `NOT APPLICABLE` or `NOT AVAILABLE` with the reason.
5. **Browser and Golden Journey:** For Web products, follow `references/browser-and-golden-journey.md`; do not replace real UI verification with source inspection.

Run cheap, relevant checks first for useful failure localization, then widen coverage to match the user's scope and risk. A system-wide request should not stop after only a targeted test unless a blocker makes broader work impossible; report the limitation.
