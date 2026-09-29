# Automation Workspace Quickstart

This workspace contains six small, executable pytest examples. They exercise an in-memory login
flow and shopping cart, so no browser, external service, credentials, or test data setup is needed.

## Files

- `tests/`: runnable tests; start with `tests/test_login.py::test_login_flow`.
- `flows/`: the example login flow under test.
- `components/`: the example cart calculation under test.
- `pages/`: a place for page objects when you connect a real browser application.
- `knowledge/`: the expected behavior illustrated by the tests.

## Run

From this workspace directory, after setting up the platform's dependencies:

```bash
mise exec -- uv run pytest
```

In Automation Studio, open the Test Explorer and run a test, or start a run with no test selection
to execute the whole `tests/` directory. Both routes use the same pytest tests.

These files demonstrate the execution flow. Replace the in-memory example with tests for your own
application when you are ready.

