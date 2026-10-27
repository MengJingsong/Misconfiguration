<!-- file: cases/none-validatekey-key_remaining--autonomous.md -->
# none (hard-coded FBUtilities.MAX_UNSIGNED_SHORT key-length bound) — verification solution  <!-- file: cases/none-validatekey-key_remaining--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`Validation.java:47`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/Validation.java#L47) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: the target line is an emptiness check against the literal 0 with no configurable constraint; the only nearby size bound (65535 bytes on one partition key) is a serialization-format limit that does not bound memory or disk use of a node. |
| Ground | Line 47 compares `key.remaining()` with 0, which is a sanity check. The adjacent bound at line 51 limits a single key to 65535 bytes (a fixed wire-format limit), but it does not limit the number of keys, rows or partitions, so heap, off-heap and disk usage grow with the data written and are governed by other mechanisms (memtable space, flush, compaction), not by this check. |

## A. Constraint trace

**A1. The constraint.** There is no configurable constraint at the target line. [`Validation.java:47`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/Validation.java#L47) is `if (key == null || key.remaining() == 0)` inside `validateKey(TableMetadata, ByteBuffer)` (Validation.java:45); it throws `InvalidRequestException("Key may not be empty")` (Validation.java:48). It compares against the literal 0; no configuration entry, JVM property or runtime-queried limit is involved. The nearest size-related bound is the next check, `key.remaining() > FBUtilities.MAX_UNSIGNED_SHORT` (Validation.java:51), whose constant is declared at [`FBUtilities.java:158`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/FBUtilities.java#L158) as `public static final int MAX_UNSIGNED_SHORT = 0xFFFF`. Kind: compile-time constant. Unit: bytes (65535). Default derivation: literal. It cannot be set by yaml, `-D` or JMX; changing it needs a code change and rebuild. The comment at Validation.java:50 states the reason: the key must be serializable by `ByteArrayUtil.writeWithShortLength` and `ByteBufferUtil.writeWithShortLength` (a 2-byte length prefix). The earlier trace was checked against the source and holds.

**A2. What it caps.** Nothing memory- or disk-significant. The quantity compared is the length in bytes of one serialized partition key (`key.remaining()`). The 65535 bound limits one key, so at most about 64 KiB of key per partition; it does not limit the number of partitions, rows, or the total bytes written.

**A3. Mechanism.** Step by step, in the pinned tree:
1. `ModificationStatement` calls `Validation.validateKey(metadata(), key)` for each key in the slice-delete path (ModificationStatement.java:781) and the clustering path (ModificationStatement.java:802).
2. The if statement: [`Validation.java:47`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/Validation.java#L47) rejects a null or zero-length key (throw at Validation.java:48).
3. Validation.java:51 rejects a key longer than 65535 bytes (throw at Validation.java:53-55).
4. Validation.java:57-63 runs `metadata.partitionKeyType.validate(key)` and rewraps a `MarshalException` as `InvalidRequestException`.
Outcomes: any rejection fails the one statement with `InvalidRequestException` before a mutation is built; otherwise execution continues with `decorateKey` (ModificationStatement.java:782, 803). There is no throttling, eviction or backpressure.
Bypass/overshoot: SELECT and the trigger path use a separate copy, `QueryProcessor.validateKey(ByteBuffer)` (QueryProcessor.java:249; callers SelectStatement.java:732, ModificationStatement.java:374, TriggerExecutor.java:209), which also checks the 65535 bound and additionally rejects the unset buffer. Writes arriving by other routes (internode, hints, commit log replay) are not checked at this line (not verified for each route).

**A4. Other consumers.** Memory and disk are governed elsewhere: memtable heap/off-heap space, commit log size, `max_mutation_size` (Config.java:406-407, read via DatabaseDescriptor.java:2827), native transport frame/message sizes (Config.java:285, 288), and compaction/SSTables for disk. All of these apply to the same writes independent of this check.

**A5. Evidence beyond the source.** none.

## B. Verification solution

**B1. Claim under test.** Memory and disk usage of a node do not follow the key-length check at Validation.java:47/51: the check only rejects empty keys and keys longer than 65535 bytes, and total heap, off-heap and disk use scale with the volume of data written (and with the real caps such as memtable space), not with this bound. Falsified if usage plateaus or writes are rejected because of this check when total key volume is large but each key is within the bound.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant, a copy of the tag on local disk (`rsync -a` to a scratch dir; never build in the shared tree). Build with `ant jar`. Test source: a new JUnit class in the copy under `test/unit/org/apache/cassandra/cql3/` (e.g. `ValidationKeyLengthTest`), run with `ant testsome -Dtest.name=org.apache.cassandra.cql3.ValidationKeyLengthTest`. JVM options: default test options plus `-Xmx512m`.

**B2b. Knobs.** The bound is not settable, so the varied value is the key length: 0, 1, 1024, 65535, 65536, 131072 bytes (boundary at 65535/65536). Set by allocating `ByteBuffer.allocate(n)`. Table: `TableMetadata.builder("ks","t").addPartitionKeyColumn("k", BytesType.instance)...build()`.

**B2c. Workload.** Call `Validation.validateKey(metadata, key)` once per length above. For the volume test, call it in a loop 100000 times with a 65535-byte key (6.5 GB of nominal key bytes if all were retained, but the loop reuses one buffer so nothing accumulates) to show that the check admits unbounded total volume. Arithmetic: 100000 x 65535 B = 6,553,500,000 B, far more than -Xmx512m, which could not be held, yet the check keeps accepting.

**B2d. Observables and instruments.** Whether `InvalidRequestException` is thrown and its message; heap used after a GC (`Runtime.totalMemory()-freeMemory()` after `System.gc()`), sampled before and after the loop. Cannot observe: node-level memtable or disk use (cluster tier).

**B2e. Procedure.**
1. Copy the tree: `rsync -a /users/jason92/cassandra-5.0.9/ $SCRATCH/c/`.
2. Write the test; for each length, record accept or reject and message.
3. Run the 100000-call loop; record post-GC heap before and after.
4. Positive control: build a `Mutation` whose size exceeds `max_mutation_size` and call `validateSize` (IMutation.java:49-54 describes it); record that it rejects, showing a real cap binding.
5. Run with `ant testsome`; clean `$SCRATCH`.

**B2f. Predictions.** Length 0: rejected with "Key may not be empty". Lengths 1, 1024, 65535: accepted. Lengths 65536 and 131072: rejected with "Key length of N is longer than maximum of 65535". Loop: all 100000 calls accepted; post-GC heap after is within noise of before (does not grow with call count). Control: oversized mutation rejected.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Accept/reject exactly as in B2f and heap flat across the loop | Claim confirmed: the check is a per-key length filter that does not bound accumulated usage |
| Heap after loop grows with the number of calls | Claim refuted (usage follows the check) or the test retained buffers by mistake; investigate |
| Loop calls start rejecting after some count | Claim refuted: a cumulative bound exists |
| Control mutation not rejected, or lengths below 65535 rejected | Not confirmed; the setup is wrong (wrong metadata, wrong limit) |

**B2h. Controls.** The positive control in B2e step 4 (max_mutation_size binds); a second table with a different partition key type (e.g. `UTF8Type`) to show the type validation at Validation.java:57 is not what rejects the long key.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, built from a local copy of the tag with `ant jar`. Data, commit log and hints directories on a local disk of known size (at least 20 GiB free); heap `-Xms2G -Xmx2G`. Default `cassandra.yaml` except `memtable_heap_space` and `memtable_offheap_space` as in B3b.

**B3b. Knobs.** The key-length bound is not settable. Vary the written key length instead: 1 KiB, 32 KiB, 65535 B (all accepted), and 65536 B (rejected). Control knob: `memtable_heap_space` (a real cap), e.g. 256MiB vs 1024MiB, set in the yaml with a restart.

**B3c. Workload.** A table `ks.t (k blob PRIMARY KEY, v int)`. Using a driver or `cqlsh` with a script, insert N = 20000 distinct partitions per key size (using a counter prefix to keep keys distinct). Nominal key data: 20000 x 65535 B = 1.31 GB, above the 256MiB memtable cap, so flushes occur. Duration: until inserts finish plus 5 minutes of idle for flush and compaction. Also send one insert with a 65536-byte key.

**B3d. Observables and instruments.** `nodetool info` (heap, off-heap), `nodetool tablestats ks.t` (memtable data size, SSTable space used), `du -sb` of the data directory, `jstat -gc` every 10 s, and the client error for the 65536 key. Cannot observe directly: per-key accounting inside the memtable.

**B3e. Procedure.**
1. Build and start the node with the yaml above; record baseline heap and disk.
2. For each key size, run the inserts, sampling at 10 s intervals; run `nodetool flush` at the end.
3. Send the 65536-byte key insert; record the error text.
4. Repeat the 65535-byte run with `memtable_heap_space` at 256MiB and 1024MiB (control).
5. Stop the node (`nodetool drain`, then kill the process), verify with `pgrep -f CassandraDaemon`, and delete the data directories.

**B3f. Predictions.** Inserts with keys up to 65535 B succeed; the 65536 B insert fails with "Key length of 65536 is longer than maximum of 65535". Disk used and memtable data size scale roughly with total key bytes written (larger keys give larger totals for equal N) and are not capped at 65535 B per anything beyond the single-key limit. Control: peak memtable heap tracks `memtable_heap_space` (flushes sooner at 256MiB), while the key-length bound plays no role in that difference.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Disk and memtable size grow with total key bytes, bound never reached by volume, only the 65536 B key rejected | Claim confirmed: the check does not cap usage |
| Total usage plateaus near a value derived from 65535 independent of the memtable setting | Claim refuted |
| Control: peak memtable heap changes with `memtable_heap_space` while key-size runs scale with data | Claim confirmed, control worked |
| Control peak does not move, or writes with <= 65535 B keys fail | Not confirmed; setup problem (flush behavior, wrong yaml key) |

**B3h. Controls.** Same workload at two `memtable_heap_space` values (positive control for a binding cap); a run with small 100 B keys and the same row count to separate key size from row count; an empty-key insert (`k = 0x`) to show the line-47 rejection is independent of volume.

**B4. Risks and cleanup.** Unit tier: tests allocate up to a few MiB buffers; scratch copy on local disk; delete it afterwards. Cluster tier: about 1.3 GB nominal per run plus compaction overhead, so keep 20 GiB free on local disk; never use shared storage; stop the node, confirm with `pgrep -f CassandraDaemon` that nothing remains, and remove data, commitlog, hints and saved_caches directories.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/Validation.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/FBUtilities.java (line 158)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/ModificationStatement.java (lines 770-806)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryProcessor.java (lines 245-262)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java (grep only: lines 285, 288, 406-407)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/IMutation.java and DatabaseDescriptor.java (grep only)

## D. Stage-4 feedback

`none yet`
