# max_points_in_leaf_node — verification solution  <!-- file: cases/max_points_in_leaf_node-add-leafvaluecount--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`BlockBalancedTreeWriter.java:528`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/bbtree/BlockBalancedTreeWriter.java#L528) (`if (leafValueCount == maxPointsInLeafNode)` in `LeafWriter.add`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: the constant only sizes four small per-writer scratch arrays and the leaf-flush cadence; the memory and disk a flush uses grow with the number of rows (per-leaf posting lists, tree and postings files), not with a bound set by this constant. |
| Ground | The limit is a fixed-size scratch buffer (about 1024 entries of `bytesPerValue`, 8 B row id, an int, and an object each), reused for every leaf (`BlockBalancedTreeWriter.java:486-489`, `:528-532`). Reaching it flushes the leaf to the output stream and starts a new one; it does not refuse or evict anything. Total heap during a flush is dominated by structures that grow per leaf (`NumericIndexWriter.LeafCallback.leafPostings`, `NumericIndexWriter.java:82-101`) and total disk by the number of values, so neither is capped by it. Its memory effect is a per-writer constant of tens of KB, which is not memory- or disk-significant. |

> **Link rule.** Declaration and if statement are links (below); other citations are plain `file:line` in the pinned tree.

## A. Constraint trace

**A1. The constraint.** `DEFAULT_MAX_POINTS_IN_LEAF_NODE` (instance field `maxPointsInLeafNode`). Kind: hard-coded constant, not a yaml key, not a JVM property, not JMX. Declared at [`BlockBalancedTreeWriter.java:96`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/bbtree/BlockBalancedTreeWriter.java#L96) (`public static final int DEFAULT_MAX_POINTS_IN_LEAF_NODE = 1024;`). Unit: values (points) per leaf block. Default: the literal 1024, derived from nothing. Chain, all verified: re-exported as `NumericIndexWriter.MAX_POINTS_IN_LEAF_NODE` (`NumericIndexWriter.java:49`); the 3-argument `NumericIndexWriter` constructor passes it on (`NumericIndexWriter.java:61`); the 4-argument constructor, marked `@VisibleForTesting` (`NumericIndexWriter.java:64-68`), takes any value and builds the `BlockBalancedTreeWriter` (`NumericIndexWriter.java:73`). The writer constructor rejects `<= 0` and `> ArrayUtil.MAX_ARRAY_LENGTH` (`BlockBalancedTreeWriter.java:106-110`) and stores the value at `:112`. Both production callers use the 3-argument constructor (`MemtableIndexWriter.java:178-181`, `SegmentBuilder.java:97`), so production always uses 1024. Not settable by operators; changing it needs a source edit, rebuild and restart. The earlier trace's claims all hold. (The tests that use the 4-argument constructor are `NumericIndexWriterTest`, `BlockBalancedTreeTest`, `BlockBalancedTreeReaderTest`, `BlockBalancedTreeIndexBuilder` under `test/unit/org/apache/cassandra/index/sai/disk/v1/bbtree/`.)

**A2. What it caps.** Nominally off-heap-neutral: it is on-heap, per writer. The quantity compared is `leafValueCount`, the number of values buffered in the current leaf (`BlockBalancedTreeWriter.java:497`). It bounds the leaf scratch arrays, `leafValues` = `maxPointsInLeafNode * bytesPerValue` bytes, `leafRowIDs` (long[]), `rowIDAndIndexes` (`RowIDAndIndex[]`, each element pre-allocated in the `LeafWriter` constructor at `:505-508`) and `orderIndex` (int[]) (`:486-489`). For a 4-byte numeric type that is roughly 4 KB + 8 KB + 4 KB + about 1024 small objects per writer, by arithmetic from the declarations, not a measurement. It does not bound the output size.

**A3. Mechanism.**
1. `BlockBalancedTreeWriter.write` creates one `LeafWriter` (`:147`; array allocation at `:486-489`) and feeds each (term, row id) pair to `add` (`:149-155`).
2. `add` copies the value into `leafValues` at `leafValueCount * bytesPerValue` and the row id into `leafRowIDs`, then increments the count (`:524-526`).
3. The check: [`if (leafValueCount == maxPointsInLeafNode)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/bbtree/BlockBalancedTreeWriter.java#L528). True: `writeLeafBlock()` (`:530`) then `leafValueCount = 0` (`:532`). False: keep buffering.
4. `writeLeafBlock` (`:551` onward) records the leaf file pointer and start value in two growing lists (`:565-567`), calls `checkMaxLeafNodeCount` (`:568`; throws `IllegalStateException` if `bytesPerValue * numLeaves > ArrayUtil.MAX_ARRAY_LENGTH`, `:651-654`), sorts by row id, writes the leaf to `treeOutput` (`:582-646`), and hands the leaf's row ids to `callback.writeLeafPostings` (`:630`). In `NumericIndexWriter` that callback builds a `PackedLongValues` per leaf and appends it to `leafPostings`, an `ArrayList` kept for the whole segment (`NumericIndexWriter.java:82-101`).
5. `finish` flushes a final partial leaf (`:543-549`). `writeBalancedTree` then writes `countPerLeaf` and the inner-node index (`:163`, `:170-190`).
Outcomes: reaching the limit never rejects data; it triggers a leaf write. There is no overshoot of the buffer (it is flushed at exactly the max, per the comment at `:530`). Bypass: none for the buffer; the lists `leafBlockFilePointers`, `leafBlockStartValues` and `leafPostings` grow with the number of leaves, i.e. with `values / maxPointsInLeafNode`, and are uncapped except by the `checkMaxLeafNodeCount` array-length error.


The check itself is the if statement at [`BlockBalancedTreeWriter.java:528`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/bbtree/BlockBalancedTreeWriter.java#L528).

**A4. Other consumers.** Memory around the same flush: the segment's in-memory term buffer for the compaction/flush path, which is bounded by the SAI segment write buffer limiter (`SegmentBuilder.java:54`, `:143-149`; `segment_write_buffer_size` in `StorageAttachedIndexOptions.java:35`, default comment at `conf/cassandra.yaml:1794`), the memtable index for the memtable flush path (`MemtableIndexWriter.java:176-181`), `leafOrderIndexOutput` and `leafBlockOutput` (`BlockBalancedTreeWriter.java:491-492`), the per-leaf `PackedLongValues` list above, and the postings writer built after the tree (`NumericIndexWriter.java:136-154`). Disk: the BALANCED_TREE and POSTING_LISTS components (`NumericIndexWriter.java:113-154`) grow with value count regardless of this constant.

**A5. Evidence beyond the source.** None. (Class comment at `BlockBalancedTreeWriter.java:55-57` describes the constant as the maximum points per leaf; it is a data-structure parameter in the Lucene BKD lineage, `@see BKDWriter` at `:87`.)

## B. Verification solution

**B1. Claim under test.** Changing `maxPointsInLeafNode` (default 1024) changes only the fixed per-writer scratch arrays and the leaf count; the heap used by one numeric-index flush and the bytes written still scale with the number of rows, and no value of the constant caps either. Falsified if peak flush heap or output size stays bounded as rows grow at a fixed constant, or if peak heap tracks the constant rather than the row count.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a /users/jason92/cassandra-5.0.9/ $WORK/c509/`), never build in the shared tree. `ant jar` in the copy (`ant build-test` for test classes). Drive the writer from a small JUnit-style class placed beside `NumericIndexWriterTest` in the copy, modelled on how that test builds a `NumericIndexWriter` with the 4-argument constructor (not reproduced here). JVM options: `-Xmx512m -XX:+UseSerialGC -Xlog:gc*:file=$WORK/gc.log` so allocation is predictable.

**B2b. Knobs.** `maxPointsInLeafNode` passed to the 4-argument constructor: 16, 128, 1024 (production), 8192, 65536. Row count N: 1e5, 1e6, 4e6. `bytesPerValue` fixed at 4 (int) then 16 (a larger fixed-size type) to show the scratch size scales with it.

**B2c. Workload.** Feed `NumericIndexWriter.writeCompleteSegment` a sorted `Iterator<IndexEntry>` of N distinct int terms, each with one row id (strictly increasing), through a temporary `IndexDescriptor` on local disk. Leaf count = ceil(N / maxPointsInLeafNode): at the defaults N=1e6 gives 977 leaves, N=4e6 gives 3907. The limit is reached on every full leaf by construction.

**B2d. Observables and instruments.** (1) Number of leaf writes: wrap the `Callback` or read `num_leaves` from the returned component attributes (`NumericIndexWriter.java:128`, key `num_leaves`) and `max_points_in_leaf_node`. (2) Allocated heap per flush: `ThreadMXBean.getThreadAllocatedBytes` (com.sun.management) before and after; retained size of the `LeafWriter` arrays via `jcmd <pid> GC.class_histogram` taken after a forced `System.gc()` while the writer is live (the arrays are visible as `long[]`, `int[]`, `byte[]`, `RowIDAndIndex`). (3) Output bytes: `treeLength` and postings lengths (the `ComponentMetadataMap`) and file sizes. Not observable directly: the transient `LeafWriter` is private, so its retained size is read from the histogram, not the object.

**B2e. Procedure.**
1. Build the copy; write the driver class; compile with `ant build-test`.
2. For each (maxPointsInLeafNode, N, bytesPerValue): fresh JVM, run `writeCompleteSegment`, record allocated bytes, `num_leaves`, tree and postings sizes.
3. Repeat the 1024 / 1e6 case three times to estimate noise.
4. Positive control run (step in B2h) after the main grid.

**B2f. Predictions (before any run).** (a) `num_leaves` equals ceil(N/maxPointsInLeafNode) for every cell. (b) The fixed scratch (live `LeafWriter` arrays) grows linearly with `maxPointsInLeafNode` and `bytesPerValue` and does not depend on N. (c) Total allocated bytes for a flush grow with N at every constant, and at a fixed N change only slightly (a few percent: fewer, larger leaves versus more, smaller leaf lists) while the constant moves 16 → 65536 (4096 times). (d) Tree and postings file sizes grow about linearly with N at every constant. Claim wrong if allocated bytes or file size is flat in N, or if they scale with the constant roughly proportionally.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Allocated bytes and file sizes grow with N at fixed constant; scratch-array size grows with constant, N-independent; total at fixed N nearly flat across the constant | Claim confirmed: the constant sizes scratch only; usage follows rows |
| Peak/allocated bytes at fixed N scale roughly with the constant | Claim refuted: usage follows the constant |
| Allocation or output size stays bounded as N grows at fixed constant | Claim refuted: something caps usage |
| `num_leaves` does not equal ceil(N/constant) | Mechanism traced wrongly (A3 wrong); re-trace |
| Positive-control quantity does not move with its knob | Not confirmed: the harness cannot see a cap that binds |
| The limit never reached (N < constant) | Not confirmed for that cell; use larger N |

**B2h. Controls.** Positive control: the SAI segment write-buffer limiter that does bind at the term buffer, or more simply an unrelated array whose size is the knob (`new long[k]` allocated by the same harness at k = 1e3, 1e6): the harness must show allocated bytes rise with k. Also: run with N = 0 (no leaf written, `treeFilePointer` is -1 at `:159`) to get the fixed baseline; run `System.gc()` before each measurement; fix the JIT state by one warm-up run discarded.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, local-disk copy of the tag, `ant jar`. Because the constant cannot be set by configuration, build three variants from three copies where `BlockBalancedTreeWriter.java:96` is edited to 128, 1024 (unmodified control), and 16384, and run each variant against an identical empty data directory on local disk of known size (say 20 GiB free). `cassandra.yaml`: `sai_options.segment_write_buffer_size` left at its default, `data_file_directories`, `commitlog_directory`, `hints_directory` and `saved_caches_directory` on local disk. JVM: `-Xms2g -Xmx2g`, `-XX:+UseG1GC`, `-Xlog:gc*:file=$WORK/gc.log`, `-XX:NativeMemoryTracking=summary`, `-XX:+HeapDumpOnOutOfMemoryError` to local disk.

**B3b. Knobs.** The constant (128 / 1024 / 16384, by variant); row count per table (2e6, 8e6); column type `int` (fixed size, so it takes the numeric writer; `fixedSizeOf` at `MemtableIndexWriter.java:178-181`) with high cardinality so every row is a distinct term. Positive control knob: `segment_write_buffer_size` (yaml key, restart required) at 16MiB versus 1024MiB, since that limiter does bind the SAI segment builder (`SegmentBuilder.java:143-149`).

**B3c. Workload.** `CREATE TABLE ks.t (id bigint PRIMARY KEY, v int); CREATE CUSTOM INDEX ON ks.t(v) USING 'StorageAttachedIndex';` Insert N rows with random `v` through `cqlsh`/driver or `cassandra-stress` (user mode, int column unique per row), then `nodetool flush ks t` (memtable path, `MemtableIndexWriter`) and, separately, drop and rebuild the index on existing sstables with `nodetool rebuild_index ks t t_v_idx` (builder path, `SegmentBuilder`) so both callers of the constant are exercised. N=8e6 at 1024 gives 7813 leaves per segment, so the leaf-flush branch executes thousands of times per run.

**B3d. Observables and instruments.** Heap during the flush: GC log live-set after the flush and peak pause-time occupancy; `jcmd <pid> GC.class_histogram` (sampled at 1 s during the flush) for `PackedLongValues`, `RowIDAndIndex`, `long[]`, `byte[]`; `nodetool info` heap line. Disk: `du -sb` of the sstable directory's `*SAI*BalancedTree*` and `*Postings*` components. Flush wall time. Not observable: the private scratch in one writer is too small to see against a 2 GiB heap; it is inferred from the histogram deltas between variants.

**B3e. Procedure.**
1. Build variants A (128), B (1024), C (16384) in separate local copies.
2. For each variant: wipe the data directory, start the node, create schema, insert N=2e6, flush, record B3d; then N=8e6, record again. Run `rebuild_index`, record.
3. Stop the node (`nodetool drain`, kill), confirm no `java` process of this run remains (`pgrep -f CassandraDaemon`).
4. Positive control: unmodified variant B with `segment_write_buffer_size` 16MiB then 1024MiB; same N=8e6 bulk load without flushing until the builder path (index build) runs; record the heap held by the segment builder.

**B3f. Predictions (before any run).** Component sizes on disk are about linear in N and nearly the same across the three variants (differences from leaf headers and prefix compression only). Peak heap during flush at fixed N differs across variants by far less than the 128-fold spread of the constant. Heap and disk both go up from N=2e6 to 8e6 in every variant. In the control, peak builder heap and the number of segments change with `segment_write_buffer_size` as the limiter predicts. Claim wrong if disk or heap at fixed N is flat in N, or tracks the constant in proportion.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Disk and heap grow with N; across variants at fixed N they are nearly equal | Claim confirmed (negative): usage does not follow the constant |
| Usage at fixed N rises or falls roughly in proportion to the constant | Claim refuted: usage follows the constant |
| Usage flat while N quadruples in every variant | Claim refuted: something else caps it |
| Control (`segment_write_buffer_size`) moves segment/heap behavior as expected while the constant does not | Claim confirmed, and the harness can see a cap that binds |
| Control does not move | Not confirmed: the harness cannot show a binding cap |
| Heap too noisy to separate variants (differences inside run-to-run spread) | Not confirmed; repeat 3 times, or use allocation profiling instead |
| Flush errors with "too many nodes; increase maxPointsInLeafNode" | Variant with too small a constant hit `BlockBalancedTreeWriter.java:651-654`; record leaf count at the failure |

**B3h. Controls.** Variant B is an unmodified-source baseline; same data seed, same JVM flags, same N across variants; run each cell three times; GC log taken after a forced full GC (`jcmd GC.run`) so retained heap is compared, not garbage; page cache dropped is not needed for heap or `du` readings.

**B4. Risks and cleanup.** Disk: each variant's data at N=8e6 is on the order of a few GiB at most (inferred from row count and index overhead, not measured); keep the data, commit log and hints on local disk of known size and delete between variants. Never build in or write to the shared source tree. Shared storage: nothing is written there. Processes: stop Cassandra (`nodetool drain` then kill), the stress client and the unit-tier JVMs; verify with `pgrep -f 'CassandraDaemon|cassandra-stress'` and `jcmd -l`. Cleanup: remove `$WORK` copies, data directories, heap dumps and GC logs. The edits to `BlockBalancedTreeWriter.java:96` exist only in throwaway copies.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/bbtree/BlockBalancedTreeWriter.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/bbtree/NumericIndexWriter.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/MemtableIndexWriter.java (lines 170-185)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentBuilder.java (lines 41-100)
- Grep results over /users/jason92/cassandra-5.0.9/src, `conf/cassandra.yaml` and `test/` for the constant, `segment_write_buffer_size` and constructor users (file names listed in A1/A4)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/StorageAttachedIndexOptions.java (by grep only)

## D. Stage-4 feedback

`none yet`
