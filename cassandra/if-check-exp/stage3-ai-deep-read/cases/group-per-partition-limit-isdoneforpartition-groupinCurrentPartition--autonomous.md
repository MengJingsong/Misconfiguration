<!-- file: cases/group-per-partition-limit-isdoneforpartition-groupinCurrentPartition--autonomous.md -->
# GROUP BY per-partition group limit (groupPerPartitionLimit) — verification solution

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/filter/DataLimits.java:1007` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code, 2026-10-27 |
| Estimate | `negative`: the compared limit is a per-query CQL value (`PER PARTITION LIMIT` on a `GROUP BY` select), not a node-level setting, and it bounds the number of groups returned per partition, not a memory or disk object on the node. |
| Ground | The limit is supplied by each client query and defaults to `NO_LIMIT` (`Integer.MAX_VALUE`). It does not bound heap or disk: memory per read is governed by paging (page size), `max_value_size`/tombstone thresholds and the read path. It is a result-shaping limit that only stops the iteration early for the current partition. |

## A. Constraint trace

**A1. The constraint.** `CQLGroupByLimits.groupPerPartitionLimit` (`DataLimits.java:663`), a final int set in the constructor (`:674-681`). Kind: runtime query parameter, not a yaml key, `-D` property, or JMX setting. It comes from the CQL `PER PARTITION LIMIT n` clause on a `SELECT ... GROUP BY` (`SelectStatement.java:130,944,1274`; `DataLimits.groupByLimits` factory at `DataLimits.java:117-121`). Unit: groups (not bytes). Default: `DataLimits.NO_LIMIT = Integer.MAX_VALUE` (`DataLimits.java:48`) when the clause is absent. Set per query; no restart.

**A2. What it caps.** Number of GROUP BY groups emitted from a single partition. The compared quantity at line 1007 is `groupInCurrentPartition` (`:842`, a counter; amended 2026-10-27, was `:839-840`) against `groupPerPartitionLimit`. The resource is nominally none: it is a result-cardinality limit. Indirect effect: once reached, the counter stops reading the rest of that partition (`stopInPartition()`), which saves read work.

**A3. Mechanism.**
- `applyToRow` (`:926`) calls `groupMaker.isNewGroup`; when a group closes, `incrementGroupCount()` and `incrementGroupInCurrentPartitionCount()` run (`:933-937`, `:990-1002`).
- `incrementGroupInCurrentPartitionCount` increments `groupInCurrentPartition` and calls `stopInPartition()` when it reaches the limit (`:999-1001`).
- `isDoneForPartition()` (`:1005-1008`), the target, returns true if the global group limit is reached (`isDone()`, `:1013`) or `groupInCurrentPartition >= groupPerPartitionLimit`. It is checked in `applyToRow` (`:943`): a row is dropped (`return null`) and `hasUnfinishedGroup` cleared.
- The paging subclass presets `groupInCurrentPartition = groupPerPartitionLimit - lastReturnedKeyRemaining` when resuming (`:1126`).
- Bypass/overshoot: rows of the last group in a partition are still read until the group boundary is detected; rows already read inside an open group are held by the aggregation. The limit is not enforced on bytes, and with default `NO_LIMIT` it never fires.

**A4. Other consumers.** Heap used by the read path (memtable and sstable iterators, row/cell buffers, merge iterators), the aggregation state of `GroupMaker`, paged result buffers (`SelectStatement` page size), and the coordinator's response accumulation; all outside this limit's control.

**A5. Evidence beyond the source.** CQL docs for `PER PARTITION LIMIT` and `GROUP BY`: https://cassandra.apache.org/doc/latest/cassandra/developing/cql/dml.html#select-statement (cited for semantics only). Otherwise none.

## B. Verification solution

**B1. Claim under test.** Heap and disk use of a node do not follow `groupPerPartitionLimit`: changing `PER PARTITION LIMIT` over a wide range changes the number of returned groups exactly, but peak read-path heap (with paging fixed) stays within noise unless the limit cuts the partition's read short, and it never behaves as a bound on node memory or disk.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a ~/cassandra-5.0.9/ /tmp/c509-unit/`), `ant jar` there; write a small JUnit/main class in a separate directory (e.g. `/tmp/unit-src`) on the classpath `/tmp/c509-unit/build/classes/main:/tmp/c509-unit/lib/*`. Run with `-Xmx512m -XX:+UseSerialGC` so allocation counts are stable.

**Amendment 2026-10-27 (audit, B2a/B2e).** The unit test is a `CQLTester` test run by `ant testsome` in a copy of the tree (the alternative named above), so one JVM runs all N: `System.gc()` three times and a forced heap reading before each measurement, 5 repetitions per N, median taken. This replaces "fresh JVM per N" in B2e; retained heap after GC does not depend on JVM age. The test reads one partition of R=100000 rows from the memtable, with `AggregationSpecification.aggregatePkPrefixFactory(comparator, 1)` (groups by `(k, ck)`, one group per row). The row source is wrapped in a counting `Transformation` applied before the limit counter, so "rows pulled" is the number of rows the counter's iterator requested from the source. Alternative: a test in `test/unit/org/apache/cassandra/db/filter/` run by `ant testsome -Dtest.name=<Class>` in the copy.

**B2b. Knobs.** `groupPerPartitionLimit` in {1, 10, 100, 1000, NO_LIMIT} via `DataLimits.groupByLimits(groupLimit=NO_LIMIT, groupPerPartitionLimit=N, rowLimit=NO_LIMIT, spec)`; secondary knob: total rows per partition R = 100000 with group size 1 row (so groups = R).

**B2c. Workload.** Build a synthetic `UnfilteredRowIterator` (or `RowIterators`/`UnfilteredPartitionIterators` over a memtable partition) with one partition, R=100000 clustering rows of fixed size; run it through `limits.newCounter(nowInSec, false, false, true)` applied via `Transformation.apply`. With N=1000 the counter stops after 1000 groups, well below R, so the limit is reached and passed.

**B2d. Observables and instruments.** `counter.countedInCurrentPartition()`, `counter.counted()`, rows consumed from the source (wrapper counting `next()`), bytes allocated by the thread (`com.sun.management.ThreadMXBean.getThreadAllocatedBytes`), retained heap after forced GC (`Runtime.totalMemory()-freeMemory()` after `System.gc()`). Cannot observe true node resource use at this tier.

**B2e. Procedure.** For each N: fresh JVM, build the iterator, record allocated bytes before, run the transformation draining the iterator, record rows pulled, groups returned, allocated bytes after, and post-GC retained heap. Repeat 5 times, take the median.

**B2f. Predictions.** Groups returned = min(N, R) exactly (N=1: 1, 10: 10, ..., 1000: 1000, NO_LIMIT: 100000). Rows pulled from the source about N plus a small constant (limit stops at the group boundary). Retained heap after GC: flat across N (within 5%) because nothing is retained once the iterator is drained. Allocated bytes grow roughly linearly with rows pulled (work, not retained memory).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Groups returned = min(N,R); retained heap flat across N; allocated bytes scale with rows pulled | claim confirmed: mechanism works as traced, but caps only result cardinality and read work, not retained memory |
| Retained heap after GC grows or shrinks with N beyond noise | claim refuted: the limit bounds a memory-significant object |
| Groups returned != min(N,R) | trace of A3 wrong |
| Rows pulled does not drop at small N (counter never stops early) | limit never reached; not confirmed |
| Positive control (see B2h) does not move retained heap | not confirmed |

**B2h. Controls.** Positive control: a materializing consumer (collect all returned rows into a list) shows retained heap rising linearly with N, which proves the harness can detect a cap that binds the retained size. Control with `NO_LIMIT` for baseline. Same iterator, same JVM flags for all runs.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, built from a local copy (`/tmp/c509-node`, `ant jar`), data/commitlog/hints under `/tmp/c509-data` on local disk (>= 5 GB free). `cassandra-env`/`jvm11-server.options`: `-Xms1g -Xmx1g`, G1. `cassandra.yaml` untouched except directories and `listen_address=127.0.0.1`.

**B3b. Knobs.** `PER PARTITION LIMIT` N in {1, 100, 10000, absent} on `SELECT k, ck, count(*) ... GROUP BY k, ck`; fixed driver page size 1000 (`cqlsh PAGING 1000`). Secondary: yaml `aggregation_subpage_size_in_kb` (default 2048, per the 5.0 config) at its default and at 64, as a positive control for a limit that does bind internal memory (`DatabaseDescriptor`).

**Amendment 2026-10-27 (audit, group D).** `aggregation_subpage_size_in_kb` does not exist in 5.0.9: `grep -rni subpage src/java conf` finds no yaml key, `Config` field or `DatabaseDescriptor` getter (checked against `cassandra-5.0.9`). The secondary knob is replaced by the **driver page size P**, which is a known-binding cap on the same resource: for a GROUP BY select, `SelectStatement.getDataLimits` passes the page size as the row limit of `DataLimits.groupByLimits` (`SelectStatement.java:899-911`), so one internal page holds at most P groups. Positive control: N absent at P=1000 against N absent at P=300000 (rows per page rise 300-fold; the replica response and the coordinator's rows for a page are held on heap). Exploratory arms, not part of B3f/B3g: P=300000 with N in {1, 100, 10000}, to record whether the limit shapes a large page. Heap instruments are named under B3d below.

**B3c. Workload.** Table `ks.t(k int, ck int, v blob, PRIMARY KEY(k, ck))`, 10 partitions x 200000 rows, 100-byte blobs (about 2 GB raw before compression; reduce to 50000 rows if disk is tight). Query each partition with every N. 20000 rows/partition at N=100 shows the limit is hit well before the end.

**Amendment 2026-10-27 (audit, group D).** The size is 10 x 200000 = 2,000,000 rows x 100 B = about 200 MB of values (not 2 GB; about 300 MB on disk with keys, compression off), so the 50000-row reduction is not needed. N=1, 100 and 10000 are all below the 200000 rows of a partition (one group per row), so the limit is reached and passed for every finite N. Data goes on a tmpfs (`/dev/shm`) per the shared-node rules, not `/tmp/c509-data`.

**B3d. Observables and instruments.** (Amendment 2026-10-27: heap is read by a JMX sampler every 100 ms, recording `HeapMemoryUsage.used`, the sum of the G1 pools' `CollectionUsage.used` (live heap as of the last collection) and the summed `getThreadAllocatedBytes` of all live threads; `jcmd GC.run` before each arm. The peak live proxy of an arm is the maximum of the pools' collection usage in the arm's window minus the same quantity after the pre-arm GC; the gap is named: a sampled proxy, not the exact per-query retained heap.) JVM heap via `jcmd <pid> GC.heap_info` and `nodetool gcstats`, sampled every 1 s during the query; peak G1 used heap from GC logs (`-Xlog:gc*`); disk via `du -s /tmp/c509-data`; rows returned by the client; `nodetool tablestats` read latency. Cannot observe per-query retained heap exactly; peak-minus-baseline is an approximation.

**B3e. Procedure.** Start the node; create schema; load data with `cassandra-stress` or a CQL script; `nodetool flush`; record baseline heap/disk. For each N, run each query 10 times from cqlsh/driver, sampling heap at 1 s; record peak and group count. Repeat for the `aggregation_subpage_size_in_kb` positive control (restart per value). Stop the node with `nodetool drain` then kill; confirm no `CassandraDaemon` process remains (`pgrep -f CassandraDaemon`).

**B3f. Predictions.** Rows returned = N groups per partition. Peak heap delta between N=1 and N=absent is within a few percent / tens of MB, because paging bounds per-page memory; disk unchanged (reads only). Positive control: changing `aggregation_subpage_size_in_kb` moves peak aggregation memory measurably more than N does. **Amended 2026-10-27:** raising the page size P from 1000 to 300000 (N absent) moves the peak live proxy by more than 30 MB and by more than three times the run-to-run spread, while N=1 against N=absent at P=1000 stays within 30 MB; the 30 MB is the "tens of MB" above, fixed before any reading.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Groups = N per partition; peak heap flat across N; disk flat; control moves | claim confirmed: limit is not a memory/disk cap |
| Peak heap tracks N monotonically beyond run-to-run variance | claim refuted |
| Counts differ from N | A3 trace wrong |
| N never smaller than partition size or control did not move | not confirmed |

**B3h. Controls.** Same data and same restarts for each N; discard first run (warm-up); fixed page size; compare against the page-size control (amended 2026-10-27, was `aggregation_subpage_size_in_kb`); the primary sweep runs forward (N=1, 100, 10000, absent) and then reversed within one node lifetime, so order effects show; run an unrelated query to measure heap noise.

**B4. Risks and cleanup.** Data stays under `/tmp/c509-data` on local disk (about 2-3 GB); build in the local copy only, never in the shared tree. After runs: kill the node, `pgrep -f 'CassandraDaemon|java.*c509'` must be empty, then `rm -rf /tmp/c509-unit /tmp/c509-node /tmp/c509-data`.

## C. Sources read

- ~/writeup-A/playbook-autonomous.md
- ~/writeup-A/_TEMPLATE-autonomous.md
- ~/cassandra-5.0.9/src/java/org/apache/cassandra/db/filter/DataLimits.java (lines 640-1130; grep of NO_LIMIT and groupPerPartitionLimit)
- ~/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java (grep of perPartitionLimit)
- https://cassandra.apache.org/doc/latest/cassandra/developing/cql/dml.html (semantics only)

## D. Stage-4 feedback

Stage 4, 2026-10-27 (results: `stage4-runtime-verification/results/group-per-partition-limit-isdoneforpartition-groupinCurrentPartition--autonomous.md`).

- **Verdict.** Unit tier **Confirmed** (B2g row 1) — does not cap: groups = min(N,R) exactly, rows pulled N+1, retained heap flat within 0.08 %, a cloning consumer moves retained heap 39.6 MB. Cluster tier **Not confirmed (no matching row)**: 1200 queries returned exactly N groups, disk unchanged, the page-size control moved the peak heap by 737 MB, but at N=absent the sampled peak was 54-55 MB against 8 MB at N=1 (frozen rule 30 MB) and the forward sweep was not strictly monotone. Outcome class: undetermined.
- **Amendments made at the audit (all dated 2026-10-27, before any reading):** A3 line cite `:842`; B2a (one JVM, `ant testsome`); B3b (`aggregation_subpage_size_in_kb` does not exist in 5.0.9, replaced by a page-size control, `SelectStatement.java:899-911`); B3c (2 M rows x 100 B is 200 MB, not 2 GB); B3d (heap instrument); B3f (30 MB threshold); B3h.
- **For stage 3.** (1) The case's estimate reasoning treats the page size as background; for a GROUP BY select the page size is itself a row limit of the same `DataLimits` (`SelectStatement.java:899-911`), and exploratory arms at page size 300000 show the peak heap following the page content (8 / 23 / 792 MB for N = 1 / 10000 / absent), so the limit shapes the result size of a large page. B3g has no row for this outcome. (2) A heap statistic for a long arm needs a drift correction: with Cassandra's G1 settings the post-collection floor rose 0 -> 40 MB over a 375 s arm (`diag-drift.txt`), which is what missed the 30 MB rule; the first 157 samples of that arm peak at 14.8 MB, equal to the 10000-group arm.
