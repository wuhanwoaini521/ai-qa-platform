# Blockers

(none recorded yet)

## R17-B1 — acceptance data is not isolated from the demo project (BLOCKED, deferrable)

- What: every acceptance run that approves a discovery suggestion creates one ordinary test case in
  `proj_golden_shop_v1` (`tc_e5cbf1e12f6b`, `tc_fc72509f37fd`, …), and every Round 17 acceptance run
  creates two workflow definitions there. Coverage numbers for the demo project therefore include
  acceptance artefacts.
- Why not fixed now: a correct fix is an acceptance-only project with its own workspace, requirements
  and seeded run, wired into every acceptance script. Deleting the created rows instead would touch
  records that look like real cases (forbidden by the mission rules).
- Safe partial step taken: acceptance identifiers are timestamped and prefixed (`R17 验收 …`,
  `R17 镜像 …`, `R17 探针 …`) so they can be filtered or removed explicitly by a human.

## R18-B1 — multi-host consistency (BLOCKED)
No PostgreSQL server and no second host in this environment. The lease design is exercised by two real
processes against one SQLite file (8/8), but `FOR UPDATE`/`SKIP LOCKED`, cross-host clock skew and
connection-pool contention are untested. `MULTI_INSTANCE_PASS` must not be claimed.

## R18-B2 — cancel across replicas (known gap, not fenced)
`TaskCommandService.cancel` writes `CANCELLED` directly from whichever replica served the request; a terminal
write from the owner is fenced, a cancel is not. Fixing this needs a cancel-request row the owner polls.
