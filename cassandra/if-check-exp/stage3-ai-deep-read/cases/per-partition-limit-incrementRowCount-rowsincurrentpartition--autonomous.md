<!-- file: cases/per-partition-limit-incrementRowCount-rowsincurrentpartition--autonomous.md -->
# CQL PER PARTITION LIMIT (CQLLimits.perPartitionLimit) — verification solution

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/filter/DataLimits.java:511` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude (Sonnet 5.5), Claude Code CLI, 2026-10-27 |
| Estimate | `negative`: the value is a per-query, client-supplied row cap that defaults to unlimited, and it counts live rows, not bytes or memory. It is not a node-level resource constraint. |
| Ground | It is set per statement by the client (`PER PARTITION LIMIT n`), not by node configuration. The default is `NO_LIMIT` (Integer.MAX_VALUE). It stops iteration after n live rows per partition, but it does not bound row width, cell size or tombstones scanned. It is ignored for aggregates. **[Amended 2026-10-27: not ignored but rejected: `PER PARTITION LIMIT` is not allowed with aggregate queries (`SelectStatement.java:1247-1248`) or with DISTINCT (`:1236`); only the internal `AGGREGATE_EVERYTHING` path leaves it at `NO_LIMIT` (`:889-897`). The estimate is unchanged.]** So node heap and disk use are governed by other mechanisms (paging, read thresholds, tombstone limits). |

## A. Constraint trace

**A1. The constraint.** `CQLLimits.perPartitionLimit`, an `int` field (`DataLimits.java:350`). Kind: per-query runtime value, not a yaml key, `-D` property or constant. The only related constant is `NO_LIMIT = Integer.MAX_VALUE` (`DataLimits.java:48`).
- Declared in the CQL grammar and parsed as `PER PARTITION LIMIT <int|bind marker>` into `SelectStatement.perPartitionLimit` (`SelectStatement.java:130`, `:173`).
- Evaluated per execution by `getPerPartitionLimit(options)` (`SelectStatement.java:942`). `getLimit` (`:947` onward) binds the term, validates it as Int32, and treats UNSET as unlimited.
- Unit: rows (live rows, or live static-only rows when `countPartitionsWithOnlyStaticData`).
- Default: no limit.
- How set: only in the CQL text or a bind variable. No restart is involved.
- Target line `DataLimits.java:511` is `if (++rowsInCurrentPartition >= perPartitionLimit) stopInPartition();` inside `CQLCounter.incrementRowCount()`.

**A2. What it caps.** The number of live rows returned or counted per partition in one read. The compared quantity is `rowsInCurrentPartition`, an int reset in `applyToPartition` (`DataLimits.java:484`). The resource is indirectly the heap and the response size of the read. It does not cap disk, off-heap or sstable bytes read.

**A3. Mechanism.**
1. `SelectStatement.execute` reads the user value (`SelectStatement.java:290`) and calls `getDataLimits` (`:296`, def `:882`).
2. In `getDataLimits`, for `AGGREGATE_EVERYTHING` the per-partition limit stays `NO_LIMIT` (`:889-897`). For other queries it is `perPartitionLimit`. PER PARTITION LIMIT is rejected with DISTINCT (`:1236`) and with aggregate queries (`:1247-1248`).
3. `DataLimits.cqlLimits(rowLimit, perPartitionLimit)` returns `NONE` when both are `NO_LIMIT`, otherwise a `CQLLimits` (`DataLimits.java:102-107`).
4. `CQLLimits.newCounter` makes a `CQLCounter` (`:433-439`).
5. `Counter.attachTo(BaseRows)` calls `applyToPartition` then `isDoneForPartition()` (`:327-335`).
6. For each row, `applyToRow` calls `incrementRowCount` if the row is live (`:489-494`).
7. At `:509-512`, `rowsCounted >= rowLimit` calls `stop()`. `rowsInCurrentPartition >= perPartitionLimit` calls `stopInPartition()`, which sets `rows.stop.isSignalled` and `rows.stopChild.isSignalled` (`StoppingTransformation.java:53-60`). The row iterator ends after the current item.
- Outcome when reached: the rest of the partition is not iterated. This is silent truncation, not an error and not a rejection.
- Bypasses and overshoot:
  - Non-live rows (tombstones, expired) are not counted, so they are still read and merged.
  - Rows are counted after merge, so memtable and sstable iterators have already been opened.
  - Static-only partitions count as one row only when `countPartitionsWithOnlyStaticData`.
  - Short-read retries rebuild the limits with `forShortReadRetry` (`:402-405`) and keep the same per-partition limit.
  - Paging keeps the per-partition limit across pages (`:392-400`), so the cap is per page and per partition, not a global cap.
  - A wide-row limit is a row count only. A row with huge cells is not bounded by it.

**A4. Other consumers.** Bounds on the same resource that are independent of this value:
- Paging: `DEFAULT_PAGE_SIZE = 10000` rows (`SelectStatement.java:114`, applied `:900-902`), and guardrails `page_size_warn_threshold` / `page_size_fail_threshold` (`conf/cassandra.yaml:~2089-2090`).
- `tombstone_failure_threshold` (`conf/cassandra.yaml:1815`).
- `read_thresholds_enabled` with `coordinator_read_size_*`, `local_read_size_*` and `row_index_read_size_*` (`conf/cassandra.yaml:~2015-2030`).
- Memtable and cache sizing.

**A5. Evidence beyond the source.** Cassandra CQL docs for SELECT `LIMIT` / `PER PARTITION LIMIT` (https://cassandra.apache.org/doc/5.0/cassandra/developing/cql/dml.html). The code comment at `DataLimits.java:41` ("we support PER PARTITION limits"). Otherwise none.

## B. Verification solution

**B1. Claim under test.** Node memory and disk use during a read do not follow `PER PARTITION LIMIT`. The counter stops at n live rows per partition (the mechanism works), but it is a query-supplied value, not a resource cap. It does not bound bytes (wide cells), tombstones scanned, or unlimited queries, which are the default.

### B2. Unit tier

**[Amended 2026-10-27 in the stage-4 audit, before any reading, for reasons that do not depend on a reading: (1) the original source (10,000 rows) equals the largest limit class and `NO_LIMIT` with 64 KiB rows would need 640 MiB, so the source is 20,000 rows and the 64 KiB width is not run with `NO_LIMIT`; (2) the original asked for allocated bytes as the observable, which counts garbage and is not retained memory, so retained heap (three `System.gc()` before each reading) is primary and allocated bytes and the `Row.unsharedHeapSize()` sum are recorded beside it; (3) "scale roughly linearly" and "about 100 times" are replaced by numeric relations; (4) a shared value buffer would make retained heap independent of width, so each row gets its own buffer; (5) the original positive control (`cqlLimits(10)` on 100 partitions) shows only that a global row limit binds on row count, so it is kept as the multi-partition series and a byte-stop control that does bind bytes is added; (6) the claim B1 is unchanged.]**

**B2a. Environment and build.** JDK 11, Ant, a local-disk copy of the tag made with `copy-source.sh`, built with `ant build-test`. The test class goes in the copy only (`test/unit/org/apache/cassandra/db/PerPartitionLimitProbeTest.java`, harness copy under `harness/<stem>/`) and runs with `ant testsome -Dtest.name=org.apache.cassandra.db.PerPartitionLimitProbeTest`. The forked test JVM has the 1 GiB heap of `ant testsome` (the `-Xmx512m` of the original text is overridden by Ant's `maxmemory`). Nothing is written to the shared tree. **[Amended 2026-10-27 after unit attempt 1, a runbook defect (results section 3, defect 1) that leaves B2f and B2g unchanged: the test JVM also gets `-XX:-UseTLAB` (`-Dtest.jvm.args=-XX:-UseTLAB`). With the default thread-local allocation buffers, the used-heap reading after `System.gc()` carried a noise of several hundred KB, larger than the 274 KB that the 900 extra 16 B rows between n = 100 and n = 1,000 retain, so attempt 1 read m(16) as -0.9 B per row while the exact `Row.unsharedHeapSize()` sum read 304 B. Without buffers each allocation is counted to the object. Attempt 1's summary is kept in `results/<stem>/run1/unit-attempt1-g1/`; the unit tier was run again from its start.]**

**B2b. Knobs.**
- `perPartitionLimit` n in {1, 10, 100, 1_000, 10_000} through `DataLimits.cqlLimits(DataLimits.NO_LIMIT, n)`, plus `NONE` (no limit). Row limit stays `NO_LIMIT`.
- Row width, the blob cell value size, in {16 B, 1 KiB, 64 KiB}. Pairs run: width 16 B with n = 1, 10, 100, 1_000, 10_000; width 1 KiB with n = 1, 10, 100, 1_000, 10_000; width 64 KiB with n = 1, 10, 100, 1_000 (at most about 70 MB retained). `NONE` runs at 16 B only (20,000 rows).

**B2c. Workload.** A lazy synthetic source of 20,000 live rows in one partition (clustering int, one blob cell, `BTreeRow.singleCellRow` over a `CQLTester` table), each row with its own freshly allocated value buffer. For each pair, wrap the source with `limits.newCounter(...).applyTo(source)` (the call `limits.filter(iter, nowInSec, false)` makes) and drain it into a `List<Row>` that is retained. Arithmetic: with 20,000 rows the limit n is reached for every n run. Four further series:
- Dead rows: row i is live when i mod 10 = 0 and a deleted-row marker otherwise, width 16 B, n = 1, 100, 1_000 (10 x n is under 20,000).
- Many partitions: 20 partitions of 5,000 live rows each (width 16 B), drained through `limits.filter(UnfilteredPartitionIterator, ...)`, with `cqlLimits(NO_LIMIT, n)` for n = 1, 10, 100, and with the global limit `cqlLimits(10)` as the control for what a global row limit does on the same source.
- Positive control (B2h): a byte stop at 8 MiB on a lazy source of 100,000 rows (a 16 B row weighs 304 B, so 8 MiB takes about 27,600 rows and the 20,000-row source would end first; 100,000 rows are never materialized, the consumer stops at 8 MiB).
- Source of fewer rows than n is not run (never in the grid).

**B2d. Observables and instruments.**
- `counter.rowsCounted()`, `counter.isDone()`, `counter.rowsCountedInCurrentPartition()` after the drain (single partition); rows out; rows that were live in the output (`Row.hasLiveData`); rows pulled from the source (a counter inside the source); for the many-partition series the number of partitions started and the total rows out.
- Retained heap R: `Runtime.totalMemory() - freeMemory()` after three `System.gc()` 100 ms apart, with the list still referenced, minus the same reading before the drain.
- U: the sum of `Row.unsharedHeapSize()` over the retained rows.
- Allocated bytes of the consuming thread (`com.sun.management.ThreadMXBean.getThreadAllocatedBytes`), recorded, not used for a verdict.
- Not observable: transient memory in the merge path.

**B2e. Procedure.**
1. Copy the tree, build, add the test class.
2. First-trigger point (warm, unrecorded): n = 100, width 16 B must give `rowsCounted == 100`, 100 rows out, `isDone() == false` (the row limit is `NO_LIMIT`) and `rowsCountedInCurrentPartition == 100`; otherwise stop.
3. Run the pairs of B2b in a fixed order, 5 repetitions each; the heap is read as in B2d.
4. Run the `NONE` series, the dead-row series, the many-partition series, and the controls, 5 repetitions each.
5. The instrument is checked before run 1 with a synthetic result file (`mk-known-answer.py good` must give no mismatch, `bad` (retained heap independent of width) must give mismatches) and a small-source shakedown that is not a reading.

**B2f. Predictions.** Stated before any run. Notation: R(w, n) is the median over the repetitions of the retained heap, in bytes, for width w and limit n; m(w) = (R(w, 1000) - R(w, 100)) / 900 is the retained bytes per extra row.
- Single partition: for every pair, `rowsCounted == n`, rows out `== n` and `rowsCountedInCurrentPartition == n`; with `NONE` rows out is 20,000.
- For w = 16 and w = 1024, R(w, 10000) - R(w, 1000) is within 0.9 to 1.1 of 10 x (R(w, 1000) - R(w, 100)) (usage follows the limit linearly at a fixed width).
- At the same n, retained bytes grow with width: m(1024) - m(16) is at least 0.95 x 1008 and at most 1.1 x 1008 + 64; m(65536) - m(16) is at least 0.95 x 65520 and at most 1.1 x 65520 + 64; m(65536) / m(16) is at least 50. The same holds for the sum of `Row.unsharedHeapSize()`. So a count limit does not bound bytes.
- Dead rows: `rowsCounted == n`, live rows out `== n`, and rows pulled from the source between 10 x n - 9 and 10 x n + 1 (tombstones are read but not counted).
- Many partitions, `cqlLimits(NO_LIMIT, n)`: rows out `== 20 x n`, `rowsCounted == 20 x n`, 20 partitions started, and total rows pulled between 20 x n and 20 x n + 20 (the cap is per partition, so total rows scale with the number of partitions). With the global limit `cqlLimits(10)`: rows out `== 10`, one partition started (the global limit ends everything).
- Positive control (B2h): with the byte stop at 8 MiB of `Row.unsharedHeapSize()` (on `NONE`), the retained sum is at least 8 MiB and less than 8 MiB plus one row for every width, and the retained heap is within 0.8 x the sum and 1.3 x (8 MiB + one row), flat across widths, while the per-partition-limit series moves with width.
- The claim would be wrong if retained bytes at a fixed n were flat across widths (m(65536) - m(16) < 0.1 x 65520), or if rows out ever exceeded n in a single partition.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| The first-trigger point holds, retained bytes at fixed n grow with width (m(65536) / m(16) >= 50 and the slope bounds of B2f hold), `rowsCounted` equals n, and the byte-stop control stays at about 8 MiB for all widths | Claim confirmed: the per-partition limit counts rows and does not bound bytes; the mechanism works. Effect: does not cap. |
| Retained bytes at fixed n flat across widths (m(65536) - m(16) < 0.1 x 65520) | Claim refuted: something in the path bounds bytes per row (investigate where). |
| Retained bytes follow n only within a constant-width series | Expected: usage follows the knob only through count x width. Not a refutation by itself. |
| Rows out > n in a single partition, or `rowsCounted != n` for a source larger than n | The mechanism does not work as traced. Re-read A3. |
| Dead rows counted into `rowsCounted`, or pulled outside the stated range | The trace of `isLive` (`:491`) is wrong; record which. |
| Many partitions: rows out != 20 x n, or the global limit does not end everything | The per-partition semantics differ from A3. Record which. |
| The byte-stop control does not hold retained bytes about 8 MiB across widths, or the limit is never reached, or an OutOfMemoryError | Not confirmed. Fix the harness. |
| Anything else | Not confirmed (no matching row). |

**B2h. Controls.** Positive control, a cap known to bind bytes: the consumer closes the iterator when the running sum of `Row.unsharedHeapSize()` reaches 8 MiB, on a source of 100,000 rows with `NONE` (a harness-side stand-in for a byte cap; the cluster tier's control uses a real one). Also the `NONE` series (retained bytes grow to the full source size) and the global `cqlLimits(10)` over many partitions (a limit that binds on count across partitions). The same synthetic source and a full GC before each reading in every run.

### B3. Cluster tier

**[Amended 2026-10-27 in the stage-4 audit, before any reading, for reasons that do not depend on a reading: (1) the original gave a payload comparison "8 KiB to 64 KiB" but no 64 KiB table (20 partitions x 5,000 x 64 KiB would be 6 GiB) and could not run as written; the workload is rescaled to three tables of one width each, 4 partitions, 123 MB at most; (2) the original absent-limit case at 800 MiB of an unpaged read on a 2 GiB heap cannot be answered, and the original positive control `fetch_size` 100 vs 100,000 is a row count too (`DEFAULT_PAGE_SIZE`), so it does not move bytes the way a byte cap does; it is replaced by a byte guardrail, `local_read_size_fail_threshold`, whose cap on the same read is known to bind (case `local_read_size_fail_threshold-addSize-failBytes--guided`, cluster tier Confirmed); paging is kept as a side series; (3) the observable `jstat` EU delta counts garbage at 500 ms and is replaced by per-thread allocated bytes read over JMX every 25 ms, with heap peak recorded beside it; (4) `cqlsh` starts a JVM per query and `PAGING OFF` is unreliable for timing, so the bundled Python driver at protocol 4 with `fetch_size=None` runs the queries; (5) `pkill -f CassandraDaemon` is replaced by killing the node's PID (shared node); (6) the "clustering rows per partition in {100, 5000}" dimension is dropped: the unit tier already shows the limit works on a partition longer than n, and a longer partition changes no count the counter touches; (7) the claim B1 is unchanged.]**

**B3a. Environment and build.** One node (RF=1), a local-disk copy of the tag made with `copy-source.sh` and built with `ant jar`, JDK 11. `conf/cassandra.yaml`: data, commitlog, hints and saved caches on a tmpfs (`/dev/shm`, 126 GB free; the data set is under 0.5 GB), `num_tokens: 1`, `row_cache_size: 0MiB`, `key_cache_size: 100MiB`, `read_request_timeout: 60000ms`, `native_transport_timeout: 60000ms`, `auto_snapshot: false`, `tombstone_failure_threshold` left at 100000, `page_size_fail_threshold` left unset. First node lifetime (U, uncapped): `read_thresholds_enabled: false`. Second lifetime (C, control): `read_thresholds_enabled: true` and `local_read_size_fail_threshold: 20MiB`. JVM: `-Xms2G -Xmx2G`, G1, `-XX:+HeapDumpOnOutOfMemoryError` to the tmpfs. Client: the bundled Python driver (protocol 4).

**B3b. Knobs.** CQL `PER PARTITION LIMIT` n in {1, 10, 100, 1_000, 10_000, none} (`none` = no clause, the default); row width in {100 B, 10 KiB, 100 KiB} (one table each); driver fetch size (unpaged, or a stated value). Control knob: `local_read_size_fail_threshold` at 20 MiB (lifetime C) against off (lifetime U).

**B3c. Workload.** Three tables `(pk int, ck int, v blob, PRIMARY KEY (pk, ck))`, compression off, 4 partitions (`pk` 1 to 4) each, written at CL=ONE, flushed and compacted: `ks.t_small` 4 x 30,000 rows of 100 B (12 MB), `ks.t_med` 4 x 300 rows of 10 KiB (12 MB), `ks.t_big` 4 x 300 rows of 100 KiB (123 MB). Queries are range reads, `SELECT * FROM ks.<t> [PER PARTITION LIMIT n]`, unpaged except where stated:
- Lifetime U: `t_small` n in {1, 10, 100, 1_000, 10_000, none}; `t_med` and `t_big` n in {1, 10, 100, none}. Paged: `t_big` n = 100 with fetch size 100, and `t_small` n = 10_000 with fetch size 5_000.
- Lifetime C (unpaged): `t_big` n in {10, 100, none}; `t_med` none; `t_small` n = 10_000.
- Every query 3 times, in a seeded shuffled order, with `jcmd GC.run` and 3 s of quiet before each. Arithmetic: rows returned are 4 x min(n, rows per partition); the largest answer is 123 MB (`t_big`, none) against a 2 GiB heap; `t_big` n = 100 returns 41 MB, above the 20 MiB control cap, and `t_big` n = 10 returns 4 MB, below it; about 70 queries, a few seconds each.

**B3d. Observables and instruments.**
- A (primary): bytes allocated during a query, the sum over all JVM threads of `ThreadMXBean.getThreadAllocatedBytes` read over JMX every 25 ms; A of a query is the last sample before its start to the first sample at least 1 s after the client has the full answer, minus the idle drift (the rate over the 1 s before the query times the window). It is a proxy for memory pressure: it counts garbage and not live bytes; the live set of a single query cannot be read from outside.
- H (secondary): peak `HeapMemoryUsage.used` in the window minus the median of the samples in the 1 s before it; reported, not used for the verdict.
- Per-page A for paged queries (sample-to-sample around each page).
- Client side: rows returned, payload bytes, pages, elapsed time, the error type of a failed query.
- Disk: `du -sb` of the node's data directory before the first and after the last query of lifetime U.
- `system.log` ERROR lines; `nodetool tablestats`.

**B3e. Procedure.**
1. Copy the tag to local disk, build, write the yaml, start the node (lifetime U), check `nodetool status` and `statusbinary`.
2. Create tables, load, flush, compact, count rows per partition. Warm-up: each query shape once, unrecorded.
3. First-trigger check: the first query (`t_big`, n = 100, unpaged) must return 400 rows and allocate at least 40 MB; if not, stop (exit 3).
4. Record `du -sb`; run the lifetime U queries as B3c with the sampler; record `du -sb` again.
5. Stop the node (drain, SIGTERM), start it with the control yaml (lifetime C) on the same data; first-trigger check: `t_big` n = 100 must fail with a read-size abort (otherwise stop); run the lifetime C queries.
6. Stop the node by PID, check with `ps` that no daemon of this tree is left, delete the tmpfs data.

**B3f. Predictions.** Stated before any run. Notation: A(t, n) is the median over the 3 repeats of A for table t and PER PARTITION LIMIT n (unpaged, lifetime U); a(t) = (A(t, 100) - A(t, 10)) / 360 is the marginal allocated bytes per extra returned row (90 extra rows per partition x 4 partitions).
- Rows returned equal 4 x min(n, rows per partition) for every query of lifetime U, with payload bytes equal to rows x width. This shows the limit works as a per-partition row count.
- Width at fixed n: a(t_med) - a(t_small) is at least 1.0 x 10,140 and a(t_big) - a(t_med) is at least 1.0 x 92,160 (every payload byte is allocated at least once), and each is at most 10 x that width difference. A(t_small, 100) < A(t_med, 100) < A(t_big, 100), and A(t_big, 100) is at least 40 MB (the payload is 41 MB).
- Same width, n: for each table A(t, n) increases with n over the values n >= 10 and `none` (n = 1 returns 4 rows, below the per-query noise, and is recorded but not tested). For `t_small` the marginal bytes per row between 100 and 1_000 and between 1_000 and 10_000 are within 0.5 to 2 x of each other; for `t_med` and `t_big` the marginal bytes per row between 10 and 100 and between 100 and none (300 rows per partition) are within 0.5 to 2 x of each other.
- `none` on `t_big` returns 1,200 rows and A(t_big, none) > A(t_big, 100).
- Paging: `t_big` n = 100 with fetch size 100 returns 400 rows in 4 or 5 pages, its total A is within 0.5 to 2 x of the unpaged A(t_big, 100), and its largest per-page A is at most 0.5 x that unpaged A. Paging is a row count too, so it bounds bytes only through count x width.
- Disk: `du -sb` of the data directory is unchanged (within 1 %) across the lifetime U queries, whatever n is.
- Control (lifetime C, a byte cap of 20 MiB): `t_big` n = 100 and n = none fail on all 3 repeats with a read-size abort; `t_big` n = 10, `t_med` none and `t_small` n = 10_000 (each under 20 MiB) return the full answer with A within 0.5 to 2 x of lifetime U; A_C(t_big, 100) is at most 0.5 x A_U(t_big, 100); and A_C(t_big, 100) is within 0.5 to 2 x of A_C(t_big, none) (the bytes stop following n once the byte cap binds).
- The claim would be wrong if a(t_med) - a(t_small) < 0.1 x 10,140 (flat across widths at fixed n), or if disk bytes changed with n.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| The first-trigger checks hold, the width and control predictions of B3f hold, disk is flat | Claim confirmed: the per-partition limit does not bound memory by itself; usage follows count x width; a byte cap on the same workload does bind. Effect: does not cap. |
| a(t_med) - a(t_small) < 0.1 x 10,140 and a(t_big) - a(t_med) < 0.1 x 92,160 (flat across widths at fixed n) while the control moved | Claim refuted: some other bound applies per row. Investigate. |
| A grows with n at fixed width | Usage follows the knob only through count x width. Consistent with the claim, not a refutation by itself. |
| The width slopes fall between 0.1 and 1.0 times the width difference, or are above 10 times | Not confirmed (partial: some per-row bytes are not payload, or the instrument is wrong). |
| The control does not abort or does not cap A (A_C(t_big, 100) > 0.5 x A_U(t_big, 100)), or the limit is never reached, or the node runs out of memory or times out before measuring | Not confirmed. Re-size and repeat, or record the defect. |
| Rows returned > 4 x n for a table with more than n rows per partition | The mechanism is not working as traced. |
| Disk bytes change with n | Unexpected; check for flush or compaction noise (not a verdict by itself). |
| Anything else | Not confirmed (no matching row). |

**B3h. Controls.** A byte cap on the same workload and instruments: lifetime C. The same query with the clause removed (`none`) gives the upper bound. 3 repeats per point with a GC before each; no concurrent client load; caches off for rows, so reads hit sstables each time. The control is a cap known to bind bytes; paging is recorded as a second, count-based bound.

**B4. Risks and cleanup.** **[Amended 2026-10-27: paths and sizes follow the rewritten B2/B3.]** Disk: the unit tier needs none beyond the build (about 2 GB under the copied tree). The cluster tier writes about 150 MB to a tmpfs (`/dev/shm`); a heap dump (up to 2 GiB) would go there too. Nothing is written to shared storage or to the shared source tree. Large unpaged reads can run a 2 GiB heap out of memory, so the largest answer is 123 MB. Cleanup: `nodetool drain`, kill the node's PID, check with `ps` (by this tree's path) that no `CassandraDaemon`, surefire or sampler process is left, then remove the trees and tmpfs directories.

## C. Sources read

- `/users/jason92/writeup-A/playbook-autonomous.md`
- `/users/jason92/writeup-A/_TEMPLATE-autonomous.md`
- `src/java/org/apache/cassandra/db/filter/DataLimits.java` (lines 40-590)
- `src/java/org/apache/cassandra/cql3/statements/SelectStatement.java` (lines 114, 130, 173, 280-300, 878-960, and grep hits at 1236-1248)
- `src/java/org/apache/cassandra/db/transform/StoppingTransformation.java` (lines 35-75)
- `conf/cassandra.yaml` (grep hits near lines 1815, 2015-2030, 2089-2090)

## D. Stage-4 feedback

**2026-10-27, run 1 (unit and cluster) filed; results file `stage4-runtime-verification/results/per-partition-limit-incrementRowCount-rowsincurrentpartition--autonomous.md`: unit tier Confirmed (does not cap), cluster tier Confirmed (does not cap); outcome class true negative; no run 2.** The estimate (`negative`) is unchanged and was right. What the runs showed: the counter stops at exactly n live rows per partition (70 of 70 unit points; 4n rows in the cluster; 20n over 20 partitions, and 10 only under a global row limit); tombstones are read and not counted; memory follows the limit only through count x width (unit: 309 B per extra 16 B row, 1,317 B per 1 KiB row, 65,829 B per 64 KiB row, a factor 213 against a refuting bound of 0.1; cluster: 1,350 B, 46,856 B and 460,837 B allocated per extra returned row for 100 B, 10 KiB and 100 KiB values); a 20 MiB `local_read_size_fail_threshold` aborted the n = 100 and unlimited reads of the 100 KiB table and cut allocation to 0.39 x, and the data directory did not change with n. Paging with fetch size 100 is a count too (total allocation unchanged, largest page 45 % of it). One runbook defect: the used-heap reading was too noisy for 16 B rows under G1 with thread buffers; `-XX:-UseTLAB` fixed it (amendment 5 above, results section 3). Upstream/doc candidate: the CQL documentation for `PER PARTITION LIMIT` could say that it is a row count and bounds bytes only through row width.

**Stage-4 audit amendments, 2026-10-27 (made before any reading; the claim B1 is unchanged; results file `results/per-partition-limit-incrementRowCount-rowsincurrentpartition--autonomous.md`):**
1. B2 rewritten (reasons at its head): source 20,000 rows and a wider grid (n = 1, 10, 100, 1_000, 10_000; widths 16 B, 1 KiB, 64 KiB; 64 KiB not run with `NONE`); retained heap primary (allocated bytes recorded only); numeric relations in B2f; a fresh value buffer per row; a dead-row series, a many-partition series (the cap is per partition, with the global `cqlLimits(10)` as control) and a byte-stop positive control.
2. B3 rewritten (reasons at its head): three single-width tables of 4 partitions (the original had no 64 KiB table and unpaged reads of 800 MiB), driver client instead of `cqlsh`, allocated bytes over JMX as the primary observable, a byte guardrail (`local_read_size_fail_threshold` 20 MiB) as the positive control in place of the `fetch_size` comparison (a row count too), disk-flat check, node stopped by PID.
3. Ground and A3: "ignored for aggregates" corrected to "rejected" (the parser rejects `PER PARTITION LIMIT` with aggregates and DISTINCT).
4. B4 rewritten to the new paths.
5. B2a: `-XX:-UseTLAB` added to the test JVM after unit attempt 1 (defect 1 in the results file; B2f and B2g unchanged; the unit tier restarted).
6. Citations checked against the pinned source (all hold): `DataLimits.java:48,102-107,350,392-405,484,489-494,509-512,542`; `StoppingTransformation.java:50-60`; `SelectStatement.java:114,290,882-902,942,1236,1247-1248`; `conf/cassandra.yaml:1815,2015-2026,2090`; `ReadCommand.java:717` (the read-size abort message used by the control). Not checked: yaml lines other than those listed.
