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

> **Amended 2026-10-28 (stage-4 audit): see B5, which overrides this section where they conflict.**

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

> **Amended 2026-10-28 (stage-4 audit): see B5, which overrides this section where they conflict.**

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

### B5. Stage-4 audit amendments (2026-10-28)

Made before any reading; they override the text of the sections named where they conflict. None depends on a reading.

1. **B2a/B2d (run form, heap).** The probe is a plain `java -cp` run against `build/classes/main` of a `copy-source.sh` copy (probe class in package `org.apache.cassandra.index.sai.disk.v1.bitpack`, compiled to its own directory), not `ant testsome`; `-Xmx1g -XX:+UseSerialGC` (a 2^24 `long[]` is 128 MiB). Instruments added: `ThreadMXBean.getThreadAllocatedBytes` around each constructor (the `ByteBuffersDataOutput(expectedSize)` allocation that A2 marks unverified is thereby measured), and a flush counter (a subclass overriding the protected `flushBlock()` and calling `super`).
2. **B2c (sink).** The output is a counting `IndexOutput` that retains nothing (B2c's ByteBuffersIndexOutput would hold up to ~400 MB for N = 10 x 2^24). Both `BlockPackedWriter` and `MonotonicBlockPackedWriter` are run; N is the same for every size.
3. **B2f (citations).** The invalid-size messages are at `SAICodecUtils.java:133` (power of two: 100) and `:142` (range: 32); the check spans `:127-144`. The flush count is `ceil(N / blockSize)` (the last flush comes from `finish()`).
4. **B3a/B3c/B3e (workload size and load path).** 20M rows is replaced by **3,000,000 rows** (`pk` int = i/100, `ck` int = i%100, `v` int random below 10^6, `txt` text `'w'+(i%100)`; five numeric-values writers because of the clustering column; indexes `v_idx` and `txt_idx`). Arithmetic: 3M/16384 = 184 monotonic blocks, 3M/128 = 23,438 plain blocks, so the check fires many times in every build; variant C (2^20) gives 3 blocks. One extra stock arm at 750,000 rows shows disk growing with rows. Heap `-Xms4G -Xmx4G`. **Load path (cluster tier, replaces the flush-and-compact load).** The rows are loaded once per row count into an *unindexed* table with the bundled python driver and left as one flushed, compacted SSTable (a seed data directory on local disk); every arm restores a copy of the seed, starts a node on its build, runs `CREATE INDEX ... USING 'sai'` (the initial index build) and then `nodetool rebuild_index` (a repeat). The index build and the memtable flush both write the per-SSTable and per-index components through `StorageAttachedIndexWriter` (`SSTableComponentsWriter` is created at `StorageAttachedIndexWriter.java:95` via `V1OnDiskFormat.java:162-164`), so the traced writers run on this path; a Byteman ledger (one line per writer construction, with the array length) is added as an instrument and proves it in every arm. Reason: it removes the memtable and commit log from the comparison and makes the arms differ only in the build and the yaml.
5. **B3b/B3h (control).** **Positive control, defined (all SAI cluster tiers).** The control is the stock build at the largest row count with `sai_options.segment_write_buffer_size: 16MiB` against the default 1024MiB. It *moves* iff (i) the peak of the JMX gauge `SegmentBufferSpaceUsedBytes` in the 16MiB arm is <= 20 MiB, (ii) the default arm's peak is > 32 MiB (the limit was reached), and (iii) the 16MiB arm's `debug.log` has the `Global limit of ... exceeded` memory-limit flush lines that the default arm lacks. Peak heap (500 ms JMX samples) and RSS are reported for every arm but are not decisive: a heap peak between garbage collections is noisy.
6. **B3f (arithmetic).** Exact scratch arrays per SSTable with clustering: 2 x 1,024 B + 3 x 131,072 B = 395,264 B (386 KiB) in A; B (64/64): 5 x 512 B; C (2^20): 5 x 8 MiB = 40 MiB, which is 1.0 % of the 4 GiB heap, not "well under 1 %". The prediction is read as: the **ledger** (Byteman) equals these figures exactly, and peak heap differs between builds by no more than the ledger difference plus 2 % of the heap (GC noise). "Disk changes only slightly" is read as: total SAI bytes across builds within 10 %, and any per-component difference explained by blocks x metadata bytes (more, smaller blocks = more metadata); a difference not explained that way, or growth that saturates in rows, refutes.
7. **B3g (added row).** A build that fails to open or query the index (e.g. a variant that cannot read its own files) is *Not confirmed*, not Confirmed; each arm ends with `SELECT count(*)` on both indexed columns equal to the seed row count.
8. **Post-freeze correction of control (iii) (2026-10-28, made after the first cluster arm (stock, 3M rows) had been seen; claim, predictions and rows unchanged, and not made from any reading of the tested quantity across builds).** Item 5's condition (iii) assumed the default 1024 MiB arm never reaches its segment-buffer limit. The first arm showed the opposite: at 3,000,000 rows the default arm's gauge peaked at 1,073,743,912 B (the limit, 1,073,741,824 B) with 8 memory-limit flush lines in `debug.log`. Condition (iii) is therefore read as: the 16 MiB arm has **more** `Global limit of ... exceeded` lines than the default arm. Conditions (i) and (ii) stand as written ((ii) is met by that reading). Run 1 was not restarted: the procedure and the raw data are unchanged, only this evaluation criterion is (recorded as a runbook defect in the results file).

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

**2026-10-28 (stage 4, node `pc39`; results: `stage4-runtime-verification/results/block_size-add-blockindex--autonomous.md`).** Unit tier **Confirmed**, effect **does not cap**; cluster tier **Refuted as frozen** (disk of five numeric-values files follows the constant by more than the scratch arrays predict), effect **does not cap**; outcome class **true negative** (estimate `negative`).

- Unit: `blockValues.length` = blockSize for sizes 64 to 2^24 on both writers, `blockIndex` never above blockSize, flushes = ceil(N / blockSize) (1,310,720 at bs 128, 10 at 2^24 for N = 167,772,160), retained `long[]` = 8 bs + 16 and identical at N = bs - 1 and N = 167,772,160; 100 and 32 rejected with the traced messages; metadata grows with the block count (10.1 MB at 128, 917 B at 2^20); a growing `long[]` control moved by 8 N.
- Cluster (3M rows with clustering, seed + `CREATE INDEX` + `rebuild_index`): ledger lengths exactly 128 / 16384, 64, 2^20 per arm; total SAI bytes 49.13 / 41.54 / 52.67 MB for A / B (64) / C (2^20), all of the difference in the five numeric-values files (`RowToToken` 20.5 / 12.6 / 24.0 MB), the other 28.3 MB byte-identical; 3.99 x for 4 x the rows; heap peak (500 ms samples) cannot separate arms (two identical stock arms differ by 293 MiB); control `segment_write_buffer_size` 16 MiB: gauge 16.0 MiB vs 1,024 MiB, 848 vs 8 `Global limit` flush lines.
- Amendments at the audit, before any reading (2026-10-28, B5.1 to B5.7): run form (`java -cp`), counting sink, 3M rows, seed + `CREATE INDEX` load path, control definition, 40 MiB figure for variant C, tolerances; post-freeze B5.8 (control condition (iii)) after the first cluster arm.
- Findings for stage 3: (1) "disk changes only slightly" was wrong in magnitude: the block size sets the bit width packing of five per-SSTable files, so a 16,384-fold change moved the total SAI bytes by 27 % (smaller blocks pack tighter: tokens are sorted, so a small block spans a small range), while the real caps and the dominant components did not move; the claim is better stated as "the constant is a layout parameter that changes the packing of the numeric-values files by tens of percent and bounds nothing". (2) Peak heap from 500 ms samples cannot resolve a 40 MiB difference on a 4 GiB G1 heap; use the Byteman ledger (B3d). (3) At 3M rows the default 1024 MiB segment buffer is reached (8 limit flushes; "Current builder usage is 1.000GiB for 604508 cells"), so it is a valid positive control on its own; the B3f remark that 40 MiB of scratch is "well under 1 %" of 4 GiB is 1.0 %.
