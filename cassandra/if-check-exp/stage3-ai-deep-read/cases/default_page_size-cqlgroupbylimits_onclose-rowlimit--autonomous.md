# default_page_size — verification solution  <!-- file: cases/default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/filter/DataLimits.java:1041` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `positive` with a stated limit: `DEFAULT_PAGE_SIZE` bounds the number of rows each internal sub-read of an un-paged GROUP BY query may return, so transient read-side heap per sub-read should scale with it; it does not bound bytes per row, nor the number of groups in the final result. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `SelectStatement.DEFAULT_PAGE_SIZE`, a compile-time constant (not yaml, not a `-D` property, not JMX), declared `public static final int DEFAULT_PAGE_SIZE = 10000;` at `src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:114`. Unit: rows (as an internal row limit; see A2). Default 10000, hard-coded, no derivation. Changing it needs an edit, a rebuild and a restart. (There is an unrelated `SecondaryIndexManager.DEFAULT_PAGE_SIZE = 10000` at `index/SecondaryIndexManager.java:142` and a `BatchlogManager.DEFAULT_PAGE_SIZE = 128` at `batchlog/BatchlogManager.java:91`; they are different constants.)

Verification of the earlier trace (checked line by line):
- `getDataLimits(...)` at `SelectStatement.java:883` replaces `pageSize <= 0` by `DEFAULT_PAGE_SIZE` (`SelectStatement.java:901-902`, comment at 899-900: "Group by and aggregation queries will always be paged internally to avoid OOM"). Correct.
- For a GROUP BY spec (not `AGGREGATE_EVERYTHING`, not DISTINCT) it calls `DataLimits.groupByLimits(cqlRowLimit, cqlPerPartitionLimit, pageSize, aggregationSpec)` (`SelectStatement.java:908-914`). So the `pageSize` lands in the third parameter, `rowLimit`, of `groupByLimits(int groupLimit, int groupPerPartitionLimit, int rowLimit, AggregationSpecification)` (`DataLimits.java:116-121`). Correct. Plain aggregates without GROUP BY (`AGGREGATE_EVERYTHING`) do NOT get a row limit from this constant: they fall to `DataLimits.cqlLimits(NO_LIMIT, NO_LIMIT)` (`SelectStatement.java:920`), i.e. the comment's "aggregation queries" is only true for GROUP BY here. The earlier trace did not say this.
- `CQLGroupByLimits` constructor calls `super(rowLimit, NO_LIMIT, false)` (`DataLimits.java:679`), which stores `CQLLimits.rowLimit` (field at `DataLimits.java:349`). Correct. `CQLGroupByLimits` is declared at `DataLimits.java:643`.
- The client page size is read at `SelectStatement.java:291` (`options.getPageSize()`) and passed to `getDataLimits` at 296. Correct. The guardrail call is `Guardrails.pageSize.guard(pageSize, ...)` at `SelectStatement.java:517`, with thresholds `page_size_warn_threshold` / `page_size_fail_threshold` (`config/Config.java:873-874`, both default -1, volatile). Correct, but note the guard receives the client value (-1 when unset), so it never sees the default and cannot bound `DEFAULT_PAGE_SIZE`.
- The entry line 1041 is `if (hasUnfinishedGroup && groupCounted < groupLimit && rowsCounted < rowLimit)` inside `GroupByAwareCounter.onClose()` (`DataLimits.java:1033-1048`), not an enforcement of the cap itself. The comment at 1036-1039 says: end of data is inferred when the row count is below the "internal page size". The real enforcement is `if (++rowsCounted >= rowLimit) stop();` at `DataLimits.java:986-987`. The same `rowsCounted < rowLimit` test also feeds `isExhausted` (`DataLimits.java:808`).

**A2. What it caps.** Resource: heap (transient, read path), and indirectly the amount of data scanned per sub-read. The quantity compared is `GroupByAwareCounter.rowsCounted` (`DataLimits.java:826`, incremented at 986) against `rowLimit`, i.e. live rows seen by one counter. One counter instance covers one `ReadCommand` execution (one replica local read, and the coordinator-side merge of it). It is a row-count cap, not a byte cap. It is not the number of groups returned: groups are limited separately by `groupLimit` (user `LIMIT`, `DataLimits.java:989-993`).

**A3. Mechanism.**
1. `SelectStatement.execute` (`SelectStatement.java:291-296`) builds the `DataLimits` with `rowLimit = clientPageSize or 10000`.
2. For GROUP BY (`aggregationSpec != null`) the `pageSize <= 0` shortcut at `SelectStatement.java:338` is not taken, so the statement goes through a pager (`getPager`) wrapped in `AggregationQueryPager` (`service/pager/AggregationQueryPager.java:47-62`, group-by branch at 59-60).
3. `GroupByPartitionIterator` turns a non-positive page size into `NO_LIMIT` groups (`AggregationQueryPager.java:193-197`), so with an unset client page size one request loops over sub-pages until data ends (`fetchNextRowIterator`, 217-251).
4. Each sub-page is a normal read command whose limits come from `forGroupByInternalPaging(state)` (`AggregationQueryPager.java:273`), which builds `new CQLGroupByLimits(rowLimit, groupPerPartitionLimit, rowLimit, groupBySpec, state)` (`DataLimits.java:740-748`), so the group limit of each sub-read is also the row limit.
5. While reading, `GroupByAwareCounter.incrementRowCount` (`DataLimits.java:984-988`) calls `stop()` once `rowsCounted >= rowLimit`. `stop()` is `StoppingTransformation.stop()` (`db/transform/StoppingTransformation.java:37`) and ends the iteration of that read.
6. At close, `onClose` (line 1033-1048): if a group is still open and neither limit was hit, the end of data is assumed and the last group is counted; otherwise the group stays open and the next sub-page continues from the saved `GroupingState`.
Outcome at the limit: the sub-read stops after about `rowLimit` live rows, the open group continues in the next sub-page; no error is raised. Overshoot / bypass paths: (a) the cap counts live rows only (`isLive(row)`, `DataLimits.java:1020-1027`), so tombstones and shadowed data are read without being counted (tombstone thresholds are a separate mechanism); (b) bytes per row are unbounded (wide cells); (c) `AGGREGATE_EVERYTHING` queries and DISTINCT (`SelectStatement.java:916-920`) do not use it; (d) the final result still holds one row per group, so many groups grow coordinator memory regardless of this constant; (e) `forPaging` / `CQLGroupByPagingLimits` (`DataLimits.java:701-709`, 1060-1110) use the caller's group page size, replacing the group limit.

**A4. Other consumers.** Memtables, row/key/chunk caches, bloom filters and index summaries, compaction, other concurrent reads, the response serialization buffers of the replica, the coordinator's own accumulation of results in `ResultSetBuilder` (`SelectStatement.java:51` import; `processResults` at `:561`), and non-GROUP-BY queries all use the same heap/off-heap and are not controlled by this constant.

**A5. Evidence beyond the source.** In-tree comment at `SelectStatement.java:899-900` and `DataLimits.java:1036-1039`. Existing tests worth reading when running: `test/unit/org/apache/cassandra/cql3/validation/operations/SelectGroupByTest.java` and `AggregationTest.java` (exist in the tree). Upstream background: CASSANDRA-10707 (GROUP BY support) introduced the internal paging; not re-read here, cited from memory, treat as unverified.

## B. Verification solution

**B1. Claim under test.** For a GROUP BY query with no client page size, the number of live rows read per internal sub-read is capped by `SelectStatement.DEFAULT_PAGE_SIZE` (so peak transient heap on the read path grows roughly in proportion to it and not to the partition size), and this cap does not apply to a plain aggregate (no GROUP BY). It would be wrong if the rows counted per sub-read exceed the constant, or if peak heap is flat when the constant changes.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a /users/jason92/cassandra-5.0.9/ $WORK/c509/`), build only there (`ant jar` then `ant testclasslist`/a single test). Put the test in the copy at `test/unit/org/apache/cassandra/cql3/validation/operations/DefaultPageSizeProbeTest.java`, extending `CQLTester`. Run: `ant testsome -Dtest.name=DefaultPageSizeProbeTest`. JVM options: the ones in `build.xml` for tests.

**B2b. Knobs.** (1) Value of `DEFAULT_PAGE_SIZE` in the local copy: 100, 1000, 10000 (stock), 50000. Set by editing line 114 and rebuilding (compile-time constant; the static final is inlined, so a full recompile of `SelectStatement` and users is needed). (2) Client page size via `QueryOptions.create(..., pageSize, ...)`: unset (-1) vs 250. (3) Query shape: GROUP BY vs plain `SELECT count(*)`.

**B2c. Workload.** Table `(pk int, c1 int, c2 int, v text, PRIMARY KEY (pk, c1, c2))`. One partition, `c1` in 0..9, `c2` in 0..N/10 with N = 200000 rows (4x the largest knob value, 2000x the smallest). Query `SELECT pk, c1, count(*) FROM t WHERE pk=1 GROUP BY pk, c1` gives 10 groups, so the result is tiny and rows read per sub-read dominate. N exceeds every knob value, so each sub-read hits the limit.

**B2d. Observables and instruments.** (a) The `DataLimits` of the built query: `stmt.getQuery(options, nowInSec).limits().toString()`; for GROUP BY it contains `LIMIT <rowLimit>` (`DataLimits.java:797-800`). (b) Rows counted per sub-read: wrap the sub-read by running the `ReadCommand` through `ReadCommand.executeLocally` with a custom `DataLimits.Counter` read through `counter.rowsCounted()` (`DataLimits.java:974`), or add a temporary counter in the copy's `AggregationQueryPager.fetchSubPage` (log `rowsCounted` per sub-page; the copy is disposable). (c) Number of sub-pages: ceil(N / rowLimit) expected. (d) Heap: `Runtime` used memory after `System.gc()` is too noisy; use allocation counting via `com.sun.management.ThreadMXBean.getThreadAllocatedBytes(threadId)` before/after each sub-page. Not observable directly: replica-vs-coordinator split inside one JVM.

**B2e. Procedure.**
1. Copy and build stock tree; write the test; run once with stock 10000 and record limits string and per-sub-page rowsCounted.
2. For each other knob value edit line 114 in the copy, `ant clean jar`, rerun.
3. Repeat with client page size 250 and with `SELECT count(*)` (no GROUP BY).
4. Delete `$WORK/c509` at the end.

**B2f. Predictions.** Limits string shows `LIMIT 100 / 1000 / 10000 / 50000` as the constant changes (client page size unset); `LIMIT 250` with client page size 250 regardless of the constant. Per sub-page `rowsCounted` equals the limit (last page smaller), and the number of sub-pages is ceil(200000 / limit): 2000, 200, 20, 4. Allocated bytes per sub-page scale roughly linearly with the limit (ratio of 50000 to 100 near 500, with fixed overhead lowering it). Plain `count(*)` shows no `LIMIT` in its limits string and one read of all N rows.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| rows per sub-page == constant, sub-page count as predicted, allocation per sub-page scales | claim confirmed |
| rows per sub-page exceed the constant | cap does not hold; claim refuted |
| limits string unchanged when the constant changes | constant is not what feeds `rowLimit`; trace wrong |
| allocation per sub-page flat while rows per sub-page change | rows capped but heap not tied to rows (large fixed cost); claim on heap not confirmed |
| plain `count(*)` also shows a limit | trace of `AGGREGATE_EVERYTHING` wrong |
| N smaller than the constant, so no sub-page reaches the limit | not confirmed; enlarge N |

**B2h. Controls.** Client page size 250 (a different path to the same `rowLimit`) shows the limit tracks the page size; plain aggregate is a negative control; rebuild each time to avoid stale inlined constants; same data and cache state for each run (single JVM, warm up once, discard first run).

### B3. Cluster tier

**B3a. Environment and build.** One node (second node optional for RF=2 coordinator/replica split) on local disk of known size (at least 20 GB free), JDK 11, built from the local copy for each knob value (`ant clean jar` after editing line 114; one build output directory per value). Settings: heap fixed `-Xms512m -Xmx512m` (small so transient read memory is visible), G1; `data_file_directories`, `commitlog_directory`, `saved_caches_directory`, `hints_directory` all on local disk; key cache and row cache off (`row_cache_size: 0MiB`), `tombstone_*` thresholds default, `page_size_*` guardrails left at -1, `native_transport_max_request_data_in_flight` default.

**B3b. Knobs.** `DEFAULT_PAGE_SIZE` = 500, 10000 (stock), 200000, via rebuild; client fetch size unset (the Python driver `fetch_size=None` is not enough because drivers set 5000 by default: use `cqlsh` with `PAGING OFF`, or a driver with `fetch_size=0`, so `options.getPageSize()` is not positive). Values: 500 (clearly small), stock, 200000 (larger than the data so the cap never binds, a "no cap" proxy).

**B3c. Workload.** Table `(pk int, c1 int, c2 int, payload blob, PRIMARY KEY (pk, c1, c2))`, `payload` 1 KiB. One partition with 2,000,000 rows (about 2 GB uncompressed; disk 20 GB is enough; disable compression to keep the arithmetic simple), flush and `nodetool compact` so reads come from sstables, then no further writes. Query `SELECT pk, c1, count(*) FROM t WHERE pk=1 GROUP BY pk, c1` with `c1` in 0..9 (10 groups, tiny result). Arithmetic: rows per sub-read at 500 / 10000 / 200000 is 0.5 MB / 10 MB / 200 MB of payload per sub-read, against a 512 MB heap, so the third value should pressure the heap, the first should not. Run the query 20 times back to back per value (about minutes). Positive control: the same data with a client fetch size of 500 and 200000 shows the same relation through a known bound path (page size guardrail, `page_size_fail_threshold`, can be used to reject 200000: set to 10000 via `nodetool` / JMX or yaml and confirm the rejection, which proves the guardrail path is live for client values).

**B3d. Observables and instruments.** Heap used peak: `jstat -gc <pid> 250` sampled every 250 ms (young + old used), or `-Xlog:gc*` GC log with `-Xlog:gc*:file=gc.log`; peak young-generation eden usage and GC pause counts per run. Allocation rate: `jcmd <pid> GC.heap_info` snapshots and `nodetool tablestats` / `nodetool tpstats` for ReadStage. Rows read per sub-read: `nodetool tablestats` "Local read count" delta and `tablehistograms` "cell count" per read. Disk: `df` on the data volume (should not change on reads). Not observable directly: per-query heap in a shared JVM; the GC log is the proxy.

**B3e. Procedure.**
1. Build the three variants into three directories. Start the stock one, create schema, load data with a driver (batches by partition, unlogged), `nodetool flush`, `nodetool compact`.
2. Warm: one full GROUP BY run, discard.
3. Start `jstat` and GC logging, run the query 20 times with paging off, record elapsed, peak heap, GC count; `nodetool tablehistograms` before/after.
4. Stop node, start the next variant on a copy of the same data directory (copy while stopped), repeat.
5. Control runs: client fetch size 500 and 200000 on the stock build; `SELECT count(*)` (no GROUP BY) on the stock build.
6. Stop all processes (`nodetool drain`, kill, `pgrep -f CassandraDaemon`), delete data directories.

**B3f. Predictions.** GROUP BY with unset client page size: per-read row count equals the constant, so the number of reads is 4000 / 200 / about 10 across the three values; peak heap rises with the constant, with 200000 giving at least several times the peak of 500 and, if the sub-read materializes about 200 MB plus overhead in a 512 MB heap, visibly more GC activity or possible OOM; 500 and 10000 stay well below the heap. The plain `count(*)` run (no GROUP BY, no row limit) reads without row-limit slicing and shows a heap profile not affected by the constant. Disk usage on the data volume is unchanged by reads in every run. Statement of failure: heap peak flat across 500 / 10000 / 200000.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| peak heap and per-read cell count rise with the constant (500 < 10000 < 200000) | claim confirmed |
| number of reads per query follows 2,000,000 / constant | internal paging confirmed |
| peak heap flat across the three values while the number of reads changes | rows are capped but heap is not tied to them (e.g. streaming, small footprint); claim on heap refuted or not shown |
| per-read cell count exceeds the constant | cap not holding; refuted |
| `count(*)` heap changes with the constant | constant also reaches plain aggregates; trace wrong |
| 200000 variant shows no more heap than 500 and the query did not read in pieces | limit never reached or the control did not move; not confirmed |
| guardrail rejection with fetch size 200000 when `page_size_fail_threshold` is set | positive control for client-side page size path works |

**B3h. Controls.** Same data and compaction state; same heap; cold vs warm cache fixed by discarding the first run; row cache off; same client; GC logging in every run; no concurrent load; client fetch size path as the second route to the same `rowLimit`; plain aggregate as the negative control. Repeat each value at least 3 times to separate GC noise.

**B4. Risks and cleanup.** Disk: 2 GB of data plus compaction headroom (about 6 GB) on local disk only; never on shared storage; commit log and hints on local disk. A 200000-row sub-read may OOM the 512 MB node: expected and acceptable, restart afterwards. Do not build in the shared source tree. Afterwards: `pgrep -f CassandraDaemon` empty, stop `jstat`, remove the data directories, the three build directories and `$WORK/c509`.

## C. Sources read

- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/INSTRUCTIONS.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/playbook-autonomous.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/_TEMPLATE-autonomous.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-in/81.md
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/filter/DataLimits.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/service/pager/AggregationQueryPager.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/Guardrails.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/GuardrailsOptions.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java (lines 873-874 via grep)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/transform/StoppingTransformation.java (grep and head)

## D. Stage-4 feedback

none yet
