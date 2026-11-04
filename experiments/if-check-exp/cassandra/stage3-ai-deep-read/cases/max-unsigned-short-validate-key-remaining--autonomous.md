# Partition-key length cap (FBUtilities.MAX_UNSIGNED_SHORT in QueryProcessor.validateKey) — verification solution  <!-- file: cases/max-unsigned-short-validate-key-remaining--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/cql3/QueryProcessor.java:259` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI, 2026-10-26 |
| Estimate | `negative`: the constant bounds the size of one serialized partition key (65535 bytes), not the memory or disk a node uses in aggregate. |
| Ground | It is a format-driven, per-object limit (keys are serialized with a 2-byte length prefix). It is not settable, and total usage is governed by other limits (memtable space, cache sizes, frame size, batch thresholds) that scale with the number of keys and rows, not with this constant. |

## A. Constraint trace

**A1. The constraint.** `FBUtilities.MAX_UNSIGNED_SHORT`, a compile-time constant (`public static final int MAX_UNSIGNED_SHORT = 0xFFFF`), declared at `src/java/org/apache/cassandra/utils/FBUtilities.java:158`. Kind: constant. Unit: bytes when compared with `key.remaining()` (it is also used as an element-count or character-count limit elsewhere). Value: 65535, which is the largest length a 2-byte unsigned prefix can hold. Setting: not settable through yaml, `-D` or JMX; changing it needs a source change and rebuild.

**A2. What it caps.** Heap, as a side effect: the length in bytes of a single partition key `ByteBuffer`. The compared quantity is `key.remaining()` (`QueryProcessor.java:259`). The stated purpose is not resource control but that the key "can be handled by ByteArrayUtil.writeWithShortLength and ByteBufferUtil.writeWithShortLength" (comment at `QueryProcessor.java:258`).

**A3. Mechanism.**
1. `QueryProcessor.validateKey(ByteBuffer)` (`QueryProcessor.java:249`) rejects null or empty keys (251), the unset sentinel (255), then keys longer than 65535 bytes (259-263) with `InvalidRequestException`. A key of exactly 65535 bytes is accepted.
2. Callers: `ModificationStatement.buildPartitionKeyNames` (`cql3/statements/ModificationStatement.java:372-374`, writes) and `SelectStatement` key decoration (`cql3/statements/SelectStatement.java:730-732`, reads), plus `TriggerExecutor.java:209`.
3. A near-duplicate check with a table-aware signature is `Validation.validateKey` (`cql3/Validation.java:51`), used at `ModificationStatement.java:781,802`.
4. Down-stream backstops for the same constant: `ByteBufferUtil.java:365` and `ByteArrayUtil.java:229` (asserts), `ByteBufferUtil.java:766`, `SortedTableWriter.java:169-172` (logs and skips the partition), and `CacheService.java:504`.
5. Outcome at the limit: the request fails with an error and nothing is written or read. Below the limit the request proceeds and the key's bytes are copied (`ByteBufferUtil.clone(key)` at `SelectStatement.java:732`).
6. Bypass or overshoot: the check is per key. A multi-key `IN`, a batch, or many concurrent requests can hold any number of 64 KB keys. Clustering values have their own limit (`ClusteringPrefix.java:278-287`, same constant). Values and other cell data are not covered at all. Tables with key sizes in memtables and sstables are bounded only by the aggregate limits in A4.

**A4. Other consumers.** Memory limits that actually bound usage: `memtable_heap_space`/`memtable_offheap_space`, `commitlog_segment_size` (`conf/cassandra.yaml:660`), `native_transport_max_frame_size` (`conf/cassandra.yaml:1044`), `batch_size_fail_threshold` (`conf/cassandra.yaml:1844`), `max_value_size` (`conf/cassandra.yaml:1864`), and the key and row cache sizes. All of these cap totals or other objects.

**A5. Evidence beyond the source.** none (the `conf/cassandra.yaml` lines above are in the pinned tree).

## B. Verification solution

**B1. Claim under test.** Node memory and disk usage do not follow the 65535-byte key cap: with the cap fixed, usage for a fixed number of partitions grows in proportion to total key bytes (up to 64 KB per key) and is bounded by the aggregate limits (memtable space, etc.), not by `MAX_UNSIGNED_SHORT`. The cap itself only rejects any single key above 65535 bytes.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`cp -r ~/cassandra-5.0.9 /local/c509-unit`), then `ant jar` in the copy. Write a small Java program (outside the tree, in `/local/unit-driver/`) compiled against `build/apache-cassandra-5.0.9.jar` and `build/lib/jars/*`. JVM options: `-Xmx512m -Dcassandra.config=file:///local/c509-unit/conf/cassandra.yaml`. Alternative: add a JUnit test in the copy and run `ant testsome -Dtest.name=<Class> -Dtest.methods=<m>`.

**B2b. Knobs.** The constant is not tunable, so the knob is the key length `L` passed in: 1, 1000, 65534, 65535, 65536, 70000, 1,000,000 bytes. These bracket the boundary from both sides.

**B2c. Workload.** For each `L`, call `QueryProcessor.validateKey(ByteBuffer.allocate(L))` (and `Validation.validateKey(metadata, key)` for the table-aware variant). For the aggregate part, build N = 100,000 distinct keys of length 65535 as direct buffers and call `validateKey` on each, to show the check passes for a number of keys far above the cap in total bytes (about 6.5 GB of logical key data if held at once, so use N = 5,000 held, about 330 MB, with `-Xmx1g`, and stream the rest).

**B2d. Observables and instruments.** Whether `InvalidRequestException` is thrown and its message; heap after each batch of keys via `Runtime.totalMemory()-freeMemory()` after `System.gc()`, and `-Xlog:gc`. Not observable: the real node's memtable accounting.

**B2e. Procedure.**
1. Build in the local copy, then compile the driver.
2. Run it for each `L` and record accepted/rejected.
3. Hold 1,000, then 5,000 accepted 65535-byte keys in a list and record retained heap after a full GC.
4. Repeat step 3 with 1-byte keys as the positive control for "usage follows key bytes".
5. Check no `java` process is left over (`pgrep -u $USER java`).

**B2f. Predictions.** `L` of 1, 1000, 65534, 65535 accepted; 65536, 70000, 1,000,000 rejected with message "Key length of L is longer than maximum of 65535". Retained heap is about 65 MB per 1,000 max-size keys and about 1 MB per 1,000 one-byte keys; no step of the check bounds it below the JVM `-Xmx`.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Boundary behaves as in B2f, heap scales with key count x length | Claim confirmed: the check is a per-key size gate and does not bound memory in aggregate |
| Heap stays flat or capped as the number of accepted keys grows, below `-Xmx` | Claim refuted: something else in the check bounds total key memory |
| 65536 accepted or 65535 rejected | The traced boundary is wrong; re-derive A3 |
| Usage flat while the positive control (more or larger keys) also stays flat | Control did not move; not confirmed |
| Limit never reached because the driver fails earlier (OOM, config load error) | Not confirmed; fix the harness |

**B2h. Controls.** The 1-byte-key run (positive control: the same workload shows usage moving with key bytes); `-Xmx` fixed identically in all runs; GC forced before each reading.

**B2i. Stage-4 audit amendments, 2026-10-26** (made before any reading; none depends on a reading; B2g is unchanged).
1. *Paths and build (B2a).* The tree is a `copy-source.sh` copy at `~/s4-b8-uk/u`, built once with `ant jar`; the driver (`harness/max-unsigned-short-validate-key-remaining--autonomous/KeyLenDriver.java`) is compiled outside the tree against `build/classes/main`, `build/lib/jars/*` and `conf` (as the earlier `PkStackTest` harness did), with `-Xmx1g` for the heap runs and `-Dcassandra.config=file://<tree>/conf/cassandra.yaml`. `Validation.validateKey(metadata, key)` needs a `TableMetadata` with a blob partition key (`TableMetadata.builder("ks","t").addPartitionKeyColumn("k", BytesType.instance)`).
2. *Boundary rows added from the source (B2b, B2f).* `L = 0` and a `null` key are also called; prediction from `QueryProcessor.java:251-254` and `Validation.java:47-48`: rejected with "Key may not be empty". Message for `L > 65535` is exactly `Key length of <L> is longer than maximum of 65535` for both methods (`QueryProcessor.java:261-262`, `Validation.java:53-55`). `ByteBufferUtil.UNSET_BYTE_BUFFER` is `ByteBuffer.wrap(new byte[]{})` (`ByteBufferUtil.java:92`), an empty buffer, so `QueryProcessor.validateKey` rejects it with "Key may not be empty" at line 251 and the "Key may not be unset" branch (line 255) is unreachable for that object. (Corrected the same day, 2026-10-26, during the instrument check: this item first said "Key may not be unset", a mistake from not reading the constant's definition; it is not in B2f/B2g and does not change the claim.)
3. *Wrong number in B2f corrected.* A heap `ByteBuffer.allocate(1)` costs about 72 B (48 B buffer object plus a 24 B `byte[]`) plus 4 to 8 B of list reference, so 1,000 one-byte keys retain about 0.08 MB, not 1 MB. The prediction is restated as a relation: the slope of retained heap between 1,000 and 5,000 held keys is `L + overhead` bytes per key with overhead between 40 and 120 B (L=65535: 65.6 to 65.7 KB per key, i.e. about 65.6 MB per 1,000; L=1: 41 to 121 B per key). The ratio of the two slopes (L=65535 over L=1) is above 500. Neither number is bounded by 65535 x anything, and no step of the check bounds the retained total below `-Xmx`.
4. *Aggregate part (B2c).* Stream N = 100,000 freshly allocated, distinct 65535-byte keys through both methods without holding them (6.55 x 10^9 key bytes in total, 100,000 times the per-key cap, with `-Xmx1g`): prediction, all accepted, zero exceptions, heap after a final `System.gc()` below 100 MB. Then hold 1,000 and 5,000 as in B2e.3.
5. *Gap named (B2d).* The retained-heap readings measure the driver's own list of key buffers (the check itself retains nothing); they show how much a node would have to hold if it held that many accepted keys, not a node's memtable accounting, which only the cluster tier sees.
6. *Leftover check (B2e.5).* `pgrep -u $USER java` is replaced by a check on the driver's own PID, because other sessions run JVMs on the same host.

### B3. Cluster tier

**B3a. Environment and build.** One node, local copy of the tag built with `ant jar` on local disk (`/local/c509-node`), data, commitlog, hints and saved_caches under `/local/c509-data` on a partition with at least 20 GB free. `JVM_OPTS`: `-Xms2g -Xmx2g`, `-XX:+UseG1GC`. Config changes in the copy's `conf/cassandra.yaml`: `memtable_heap_space: 512MiB` (so the aggregate limit is visible), `memtable_offheap_space: 512MiB`, `commitlog_total_space: 1GiB`, `memtable_allocation_type: offheap_objects`. Clients: `cqlsh` and a Python driver script.

**B3b. Knobs.** Key size K per partition, with a fixed row count: K = 16 B, 1 KB, 32 KB, 65535 B, 65536 B. The constant itself cannot be changed. 65535 is the boundary key; 65536 is the rejected key.

**B3c. Workload.** Table `ks.t (k blob PRIMARY KEY, v int)`. For each K insert N = 10,000 distinct partitions through the driver (prepared statement, blob key built from a counter padded to K), single-partition writes, then flush. Arithmetic: at K = 65535 this is about 655 MB of key bytes, which exceeds the 512 MiB memtable heap budget and so forces flushes and shows that the aggregate limit, not the key cap, governs. At K = 65536 expect every insert rejected. Duration: about 5 minutes per K.

**B3d. Observables and instruments.** `nodetool tablestats ks.t` (memtable data size, off-heap size, SSTable space used); `nodetool gcstats`; `jcmd <pid> GC.heap_info` and `jcmd <pid> VM.native_memory summary` (with `-XX:NativeMemoryTracking=summary`); `du -sb /local/c509-data` for disk, sampled every 10 s; the driver's count of `InvalidRequest` errors. Not observable directly: exact per-key heap cost.

**B3e. Procedure.**
1. Build, apply B3a config, start the node, wait for `nodetool status` to show UN.
2. Create the table; record baseline heap and disk.
3. For each K in order, run the N-insert workload, sampling instruments every 10 s, then `nodetool flush` and read final disk use. Truncate the table between runs.
4. Run K = 65536 and record the driver errors.
5. Positive control: repeat with K = 16 B but N = 650,000 (about the same logical key bytes as K = 1 KB, N = 10,000), and with a smaller `memtable_heap_space` (128MiB) at K = 1 KB to show a known cap that does bind.
6. Stop the node (`nodetool drain`, then kill), delete `/local/c509-data`, check no `java` processes remain.

**B3f. Predictions.** K up to 65535 accepted; K = 65536 gives 10,000 `InvalidRequest` errors and zero disk growth. Disk and memtable size scale roughly linearly with N x K (about 655 MB of key bytes at K = 65535 plus overhead) and are not clamped by the constant. Memtable heap/off-heap use is held near the configured `memtable_*_space` through flushes, regardless of K. With `memtable_heap_space: 128MiB` the plateau drops accordingly (control moves).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Disk and memtable use scale with N x K up to 65535, 65536 rejected, plateau set by `memtable_*_space` | Claim confirmed: the cap is a per-key size gate; usage follows other limits |
| Usage plateaus at or near a level that depends on 65535 and not on memtable/other settings | Claim refuted |
| 65536 accepted, or 65535 rejected | The traced boundary is wrong |
| Plateau moves with `memtable_heap_space` while usage across K is flat per byte of key | Positive control works; claim confirmed |
| No flush or plateau seen, or the control plateau does not move | Limit never reached or control did not move; not confirmed |

**B3h. Controls.** The `memtable_heap_space` change (known binding cap); the small-key, high-N run (same bytes, different key size); the same node configuration for every K; table truncated and node idle between runs.

**B3i. Stage-4 audit amendments, 2026-10-26** (made before any reading; none depends on a reading; B3g is unchanged).
1. *Placement (B3a).* Tree `~/s4-b8-uk/c` (copy-source.sh copy, `ant jar`); node data, commitlog, hints, saved_caches on tmpfs `/dev/shm/s4-b8-uk/node` (not `/local/...`, which does not exist; many local nodes on a spinning disk stall). Port slot 7: address 127.0.7.1 (storage 7000, native 9042 on that address only), JMX 7170. `MAX_HEAP_SIZE=2G`, G1 (the JDK 11 default of `jvm11-server.options`). Added yaml lines to B3a: `auto_snapshot: false` (a truncate or drop would otherwise snapshot the data), `memtable_cleanup_threshold: 0.99` (otherwise a flush starts at the default 1/(memtable_flush_writers+1) of the pool and the pool limit is never approached), `native_transport_timeout: 30s`, `write_request_timeout: 20000ms`. The memtable is the default `skiplist` class; `memtable_allocation_type: offheap_objects` as in B3a, so key bytes are charged to the off-heap pool.
2. *Keys (B3c).* The blob key is an 8-byte big-endian counter followed by seeded pseudo-random bytes up to K (a zero-padded key would compress to nothing in the LZ4-compressed data file and make disk bytes flat for a reason unrelated to the cap). Prepared statement, protocol version 4, `execute_concurrent_with_args` with 32 in flight.
3. *Fresh table per arm (B3e.3).* A new table (`ks.t_<arm>`) per arm replaces the truncate: same empty starting state, no truncate timeouts. `nodetool flush` after the writes, then `du -sb` of the table's data directory.
4. *Order and first-trigger check (B3e).* The first step after the table exists is the boundary precheck: 5 writes at K = 65535 must all succeed and 5 writes at K = 65536 must all fail with `Key length of 65536 is longer than maximum of 65535`; if either differs the run stops (the traced boundary is wrong, B3g row 3). Life 1 (memtable pools 512 MiB each): K = 16, 1024, 32768, 65535, 65536 at N = 10,000, then the K = 16, N = 650,000 control. Life 2 (restart with `memtable_heap_space` and `memtable_offheap_space` both 128 MiB): K = 32768, N = 10,000.
5. *Control arithmetic corrected (B3e.5, B3f).* K = 1 KB at N = 10,000 is 10 MB, which never reaches a 128 MiB pool, so that control could not move; the binding-cap control is K = 32768 (N = 10,000, 328 MB, above 128 MiB = 134 MB and below 512 MiB). Because `offheap_objects` charges the key bytes to the off-heap pool, the control lowers both pools to 128 MiB (B3f says `memtable_heap_space: 128MiB`; lowering only the heap pool would not bind). The small-key control (K = 16, N = 650,000 = 10.4 MB of key bytes, about the same as K = 1 KB, N = 10,000) is for a different question: that usage follows per-partition count as well as key bytes; its prediction is that its disk bytes exceed those of K = 1 KB at N = 10,000 (per-partition overhead), not that they are equal.
6. *Numbers for B3f (stated before any reading).* K = 65536: 10,000 `InvalidRequest` replies, 0 B added to the data directory and no memtable growth. Flushed Data.db + Index.db bytes at K >= 32768 are between 1.0 and 3.0 times N x K (key stored in data and index files; random keys do not compress). K = 65535, 512 MiB pools: 655 MB of keys exceeds the pool, so at least one flush with reason `MEMTABLE_LIMIT` is logged and its logged usage is at most 640 MiB; K = 32768 at 512 MiB: no `MEMTABLE_LIMIT` flush (328 MB is under the pool); K = 32768 at 128 MiB: at least one `MEMTABLE_LIMIT` flush with logged off-heap usage at most 160 MiB (1.25 x 128). Ratio of the first `MEMTABLE_LIMIT` flush's logged off-heap usage, K = 65535 at 512 MiB over K = 32768 at 128 MiB, between 2.5 and 6.
7. *Observables (B3d).* Added: `RssAnon` of the node PID (memtable regions are JNA `malloc`, which native memory tracking cannot see), the `MEMTABLE_LIMIT` lines of `system.log`, and JMX `MemtableLiveDataSize` read just before the flush (the `MemtableOffHeapDataSize` gauge is registered under the on-heap name, `TableMetrics.java:500`, so it is not used). `du -sb` and `RssAnon` are sampled every 2 s while the writes run (finer than the 10 s of B3d). Disk is tmpfs bytes, a proxy for disk bytes with the same file sizes.
8. *Cleanup and leftover check (B3e.6, B4).* The node is stopped by PID (`nodetool stopdaemon`, then `kill`), `/dev/shm/s4-b8-uk` removed, and the check is on that PID and that directory, not `pgrep -u $USER java`. Disk use per life is about 3 GB of tmpfs.

**B4. Risks and cleanup.** Unit tier: heap only, about 1 GB; remove `/local/c509-unit` and `/local/unit-driver`. Cluster tier: disk use up to about 3 GB per run (data plus commitlog) on local disk only, never the shared source tree or shared storage; the node must be stopped and its data directory deleted, and `pgrep -u $USER java` must show nothing left.

## C. Sources read

- `/users/jason92/writeup-A/playbook-autonomous.md`
- `/users/jason92/writeup-A/_TEMPLATE-autonomous.md`
- `src/java/org/apache/cassandra/cql3/QueryProcessor.java` (lines 225-304)
- `src/java/org/apache/cassandra/utils/FBUtilities.java` (150-160)
- `src/java/org/apache/cassandra/cql3/statements/ModificationStatement.java` (365-378)
- `src/java/org/apache/cassandra/cql3/statements/SelectStatement.java` (725-735)
- `src/java/org/apache/cassandra/cql3/Validation.java` (45-58)
- `src/java/org/apache/cassandra/io/sstable/format/SortedTableWriter.java` (160-175)
- `conf/cassandra.yaml` (grep matches only)
- grep results for `MAX_UNSIGNED_SHORT` and `validateKey(` over `src/java`

## D. Stage-4 feedback

**2026-10-26, stage 4 run 1 (node pc07, no run 2): unit tier Confirmed - does not cap; cluster tier Confirmed - does not cap. Outcome class: true negative.** Results: `stage4-runtime-verification/results/max-unsigned-short-validate-key-remaining--autonomous.md`; harness: `stage4-runtime-verification/harness/max-unsigned-short-validate-key-remaining--autonomous/`. The estimate stands as filed.
- Unit: 65535-byte keys accepted and 65536 rejected with "Key length of L is longer than maximum of 65535" in both `QueryProcessor.validateKey` and `Validation.validateKey`; 100,000 distinct 65535-byte keys (6.55 x 10^9 key bytes) passed without a rejection; held keys retain L + 82 B each (slope ratio 728 against the 1-byte control).
- Cluster: all 10,000 writes at K = 65536 rejected with the exact text and nothing written; Data+Index bytes 2.0 x N x K at K = 32768 and 65535 (the key is in Data.db and Index.db); the memtable pool reached its limit at 507.4 MiB (512 MiB pools) and 127.6 MiB (128 MiB pools), ratio 3.98.
- Notes for stage 3: the unset-key branch (`QueryProcessor.java:255`) is unreachable for `UNSET_BYTE_BUFFER` (an empty buffer, `ByteBufferUtil.java:92`; the amendment B2i.2 first got this wrong and was corrected the same day); `tablestats` "Memtable data size" omits partition-key bytes. Amendments: B2i, B3i (2026-10-26).

Stage-4 audit amendments of 2026-10-26 are B2i and B3i above. Citation checks (pinned `cassandra-5.0.9`): lines 249-263 of `QueryProcessor.java`, 158 of `FBUtilities.java`, 372-374 and 781/802 of `ModificationStatement.java`, 730-732 of `SelectStatement.java`, 51-55 of `Validation.java`, 209 of `TriggerExecutor.java`, 169-172 of `SortedTableWriter.java`, 365 and 766 of `ByteBufferUtil.java`, 229 of `ByteArrayUtil.java` hold. Two notes: `conf/cassandra.yaml:1044` (`native_transport_max_frame_size`) and `:1864` (`max_value_size`) are commented-out defaults (16MiB, 256MiB); `CacheService.java:504` is a corrupted-key-cache read check, not a write-path backstop.
