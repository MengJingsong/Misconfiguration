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

**B4. Risks and cleanup.** Disk: worst case about 3 GB on the local scratch directory; do not use shared storage; cap with the 20 GB directory. Remove `$WORK`, stop JUnit and node processes, check with `pgrep -f "CassandraDaemon|ant"`. No change to the shared source tree.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/internal/CassandraIndex.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/FBUtilities.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/SecondaryIndexManager.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/PartitionUpdate.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SingleTableUpdatesCollector.java
- grep results over /users/jason92/cassandra-5.0.9/src/java for MAX_UNSIGNED_SHORT (ClusteringPrefix, QueryProcessor, Validation, CacheService, others)

## D. Stage-4 feedback

`none yet`
