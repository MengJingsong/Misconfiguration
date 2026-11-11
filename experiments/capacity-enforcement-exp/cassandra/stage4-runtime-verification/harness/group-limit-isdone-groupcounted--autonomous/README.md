# Harness — group-limit-isdone-groupcounted--autonomous

Stage-4 harness for the autonomous case file (`DataLimits.java:1013`, `GroupByAwareCounter.isDone()`); written 2026-10-27 on `pc07` (port slot 2, tag g72).
Frozen versions and the audit are in the results file (`../../results/group-limit-isdone-groupcounted--autonomous.md`, section 1).
Working trees (made by `copy-source.sh`): `~/s4-b11-g72` (`ant build-test`; unit tier) and `~/s4-b11-g72-c` (`ant jar`; cluster tier). Logs: `~/s4-b11-g72-logs/`.

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `GroupByLimitMemoryTest.java` | unit (B2) | CQLTester probe, prints `G72` lines. W: the statement's own `DataLimits` counter over a raw read (groups, rowsCounted, isDone). E: the real `AggregationQueryPager` (fresh pager per page from the previous `PagingState`, as the request path) over a counting `QueryPager` wrapper: rows per sub-page, groups, sub-pages, exact thread-allocated bytes. C: control `SELECT * ... LIMIT`. Datasets: S = 1 partition x 20000 rows x 1 KB; M = 20000 partitions x 1 row x 1 KB. | shakedown at 2000 rows (renamed copy); the first shakedown caught three instrument faults (row count 0 from a transformation that skipped rows, reuse of one pager across pages tripping an assertion in `CQLGroupByPagingLimits.newCounter`, lower-case booleans) |
| `unit-run.sh [run] [shakedown]` | unit | copies the probe into the tree, `ant testsome`, collects output, removes the probe, runs `unit-analyze.py` | shakedown |
| `unit-analyze.py` | unit | B2f/B2g as `EXPECTED:` lines (thresholds from the amended case file), matched B2g row | shakedown |
| `G72Jmx.java` | cluster | JMX helper: `serve` (stdin `alloc` = sum of `getThreadAllocatedBytes` over all threads, `heap`), `poll` (heap used every 100 ms) | shakedown |
| `groupby.btm` | cluster | Byteman observation rule, `GroupByAwareCounter.onClose` AT EXIT: `GB ms rows groups unfinished done`; each sub-page read closes K = 4 counters (calibrated on the first-trigger query) | shakedown: first-trigger query shows K=4 identical lines |
| `cluster-run.py <run> [shakedown]` | cluster | node on 127.0.2.1 (tmpfs, 512 MB heap), Python-driver client, load, flush/compact, first-trigger check (many-groups L=1 P=100 must show rows=1 groups=1 done=true), cells; node stopped and tmpfs removed on any exit | shakedown at scale 50 (found `statusbinary` prints "not yet running", which contains "running") |
| `cluster-analyze.py <dir>` | cluster | B3f/B3g as `EXPECTED:` lines, calibrates K, matched B3g row | shakedown |
