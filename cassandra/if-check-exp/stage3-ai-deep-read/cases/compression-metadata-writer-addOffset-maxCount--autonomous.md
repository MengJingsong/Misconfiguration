# CompressionMetadata.Writer offsets-array growth trigger (`maxCount`) — verification solution  <!-- file: cases/compression-metadata-writer-addOffset-maxCount--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/io/compress/CompressionMetadata.java:366` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude (Sonnet 5.5), Claude Code CLI via Agent SDK, 2026-10-25 |
| Estimate | `negative`: line 366 is a capacity-doubling trigger, not a limit; the off-heap chunk-offset array grows without bound as (data written / chunk length), so usage does not follow `maxCount`. |
| Ground | `maxCount` is an internal, non-configurable growth threshold (initial 100, doubled whenever reached); nothing rejects, blocks or caps when it is hit. The memory it governs (8 bytes per chunk, native) is driven by data volume and `chunk_length_in_kb`, and it is small relative to heap/data. |

## A. Constraint trace

**A1. The constraint.** `maxCount`, an instance field of `CompressionMetadata.Writer` (kind: constant-like internal field, not settable). Declared `CompressionMetadata.java:346` (`private int maxCount = 100;`). Unit: number of 8-byte chunk offsets the current `SafeMemory` holds. Default 100 is a literal; the initial buffer is `new SafeMemory(maxCount * 8L)` (`:347`) = 800 bytes. Not settable via yaml, `-D`, or JMX; fixed at compile time. Its effective value is `100 * 2^k` after k doublings (`:368`).

**A2. What it caps.** Nothing; it is the current capacity of the off-heap offsets buffer (native memory allocated by `Memory` via `MemoryUtil.allocate`, `Memory.java:65`). The check at `:366` compares `count` (offsets added so far, `:348`) against `maxCount`. Resource touched: off-heap (native) memory, 8 bytes per chunk, during SSTable write; and later, on read, the same size loaded into `Memory` (`:202`) and reported by `offHeapSize()` (`:163-166`).

**A3. Mechanism.**
1. `CompressedSequentialWriter` opens one `CompressionMetadata.Writer` per SSTable (`CompressedSequentialWriter.java:103`) and calls `metadataWriter.addOffset(chunkOffset)` once per flushed chunk (`:183`).
2. `addOffset` (`CompressionMetadata.java:364-373`): if `count == maxCount` (`:366`) it allocates a copy at `(maxCount *= 2L) * 8L` bytes (`:368`; `offsets` is a `SafeMemory`, so the call is `SafeMemory.copy` (`SafeMemory.java:70-74`), which does `new SafeMemory(newSize)` and reaches `MemoryUtil.allocate` in the `Memory` constructor, `Memory.java:60-65`; `Memory.copy` (`:211-215`) is not the one called [Amended 2026-10-26, stage-4 audit: cite corrected]), closes the old buffer (`:369`), swaps (`:370`). Then writes the offset at `8L * count++` (`:372`).
3. Outcome when the "limit" is reached: capacity doubles. There is no rejection, error or back-pressure path. Peak transient native use during a doubling is old + new = 3x old capacity.
4. `doPrepare` (`:409`) trims the buffer to exactly `count * 8L` (`:415-418`) and writes `count` offsets to the `-CompressionInfo.db` file (`:425-427`) [Amended 2026-10-26, stage-4 audit: cite corrected from 426-427].
5. Overshoot: while writing, capacity is up to ~2x `count * 8` (slack). Latent bug-like edge: `maxCount` is `int`; `maxCount *= 2L` narrows silently. `100*2^24` = 1,677,721,600 still fits (int max 2,147,483,647); the next doubling (`100*2^25` = 3,355,443,200) wraps negative, so the overflow happens when `count` reaches 1,677,721,600 entries (a 13.4 GB offsets buffer). The `count` field is `int` (`:348`) and `finalizeLength` takes an `int` (`:401`); `Writer.chunkCount` (`:351`) is `long` and `CompressedSequentialWriter.chunkCount` is `int` (`CompressedSequentialWriter.java:59`). At 16 KiB chunks 1,677,721,600 entries is 25 TiB of uncompressed data per SSTable, unreachable in practice; at 1 KiB chunks 1.56 TiB. [Amended 2026-10-26, stage-4 audit: the write-up said overflow at k=24 / 2^30, and `:351` is `int`; both wrong]
6. Reader side: `readChunkOffsets` reads `chunkCount` (int) and allocates `chunkCount * 8L` (`:188-202`, allocate at `:202`); no cap either.

**A4. Other consumers.** Per-SSTable off-heap neighbors, all outside this field: bloom filter, index summary, partition index (off-heap), compression-info, chunk cache (`file_cache_size`, `conf/cassandra.yaml:753`), memtable off-heap pool (`memtable_offheap_space`, `conf/cassandra.yaml:799`), direct buffers of the compressed writer (`CompressedSequentialWriter.java:98`). The chunk count itself is fixed by `chunk_length_in_kb` (power of two, validated at `CompressionParams.java:448-451`; parsed `:345-360`; default `DEFAULT_CHUNK_LENGTH = 16 KiB`, `:48`).

**A5. Evidence beyond the source.** none. (Reader-side metric: `CompressionMetadataOffHeapMemoryUsed`, `TableMetrics.java:761-770`, sums `SSTableReader.getCompressionMetadataOffHeapSize()`, `SSTableReader.java:728-734`.)

## B. Verification solution

**B1. Claim under test.** The off-heap memory used for chunk offsets does not follow `maxCount`: capacity scales with number of chunks written (data size / chunk length), exceeds 100 entries without any rejection, and is only ever bounded by data volume, not by a cap.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a ~/cassandra-5.0.9/ /local/c509/`), `cd /local/c509 && ant jar` (or `ant build-test`). Test class placed only in the copy: `test/unit/org/apache/cassandra/io/compress/ChunkOffsetGrowthProbe.java` (same package, to use package-visible APIs; `Writer.open` is public so not strictly required). Run: `ant testsome -Dtest.name=org.apache.cassandra.io.compress.ChunkOffsetGrowthProbe`. JVM: test defaults, add `-Xmx1g`; no `-D` knobs needed.

**B2b. Knobs.** (i) N = number of `addOffset` calls: 99, 100, 101, 200, 201, 1_000, 65_536, 10_000_000. (ii) `chunkLength` in `CompressionParams.lz4(chunkLength)` (`CompressionParams.java:153`): 4096, 16384, 65536 for the datalength-to-count mapping in `Writer.open(long,long)`. Chosen to straddle the first threshold (100) and several doublings (100,200,400,...).

**B2c. Workload.** Create `CompressionMetadata.Writer w = Writer.open(CompressionParams.lz4(16384), file)`; loop `w.addOffset(i * 16384L)` N times. Arithmetic: capacity after N adds = 100*2^ceil(log2(N/100)) entries for N>100 (e.g. N=101 -> 200; N=65,536 -> 102,400; N=10M -> 13,107,200 entries = 104,857,600 B native) [Amended 2026-10-26, stage-4 audit: the write-up said 12,800,000 / 102.4 MB; 100*2^17 = 13,107,200]. Then `CompressionMetadata m = w.open(N * 16384L, N*16400L)` and read `m.offHeapSize()` (= current buffer size, untrimmed, `:165`). Separately `w.finalizeLength(N*16384L, N).prepareToCommit()` (`doPrepare`) and then `w.open(...).offHeapSize()` to see the trimmed value `N*8`.

**B2d. Observables and instruments.** `offHeapSize()` of the opened metadata (bytes) before and after prepare; private fields `maxCount`/`count` via reflection (read-only) to confirm the doubling sequence; native allocation watched with `-XX:NativeMemoryTracking=summary` + `jcmd <pid> VM.native_memory summary` (Cassandra's `Memory` uses Unsafe malloc, which NMT does not track, so use RSS from `/proc/<pid>/status` VmRSS as cross-check for the 10M case). Not directly observable: transient old+new peak at each doubling (only inferable from RSS sampling at 10 ms).

**B2e. Procedure.**
1. Build the copy; write the probe.
2. For each N in B2b(i): fresh Writer, add N offsets, record reflected `maxCount`, `count`, `open(...).offHeapSize()`.
3. Call `finalizeLength(...)` + `prepareToCommit()`; record trimmed `offHeapSize()` of a new `open`.
4. For the 10M case sample VmRSS before, during, after (`close()`/abort).
5. Repeat step 2 for chunk lengths 4096 and 65536 (offsets stored are the same; `open` count `tCount` differs via `dataLength/chunkLength`, `:446-450`; it sets only the `tCount * 8L` size field, while `offHeapSize()` reads `chunkOffsets.size()`, the buffer capacity).
6. Delete temp files; confirm no JVM left.

**B2f. Predictions.** N<=100: `maxCount`=100, offHeapSize 800. N=101: 200 / 1600. N=201: 400 / 3200. N=1000: 1600 / 12,800. N=65,536: 102,400 / 819,200. N=10M: 13,107,200 / 104,857,600 (the last doubling, from 6,553,600 entries, peaks at old + new = 157,286,400 B). N=200: 200 / 1600. N=100,000: 102,400 / 819,200. [Amended 2026-10-26, stage-4 audit: 10M row corrected; N=200 and N=100,000 rows added, both follow from the same rule] After prepare, offHeapSize == 8*N exactly. No exception for any N. Capacity is never held at 100: `count` exceeds `maxCount`'s initial value.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `count` passes 100 with no exception; capacity doubles per the table | Claim confirmed: line 366 is a growth trigger, not a cap |
| offHeapSize stays at 800 for N>100, or an exception/rejection at 100 | Claim wrong (it would be a limit) |
| Capacity tracks N (ratio capacity/(8N) between 1 and 2) | Usage follows data volume, not `maxCount` |
| Controls (B2h): C1 throws on the fixed 800-byte region, `addOffset` does not at the 101st offset, and C2 moves | Confirmed |
| N never exceeded 100, or C1 did not throw, or C2 did not move | Not confirmed |

**B2h. Controls.** [Rewritten 2026-10-26, stage-4 audit, before any reading: the original paragraph named a cache and a `com.github.benmanes`-free alternative that it never used, and its "positive control" was not defined. Claim, prediction and conclusion rows are unchanged.] There is no knob that binds this resource, so the controls show that the instrument tells a fixed bound from a doubling one, and that it moves both ways:
- **C1, fixed-size region (the bound that `addOffset` does not have).** In the same JVM and class, allocate `Memory.allocate(800)` (the size of the initial buffer) and call `setLong(800, x)`, the write `addOffset` would make as the 101st offset without the doubling. Expected: `AssertionError "Illegal bounds [800..808); size: 800"` from `Memory.checkBounds` (`Memory.java:198-202`, an `assert`, so it needs `-ea`, which `ant testsome` sets, `build.xml:511`/`:1160`/`:1517`). The 101st `addOffset` on a `Writer` does not throw.
- **C2, the reading moves with usage in both directions.** `offHeapSize()` rises with N along the B2f table and falls to `8*N` after `prepareToCommit()`.
- **C3, assertions on and off.** N=101 `addOffset` run by a plain `java` launch (the probe's `main`) with `-ea` and with `-da`: same capacity 200 and no exception in both. C1 is not run without `-ea` (the write would go past the allocation).
- **Gap named:** the controls do not show a cap binding the same resource, because none exists for `maxCount`; they show only that a bound would have been seen.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, built from the local copy (`ant jar`), data/commitlog/hints under `/local/c509/data` on a local disk with >=20 GiB free (run on a tmpfs, `/dev/shm`, which has >100 GiB free; the shared home disk had 36 GB free). `cassandra.yaml`: single `data_file_directories`, `commitlog_directory`, `hints_directory` on that filesystem; for the main arm `file_cache_enabled` stays at its default `false` (`conf/cassandra.yaml:742`); for the two control arms `file_cache_enabled: true` with `file_cache_size: 48MiB` and then `96MiB` [Amended 2026-10-26, stage-4 audit, before any reading: the original `file_cache_size: 64MiB` alone does nothing, because the chunk cache is off by default; and the cache holds `file_cache_size - 32 MiB` (`ChunkCache.java:49-50`), so 16 MiB would give a cache of size 0, which disables it (`:53`); 48 and 96 MiB give 16 and 64 MiB caches]; defaults otherwise. JVM: `-Xms2G -Xmx2G`, `-XX:MaxDirectMemorySize` default, `-XX:NativeMemoryTracking=summary`. Start: `bin/cassandra -f -R` in a background shell; wait for `nodetool status` UN.

**B3b. Knobs.** Table option `compression = {'class':'LZ4Compressor','chunk_length_in_kb': K}` with K in {64, 16, 4, 1}. There is no knob for `maxCount`; the claim is that it is irrelevant, so the varied quantity is chunk size (chunk count). Positive control: `file_cache_size` 16MiB vs 64MiB (binding cap).

**B3c. Workload.** `cassandra-stress` (from the same copy, `tools/bin/cassandra-stress`) write about 2 GB of data per K: `cassandra-stress write n=400000 -col size=FIXED(1000) -rate threads=16 -schema keyspace=ks<K>` (5 cells per row by default, `SettingsColumn.java:170`, so about 5.05 kB per row and 2.0 GB per keyspace; stress creates its own `standard1` only `IF NOT EXISTS`, `SettingsSchema.java:168`, so create each `ks<K>.standard1` first with `cqlsh`: `key blob PRIMARY KEY, "C0".."C4" blob` and `compression = {'class':'LZ4Compressor','chunk_length_in_kb':'<K>'}`); `nodetool flush`; read each SSTable's chunk count from its `-CompressionInfo.db` header; then `nodetool compact` per table. Uncompressed ~2.0 GB / K KiB chunks: K=64 -> ~31k chunks (~0.24 MiB); K=16 -> ~123k (~0.94 MiB); K=4 -> ~493k (~3.8 MiB); K=1 -> ~1.97M (~15 MiB); every SSTable has hundreds to millions of chunks against the initial 100. For the positive control, in two further node lifetimes on the same data (cache 48 MiB, then 96 MiB), run `cassandra-stress read n=100000 -col size=FIXED(1000) -pop dist=UNIFORM(1..400000) -rate threads=32 -schema keyspace=ks16` (about 0.5 GB read, more than either cache) and sample the chunk cache `Size` and `Capacity` [Amended 2026-10-26, stage-4 audit, before any reading: the write-up's `n=4000000` is about 20 GB per table, not 4 GiB, and 4 tables would not fit; its chunk counts 65k/262k/1.05M/4.2M assumed 4 GiB]

**B3d. Observables and instruments.** `nodetool tablestats <ks>.<table>` ("Compression metadata off heap memory used") and JMX `org.apache.cassandra.metrics:type=Table,keyspace=..,scope=..,name=CompressionMetadataOffHeapMemoryUsed` (via `nodetool sjk mx` or `jmxterm`), sampled after compaction and after restart. Process native memory: `jcmd <pid> VM.native_memory summary`, VmRSS from `/proc/<pid>/status` every 5 s. On-disk `*-CompressionInfo.db` size (`ls -l`; = header + 8*chunks) for ground truth. `nodetool info` "Off Heap Memory (MB)". Chunk-cache: JMX `org.apache.cassandra.metrics:type=Cache,scope=ChunkCache,name=Size` and `name=Capacity` (`CacheMetrics.java:69-70`). The doubling itself is seen with a Byteman rule at the `copy` call inside `CompressionMetadata$Writer.addOffset` (one trace line per doubling: `maxCount`, `count`, the file), main arm only. Not observable by sampling: the writer's transient buffer (gone after prepare); only the Byteman trace shows its sizes.

**B3e. Procedure.**
1. Build, copy, start node, create keyspace (RF 1) and four tables with K = 64,16,4,1.
2. Stress-write each; flush; compact; record `CompressionMetadataOffHeapMemoryUsed` and `CompressionInfo.db` sizes.
3. Restart the node; re-record (reader loads `readChunkOffsets`, `:190-202`).
4. Read the Byteman doubling trace for the flushes and the K=1 compaction (writer growth path at `:366`); sample VmRSS during that compaction for the record (not a pass/fail reading).
5. Positive control: two further lifetimes on the same data directory with `file_cache_enabled: true` and `file_cache_size` 48MiB, then 96MiB (caches of 16 and 64 MiB); run the read stress and record the chunk cache `Size` (every 2 s) and `Capacity`.
6. `nodetool drain`, stop the node, no `CassandraDaemon` left, delete the data directory.

**B3f. Predictions.** Metric = 8 * (sum over live SSTables of the chunk count in the `-CompressionInfo.db` header) exactly (reader buffers are trimmed to the file's count, `readChunkOffsets` `:202`), and each SSTable's `-CompressionInfo.db` is that count * 8 plus a header. With about 2.0 GB per keyspace (+-15%) the metric is about 0.24, 0.94, 3.8 and 15 MiB for K=64,16,4,1, scaling about 4x per K step, thousands of times the 800-byte initial buffer, with no error in `system.log`. The Byteman trace shows each writer's `maxCount` going 100 -> 200 -> 400 ... with each new value 2x the last. Chunk cache `Size` plateaus at or just under `Capacity` = `file_cache_size` - 32 MiB (16 MiB, then 64 MiB) while the offsets metric stays at its own value (control). [Amended 2026-10-26, stage-4 audit, before any reading: the transient-RSS prediction (~3x final, ~100 MiB) was arithmetically wrong (the last doubling of a 1.97M-chunk writer peaks at about 20 MB over the final 15 MiB) and not resolvable by 5-s sampling; replaced by the trace]

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Metric scales with 1/K and total data, far above 800 bytes, no errors | Claim confirmed (usage does not follow `maxCount`) |
| Metric plateaus near a fixed value independent of data size | Claim refuted (a cap exists) |
| Writer errors/stalls when crossing 100, 200, ... chunks | Claim refuted |
| Chunk cache `Size` plateaus at `Capacity` (= `file_cache_size` - 32 MiB) while offsets metric grows | Positive control binds; claim confirmed |
| Chunk cache does not move, or metric does not scale with K (e.g. compaction produced tiny SSTables, <100 chunks) | Not confirmed; enlarge data |

**B3h. Controls.** Same data volume (n=100,000 rows) in an uncompressed table (`compression = {'enabled':'false'}`; metric must be 0, `SSTableReader.java:730-731`); identical workload with K varied only; compare `CompressionInfo.db` size to metric to exclude measurement error; the cache control (`file_cache_size`) as the known binding cap; repeat after restart to separate writer-side from reader-side allocation.

**B4. Risks and cleanup.** Disk/tmpfs: ~2 GB x 4 tables plus compaction headroom, ~12 GiB, local only (`df` before). Unit tier 10M case uses ~105 MB native, peak ~157 MB. Stop the stress and Cassandra processes, `pgrep -fl 'cassandra|stress'` must be empty; `rm -rf /local/c509`. Do not build or write in the shared tree.

## C. Sources read

- ~/writeup-A/playbook-autonomous.md
- ~/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/io/compress/CompressionMetadata.java
- src/java/org/apache/cassandra/io/compress/CompressedSequentialWriter.java
- src/java/org/apache/cassandra/io/util/Memory.java
- src/java/org/apache/cassandra/io/util/SafeMemory.java
- src/java/org/apache/cassandra/schema/CompressionParams.java
- src/java/org/apache/cassandra/io/sstable/format/SSTableReader.java
- src/java/org/apache/cassandra/metrics/TableMetrics.java
- conf/cassandra.yaml

## D. Stage-4 feedback

2026-10-26, stage 4 (results: `stage4-runtime-verification/results/compression-metadata-writer-addOffset-maxCount--autonomous.md`, no commit yet). Design audit: Ready after amendments; the amendments are dated in the text (A3.2, A3.4, A3.5, B2c, B2f, B2h, B2g, B3a-B3h, B4). Unit tier: Confirmed, does not cap (27 cells, N from 99 to 10,000,000: capacity 100 x 2^ceil(log2(N/100)), `offHeapSize()` 8 x capacity before and 8N after `prepareToCommit()`, no exception; C1 fixed 800-byte region throws, `addOffset` does not). Cluster tier: Confirmed, does not cap (four chunk lengths, 2.0 GB per keyspace: the metric is exactly 8 x the header chunk count, 0.25 / 0.99 / 3.96 / 15.8 MB for K=64/16/4/1; a Byteman trace shows 528 doublings in 64 writers, largest capacity 3,276,800; chunk-cache control filled 16 and 64 MiB while the metric stayed flat). Outcome class: true negative. The estimate stands. Notes: the control is a different consumer, not a cap on this resource; the +1 header chunk in compacted files and the 11 % flush-versus-compact data-length difference were observed and not explained.
