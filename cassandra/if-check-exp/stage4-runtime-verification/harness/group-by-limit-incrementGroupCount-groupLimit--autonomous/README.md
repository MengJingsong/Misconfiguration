# Harness — group-by-limit-incrementGroupCount-groupLimit--autonomous

Stage-4 harness for the autonomous case file (`DataLimits.java:993`, `GroupByAwareCounter.incrementGroupCount()`); written 2026-10-27 on `pc12` (port slot 9, tag l79).
Adapted from the sibling harness `../group-limit-isdone-groupcounted--autonomous/` (same field `groupLimit`, other check site); the data sizes, the
group-limit sweep, the table layouts, the instruments for peak heap and bytes read, and the analyzers follow this case file's amendments A1-A14.
Frozen versions and the audit are in the results file (`../../results/group-by-limit-incrementGroupCount-groupLimit--autonomous.md`, section 1).
Working trees (made by `copy-source.sh`): `~/s4-b11-l79` (`ant build-test`; unit tier) and `~/s4-b11-l79-c` (`ant jar`; cluster tier). Logs: `~/s4-b11-l79-logs/`.
Scripts are called from this folder on the shared mount (`bash unit-run.sh`, `python3 cluster-run.py`).

| File | Tier | What it does | Checked how |
|---|---|---|---|
| `GroupLimitProbeTest.java` | unit (B2) | CQLTester probe, prints `L79` lines. W: the statement's own `DataLimits` counter over a raw read (groups, rowsCounted, isDone). E: the real `AggregationQueryPager` (fresh pager per client page from the previous `PagingState`) over a counting `QueryPager` wrapper: rows per sub-page, groups, sub-pages, exact thread-allocated bytes, summed heap-pool peaks (`peakPools`). C: control `SELECT * ... LIMIT n`. Datasets: S = 1 partition x 1,000,000 rows x 100 B read as slices `ck < r`; M = 1000 partitions x 1000 rows x 100 B. | shakedown at S 20,000 rows / M 1000 x 20 (renamed copy); caught a ClassCastException (a single-partition read query is a `SinglePartitionReadCommand.Group`) and `peakPools = 0` (pool names differ per collector; now all HEAP pools) |
| `unit-run.sh [run] [shakedown]` | unit | copies the probe into the tree, `ant testsome`, collects output, removes the probe, runs `unit-analyze.py` | shakedown |
| `unit-analyze.py` | unit | B2f/B2g as `EXPECTED:` lines (thresholds from the amended case file, sizes from the START line), matched B2g row | shakedown |
| `L79Jmx.java` | cluster | JMX helper: `serve` (stdin `alloc` = sum of `getThreadAllocatedBytes`, `heap`), `poll` (heap used every 100 ms) | shakedown |
| `groupby.btm` | cluster | Byteman observation rule, `GroupByAwareCounter.onClose` AT EXIT: `GB ms rows groups unfinished done`; each range sub-page read closes K = 4 counters (single-partition reads: 2); K is calibrated on the first-trigger query | shakedown (found K = 2 for a single-partition first-trigger query; now a range query) |
| `cluster-run.py <run> [shakedown]` | cluster | node on 127.0.9.1 (tmpfs, 1 GB heap, 600 s timeouts), Python-driver client, load, flush/compact, first-trigger check (`ks.g GROUP BY pk LIMIT 1` must show rows=300 groups=1 done=true), cells; per query: JVM allocation and `rchar` of `/proc/<pid>/io`; node stopped and tmpfs removed on any exit | shakedown at scale 50 |
| `cluster-analyze.py <dir>` | cluster | B3f/B3g as `EXPECTED:` lines, calibrates K, matched B3g row | shakedown |
| `selfcheck.py <run-dir>` | both | independent re-parse of the raw files (own code, not the analyzers) | run after run 1 |
