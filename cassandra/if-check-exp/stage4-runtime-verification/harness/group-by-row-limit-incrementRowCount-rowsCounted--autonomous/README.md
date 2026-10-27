# Harness — group-by-row-limit-incrementRowCount-rowsCounted--autonomous

Stage-4 harness for the autonomous case file (`DataLimits.java:986`, `GroupByAwareCounter.incrementRowCount()`); written 2026-10-27 on `pc07` (port slot 8, tag b78). Adapted from the sibling harness `group-limit-isdone-groupcounted--autonomous` (same code path, different constraint).
Frozen versions and the audit are in the results file (`../../results/group-by-row-limit-incrementRowCount-rowsCounted--autonomous.md`, section 1).
Working trees (made by `copy-source.sh`): `~/s4-b11-b78` (`ant build-test`; unit tier) and `~/s4-b11-b78-c` (`ant jar`; cluster tier). Logs: `~/s4-b11-b78-logs/`.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `GroupByRowLimitTest.java` | unit (B2) | CQLTester probe, prints `B78` lines. W: the statement's own `DataLimits` counter over a raw read of one sub-page (groups, rowsCounted, isDone). B: serialised size of the first sub-read's data response (`createResponse` + `ReadResponse.serializer.serializedSize`). E: the real `AggregationQueryPager` (fresh pager per client page from the previous `PagingState`) over a counting `QueryPager` wrapper: rows per sub-read, sub-reads, client pages, exact thread-allocated bytes. C: control `SELECT ... LIMIT p`. Dataset: 1 partition x 50000 rows x 1 KiB, `count(v)`. | shakedown at 2000 rows (renamed copy): found one instrument fault (a single-partition SELECT yields a `SinglePartitionReadCommand.Group`, not a `ReadCommand`) and one prediction error not tied to any reading (p=1 makes a second client page: amendment A10) |
| `unit-run.sh [run] [shakedown]` | unit | copies the probe into the tree, `ant testsome`, collects output, removes the probe, runs `unit-analyze.py` | shakedown |
| `unit-analyze.py` | unit | B2f/B2g as `EXPECTED:` lines, matched B2g row | shakedown |
| `B78Jmx.java` | cluster | JMX helper: `poll` (heap used every 100 ms, per node) | shakedown |
| `rowlimit.btm` | cluster | Byteman observation rule, `GroupByAwareCounter.onClose` AT EXIT: `GB ms rows groups unfinished done`; K counters close per sub-read, K calibrated on a one-sub-read query | shakedown: K=2 |
| `cluster-run.py <run> [shakedown]` | cluster | two nodes on 127.0.8.1/.2 (tmpfs, 512 MB heap, PasswordAuthenticator, role `app`), Python-driver client, load, flush/compact, calibration and first-trigger check (fetch-1000 GROUP BY must show sub-reads of 1000 rows with the group unfinished), fetch grid, plain SELECT * control, 100-byte control, guardrail arm; nodes stopped and tmpfs removed on any exit | shakedown at scale 50 (4000 rows) |
| `cluster-analyze.py <dir>` | cluster | B3f/B3g as `EXPECTED:` lines; definitions of "peak above baseline" (post-GC occupancy), "severe GC" and "near baseline" fixed in its docstring before any reading | shakedown |
| `selfcheck.py` | both | independent re-parse of the raw logs | (written for step 4) |
