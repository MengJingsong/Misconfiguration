<!-- file: cases/group-by-row-limit-incrementRowCount-rowsCounted--autonomous.md -->
# GROUP BY internal row limit (page size passed as `rowLimit`) — verification solution

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/filter/DataLimits.java:986` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code (Agent SDK), 2026-10-27 |
| Estimate | `positive` (with a byte-size caveat): the GROUP BY counter stops every internal read after `rowLimit` live rows, and `rowLimit` is the page size (client fetch size or 10000), so rows materialised per internal read are bounded. It is a row-count cap, not a byte cap, so memory is bounded only as rowLimit x row size. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** The `rowLimit` field of `CQLGroupByLimits` (inherited from `CQLLimits.rowLimit`, `DataLimits.java:349`, assigned `:367`). It is a per-query, runtime-built constant, not a yaml key. The target line is `GroupByAwareCounter.incrementRowCount()` (`DataLimits.java:983-988`): `if (++rowsCounted >= rowLimit) stop();`.
- First declaration: `CQLLimits.rowLimit` at `DataLimits.java:349`. `CQLGroupByLimits` passes it to `super(rowLimit, NO_LIMIT, false)` at `:679`.
- Where the value comes from: `SelectStatement.getDataLimits` (`SelectStatement.java:881-921`). For GROUP BY it calls `DataLimits.groupByLimits(cqlRowLimit, cqlPerPartitionLimit, pageSize, aggregationSpec)` (`:911-914`). Parameter 1 is the group limit (the user's `LIMIT`), parameter 3 is named `rowLimit` (`DataLimits.java:116-122`). The page size is passed in the `rowLimit` slot. The comment at `SelectStatement.java:896-897` says GROUP BY and aggregation queries "will always be paged internally to avoid OOM".
- Unit: rows (live rows, counted after the row passes `isLive`, `DataLimits.java:949-954`).
- Default: `pageSize = options.getPageSize()` (`SelectStatement.java:1923`). If it is <= 0 (paging off or unset), `DEFAULT_PAGE_SIZE = 10000` (`SelectStatement.java:114`, `:901-902`).
- How it is set: not by yaml. The client sets it through the driver or protocol fetch size, or cqlsh `PAGING <n>`. The guardrail `page_size_warn_threshold` / `page_size_fail_threshold` (`Guardrails.java:236-246`, `Config.java:873-874`, yaml `cassandra.yaml:2089-2090`, default -1 = off; checked at `SelectStatement.java:517`) can cap the client value. *[Amended 2026-10-27, A1: guardrails are not applied to superusers or internal calls, so a client that tests it must log in as an ordinary role under `PasswordAuthenticator`.]* No restart is needed. The 10000 default is a compile-time constant.
- Not applied to: `AGGREGATE_EVERYTHING` (plain `count(*)`, `sum()`), which gets `cqlLimits(NO_LIMIT, ...)` (`:920`) and is paged only by the `AggregationQueryPager` sub-page size. DISTINCT also takes another branch (`:908-909`, `:917-918`).

**A2. What it caps.** Heap, on both the replica and the coordinator: the number of live rows read in one internal sub-read of a GROUP BY query. The quantity compared is `rowsCounted` (`DataLimits.java:826`) against `rowLimit`. Rows are serialised into one `ByteBuffer` per replica response (`ReadResponse.java:46`, `LocalDataResponse.build` `:197`) and then deserialised and merged on the coordinator, so the cap bounds the per-sub-read materialised data.

**A3. Mechanism.**
1. `incrementRowCount()` runs for each live row in `applyToRow` (`:949-954`), after the new-group check (`:931-939`) and the done-for-partition check (`:943-947`).
2. When `++rowsCounted >= rowLimit`, `stop()` (`StoppingTransformation`) halts the row and partition iterators. The stopping row is still returned, so exactly `rowLimit` live rows pass (no off-by-one overshoot). Static-only partitions are counted in `onPartitionClose` (`:1022-1026`), which can call `incrementRowCount` once more.
3. `onClose` (`:1041`) treats `rowsCounted < rowLimit` as "end of data reached, so close the open group". If `rowsCounted == rowLimit`, the group is left open and the next sub-page continues it.
4. `AggregationQueryPager.GroupByPartitionIterator.fetchNextRowIterator` (`AggregationQueryPager.java:~222-250`) loops. It fetches a sub-page, and when it is drained it calls `updatePagerLimit` with `limits.forGroupByInternalPaging(state)` (`DataLimits.java:~739-746`, which sets `groupLimit = rowLimit`). It then fetches `pageSize - counted` more groups, until `counted == pageSize` or the pager is exhausted.
5. Because each sub-page ends after at most `rowLimit` rows, a single group (e.g. `GROUP BY pk` over one huge partition) is read in `ceil(rows / rowLimit)` bounded chunks. With paging off, the top-level page size is `NO_LIMIT` but `rowLimit` is still 10000, so reads are still chunked.
- Bypasses and overshoot:
  - The cap counts live rows only. Tombstones and shadowed data are not counted here (they are governed by `tombstone_*_threshold`).
  - Row size is unbounded: wide rows or large blobs make `rowLimit x rowSize` large (the cell/partition size limits are separate).
  - Multiple replicas and read repair multiply the footprint.
  - Sub-pages are sequential, so the previous one should be closed before the next, but the coordinator accumulates the page's output groups (up to `pageSize` groups).
  - A client fetch size of, e.g., 1,000,000 raises the cap itself unless the `page_size` guardrail is set.

**A4. Other consumers.** Memtables, the row/key/chunk caches, the OS page cache, compaction, other concurrent reads and the response serialisation buffers all use the same heap and are outside this cap. The `LIMIT` clause also uses `groupLimit`, not `rowLimit` (`:993`).

**A5. Evidence beyond the source.** None used. The in-tree comment at `SelectStatement.java:896-897` is the only stated design intent.

## B. Verification solution

**B1. Claim under test.** For a GROUP BY query, the number of live rows read in one internal sub-read equals `min(rowLimit, rows available)`, where `rowLimit` is the client fetch size (10000 when unset). Replica- and coordinator-side heap during the query scales with that value and is bounded when it is small, even if the partition holds far more rows.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a ~/cassandra-5.0.9/ /tmp/c509/`), then `cd /tmp/c509 && ant jar` (needs network for dependency download, or a prepared `~/.m2`). Add a new test class `test/unit/org/apache/cassandra/db/filter/GroupByRowLimitTest.java` (extends `CQLTester`, modelled on `test/unit/org/apache/cassandra/cql3/validation/operations/SelectGroupByTest.java`). Run it with `ant testsome -Dtest.name=GroupByRowLimitTest`. JVM options are the build's defaults (`-Xmx1g` is enough).

**B2b. Knobs.** The `pageSize` argument to `DataLimits.groupByLimits(groupLimit, perPartitionLimit, rowLimit, spec)`, with values 1, 7, 1000, 10000 and `DEFAULT_PAGE_SIZE` unset (to confirm the 10000 default). This is the exact slot `SelectStatement` fills at `:911`. Also vary the data shape: one group per partition vs many groups.

**B2c. Workload.** `CREATE TABLE t (pk int, ck int, v blob, PRIMARY KEY (pk, ck))`. Insert 1 partition with 50000 rows (ck 0..49999), each with a 1 KiB blob. `SELECT pk, count(v) FROM t WHERE pk=0 GROUP BY pk` has a single group of 50000 rows, so the limit is passed many times over. *[Amended 2026-10-27, A2: `count(*)` selects no regular column, so the replica would not read or serialise `v` and the bytes-per-row prediction of B2f could not hold; `count(v)` forces the blob to be read and returned. This applies to every GROUP BY query of both tiers. A3: the second table of 3000 groups has no prediction or conclusions row, so it is not run; the groupLimit path is the subject of another case file.]* For rowLimit=1000 the 50000 rows need 50 sub-reads; for 10000, 5.

**B2d. Observables and instruments.** For each local read, `Counter.rowsCounted()` (`DataLimits.java:972`), obtained from `limits.newCounter(...)` wrapped on `cmd.executeLocally(...)`, and the number of rows actually emitted by the wrapped iterator. Also the serialized size from `ReadResponse.createDataResponse(...).toDebugString`, or the length of the built buffer, as a proxy for the data materialised per sub-read. The count of sub-reads is the number of `updatePagerLimit` calls (count via a test subclass or by counting `fetchPageInternal` calls). Heap itself cannot be observed meaningfully in a unit test.

**B2e. Procedure.**
1. Build and create the tables with the Section B2c data and flush.
2. For each pageSize p in {1, 7, 1000, 10000}: build `DataLimits.groupByLimits(NO_LIMIT, NO_LIMIT, p, AggregationSpecification.aggregatePkPrefix(...))` (or issue the CQL via `executeNet` with `fetchSize=p` and record the counters).
3. Run `executeLocally` through the counter. Record rows emitted, `rowsCounted()`, and the buffer size.
4. Loop the sub-pager as `AggregationQueryPager` does (use `QueryPagers.pager(...).fetchPageInternal`) until exhausted; record sub-read count and the max rows in any single sub-read.
5. Repeat with paging unset (page size -1 in `QueryOptions`, as a client that sends no page size) to confirm the 10000 default. *[Amended 2026-10-27, A4: B2d's "serialised size" is the size of the first sub-read's data response: `cmd.createResponse(iterator, ...)` on the command with the real `DataLimits`, measured with `ReadResponse.serializer.serializedSize(resp, MessagingService.current_version)`; later sub-reads are not serialised, their cost is read as thread-allocated bytes (`ThreadMXBean`) over the whole drain.]*

**B2f. Predictions.** *[Amended 2026-10-27, A5 (before any reading): sub-read counts corrected, bytes-per-row given bounds, paging-off count corrected. Original text: "Rows emitted per sub-read = p exactly for p in {1, 7, 1000, 10000} on the 50000-row group (never p+1). Sub-reads = ceil(50000/p) = 50000, 7143, 50, 5. Serialised bytes per sub-read are about p x (1 KiB + overhead), so 1000 -> about 1 MiB and 10000 -> about 10 MiB, a linear relation in p. Paging off gives 5 sub-reads of 10000 rows." Reason: `onClose` counts the trailing group only if `rowsCounted < rowLimit` (`DataLimits.java:1041`), so when p divides 50000 the last full sub-read ends on `rowLimit` and one more, empty, sub-read is needed (the same rule was seen in the shakedown of a sibling case with 2000 rows: 3 sub-reads for p = 1000).]* Query `SELECT pk, count(v) FROM t WHERE pk = 0 GROUP BY pk` on the 50000-row group, for p in {1, 7, 1000, 10000} and paging unset. (1) White-box counter after the first sub-read: `rowsCounted == p` exactly (never p+1), groups 0, `isDone()` false. (2) End-to-end drain: every sub-read emits at most p rows, every non-empty sub-read except at most one (the remainder) emits exactly p, total rows 50000. (3) Sub-reads = floor(50000/p) + 1 = 7143, 51, 6 for p = 7, 1000, 10000 (for p = 1000 and 10000 the last is empty), and 50002 for p = 1 over two client pages *[Amended 2026-10-27, A10, after the unit shakedown at 2000 rows, an instrument check and not a reading: with p = 1 the top-level page size equals the one group the query returns, so the pager is not marked exhausted, the client asks for a second page, and that page makes one more empty sub-read (`AggregationQueryPager.java` `isDone(pageSize, counted)`: `counted == pageSize`); the earlier figure 50001 missed it]*. Paging unset: 6 sub-reads of at most 10000 rows, the same as p = 10000. (4) Serialised size of the first sub-read's data response: for p = 1000 and 10000, between 1024 and 1120 bytes per row (size/p), and size(10000)/size(1000) between 9 and 11 (about 1 MiB at 1000, about 10 MiB at 10000). (5) The control (plain `SELECT *` with `LIMIT p` and page size p) emits p rows and its serialised size per row is within 5 percent of the GROUP BY read's. A group-by with no cap would show one read of 50000 rows (about 50 MiB).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| max rows per sub-read == p, bytes linear in p | claim supported |
| any sub-read emits more than p rows (e.g. p+1, or the whole 50000) | the `:986` cap does not bind: claim wrong |
| per-sub-read bytes unchanged when p changes | rows are capped but the cap does not scale the materialised size: claim wrong |
| sub-read count != floor(rows/p)+1 (floor(rows/p)+2 for p = 1) *[Amended 2026-10-27, A5: was ceil(rows/p); A10: p = 1]* | the open-group continuation (`:1041`) behaves differently from traced: re-check A3 step 3 |
| paging unset gives a single 50000-row read | the 10000 default is not applied: claim wrong |
| any other reading (for example bytes per row outside 1024-1120 while rows == p) | *[Amended 2026-10-27, A5]* **Not confirmed (no matching row)**: recorded as found, prediction not edited |

(The positive-negative extra rows for a negative estimate do not apply, since the estimate is positive.)

**B2h. Controls.** The same data read with a plain `SELECT * ... LIMIT` and `cqlLimits(p)` (the `CQLCounter` path at `:509`) gives the same per-read row count, showing the harness measures the cap and not a test artifact. Use a different seed for the blob content to rule out compression effects (none apply to memtable/response buffers).

### B3. Cluster tier

**B3a. Environment and build.** Two nodes, RF=2, local disk of known size (>= 10 GB free; data, commitlog and hints on `/tmp`-style local paths). Build `ant jar` in the local copy. `cassandra-env.sh`: `MAX_HEAP_SIZE=512M`, `HEAP_NEWSIZE=128M`, and add `-XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/localdisk/dumps` plus `-Xlog:gc*:file=/localdisk/gc.log`. Defaults otherwise. `read_request_timeout` at 10 s may need raising to 60 s so slow runs are not mistaken for failures. *[Amended 2026-10-27, A6: the two nodes are two JVMs on one machine (pc07), loopback addresses 127.0.8.1 and 127.0.8.2 (port slot 8), JMX 7180 / 7181, data on tmpfs (`/dev/shm`) of known free space, not a local disk; heap dumps are off (`-XX:-HeapDumpOnOutOfMemoryError`), the GC log is kept. `range_request_timeout`, `read_request_timeout`, `request_timeout` = 600000ms and `native_transport_timeout` = 600s: the coordinator's range deadline spans every sub-read of one request (a sibling case timed out at 10 s with 5001 sub-pages). A12 (runbook defect found by cluster attempt 1, 2026-10-27, tier restarted; no prediction or conclusion text changed): loading 200000 rows x 4 KiB into one partition with a 512 MB heap killed node 1 (`OutOfMemoryError`, live set up to 465 MB of 512 MB while loading) before any query, so the load phase runs with a 2 GiB heap and both nodes are restarted with the measured 512 MB heap before the idle baseline; every measurement runs at 512 MB.]*

**B3b. Knobs.** Client fetch size: 100, 1000, 10000 (default), 100000, 1000000, set through cqlsh `PAGING <n>` or the driver (`SimpleStatement.setPageSize`). Secondary knob: `page_size_fail_threshold: 20000` in yaml (restart or JMX/nodetool guardrail setter if present) to show the guardrail turns an over-large value into an error.

**B3c. Workload.** Table `ks.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck))`, populate partition 0 with 200000 rows x 4 KiB blob (about 800 MB raw), written with `cassandra-stress` or a driver loop with unlogged batches per row group, then `nodetool flush`. Query: `SELECT pk, count(*) FROM ks.t WHERE pk=0 GROUP BY pk` at each fetch size. The query has one group, so all 200000 rows are read in rowLimit-sized sub-reads. Note that `count(*)` without values still reads cells; use `SELECT pk, max(ck), count(v)` if `v` must be materialised. Each setting is run 3 times, about 1-2 minutes each. At 4 KiB rows: fetch 1000 -> about 4 MB per sub-read, 10000 -> about 40 MB, 100000 -> about 400 MB (exceeds 512M heap with serialised plus deserialised copies), 1000000 -> more than the heap.

**B3d. Observables and instruments.** Heap peak via `jstat -gc <pid> 200` (sample 5/s, record max of used old+young) on both nodes, and the GC log. *[Amended 2026-10-27, A7: `jstat` is replaced by a JMX poller reading `HeapMemoryUsage.used` every 100 ms on both nodes. "Peak heap above baseline" in B3f/B3g is defined as: the maximum heap occupancy after a GC pause inside the query window (the `X->Y` value of a `Pause` line in `gc.log`; this approximates live data, because sampled `used` also holds garbage that G1 has not collected), minus the occupancy after the forced full GC (`jcmd <pid> GC.run`) that precedes the cell. The maximum sampled `used` is reported beside it but the rows of B3g are read against the post-GC figure. The mid-query `GC.class_histogram` is not taken (it stops the world and perturbs the query); this is a named gap. Which node served the read is read from a Byteman observation rule on `GroupByAwareCounter.onClose` that writes rows per sub-read to a file per node.]* `nodetool gcstats`, and `jcmd <pid> GC.class_histogram` taken mid-query for `byte[]`/`HeapByteBuffer` totals. Query outcome and latency from the client. OOM count and heap dumps. The data-per-sub-read figure cannot be read directly in a live node, so it is inferred from the peak-heap delta against the idle baseline. Disk is also checked (`df`) to confirm no spill.

**B3e. Procedure.**
1. Start both nodes with the options in B3a; create the schema (RF=2) and load the data; flush; wait for compaction to settle.
2. Record an idle heap baseline (`jstat`, 30 s).
3. For each fetch size in the order 100, 1000, 10000, 100000, 1000000: restart the nodes (or force GC with `jcmd <pid> GC.run`), start `jstat` logging, run the query three times, stop `jstat`, and collect max used heap and any OOM/timeout from the logs.
4. Repeat with `PAGING OFF`.
5. Set `page_size_fail_threshold` to 20000 and run fetch 100000; expect a `Aborting query ... page size ... exceeds fail threshold` error. *[Amended 2026-10-27, A8: the cluster runs `PasswordAuthenticator` from the start with an ordinary role `app` (superusers skip guardrails); all cells run as `app` so that the guardrail arm differs only in the threshold, set through the guardrail JMX bean `GuardrailsMBean.setPageSizeThreshold(-1, 20000)` (no restart). Client: the bundled Python driver replaces cqlsh (`PAGING <n>` = the driver's `fetch_size`; `PAGING OFF` = `fetch_size=None`); each cell keeps the 3 repetitions.]*
6. Collect logs, then clean up as in B4.

**B3f. Predictions.** Peak heap above baseline grows roughly linearly with fetch size while below the heap limit: fetch 1000 about +10 to 30 MB, 10000 about +100 to 300 MB (the response buffer plus its deserialised copy plus the coordinator's rows), where the bytes-per-row factor is about 4 KiB x 2-3 copies. Fetch 100 stays near baseline. Fetch 100000 and above should cause OOM or severe GC (over 50 percent of time in GC) in a 512 MB heap. `PAGING OFF` behaves like fetch 10000 (peak within 20 percent of it), not like unbounded (no OOM from reading all 200000 rows at once). The guardrail run fails fast with the error and a flat heap. *[Amended 2026-10-27, A9 (before any reading): "OOM or severe GC" is measured as an `OutOfMemoryError` in a node's `system.log` or a client error, or the sum of GC pause time inside the query window above 50 percent of the query's wall time (from `gc.log`); "peak heap above baseline" is the post-GC figure defined in B3d (A7); "within 20 percent" compares the means of the 3 repetitions. The 100-byte-row control (B3h 2) runs at fetch 10000 and 100000 on a separate table `ks.s` (200000 rows).]*

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| peak heap rises with fetch size and PAGING OFF matches 10000 | claim supported: the row cap governs heap |
| PAGING OFF peaks far above the 10000 run (towards all 200000 rows, about 800 MB, OOM) | the internal cap does not bind when paging is off: claim wrong |
| peak heap identical across 100 and 100000 | the fetch size does not reach `rowLimit` or memory is not governed by it: claim wrong |
| 1000000 succeeds with a peak below the 10000 run | the cap is not the dominant factor (something else bounds it): claim wrong |
| 100000 succeeds with peak well below the model | rows are not materialised as a whole per sub-read (streaming): claim partly wrong, record the real slope |
| OOM only at the large sizes, none at 100 to 10000 | claim supported with boundary |
| any other reading | *[Amended 2026-10-27, A9]* **Not confirmed (no matching row)**: recorded as found, prediction not edited |

**B3h. Controls.** (1) A plain `SELECT * FROM ks.t WHERE pk=0` with the same fetch sizes, to show the ordinary paging path scales the same way (the harness measures page size effects, not an artifact of GROUP BY). *[Amended 2026-10-27, A11 (a time and safety bound, outside the frozen B2f/B2g/B3f/B3g tables): the control runs at fetch sizes 100, 1000, 10000 (3 repetitions each) and 100000 (1 repetition, 120 s client timeout); 1000000 and unset are not run, because a plain page of that size is an 800 MB response on a 512 MB heap: in the scale-5 shakedown (an instrument check) the control at fetch 100000 stalled for 10 minutes and killed a node. The B3h-1 comparison reads fetch 100, 1000, 10000.]* (2) Rows of 100 bytes (same 200000 count) at fetch 100000: heap about 10 MB x copies, no OOM, showing bytes (not rows) are the real determinant, which is the byte-size caveat in the Estimate. (3) Idle baseline and a `nodetool` flush/compaction-quiet period so background work does not contaminate the peak. (4) Compare node 1 (coordinator) and node 2 (replica) separately.

**B4. Risks and cleanup.** Unit tier: writes only under the build directory on local disk. Cluster tier: 800 MB raw x RF=2 plus commitlog needs about 4 GB; keep all of it on a local disk of known size, not on shared storage; heap dumps can reach 512 MB each (keep the OOM tests few, delete dumps afterwards). Never build inside the shared source tree. At the end, stop both nodes (`nodetool drain`, then `kill`), check that no `CassandraDaemon` or `jstat` process remains (`pgrep -fl 'CassandraDaemon|jstat'`), and `rm -rf` the data, commitlog, hints, logs and dumps directories.

## C. Sources read

- `~/writeup-A/playbook-autonomous.md`
- `~/writeup-A/_TEMPLATE-autonomous.md`
- `src/java/org/apache/cassandra/db/filter/DataLimits.java` (lines 44-125, 225-345, 347-370, 643-1137)
- `src/java/org/apache/cassandra/cql3/statements/SelectStatement.java` (lines 114, 296, 326, 390, 880-925, 1923)
- `src/java/org/apache/cassandra/service/pager/AggregationQueryPager.java` (lines 40-64, 114-300)
- `src/java/org/apache/cassandra/db/guardrails/Guardrails.java` (lines 235-246)
- `src/java/org/apache/cassandra/config/Config.java` (lines 873-874), `conf/cassandra.yaml` (lines 2089-2090)
- `src/java/org/apache/cassandra/db/ReadResponse.java` (lines 46-63, 182-197, by grep)
- `test/unit/org/apache/cassandra/cql3/validation/operations/SelectGroupByTest.java` (existence only)

## D. Stage-4 feedback

**Stage-4 design-audit amendments, 2026-10-27** (made before run 1; none depends on a reading; each is marked next to the text it changes): A1 guardrail applies to non-superusers only (A1); A2 `count(v)` instead of `count(*)` in every GROUP BY query (B2c); A3 second 3000-group table not run (B2c); A4 definition of the serialised-size instrument (B2e); A5 sub-read counts floor(N/p)+1, bytes-per-row bounds, paging-unset count, catch-all row (B2f, B2g); A6 two nodes on one machine, tmpfs, timeouts (B3a); A7 peak-heap definition and instruments (B3d); A8 authentication and client for the guardrail arm (B3e.5); A9 measurable "severe GC", catch-all row (B3f, B3g); A10 sub-read count at p = 1 is 50002 over two client pages (B2f, B2g); A11 bounded plain-SELECT control (B3h); A12 load phase with a 2 GiB heap, measured phase at 512 MB (B3a, runbook defect D1).

**Stage 4, 2026-10-27 (results: `stage4-runtime-verification/results/group-by-row-limit-incrementRowCount-rowsCounted--autonomous.md`; harness: `stage4-runtime-verification/harness/group-by-row-limit-incrementRowCount-rowsCounted--autonomous/`).** Unit **Confirmed — caps**; cluster **Confirmed — caps**; outcome class **true positive**. The B1 trace held: every internal sub-read of a GROUP BY stops at exactly `rowLimit` rows (white-box `rowsCounted == p`, never p+1, for p = 1, 7, 1000, 10000 and paging unset), the first sub-read's serialised response is 1036 bytes per row (size(10000)/size(1000) = 10.000), and sub-reads number floor(rows/p)+1. On two 512 MB nodes with one 200000 x 4 KiB partition the post-GC peak above baseline rose +2.0 / +12.3 / +314 MB for fetch 100 / 1000 / 10000, paging unset gave +327 MB (peak occupancy within 3.6 percent of fetch 10000), and fetch 100000 and 1000000 killed the nodes (OOM, read from the GC log; `kill -9` leaves no log line). The `page_size_fail_threshold` guardrail (non-superuser) rejected fetch 100000 in 4-14 ms with a flat heap. Misses and notes: (1) the filed band for fetch 10000 was +100 to +300 MB, observed +314 MB (4.8 percent above), recorded, not edited; (2) the 100-byte-row control read +112 to +128 MB at fetch 100000 (filed: "about 10 MB x copies"): no OOM, which is the control's point; (3) the cap is a row count: with 4 KiB rows fetch 100000 exceeds the 512 MB heap, so on a small heap the page size the client sends (or the guardrail) decides whether a GROUP BY fits; (4) the plain `SELECT *` control was bounded (A11) and the load needed a 2 GiB heap (A12). Doc note: for GROUP BY the page size is also the internal row limit (`SelectStatement.getDataLimits` passes it in the `rowLimit` slot, default 10000).
