<!-- file: cases/cql-row-limit-incrementRowCount-rowsCounted--autonomous.md -->
# CQL row limit (CQLLimits.rowLimit) — verification solution

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/filter/DataLimits.java:509` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude (claude-sonnet-5-5), Claude Code CLI, 2026-10-27 (design only, nothing run) |
| Estimate | `negative`: `rowLimit` is a count of CQL rows, not bytes. Heap or off-heap use per query is count x row width, and the width is not bounded by this check. |
| Ground | `incrementRowCount()` (`DataLimits.java:507-513`) compares a row counter, `rowsCounted`, with the int `rowLimit`. A row has no size cap here. Cell and value sizes are only bounded elsewhere (`max_value_size`, mutation size, byte-based guardrails). The check also fires after a row has been read and counted, so the row that reaches the limit is already in memory. Memory-sized caps in this area are byte-based and sit elsewhere: `coordinator_read_size_*`, `local_read_size_*`, `page_size_*` (bytes) and the paging byte limit. |

## A. Constraint trace

**A1. The constraint.** It is the CQL row limit, `CQLLimits.rowLimit` (`DataLimits.java:349`). The check at the target line is `if (++rowsCounted >= rowLimit) stop();` (`:509-510`). Kind: runtime-queried, per-query value. It is first declared as the final field `rowLimit` of `CQLLimits` (`:349`), set in the constructor (`:365-370`). Its sources are:
- User `LIMIT n`. `SelectStatement.getLimit` (`SelectStatement.java:947-965`) parses it and requires it to be > 0. `getDataLimits` (`:884-920`) passes it to `DataLimits.cqlLimits(cqlRowLimit, cqlPerPartitionLimit)` (`:920`), unless post-query ordering or aggregation is in use (`:890-896`).
- Paging. `CQLLimits.forPaging(pageSize)` (`DataLimits.java:392-395`) replaces `rowLimit` with the page size. The same happens for `CQLPagingLimits` and for `forShortReadRetry` (`:402-405`).
- Row cache fill. `CacheService.java:420` calls `DataLimits.cqlLimits(rowsToCache)`. `rowsToCache` is the table option `caching = {'rows_per_partition': N}` (`CachingParams.java:51`, default 0).

Unit: CQL rows. Default: `DataLimits.NO_LIMIT = Integer.MAX_VALUE` (`:48`). `cqlLimits(NO_LIMIT)` returns the shared `NONE` instance (`:97-100`). `NONE` and `DISTINCT_NONE` (`:50`, `:83`) do not stop early. `NONE` skips the counting filter altogether (`:59-78`). Settable: per statement `LIMIT`, and driver page size (native protocol, per request); `rows_per_partition` through `ALTER TABLE`. No restart is needed for any of them. The default page size is `SelectStatement.DEFAULT_PAGE_SIZE = 10000` (`:114`), and it is applied only to GROUP BY and aggregation (`:900-903`).

**A2. What it caps.** It caps the number of live CQL rows a counted iterator returns. The compared quantity is `rowsCounted` (`:466`), incremented in `applyToRow` for live rows (`:489-494`) and for static-only partitions (`:502-503`). The resource affected is heap on the coordinator and replicas: result rows, `ResultSet` building and the merged iterators. Row-cache rows are on-heap or off-heap (OHC) when `rowsToCache` is the limit. Memory in bytes is not what is compared.

**A3. Mechanism.**
1. `Counter.applyTo` wraps an iterator with a `StoppingTransformation` (`:233-273`). `attachTo(BasePartitions)` stops at once if `isDone()` (`:318-325`).
2. For every live row, `applyToRow` calls `incrementRowCount()` (`:489-494`).
3. At the limit, `stop()` ends the whole iteration (`:509-510`). `stopInPartition()` ends the current partition once `perPartitionLimit` is hit (`:511-512`).
4. `isDone()` is `rowsCounted >= rowLimit` (`:535-538`). `isDoneForPartition()` is `isDone() || rowsInCurrentPartition >= perPartitionLimit` (`:540-543`).
5. The `NO_LIMIT` case never stops. `DataLimits.NONE` skips even the counting transform.

Bypasses and overshoot:
- Row width is unbounded by this check: one row can hold many cells or large values, up to `max_value_size` per value (`cassandra.yaml:1864`).
- The overshoot is one row. The row that reaches the limit has already been read.
- Tombstones and non-live rows are not counted (`:491`, `isLive`). A scan can therefore read many dead rows or tombstones (`tombstone_failure_threshold: 100000`, `cassandra.yaml:1815`) without reaching the limit.
- Replica-side read-repair or short-read protection can issue new reads with a different `rowLimit` (`forShortReadRetry`, `:402-405`).
- Post-ordering and aggregation queries set `cqlRowLimit = NO_LIMIT` (`SelectStatement.java:890-896`). The user LIMIT is applied after all rows are collected, so the counter does not bound memory in those cases.
- The `RangeCommandIterator` counter is built from `DataLimits.NONE` and is used only for counting (`RangeCommandIterator.java:253-254`).

**A4. Other consumers.** The heap is also used by memtables, the key and row caches, the chunk cache, compaction and the internode buffers. Per-query memory also depends on the partition and row widths, on the read consistency level (the number of replica responses held at the coordinator), and on page size in bytes. Guardrails that bound bytes are `page_size_warn/fail_threshold`, `coordinator_read_size_*`, `local_read_size_*`, `row_index_read_size_*` (`cassandra.yaml:2017-2030`, `:2089-2090`).

**A5. Evidence beyond the source.** Cassandra CQL documentation for `SELECT ... LIMIT` and paging: https://cassandra.apache.org/doc/5.0/cassandra/developing/cql/dml.html. The row-cache `rows_per_partition` option is documented in the CQL DDL page, https://cassandra.apache.org/doc/5.0/cassandra/developing/cql/ddl.html. Nothing else relied on. The source comments at `SelectStatement.java:1131` mention that LIMIT 1 can still read oversized rows.

## B. Verification solution

**B1. Claim under test.** Raising or lowering the CQL row limit does not bound memory by itself. For a fixed LIMIT, the peak memory of a query scales with row width (and with the number of tombstones scanned), so there is no row-count-derived byte bound. Row count alone predicts memory only when the width is held constant.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant, in a local-disk copy of the tag (`rsync -a ~/cassandra-5.0.9/ /tmp/c509/`). Build with `ant jar` and `ant build-test`. Add a JUnit test class, for example `test/unit/org/apache/cassandra/db/filter/RowLimitMemoryTest.java`, in the copy only. Run it with `ant testsome -Dtest.name=RowLimitMemoryTest`. JVM options: `-Xmx1g -XX:+UseSerialGC` (a deterministic collector), `-Dcassandra.config=file:///tmp/c509/test/conf/cassandra.yaml`.

**B2b. Knobs.** The varied values are:
- `rowLimit` in {1, 100, 1_000, 10_000, 1_000_000} through `DataLimits.cqlLimits(n)`, plus `NO_LIMIT` (the `NONE` path). **[Amended 2026-10-27: 1_000 added; pairs are run only where limit x (about 300 B row overhead + width) is at most 300 MB: width 16 B with limits 1, 100, 1_000, 10_000, 1_000_000; width 1 KiB with 1, 100, 1_000, 10_000; width 64 KiB with 1, 100, 1_000. The other pairs are skipped (they would exceed the 1 GiB test JVM; the original text itself said to choose pairs under 700 MB).]**
- Row width, with the cell value size in {16 B, 1 KiB, 64 KiB}.
- `perPartitionLimit` stays `NO_LIMIT` in the main series. One extra run uses `cqlLimits(rowLimit, 10)` to confirm the per-partition path.

**B2c. Workload.** Build an in-memory `UnfilteredRowIterator` of 1_200_000 synthetic live rows (**amended 2026-10-27: was 2_000_000; 1_200_000 exceeds the largest limit, 1_000_000, and keeps the NONE series under about 300 MB**), using `BTreeRow.singleCellRow` over a one-column `TableMetadata` (a `CQLTester` table). Generation is lazy. **[Amended 2026-10-27: each row gets its own freshly allocated value buffer of the stated width. The original "value buffers are reused" would make every retained row share one buffer, so retained heap would not depend on width and the series could not show the claim.]** Retain the rows that pass the counter into a `List<Row>` (the "consumer"). For each (limit, width) pair, wrap with `limits.filter(iter, nowInSec, false)` and drain. Arithmetic: at limit n the consumer holds exactly n rows (so the limit is reached for n < 2_000_000), and the retained bytes are about n x (row overhead + width). At n=1_000_000 and 64 KiB the retained rows exceed 64 GB, so the 1 GB heap is hit first. Choose the largest pairs so that the retained size stays under 300 MB (amended 2026-10-27, see B2b for the grid actually run).

**B2d. Observables and instruments.**
- `counter.rowsCounted()` and `counter.isDone()` after the drain.
- Number of rows that came out of the iterator (a count in the consumer).
- Retained bytes: heap used after a forced `System.gc()`, via `Runtime.totalMemory()-freeMemory()`, and, as a second measure, the sum of `Row.unsharedHeapSize()` over the retained rows (amended 2026-10-27: `jol` is not on the classpath; it is not used). The JVM `-Xlog:gc` output is a cross-check.
- Not observable directly: the transient memory in the merge path and the one extra row that was read to trigger the stop.

**B2e. Procedure.**
1. Copy the tree, build, add the test class.
2. For each (rowLimit, width), run the drain in a fresh test method, after `System.gc()` take a baseline, drain, `System.gc()` again, record retained bytes and the three counts.
3. Repeat each point 5 times and take the median. (Amended 2026-10-27: each repetition forces `System.gc()` three times, 100 ms apart, before each heap reading; retained bytes of a point are the heap after the drain minus the baseline taken before it, with the list still referenced.)
4. Run the `NONE` series with the smallest width only (1_200_000 x 16 B).
5. Run the dead-row series. Mix 90% tombstoned rows (`isLive` false) into the source with the live rows and check that `rowsCounted` ignores them. (Amended 2026-10-27: row i is live when i mod 10 = 0 and a deleted-row marker otherwise, width 16 B, limits 1, 100, 1_000; `DataLimits.filter(UnfilteredRowIterator, ...)` builds its counter with `assumeLiveData=false` (`DataLimits.java:210-216`), so dead rows are tested by the same call as the main series.)
6. Run the positive control (B2h).

**B2f. Predictions.** Stated before any run. **[Amended 2026-10-27, before any reading: the qualitative lines are made numeric; the claim and the meaning of the readings are unchanged. Notation: R(w, L) is the median retained heap, in bytes, of width w (bytes) and limit L; m(w) is the retained bytes per extra row: (R(w, 10000) - R(w, 1000)) / 9000 for w = 16 and 1024, and (R(w, 1000) - R(w, 100)) / 900 for w = 65536 (the largest pair that fits the 300 MB rule). A shakedown on the instrument (not a reading of the final run) showed a noise of about 0.3 MB in a retained-heap reading, so differences are taken over the widest pairs.]**
- `rowsCounted == rowLimit` and the output row count equals `rowLimit` for every limit < source size in every pair run. With `NONE`, the output is 1_200_000.
- For a fixed width, retained bytes grow linearly with `rowLimit`: the retained bytes per row, R(w, L) / L, agree within 0.75 to 1.35 between L = 10_000 and L = 1_000_000 for w = 16, and between L = 100 and L = 1_000 for w = 65536 (points with R below 2 MB are not used).
- At the same `rowLimit`, retained bytes grow with width: m(1024) - m(16) is at least 0.9 x (1024 - 16) and at most 1.15 x (1024 - 16) + 64 (every extra payload byte is retained once; allowance for 8-byte alignment and reading noise), and the same for m(65536) - m(16) with 65536 - 16. m(65536) / m(16) is at least 50. The same holds for the sum of `Row.unsharedHeapSize()`.
- At constant `rowLimit`, there is no plateau in bytes as width grows, so no byte bound.
- Tombstoned rows add to the source consumption but not to `rowsCounted`: in the dead-row series `rowsCounted == L`, the output has L live rows (`Row.hasLiveData`), and the rows pulled from the source (live and deleted) are between 10 x L - 9 and 10 x L + 1.
- Positive control (B2h): with the byte stop at 8 MiB (sum of `Row.unsharedHeapSize()` of the retained rows), the retained `unsharedHeapSize` sum for every width is at least 8 MiB and less than 8 MiB plus one row, and the retained heap is within 0.8 to 1.3 x (8 MiB + one row), flat across widths, while the row-limit series moves with width.
- The claim would be wrong if retained bytes at a fixed `rowLimit` were flat across widths (m(65536) - m(16) < 0.1 x 65520).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Retained bytes at fixed limit grow with width (m(65536) / m(16) >= 50 and the slope bounds of B2f hold) while `rowsCounted` is constant | Claim confirmed: the row limit does not bound bytes. |
| Retained bytes at fixed limit flat across widths (m(65536) - m(16) < 0.1 x 65520) | Claim refuted: something in the path bounds bytes per row (investigate where). |
| Retained bytes follow `rowLimit` only for the constant-width series | Expected: usage follows the knob, but only through count x width. Not a refutation of the claim by itself. |
| Positive control (byte-bounded size) stays flat or capped as width grows while the row-limit series grows | Claim confirmed. |
| `rowsCounted != rowLimit` for a source larger than the limit | The mechanism does not work as traced. Re-read A3. |
| The positive control does not move with its knob, or the limit is never reached | Not confirmed. Fix the harness. |
| Dead rows counted into `rowsCounted` | The trace of `isLive` (`:491`) is wrong. |

**B2h. Controls.** Positive control, a cap known to bind: replace the row count with a byte bound, such as stopping when a running `row.unsharedHeapSize()` sum reaches 8 MiB (a harness-side stop, which stands in for byte-paging; amended 2026-10-27: the consumer ends the drain and closes the iterator when the sum reaches 8 MiB, on the same source and with `DataLimits.NONE`; it is a stand-in for a byte cap, and the cluster tier's control uses a real one). The same workload then keeps retained bytes about at 8 MiB for every width, while the row-limit series moves with width. Other controls: the same width with `NONE` to show the bound is real (retained bytes grow to the full source size); `perPartitionLimit` run to show it is a count too; use the same synthetic source in all runs and a full GC before each reading.

### B3. Cluster tier

**[Amended 2026-10-27 in the stage-4 audit, before any reading, with these reasons that do not depend on a reading: (1) the data volumes of the original text (a partition of 100_000 rows of 10 KiB, 2_000 of 1 MiB; unpaged LIMIT 100_000 on 10 KiB rows = 1 GB) cannot be answered by a 2 GB heap and ended in "Not confirmed" by its own table; (2) its prediction "more than 100x from 100 B to 10 KiB" ignores the per-row overhead (a 100 B row costs about 1 KB to allocate), so even a correct run would miss it; (3) the Python driver pages at 5000 rows by default, so "unpaged" needs `fetch_size=None`; (4) the row-cache control compares counts and does not move the same resource; it is replaced by a byte-based guardrail, a cap known to bind (`local_read_size_fail_threshold`, case `local_read_size_fail_threshold-addSize-failBytes--guided`, cluster tier Confirmed). The claim (B1) is unchanged.]**

**B3a. Environment and build.** One node (single node, RF=1), a local-disk copy of the tag (`copy-source.sh`), built with `ant jar`, JDK 11. `conf/cassandra.yaml`: `data_file_directories`, `commitlog_directory`, `saved_caches_directory` and `hints_directory` on a tmpfs of known size (126 GB free; the data set is under 0.5 GB), `num_tokens: 1`, `row_cache_size: 0MiB`, `key_cache_size: 100MiB`, `read_request_timeout: 60000ms`, `native_transport_timeout: 60000ms` (so that a 100 MB read is not timed out), `auto_snapshot: false`. Guardrails at their defaults in the first node lifetime (U, uncapped): `read_thresholds_enabled` false. In the second lifetime (C, control): `read_thresholds_enabled: true` and `local_read_size_fail_threshold: 20MiB`. JVM options: `-Xms2G -Xmx2G`, `-XX:+UseG1GC`, `-XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=<tmpfs>/dumps`. Client: the bundled Python driver (protocol 4, `fetch_size=None` for unpaged).

**B3b. Knobs.** CQL `LIMIT` in {10, 100, 1_000, 10_000, 100_000, none} (`none` = no LIMIT clause, the default); row width in {100 B, 10 KiB, 100 KiB} set by the written value size; driver fetch size (paging) in {unpaged, a stated value}. Control knob: `local_read_size_fail_threshold` (a byte cap on the same read, replica side) at 20 MiB in lifetime C against off in lifetime U.

**B3c. Workload.** Three tables, each one partition (`pk = 1`) with clustering rows, written at CL=ONE through the driver, then flushed and compacted (compression disabled): `ks.t_small` 120_000 rows of 100 B (about 12 MB), `ks.t_med` 1_200 rows of 10 KiB (about 12 MB), `ks.t_big` 1_200 rows of 100 KiB (about 120 MB). Each partition has more rows than the largest LIMIT run on it. Queries (`SELECT * FROM ks.<t> WHERE pk=1 [LIMIT n]`):
- Lifetime U, unpaged: `t_small` with n in {10, 100, 1_000, 10_000, 100_000, none}; `t_med` and `t_big` with n in {10, 100, 1_000, none}. Paged: `t_big` n=1_000 with fetch size 100; `t_small` n=100_000 with fetch size 5000.
- Lifetime C, unpaged: `t_big` n in {100, 1_000, none}; `t_med` n=1_000; `t_small` n=100_000.
- Every query 3 times, in a seeded shuffled order, 5 s apart, with `jcmd GC.run` and 3 s of quiet before each. Arithmetic: the largest result is 120 MB (`t_big`, none) against a 2 GB heap; 56 queries in U, 15 in C, a few seconds each; the whole tier takes about 15 minutes plus two node starts.

**B3d. Observables and instruments.**
- A (primary): bytes allocated during a query, the sum over all JVM threads of `ThreadMXBean.getThreadAllocatedBytes` read over JMX every 25 ms; A of a query is the last sample before its start to the first sample at least 1 s after the client has the full answer, minus the idle drift (the rate measured over the 3 s before the query times the window length). Allocation is a proxy for memory pressure, not retained memory: the gap is that garbage is counted and live bytes are not; it is used because the live set of a single transient query cannot be read from outside.
- H (secondary): peak `HeapMemoryUsage.used` in the window minus the median of the samples in the 1 s before it (a G1 collection inside the window lowers it; reported, not used for the verdict).
- Per-page A for paged queries: the client records each page's start and end; A of a page is the sample-to-sample delta around it.
- Client side: rows returned, payload bytes (sum of the value lengths), pages, elapsed time, the error type of a failed query.
- `system.log` ERROR lines and `Read on table` messages; `nodetool tablestats` for the data size.
- Not directly visible: the live set of a single query on the coordinator.

**B3e. Procedure.**
1. Copy the tag to local disk, build, write the yaml, start the node (lifetime U), check `nodetool status` and `statusbinary`.
2. Create tables, load, flush, compact. Warm-up: each query shape once, unrecorded.
3. Run the lifetime U queries as B3c, sampling as B3d. First-trigger check: the first query (`t_big`, n=1_000) must return 1_000 rows and allocate at least 50 MB; if not, stop (exit 3).
4. Stop the node (drain, SIGTERM), start it again with the control yaml (lifetime C) on the same data, run the lifetime C queries. First-trigger check: `t_big` n=1_000 must fail with a read-size abort (otherwise stop).
5. Stop the node and check with `ps` that no `CassandraDaemon` of this tree is left; delete the tmpfs data.

**B3f. Predictions.** Stated before any run. Notation: A(t, n) is the median over the 3 repeats of A for table t and LIMIT n (unpaged, lifetime U); a(t) = (A(t, 1000) - A(t, 10)) / 990 is the marginal allocated bytes per extra row, which removes the fixed per-query cost.
- Rows returned equal min(LIMIT, rows in the partition) for every query of lifetime U (paged: the sum over pages). This shows the limit works as a row count.
- Width at fixed LIMIT: a(t_med) - a(t_small) is at least 1.0 x (10240 - 100) and a(t_big) - a(t_med) is at least 1.0 x (102400 - 10240) (every payload byte is allocated at least once), and each is at most 10 x that width difference. A(t_small, 1000) < A(t_med, 1000) < A(t_big, 1000), and A(t_big, 1000) is at least 100 MB (the payload is 102 MB).
- Same width, LIMIT: for each table A(t, n) increases with n. For `t_small` the marginal bytes per row between 10_000 and 100_000, (A(100000) - A(10000)) / 90000, and between 1_000 and 10_000, (A(10000) - A(1000)) / 9000, are within 0.5 to 2 x of each other; for `t_med` and `t_big` the same for (A(1000) - A(100)) / 900 and (A(100) - A(10)) / 90.
- `none` on `t_big` returns 1_200 rows and A(t_big, none) > A(t_big, 1000).
- Paging: `t_big` n=1_000 fetch size 100 returns 1_000 rows in 10 pages (11 if the pager ends with an empty page; the instrument check showed that an exhausted LIMIT can leave a final empty page when the partition is shorter than the LIMIT), its total A is within 0.5 to 2 x of A(t_big, 1000) unpaged, and its largest per-page A is at most 0.25 x A(t_big, 1000) unpaged. Paging is a count too (`forPaging`, `:392-395`) and bounds the per-request bytes only through count x width.
- Control (lifetime C, `local_read_size_fail_threshold` 20 MiB, a byte cap): `t_big` n=1_000 and n=none fail on all 3 repeats with a read-size abort; `t_big` n=100, `t_med` n=1_000 and `t_small` n=100_000 (each under 20 MiB of payload) return the full answer with A within 0.5 to 2 x of lifetime U; A_C(t_big, 1000) is at most 0.5 x A_U(t_big, 1000); and A_C(t_big, 1000) is within 0.5 to 2 x of A_C(t_big, none) (the bytes stop following the LIMIT once the byte cap binds).
- The claim would be wrong if a(t_med) - a(t_small) < 0.1 x (10240 - 100) (flat across widths at fixed LIMIT).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| The first-trigger checks hold, the width and control predictions of B3f hold: a(t_med) - a(t_small) >= 1.0 x 10140, a(t_big) - a(t_med) >= 1.0 x 92160, the control aborts and caps A | Claim confirmed: the row limit does not bound memory by itself; usage follows count x width; a byte cap on the same workload does bind. Effect: does not cap. |
| a(t_med) - a(t_small) < 0.1 x 10140 and a(t_big) - a(t_med) < 0.1 x 92160 (flat across widths at fixed LIMIT) while the control moved | Claim refuted: some other bound applies per row. Investigate. |
| A grows with LIMIT at fixed width (the LIMIT-series prediction) | Usage follows the knob only through count x width. Consistent with the claim, not a refutation by itself. |
| The width slopes fall between 0.1 and 1.0 times the width difference, or are above 10 times | Not confirmed (partial: some per-row bytes are not payload, or the instrument is wrong). |
| The control does not abort or does not cap A (A_C(t_big, 1000) > 0.5 x A_U(t_big, 1000)), or the limit is never reached, or the node OOMs or times out before measuring | Not confirmed. Re-size and repeat, or record the defect. |
| Rows returned > LIMIT | The mechanism is not working as traced. |
| Anything else | Not confirmed (no matching row). |

**B3h. Controls.** A byte cap on the same workload and instruments: lifetime C (above). The same query with LIMIT removed (the `NONE` path) gives the upper bound. 3 repeats per point with a GC before each; no concurrent client load. **[Amended 2026-10-27: "the same data and queries with `-Xmx4G`" and "one run with tracing on" are not run: allocation is counted per thread and does not depend on the heap size, and the rows read per replica are not needed for the claim; the row-cache control of the original text is dropped (reason in the amendment note above).]**

**B4. Risks and cleanup.** Disk: unit tier needs none beyond the build (about 2 GB under the tree). Cluster tier (amended 2026-10-27): data about 150 MB on tmpfs, no result larger than 120 MB against a 2 GB heap; a heap dump (up to 2 GB) would go to the tmpfs. Nothing is written to shared storage or to the shared source tree. Cleanup: `nodetool drain`, kill the pid, verify with `ps` (by this tree's path) that no `CassandraDaemon` or `surefire` process is left, then remove the tree and tmpfs directories.

## C. Sources read

- `~/writeup-A/playbook-autonomous.md`
- `~/writeup-A/_TEMPLATE-autonomous.md`
- `src/java/org/apache/cassandra/db/filter/DataLimits.java` (lines 40-590)
- `src/java/org/apache/cassandra/cql3/statements/SelectStatement.java` (lines 885-925 and grep hits)
- `src/java/org/apache/cassandra/service/CacheService.java` (lines 395-430)
- `src/java/org/apache/cassandra/service/reads/range/RangeCommandIterator.java` (grep hit)
- `src/java/org/apache/cassandra/schema/CachingParams.java` (grep hits)
- `src/java/org/apache/cassandra/config/GuardrailsOptions.java` (grep hits)
- `conf/cassandra.yaml` (grep hits)
- https://cassandra.apache.org/doc/5.0/cassandra/developing/cql/dml.html (cited, not fetched)

## D. Stage-4 feedback

**Run 1, 2026-10-27 (results `stage4-runtime-verification/results/cql-row-limit-incrementRowCount-rowsCounted--autonomous.md`; uncommitted, the orchestrator commits): Unit **Confirmed** — does not cap; cluster **Confirmed** — does not cap. Outcome class: true negative.** Unit: the bytes per extra row grow with the width (301 B at 16 B, 1 318 B at 1 KiB, 65 829 B at 64 KiB; ratio 218.6) while `rowsCounted == rowLimit` in every pair; dead rows are not counted (L live rows from 10L-9 pulled); a consumer byte stop at 8 MiB keeps about 8.5 MB for every width. Cluster: at a fixed LIMIT the allocated bytes per extra row are 1.3 KB (100 B rows), 42 KB (10 KiB) and 415 KB (100 KiB), i.e. about 4.04 x the payload; LIMIT 1 000 on 100 KiB rows allocates 416 MB; paging with fetch size 100 bounds the largest page at 0.14 x the unpaged query; a byte cap (`local_read_size_fail_threshold` 20 MiB) holds the same workload to 73.6 MB at LIMIT 1 000 and at none. Misses recorded, not tuned: one of 15 unit control repetitions read 3.7 MB (medians hold), and `t_small` LIMIT 100 000 was aborted by the 20 MiB guardrail although its payload is 12 MB (the local-read size counts row heap, not payload). No section of the case needs correcting beyond the amendments below; the Estimate line stands.

**Stage-4 audit amendments, 2026-10-27 (made before any reading; the claim B1 is unchanged; results file `results/cql-row-limit-incrementRowCount-rowsCounted--autonomous.md`):**
1. B2b: limit 1_000 added; the pairs run are limited to limit x (about 300 B + width) <= 300 MB (the original grid contained 1_000_000 x 64 KiB and 10_000 x 64 KiB).
2. B2c: the "value buffers are reused" text is replaced by a fresh buffer per row (a shared buffer makes retained heap independent of width); source 1_200_000 rows (was 2_000_000).
3. B2d/B2e: `jol` dropped (not on the classpath), `Row.unsharedHeapSize()` sum added; GC protocol and the dead-row series fixed (checked: `DataLimits.filter(UnfilteredRowIterator ...)` builds its counter with `assumeLiveData=false`, `DataLimits.java:210-216`; the `PartitionIterator` variant uses `true`).
4. B2f/B2g: numeric relations (marginal bytes per row m(w), slope bounds, pulled-row bounds, control bounds) replace "about linear" and ">50x"; B2h: the stop is driven through the counter.
5. B3 rewritten (reasons at its head): data volumes rescaled, the "more than 100x" prediction replaced by a marginal-bytes-per-row slope (the per-row overhead was ignored), unpaged needs `fetch_size=None`, allocation counter as the primary observable, a byte guardrail (`local_read_size_fail_threshold`) as the positive control in place of the row-cache control, `-Xmx4G` and tracing controls not run.
6. Found at the instrument check on small data (a shakedown, not a reading of the final run, before the freeze): the retained-heap reading has a noise of about 0.3 MB, so B2f takes slopes over the widest limit pairs and linearity only for readings of at least 2 MB; a paged query whose LIMIT equals the rows available may end with an empty page (B3f accepts 10 or 11 pages, 20 or 21); the per-page allocation is read by interpolating the cumulative counter (samples are 26 ms apart, a page takes 40 to 80 ms). The shakedown also showed the control working (a read-size abort at 21 MB with `local_read_size_fail_threshold` 20 MiB) and an allocation of about 4.6 x the payload for a 100 KiB row.
7. Citations checked against the pinned source (all hold): `DataLimits.java:48,50,83,349,365-370,392-395,402-405,466,507-513,535-543`; `SelectStatement.java:114,881-920,889-895`; `CacheService.java:420`; `RangeCommandIterator.java:253`. `:509-512` are the two `if` statements and their `stop()` / `stopInPartition()` calls as cited.

