# min_compress_ratio — verification solution  <!-- file: cases/min_compress_ratio-flushdata-maxcompressedlength-2--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`CompressedSequentialWriter.java:163`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/compress/CompressedSequentialWriter.java#L163) (`if (uncompressedLength >= maxCompressedLength)`, inside `flushData()`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: `min_compress_ratio` decides, per chunk, whether to store the chunk compressed or raw. It does not bound heap, off-heap or total disk. If anything, a higher ratio makes SSTables larger on disk. |
| Ground | The check only picks between two representations of one chunk, and the raw representation is never smaller than the compressed one when the check fires (the check fires when the compressed length is at least `maxCompressedLength`). Buffers are sized from the chunk length and the compressor, not from `maxCompressedLength` (CompressedSequentialWriter.java:98). The stored chunk is bounded by `chunkLength` whatever the ratio. The option trades disk for read CPU, so it is not a cap. |

## A. Constraint trace

**A1. The constraint.** `min_compress_ratio`: a per-table CQL compression sub-option (not a cassandra.yaml key, not a `-D` property, no JMX setter). It is turned into the derived integer `maxCompressedLength` (bytes), the largest compressed chunk size still worth storing compressed.
- Option name declared at [`CompressionParams.java:57`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/CompressionParams.java#L57) (`MIN_COMPRESS_RATIO = "min_compress_ratio"`).
- Default declared at [`CompressionParams.java:49`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/CompressionParams.java#L49) (`DEFAULT_MIN_COMPRESS_RATIO = 0.0`); the comment at lines 49-51 says it stays 0.0 because pre-4.0 versions do not understand the parameter. The value is read from the option map in `removeMinCompressRatio` (CompressionParams.java:384-392; `Double.parseDouble` at 389, default returned at 391) and called from `fromMap` (CompressionParams.java:95).
- Unit: dimensionless ratio (chunk length / compressed length). Derived value `maxCompressedLength` is in bytes: `(int) Math.ceil(Math.min(chunkLength / minCompressRatio, Integer.MAX_VALUE))` (CompressionParams.java:187-190). With the default 0.0 the division gives infinity, so the result is `Integer.MAX_VALUE`. With the default chunk length `DEFAULT_CHUNK_LENGTH` = 16 KiB (CompressionParams.java:48) and ratio 1.1 it is 14894 bytes (arithmetic from the formula).
- Validation (CompressionParams.java:453-457): `maxCompressedLength` must be non-negative and, unless it is `Integer.MAX_VALUE`, at most `chunkLength`; i.e. ratio is 0 or at least 1.
- Setting: CQL `CREATE TABLE ... WITH compression = {'class': 'LZ4Compressor', 'min_compress_ratio': 1.1}` or `ALTER TABLE`. No restart; applies to SSTables written afterwards. Existing SSTables keep the value stored in their `-CompressionInfo.db` (written at CompressionMetadata.java:389). The earlier trace cited CompressionParams.java:520 for this; that line is the inter-node `Serializer.serialize` (messaging), not the SSTable component, so the earlier citation was wrong.

**A2. What it caps.** Nothing in memory. The quantity compared is the length in bytes of the chunk just produced: `compressedLength = compressed.position()` (CompressedSequentialWriter.java:157) and `uncompressedLength = buffer.position()` (CompressedSequentialWriter.java:156) against `maxCompressedLength` (field at CompressedSequentialWriter.java:68, assigned at line 100). Resource touched: disk bytes of the SSTable `Data.db` file (and read-time CPU). It is a threshold for "compression is worth it", not a limit on a resource total.

**A3. Mechanism.** In `flushData()` (CompressedSequentialWriter.java:140 onward; the method header is at line 140, not re-counted here beyond the lines cited):
1. Compress `buffer` into `compressed` (CompressedSequentialWriter.java:148-150, via the `compressor.compress` call just before 156).
2. Read both lengths (lines 156-157) and add the uncompressed length to `uncompressedSize` (line 158).
3. Outer check at CompressedSequentialWriter.java:160, `if (compressedLength >= maxCompressedLength)`: compression did not save enough; write the raw `buffer` (line 162) instead of `compressed`.
4. Entry-pointer check, [`CompressedSequentialWriter.java:163`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/compress/CompressedSequentialWriter.java#L163), `if (uncompressedLength >= maxCompressedLength)`:
   - True (a full chunk, the normal case): record `compressedLength = uncompressedLength` (line 165), i.e. store the raw chunk.
   - False (only a short last chunk, per the comment at lines 168-170): zero-pad the raw data up to `maxCompressedLength` (lines 172-175), so that readers can tell by length that the chunk is stored uncompressed.
5. If the outer check at line 160 is false, the compressed bytes are written and `compressedLength` stays as compressed.
6. Add `compressedLength` to `compressedSize` (line 177); write the chunk, its offset in `CompressionInfo` and its CRC (lines 182-195); advance `chunkOffset += compressedLength + 4` (line 205).
Read side: `CompressedChunkReader.java:269` and `:364` take `chunk.length < maxCompressedLength` as "compressed, decompress it"; otherwise the bytes are used as is. `CompressedSequentialWriter.java:265` does the same when the writer reopens a chunk.
Bypass / overshoot: with the default (`Integer.MAX_VALUE`) the check at 160 is never true, so every chunk is stored compressed, whatever the saving. A chunk stored raw is as large as the chunk length, which is larger than its compressed form; so a nonzero ratio can only increase disk use relative to ratio 0. The padding path can make the last chunk up to `maxCompressedLength` bytes instead of its actual short length.

**A4. Other consumers.** Disk: all other SSTable components, commit log, hints, snapshots, other tables. Memory: the writer's `buffer` and `compressed` buffers are sized from the chunk length and the compressor (CompressedSequentialWriter.java:98), plus chunk cache, bloom filters and index summaries. None of them depends on `maxCompressedLength`. (Not verified: the exact buffer type per compressor.)

**A5. Evidence beyond the source.** In-tree unit tests exist that exercise `maxCompressedLength`: `test/unit/org/apache/cassandra/io/compress/CompressedSequentialWriterTest.java` (uses `compressionParameters.maxCompressedLength()` at line 195) and `CompressionMetadataTest.java`, `CQLCompressionTest.java` in the same directory (listed, not read). Public docs: the Cassandra compression documentation for the `min_compress_ratio` table option (https://cassandra.apache.org/doc/5.0/cassandra/developing/cql/ddl.html#compression, content not re-verified in this session). No issue numbers cited.

## B. Verification solution

**B1. Claim under test.** Raising `min_compress_ratio` does not reduce the bytes a table's SSTable data occupies (or any heap/off-heap use): for compressible-but-not-highly-compressible data, on-disk `Data.db` size at ratio R >= 1 is greater than or equal to the size at ratio 0, and never smaller; the option's only effect is the compressed/raw choice per chunk. Falsified if any ratio produces a smaller `Data.db` than ratio 0 for the same data, or if memory use varies with the ratio.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a /users/jason92/cassandra-5.0.9/ $WORK/c5/`), build there: `cd $WORK/c5 && ant jar`. Write a small JUnit test in `$WORK/c5/test/unit/org/apache/cassandra/io/compress/` modelled on `CompressedSequentialWriterTest` (existing test, not copied here); run with `ant testsome -Dtest.name=<Class> -Dtest.methods=<method>`. Default test JVM options.

**B2b. Knobs.** `min_compress_ratio` in `CompressionParams.fromMap` / `CompressionParams.lz4(chunkLength, maxCompressedLength)`: values 0.0 (default), 1.0, 1.1, 2.0, 4.0 with chunk length 16384. Resulting `maxCompressedLength`: MAX_VALUE, 16384, 14894, 8192, 4096 (formula at CompressionParams.java:187-190).

**B2c. Workload.** Write 64 chunks (1 MiB) per ratio through `CompressedSequentialWriter` with three data kinds: (a) zeros (compress to far below 4096 bytes per chunk), (b) text-like data with about 1.5x compressibility (build by mixing repeated words with random bytes; calibrate with `LZ4Compressor` first so each chunk compresses to about 10-11 KiB), (c) random bytes (incompressible). Also write one final partial chunk of 1000 bytes to reach the padding branch (line 172-175).

**B2d. Observables and instruments.** Per run: `Data.db` file length; each chunk length in `CompressionInfo` via `CompressionMetadata.chunkFor` / `.Chunk.length`; count of chunks with length >= `maxCompressedLength` (raw); `compressedSize` (not exposed publicly: observe via file length). Memory: `compressed.capacity()` through reflection (field at CompressedSequentialWriter.java:56) and `Runtime` used-heap before/after with `System.gc()`. Cannot be observed directly: allocation done inside the compressor library.

**B2e. Procedure.**
1. For each data kind and each ratio, write the 1 MiB plus tail file in a fresh temp dir on local disk.
2. Record file length, per-chunk lengths, raw-chunk count, `compressed.capacity()`.
3. Repeat with compression disabled (`CompressionParams.noCompression()`, positive control: on-disk size known to follow the compression switch) and with chunk length 4096 vs 16384 for the zeros kind.
4. Delete temp dirs.

**B2f. Predictions.** (a) zeros: file length identical at every ratio (compressed far below every threshold). (b) 1.5x data: at ratio 0 and 1.0 about 2/3 of the raw size; at ratio 2.0 and 4.0 every chunk is stored raw, so file length is about the raw size plus per-chunk CRC (4 bytes each), larger than at ratio 0. (c) random: all chunks raw at ratio >= 1.0, size about the raw size at every ratio; at ratio 0 about the raw size plus compressor overhead, slightly larger or equal. `compressed.capacity()` identical across all ratios. The tail chunk is padded to `maxCompressedLength` when 1000 < `maxCompressedLength`.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| File length at ratio R >= 1 equals or exceeds ratio 0, `compressed.capacity()` constant | Claim confirmed: not a cap |
| File length at some ratio smaller than ratio 0 for the same bytes | Claim refuted: ratio shrinks disk |
| `compressed.capacity()` or heap delta varies with ratio | Claim refuted for memory |
| noCompression file length moves (about raw size) while ratio runs stay flat for zeros | Positive control works |
| No chunk reaches the raw branch at any ratio (raw-chunk count 0 for kinds b, c) | Limit never reached: not confirmed; recalibrate data |
| noCompression control does not change size | Control did not move: not confirmed |

**B2h. Controls.** Same bytes and same chunk length across ratios; compression-off and chunk-length controls show the harness can see disk change; data kind (a) shows the check is not reached when compression is good; compare against ratio 0 as baseline.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, local copy built with `ant jar`. `cassandra.yaml`: `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory` on a local disk of known free size (at least 5 GiB); `-Xms2G -Xmx2G` in `conf/jvm11-server.options`; `commitlog_sync` default; auto-snapshot off in the test keyspaces by dropping them at the end.

**B3b. Knobs.** Four tables with identical schema (`id uuid primary key, v blob`), differing only in compression: T0 `{'class':'LZ4Compressor'}` (ratio 0); T1 `{'class':'LZ4Compressor','min_compress_ratio':1.1}`; T2 `{'class':'LZ4Compressor','min_compress_ratio':2.0}`; TC control `{'enabled':'false'}` (positive control). Set by `CREATE TABLE` with `WITH compression`.

**B3c. Workload.** Insert 200000 rows of 2 KiB `v` each (about 400 MB raw) into each table, with `v` generated so it compresses about 1.5x (same generator for all tables, same seed, e.g. cassandra-stress user profile or a small driver script). Then `nodetool flush` and `nodetool compact` on each table. Duration: tens of minutes.

**B3d. Observables and instruments.** Disk: `nodetool tablestats <ks>.<t>` ("Space used (live)", "SSTable Compression Ratio") and `du -sb` of each table's data directory (`*-Data.db` and `*-CompressionInfo.db`). Memory: `nodetool info` heap and off-heap, `jcmd <pid> GC.heap_info`, `nodetool tablestats` off-heap lines (bloom filter, index summary, compression metadata). Cannot be observed directly: the writer's transient buffers (too short-lived), covered by the unit tier.

**B3e. Procedure.**
1. Start the node; create keyspace and the four tables.
2. For each table: load, flush, compact, record B3d values.
3. Run `nodetool compact` again on T1 after `ALTER TABLE ... min_compress_ratio = 0.0` is not needed; instead create one more table T3 identical to T1 but with chunk length 4 KiB (`chunk_length_in_kb: 4`) as a second control.
4. Drop the keyspace, stop the node (`nodetool drain`; `kill`), check `pgrep -f CassandraDaemon` is empty.

**B3f. Predictions.** Space used: TC about the raw size; T0 about 2/3 of raw; T1 equal to T0 within a small margin (chunks compress to about 10-11 KiB, below 14894); T2 about the raw size (every chunk raw), so T2 is larger than T0. Heap and off-heap equal across T0, T1, T2 within noise, except compression-metadata off-heap which tracks chunk count, not the ratio. No table is smaller than T0.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| T2 >= T0 in disk, off-heap equal | Claim confirmed |
| T1 or T2 smaller than T0 | Claim refuted |
| Heap or off-heap differs between T0, T1, T2 beyond noise | Refuted for memory (check compression metadata first) |
| TC moves to about the raw size while T0 to T2 do not follow any cap | Positive control works; usage follows compression, not the ratio |
| T2 equals T0 (no chunk reached the raw branch) | Limit never reached: not confirmed; lower data compressibility |
| TC equals T0 | Control did not move: not confirmed |

**B3h. Controls.** Same data and seed for all tables; same flush/compact schedule; TC (compression off) and T3 (chunk length) show the instruments detect disk change; repeat with a second seed.

**B4. Risks and cleanup.** Disk: about 4 x 400 MB raw plus compaction headroom, so keep at least 5 GiB free on the local volume; never use shared storage; unit-tier temp files are small and deleted at step 4. Processes: the Ant test JVM and the Cassandra daemon must both be stopped; check with `pgrep -f "CassandraDaemon|ant"`. Cleanup: drop keyspace, `rm -rf` the local data, commitlog, hints and the copied source tree.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/io/compress/CompressedSequentialWriter.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/schema/CompressionParams.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/CompressedChunkReader.java (lines 262-272 only)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/io/compress/CompressionMetadata.java (grep only)
- /users/jason92/cassandra-5.0.9/test/unit/org/apache/cassandra/io/compress/ (directory listing and grep of CompressedSequentialWriterTest.java)
- /users/jason92/cassandra-5.0.9/conf/cassandra.yaml (grep only, no min_compress_ratio entry found)

## D. Stage-4 feedback

none yet
