<!-- file: cases/max-unsigned-short-validateKey-keyRemaining--autonomous.md -->
# FBUtilities.MAX_UNSIGNED_SHORT (partition-key length cap) — verification solution

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/cql3/Validation.java:51` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI, 2026-10-26 |
| Estimate | `negative`: the constant caps the byte length of a single serialized partition key at 65535 bytes. That is a format/serialization limit, not a memory or disk budget; total usage is unbounded in the number of keys. |
| Ground | The check bounds one key (<= 64 KiB), a bound on the size of an object that is not itself memory- or disk-significant. Nothing limits how many keys, rows or bytes the node holds, and the cap is not tunable. Usage (heap, memtable, commit log, SSTables) scales with key count and value sizes and is independent of this value. |

## A. Constraint trace

**A1. The constraint.** `FBUtilities.MAX_UNSIGNED_SHORT = 0xFFFF` (65535), a compile-time `public static final int` constant, first declared at `src/java/org/apache/cassandra/utils/FBUtilities.java:158`. Unit: bytes when used on key lengths (also reused as a count limit for bind markers and warnings). Default: fixed, derived from the 2-byte unsigned length prefix used by `writeWithShortLength`. Not settable via yaml, `-D` or JMX; changing it requires editing the source and rebuilding.

**A2. What it caps.** Resource: neither heap nor disk as a budget. It caps the serialized length of one partition key (`key.remaining()`), in bytes, so that the key fits the unsigned-short length prefix. The operand compared at the target is `key.remaining()` (`Validation.java:51`).

**A3. Mechanism.**
1. `ModificationStatement` calls `Validation.validateKey(metadata(), key)` for each key on both the range-deletion and normal paths (`cql3/statements/ModificationStatement.java:781`, `:802`).
2. `Validation.validateKey` throws `InvalidRequestException("Key may not be empty")` if null/empty (`Validation.java:47-48`).
3. If `key.remaining() > MAX_UNSIGNED_SHORT` it throws `InvalidRequestException("Key length of N is longer than maximum of 65535")` (`Validation.java:51-56`); the comment at line 50 names the reason: `ByteArrayUtil.writeWithShortLength` / `ByteBufferUtil.writeWithShortLength`.
4. Then the type validates the key (`partitionKeyType.validate`, `Validation.java:60`).
Sibling enforcement points of the same constant: `QueryProcessor.validateKey` (`QueryProcessor.java:259`, used by `ModificationStatement.java:374` and `SelectStatement.java:732`, `TriggerExecutor.java:209`); defensive asserts in `ByteBufferUtil.java:365`, `ByteArrayUtil.java:229`, `NativeClustering.java:50`; `ClusteringPrefix.java:278-287` (clustering values); `SortedTableWriter.java:169-171` (logs and skips a too-large key on flush); `CacheService.java:504`.
Outcomes: a statement with an oversized key is rejected before a mutation is built, so it never reaches memtable or commit log. Keys <= 65535 bytes pass. Bypass/overshoot: the cap does not limit the number of keys, the clustering/value/row size, or the total partition size; a multi-column composite key is checked as one serialized buffer. Paths that do not call these validators (e.g. internal/batch-replay, streaming) are bounded by asserts or the writer's skip.

**A3 note (stage-4 audit amendment, 2026-10-26).** The reject branch of `Validation.validateKey` (`Validation.java:51-56`) is shadowed twice on every CQL path, so it can fire only on a direct call. (1) A partition key built from the statement's restrictions (a bound or literal key in INSERT, UPDATE or DELETE) is made by `PartitionKeySingleRestrictionSet.toByteBuffers`, which calls `ClusteringPrefix.validate()` on each key (`PartitionKeySingleRestrictionSet.java:67`); that method throws the same message `Key length of N is longer than maximum of 65535` for a value above `MAX_UNSIGNED_SHORT` (`ClusteringPrefix.java:278-285`). (2) Each key list then goes through `ModificationStatement.buildPartitionKeyNames`, which calls `QueryProcessor.validateKey(key)` on every key (`ModificationStatement.java:372-374`; callers `getMutations` `:746`, the CAS path `:559`, `BatchStatement.java:287`); that method has the same `> MAX_UNSIGNED_SHORT` test and message (`QueryProcessor.java:259-263`). (3) `addUpdates` receives that same list (`ModificationStatement.java:749`, `BatchStatement.java:312`), and `Validation.validateKey` (`:781`, `:802`) sees only keys that already passed both. Steps 1-3 above are right about what the method does, not about which line rejects first. The claim (B1) and the estimate do not change. (The first version of this note, written before the instrument check, named only (2); the cluster shakedown showed no oversize key reaching `QueryProcessor.validateKey`, and (1) was found in the source afterwards. Dated the same day, before any run-1 reading.)

**A4. Other consumers.** Heap (memtables, key cache, row cache, request buffers) and disk (commit log, SSTables, hints) are governed by other settings (memtable space, `max_value_size`, native transport in-flight limits, `commitlog_total_space`, etc.), which are outside this constant's control.

**A5. Evidence beyond the source.** none (conclusions from source only).

## B. Verification solution

**B1. Claim under test.** Memory/disk usage of a node does not follow `MAX_UNSIGNED_SHORT`: it only rejects individual partition keys longer than 65535 bytes, and total usage with keys at or below the limit grows with the number of keys written without being bounded by it. (Refuted if usage is bounded by or tracks this constant beyond the single-key length check.)

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a ~/cassandra-5.0.9/ /local/tmp/c509/`), `cd /local/tmp/c509 && ant jar`. Write a JUnit test (or small main) in a new class under `/local/tmp/c509/test/unit/org/apache/cassandra/cql3/ValidationKeyLengthTest.java`; run `ant testsome -Dtest.name=ValidationKeyLengthTest`. JVM options: defaults, `-Xmx512m`. Use `DatabaseDescriptor.daemonInitialization()` / `SchemaLoader` setup for a table with a `blob` partition key.

**B2b. Knobs.** Key length L in bytes: 1, 65534, 65535, 65536, 70000. (The constant itself is not settable; boundaries around it are the knob.) Number of keys N per run: 1, 1000, 100000.

**B2c. Workload.** For each L, build `ByteBuffer.allocate(L)` and call `Validation.validateKey(metadata, key)`. Then loop N validations of distinct 65535-byte keys retained in a list (strongly referenced) to show total retained bytes = N*65535 with no rejection. Arithmetic: 100000 * 65535 ~ 6.5 GB exceeds the heap, so use N=5000 (~328 MB) under -Xmx512m, and N=20000 under -Xmx256m to show an OOM, not a validator rejection.

**B2d. Observables and instruments.** Whether `InvalidRequestException` is thrown and its message; retained bytes via `Runtime.totalMemory()-freeMemory()` after `System.gc()` (or JMX `MemoryMXBean`) sampled after each batch of 1000. Cannot be observed: any server-side memtable accounting (no node).

**B2e. Procedure.** 1) Build. 2) Run boundary test over the L values. 3) Run the N-scaling loop at L=65535. 4) Positive control: run the same retention loop against a known binding cap, e.g. wrap values in `ByteBufferUtil.writeWithShortLength`-style size checks is not a cap; instead use `Memtable`-independent control `org.apache.cassandra.utils.memory.MemtablePool` allocator with a small limit (`MemtableAllocator`) to show retained usage stops/blocks at its limit while the key validator never does. 5) Record.

**B2f. Predictions (before any run).** L<=65535: no exception; L=65536 and 70000: exception with message "Key length of L is longer than maximum of 65535". N-scaling at L=65535: all N validations pass; retained heap grows linearly ~ N*65535 bytes until OOM (at -Xmx256m, N=20000 should OOM before completing), with no validation failure. Positive control: allocation is blocked or throttled at the pool limit.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Rejection only at L>65535; heap grows ~N*65535 and no rejection (or OOM first) | Claim confirmed: the constant bounds one key, not usage |
| Heap plateaus at a value tied to 65535 while N grows | Claim refuted: usage follows the constant |
| Keys of 65536+ accepted | Trace wrong (check not on this path) |
| Usage flat while the positive control (pool limit) also stays flat/blocked-by-limit | Confirmed only if the control's cap binds at its limit; control must move/bind |
| Control never reaches its limit, or heap never grows | Not confirmed (limit not reached / workload too small) |

**B2h. Controls.** Same JVM and heap across runs; warm-up pass discarded; explicit GC before readings; positive control as in B2e; L=1 run as baseline.

**B2i. Stage-4 audit amendments, 2026-10-26** (made before any reading; none depends on a reading; B2g is unchanged).
1. *Paths and build (B2a).* `/local/tmp/...` does not exist on the run node. The tree is a `copy-source.sh` copy at `~/s4-b9-vk/u` on local disk, built once with `ant jar`. The driver (`harness/max-unsigned-short-validateKey-keyRemaining--autonomous/KeyLenDriver.java`) is compiled outside the tree against `build/classes/main`, `build/lib/jars/*` and `conf`, and run with `-Dcassandra.config=file://<tree>/conf/cassandra.yaml`. Table metadata for the target call: `TableMetadata.builder("ks","t").partitioner(Murmur3Partitioner.instance).addPartitionKeyColumn("k", BytesType.instance).build()`. JVM heaps: `-Xmx512m` for the hold runs, `-Xmx256m` for the OOM run, `-Xmx1g` otherwise.
2. *Boundary rows (B2b, B2f), from the source.* The target is `Validation.validateKey(metadata, key)`; `QueryProcessor.validateKey(key)` is also called, as the shadowing method (A3 note). L = 0 and a `null` key: rejected with "Key may not be empty" (`Validation.java:47-48`). L in {1, 1000, 65534, 65535}: accepted. L in {65536, 70000, 1,000,000}: rejected with exactly `Key length of <L> is longer than maximum of 65535` (`Validation.java:53-55`). Order of the checks (`Validation.java:51` before `:60`): with a table whose key type is `Int32Type`, a 65536-byte key is rejected with the length message, a 65535-byte key is rejected with a type message that does not start with "Key length" ("Expected 4 or 0 byte int (65535)", `Int32Serializer.java:43`), and a 4-byte key is accepted.
3. *Wrong number in B2f corrected.* A heap `ByteBuffer.allocate(1)` costs about 72 B (48 B object plus a 24 B array) plus a list reference, so 1,000 one-byte keys retain about 0.08 MB, not 1 MB. B2f's "about 65 MB per 1,000 max-size keys" is kept. Restated as a relation: the slope of retained heap between 1,000 and 5,000 held keys is `L + overhead` bytes per key with overhead between 40 and 120 B (L = 65535: 65.6 to 65.7 KB per key; L = 1: 41 to 121 B per key), and the ratio of the two slopes (L = 65535 over L = 1) is above 500. 5,000 x 65.6 KB = 328 MB fits `-Xmx512m`.
4. *Aggregate part (B2b, B2c).* Stream N = 100,000 freshly allocated, distinct 65535-byte keys through `Validation.validateKey`, none held (6.55 x 10^9 key bytes, 100,000 times the per-key cap): all accepted, no exception, heap after a final full GC below 100 MB.
5. *OOM leg (B2c, B2f).* Hold distinct 65535-byte keys in a list under `-Xmx256m`, validating each, until `OutOfMemoryError`: prediction, the driver reports the OOM after between 1,500 and 4,100 held keys (256 MiB / 65.6 KB = 4,091 is the ceiling), before 20,000, with 0 validation rejections.
6. *Positive control made specific (B2e.4, B2h).* B2e.4 names a pool but not its use. The control is a real memtable pool: `new HeapPool(64 MiB, 0.75f, null)` and `HeapPool.Allocator.allocate(65535, group)` (a real memtable allocation of key size) called from a worker thread, with an `OpOrder.Group` from `new OpOrder().start()`. Source: `MemtablePool.SubPool.tryAllocate` refuses when `allocated + size > limit` (`MemtablePool.java:151-155`) and `SubAllocator.allocate` then waits (`MemtableAllocator.java:169-196`). Prediction: exactly 1,024 allocations return (1,024 x 65,535 = 67,107,840 <= 67,108,864 < 1,025 x 65,535), `pool.onHeap.used()` equals 67,107,840, the 1,025th call is still blocked after 2 s, and meanwhile `Validation.validateKey` accepts 100,000 further 65535-byte keys with no rejection. This is the "control must bind" row of B2g.
7. *Gap named (B2d).* Retained-heap readings measure the driver's own list (the check retains nothing): they show the cost of holding that many accepted keys, not a node's memtable accounting, which only the cluster tier sees.
8. *Leftover check (B2e).* By the driver's own PID and its work directory, not `pgrep -fl "java|python"` (other agents run JVMs on the same host).

### B3. Cluster tier

**B3a. Environment and build.** One node, local disk of known size (>= 20 GB, dedicated directory), JDK 11, source copy built with `ant jar`. `-Xms2g -Xmx2g`. Config: `memtable_allocation_type: heap_buffers`, `memtable_heap_space: 256MiB`, `commitlog_total_space: 512MiB`, data/commitlog/hints dirs under `/local/tmp/node1/`. Table: `CREATE TABLE ks.t (k blob PRIMARY KEY, v blob)` with `replication_factor 1`.

**B3b. Knobs.** Key size L: 1000, 65535, 65536 bytes (the constant is not configurable). Key count N: 10k, 100k. Value size fixed at 100 bytes. (Control knob: `memtable_heap_space`, 256MiB vs 128MiB.)

**B3c. Workload.** Python driver or `cassandra-stress`-like loop using prepared INSERTs with random distinct keys of L bytes. 65535-byte keys: N=100k => ~6.5 GB logical key bytes, which exceeds `memtable_heap_space`, forcing flushes and disk growth, and passes `commitlog_total_space`. 65536-byte keys: 100 attempts. Duration: until N inserted (about tens of minutes).

**B3d. Observables and instruments.** Client errors (message text); `nodetool tpstats`, `nodetool info` (heap); `jcmd <pid> GC.heap_info` every 10 s; `du -sb` on data and commitlog directories every 10 s; JMX `org.apache.cassandra.metrics:type=Table,name=MemtableOnHeapDataSize` and `LiveDiskSpaceUsed`. Not observable directly: per-key retained bytes inside the memtable.

**B3e. Procedure.** 1) Build, start node, create schema. 2) Insert 100 keys at L=65536; expect all rejected. 3) Insert N=10k then 100k keys at L=65535 with sampling. 4) Repeat with L=1000. 5) Positive control: repeat L=65535 with `memtable_heap_space: 128MiB` and compare memtable size and flush counts. 6) `nodetool drain`, stop the node, check `pgrep -f CassandraDaemon`, delete `/local/tmp/node1`.

**B3f. Predictions.** L=65536: 100/100 rejected with "Key length of 65536 is longer than maximum of 65535"; nothing appears in memtable or disk. L=65535: no rejections; data-dir size grows roughly linearly in N * (L+overhead), e.g. >= 6 GB at 100k, unaffected by the constant. Memtable heap is bounded by `memtable_heap_space` (flushes occur), and halving it changes flush frequency while the key limit has no effect.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Only L>65535 rejected; disk and heap scale with N and L<=65535, and the control knob moves memtable size/flush rate | Claim confirmed |
| Total disk/heap saturates near a value derived from 65535 independent of N | Claim refuted |
| 65536-byte keys accepted | Trace wrong |
| Control knob (`memtable_heap_space`) does not change memtable behaviour, or the memtable never reaches its limit | Not confirmed (control did not move / limit not reached) |

**B3h. Controls.** L=1000 baseline; identical node config across runs; wipe data dirs between runs; positive control via `memtable_heap_space`.

**B3i. Stage-4 audit amendments, 2026-10-26** (made before any reading; none depends on a reading; B3g is unchanged).
1. *Placement (B3a).* `/local/tmp/node1` does not exist. Tree `~/s4-b9-vk/c` on pc12 (`copy-source.sh` copy, `ant jar`); node data, commitlog, hints, saved_caches on tmpfs `/dev/shm/s4-b9-vk/node` (disk bytes are tmpfs bytes, the same file sizes). Port slot 5: address 127.0.5.1 (storage 7000, native 9042 on that address only), JMX 7150, Byteman agent port 19150. `MAX_HEAP_SIZE=2G` (G1, the JDK 11 default). Yaml as B3a (`memtable_allocation_type: heap_buffers`, `memtable_heap_space: 256MiB`, `commitlog_total_space: 512MiB`) plus `auto_snapshot: false`, `memtable_cleanup_threshold: 0.99` (otherwise a flush starts well below the pool limit), `native_transport_timeout: 30s`, `write_request_timeout: 20000ms`. With `heap_buffers` the key bytes are charged to the on-heap pool, so `memtable_heap_space` is the pool that can bind.
2. *Workload (B3c).* Table per arm `ks.t_<arm>` (`k blob PRIMARY KEY, v blob`, RF 1), replacing the truncate (no snapshot, no timeout). Prepared INSERT, protocol 4, 32 in flight. Key: an 8-byte counter followed by seeded random bytes up to K (zero padding would compress to nothing in the data files and flatten disk bytes for a reason unrelated to the cap); value: 100 random bytes. `nodetool flush` after the writes, then sizes of `*-Data.db` and `*-Index.db`.
3. *First-trigger check and run order (B3e).* After the first table exists: 5 writes at K = 65535 must succeed and 5 at K = 65536 must fail with `Key length of 65536 is longer than maximum of 65535`; otherwise the run stops (the traced boundary is wrong, B3g row 3). Life 1 (`memtable_heap_space: 256MiB`): K = 1000 at N = 10,000 and 100,000; K = 65535 at N = 10,000 and 100,000; K = 65536, 100 attempts. Life 2 (restart, `memtable_heap_space: 128MiB`): K = 65535, N = 100,000. K = 65535 at N = 100,000 writes 6.55 GB of keys, about 13 GB of Data+Index on tmpfs (126 GB free, the table is dropped after each arm).
4. *Which line rejects (new observable).* Because of the A3 note, the cluster rejection at K = 65536 comes from `ClusteringPrefix.java:279`, not from `Validation.java:51` (nor `QueryProcessor.java:259`). A Byteman script (agent `listener:true,port:19150`, rules on Cassandra classes, trace to a file on tmpfs) traces: `Validation.validateKey` entries with `key.remaining() >= 1000` (line `V <length>`); `QueryProcessor.validateKey` entries with `key.remaining() > 65535` (line `Q <length>`); and every `InvalidRequestException(String)` whose message starts with "Key length of" (line `X <message> :: <top 8 stack frames>`). Prediction: in life 1, 105 `X` lines (5 precheck + 100 attempts), all with the message for length 65536, every stack containing `ClusteringPrefix.validate` and none containing `QueryProcessor.validateKey` or `Validation.validateKey`; 0 `Q` lines; 0 `V` lines above 65535; `V` lines of length exactly 65535 equal the accepted writes at K = 65535 (life 1: 5 + 10,000 + 100,000 = 110,005; life 2: 100,000) and of length 1000 equal 110,000 in life 1; life 2: 0 `X`, 0 `Q`. Direct evidence that the `:51` branch fires is therefore the unit tier's (a direct call); the cluster tier shows the key-size gate by the earlier method and the usage behaviour.
5. *Numbers for B3f (stated before any reading).* K = 65536: 100 of 100 rejected with the exact message, 0 B added to the table directory, memtable empty. K = 1000 and 65535: no write rejected. Data.db + Index.db after the final flush between 1.0 and 3.0 times N x K at every arm of K = 65535 and between 1.0 and 4.0 times N x K at K = 1000 (per-partition overhead matters at 1 KB); the N = 100,000 arm is 8 to 12 times the N = 10,000 arm of the same K (linear in N). Pool: K = 65535, N = 100,000 at 256 MiB: at least 10 flushes with reason `MEMTABLE_LIMIT`, each with logged on-heap usage at most 320 MiB (1.25 x 256); K = 65535, N = 10,000 at 256 MiB: 1 to 3 such flushes; K = 1000, N = 100,000 (about 100 MB of keys): at most 1. Life 2 (128 MiB), K = 65535, N = 100,000: at least 20 such flushes, each at most 160 MiB; the ratio of flush counts (128 MiB over 256 MiB, same N and K) between 1.6 and 2.5; the ratio of the median logged on-heap usage (256 MiB over 128 MiB) between 1.6 and 2.5. Halving the pool is the known binding cap that moves the plateau; the key limit has no effect on it.
6. *Observables (B3d).* Added: `RssAnon` of the node PID, `du`-equivalent sizes of the table directory and commit log every 2 s, `jcmd <pid> GC.heap_info` every 10 s (used heap), the `Enqueuing flush ... Reason: ... Usage: ...` lines of `system.log` (pool usage at each flush, with the reason), and `nodetool tablestats` just before the flush. Off-heap gauges are not relied on (`TableMetrics.java:500-507` registers the off-heap size under the on-heap name).
7. *Cleanup and leftover check (B3e.6, B4).* Stop by PID (`nodetool stopdaemon`, then `kill`), remove `/dev/shm/s4-b9-vk`, check the PID and that directory (not `pgrep -f CassandraDaemon`: other agents run nodes on the host).

**B4. Risks and cleanup.** 100k * 65535 B writes ~6.5 GB on node disk (commit log capped at 512 MiB; data is on dedicated local disk, not shared storage); keep N lower if the disk is smaller than 20 GB. The unit tier OOM run is confined to its own JVM. Stop every started process (node, JVMs, driver), verify with `pgrep -fl "java|python"`, remove `/local/tmp/c509` and `/local/tmp/node1`.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/cql3/Validation.java
- src/java/org/apache/cassandra/utils/FBUtilities.java (line 158)
- src/java/org/apache/cassandra/cql3/QueryProcessor.java (lines 245-266)
- src/java/org/apache/cassandra/cql3/statements/ModificationStatement.java (lines 775-805)
- src/java/org/apache/cassandra/io/sstable/format/SortedTableWriter.java (lines 165-175)
- grep results over src/java for MAX_UNSIGNED_SHORT and validateKey; conf/cassandra.yaml grep

## D. Stage-4 feedback

**2026-10-26, stage 4 run 1 (node pc12, no run 2): unit tier Confirmed - does not cap; cluster tier Confirmed - does not cap. Outcome class: true negative.** Results: `stage4-runtime-verification/results/max-unsigned-short-validateKey-keyRemaining--autonomous.md`; harness: `stage4-runtime-verification/harness/max-unsigned-short-validateKey-keyRemaining--autonomous/`. The estimate stands as filed.
- Unit: a direct `Validation.validateKey` call accepts 65535-byte keys and rejects 65536 with "Key length of L is longer than maximum of 65535" (the length check precedes the type check); 100,000 distinct 65535-byte keys (6.55 x 10^9 key bytes) passed without a rejection; held keys retain L + 83 B each (slope ratio 733 against the 1-byte control); an OOM under `-Xmx256m` came after 3,662 held keys with 0 rejections; a real `HeapPool` of 64 MiB bound at exactly 1,024 allocations of 65535 B while the validator kept accepting.
- Cluster (heap_buffers): all 100 writes at K = 65536 rejected and nothing written; K = 1000 and 65535 accepted at N = 10,000 and 100,000; flushed Data.db bytes 1.002 x N x K at K = 65535 and exactly 10 x at N = 100,000; the memtable pool reached its limit (24 `MEMTABLE_LIMIT` flushes at 253.9 MiB with a 256 MiB pool, 49 at 127.1 MiB with 128 MiB). One frozen number was missed: Data+Index read from the directory at K = 65535, N = 100,000 was 14.3 x the N = 10,000 arm (predicted 8 to 12) because a compaction was running when it was read; the flushed sums give 10.000. Recorded, not edited.
- Notes for stage 3: (1) the A3 note: through CQL the branch at `Validation.java:51` never rejects; `ClusteringPrefix.validate` (`PartitionKeySingleRestrictionSet.java:67`, `ClusteringPrefix.java:279`) rejects first and `QueryProcessor.validateKey` saw 0 oversize keys in the cluster run (Byteman trace of 105 rejections, all from `ClusteringPrefix.validate`); (2) `tablestats` "Memtable data size" omits partition-key bytes; (3) the commit log (512 MiB) also bound in the 100,000-key arms. Amendments: A3 note, B2i, B3i (2026-10-26).

Stage-4 audit amendments of 2026-10-26 are the A3 note, B2i and B3i above. Citation checks (pinned `cassandra-5.0.9`): lines 45-72 of `Validation.java`, 158 of `FBUtilities.java`, 249-263 of `QueryProcessor.java`, 372-374, 746, 781 and 802 of `ModificationStatement.java`, 732 of `SelectStatement.java`, 209 of `TriggerExecutor.java`, 169-172 of `SortedTableWriter.java`, 365 of `ByteBufferUtil.java`, 229 of `ByteArrayUtil.java`, 50 of `NativeClustering.java` and 278-287 of `ClusteringPrefix.java` hold. `CacheService.java:504` is a corrupted-key-cache read check, not a write-path backstop.
