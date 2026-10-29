# MAX_UNSIGNED_SHORT — verification solution  <!-- file: cases/max_unsigned_short-validateindexedvalue-value_remaining--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`CassandraIndex.java:618`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/internal/CassandraIndex.java#L618) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: the constant bounds the size of one indexed value (a format limit, below 64 KiB), not the number of indexed values or the total bytes of the index table, so memory and disk used by a secondary index are not capped by it. |
| Ground | The check at line 618 is applied per value, per write, in `validateIndexedValue` ([`CassandraIndex.java:616-627`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/internal/CassandraIndex.java#L616-L627)). Nothing sums values across rows or partitions, so any number of values just under the limit is accepted and each becomes a partition key of the hidden index table. The index table's total size grows with row count without bound from this constant. |

> **Link rule.** Followed: A1 declaration and the if statement (A3 and Entry pointer) are permalinks at `cassandra-5.0.9`.

## A. Constraint trace

**A1. The constraint.** `FBUtilities.MAX_UNSIGNED_SHORT`; kind: hard-coded constant (not a yaml entry, JVM property, JMX attribute or runtime-queried limit). Declared at [`FBUtilities.java:158`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/FBUtilities.java#L158) as `public static final int MAX_UNSIGNED_SHORT = 0xFFFF;` (verified). Unit: bytes when used as a length limit (it is also used as a count limit elsewhere, e.g. `QueryProcessor.java:758` bound markers). Value 65535, a literal with no derivation. Not settable by yaml, `-D` or JMX; changing it needs a source edit and rebuild. The earlier trace was checked: the declaration line and the `>=` comparison are correct, so the effective largest accepted indexed value is 65534 bytes (`remaining() >= 65535` is rejected). The earlier trace cited `Validation.java:51`; the file is `src/java/org/apache/cassandra/cql3/Validation.java:51` (not `db/`), where the same constant bounds a partition key length. Line numbers `QueryProcessor.java:259` and `ClusteringPrefix.java:278` check out.

**A2. What it caps.** Not a memory or disk budget. The quantity compared is `value.remaining()` of one indexed value (the bytes of the indexed column's value, or for a primary-key index the partition key or clustering value) at write validation. It caps the size of the key of one row in the hidden index table, a serialization-format limit (a 2-byte length prefix).

**A3. Mechanism.**
1. A write goes through `SingleTableUpdatesCollector`, which calls `mutation.validateIndexedColumns(state)` at `cql3/statements/SingleTableUpdatesCollector.java:111`.
2. `PartitionUpdate.validateIndexedColumns` calls `IndexRegistry.obtain(metadata()).validate(this, state)` (`db/partitions/PartitionUpdate.java:546-549`), which dispatches to each index (`index/SecondaryIndexManager.java:1345-1349`).
3. `CassandraIndex.validate(PartitionUpdate, ClientState)` (`CassandraIndex.java:320-338`) switches on the indexed column kind and calls `validatePartitionKey` (:580-584), `validateClusterings` (:586-591) or `validateRows` (:593-613), each of which calls `validateIndexedValue`.
4. The check: [`if (value != null && value.remaining() >= FBUtilities.MAX_UNSIGNED_SHORT)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/internal/CassandraIndex.java#L618) throws `InvalidRequestException` ("Cannot index value of size %d ...", lines 619-625). Otherwise nothing happens and the write proceeds.
Outcomes: at or above the limit the whole write is rejected before apply (`mutation.validateSize` follows at `SingleTableUpdatesCollector.java:112`); below it the write is accepted with no accounting.
Related read-side check: `CassandraIndex.validate(ReadCommand)` rejects an index expression value over the limit (`CassandraIndex.java:225`, note `>` there versus `>=` at 618).
Bypasses: the check runs only on the client write path. Index builds on existing data, streaming, hints and sstable import do not go through `validateIndexedColumns` (I traced the callers I found by grep: only `IMutation.java:45`, `VirtualMutation.java:117`, `SingleTableUpdatesCollector.java:111`; other paths not verified). Also, `getIndexedValue` for keys/entries collection indexes builds a composite value (not verified in detail), so the checked size is that of the built indexed value.


The check itself is the if statement at [`CassandraIndex.java:618`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/internal/CassandraIndex.java#L618).

**A4. Other consumers.** The index table is an ordinary table: its memtable (heap or off-heap per `memtable_allocation_type`), commit log segments, sstables and caches are governed by `memtable_heap_space`, `memtable_offheap_space`, `commitlog_total_space`, compaction and disk space, none of which this constant touches. The base table also holds the same value, bounded only by mutation size (`mutation.validateSize`, `SingleTableUpdatesCollector.java:112`). The same constant also limits partition keys (`cql3/Validation.java:51`), clustering (`db/ClusteringPrefix.java:278`), marker count (`cql3/QueryProcessor.java:758`), cache keys (`service/CacheService.java:504`).

**A5. Evidence beyond the source.** none. (Cassandra docs describe a 64 KB limit on indexed values / keys; not looked up, not verified.)

## B. Verification solution

**B1. Claim under test.** Claim (negative): indexed-value validation caps only the size of a single value; the memory and disk used by the secondary index keep growing with the number of rows whose values are just under 65534 bytes, so usage does not follow `MAX_UNSIGNED_SHORT`. Sub-claim (mechanism): values of 65534 bytes are accepted and 65535 bytes are rejected.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`cp -r /users/jason92/cassandra-5.0.9 $WORK/c509`), never build in the shared tree. `cd $WORK/c509 && ant jar` then add a JUnit test `test/unit/org/apache/cassandra/index/internal/IndexedValueLimitTest.java` extending `CQLTester`. Run: `ant testsome -Dtest.name=org.apache.cassandra.index.internal.IndexedValueLimitTest`. JVM options as in `build.xml` defaults, plus `-Xmx2g` via `-Dtest.jvm.args` (not verified whether that property name is honored in this build.xml).

**B2b. Knobs.** The constant cannot be set. Varied instead: (a) value size S in bytes: 1000, 65533, 65534, 65535, 65536; (b) number of rows N: 100, 1000, 4000 at S=65534. Index on a `text` regular column with ASCII content (1 byte per char), and a second table with the index on the partition key `blob`.

**B2c. Workload.** `CREATE TABLE t(k int PRIMARY KEY, v text); CREATE INDEX ON t(v);` then `INSERT` rows with distinct values of size S (distinct so each is its own index partition). Sum of indexed bytes = N x S, e.g. 4000 x 65534 = about 262 MB of index keys, far above the single-value limit, which shows the limit is not an aggregate.

**B2d. Observables and instruments.** (1) Accept or reject, and exception message. (2) After `flush` of base and index tables, the index table's on-disk size via `ColumnFamilyStore.metric.liveDiskSpaceUsed` of `getIndexManager().getIndexByName(...)`'s backing CFS (access via `CassandraIndex.getBackingTable()`; not verified exact accessor). (3) Index memtable `getMemtable().getLiveDataSize()` before flush (not verified exact method name). Not directly observable: heap retained by the index table in a unit JVM beyond these metrics.

**B2e. Procedure.**
1. Build, create the test class with one method per knob row.
2. For S in the list, insert one row; assert accept for S <= 65534 and `InvalidRequestException` containing "Cannot index value of size" for S >= 65535.
3. For N in {100, 1000, 4000} at S=65534, insert N rows, record index live data size, flush, record index on-disk size.
4. Positive control (below): repeat step 3 with the same workload on a table in which a known cap binds.
5. Remove `$WORK`.

**B2f. Predictions.** S=65534 accepted; S=65535 rejected (message shows size 65535, max 65535); S=65536 rejected. Index table size at S=65534 grows about linearly in N (ratio of size at N=4000 to N=1000 near 4, the index key bytes dominate); it reaches well above 65535 bytes in total. Claim is wrong if the index size stops growing or writes start being rejected at some N with S fixed at 65534.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Index size grows with N, no rejection at S=65534 | Claim confirmed: not an aggregate cap |
| Rejection at S=65534 or acceptance at 65535 | Boundary analysis wrong (check `>=` at line 618) |
| Index size plateaus below N x S while writes succeed | Another mechanism bounds it; claim refuted for this path (investigate) |
| Index size flat while the positive control moves | Claim confirmed |
| Control table does not move, or N too small to flush | Not confirmed |

**B2h. Controls.** Positive control: the same insert loop on a table with a per-value cap that binds on aggregate, here a memtable limit: set `memtable_heap_space` small (e.g. 64 MiB) through the test's DatabaseDescriptor and observe that memtable live size stays bounded because flushes trigger (expected from `memtable_heap_space` semantics; not verified in source for this case). Also a control with the index absent (same inserts) to separate base-table from index-table growth.

### B2i. Audit amendments, unit tier (stage 4, 2026-10-28)

These apply to B2a-B2h; the prediction (B2f) and the readings table (B2g) are not changed, only given numbers where B2f says "about" or "near".

1. **Launcher and paths.** Copy by `copy-source.sh` to local disk (`~/s4-b2/c`), `ant build-test`. The test class is compiled outside the tree (`javac -d`) and run in a separate JVM per arm through `org.junit.runner.JUnitCore` with the build classpath and the module flags of `conf/jvm11-server.options`; heap `-Xmx4g`. The unit yaml is the tree's `test/conf/cassandra.yaml` with directories moved to local disk and `memtable_heap_space` set per arm (2048 MiB "default" arm, 64 MiB control arm). The `ant testsome` heap (4G, set last) is the same size; the launcher is used so that the yaml and the arms are explicit.
2. **Second path.** A single-column partition key cannot carry a secondary index, and a composite partition key is rejected by the key-length check before the index check can see a value of 65535 bytes, so "a second table with the index on the partition key `blob`" cannot show the boundary. Replaced by a table `(k int, c blob, v int, PRIMARY KEY (k, c))` with the index on the clustering column `c`: `ClusteringPrefix.validate` (`ClusteringPrefix.java:278`) rejects only `size > 65535`, so a clustering value of 65535 bytes reaches `validateClusterings` (`CassandraIndex.java:586-591`) and the check at line 618. The partition-key path is probed once and reported as information, not as an EXPECTED line. Control: the same 65535-byte value into the same tables **without** the index is accepted (so the rejection comes from line 618, not from another validator).
3. **Instruments (B2d, accessors checked in source).** Index backing table: `getCurrentColumnFamilyStore().indexManager.getIndexByName(<name>)` cast to `CassandraIndex`, `getBackingTable()` (`CassandraIndex.java:181`). Memtable size: `Memtable.getLiveDataSize()` (`SkipListMemtable.java:363`) does not count partition keys, which is where the index table keeps the value; the pool-accounted size `((AbstractAllocatorMemtable) memtable).getAllocator().onHeap().owns()` (`AbstractAllocatorMemtable.java:125, 190`) does, so `owns()` (bytes) is the memtable reading, sampled after every insert to give a peak; `getLiveDataSize` is recorded as information. Disk: `metric.liveDiskSpaceUsed` of the backing table after an explicit flush (all components, so about twice the key bytes: the key is in Data.db and Index.db). Heap after `System.gc()` is recorded as information. Unit yaml has `memtable_allocation_type: heap_buffers`, so memtable bytes are on-heap.
4. **Numbers for B2f** (stated before any run; N rows, S = 65534, distinct random base64 ASCII text so LZ4 does not shrink it; a fresh table per N): index backing-table disk bytes after flush lie between 0.9 x N x S and 2.2 x N x S; the ratio of that size at N = 4000 to N = 1000 lies in [3.5, 4.5] and at N = 1000 to N = 100 in [8, 12]; peak index memtable `owns()` at N = 4000 is at least 0.9 x N x S (about 236 MB) in the 2048 MiB arm. No insert at S = 65534 is rejected at any N. The base table of the indexed table has disk bytes within 5 percent of the unindexed table at the same N and S, and the index adds at least 0.9 x N x S on top.
5. **Control (B2h) made exact.** Same workload, `memtable_heap_space: 64MiB`: at least one memtable flush happens before the explicit flush (the index table has at least one sstable then) and the peak of base plus index `owns()` stays at or below 160 MiB (2.5 x the pool), while the 2048 MiB arm's peak at N = 4000 exceeds twice that (so the cap that binds is the pool, and the workload is large enough to reach it); total index bytes (memtable plus sstables) at N = 4000 in the 64 MiB arm still lie in the band of item 4.
6. **Boundary lines (EXPECTED).** Regular text column: S = 1000, 65533, 65534 accepted; 65535 and 65536 rejected with a message starting "Cannot index value of size S for index" and ending "(maximum allowed size=65535)". Clustering blob column: 65535 rejected with the same message; accepted without the index.
7. **Bookkeeping.** The sizes S are in bytes; for ASCII text 1 char = 1 byte. `-Xmx4g`; the largest arm holds about 2 x 262 MB on the heap. Stop condition: if the boundary arm fails (item 6), stop (B2g row 2) before the scale arms.

### B3. Cluster tier

**B3a. Environment and build.** One node (second optional), JDK 11, built from a local copy (`ant jar`), run with `bin/cassandra -f` from the copy. Data, commit log, hints and saved caches on a local disk of known size (e.g. a 20 GB scratch directory) via `-Dcassandra.storagedir=$WORK/data` and yaml directories; `MAX_HEAP_SIZE=2G`, `HEAP_NEWSIZE=400M`, `memtable_allocation_type: offheap_objects` for part 2.

**B3b. Knobs.** The constant cannot be set. Vary: value size S in {65534, 65535} and row count N in {1000, 4000, 16000}; `memtable_offheap_space` default versus 256 MiB for the control.

**B3c. Workload.** Via cqlsh/driver (Python script, one connection): `CREATE KEYSPACE ks WITH replication={'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE ks.t(k int PRIMARY KEY, v text); CREATE INDEX ON ks.t(v);` Insert N rows with distinct ASCII values of S bytes. At S=65534 and N=16000, index key data is about 1.05 GB; free disk must exceed 3 GB for base + index + commit log (fits the 20 GB scratch). Duration: minutes at a modest rate. Note a mutation is also bounded by commit log segment size (`mutation.validateSize`, `SingleTableUpdatesCollector.java:112`), so one row per statement.

**B3d. Observables and instruments.** `nodetool tablestats ks.t` and the index table (`ks.t.t_v_idx`) for "Space used (live)" and memtable data size; `du -sh $WORK/data/data/ks/*`; heap/off-heap via `nodetool info` and `jcmd <pid> GC.heap_info`; error text returned to the client. Sample after the workload, after `nodetool flush`, every 30 s during load. Not observable: the exact per-value memory inside the memtable beyond the reported data size.

**B3e. Procedure.**
1. Copy tree, `ant jar`, configure local dirs, start node, wait for "Starting listening for CQL clients".
2. Create schema. Insert one row at S=65535: expect rejection. Insert at S=65534: expect success.
3. Load N=1000, flush, record sizes; N=4000; N=16000, each time record index table and `du` size.
4. Control run: repeat load with the base table only (drop index) and with the positive control `memtable_offheap_space: 256MiB` to see memtable growth bounded by flushing.
5. `nodetool drain`, stop the node, `rm -rf $WORK`, check with `pgrep -f CassandraDaemon`.

**B3f. Predictions.** Rejection at 65535, acceptance at 65534. Index table live space grows about linearly with N (on the order of N x 65 KB before compression; compression may reduce for repetitive content, so use random ASCII so it compresses little). No N triggers a rejection from this constant. Claim wrong if the index table size stops growing or writes fail by this constant at some N.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Index table space grows with N, writes succeed at 65534 | Claim confirmed (negative) |
| 65534 rejected or 65535 accepted | Boundary assumption wrong |
| Index space saturates while writes succeed | Another bound acts; refutes claim for this path |
| Index space flat while memtable-limit control shows bounded memtable | Claim confirmed |
| Control memtable does not move or load too small to reach flushing | Not confirmed |

**B3h. Controls.** No-index run (isolates index cost); random versus repeated content (compression); positive control with the small `memtable_offheap_space` (a known cap) driven by the same workload; same S with values of 100 bytes and N x (65534/100) rows to show cost depends on bytes written rather than the per-value limit.

### B3i. Audit amendments, cluster tier (stage 4, 2026-10-28)

1. **Node.** Local copy `~/s4-b2/c` (`ant build-test`, which builds what the node needs); data, commit log, hints, saved caches and logs on tmpfs `/dev/shm/s4-b2/node` (so "disk bytes" are tmpfs bytes; `/local/...` and a 20 GB scratch directory do not exist on the node; the node has 251 GiB RAM); one node, address 127.0.2.1, JMX 7270; `MAX_HEAP_SIZE=2G`, `memtable_allocation_type: offheap_objects`, `memtable_cleanup_threshold: 0.99`, `auto_snapshot: false`, `commitlog_total_space: 1GiB`. Memtable pools: life 1 `memtable_offheap_space: 512MiB` (the computed default for a 2G heap), life 2 `memtable_offheap_space: 256MiB` (the B3h control); heap pool left at its default.
2. **Workload driver.** The build's bundled Python driver (protocol 4, 32 requests in flight), one INSERT per row (B3c). Values: seeded random base64 ASCII, 8-digit counter prefix so every value is distinct. A fresh table (and index named `idx_<table>`) per arm, dropped after the arm.
3. **Arms (B3b sized).** Life 1 (512 MiB): boundary precheck (5 inserts at S = 65534 accepted, 5 at S = 65535 rejected; else stop, B3g row 2); then S = 65534 at N = 1000, 4000, 16000; S = 65535 at N = 200 (all rejected); no-index control S = 65534 at N = 4000; small-value control S = 100 at N = 655,340 (the same key bytes as N = 1000 x 65534, B3h). Life 2 (256 MiB): S = 65534 at N = 16000.
4. **Observables.** Per arm: accept and reject counts and messages; `*-Data.db` plus `*-Index.db` bytes of the index backing table (directory `.idx_<table>` inside the table directory) and of the base table after `nodetool flush`; `nodetool tablestats ks.<table>.idx_<table>` "Space used (live)"; `Enqueuing flush ... Reason: MEMTABLE_LIMIT, Usage: ...` lines of `system.log` (logged on/off-heap usage); RssAnon of the daemon sampled every 2 s.
5. **Numbers for B3f.** S = 65534: no insert rejected at any N; index Data+Index bytes lie in [0.9, 2.2] x N x S; the ratio N = 16000 to N = 4000 lies in [3.5, 4.5] and N = 4000 to N = 1000 in [3.5, 4.5]; the 16000-row arm (1.05 GB of index keys) at 512 MiB logs at least one MEMTABLE_LIMIT flush with logged off-heap usage at most 640 MiB; at 256 MiB at least one, at most 320 MiB; the ratio of the first logged off-heap usages (512 over 256) lies in [1.4, 3.0]. S = 65535: all 200 inserts rejected with the text "Cannot index value of size 65535 for index", nothing added to the base or index table directory, memtable empty. No-index control: base table bytes within [0.9, 1.3] x N x S, and (base + index) of the indexed N = 4000 arm exceeds the no-index arm by at least 0.9 x N x S. Small-value control: (index bytes / key bytes) of the S = 100 arm is within [0.5, 2.0] times that of the N = 1000 x 65534 arm.
6. **Time and size.** The 16000-row arm writes about 2 x 1.05 GB (base value and index key) through a 512 MiB pool; tmpfs holds it. If a driver run exceeds 40 minutes the arm is a runbook defect, not a redesign.
7. **Cleanup.** Stop the daemon, delete `/dev/shm/s4-b2`, verify with `ps -eo cmd | grep '[C]assandraDaemon'` (not `pgrep -u $USER java`, which matches other agents' processes).

**B4. Risks and cleanup.** Disk: worst case about 3 GB on the local scratch directory; do not use shared storage; cap with the 20 GB directory. Remove `$WORK`, stop JUnit and node processes, check with `pgrep -f "CassandraDaemon|ant"`. No change to the shared source tree.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/internal/CassandraIndex.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/FBUtilities.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/SecondaryIndexManager.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/PartitionUpdate.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SingleTableUpdatesCollector.java
- grep results over /users/jason92/cassandra-5.0.9/src/java for MAX_UNSIGNED_SHORT (ClusteringPrefix, QueryProcessor, Validation, CacheService, others)

## D. Stage-4 feedback

**2026-10-28, stage 4 (results: [`results/max_unsigned_short-validateindexedvalue-value_remaining--autonomous.md`](../../stage4-runtime-verification/results/max_unsigned_short-validateindexedvalue-value_remaining--autonomous.md), node `pc32`, run 1 only, self-checked).**

- **Unit tier: Confirmed (B2g row 1) - does not cap.** 65534 accepted, 65535 and 65536 rejected with "Cannot index value of size S for index ... (maximum allowed size=65535)"; the same values are accepted without the index (the rejection is line 618, not another validator). Index backing-table disk bytes 13.3 MB, 132.1 MB, 528.1 MB at N = 100, 1000, 4000 (S = 65534; 2.0 x N x S; ratios 9.90 and 4.00), no rejection. Control: `memtable_heap_space` 64 MiB held the pool at 64.1 MiB (754.0 MiB at 2048 MiB), 7 index sstables flushed early, same 528.9 MB written.
- **Cluster tier: Confirmed (B3g row 1) - does not cap.** Precheck 5 / 5. Index live space 132.1 MB, 528.0 MB, 2,111.8 MB at N = 1000, 4000, 16000 (ratios 4.00, 4.00), all accepted; S = 65535: 200 of 200 rejected, nothing written. Pool control: first logged `MEMTABLE_LIMIT` off-heap usage 507.2 MiB at `memtable_offheap_space` 512 MiB and 256.0 MiB at 256 MiB (3 versus 7 flushes), index live space 2,111.8 MB versus 2,112.5 MB.
- **Outcome class: true negative.** The estimate stands.
- **Amendments of this audit (B2i, B3i):** a second table "with the index on the partition key" cannot show the boundary (a single-column partition key cannot be indexed; a composite key is rejected by the key-length check first, "Key length of 65539 ..."): a clustering blob column was used (`ClusteringPrefix.validate` rejects only `> 65535`, so 65535 reaches line 618). `Memtable.getLiveDataSize()` does not count partition keys, which hold the indexed value (132,000 B for 4000 keys of 65534 B), so the pool-accounted `owns()` was used.
- **Side findings:** the index table stores the value twice on disk (Data.db and Index.db: 2 x S per indexed value); `nodetool tablestats` "Memtable data size" of an index table under-reports by about 2000 times for large values; a directory-glob size reading overcounts while compactions run (the node's "Space used (live)" does not).
- **Not run:** the read-side check at line 225 (`>`), the non-client paths (index build, streaming, hints, sstable import).
