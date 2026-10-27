# max_array_length-checkmaxleafnodecount-numleaves — verification solution  <!-- file: cases/max_array_length-checkmaxleafnodecount-numleaves--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`BlockBalancedTreeWriter.java:651`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/bbtree/BlockBalancedTreeWriter.java#L651) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: the check bounds `bytesPerValue * numLeaves` by the Java array limit, a ceiling about 2^31 bytes that is unreachable for any realistic SAI segment, so it does not cap the node's memory or disk in practice. |
| Ground | With `bytesPerValue` at most 24 (the largest fixed width, `IndexTermType.java:91`) and 1024 points per leaf (`BlockBalancedTreeWriter.java:96`), the check needs about 89 million leaves, i.e. about 9.2e10 points in ONE segment, before it fires. Real heap and disk use in this writer is set by the segment size (`segment_write_buffer_size` on the build path, memtable size on the flush path), not by this check. It is an overflow guard on a Java array index, not a resource budget. |

> **Link rule.** Declaration and if statement are linked below (A1, A3, Entry pointer).

## A. Constraint trace

**A1. The constraint.** Name: `ArrayUtil.MAX_ARRAY_LENGTH`. Kind: constant of the Lucene library (`org.apache.lucene.util.ArrayUtil`), imported at [`BlockBalancedTreeWriter.java:41`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/bbtree/BlockBalancedTreeWriter.java#L41). It is not declared in the Cassandra tree; the declaration is in the Lucene jar (lucene-core 9.7.0 per `.build/parent-pom-template.xml:1229-1231`). The jar is not in the checked-out tree, so the exact value and its derivation are not verified here (from general knowledge it is `Integer.MAX_VALUE` minus the array header size; not verified). Unit: bytes (compared against a byte count). Default: fixed by the jar. Not settable by yaml, `-D` or JMX; changing it means changing the Lucene dependency and restarting.
The check compares it to `bytesPerValue * (long) numLeaves`. Operands: `bytesPerValue` is a constructor argument (`BlockBalancedTreeWriter.java:104,113`), set by callers to `IndexTermType.fixedSizeOf()` (`IndexTermType.java:352-363`): the fixed width of the type, 20 for varint, 24 for decimal, 16 for inet and the default (`IndexTermType.java:91-94`). `numLeaves` is `leafBlockFilePointers.size()` (call at `BlockBalancedTreeWriter.java:568`). The only knob that changes the leaf count is `maxPointsInLeafNode`, default `DEFAULT_MAX_POINTS_IN_LEAF_NODE = 1024` (`BlockBalancedTreeWriter.java:96`), re-exported as `NumericIndexWriter.MAX_POINTS_IN_LEAF_NODE` (`NumericIndexWriter.java:49`). Both production call sites use the short constructor and so the default: `MemtableIndexWriter.java:179-181` and `SegmentBuilder.java:97`; `NumericIndexWriter.java:66-73` (the long constructor, marked `@VisibleForTesting`) has no `src/java` caller (grep over `src/java`). So `maxPointsInLeafNode` has no yaml key and needs a code change plus reindex. The constructor rejects `maxPointsInLeafNode <= 0` and `> ArrayUtil.MAX_ARRAY_LENGTH` (`BlockBalancedTreeWriter.java:106-110`), a separate use of the same constant.
The earlier trace's claim that the limit is "roughly Integer.MAX_VALUE minus the header" is plausible but not verified here. Its claim that `splitValues` is built at line 163 is imprecise: line 163 calls `writeBalancedTree`, and the array is allocated at line 173.

**A2. What it caps.** Heap (and, secondarily, tree-file size). The compared quantity is `bytesPerValue * numLeaves`, the byte length of the packed split-value array `splitValues`, allocated as `new byte[(1 + numInnerNodes) * bytesPerValue]` (`BlockBalancedTreeWriter.java:172-173`), an `int` expression that would overflow without this guard. The same product approximates the heap held by `leafBlockStartValues`, one `bytesPerValue`-byte copy per leaf after the first (`BlockBalancedTreeWriter.java:562-565`). It is a limit on one array, not on total heap.

**A3. Mechanism.**
1. `write` creates a `LeafWriter` (`BlockBalancedTreeWriter.java:147`) and feeds it every (term, rowId) pair (`:149-153`).
2. Each full leaf is flushed by `writeLeafBlock` (`:550`). It appends the leaf's first value to `leafBlockStartValues` (not for the first leaf, `:562-565`) and its file pointer to `leafBlockFilePointers` (`:567`).
3. It then calls `checkMaxLeafNodeCount(leafBlockFilePointers.size())` (`:568`).
4. The if statement: [`BlockBalancedTreeWriter.java:651`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/bbtree/BlockBalancedTreeWriter.java#L651). If true, it throws `IllegalStateException("too many nodes; increase maxPointsInLeafNode ... and reindex")` (`:653`), which aborts the segment write (flush or index build). If false, writing continues.
5. After the last leaf, `writeBalancedTree` allocates `splitValues` (`:172-173`) and `leafBlockFPs` (`:175`).
Bypass or overshoot: the check runs after the leaf's start value was already copied (`:565`), so at the throw the lists hold one entry beyond the allowed count. The check covers only `splitValues`; it does not bound `leafBlockStartValues` as a `List` of separate arrays (each has its own object header), `leafBlockFilePointers` (boxed `Long`s, no `bytesPerValue` factor), or the per-leaf buffers (`leafValues = maxPointsInLeafNode * bytesPerValue`, `:486`). The comment at `:85` says the writer can write at most `Integer.MAX_VALUE * maxPointsInLeafNode` points.
Reachability arithmetic (ignoring the header, which is small): leaves needed at width 24 is about 2^31/24, about 8.9e7; points about that times 1024, about 9.2e10 in a single segment. At width 16, about 1.3e8 leaves, 1.4e11 points. A segment of this size is far beyond what the segment buffer or a memtable holds (`StorageAttachedIndexOptions.java:27-35` caps the build buffer at 1024 MiB by default, 32768 MiB maximum; `V1OnDiskFormat.java:126`).

**A4. Other consumers.** Heap during a segment write: the `LeafWriter` buffers (`:486-494`), `leafBlockOutput` and `leafOrderIndexOutput` (`:490-491`), the per-leaf postings built by `NumericIndexWriter.LeafCallback` (`NumericIndexWriter.java:88-111`), and, on the build path, the trie buffer limited by `SEGMENT_BUILD_MEMORY_LIMITER` (`V1OnDiskFormat.java:126-128`; flush when `hasReachedMinimumFlushSize`, `SegmentBuilder.java:211-214`). On the flush path, memtable and its SAI memtable index are bounded by memtable settings, not by this check. Disk: the BALANCED_TREE component plus other index components.

**A5. Evidence beyond the source.** none (Lucene's `ArrayUtil` source and the jar were not read; see A1).

## B. Verification solution

**B1. Claim under test.** The check at `BlockBalancedTreeWriter.java:651` does not bound the heap or disk a node uses for numeric SAI writes: for every real numeric type (`bytesPerValue <= 24`) and the default leaf size it is never reached, while heap use follows the number of leaves and the segment buffer; it only fires when `bytesPerValue * numLeaves` is made to approach `ArrayUtil.MAX_ARRAY_LENGTH` artificially, and then it is an array-size guard. It would be refuted if the throw occurred in a normal workload, or if heap use of the writer stopped growing with leaf count at a level set by this limit.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (never build in the shared tree): `rsync -a /users/jason92/cassandra-5.0.9/ $WORK/c509/`, then `cd $WORK/c509 && ant jar`. Put a test class `LeafCountProbe` in package `org.apache.cassandra.index.sai.disk.v1.bbtree` (needed: `Callback` and `RowIDAndIndex` are package-private, `BlockBalancedTreeWriter.java:458,463`), compiled against `build/classes/main` and the jars in `build/lib/jars`. Run with `-Xmx6g -XX:+UseSerialGC -XX:+HeapDumpOnOutOfMemoryError`, heap dumps to local disk. Output goes to a discarding `IndexOutput` subclass (counts bytes, stores nothing) so no large file is written.

**B2b. Knobs.** (1) `bytesPerValue` B in {16, 24, 4096, 262144, 1048576}: the real widths and artificial large widths to reach the limit cheaply. (2) `maxPointsInLeafNode` M in {1, 1024}: set directly via the public constructor `BlockBalancedTreeWriter(B, M)` (`:104`). Large B with M=1 makes `numLeaves` equal the point count, so the limit is reachable with a few thousand points: leaves needed is L = ceil(LIMIT / B) + 1, where LIMIT is read at run time from `ArrayUtil.MAX_ARRAY_LENGTH` (for B = 1 MiB, about 2048 leaves).

**B2c. Workload.** A synthetic `Iterator<IndexEntry>` (`IndexEntry.create(ByteComparable, PostingList)`, `utils/IndexEntry.java:35`) producing terms of exactly B bytes in strictly increasing order, one row id each, plus a no-op `Callback`. Run A: B=24, M=1024, N = 50 million points (about 49 thousand leaves): shows the check far from firing. Run B: B=1048576, M=1, N = L points (about 2048): the check should fire at the L-th leaf. Run C: B=1048576, M=1, N = L-5: should complete. Heap in B/C is about N*B, about 2 GiB, hence `-Xmx6g`.

**B2d. Observables and instruments.** (1) Whether `IllegalStateException` with message "too many nodes" is thrown, and at which `leafBlockFilePointers.size()` (read via a debugger-free trick: count `IndexEntry` terms consumed by the iterator when the throw happens). (2) Heap: `Runtime.totalMemory()-freeMemory()` after `System.gc()` before and just before the throw / at the end, and a class histogram (`jcmd <pid> GC.class_histogram`) showing `byte[]` count about the leaf count. (3) Computed ratio `B * numLeaves / ArrayUtil.MAX_ARRAY_LENGTH`. Not observable directly: the allocation of `splitValues` (it happens only after the last leaf; use the histogram or a final `-Xlog:gc`).

**B2e. Procedure.**
1. Build and compile as in B2a.
2. Print `ArrayUtil.MAX_ARRAY_LENGTH` and compute the leaf counts for each B.
3. Run A, record heap after GC and the ratio; no throw expected.
4. Run C then B for B=1 MiB, M=1; record throw/no throw and the consumed count.
5. Positive-control run (next paragraph).
6. Repeat each run 3 times; one fresh JVM per run.
7. Cleanup per B4.

**B2f. Predictions** (stated before any run). Run A: no exception; the ratio B*numLeaves/LIMIT is about 5.5e-4 (49 thousand * 24 / 2.1e9, i.e. under 0.1%); heap after GC grows about linearly with the leaf count, tens of MB. Run C: completes, ratio just under 1. Run B: `IllegalStateException` "too many nodes" exactly when `B * numLeaves > LIMIT`, at leaf L (the first count with product above the limit). For B in {16, 24} with M=1024, extrapolating run A: the limit would need about 9.2e10 points (not run; arithmetic only). Claim wrong if run A throws, or if B throws at a leaf count not equal to the formula.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Run A completes, ratio below 0.1%, heap grows with leaf count | Claim confirmed for real widths: the check is not reached at real sizes |
| Run B throws at the formula's leaf; run C completes | Mechanism is as traced (an array-size guard); it only binds at artificial widths |
| Run A throws | Claim refuted |
| Throw at a count different from the formula | A1/A3 wrong; re-trace |
| Heap at the throw about equal to LIMIT-scale and not lower | The check does bound the heap of `leafBlockStartValues`, only at the artificial scale |
| Positive control moves while the check's operand stays far below the limit | Usage is governed by other limits, claim confirmed |
| Neither run B throws nor the control moves (limit never reached, control flat) | Not confirmed; redo with other sizes |

**B2h. Controls.** Positive control: a limit known to bind in the same writer path, `maxPointsInLeafNode > ArrayUtil.MAX_ARRAY_LENGTH` (rejected by the constructor, `:108-110`), and the same N run with M=1024 vs M=1: leaf count and heap (`byte[]` count) scale by about 1024 between them, showing the workload does move usage when the leaf geometry changes. Controls on other explanations: fresh JVM per run, fixed heap, serial GC, same iterator for all runs, discarding output so disk does not intervene.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, built from the local copy (B2a). Local disk of known size (at least 20 GB free) for data, commit log and hints (`data_file_directories`, `commitlog_directory`, `hints_directory` under `$WORK/node1`). `cassandra.yaml`: `sai_options: segment_write_buffer_size: 1024MiB` (default, `StorageAttachedIndexOptions.java:27`; key per field name at `:35`; not verified against the shipped yaml), `memtable_allocation_type: offheap_objects` off (keep heap), `-Xms4g -Xmx4g` in `jvm11-server.options`, `-XX:+UseG1GC`.

**B3b. Knobs.** (1) Row count in the indexed table: 5M, 20M, 40M rows, one numeric (bigint, 8 bytes; `fixedSizeOf` returns the fixed length) and one decimal column (24 bytes) with SAI indexes. The leaf geometry `maxPointsInLeafNode` is not settable at runtime (A1). (2) Positive control knob: `segment_write_buffer_size` of 32MiB vs 1024MiB (restart), which binds on the index-build path (`SegmentBuilder.java:211-214`).

**B3c. Workload.** Create keyspace/table with `CREATE CUSTOM INDEX ... USING 'StorageAttachedIndex'` on both columns, then load rows with `cassandra-stress` or CQL batches (unique, growing numeric values so each leaf is full), flush (`nodetool flush`), then force an index build over existing sstables (`nodetool rebuild_index`) to use the segment-builder path. Leaves per segment = rows/1024 (e.g. 40M rows gives about 39 thousand leaves; the check threshold needs about 89 million). Duration: load plus flush plus rebuild, tens of minutes.

**B3d. Observables and instruments.** Heap used after GC (`jcmd <pid> GC.heap_info`, `-Xlog:gc*` file), sampled every 5 s during flush and rebuild; peak via GC log. Disk: `du -sb` of the index components (`*_BalancedTree*`) and of the data dir. Metrics: SAI `SegmentBufferSpaceUsedBytes` / `SegmentBufferSpaceLimitBytes` (`V1OnDiskFormat.java:133,136`) via JMX. Log search for "too many nodes" in `system.log`. Not observable directly: `splitValues` size (a few hundred KB at these sizes).

**B3e. Procedure.**
1. Build, prepare `$WORK/node1` with local directories, start one node, record the PID.
2. Create schema and indexes; load 5M rows; `nodetool flush`; `nodetool rebuild_index`; record heap samples, log grep, BalancedTree sizes.
3. Repeat at 20M and 40M (fresh data dir each).
4. Positive control: restart with `segment_write_buffer_size: 32MiB`, repeat the 20M run, record segment count (per-index segment metadata via `nodetool` / component listing) and peak heap.
5. `nodetool drain`, stop the node, check no `CassandraDaemon` process is left, delete `$WORK/node1`.

**B3f. Predictions.** At all three row counts: no "too many nodes" in the log (the operand is under 0.1% of the limit); BalancedTree file size and writer heap grow about linearly with rows; the heap contribution of the split-value structures is a small fraction of the segment buffer. Control: with 32MiB, more segments are written and peak build-path heap is lower than with 1024MiB, showing a cap that binds. Claim wrong if the log shows "too many nodes", or if heap and file size plateau with rows at a level that does not move with the buffer.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| No "too many nodes" at any row count; sizes grow with rows | Claim confirmed: the check does not bound real usage |
| "too many nodes" appears | Claim refuted |
| 32MiB control gives more segments / lower peak heap while runs show no throw | Usage follows the buffer, not this check; claim confirmed |
| Control does not change segment count or heap | Control did not move; not confirmed (wrong path exercised or buffer not reached) |
| Plateau in heap or file size unrelated to the buffer | Another limit binds; investigate |

**B3h. Controls.** Same data and workload for each run; fresh data dir; same heap; the buffer-size control above; a second table with only a numeric (8-byte) column to separate widths; GC log to separate writer heap from memtable heap (flush path, `MemtableIndexWriter.java:176-181`).

**B4. Risks and cleanup.** Unit tier: runs with up to about 6 GB heap; use a discarding output so no large file is written; heap dumps only on OOM, on local disk; delete `$WORK/c509` classes and dumps afterwards; confirm no leftover `java` process (`pgrep -u $USER -f LeafCountProbe`). Cluster tier: up to roughly 20 GB of local disk; data, commit log and hints only on local disk of known size, never on shared storage; stop the node and check `pgrep -u $USER -f CassandraDaemon` returns nothing; remove `$WORK/node1`. Never build in or write to the shared source tree.

## C. Sources read

- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/INSTRUCTIONS.md
- .../agent-docs/playbook-autonomous.md
- .../agent-docs/_TEMPLATE-autonomous.md
- .../agent-in/92.md
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/bbtree/BlockBalancedTreeWriter.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/bbtree/NumericIndexWriter.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/MemtableIndexWriter.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentBuilder.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/V1OnDiskFormat.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/utils/IndexTermType.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/utils/IndexEntry.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/StorageAttachedIndexOptions.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java (line 5264-5266)
- /users/jason92/cassandra-5.0.9/.build/parent-pom-template.xml (lucene version)

## D. Stage-4 feedback

`none yet`
