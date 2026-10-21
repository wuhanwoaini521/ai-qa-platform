"""Some application modules under `app/api` are named after the resource they serve, and three of
them start with `test_` (`test_cases.py`, `test_designs.py`, `testrail.py`). They are routers, not
tests: without this, `pytest apps/api` imports them and collects their imported helpers as tests.
"""

collect_ignore_glob = ["app/api/*.py"]
