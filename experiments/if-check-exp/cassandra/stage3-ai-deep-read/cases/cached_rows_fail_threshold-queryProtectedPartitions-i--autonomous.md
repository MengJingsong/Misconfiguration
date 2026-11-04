# replica_filtering_protection.cached_rows_fail_threshold — verification solution  <!-- file: cases/cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`ReplicaFilteringProtection.java:430`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/ReplicaFilteringProtection.java#L430) (`if (i > 0) mergeListener.populate();`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (Claude Code CLI, stage-3 autonomous agent, Band D triage), 2026-10-26 |
| Estimate | `positive`. The target branch belongs to replica filtering protection (RFP), which materializes replica rows on the coordinator heap; every cached row goes through `incrementCachedRows()`, which throws `OverloadedException` once the per-query count exceeds `cached_rows_fail_threshold`, so the number of cached rows per query is capped at threshold+1 (rows, not bytes). |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `replica_filtering_protection.cached_rows_fail_threshold`;
configuration entry (nested yaml block). Declared at
[`ReplicaFilteringProtectionOptions.java:27`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/ReplicaFilteringProtectionOptions.java#L27)
(`public volatile int cached_rows_fail_threshold = DEFAULT_FAIL_THRESHOLD;`), default
`DEFAULT_FAIL_THRESHOLD = 32000` at `:23`; container field
[`Config.java:537`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L537). Unit: rows (per query, counted across all replicas). Shipped
`conf/cassandra.yaml:1822-1837` (`cached_rows_fail_threshold: 32000`). Settable in yaml
(restart) and at runtime via JMX `StorageServiceMBean.setCachedReplicaRowsFailThreshold`
([`StorageServiceMBean.java:999`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageServiceMBean.java#L999), [`StorageService.java:6749-6752`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L6749-L6752) ->
`DatabaseDescriptor.setCachedReplicaRowsFailThreshold` [`DatabaseDescriptor.java:2867-2869`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L2867-L2869));
read per query at [`DataResolver.java:257-258`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/DataResolver.java#L257-L258), so a runtime change takes effect on the next
query. Sibling: `cached_rows_warn_threshold` (default 2000, `:26`) only warns.


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../../../stage3-ai-deep-read/README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** Coordinator heap: the rows RFP holds in `PartitionBuilder.contents`
(`ReplicaFilteringProtection.java:458`, an `ArrayDeque<Unfiltered>`) and `staticRow`
while it waits to complete stale rows from silent replicas. Compared quantity:
`currentRowsCached` (`:116`), incremented once per row version per replica, null versions
included (`addRow`, `:477-492`).

**A3. Mechanism.**
1. `DataResolver.resolve()` takes the RFP path when the query uses replica-side filtering
   (index or `ALLOW FILTERING`) at CL above ONE ([`DataResolver.java:122-144`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/DataResolver.java#L122-L144)), building an
   RFP with both thresholds (`:252-258`).
2. First phase: replica responses are merged with `rfp.mergeController()` as the merge
   listener (`:261-264`). For each merged row, `PartitionMergeListerner.onMergedRows`
   calls `builders.get(i).addRow(versions[i])` for every replica ([`ReplicaFilteringProtection.java:215-219`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/ReplicaFilteringProtection.java#L215-L219)).
3. `addRow` -> `incrementCachedRows()` (`:316-332`): `currentRowsCached++`; when it equals
   `cachedRowsFailThreshold + 1` it logs, traces and throws `OverloadedException`
   (`:320-331`), aborting the query; at warn+1 it sends a client warning (`:333-345`).
4. Second phase: `queryProtectedPartitions` (`:358-449`) pulls partitions from the merged
   first-phase iterator. The target lines `:420-430` consume up to `command.limits().count()`
   rows from the current partition (only when not `consumeEntirePartitions`, `:143`), and
   if at least one row was consumed (`i > 0`, the target) call `mergeListener.populate()`
   to queue the builders (`:293-297`, `:309-313`). Consuming rows is what drives step 2-3.
5. Release: when an original partition iterator is closed, `releaseCachedRows(partitionRowsCached)`
   (`:347-351`, called at `:564`) lowers the count; `maxRowsCached` is reported to
   the histogram `rfpRowsCachedPerQuery` on close (`:282-286`; `TableMetrics.java:356,837`).
   - Outcome at the limit: the query fails with `OverloadedException`; nothing caps silently.
   - Overshoot: the cap counts rows, not bytes; a row's size is unbounded, so heap per
     cached row can be arbitrarily large. Null versions count but use no heap (`:481-485`), so
     the count overstates heap for silent replicas. The cap is per query; concurrent queries
     multiply. The count is per partition window (released on partition close), so a range
     query over many small partitions never reaches it.
   - The comment at `:483-484` notes the assumption that null rows will be fetched later.

**A4. Other consumers.** The raw `Message<ReadResponse>` payloads of every replica
(`DataResolver` / `ReadCallback`) are held in full regardless of this cap; second-phase
fetches (`fetchFromSource`, `:604-650`, `DataLimits.NONE`) can return unbounded rows;
short-read protection extra fetches; read-repair mutations; the CQL result message; other
queries and caches.

**A5. Evidence beyond the source.** `conf/cassandra.yaml:1815-1837` comment ("materializes
replica results by partition on-heap at the coordinator ... limit the number of rows ... can
materialize on-heap"); CASSANDRA-15907 (introduced thresholds), CASSANDRA-19018 (the
LIMIT-bounded consumption at `:420-430`), linked from the class javadoc `:89-92`;
`test/distributed/org/apache/cassandra/distributed/test/ReplicaFilteringProtectionTest.java`
(`testMissedUpdatesAroundCachingFailThreshold`, `:96-110`, setters at `:120-121`, metric at `:233`).

## B. Verification solution

**B1. Claim under test.** For a replica-filtering query whose replicas disagree, the
number of rows RFP holds on the coordinator heap never exceeds `cached_rows_fail_threshold`
(the query fails at threshold+1), and the coordinator's live heap attributable to cached rows
scales with min(threshold, rows that would be cached unbounded).

### B2. Unit tier

In-JVM dtest (`org.apache.cassandra.distributed.Cluster`, two instances inside one test
JVM). No external node is started; RFP needs two replica responses, which a plain
single-node CQLTester cannot produce.

**B2a. Environment and build.** JDK 11, Ant. `git clone --branch cassandra-5.0.9 /Users/yangwang/cassandra-src /local/c509-rfp` (local disk; never build in the shared clone). Add
`test/distributed/org/apache/cassandra/distributed/test/RfpCapProbeTest.java` in the copy.
`ant jar build-test` then `ant test-jvm-dtest-some -Dtest.name=org.apache.cassandra.distributed.test.RfpCapProbeTest`. Test JVM default heap from build.xml is fine (rows are small here).

> **Amendment U1 (2026-10-27, stage-4 audit; replaces the paths and commands above).** Host: the advisor's Mac
> (`environment-advisor.md`). Clone: `W=~/Library/Caches/stage4`; `git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run50`
> (no `/local` on this host), then `cd $W/cassandra-run50 && ant -Dlocal.repository=$W/m2 build-test` (`build-test` already
> compiles what the in-JVM dtest needs; no `ant jar`). The test class is kept in
> `stage4-runtime-verification/harness/cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous/RfpCapProbeTest.java` and copied
> into the clone at `test/distributed/org/apache/cassandra/distributed/test/` only for the run (removed afterwards); the run is
> `harness/…/unit-run.sh r1`, i.e. `ant -Dlocal.repository=$W/m2 test-jvm-dtest-some -Dtest.name=org.apache.cassandra.distributed.test.RfpCapProbeTest`
> (one forked JVM, `-Xmx8G` from `build.xml:1835`). The frozen values are the test's defaults; a shakedown may override them only through
> `-Dtest.jvm.args="-Drfp.n=… -Drfp.ts=… -Drfp.ctl=…"` (plain `-D` on the ant line does not reach the forked JVM, `build.xml:1192`).
> Every reading is one stdout line starting `RFPU` in `build/test/logs/**/TEST-<class>.log`.

**B2b. Knobs.** `cached_rows_fail_threshold` T in {1000, 10000, 100000}; warn threshold
fixed at `Integer.MAX_VALUE`. Set via `cluster.get(1).runOnInstance(() -> StorageService.instance.setCachedReplicaRowsFailThreshold(T))`
before each query (runtime-effective, A1). T=100000 is above the workload's demand (unbounded control).

> **Amendment U2 (2026-10-27, stage-4 audit; group A: the default was missing).** T ∈ {1000, 10000, **32000 (the default,
> `ReplicaFilteringProtectionOptions.java:23`)**, 100000}. The fail threshold is read back with
> `StorageService.instance.getCachedReplicaRowsFailThreshold()` after it is set, and the warn threshold likewise (`Integer.MAX_VALUE`;
> `currentRowsCached == Integer.MAX_VALUE + 1` can never hold, `ReplicaFilteringProtection.java:333`).

**B2c. Workload.** `Cluster.build(2).withConfig(c -> c.set("hinted_handoff_enabled", false)).start()`;
keyspace RF=2; `CREATE TABLE ks.t (k int, c int, v text, PRIMARY KEY (k, c))`.
Insert one partition k=0 with N=20000 rows `v='old'` at `ConsistencyLevel.ALL`. Then on
node 1 only, `cluster.get(1).executeInternal("UPDATE ks.t SET v='new' WHERE k=0 AND c=?", c)`
for all c (local write, newer timestamp, not replicated). Query from node 1:
`SELECT * FROM ks.t WHERE v='old' ALLOW FILTERING` at `ALL` (unpaged `coordinator(1).execute`).
Node 2 returns 20000 rows, node 1 none; each merged row calls `addRow` on 2 builders, so the
unbounded cached count is 2N = 40000 (range query -> `consumeEntirePartitions=true`, `:143`).
Arithmetic: 40000 > 1000 and > 10000, < 100000.

**B2d. Observables and instruments.** (1) Whether the query throws (exception class/message
containing `cached_replica_rows_fail_threshold`); (2) node 1
`ColumnFamilyStore.metricsFor(id).rfpRowsCachedPerQuery.getSnapshot().getMax()` read via
`runOnInstance` after each query (reset by using a fresh table per T); (3) node 1 log line
"Replica filtering protection has cached over". Heap is not measured in this tier.

**B2e. Procedure.** For each T: create a fresh table `t_T`, load as B2c, set T, run the query
inside try/catch, record (1)-(3). Close the cluster in `@AfterClass`.

> **Amendment U3 (2026-10-27, stage-4 audit; makes B2c/B2e exact).** One cluster for all runs: `init(Cluster.build(2).withConfig(c ->
> c.set("hinted_handoff_enabled", false)).start())` (keyspace `distributed_test_keyspace`, RF 2). Runs in this order: T = 1000, 10000,
> 32000, 100000, then the B2h control. For each: `CREATE TABLE <ks>.t_<T> (k int, c int, v text, PRIMARY KEY (k, c))`; for c = 0 … N−1
> (N = 20,000) `INSERT INTO <ks>.t_<T> (k, c, v) VALUES (0, ?, 'old')` through `coordinator(1)` at ALL; then for every c on node 1 only
> `executeInternal("UPDATE <ks>.t_<T> SET v = 'new' WHERE k = 0 AND c = ?")`; set warn = `Integer.MAX_VALUE` and fail = T on node 1, read
> both back; record the histogram count and the `replicaFilteringProtectionRequests` meter count and a node-1 log mark; run
> `coordinator(1).executeWithResult("SELECT * FROM <ks>.t_<T> WHERE v = 'old' ALLOW FILTERING", ALL)` (unpaged: page size
> `Integer.MAX_VALUE`, `CoordinatorHelper.java`) inside try/catch; record outcome, rows, exception class and message, the number of node-1
> log lines containing "Replica filtering protection has cached over" since the mark, histogram samples added and `getSnapshot().getMax()`,
> and the RFP request meter delta. **Control (B2h):** table `t_ctl`, loaded the same way **without** the node-1 update, queried at
> T = 100000. **Instrument check:** on node 1, a fresh `DecayingEstimatedHistogramReservoir(true)` updated once with each of 1001, 10001,
> 32001, 40000, 200000 must read `getMax()` = 1109, 11864, 35425, 42510, 219342 (U4).

**B2f. Predictions.** T=1000: `OverloadedException` (surfaced to the coordinator call as a
failure), histogram max = 1001. T=10000: exception, max = 10001. T=100000: query returns 0
rows (all 'old' rows are stale), histogram max = 40000.

> **Amendment U4 (2026-10-27, stage-4 audit; restates the predictions above in the instrument's units, derived from source before any
> reading).** `rfpRowsCachedPerQuery` is a `DecayingEstimatedHistogramReservoir` (`TableMetrics.java:837`, `CassandraMetricsRegistry.java:95-101`);
> `getMax()` returns the **upper bound of the highest non-empty bucket**, not the value (`DecayingEstimatedHistogramReservoir.java:537-549`;
> offsets `EstimatedHistogram.newOffsets(164, true)`, `EstimatedHistogram.java:91-109`: …, 924, 1109, …, 9887, 11864, …, 29521, 35425,
> 42510, …). The value recorded on close is `max(currentRowsCached, maxRowsCached)` (`ReplicaFilteringProtection.java:289`), and on the
> failing path `currentRowsCached` = T+1 (incremented before the check, `:321-331`). Unbounded demand: 2N = 40,000 (one partition,
> `consumeEntirePartitions` = true for a range read, `:143`; two `addRow` per merged row, `:222`). Predictions:
> T = 1000: `OverloadedException`, message contains "cached over 1000 rows" and `cached_replica_rows_fail_threshold`, exactly 1 node-1 log
> line, histogram max **1109** (bucket of 1001). T = 10000: same with **11864**. T = 32000 (default): same with **35425**. T = 100000:
> success, 0 rows, histogram max **42510** (bucket of 40,000), RFP request meter ≥ 1, no log line. Control: success, **20,000 rows**,
> histogram max **42510**, RFP request meter 0, no log line.

> **Amendment D1 (2026-10-27, stage-4 runbook defect found at the unit shakedown, before run 1; the predictions and rows are unchanged).**
> (i) A "log line" in U3/U4/U5 and C6/C7 is a line written by RFP's own `logger.error` (`ReplicaFilteringProtection.java:329`), counted
> with the pattern `ReplicaFilteringProtection\.java:[0-9]+ - Replica filtering protection has cached over`. In the in-JVM dtest the
> isolated executor also reports the uncaught exception (`JVMStabilityInspector`), and that report's message line contains the same text,
> so the plain-text count of U3 reads 2 per failure; the plain count is still recorded, for information only. (ii) The in-JVM dtest target
> prints the test's stdout to the ant console (`showoutput="true"`, `build.xml:1827`), so the `RFPU` lines are read from the copied ant log,
> not from a `TEST-<class>.log` (U1).

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| Failure and max = T+1 for T<2N; success and max = 2N for T=100000 | claim holds at the operand level |
| T=1000 or 10000 succeeds, or max > T+1 | claim wrong: the counter does not bound caching |
| T=100000 max far below 40000 | workload did not produce divergence; test invalid, not a refutation |

> **Amendment U5 (2026-10-27, stage-4 audit; B2g rows read in bucket terms and rows added before any reading).** Row 1 reads "failure,
> exactly one log line and histogram max = bucket(T+1) for every T < 2N (1000, 10000, 32000); success with max = bucket(2N) for
> T = 100000; control as U4 — claim holds at the operand level". Row 2 reads "any T < 2N succeeds, or its histogram max is above bucket(T+1)
> — claim wrong". Added rows: (a) a T < 2N run fails with an exception other than `OverloadedException`, or with a histogram max below
> bucket(T+1) — invalid run for that T (the failure is not the check); (b) a failing run adds no histogram sample — the disallow fired but the
> operand cannot be read; **Not confirmed (instrument)**; (c) the control returns ≠ 20,000 rows or its max ≠ 42510 — the counting rule of
> A3 is wrong; Not confirmed; (d) a threshold read-back differs from the intended T — invalid run; (e) the instrument check of U3 fails —
> histogram readings not interpretable; Not confirmed.

**B2h. Controls.** T=100000 shows the workload really demands 40000; a run with no
node-1 local update (replicas agree) should still cache 2N in the first phase (rows are cached
before divergence is known) - record it to confirm the counting rule; fresh table per T avoids
histogram carry-over.

### B3. Cluster tier

**B3a. Environment and build.** One Linux host, two nodes on 127.0.0.1 and 127.0.0.2, each
from its own copy of the built tree (`/local/c509-n1`, `/local/c509-n2`; `ant jar` once in the
local clone, then copy). Per node `cassandra.yaml`: `listen_address`/`rpc_address` = its IP,
`seeds: 127.0.0.1`, `num_tokens: 16`, `hinted_handoff_enabled: false`,
`data_file_directories`, `commitlog_directory`, `saved_caches_directory`, `hints_directory`
on local disk under `/local/c509-nX/var` (needs ~3 GB free). JMX ports 7199 / 7299
(`JMX_PORT` in `conf/cassandra-env.sh`). `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`, G1, plus
`-Xlog:gc*:file=/local/c509-n1/gc.log:time,uptime`.

> **Amendment C1 (2026-10-27, stage-4 audit; replaces the host, paths, build and copies above).** Host: the advisor's Mac
> (`environment-advisor.md`; loopback aliases 127.0.0.1–.3 on `lo0`). Both nodes run from the one built clone `$W/cassandra-run50`
> (no `ant` while a node runs), each with its own `CASSANDRA_CONF`, `CASSANDRA_LOG_DIR` and data under `$W/node-rfp1`, `$W/node-rfp2`.
> Per-node yaml (the shipped file plus overrides): `cluster_name: 'rfp'`, `num_tokens: 16`, `listen_address`/`rpc_address` = its IP,
> `hinted_handoff_enabled: false`, **`auto_bootstrap: false`** (zero-copy bootstrap streaming fails on this Mac, so a joining node stays
> joining), **`read_request_timeout: 60000ms` and `range_request_timeout: 60000ms`** (the second-phase fetch waits on a deadline counted
> from the query start, `ReadCallback.java:98-100,128-130`; held fixed for every T), directories under the node folder; the shipped
> `seeds: "127.0.0.1:7000"` and `replica_filtering_protection` block are kept. Node 2's `cassandra-env.sh` copy sets `JMX_PORT="7299"`.
> `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`; G1 is the shipped default (`jvm11-server.options:63`) and `cassandra-env.sh:83` already writes
> `gc.log` to the node's log folder, so no extra `-Xlog` flag. Node 1 also gets the Byteman agent of C4. Driven by
> `harness/…/cluster-run.sh r1`. Cleanup (replaces B4's paths): both nodes stopped with `nodetool stopdaemon`, no
> `Cassandra[D]aemon` process left, `$W/node-rfp*` removed, the clone's `git status` clean.

**B3b. Knobs.** T in {1000, 10000, 1000000} on node 1. No nodetool command exists for this
key, so set it over JMX:
`echo "set -b org.apache.cassandra.db:type=StorageService CachedReplicaRowsFailThreshold T" | java -jar jmxterm.jar -l localhost:7199`
(or restart with yaml). 1000000 is the unbounded control.

> **Amendment C2 (2026-10-27, stage-4 audit; group A: the default was missing; jmxterm is absent).** T ∈ {1000, 10000, **32000 (the
> default)**, 1000000} on node 1, set and read back over JMX with `harness/…/RfpJmx.java` (`set <T>` writes the StorageService attribute
> `CachedReplicaRowsFailThreshold` and prints the read-back, `StorageServiceMBean.java:996-999`).

**B3c. Workload.** Keyspace `rfp` RF=2, table as B2c but `v text, pad blob`. Load with the Python
driver (CL ALL) one partition k=0 with N=100000 rows, `v='old'`, `pad` = 4 KiB random
(~400 MB serialized per replica). `nodetool -p 7299 drain` and stop node 2; on node 1 run
`UPDATE rfp.t SET v='new' WHERE k=0 AND c=?` for all c at CL ONE; start node 2. Node 2 now
holds 'old', node 1 'new'. Query (driver pinned to 127.0.0.1 with `WhiteListRoundRobinPolicy`,
`fetch_size=None` i.e. paging off, `request_timeout=120`, CL ALL):
`SELECT * FROM rfp.t WHERE v='old' ALLOW FILTERING` (`SELECT *` so `pad` is materialized). Unbounded demand: 2N = 200000
cached row versions, of which N=100000 carry ~4 KiB each = ~400 MB on heap at peak (plus raw
response). Duration: one query per T, about 1 min each.

> **Amendment C3 (2026-10-27, stage-4 audit; the workload as written cannot reach RFP).** (i) **`pad` is 512 bytes, not 4 KiB.** With
> N = 100,000 rows of 4 KiB, node 2's first-phase response is ≈ 410 MB, above the default `internode_max_message_size` of 128 MiB
> (`DatabaseDescriptor.java:990-997`); `OutboundConnection.enqueue` refuses it (`OutboundConnection.java:331-332`), so the query would
> time out before RFP runs. With 512 B the response is ≈ 54 MB. (ii) **The table is created `WITH read_repair = 'NONE'`**: after a
> successful query the default blocking read repair would write the merged rows to node 2 and remove the divergence, so "run each T twice;
> same data" (B3h) would not hold; `NONE` installs `ReadOnlyReadRepair`, whose merge listener is a no-op (`ReadRepairStrategy.java`,
> `ReadOnlyReadRepair.java:47-50`); RFP's own first-phase listener is unaffected (`DataResolver.java:260-264`). (iii) Exact client
> (`harness/…/rfp-client.py`, the bundled driver, protocol 5, `WhiteListRoundRobinPolicy(['127.0.0.1'])`, `token_metadata_enabled=False`,
> heartbeat off, **`FallthroughRetryPolicy`** so an Overloaded error is not retried on another host): load `INSERT INTO rfp.t (k, c, v, pad)
> VALUES (0, ?, 'old', ?)` at ALL, pad = `os.urandom(512)`, in chunks of 20,000, 64 in flight; `nodetool -p 7299 drain`, stop node 2, wait
> until node 1 sees it DN; `UPDATE rfp.t SET v = 'new' WHERE k = 0 AND c = ?` for every c at ONE (chunks of 20,000); start node 2, wait
> until node 1 sees two UN. Query: `SELECT * FROM rfp.t WHERE v = 'old' ALLOW FILTERING`, `fetch_size=None`, timeout 120 s, CL ALL.
> Unbounded demand: 2N = 200,000 cached row versions, N = 100,000 of them non-null.

**B3d. Observables and instruments.** Node 1: (1) query outcome; (2) JMX
`org.apache.cassandra.metrics:type=Table,keyspace=rfp,scope=t,name=ReplicaFilteringProtectionRowsCachedPerQuery` (Max);
(3) live heap: `jcmd <pid1> GC.class_histogram` every 2 s during the query, recording
instances and bytes of `org.apache.cassandra.db.rows.BTreeRow` and `org.apache.cassandra.db.rows.BufferCell`
and `[B`/`java.nio.HeapByteBuffer`; (4) `jstat -gc <pid1> 500` for old-gen used (OU) peak;
(5) gc.log. Cannot be observed directly: the split between raw response buffers and RFP-cached
rows; infer from the BTreeRow live count.

> **Amendment C4 (2026-10-27, stage-4 audit; instruments that can see the quantity).** (2) The histogram is read over JMX after each query
> as `Count`, `Max` and **`RecentValues`** (bucket counts since the previous read, `CassandraMetricsRegistry.java:462-468`; read once before
> the query to reset). The per-query value is the offset of the highest non-empty `RecentValues` bucket (U4's offsets); `Max` is
> informational, because the decaying max forgets a sample after about 40 s (`DecayingEstimatedHistogramReservoir.java:537-549, 680`).
> **(2b) New, the main heap instrument: an observe-only Byteman probe on node 1** (`harness/…/rfp.btm` + `stage4/rfp/RfpProbe.java`,
> type-checked with `TestScript`). Rule A, `AT THROW` in `ReplicaFilteringProtection.incrementCachedRows` (the only throw, `:331`); rule B,
> `AT ENTRY` of `ReplicaFilteringProtection$QueryMergeListener.populate` (a partition fully consumed, `:396`, the peak of a successful query
> since nothing is released before it, `:564`); each writes one `PEAK` line: `currentRowsCached`, `maxRowsCached`, the threshold, the number
> of non-null rows held in all `PartitionBuilder.contents` (+ non-empty static rows) and their **bytes** = `ObjectSizes.measureDeep` of an
> array of those rows minus the array shell (`ColumnMetadata` and `TableMetadata` are `@Unmetered`, so the schema is not counted). Rule C,
> `AT ENTRY` of `DataResolver.resolveWithReplicaFilteringProtection`, writes one `RESP` line with `measureDeep` of each replica response
> payload (the raw responses of A4, held regardless of the cap). (3) The class-histogram sampler every 2 s stays, **informational only**: a
> failing query ends well within 2 s, so it cannot see the transient. (4) `jstat` cannot attach on this machine; dropped (the probe's bytes
> replace "OU rise"). (5) gc.log copied, informational.

**B3e. Procedure.** 1) start both nodes, load, diverge (B3c). 2) Record idle baseline of (3)/(4).
3) For each T: set T via JMX; start samplers (3)(4) in background; run the query; stop
samplers; record outcome and metric max; force `jcmd <pid1> GC.run` and wait 10 s between runs.
4) Shut down (B4).

> **Amendment C5 (2026-10-27, stage-4 audit; exact sequence).** 1) Start node 1, then node 2; load; diverge (C3). 2) `jcmd GC.run`,
> baseline class histogram. 3) For T = 1000, 10000, 32000, 1000000, **each twice in a row (r1, r2)**: set T and read it back; read the
> histogram (reset `RecentValues`); start the sampler; run the query; stop the sampler; read the histogram; keep the probe lines written
> since the query started; `jcmd GC.run`; wait 10 s. 4) The CL ONE run of B3h at T = 1000000 (C8). 5) Copy node logs, stop both nodes (B4/C1).

**B3f. Predictions.** T=1000: query fails fast (`OverloadedException`, client sees a read
failure/overloaded error) ; peak live BTreeRow above baseline <= ~1000; OU rise ~ size of the
raw node-2 response only. T=10000: fails; peak extra BTreeRow <= ~5000 (half the versions are
null); old-gen rise ~ raw response + ~20 MB. T=1000000: succeeds with 0 rows; metric max
200000; peak extra BTreeRow ~100000 and old-gen rise ~ raw response + ~400 MB. Relation:
peak cached-row heap rises with min(T/2, N) x row size.

> **Amendment C6 (2026-10-27, stage-4 audit; replaces the predictions above, which were sized for 4-KiB rows and read through instruments
> that cannot see the transient; derived from source before any reading).** Per merged row RFP adds one null version (node 1, silent) and one
> non-null version (node 2) (`:218-223`, `:477-492`), so after k merged rows `currentRowsCached` = 2k and k rows are held. For T ∈ {1000, 10000,
> 32000}: the query fails with an Overloaded error naming "cached over T rows"; exactly **one `PEAK` throw line with current = T+1 and
> non-null = T/2** (500, 5000, 16000; the row whose count trips the check is not added, `:479-492`), no populate line; `RecentValues` top
> bucket = bucket(T+1) = 1109, 11864, 35425. T = 1000000: success, 0 rows; exactly **one `PEAK` populate line with current = 2N = 200,000 and
> non-null = N = 100,000**; top bucket 219342. Bytes: **bytes = b × non-null with b the same in every run** (max/min ≤ 1.02; same row shape),
> so the cached bytes stand 500 : 5000 : 16000 : 100000; sub-prediction from source b ∈ [700, 1200] B (pad array 528 B plus row, clustering,
> liveness, two cells and three buffers). r1 and r2 agree exactly in current and non-null and within 1 % in bytes. `RESP` (2 responses) the
> same in every CL ALL run within 1 %, sub-prediction ∈ [N × 512, N × 700] B. One node-1 log line per failing query (6). Relation: RFP-held
> heap = b × min(T/2, N).

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| Extra live rows and OU rise track min(T/2,N); T<2N fails | claim confirmed at the resource level |
| T=1000 run shows the same heap peak as T=1000000 and the query does not fail | claim refuted |
| Fails at T but heap peak equally high for all T | count cap holds but heap is dominated by A4 consumers (raw responses); cap does not govern actual heap |
| Unbounded control shows no rise | workload not divergent / RFP not engaged; not confirmed |

> **Amendment C7 (2026-10-27, stage-4 audit; rows read with C4/C6 instruments, rows added before any reading).** Row 1 ("claim confirmed at the
> resource level") requires every C6 relation: the three T < 2N runs fail at current = T+1 holding T/2 rows, the control holds N rows at 2N,
> b constant, bytes ordered with T, repeats agree. Row 2 ("refuted"): any T < 2N run succeeds, or a `PEAK` line shows current > T+1, or the
> bytes at a T < 2N reach the control's. Row 3 ("cap holds but heap dominated by A4"): row 1's count relations hold but `RESP` + bytes at the
> smallest T is within 10 % of `RESP` + bytes of the control. Row 4 ("not confirmed"): the control's populate line is missing or holds
> ≠ N rows. Added: (a) a query fails with another error (timeout, unavailable) — invalid run for that T; (b) a `PEAK-ERROR`/`RESP-ERROR` line
> or a missing `PEAK` line — Not confirmed (instrument); (c) r1 and r2 disagree — Not confirmed; (d) a threshold read-back differs — invalid run.

**B3h. Controls.** The T=1000000 run is the positive control that the workload moves heap.
Repeat the same query at CL ONE (no RFP, `DataResolver.java:122`) to measure the raw-response
baseline. Run each T twice; same JVM, same data.

> **Amendment C8 (2026-10-27, stage-4 audit; the CL ONE control's premise does not hold in source).** `DataResolver.resolve` takes the RFP
> path whenever the row filter is non-empty (`DataResolver.java:122-144`; no consistency-level test), and a range read always resolves through a
> `DataResolver` (`RangeCommandIterator.java:198-203`), so at CL ONE RFP still runs with one source and counts the serving replica's rows. The
> CL ONE query is run once at T = 1000000 after the main runs as an **informational** control, with two source-derived outcomes: node 1 serves
> (0 rows, no `PEAK` line) or node 2 serves (100,000 stale rows returned, one populate line with current = non-null = 100,000). It is not a
> raw-response baseline; `RESP` (C4) is.

**B4. Risks and cleanup.** Data ~1 GB per node on local disk only; delete `/local/c509-*`
after. Stop with `nodetool -p 7199 stopdaemon` / `-p 7299`, then `pgrep -f CassandraDaemon`
must return nothing; kill the jstat/jcmd samplers. The in-JVM dtest closes its cluster in
`@AfterClass`; check `pgrep -f RfpCapProbeTest` afterwards. Nothing written to the shared clone.

## C. Sources read

- src/java/org/apache/cassandra/service/reads/ReplicaFilteringProtection.java
- src/java/org/apache/cassandra/service/reads/DataResolver.java
- src/java/org/apache/cassandra/config/ReplicaFilteringProtectionOptions.java
- src/java/org/apache/cassandra/config/Config.java (line 537)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (2852-2869)
- src/java/org/apache/cassandra/service/StorageService.java (6733-6752), StorageServiceMBean.java (990-999)
- src/java/org/apache/cassandra/metrics/TableMetrics.java (354-356, 837)
- conf/cassandra.yaml (1815-1837)
- test/distributed/org/apache/cassandra/distributed/test/ReplicaFilteringProtectionTest.java
- build.xml (test-jvm-dtest-some target)
- https://issues.apache.org/jira/browse/CASSANDRA-15907, CASSANDRA-19018 (cited from the class javadoc, not opened)

## D. Stage-4 feedback

**2026-10-27, advisor-run stage 4 (Claude Opus 5.5, on the advisor's Mac), run 1 at sha256 `3fe55d66…7a9a`:**
unit **Confirmed (B2g row 1, U5) — caps**; cluster **Confirmed (B3g row 1, C7) — caps**. Results:
[`stage4-runtime-verification/results/cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous.md`](../../stage4-runtime-verification/results/cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous.md).
Unit: with 20,000 divergent rows the query fails with `OverloadedException` at T = 1000 / 10000 / 32000 (default), peak in the histogram
bucket of T+1; at T = 100000 it completes (peak bucket of 40,000). Cluster: RFP holds exactly T/2 rows (500 / 5,000 / 16,000; 0.40 / 4.0 /
12.8 MB at 800 B per row) and fails at count T+1; with the threshold not binding it holds 100,000 rows (80.0 MB) at count 200,000. The raw
replica responses (53 MB) are outside the cap, as A4 says. Amendments before run 1: U1–U5, C1–C8 (default added; histogram-bucket units;
pad 512 B because a 4-KiB-row response exceeds the 128 MiB internode limit; `read_repair = 'NONE'`; Byteman probe of held rows and bytes;
CL ONE premise corrected) and runbook fix D1. For stage 3: neither tier exercises the entry-pointer branch `:430` (both run range reads,
`consumeEntirePartitions` = true); a single-partition `LIMIT` arm would. Commits: none yet (uncommitted on `advisor-run`, after `561e1ac`).
