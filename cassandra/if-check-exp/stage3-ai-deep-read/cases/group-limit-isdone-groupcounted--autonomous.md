<!-- file: cases/group-limit-isdone-groupcounted--autonomous.md -->
# GROUP BY group limit (`CQLGroupByLimits.groupLimit`) — verification solution  <!-- file: cases/group-limit-isdone-groupcounted--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/filter/DataLimits.java:1013` (`return groupCounted >= groupLimit;` in `GroupByAwareCounter.isDone()`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI (version not reported to the agent), 2026-10-27 |
| Estimate | `negative`: `groupLimit` is the number of GROUP BY result groups the user asked for (CQL `LIMIT`) or the paging page size. It bounds how many groups are returned, not how many rows or bytes a node materialises. The memory-relevant bound for the same counter is `rowLimit`, which for GROUP BY queries is the page size (default 10000 rows). |
| Ground | A single group can contain an unbounded number of rows. A group is counted only when the next group or the end of data is reached (`DataLimits.java:834-837`, `:1041`), so `isDone()` stays false for the whole group while rows are read. Row reads are bounded by `rowLimit` (`DataLimits.java:986-987`), a different operand. The group limit is also a per-query value chosen by the client, not a node-level resource setting. |

## A. Constraint trace

**A1. The constraint.** Name: the GROUP BY group limit, field `CQLGroupByLimits.groupLimit` (`DataLimits.java:658`, `protected final int groupLimit`; constructors `:665-690`) *[Amended 2026-10-27, A1: line numbers corrected from `~665` and `~676-690`; stage 4 audit.]*. Kind: runtime-derived per-query value, not a yaml key, `-D` property or constant. It is first set in `SelectStatement.getDataLimits` (`cql3/statements/SelectStatement.java:880-914`). The call `DataLimits.groupByLimits(cqlRowLimit, cqlPerPartitionLimit, pageSize, aggregationSpec)` (`:911-914`) fills the parameters `(groupLimit, groupPerPartitionLimit, rowLimit)` (`DataLimits.java:116-122`). Two things follow.

- `groupLimit` = the user `LIMIT` (`cqlRowLimit = userLimit`, `SelectStatement.java:893-896`), or `NO_LIMIT` (`Integer.MAX_VALUE`) if no `LIMIT` is given.
- `rowLimit` = `pageSize`, which is the client page size, or `DEFAULT_PAGE_SIZE = 10000` (`SelectStatement.java:114`, `:901-902`) when paging is off.

When the query is paged, `forPaging(pageSize)` (`DataLimits.java:717-725`) and `forPaging(pageSize, key, remaining)` (`:727-737`) replace `groupLimit` with the page size. `AggregationQueryPager` sub-pages use `computeSubPageSize` (`service/pager/AggregationQueryPager.java:284-287`), and `forGroupByInternalPaging` (`DataLimits.java:739-747`) sets `groupLimit := rowLimit`.

Unit: number of groups. Default: unlimited. It is set by the CQL `LIMIT` (or the driver page size), per request. No restart is needed.

**A2. What it caps.** The number of completed groups returned by a GROUP BY read (or per page). The compared quantity is `groupCounted`, the counter of completed groups (`DataLimits.java:837`, incremented at `:990-995`). It is a count, not bytes, and it concerns the resource "rows/groups returned", only indirectly heap.

**A3. Mechanism.**

1. `newCounter` builds a `GroupByAwareCounter` (`DataLimits.java:749-756`).
2. `applyToPartition` (`:865-909`) and `applyToRow` (`:925-957`) detect group boundaries through `groupMaker.isNewGroup`. Only when a *new* group is reached while `hasUnfinishedGroup` is true does `incrementGroupCount()` run (`:933-937`, `:888-890`).
3. `incrementGroupCount()` (`:990-995`) does `groupCounted++` and calls `stop()` when `groupCounted >= groupLimit`.
4. `isDone()` (`:1011-1014`, the target) returns `groupCounted >= groupLimit`. It is consulted in `applyToPartition` (`:894`, `:904`), in `applyToStatic` (`:917`), in `isDoneForPartition()` (`:1007`) and by `isExhausted` (`:806-810`).
5. When the limit is reached, `stop()` (`StoppingTransformation`) cuts the iterator, and the static row of the next partition is dropped (`:917-921`).
6. Row bound: `incrementRowCount()` (`:983-988`) stops at `rowLimit`. This is the actual per-read bound on the number of rows pulled through the pipeline.
7. `onClose()` (`:1041`) counts the trailing unfinished group only if `groupCounted < groupLimit` and `rowsCounted < rowLimit`.

Overshoot and bypass paths:

- A single group that is larger than the row limit never increments `groupCounted`, so `isDone()` is false until `rowLimit` stops the read. The group is then continued in the next sub-page via `GroupingState`.
- `AGGREGATE_EVERYTHING` (a plain `count(*)` with no GROUP BY) does not use this class (`SelectStatement.java:889-896`, `:911`).
- `DISTINCT` returns `distinctLimits` (`:908-909`), which does not use it.

**A4. Other consumers.** Memory and disk on the node is also used by memtables, the row cache, key cache, chunk cache and the coordinator's response buffering. The page-size guardrail (`Guardrails.pageSize`, `SelectStatement.java:517`; `page_size_warn_threshold` / `page_size_fail_threshold`, `config/GuardrailsOptions.java:72`) limits the client page size, which indirectly sets `rowLimit`. Byte-based paging (`PageSize` in bytes) is a separate mechanism. Read-time memory is also affected by wide-row/tombstone thresholds (`tombstone_warn_threshold`, `tombstone_failure_threshold`), which are not related to `groupLimit`.

**A5. Evidence beyond the source.** None beyond the tree. Cassandra docs on GROUP BY and paging (https://cassandra.apache.org/doc/5.0/cassandra/developing/cql/dml.html) describe `LIMIT` as a bound on returned groups, which matches the trace.

## B. Verification solution

**B1. Claim under test.** The GROUP BY `groupLimit` comparison at `DataLimits.java:1013` does not bound how much memory a read uses. With a fixed row layout, per-read rows pulled and heap allocated stay the same when `groupLimit` (CQL `LIMIT`) varies from 1 to 100000, as long as one group spans many rows. They scale with `rowLimit` (the page size) instead. The comparison only decides when the result stops (number of groups returned).

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a ~/cassandra-5.0.9/ /local/c509/`) and build there: `cd /local/c509 && ant jar`. Add a new test class `test/unit/org/apache/cassandra/db/filter/GroupByLimitMemoryTest.java` extending `CQLTester` (in-JVM single node, no cluster). Run it with `ant testsome -Dtest.name=GroupByLimitMemoryTest`, with `-Dtest.jvm.args="-Xmx1g -XX:+UseG1GC"`. The test needs `com.sun.management.ThreadMXBean` for `getThreadAllocatedBytes`.

**B2b. Knobs.** The CQL `LIMIT` (groupLimit): 1, 10, 1000, 100000 and none. The page size (rowLimit): 100, 1000, 10000 (via `executeNetWithPaging` or `session.execute(new SimpleStatement(...).setFetchSize(n))`). Rationale: `LIMIT` varies `groupLimit` while page size varies `rowLimit`, the competing bound.

**B2c. Workload.** `CREATE TABLE t(pk int, ck int, v blob, PRIMARY KEY(pk, ck))`. Insert 1 partition (pk=1) with 20000 rows, `v` = 1 KB (about 20 MB), and flush. Query `SELECT pk, count(*) FROM t GROUP BY pk LIMIT L` (a single group of 20000 rows). `groupLimit` L=1 is reached only after the end of the partition (`onClose`), so `isDone()` stays false while the 20000 rows stream. A second dataset has 20000 partitions with 1 row each, queried with `GROUP BY pk LIMIT L`. There every row is a group, so `groupCounted` reaches L and the read stops after L groups, which is the contrast.

**B2d. Observables and instruments.** (1) The number of rows pulled per sub-page, via a spy on `DataLimits.Counter.rowsCounted()` obtained by building the `DataLimits` by hand: `DataLimits.groupByLimits(L, NO_LIMIT, pageRows, AggregationSpecification.aggregatePkPrefix(metadata.comparator, 1))` applied via `limits.newCounter(...)` to the read command's iterator (read `counted()`, `rowsCounted()`, `isDone()` after the iterator is drained). (2) Thread-allocated bytes around the read: `((com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean()).getThreadAllocatedBytes(Thread.currentThread().getId())`. (3) Number of sub-pages: count calls through `AggregationQueryPager` (add a log counter in the test, or count Tracing events). Not directly observable: the peak live heap (only allocation volume is measured here).

**B2e. Procedure.**

1. Build the tree (B2a).
2. Create the table and data (B2c), then `flush()`.
3. For each (L, pageRows) in {1, 1000, 100000, NO_LIMIT} x {100, 1000, 10000}, run the single-group query three times, discarding the first.
4. Record rowsCounted, groupCounted, isDone(), sub-page count and allocated bytes.
5. Repeat on the 20000-partition dataset.
6. Positive control: run `SELECT * FROM t WHERE pk=1 LIMIT L` (cqlLimits, not GROUP BY), where the row limit is L, and record rows and allocated bytes for L = 100, 1000, 10000.
7. Assert nothing; print the table.

**B2f. Predictions.** Single-group dataset: for every L in {1, 1000, 100000, none} and a fixed page size P, total rows read = 20000 (the group has no end until the data ends), rows per sub-page <= P, sub-page count = floor(20000/P) + 1, and `isDone()` is false until the final sub-page. *[Amended 2026-10-27, A2: was `ceil(20000/P)`. `onClose` (`DataLimits.java:1041`) counts the trailing group only if `rowsCounted < rowLimit`, so when P divides 20000 the last full sub-page ends on `rowLimit`, and one more, empty, sub-page is needed to close the group: 201, 21 and 3 sub-pages for P = 100, 1000, 10000. The count is a secondary observable and is not part of any B2g row.]* Allocated bytes agree across L within 10 percent, and scale with P only in the per-sub-page transient size. Many-groups dataset: total rows read over all sub-pages = L (or L+1 for the boundary row) for every L below the group count (20000), at most P rows per sub-page, and `isDone()` becomes true at `groupCounted == L`; for L >= 20000 the limit is not reached and all 20000 rows are read. *[Amended 2026-10-27, A3: the filed text said "for L < P"; the total over sub-pages is L for any L below 20000.]* Positive control: allocated bytes grow about linearly with L (100 -> 10000 gives about 100x). *[Amended 2026-10-27, A4: "moved" is defined as rows read == L for L = 100, 1000, 10000 and allocated bytes at L=10000 at least 10 times those at L=100 (a fixed per-query overhead keeps the ratio below 100). The page-size sweep (rows per sub-page == P, with L fixed) is a second control on the same resource: `rowLimit` is a known-binding bound of the same read.]*

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Single-group dataset: rows read and allocated bytes the same for L=1 and L=100000 (rows read 20000); the per-sub-page row count follows P | Claim confirmed: `groupLimit` does not bound memory; `rowLimit` does |
| Single-group dataset: rows read drop to about 1 when L=1 | Claim refuted: group limit stops the read early |
| Allocated bytes grow with L while P is fixed | Claim refuted: usage follows the knob |
| Many-groups dataset: rows read = L+1 and `isDone()` true | Mechanism works as traced (the limit bounds the result size only) |
| Positive control (non-GROUP BY LIMIT) allocated bytes did not move with L | Control invalid; the result is not confirmed |
| Limit never reached (L > number of groups) in the many-groups run | Not confirmed for that row *[Amended 2026-10-27, A5: this applies only if no cell with L below 20000 reached the limit; the cells L = 100000 and none are expected not to reach it and are not a failure.]* |

**B2h. Controls.** Fixed data, flushed once, so memtable state does not vary. Discard warm-up iterations, force `System.gc()` between runs. Run page-size sweeps independently of L sweeps. Pin the heap with `-Xmx1g -Xms1g`. Disable the row cache and chunk cache effects by using the same cache state in every run.

### B3. Cluster tier

**B3a. Environment and build.** A single node (a second node optional) on a Linux host with JDK 11. Copy the tree to local disk and build: `cp -r ~/cassandra-5.0.9 /local/c509n && cd /local/c509n && ant jar`. Use local disk dirs of known size (at least 5 GB free): set `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory` under `/local/c509n/run/`. Settings: `JVM_OPTS="-Xms512m -Xmx512m -XX:+UseG1GC -Xlog:gc*:file=/local/c509n/run/gc.log"` (conf/jvm11-server.options), `page_size_fail_threshold` left at its default (disabled), `num_tokens: 16`, `tombstone_failure_threshold` default. Start with `bin/cassandra -R -p /local/c509n/run/pid`. *[Amended 2026-10-27, A11: also `range_request_timeout`, `read_request_timeout`, `request_timeout` = 600000ms and `native_transport_timeout` = 600s; see section D.]*

**B3b. Knobs.** CQL `LIMIT` (groupLimit): 1, 100, 100000, none. Fetch size (rowLimit): 100, 1000, 10000 (via `cqlsh` `PAGING <n>` or a driver `setFetchSize`). The aim is to hold one of them fixed while the other varies. *[Amended 2026-10-27, A10: the client is the bundled Python driver (protocol 4, `fetch_size` = P, `None` for paging off), not cqlsh; each cell has one warm-up query, then 5 timed ones.]*

**B3c. Workload.** `CREATE KEYSPACE ks WITH replication={'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE ks.t(pk int, ck int, v blob, PRIMARY KEY(pk,ck));`. Load 1 partition (pk=1) with 500000 rows with 1 KB blobs (about 500 MB on disk, which is about the size of the 512 MB heap if materialised at once), by running 100 concurrent cqlsh/driver batches of single inserts (or `cassandra-stress` with a user profile). `nodetool flush`. Query `SELECT pk, count(*) FROM ks.t GROUP BY pk LIMIT L` and repeat 5 times per (L, page size) cell. Duration: roughly 1 to 3 minutes per cell. Arithmetic: if the group limit bounded memory, L=1 would read about 1 row of data. The group has 500000 rows, so a read of the whole group is needed, giving about 500 MB of data crossing the heap in sub-pages of P rows (P x 1 KB = 0.1 MB, 1 MB, 10 MB).

**B3d. Observables and instruments.** (1) GC log: bytes allocated and the maximum heap occupancy after GC (`-Xlog:gc*`), plus `jstat -gc <pid> 250ms` sampling. (2) `jcmd <pid> GC.heap_info` before and after each query. (3) Tracing (`TRACING ON` in cqlsh) lines of the form `Read N live rows and M tombstone cells`, to count rows per sub-page and sub-pages per query. *[Amended 2026-10-27, A8: tracing is replaced by a Byteman observation rule, loaded at node start, on `DataLimits$CQLGroupByLimits$GroupByAwareCounter.onClose` (AT EXIT) that appends one line per local sub-page read: `rowsCounted`, `groupCounted`, `isDone()`, `hasUnfinishedGroup`, epoch ms. Tracing a query of 5000 sub-pages is not practical. Whole-JVM allocation per query is read as the sum of `ThreadMXBean.getThreadAllocatedBytes` over all threads through JMX, before and after the query, with an idle-window baseline for its noise; the peak heap is the maximum of `HeapMemoryUsage.used` sampled every 100 ms. Allocation and peak `used` include garbage; this is the gap B3d already names (no per-request attribution).]* (4) `nodetool tablestats ks.t` for sstable size. Disk is not expected to move (read-only workload). Not observable: the per-request heap attribution inside the node (only whole-JVM heap is visible).

**B3e. Procedure.**

1. Build (B3a) and start the node. Confirm `nodetool status`.
2. Create the schema and load the data (B3c). `nodetool flush`, `nodetool compact ks t`. Record the baseline heap with `jcmd <pid> GC.heap_info` after `jcmd <pid> GC.run`.
3. For each fetch size P in {100, 10000}: set `PAGING P` in cqlsh; for each L in {1, 100000, none} run the query 5 times, and record the GC log window, `jstat` peak, and the trace rows/sub-page.
4. Positive control: `SELECT * FROM ks.t WHERE pk=1 LIMIT L` for L = 1000, 10000, 50000 with paging off (`PAGING OFF`), recording the same instruments. Stay below the heap size to avoid OOM. *[Amended 2026-10-27, A6: filed values were 100, 10000, 100000. L=100 (about 0.1 MB) is below the noise of a JVM-wide allocation reading; L=100000 builds a result of about 100 MB that the coordinator, the response encoder and the client each hold, which risks the 512 MB heap that this step says to stay below.]*
4b. Many-groups variant (added 2026-10-27, A7): create `ks.g (pk int, ck int, v blob, PRIMARY KEY (pk, ck))` with 20000 partitions of 1 row of 1 KB (about 20 MB), `nodetool flush`; query `SELECT pk, count(*) FROM ks.g GROUP BY pk LIMIT L` for L = 1, 100, 5000 and none at P = 100 and 10000, 3 repeats per cell. Prediction: the sum of `rowsCounted` over the sub-pages equals L (or L+1), the last sub-page has `isDone() == true` and `groupCounted == L`; for L=none all 20000 rows are read. This is the cluster-tier evidence that the disallow branch can fire.
5. Tear down (B4).

**B3f. Predictions.** For fixed P, peak heap occupancy and allocation volume are the same for L=1, 100000 and none (within 15 percent), and each query reads all 500000 rows (tracing shows `ceil(500000/P)` sub-page reads). When P changes from 100 to 10000 the per-sub-page transient allocation rises about proportionally (to about 100x in the per-sub-page row batch) while the total allocation volume stays about the same *[Amended 2026-10-27, A9: "about the same" means within a factor of 2, because P=100 repeats the per-read setup 5001 times against 51 times; ceil(500000/P) in the sub-page count is floor(500000/P)+1 for the reason in A2: 5001 and 51]*. The positive control raises peak heap about linearly with L (100 -> 100000).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Heap peak and rows read flat across L (1 / 100000 / none) at fixed P, while P moves the per-sub-page batch | Claim confirmed: the group limit does not cap memory; the row/page limit does |
| Query with L=1 reads far fewer rows or allocates far less than L=none | Claim refuted: the group limit bounds the work |
| Peak heap follows L | Claim refuted |
| Positive control (non-GROUP BY, `LIMIT`) flat in L | Control did not move; result not confirmed (the instrument is insensitive) |
| Limit never reached: the many-partitions variant (`GROUP BY pk`, 1 row each) not run, or L above group count | Not confirmed for that cell |
| Node OOMs or the heap goes above 90 percent for L=none | Stop; reduce the dataset, since the result is bounded by the heap choice, not the limit |

**B3h. Controls.** Same data and the same flush/compaction state for all cells. Warm up each cell once. `jcmd GC.run` between cells and take baselines. Keep the client in a separate process or at least outside the JVM. Repeat the L=none cell at the beginning and the end to detect drift. Keep the row cache disabled (`row_cache_size: 0`, the default) so cached partitions do not mask reads.

**B4. Risks and cleanup.** Disk: the dataset is about 0.5 GB plus compaction headroom (about 1.5 GB); everything goes under `/local/c509n/run/` on local disk, never the shared source tree or shared storage. Build only in the copy. Unit tier: the CQLTester creates temp directories under `build/test/cassandra` in the copy, so delete them. Cleanup: `kill $(cat /local/c509n/run/pid)`, then `pgrep -f CassandraDaemon` and `pgrep -f ant` must return nothing; `rm -rf /local/c509n/run`.

## C. Sources read

- `~/writeup-A/playbook-autonomous.md`
- `~/writeup-A/_TEMPLATE-autonomous.md`
- `~/cassandra-5.0.9/src/java/org/apache/cassandra/db/filter/DataLimits.java` (lines 97-160, 233-273, 640-1100)
- `~/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java` (lines 110-115, 285-340, 505-545, 880-945)
- `~/cassandra-5.0.9/src/java/org/apache/cassandra/service/pager/AggregationQueryPager.java` (lines 40-80, 114-300, 406-445)
- `~/cassandra-5.0.9/src/java/org/apache/cassandra/config/GuardrailsOptions.java` (grep of page_size lines)
- https://cassandra.apache.org/doc/5.0/cassandra/developing/cql/dml.html (cited, not fetched)

## D. Stage-4 feedback

**Stage 4, 2026-10-27 (results: `stage4-runtime-verification/results/group-limit-isdone-groupcounted--autonomous.md`; harness: `stage4-runtime-verification/harness/group-limit-isdone-groupcounted--autonomous/`).** Unit **Confirmed — does not cap**; cluster **Confirmed — does not cap**; outcome class **true negative**. The B1 trace held: with one group of 20000 rows (unit) or 500000 rows (cluster) the rows read, the allocated bytes (unit: exact thread-allocated bytes, 29.4 to 31.9 MB; cluster: JVM-wide, 2.87 to 3.09 GB) and the sampled peak heap are the same for L = 1, 100000 and no limit (within 0.6 percent in the unit tier, 2.3 percent in the cluster tier), `isDone()` is false in every sub-page but the last, and rows per sub-page equal the page size P (`rowLimit`). In the many-groups data the limit fires (rows read = L, `isDone()` true at `groupCounted == L`), so the comparison at `DataLimits.java:1013` decides only when the result stops. Positive controls moved (`SELECT * LIMIT L`: x96.6 unit, x54.6 cluster; the page-size sweep moves the per-sub-page allocation x105). Nothing in A1-A5 needs to be changed. Two corrections to the filed text came from the run: the sub-page count is floor(N/P)+1 (amendment A2, confirmed: 201 / 21 / 3 at P = 100 / 1000 / 10000), and the many-groups total is L rows (rowsCounted = L, not L+1). Each local sub-page read closes four `GroupByAwareCounter` instances (replica and coordinator-side), so a counter-level trace shows every sub-page four times. Caveat: at P=100 the 512 MB heap was tight (sampled `used` 89 to 93 percent, full GCs at the same rate for every L, live set 52 percent after a full GC); the P=10000 cells (80 percent) carry the conclusion on their own. Doc note: `LIMIT` on a GROUP BY bounds the number of result groups, not the rows scanned.

**Stage-4 design-audit amendments, 2026-10-27** (made before run 1; none depends on a reading; each is also marked next to the text it changes):
A1 line numbers in A1; A2 sub-page count is floor(N/P)+1 (B2f); A3 many-groups total rows in B2f; A4 definition of "control moved" (B2f); A5 scope of the "limit never reached" row (B2g); A6 control values L = 1000, 10000, 50000 (B3e.4); A7 many-groups variant added as B3e.4b; A8 Byteman observation rule and JMX allocation instrument replace tracing (B3d); A9 tolerance across P and sub-page count in B3f; A10 Python driver client (B3b).
A11 (runbook defect found by run 1 attempt 1, 2026-10-27, tier restarted; no prediction or conclusion text changed): B3a also sets `range_request_timeout`, `read_request_timeout`, `request_timeout` to 600000ms and `native_transport_timeout` to 600s. The coordinator's 10 s range deadline runs from the start of the request and spans every sub-page, so a full scan of the 500000-row group at P=100 (5001 sub-pages) timed out (`ReadTimeout` / `ReadFailure`) in attempt 1; the P=10000 cells of that attempt completed. Attempt 1's logs are kept at `~/s4-b11-g72-logs/run1a-aborted-timeouts/` on pc07.
