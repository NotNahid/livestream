# Contributing

1. Fork, create a branch, make your change.
2. `make lint && make test && python3 scripts/smoke_test.py` (needs `pip install -r requirements.txt -r requirements-dev.txt` and `playwright install chromium` for the smoke test).
3. Open a pull request. CI runs ruff, ShellCheck, unit tests, a headless-Chromium smoke test and a Docker build.

Adding a data source is the easiest contribution: one function with `@source("name")` in `agent.py`, plus a test in `tests/test_agent.py` that mocks the network call.

Keep the project dependency-free (standard library only) where possible.
