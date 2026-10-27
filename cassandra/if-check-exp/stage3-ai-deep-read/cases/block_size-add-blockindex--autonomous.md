# block_size (SAI block-packed writer buffer) — verification solution  <!-- file: cases/block_size-add-blockindex--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`AbstractBlockPackedWriter.java:62`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/bitpack/AbstractBlockPackedWriter.java#L62) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: the line is a buffer-full check on a fixed-size `long[]` whose length is a hard-coded constant; it flushes to disk and does not cap node memory or disk. |
| Ground | The check bounds only a small per-writer scratch array (128 or 16384 longs). The constants are not configurable and are not a limit on anything that grows with data: the array never grows, it is flushed and reused. Memory and disk used by SAI writing are governed by other things (index segment buffer, number of rows). The one thing that does grow, the block metadata buffer, grows with row count and is not bounded by `blockSize`. |

> **Link rule.** Followed: declaration (A1) and if statement (Entry pointer, A3) are permalinks at `cassandra-5.0.9`.

## A. Constraint trace

**A1. The constraint.** The target line is not a limit check against a configured value. It is `if (blockIndex == blockValues.length)` in `AbstractBlockPackedWriter.add` ([`AbstractBlockPackedWriter.java:62`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/bitpack/AbstractBlockPackedWriter.java#L62)). The nearest "constraint" is the block size, kind: compile-time constant (not a yaml key, `-D` property or JMX value).
- Validity bounds: `MIN_BLOCK_SIZE = 64` ([`AbstractBlockPackedWriter.java:34`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/bitpack/AbstractBlockPackedWriter.java#L34)) and `MAX_BLOCK_SIZE = 1 << (30 - 3)` ([`AbstractBlockPackedWriter.java:35`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/bitpack/AbstractBlockPackedWriter.java#L35)), i.e. 134,217,728 elements, enforced by `checkBlockSize` at AbstractBlockPackedWriter.java:49, implemented at SAICodecUtils.java:127-139 (power of two within range, else `IllegalArgumentException`).
- Actual values, where first declared: `MONOTONIC_BLOCK_SIZE = 16384` ([`NumericValuesWriter.java:34`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/bitpack/NumericValuesWriter.java#L34)) and `BLOCK_SIZE = 128` ([`NumericValuesWriter.java:35`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/bitpack/NumericValuesWriter.java#L35)), chosen at NumericValuesWriter.java:49 (`monotonic ? MONOTONIC_BLOCK_SIZE : BLOCK_SIZE`).
- Unit: number of `long` elements (8 bytes each): 1 KiB and 128 KiB of heap per writer.
- Default derivation: fixed literals. Setting: only by source change; takes effect on rebuild and restart. A 5-argument public constructor accepts a size (NumericValuesWriter.java:52-57), but in `src/java` the only callers use the 4-argument form (SSTableComponentsWriter.java:58, 59, 60, 62, 72). The prior trace's lines for these were checked and hold.

**A2. What it caps.** Heap: the length of the `long[] blockValues` array allocated at AbstractBlockPackedWriter.java:52, plus the initial capacity hint `blockSize` bytes of `blockMetaWriter` (:51; what `ByteBuffersDataOutput(expectedSize)` actually allocates is not verified). The quantity compared at line 62 is `blockIndex` (declared :44) against `blockValues.length`: number of buffered longs, not bytes of resource, and not compared to any limit.

**A3. Mechanism.**
1. `add(long)` at AbstractBlockPackedWriter.java:59; `checkNotFinished()` at :61.
2. The if statement: [`AbstractBlockPackedWriter.java:62`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/bitpack/AbstractBlockPackedWriter.java#L62).
3. True (buffer full): `flush()` (:64, defined :111-115) calls abstract `flushBlock()` then resets `blockIndex = 0`. `BlockPackedWriter.flushBlock` (BlockPackedWriter.java:44-76) and `MonotonicBlockPackedWriter.flushBlock` (MonotonicBlockPackedWriter.java:51-86) compute bits per value, append block metadata to `blockMetaWriter` and write packed values to `indexOutput` through `writeValues` (AbstractBlockPackedWriter.java:90-98).
4. False: store the value, `blockValues[blockIndex++] = l` (:66).
5. `finish()` flushes the partial block if `blockIndex > 0` (:78-81) and copies the metadata to the file (:83).
Outcomes: no rejection, no exception, no back-pressure; the only effect is a disk write. Bypass/overshoot: none for the array (fixed length). Unbounded growth: `blockMetaWriter` accumulates metadata for every block until `finish()` (a few bytes per block, so growing with row count / blockSize); it is not capped by this constant.
Instance counts per SSTable components writer (SSTableComponentsWriter.java:58-72): non-monotonic `BLOCK_SIZE` writers = 2 (token, partition size); monotonic = 2 (row-to-partition, partition key block offsets), +1 monotonic if clustering (:72). So about 2 x 1 KiB + 2 x 128 KiB = 258 KiB of `long[]`, 386 KiB with clustering, per SSTable being written with SAI per-SSTable components (derived from the lines above, not measured).

**A4. Other consumers.** Heap used by SAI index building is dominated by per-column segment buffers, limited by `sai_options.segment_write_buffer_size` (conf/cassandra.yaml:1790-1795, default 1024MiB; `SEGMENT_BUILD_MEMORY_LIMIT` at V1OnDiskFormat.java:126), by the key stores and trie/balanced-tree writers, and by memtable/SSTable memory generally. Disk is used by all SAI components and SSTables.

**A5. Evidence beyond the source.** The class comment states it is a modified copy of Lucene's `AbstractBlockPackedWriter` (AbstractBlockPackedWriter.java:28-31). Existing test: `test/unit/org/apache/cassandra/index/sai/disk/v1/bitpack/NumericValuesTest.java` (method names seen: testMonotonic, testRegular, testRepeatsMonotonicValues, testRepeatsRegularValues; body not read). No issue numbers cited.

## B. Verification solution

**B1. Claim under test.** Usage does not follow this constraint: (a) the writer's heap buffer is exactly `blockSize` longs regardless of how many values are added, and the check at :62 flushes rather than limiting; (b) on a real node, heap and disk used by SAI writing do not track `BLOCK_SIZE` / `MONOTONIC_BLOCK_SIZE`, while they do track a known cap (`segment_write_buffer_size`) and the data volume.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a ~/cassandra-5.0.9/ /local/work/c509/`), `cd /local/work/c509 && ant jar` (or `ant generate-idea-files` not needed). Write a small JUnit test or main class beside `NumericValuesTest` (copy, do not edit the shared tree) that builds `BlockPackedWriter` / `MonotonicBlockPackedWriter` over a `ByteBuffersIndexOutput` or the pattern used in `NumericValuesTest`. JVM options: `-Xmx512m -XX:+UseSerialGC` (so the heap is deterministic).

**B2b. Knobs.** `blockSize` passed to the public constructors (BlockPackedWriter.java:38, MonotonicBlockPackedWriter.java:38): 64 (minimum), 128 (production non-monotonic), 16384 (production monotonic), 1<<20, 1<<24 (valid powers of two) and invalid 100 and 32. Why: edges of the check at SAICodecUtils.java:127-139 plus the two production values and two large values to see allocation scale.

**B2c. Workload.** For each blockSize feed N = 10 x 1<<24 sequential values (monotonic: increasing; plain: random below 1<<20) via `add`. Arithmetic: with N far above every blockSize, the check at :62 fires N / blockSize times. Also feed fewer than blockSize values for the never-flushed case.

**B2d. Observables and instruments.** (1) `blockValues.length` via reflection on the protected field; (2) `blockIndex` via reflection, sampled after each `add`; (3) count of `flushBlock` calls via a subclass or counting `IndexOutput`; (4) bytes written to the output; (5) heap via `jcmd <pid> GC.class_histogram` (instances and bytes of `long[]`) after a forced GC with N values added; (6) `blockMetaWriter.intSize()` (ResettableByteBuffersIndexOutput.java, `intSize`). Cannot observe: actual native allocation of the `ByteBuffersDataOutput` beyond its reported size.

**B2e. Procedure.** 1. Build. 2. For each blockSize: construct writer; assert `blockValues.length == blockSize`; add N values sampling `blockIndex` (never exceeds blockSize); record flush count; call `finish()`; record file size and `blockMetaWriter` size. 3. Run `jcmd GC.class_histogram` with the writer alive, before `finish()`. 4. Run invalid sizes and record the exception. 5. Positive control (below).

**B2f. Predictions.** `blockValues.length == blockSize` for all valid sizes; `blockIndex <= blockSize` always; flush count = ceil(N / blockSize); heap of the `long[]` is 8 x blockSize bytes (+16 byte header) independent of N; sizes 100 and 32 throw `IllegalArgumentException` with the messages at SAICodecUtils.java:132 / :140 area (message text not re-checked). Metadata size grows with N / blockSize, not bounded by the check. Claim wrong if the array length or heap of the writer grows with N, or if a limit stops the writer at the boundary.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `long[]` size = 8 x blockSize, flat in N; flush count = N / blockSize | Check only recycles the buffer; claim confirmed |
| Writer-held heap grows with N beyond metadata | Claim refuted; a hidden accumulation exists |
| Heap/usage scales with blockSize only as 8 x blockSize | Confirms the knob bounds only the scratch array (tiny at production values) |
| Positive control moves (see B2h) while writer heap flat vs N | Confirms: usage does not follow the constraint |
| N never exceeds blockSize or control did not move | Not confirmed; rerun with larger N or fix the control |

**B2h. Controls.** Positive control: a plain `ArrayList<Long>` / `LongArrayList` accumulating the same N values shows heap rising with N in the same histogram, proving the instrument sees growth. Second control: the metadata buffer rising with N shows the instrument detects real accumulation.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, local copy of the tag built with `ant jar`; data, commitlog, hints on local disk of known size (>= 20 GB free). Config in cassandra.yaml: `sai_options: segment_write_buffer_size: 1024MiB` baseline (`sai_options` at conf/cassandra.yaml:1789-1795). JVM: `-Xms4G -Xmx4G`, GC logging on. A table with a SAI index on one column (SAI requires the `sai` index class; yaml hint at conf/cassandra.yaml:2259, not read further).

**B3b. Knobs.** The block-size constants cannot be set at runtime. Variant A: stock build. Variant B: a local copy where `BLOCK_SIZE` and `MONOTONIC_BLOCK_SIZE` (NumericValuesWriter.java:34-35) are set to 64 and 64 (minimum). Variant C: both set to 1<<20. These bracket the production values 128 / 16384 by orders of magnitude; each variant is a separate build in its own directory. Control knob: `segment_write_buffer_size` 128MiB vs 1024MiB (positive control, claimed in the yaml comment to cap segment build memory).

**B3c. Workload.** `cassandra-stress` or CQL inserts through the normal client path: 20 million rows (partition key int, one indexed text/int column, optionally a clustering column to add the extra monotonic writer), forcing `nodetool flush` and one `nodetool compact` so SAI per-SSTable component writers run. Arithmetic: 20M rows is 20M / 16384 = ~1221 monotonic blocks per component, and 20M / 128 = ~156k non-monotonic blocks, so the check fires many times in all variants. Duration: until flush and compaction finish (minutes to tens of minutes).

**B3d. Observables and instruments.** Heap: `jcmd <pid> GC.class_histogram` taken repeatedly during flush/compaction (look at `long[]` instances of 16400 / 1 << 20 sized arrays, via `jcmd GC.heap_dump` and offline analysis if needed); peak heap from GC log; `nodetool info`; disk: `du` of the SAI components (`*SAI*` files in the data dir) after flush and after compaction; `nodetool tablestats` for off-heap and SSTable sizes. Cannot observe: transient per-writer arrays directly in a histogram if the writer lives for less than the sampling interval (sample every 1 s).

**B3e. Procedure.** 1. Build three variants. 2. For each, start the node, create keyspace/table/index, load the workload, flush, compact, sampling heap and disk throughout. 3. Record peak `long[]` bytes, peak heap, SAI component sizes. 4. Repeat with `segment_write_buffer_size` 128MiB vs 1024MiB on the stock build (positive control). 5. Stop the node (`nodetool drain`, kill process), confirm no `CassandraDaemon` remains (`pgrep -f CassandraDaemon`), delete the data directories.

**B3f. Predictions.** Variants A/B/C: peak heap differs by at most the scratch arrays (A: ~258 KiB per SSTable writer; C: a few MiB per writer: 4 x 8 MiB + metadata, derived from A3), well under 1% of the 4 GiB heap; SAI component disk size changes only slightly (block packing efficiency differs, not a cap). `segment_write_buffer_size` 128MiB vs 1024MiB: peak heap during build changes by a clearly larger amount, in the direction of the smaller value (relation, not a number). Claim wrong if peak heap or disk tracks the block-size variant by more than the scratch arrays predict.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Peak heap and disk nearly identical across A/B/C; control moves | Claim confirmed: usage does not follow the constraint |
| Peak heap/disk differs between A/B/C by far more than the scratch arrays | Claim refuted |
| Control `segment_write_buffer_size` shows no movement, or the limit was never reached | Not confirmed; raise rows or check the index is actually being built |
| Metadata or SAI file size grows with row count in all variants | Expected; confirms growth is data-driven, not block-size-driven |

**B3h. Controls.** Same data, same seeds, same heap size across variants; one fresh data directory per run; GC forced (`jcmd GC.run`) before each snapshot to remove garbage; positive control above.

**B4. Risks and cleanup.** Disk: 20M-row loads and compaction need several GB; use a local disk of known size, never shared storage; set commitlog and hints directories locally. Processes: stop the node and any stress tool, then `pgrep -f "CassandraDaemon|cassandra-stress"` must be empty. Build only in local copies; delete `/local/work/c509*` and the data directories afterwards. Unit tier needs only a temporary directory; delete it.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/bitpack/AbstractBlockPackedWriter.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/bitpack/BlockPackedWriter.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/bitpack/MonotonicBlockPackedWriter.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/bitpack/NumericValuesWriter.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/SAICodecUtils.java (lines 120-142)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/SSTableComponentsWriter.java (lines 50-80)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/ResettableByteBuffersIndexOutput.java (lines 30-75)
- /users/jason92/cassandra-5.0.9/conf/cassandra.yaml (SAI sections)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/V1OnDiskFormat.java (grep only)
- /users/jason92/cassandra-5.0.9/test/unit/org/apache/cassandra/index/sai/disk/v1/bitpack/NumericValuesTest.java (method list only)

## D. Stage-4 feedback

`none yet`
