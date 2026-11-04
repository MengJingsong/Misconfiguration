# compressed-sstable-writer buffer (chunk_length) — verification solution  <!-- file: cases/compressed-sequentialwriter-resetandtruncate-compressedbuffer--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/io/compress/CompressedSequentialWriter.java:247` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code agent, 2026-10-25 |
| Estimate | `negative`: the grow-the-buffer branch at :247 is not governed by any configured limit and, with the shipped compressors, is not reached; the only size that matters is set up front by the table's `chunk_length_in_kb`. |
| Ground | The check is a grow-on-demand test (`compressed.capacity() < chunkSize`), not a cap. `chunkSize` is a chunk this writer already wrote, and every shipped `ICompressor.initialCompressedBufferLength` is an upper bound on compressor output, so the branch should never fire. Its only caller (`resetAndTruncate`) is reached solely from the scrubber's failure path. The buffer's size is fixed at construction by `chunk_length_in_kb`; no limit bounds the number of concurrent writers. |

## A. Constraint trace

**A1. The constraint.** There is no dedicated limit at :247. The constraint behind it is the per-table compression option `chunk_length_in_kb` (`CompressionParams.CHUNK_LENGTH_IN_KB`, declared at `src/java/org/apache/cassandra/schema/CompressionParams.java:55`) together with `min_compress_ratio`, which is turned into `maxCompressedLength` (`CompressionParams.java:187-190`). Unit: KiB in the option, bytes in `chunkLength` (`parseChunkLength`, `CompressionParams.java:345-360`, multiplies by 1024). Default: `DEFAULT_CHUNK_LENGTH = 1024 * 16` (`CompressionParams.java:48`), i.e. 16 KiB, with `DEFAULT_MIN_COMPRESS_RATIO = 0.0` (`:49`), which gives `maxCompressedLength = Integer.MAX_VALUE` (`:189`, a division by 0.0 gives infinity, which `Math.min` clamps). Validation (`validate()`, `:444-458`): chunk length must be positive and a power of 2, and `maxCompressedLength <= chunkLength` unless it is `Integer.MAX_VALUE`. It is set per table with `CREATE/ALTER TABLE ... WITH compression = {'class': ..., 'chunk_length_in_kb': N}` (schema change, no restart). It only applies to SSTables written afterwards. Flush may substitute other params (`DataComponent.java:68-98`; `flush_compression` default `fast`, `Config.java:399`).

**A2. What it caps.** Memory of a writer's scratch buffers. Two buffers scale with chunk length: the base `buffer` (`SequentialWriter`, allocated from `option.allocateBuffer()` at `SequentialWriter.java:166`, sized `parameters.chunkLength()` and typed `preferredBufferType()` by `CompressedSequentialWriter.java:90-91`), and `compressed`, allocated at `:98` with `compressor.initialCompressedBufferLength(buffer.capacity())`. For LZ4 and Zstd, `preferredBufferType()` is `OFF_HEAP` (`LZ4Compressor.java:240-243`, `ZstdCompressor.java:208-211`), so these are `ByteBuffer.allocateDirect` (`BufferType.java:33-36`), counted against direct memory. What the line compares: `compressed.capacity()` against `chunkSize`, the compressed length (without the 4-byte CRC) of a chunk already on disk.

**A3. Mechanism.**
1. `SSTableRewriter.tryAppend` (`SSTableRewriter.java:140-152`) calls `writer.mark()` (`:142`) and, if the append throws, `writer.resetAndTruncate()` (`:149`). This is the only production path to the method: callers of `tryAppend` are `SortedTableScrubber.java:300`, from `BigTableScrubber.java:167,188` and `BtiTableScrubber.java:187,210`.
2. `SortedTableWriter.resetAndTruncate()` (`SortedTableWriter.java:297-302`) calls `dataWriter.resetAndTruncate(dataMark)`, which is `CompressedSequentialWriter.resetAndTruncate` (`:224`).
3. If the mark is in the current chunk (`realMark.chunkOffset == chunkOffset`, `:233`) it just drops buffered bytes and returns (`:236-237`). Otherwise it syncs (`:241`) and computes `chunkSize` from the metadata offset of the chunk after the mark (`:246`; `CompressionMetadata.Writer.chunkOffsetBy`, `CompressionMetadata.java:466-469`).
4. `:247`: if `compressed.capacity() < chunkSize`, free it (`:249`) and allocate exactly `chunkSize` (`:250`). Otherwise reuse it. Either way it reads the chunk back (`:255-258`), decompresses or copies into `buffer` (`:265-268`), checks the CRC (`:275-283`), and truncates (`:305`).
5. Why `chunkSize <= capacity` normally holds: in `flushData`, a compressed chunk is stored as-is only if `compressedLength < maxCompressedLength` (`:160`); otherwise the raw chunk is stored, either unpadded when it is at least `maxCompressedLength` (`:163-165`) or padded up to `maxCompressedLength` (`:166-176`). So stored sizes are at most the compressor's output bound or `chunk_length`. The initial capacity is that bound: LZ4 `4 + maxCompressedLength(chunk)` (`LZ4Compressor.java:113-115`), Snappy `Snappy.maxCompressedLength` (`SnappyCompressor.java:77-80`), Zstd `compressBound` (`ZstdCompressor.java:105-108`), Deflate zlib `deflateBound` (`DeflateCompressor.java:88-92`), Noop `chunkLength` (`NoopCompressor.java:45-48`). The branch needs a compressor whose output exceeds its own advertised bound. Test code does this with `MockCompressor` (ratio below 1, `MockCompressor.java:57-60`). **[Amended 2026-10-26, stage-4 audit: this sentence is wrong.]** `MockCompressor.initialCompressedBufferLength` is `ceil(chunk / ratio + extra)` (`MockCompressor.java:57-60`) and its `compress` writes exactly `initialCompressedBufferLength(inputLength)` bytes (`:71-79`), so for a full chunk the output equals its own bound and a ratio below 1 only makes `compressed` larger than the chunk. The branch fires only when a compressor's bound is *below* the stored chunk size, which needs the raw-chunk path of `flushData` (`:160-165`): a mock with ratio R > 1 and `min_compress_ratio` = R gives capacity = chunk/R, `maxCompressedLength` = chunk/R, compressed output = chunk/R, which is `>= maxCompressedLength`, so the raw chunk (`chunk` bytes) is stored and `chunkSize` = chunk > capacity. No shipped compressor has a bound below its chunk length, so the branch is unreachable with them, at any `min_compress_ratio` (stored size <= max(compressed output <= bound, chunk) <= bound).
6. Overshoot: when it does fire, there is no ceiling; the new size is `chunkSize` taken straight from the file metadata. It is also an `int` cast of a `long` (`:246`). An unbounded `compress()` result at `:149` would fail first, since `compressed` is bounded by the compressor.

**A4. Other consumers.** `buffer` (same chunk length); the CRC/digest writers; `CompressionMetadata.Writer` offsets (off-heap, grows with chunk count, not chunk length); the buffer pool / chunk cache for reads (`file_cache_size`), which does not include these writer buffers; memtables (heap or off-heap); index summary, bloom filter and partition index builders. One writer per concurrent flush or compaction (`concurrent_compactors`, flush writers), each holding `buffer` plus `compressed` of about 2x chunk_length. No configuration entry limits their sum.

**A5. Evidence beyond the source.** Tests: `test/unit/org/apache/cassandra/io/compress/CompressedSequentialWriterTest.java:282-312` (`resetAndTruncateTest` with `CompressionParams.lz4(48)`), `MockCompressor.java`. Docs: Cassandra table compression options (`chunk_length_in_kb`, `min_compress_ratio`), https://cassandra.apache.org/doc/5.0/cassandra/developing/cql/ddl.html (not re-read in this session; claims above rest on the source only). Otherwise none.

## B. Verification solution

**B1. Claim under test.** (a) In `CompressedSequentialWriter.resetAndTruncate`, the reallocation at :247-250 is not a cap: it never fires for real compressors, so the capacity of `compressed` stays equal to `initialCompressedBufferLength(chunk_length)` for the writer's life; when forced with a compressor that exceeds its bound, it grows to exactly the stored chunk size with no ceiling. (b) Writer scratch memory follows `chunk_length_in_kb` (with the number of concurrent writers), not any node-level limit.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a ~/cassandra-5.0.9/ /local/scratch/c509/`; never build in the shared tree). `cd /local/scratch/c509 && ant jar` then `ant build-test`. Put a new JUnit test `test/unit/org/apache/cassandra/io/compress/ChunkBufferGrowthTest.java` in the copy, modelled on `CompressedSequentialWriterTest.java:282-312`. Run with `ant testsome -Dtest.name=ChunkBufferGrowthTest`. JVM options: defaults of the test target plus `-XX:MaxDirectMemorySize=256m`.

**B2b. Knobs.** Compressor: `LZ4Compressor` (via `CompressionParams.lz4(chunk)`), plus `MockCompressor`, built as `CompressedSequentialWriterTest.testUncompressedChunks` does (`new CompressionParams(MockCompressor.class.getTypeName(), MockCompressor.paramsFor(ratio, 0), chunk, minCompressRatio)`, `CompressedSequentialWriterTest.java:227-229`). **[Amended 2026-10-26: the forcing arm is ratio 2.0 with `min_compress_ratio` 2.0 (capacity = chunk/2, stored chunk = chunk), not ratio 0.5; a ratio-0.5 arm is kept as a second control that must NOT fire (capacity = 2 x chunk).]** Chunk length: 4096, 16384, 65536, 1048576 bytes (power of 2, as `validate()` requires). Data: incompressible (`new Random(1).nextBytes`) versus zeros.

**B2c. Workload.** For each configuration: create the writer on a temp file in local scratch, write 2 chunks of data (`2 * chunk` bytes), take `mark()` (the buffer is full at that point, so `mark()` flushes it, `CompressedSequentialWriter.java:216-221`, and the mark sits at the start of chunk index 2), write 4 more chunks (`4 * chunk` bytes) so chunks 2 to 4 flush and chunk 5 stays buffered, then call `resetAndTruncate(mark)`. **[Amended 2026-10-26: the original text said 8 chunks then a mark after chunk 2, which is inconsistent.]** Arithmetic: after the 4 extra chunks `chunkOffset` is the offset of chunk 5, not the mark's (chunk 2), so :233 is false and :247 is evaluated; `syncInternal` (:241) flushes chunk 5 first, so `chunkOffsetBy(3)` exists. Observable proof that the path went past :233: the data file shrinks to `realMark.chunkOffset` (`truncate`, :305) while the early-return control leaves the file length unchanged.

**B2d. Observables and instruments.** Private field `compressed` read by reflection (`Field f = CompressedSequentialWriter.class.getDeclaredField("compressed"); f.setAccessible(true)`) before the call and after: its `capacity()` and identity (`System.identityHashCode`). The value `chunkSize` is not observable directly; recompute it as `chunkOffsetBy(next) - chunkOffset - 4` from the written CompressionInfo or use a debugger/log line in the scratch copy (only the scratch copy may be edited). `java.nio.BufferPoolMXBean` "direct" count and `totalCapacity` as a second view. Not observable: native allocator overhead.

**B2e. Procedure.**
1. Build as in B2a.
2. For each (compressor, chunk, data) cell run the workload, recording capacity before and after `resetAndTruncate`.
3. Assert the position, flushed length, and read-back data after reset (so the path really ran and truncated).
4. Repeat for the positive control cell: `MockCompressor` exceeding its bound.
5. Delete temp files; confirm no `java` test process left.

**B2f. Predictions.** (stated before any run)
- LZ4, any chunk, either data: capacity before = `4 + LZ4 maxCompressedLength(chunk)`; after = same value; the same buffer object (identity unchanged). The branch at :247 does not fire. For incompressible data stored bytes exceed `chunk` slightly (up to the bound) but not the capacity.
- Capacity scales with chunk. **[Amended 2026-10-26: numbers corrected; lz4-java `maxCompressedLength(n)` = `n + n/255 + 16`.]** Expected capacities: chunk 4096 -> 4132, 16384 -> 16468, 65536 -> 65813, 1048576 -> 1052708 bytes (overhead over the chunk = 20 + chunk/255, i.e. 36, 84, 277, 4132 bytes; ratio to chunk 1.0088, 1.0051, 1.0042, 1.0039, so within 1.0 to 1.01). Ratios between cells: 16 KiB/4 KiB = 3.99, 64 KiB/4 KiB = 15.9, 1 MiB/4 KiB = 254.8. Base `buffer` capacity = chunk exactly.
- MockCompressor forcing arm (ratio 2.0, `min_compress_ratio` 2.0): capacity before = chunk/2; stored chunk = chunk (raw); after = chunk exactly (> before), new object identity; no ceiling. The write-up's original arm (ratio 0.5, which was said to exceed its bound) does not exceed it: capacity before = 2 x chunk, after = the same, identity unchanged (a control that must not fire).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Capacity unchanged, same identity, for LZ4 in every cell | Claim (a) supported: branch not reached; size set by chunk_length |
| Capacity differs from `initialCompressedBufferLength(chunk)` after reset with a real compressor | Claim (a) refuted: the branch fires in normal data (usage follows data, not config) |
| MockCompressor forcing arm (ratio 2.0, `min_compress_ratio` 2.0): capacity after equals the stored chunk size (= chunk), larger than before (chunk/2) | Branch is a bare grow with no ceiling (confirms the negative: nothing limits it); also the positive control that the instrument sees a grow when one happens |
| MockCompressor: capacity after is clamped at some limit | Claim refuted: a cap exists (find where) |
| Capacity proportional to chunk across cells | Claim (b) supported (control: chunk_length moves memory) |
| Capacity flat across chunk sizes | Control did not move; reading not valid |
| The branch never evaluated (position check at :233 true) | Workload did not reach :247; not confirmed |

**B2h. Controls.** (Amended 2026-10-26: the forcing arm above is the positive control for the instrument; the ratio-0.5 arm and the early-return arm are negative controls.) The chunk-length sweep is the positive control (a known knob that moves the buffer). Incompressible versus zero data separates data-dependence from config-dependence. A run that skips the extra chunks (mark in the current chunk, :233 true) confirms the branch is not reached trivially. Same JVM flags in all cells.

### B3. Cluster tier

**B3a. Environment and build.** One node suffices (optionally two). Local copy of the tag built with `ant jar` in `/local/scratch/c509`; JDK 11. `cassandra.yaml`: data, commitlog, hints, saved_caches directories on local disk of known size (at least 20 GB free), `num_tokens: 1`, `concurrent_compactors: 1` for the first pass. `conf/jvm11-server.options`: `-Xms2g -Xmx2g -XX:MaxDirectMemorySize=1g -XX:NativeMemoryTracking=summary`.

**B3b. Knobs.** Table compression `chunk_length_in_kb` in {4, 16, 256, 1024} (LZ4Compressor, `min_compress_ratio` default 0), set with `ALTER TABLE ks.t WITH compression = {'class':'LZ4Compressor','chunk_length_in_kb':'N'}`. `concurrent_compactors` in {1, 4} for the writer-count control. `flush_compression: table` (yaml) so flush uses the table's params rather than the default (`DataComponent.java:79-98`).

**B3c. Workload.** Table with a blob column; load with `cassandra-stress` (user mode or `write n=2000000`, 1 KiB values, random so incompressible) to produce several SSTables of about 100 MB each; then force `nodetool flush` and `nodetool compact ks t` (compaction opens one writer; 4 concurrent tables for 4 writers). Arithmetic: per writer scratch about `chunk + (chunk + bound)` = about 2x chunk, so 4 KiB gives 8 KiB per writer, 1024 KiB gives 2 MiB per writer; with 4 writers 32 KiB to 8 MiB, visible against NMT granularity if sampled during the write. To reach :247 itself in a cluster, run `nodetool scrub` on a table whose SSTable contains a partition that makes `append` throw (for example a corrupt cell injected by editing the data file in the scratch copy); this is the only path to :247. If such a corruption cannot be produced reliably, mark that sub-step n/a and rely on the unit tier for the branch. **[Amended 2026-10-26, stage-4 audit.]** The scrub sub-step is run as two arms on a LZ4 table with chunk 16 KiB: (S1) stop the node after flush, flip one byte of `*-Data.db` inside a late chunk of a multi-chunk partition (partitions of about 160 KiB of random 4 KiB blobs), restart, run `nodetool scrub`: the corrupt chunk fails its CRC while the scrubber is appending that partition, after earlier chunks of the partition were already written to the output; (S2) the same with a Byteman rule that, at line 247, replaces `compressed` by a 64-byte direct buffer, so the branch is forced on the real stored chunk. If S1 cannot be made to reach the line (the Byteman line trace of the observer rule R2 below shows no evaluation), the sub-step is recorded n/a with that reason and S2 stays as the Byteman-forced path (a deviation). Data volume is also reduced: per chunk value one table of 200,000 rows x 1 KiB random blob (about 200 MB), flushed in 4 SSTables, then compacted (writer arithmetic does not depend on volume; time and disk are bounded).

**B3d. Observables and instruments.** `jcmd <pid> VM.native_memory summary` (Internal/Other categories) sampled at 1 s during compaction, delta against a baseline taken before the job; `jcmd <pid> GC.heap_info`; the JMX `java.nio:type=BufferPool,name=direct` (`TotalCapacity`, `Count`) via `nodetool sjk mxdump` or `jconsole`; `du -sh` of the data directory. Not observable by these: the exact `chunkSize` inside `resetAndTruncate`; per-writer attribution (infer from count delta). **[Amended 2026-10-26: added, because the BufferPool/direct totals also include read-side chunk buffers of the compaction readers, which scale with chunk length too, so those totals cannot separate writer scratch from reader buffers.]** Direct instrument: a Byteman observer rule R1 on `CompressedSequentialWriter.<init>` AT EXIT writing `buffer.capacity()`, `compressed.capacity()` and `compressed.isDirect()` of every writer to a trace file, and R2 at line 247 writing `compressed.capacity()`, `chunkSize` and identity of `compressed` before the branch and R3 at line 255 after it. These give the writer scratch exactly; the NMT/BufferPool/JMX readings are secondary and are reported with this caveat.

**B3e. Procedure.**
1. Build, configure, start one node; wait for `nodetool status` UN.
2. For each chunk N: create the table, apply the ALTER, load data, flush, record baseline direct-buffer count/capacity and NMT.
3. Start `nodetool compact` and sample every second until it ends; record peak minus baseline.
4. Repeat with `concurrent_compactors: 4` (restart) and 4 tables compacted together.
5. Optional scrub run (B3c).
6. Stop node, `pgrep -f CassandraDaemon` must be empty, delete data directories.

**B3f. Predictions.** Peak direct-buffer increase during compaction is roughly 2 x chunk x writers, scaling linearly with `chunk_length_in_kb` (4 KiB: tens of KiB; 1024 KiB: about 2 MiB per writer) and with the writer count; no run shows growth beyond that from :247, because it is not reached in normal compaction. Heap is flat across chunk sizes. The scrub sub-step (if possible) shows no change in direct-buffer capacity at the reset event.
**[Amended 2026-10-26, stage-4 audit, before any reading; relation stated exactly.]** Trace form (R1): for chunk 4, 16, 256, 1024 KiB every constructed writer shows `buffer.capacity()` = 4096, 16384, 262144, 1048576 and `compressed.capacity()` = 4132, 16468, 263192, 1052708 (LZ4, `4 + n + n/255 + 16`), both direct (`isDirect()` true), for flush and compaction writers alike. R2 never prints in the normal flush/compaction runs. Scrub arm S1: if R2 prints, `compressed.capacity()` (16468) >= `chunkSize` and R3 prints the same identity (no grow). Scrub arm S2 (Byteman shrinks `compressed` to 64 bytes at line 247): R3 shows capacity = `chunkSize` exactly (about 16 KiB, no ceiling), new identity. Writer count: with `concurrent_compactors` 4 and 4 tables compacted together, 4 compaction writers are constructed within the run window (R1 count), against 1 for a single compaction. Uncompressed control: no CompressedSequentialWriter is constructed for that table's flush or compaction (R1 silent for it).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Peak direct usage proportional to chunk and writers; no extra step at scrub reset | Claim (a) and (b) supported |
| Usage independent of chunk_length | Positive control failed (writers not the dominant direct user, or instrument too coarse); not confirmed |
| Usage jumps at scrub reset beyond the chunk-based value | Claim (a) refuted for real data |
| R2 prints in a normal flush or compaction (no scrub), or in S1 with `chunkSize` > `compressed.capacity()` | Claim (a) refuted: the grow branch is reached with a shipped compressor |
| R1 capacities equal the trace form above for every chunk value, R2 silent in normal runs, S2 grows to exactly `chunkSize` | Claims (a) and (b) supported with direct evidence (secondary totals only corroborate) |
| S1 never evaluates line 247 (R2 silent after the scrub finished) | Scrub sub-step n/a for S1; S2 is the Byteman-forced path, recorded as a deviation |
| Usage follows a node-level limit when set (for example if `MaxDirectMemorySize` is hit, OOM) | Process-wide JVM limit, not this check; note separately |
| Compaction never opened more than one writer | Writer-count control did not move; not confirmed |

**B3h. Controls.** Chunk sweep and concurrent_compactors sweep are the positive controls (known to move buffer memory). Baseline NMT before each compaction removes memtable and cache noise. Same data and seed in every run. Uncompressed table (`compression = {'enabled':'false'}`) as a negative control: no `compressed` buffer, lower direct usage.

**B4. Risks and cleanup.** Disk: 20 GB local only; 2M x 1 KiB rows is about 2 GB per table times four tables plus compaction copies, so keep total under 15 GB and delete tables between chunk runs. Never write under the shared tree or shared storage. The scrub corruption step edits only the scratch copy of an SSTable. Leftover processes: `pgrep -f 'CassandraDaemon|cassandra-stress|ant'` must be empty at the end; `kill` any remainder; remove `/local/scratch/c509` and data directories.

## C. Sources read

- ~/writeup-A/playbook-autonomous.md
- ~/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/io/compress/CompressedSequentialWriter.java
- src/java/org/apache/cassandra/io/compress/{LZ4,Snappy,Zstd,Deflate,Noop}Compressor.java (initialCompressedBufferLength, preferredBufferType)
- src/java/org/apache/cassandra/io/compress/BufferType.java
- src/java/org/apache/cassandra/io/compress/CompressionMetadata.java (chunkOffsetBy)
- src/java/org/apache/cassandra/schema/CompressionParams.java
- src/java/org/apache/cassandra/io/util/SequentialWriter.java, SequentialWriterOption.java
- src/java/org/apache/cassandra/io/sstable/SSTableRewriter.java
- src/java/org/apache/cassandra/io/sstable/format/SortedTableWriter.java, SortedTableScrubber.java, DataComponent.java
- src/java/org/apache/cassandra/io/sstable/format/big/{BigTableWriter,BigTableScrubber}.java
- src/java/org/apache/cassandra/io/sstable/format/bti/{BtiTableWriter,BtiTableScrubber}.java (grep only)
- src/java/org/apache/cassandra/config/Config.java (flush_compression)
- conf/cassandra.yaml (grep)
- test/unit/org/apache/cassandra/io/compress/CompressedSequentialWriterTest.java, MockCompressor.java

## D. Stage-4 feedback

2026-10-26, stage 4 (results: `stage4-runtime-verification/results/compressed-sequentialwriter-resetandtruncate-compressedbuffer--autonomous.md`; node pc12, tree `~/s4-cs`; case-file commit and harness commit: not yet committed).
- **Audit amendments (before any reading, dated 2026-10-26, in A3 step 5, B2b, B2c, B2f, B2g, B2h, B3c, B3d, B3f, B3g):** the write-up's claim that `MockCompressor` at ratio 0.5 exceeds its bound was wrong (`MockCompressor.java:57-60,71-79`: output equals its own bound); the forcing arm is ratio 2.0 with `min_compress_ratio` 2.0. B2c's workload sequence was inconsistent; B2f's capacity numbers were wrong (correct: 4132 / 16468 / 65813 / 1052708); a direct Byteman writer trace (R1/R2/R3) and scrub arms S1 (real corrupted SSTable) and S2 (forced grow) were added. sha256 after the amendments (the frozen version): `0ce1a2742f945a5b0ac9377dccdbb4c8b424d6f7163c1b8d53afe664625f9ad7`.
- **Verdict:** unit Confirmed, cluster Confirmed; effect `does not cap`; outcome class true negative. LZ4 writers always had `compressed` = 4 + n + n/255 + 16 and `buffer` = chunk (chunk 4, 16, 256, 1024 KiB), 4 live compaction writers in the 4-table arm; the scrubber's failure path reached line 247 in 3 of 3 corrupted-SSTable runs and did not grow the buffer (capacity 16468, chunkSize 16454); with the grow forced the buffer became exactly the stored chunk size (unit Mock and cluster S2).
- **Notes:** the original B3f wording "roughly 2 x chunk x writers" for the direct-pool total was not met (the pool also holds the compaction readers' buffers: +1.1 MB at 4 KiB, +7.4 MB at 1024 KiB); the decisive reading is the per-writer trace. Scrub of a corrupted compressed SSTable raised `AssertionError: Buffer holder has not been acquired` to `nodetool scrub` in every run (unrelated to this check; not examined). Only LZ4 was run.
