# min_compress_ratio — verification solution  <!-- file: cases/min_compress_ratio-flushdata-maxcompressedlength--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`CompressedSequentialWriter.java:160`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/compress/CompressedSequentialWriter.java#L160) (`if (compressedLength >= maxCompressedLength)`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`. `min_compress_ratio` decides, chunk by chunk, whether a chunk is stored compressed or raw. It is not a cap on the SSTable data size. At its default (0.0) it never triggers, and raising it can only make files larger. |
| Ground | The check bounds one chunk's on-disk length (at most the uncompressed chunk length, `CompressedSequentialWriter.java:163-175`), not the total disk used by a table or node. Total Data.db size is set by data volume, compressor and chunk length. A higher ratio stores more chunks raw, so disk goes up with the knob instead of being capped by it. The only "cap" is the small guard against a compressor expanding incompressible data. |

> **Link rule.** Declaration and if statement are linked below at tag `cassandra-5.0.9`. All line numbers were re-opened and checked in the pinned tree.

## A. Constraint trace

**A1. The constraint.** `min_compress_ratio`: a per-table compression sub-option (schema option, in the `compression` map of CREATE/ALTER TABLE). It is not a cassandra.yaml key and not a JVM property. First declared as the string constant [`CompressionParams.java:57`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/CompressionParams.java#L57) (`MIN_COMPRESS_RATIO = "min_compress_ratio"`). Its default value is [`CompressionParams.java:49`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/CompressionParams.java#L49) (`DEFAULT_MIN_COMPRESS_RATIO = 0.0`).

- Parsing: `removeMinCompressRatio` reads the option with `Double.parseDouble`, else returns the default (`CompressionParams.java:384-391`).
- Derived value the check uses: `maxCompressedLength`, in bytes, from `calcMaxCompressedLength(chunkLength, minCompressRatio) = (int) ceil(min(chunkLength / ratio, Integer.MAX_VALUE))` (`CompressionParams.java:187-190`). With ratio 0.0 the division is `+Infinity`, so the value is `Integer.MAX_VALUE`. The earlier trace's reading is correct here.
- Chunk length: `chunk_length_in_kb` (`CompressionParams.java:55`, `:370-375`), default `DEFAULT_CHUNK_LENGTH = 16 KiB` (`:48`).
- Validation: `chunk_length` must be a power of two (`:450-451`); a negative max is rejected (`:453-454`); a max above the chunk length but below `Integer.MAX_VALUE` is rejected, i.e. the ratio must be 0 or >= 1 (`:456-457`).
- Setting: per table via CQL `compression = {'class': ..., 'min_compress_ratio': ...}`. No restart is needed for a schema change. It affects only SSTables written afterwards; the value in use is serialized into each SSTable's CompressionInfo (`CompressionParams.java:520`, `CompressionMetadata.java:389`).
- Earlier-trace correction: its statement that the padding "bounds disk use" is overstated; see A2/A3. Its line cites `:100`, `:160` and `:171-175` hold except that the padding block is `:163-175` (the `assert` is at `:172`).

**A2. What it caps.** Resource: disk (Data.db), and only per chunk. The quantity compared at `CompressedSequentialWriter.java:160` is `compressedLength` (bytes the compressor produced for one chunk, `compressed.position()` at `:157`) against `maxCompressedLength` (bytes, = chunk_length / ratio). It does not compare table size, node size or any memory quantity.

**A3. Mechanism.**
1. DataComponent builds the writer only if table compression is enabled (`io/sstable/format/DataComponent.java:43-52`; otherwise a `ChecksummedSequentialWriter`, `:54-60`). For flushes, `buildCompressionParams` can replace the table params: `flush_compression: none` uses `CompressionParams.NOOP`, and `fast` (the default, `config/Config.java:399`) swaps in the default LZ4 params if the table compressor lacks `FAST_COMPRESSION` (`DataComponent.java:73-96`). Those replacements carry ratio 0.0 (`CompressionParams.java:59-72`), so the table's `min_compress_ratio` is ignored for flushes with such compressors. Default LZ4 (fast) has all uses (`LZ4Compressor.java:106`), so it keeps the table's params; LZ4HC does not (`:99`).
2. Constructor: `maxCompressedLength = parameters.maxCompressedLength()` (`CompressedSequentialWriter.java:100`); the buffer size is the chunk length (`:90`).
3. `flushData()` compresses the chunk (`:149`), reads `uncompressedLength` and `compressedLength` (`:157-158`) and tests [`CompressedSequentialWriter.java:160`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/compress/CompressedSequentialWriter.java#L160) `if (compressedLength >= maxCompressedLength)`.
4. Outcome "true": write the raw buffer instead of the compressed one (`:162`). If the raw length is also `>= maxCompressedLength`, the chunk length written is the raw length (`:163-166`); otherwise (short final chunk only, per the code comment `:169-170`) the raw data is zero-padded up to `maxCompressedLength` (`:172-175`).
5. Outcome "false": the compressed bytes are written, so the chunk is smaller than `maxCompressedLength`.
6. Bookkeeping: `compressedSize += compressedLength` (`:178`), offset advance `chunkOffset += compressedLength + 4` (`:203`; 4 bytes is the CRC), and `addCompressionRatio(compressedSize, uncompressedSize)` at close (`:394`).
7. Readers decide compressed or raw by the same threshold: `chunkSize < maxCompressedLength` means decompress (`CompressedSequentialWriter.java:265`, `io/util/CompressedChunkReader.java:269,364`).

Consequences: with ratio 0 the test never fires, so incompressible chunks are stored as compressor output (which can be slightly larger than the chunk). With ratio `r >= 1` every chunk whose compression is worse than `r`:1 is stored raw, which is larger than its compressed form. Upper bound on a stored chunk: the raw chunk length (when the test fires) or less than `maxCompressedLength` (when it does not). Bypasses: compression disabled; flush with `flush_compression` as above; other compressors' flush.

**A4. Other consumers.** The SSTable's other components (Index.db, Summary, Filter, CompressionInfo offsets: one 8-byte offset per chunk, `CompressionMetadata.Writer.addOffset`, `CompressedSequentialWriter.java:183`) and the commit log, hints, snapshots and uncompacted SSTable overlap are all outside this knob. The compression buffers are heap/off-heap per writer: `compressed` is allocated at `initialCompressedBufferLength(buffer.capacity())` (`:98`), independent of the ratio.

**A5. Evidence beyond the source.** Existing unit test `test/unit/org/apache/cassandra/io/compress/CompressedSequentialWriterTest.java` uses `compressionParameters.maxCompressedLength()` (line 195, only that grep hit was read). Cassandra's compression docs describe the option (https://cassandra.apache.org/doc/5.0/cassandra/managing/operating/compression.html, not re-read this session, "not verified"). Issue numbers: none cited.

## B. Verification solution

**B1. Claim under test.** (Negative) The total on-disk Data.db size for a fixed data set does not shrink as `min_compress_ratio` rises. It stays equal (ratio 0.0 vs 1.0 on incompressible data, within one expansion margin) or grows (ratio above the data's actual compressibility), while a known disk-binding change (disabling or enabling compression) moves it. Per chunk, the stored length never exceeds the raw chunk length once the test fires.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a /users/jason92/cassandra-5.0.9/ $WORK/cassandra-5.0.9/`), `cd` there, `ant jar` (or `ant build-test` for a JUnit class). Put the test beside `CompressedSequentialWriterTest` (copy only; never in the shared tree). JVM options: default test options, `-Xmx1g`.

**B2b. Knobs.** `min_compress_ratio` in {0.0, 1.0, 1.25, 2.0, 4.0} with `chunk_length_in_kb` = 16 (default) and compressor LZ4 (`CompressionParams.lz4(chunkLength)` or the 4-arg public constructor at `CompressionParams.java:182-185` with `ratio`). Values: 0.0 is default/no trigger; 1.0 is the smallest legal and fires only for expansion; 2.0 and 4.0 straddle the data's real compressibility (maxCompressedLength 8192 and 4096 bytes).

**B2c. Workload.** Write 64 MiB = 4096 chunks of 16 KiB through `CompressedSequentialWriter` (constructor `:80-85`) for three payloads: (P0) all zeros (compresses far beyond 4:1); (P1) per chunk 10 KiB random plus 6 KiB zeros (LZ4 output roughly 10-11 KiB, ratio about 1.5:1, which is above 8192 and below 16384, so ratio 2.0 triggers, ratio 1.0 does not); (P2) fully random (LZ4 output at or above 16384, so ratio 1.0 and above trigger). Arithmetic: threshold = ceil(16384 / r) = 16384, 13108, 8192, 4096 for r = 1, 1.25, 2, 4.

**B2d. Observables and instruments.** Data.db length (`File.length()` after close); `getOnDiskFilePointer()` (`CompressedSequentialWriter.java:110`); the chunk offsets in CompressionInfo.db read through `CompressionMetadata` (per chunk stored length = next offset - offset - 4); the ratio recorded via the `MetadataCollector` (`:394`); count of chunks whose stored length equals the raw length. Not observable directly: the local `compressedLength` before the branch (derive it from a second run at ratio 0.0 for the same payload).

**B2e. Procedure.**
1. Build as B2a. Write a JUnit test (copy of the structure of `CompressedSequentialWriterTest`, not verified in detail) that, for each payload and each ratio, creates a temp file on local disk, writes the 4096 chunks with `write(byte[])`, closes the writer, and records Data.db length, chunk-length histogram and the recorded compression ratio.
2. Run `ant testsome -Dtest.name=<YourTest>` (set `-Dtest.methods` if needed).
3. Re-read each written file with `CompressedRandomAccessReader` through the metadata and compare bytes to the input, to prove the stored form (raw or compressed) is readable.
4. Delete temp files.

**B2f. Predictions (stated before any run).**
- P0: every chunk compresses below 4096, so file size is identical for all five ratios; no raw chunks.
- P1: size at r = 0.0, 1.0, 1.25 equal (chunks stay compressed); size at r = 2.0 and 4.0 larger, approaching 4096 x 16388 bytes (raw chunk + 4 CRC); raw-chunk count 0 vs 4096.
- P2: size at r = 0.0 is >= 4096 x 16388 (output may expand); at r >= 1.0 each chunk is exactly 16388 bytes on disk, so size is the same for 1.0, 1.25, 2.0, 4.0 and no larger than the r = 0.0 size.
- No payload ever shows Data.db shrinking as r rises. The claim is wrong if any payload's file is smaller at a higher ratio than at 0.0 by more than the expansion margin (at most a few bytes per chunk).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Size monotone non-decreasing in r on P1, flat on P0, equal-or-slightly-smaller only on P2 at r >= 1 | Claim confirmed: the knob picks a form per chunk, it does not cap total disk. |
| Size at higher r smaller than at 0.0 on P0 or P1 by more than a few bytes per chunk | Claim refuted: the knob reduces disk. |
| Control (compression class changed: LZ4 vs `CompressionParams.noCompression()` or `NOOP`) moves size for P0 while r does not | Claim confirmed (positive control moves). |
| Raw-chunk count stays 0 at r = 2.0 on P1 | Limit never reached (P1 did not hit the 1.5:1 range); adjust payload; not confirmed. |
| Readback differs from input | Stored form not understood; discard the run. |

**B2h. Controls.** Positive control: same payloads with compression class swapped (LZ4 vs none/NOOP) so disk moves for P0. Same temp dir, same JVM, one payload generated once (fixed seed) and reused; order of ratios randomized across a second pass to rule out file-cache effects.

### B3. Cluster tier

**B3a. Environment and build.** One node, local disk with at least 2 GiB free for data and 1 GiB for commit log, JDK 11, Ant. Copy the tree to local disk, `ant jar`. In `cassandra.yaml` copy: `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory` on local disk; `flush_compression: fast` (default, `Config.java:399`); `-Xmx2G -Xms2G`. Client: Python `cassandra-driver` from outside the tree.

**B3b. Knobs.** `min_compress_ratio` in {0.0, 1.0, 2.0} on four otherwise identical tables with LZ4 and `chunk_length_in_kb` = 16: `ALTER TABLE ... WITH compression = {'class':'LZ4Compressor','chunk_length_in_kb':16,'min_compress_ratio':R}`. Plus control tables: `compression = {'enabled': false}` and `{'class':'LZ4Compressor'}` default. Values as in B2b. Set by CQL; no restart.

**B3c. Workload.** Per table, 32768 rows, 4 KiB blob per row (128 MiB raw) with the same generator as B2c P1 (2560 random bytes + 1536 zeros, fixed seed) in one run, and fully random 4 KiB blobs (P2) in a second run. Single-row partitions (key = int). 32768 x 4096 = 128 MiB raw per table, well below node disk. Then `nodetool flush` and `nodetool compact <ks> <table>` so the final single SSTable is written by compaction (which uses the table params, unlike a flush with a non-FAST compressor; see A3.1).

**B3d. Observables and instruments.** `du -sb` of the table's `*-Data.db` on local disk (actual resource); `nodetool tablestats ks.t` fields "Space used (live)" and "SSTable Compression Ratio"; JMX `CompressionRatio` table gauge (`metrics/TableMetrics.java:556` region); the CompressionInfo.db header (stored max length, written at `CompressionMetadata.java:389`) to confirm each table used its ratio. Not observable: per-chunk branch; infer from size.

**B3e. Procedure.**
1. Start the node from the local build; create keyspace (RF 1) and the tables of B3b.
2. Insert the P1 rows into each table with the driver (same bytes for all tables), `nodetool flush`, `nodetool compact`, `nodetool tablestats`, `du -sb` Data.db.
3. `DROP`/`TRUNCATE` the tables, repeat with P2 data.
4. Stop the node, check no Cassandra process remains.

**B3f. Predictions.** P1: Data.db size at R = 0.0 and 1.0 equal (about 128 MiB / 1.5 plus overhead); at R = 2.0 about 128 MiB plus 4 bytes per chunk (raw), i.e. larger than R = 0.0 by roughly one third. P2: sizes about 128 MiB plus per-chunk CRC for all R; R = 0.0 not smaller than R >= 1.0 by more than expansion (< 1 %). Compression-disabled table: about raw size, bigger than the compressed P1 tables; this is the positive control. No table at higher R is smaller than its R = 0.0 sibling.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Size(R=2.0) > Size(R=0.0) on P1; Size(R=1.0) ~ Size(R=0.0); P2 sizes within 1 % | Claim confirmed. |
| Size(R=2.0) < Size(R=0.0) on P1 by more than a few percent | Claim refuted: ratio shrinks disk. |
| Compression disabled table larger than compressed tables | Positive control moved. If it is not, the experiment is invalid. |
| Size(R=2.0) == Size(R=0.0) on P1 | Limit never reached (data too compressible or flush path used a different compressor); not confirmed. |
| CompressionInfo header shows the same max length for all tables | ALTER did not apply; discard. |

**B3h. Controls.** Same bytes and same row order in each table; compaction used so the writer sees table params (A3.1); compression-disabled control; `du` on Data.db only (excludes Index, Summary, commit log); one SSTable per table verified by `ls` before measuring; node restarted between P1 and P2 not needed.

**B4. Risks and cleanup.** Disk: about 128 MiB raw x 6 tables x 2 payloads, plus compaction transient (at most 2x), so under 3 GiB on local disk; point all directories to a known local path, never the shared home. Unit tier writes about 64 MiB x 15 files to a temp dir, deleted after each run. Cleanup: drop the keyspace, `nodetool clearsnapshot`, stop the node (`kill` the PID, then `pgrep -f CassandraDaemon` returns nothing), remove the local data, commit log and copied tree. Never build in the shared tree.

## C. Sources read

- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/INSTRUCTIONS.md
- .../scratchpad/agent-docs/playbook-autonomous.md and _TEMPLATE-autonomous.md
- .../scratchpad/agent-in/100.md
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/io/compress/CompressedSequentialWriter.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/schema/CompressionParams.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/DataComponent.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/io/compress/LZ4Compressor.java and ICompressor.java (grep excerpts)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/CompressedChunkReader.java, io/compress/CompressionMetadata.java, config/Config.java, metrics/TableMetrics.java (grep hits only)
- /users/jason92/cassandra-5.0.9/test/unit/org/apache/cassandra/io/compress/CompressedSequentialWriterTest.java (one grep hit)

## D. Stage-4 feedback

`none yet`
