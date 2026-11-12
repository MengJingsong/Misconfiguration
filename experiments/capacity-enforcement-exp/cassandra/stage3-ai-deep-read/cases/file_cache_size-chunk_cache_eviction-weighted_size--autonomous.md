<!-- file: cases/file_cache_size-chunk_cache_eviction-weighted_size--autonomous.md -->
# file_cache_size (less RESERVED_POOL_SPACE_IN_MiB) — verification solution  <!-- file: cases/file_cache_size-chunk_cache_eviction-weighted_size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (a capacity derivation, not an if statement), **linked**: [`ChunkCache.java:49`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/ChunkCache.java#L49) — `public static final int RESERVED_POOL_SPACE_IN_MiB = 32;` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code autonomous subagent, 2026-11-11 |
| Estimate | `positive`: the 32 MiB constant is subtracted from `file_cache_size` to give the chunk cache's Caffeine `maximumWeight`, whose weigher is each cached buffer's byte capacity, so the off-heap bytes the chunk cache retains are capped at `file_cache_size − 32 MiB`, and the chunk-cache buffer pool's slabs are capped at `file_cache_size`. The "reserve" itself is only headroom and is not guaranteed to other pool users; overshoot is limited to transient Caffeine lag, evicted-but-referenced buffers, and unpooled overflow allocations. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- **The given line** is a hard-coded constant, `RESERVED_POOL_SPACE_IN_MiB = 32`, declared at [`ChunkCache.java:49`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/ChunkCache.java#L49). It cannot be set: there is no yaml key, `-D` property or JMX setter.
- **What it feeds:** the chunk cache's effective capacity, computed at class load:
  `cacheSize = 1024L*1024L*Math.max(0, DatabaseDescriptor.getFileCacheSizeInMiB() - RESERVED_POOL_SPACE_IN_MiB)` ([`ChunkCache.java:50`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/ChunkCache.java#L50)). The unit is bytes; the yaml value is in MiB.
- **The settable constraint** is the configuration entry `file_cache_size`, declared at [`Config.java:497`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L497). It has the type `DataStorageSpec.IntMebibytesBound`, and the deprecated old name `file_cache_size_in_mb` is still accepted (Config.java:496).
  - **Default:** if unset, `min(512, maxHeap / 4 MiB)` MiB (DatabaseDescriptor.java:576-577). The getter is DatabaseDescriptor.java:3784-3793. The yaml comment at conf/cassandra.yaml:744-753 says "32MB of this are reserved for pooling buffers, the rest is used for chunk cache".
  - **How it is set:** in `cassandra.yaml` as `file_cache_size: <N>MiB`. It is read once into `static final` fields, so a change needs a restart. `ChunkCache.setCapacity` throws `UnsupportedOperationException` (ChunkCache.java:310-314).
- **Gating:** the cache exists only if `file_cache_enabled` is true and `cacheSize > 0` (ChunkCache.java:53-54).
  - `file_cache_enabled` is declared at Config.java:499, defaults to the system property `cassandra.file_cache_enabled` (CassandraRelevantProperties.java:227), and is **false by default** (conf/cassandra.yaml:742, CASSANDRA-16036 in CHANGES.txt:1406).
  - With `file_cache_size ≤ 32MiB`, `cacheSize = 0` and the cache is disabled.
- **The same `file_cache_size` also sets the threshold of the chunk-cache `BufferPool`:** `FILE_MEMORY_USAGE_THRESHOLD = getFileCacheSizeInMiB()*1 MiB`, with no subtraction (BufferPools.java:38-39). The 32 MiB difference between the two limits is the "reserved pool space".

**A2. What it caps.**
- **Resource:** off-heap (direct) memory used for uncompressed SSTable chunks.
- **Quantity compared (cache):** Caffeine's weighted size, which is the sum over cached entries of `buffer.capacity()` (weigher, ChunkCache.java:154), compared against `maximumWeight(cacheSize)` (ChunkCache.java:152). It is exposed as metric `org.apache.cassandra.metrics:type=Cache,scope=ChunkCache,name=Size` (CacheMetrics.java:70 → `ChunkCache.weightedSize()`, ChunkCache.java:322-328), with `Capacity` = `cacheSize` (ChunkCache.java:304-308), and as `system_views.caches` row `chunks` (CachesTable.java:74-75).
- **Quantity compared (pool):** `memoryAllocated + MACRO_CHUNK_SIZE` (1 MiB slabs) against `memoryUsageThreshold = file_cache_size` (BufferPool.java:443).

**A3. Mechanism.**
1. **Wrapping.** Each data file's `FileHandle` is wrapped by the cache only if the cache is enabled. Compressed files, both standard and mmap, go through `maybeCached` (FileHandle.java:411, 424); uncompressed non-mmapped files also do (FileHandle.java:428-429). The check that decides this is [`FileHandle.java:446`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/FileHandle.java#L446): `if (chunkCache != null && chunkCache.capacity() > 0)`. Uncompressed mmapped files and indexes under the default `disk_access_mode: mmap_index_only` (Config.java:122) are **not** cached (FileHandle.java:413-418).
2. **Read path.** A read calls `CachingRebufferer.rebuffer(position)`, which calls `cache.get(Key)` and then `reference()` (ChunkCache.java:241). On a miss, `load` takes a buffer of `chunkSize` from the chunk-cache pool and reads the chunk into it (ChunkCache.java:163-168). Chunk size is the compression `chunk_length`, 16 KiB by default (CompressionParams.java:48), or a power of two ≤ 64 KiB for uncompressed files (DiskOptimizationStrategy.java:63-72).
3. **Cache limit check.** It is configured at [`ChunkCache.java:152`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/ChunkCache.java#L152) (`.maximumWeight(cacheSize)`), with the weigher at [`ChunkCache.java:154`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/ChunkCache.java#L154). The comparison itself is inside Caffeine 3.1.8 (.build/parent-pom-template.xml:1061), not in the tree. After each write Caffeine evicts entries until the weighted size is ≤ `maximumWeight`. The maintenance runs synchronously because the executor is `ImmediateExecutor` (ChunkCache.java:153).
   - **On eviction:** `onRemoval` → `Buffer.release()` → `bufferPool.put(buffer)` when the reference count reaches 0 (ChunkCache.java:177-181, 139-144).
   - **Outcome at the limit:** the cache never refuses an insert; it evicts older entries.
4. **Pool limit check.** It is at [`BufferPool.java:443`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L443): `if (cur + MACRO_CHUNK_SIZE > memoryUsageThreshold)`.
   - **Within the limit:** a new 1 MiB direct slab is allocated (BufferPool.java:452-460).
   - **At the limit:** it logs "Maximum memory usage reached" and returns null. The caller then falls back to an **unpooled** `ByteBuffer.allocateDirect(size)` counted as overflow (BufferPool.java:904-923 → 233-238).
   - **Slabs are never freed:** `memoryAllocated` never decreases, so the pool's `Size` stays at its peak.
5. **Overshoot and bypass paths:**
   - (a) Caffeine may exceed `maximumWeight` transiently while evicting ([Caffeine javadoc](https://www.javadoc.io/doc/com.github.ben-manes.caffeine/caffeine/3.1.8/com.github.benmanes.caffeine/com/github/benmanes/caffeine/cache/Caffeine.html#maximumWeight(long))).
   - (b) An evicted buffer still referenced by a reader is returned to the pool only on its last `release()` (ChunkCache.java:139-144). This is bounded by the number of concurrent readers × chunk size.
   - (c) If the pool cannot serve a request (exhausted or fragmented), the cached buffer is an overflow direct buffer. It still counts toward the cache weight, so the cache cap holds, but pool slabs (≤ `file_cache_size`) plus cached overflow buffers can together exceed `file_cache_size`.
   - (d) **The 32 MiB "reserve" is not enforced:** it is first-come headroom shared with other users of the same pool (A4). Nothing stops the cache's buffers from occupying that headroom when fragmentation or pinned buffers push slab use higher.
   - (e) On-heap per-entry overhead (Key, Buffer, Caffeine node, ~128 B per chunk according to cassandra.yaml:748-749) is not counted.

**A4. Other consumers.**
- **Same chunk-cache pool, not cache-capped:**
  - `BufferManagingRebufferer` buffers for uncached readers (BufferManagingRebufferer.java:45, 52);
  - hints decompression (CompressedChecksummedDataInput.java:35).
- **Other off-heap users:**
  - the networking pool, `networking_cache_size` (BufferPools.java:44-45);
  - off-heap memtables;
  - bloom filters, index summaries and compression metadata;
  - mmapped index/data regions (OS page cache, not direct memory);
  - the JDK's own temporary direct buffers for NIO.

**A5. Evidence beyond the source.**
- conf/cassandra.yaml:740-753 (the "32MB reserved for pooling buffers" comment).
- CHANGES.txt:1406 (CASSANDRA-16036, cache disabled by default), CHANGES.txt:2911 (CASSANDRA-5863, chunk cache), CHANGES.txt:2238 (CASSANDRA-13897).
- Caffeine `maximumWeight` javadoc (link above).
- https://issues.apache.org/jira/browse/CASSANDRA-5863
- https://issues.apache.org/jira/browse/CASSANDRA-16036

## B. Verification solution

**B1. Claim under test.**
- With `file_cache_enabled: true` and `file_cache_size = F` MiB (F > 32), the chunk cache's retained bytes (`ChunkCache.weightedSize()` / `size_bytes`) plateau at, and never exceed by more than a few chunks, `(F − 32) MiB`, not `F` MiB, however much data is read.
- The node's direct memory attributable to the chunk cache follows `F − 32`. The claim is wrong if the weighted size or the direct-memory delta grows past `(F − 32) MiB` + a small number of chunks, or plateaus at `F` instead of `F − 32`.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 11, Ant. Copy the tree to local disk and build there:
  `rsync -a /users/jason92/cassandra-5.0.9/ /local/ccprobe/cassandra/ && cd /local/ccprobe/cassandra && ant jar build-test`
- Add the test at `test/unit/org/apache/cassandra/cache/ChunkCacheCapProbeTest.java` in the **copy** only.
- JVM options: the defaults of `ant testsome`. Unit tests in build.xml set `-Djava.io.tmpdir=${tmp.dir}` under the copy (build.xml:1161).

**B2b. Knobs.**
- `file_cache_size` F ∈ {32, 33, 64, 160} MiB, passed through the environment variable `PROBE_FCS`. The test reads it and injects it with `DatabaseDescriptor.daemonInitialization(Supplier<Config>)` (DatabaseDescriptor.java:250).
- `file_cache_enabled = true` in all runs.
- Why these values:
  - 32: boundary, `cacheSize = 0`, so the instance is null.
  - 33: smallest cache, 1 MiB.
  - 64: distinguishes cap = F−32 (32 MiB) from cap = F (64 MiB).
  - 160: cap 128 MiB, which shows proportionality.
- Because `cacheSize` is `static final`, each F needs a fresh JVM. Run `ant testsome` once per value.

**B2c. Workload.** A 256 MiB random-bytes file written into `build/tmp`. Open it with `new FileHandle.Builder(file).withChunkCache(ChunkCache.instance).bufferSize(65536).complete()`, which gives an uncompressed `SimpleChunkReader` with chunkSize 65536, cached (FileHandle.java:426-429). Read it sequentially in 64 KiB steps with `createReader()`, `seek`, `readFully`.
- That is 4096 distinct chunks, 256 MiB, which is ≥ 2× the largest cap (128 MiB). Every cap is crossed.
- Then make a second pass in random order, so hits and misses are mixed.

Test body sketch:
```java
@BeforeClass public static void init() {
  int f = Integer.parseInt(System.getenv().getOrDefault("PROBE_FCS", "64"));
  DatabaseDescriptor.daemonInitialization(() -> { Config c = DatabaseDescriptor.loadConfig();
      c.file_cache_size = new DataStorageSpec.IntMebibytesBound(f); c.file_cache_enabled = true; return c; });
}
@Test public void fill() throws Exception {
  if (ChunkCache.instance == null) { System.out.println("PROBE instance=null cacheSize=" + ChunkCache.cacheSize); return; }
  File f = FileUtils.createTempFile("ccprobe", ".bin");      // write 256 MiB of random bytes with FileChannel
  long maxW = 0; long maxE = 0;
  try (FileHandle fh = new FileHandle.Builder(f).withChunkCache(ChunkCache.instance).bufferSize(65536).complete();
       RandomAccessReader r = fh.createReader()) {
    byte[] b = new byte[65536];
    for (long p = 0; p < fh.dataLength(); p += 65536) { r.seek(p); r.readFully(b);
      maxW = Math.max(maxW, ChunkCache.instance.weightedSize()); maxE = Math.max(maxE, ChunkCache.instance.size()); }
    // second pass: random positions, same sampling
  }
  BufferPool pool = BufferPools.forChunkCache();
  System.out.printf("PROBE F=%s cap=%d maxW=%d maxE=%d poolSize=%d poolUsed=%d overflow=%d%n", System.getenv("PROBE_FCS"),
      ChunkCache.instance.capacity(), maxW, maxE, pool.sizeInBytes(), pool.usedSizeInBytes(), pool.overflowMemoryInBytes());
  f.delete();
}
```

**B2d. Observables and instruments.** Each run prints a single `PROBE` line. Run the probe once per F.
- Measured:
  - `ChunkCache.instance.capacity()`;
  - `weightedSize()` and `size()`, sampled after every 64 KiB read, recording the maximum;
  - final `BufferPool.sizeInBytes()`, `usedSizeInBytes()` and `overflowMemoryInBytes()` for the chunk-cache pool.
- Not observable here: the transient weight inside a Caffeine write before eviction (sampling happens only between reads), and the process's real direct memory (that is the cluster tier).

**B2e. Procedure.**
1. `cd /local/ccprobe/cassandra`
2. `for F in 32 33 64 160; do PROBE_FCS=$F ant testsome -Dtest.name=org.apache.cassandra.cache.ChunkCacheCapProbeTest > probe-$F.log 2>&1; grep PROBE probe-$F.log; done`
3. `ls build/tmp` to check that no `ccprobe*.bin` is left. Delete any leftover.

**B2f. Predictions.**

| F (MiB) | capacity (bytes) | max weightedSize | max entries | pool Size | overflow |
|---|---|---|---|---|---|
| 32 | instance null, cacheSize 0 | — | — | — | — |
| 33 | 1,048,576 | ≤ 1,048,576 (+ ≤ 1 chunk, 65,536) | ≤ 16 (+1) | ≤ 33 MiB (34,603,008) | 0 |
| 64 | 33,554,432 | ≤ 33,554,432 (+ ≤ 65,536), and ≥ 33,554,432 − 65,536 after the first pass | ≤ 512 (+1) | ≥ 32 MiB and ≤ 67,108,864 | 0 |
| 160 | 134,217,728 | ≤ 134,217,728 (+ ≤ 65,536), reaching it | ≤ 2048 (+1) | ≥ 128 MiB and ≤ 167,772,160 | 0 |

Max weightedSize ∝ (F − 32), while the data read is constant at 256 MiB.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| maxW plateaus at (F−32) MiB for 33/64/160; instance null at 32 | claim confirmed (cache operand capped at F−32) |
| maxW plateaus at F MiB (e.g. 64 MiB for F=64) | reserve not applied: claim wrong for the given line |
| maxW > (F−32) MiB + a few chunks, or grows toward 256 MiB | cap not enforced: claim refuted |
| maxW well below the cap for all F (never reached) | workload did not reach the limit: not confirmed, so enlarge the file |
| overflow > 0 or pool Size > F MiB | pool bypass (A3 5c) observed: cache cap may hold while pool-attributed memory exceeds F; record it |
| positive control: maxW at F=160 ≈ 4× maxW at F=64 for the same 256 MiB read | the workload moves the operand and the knob governs it |

**B2h. Controls.**
- F=32 (cache disabled) is the boundary control.
- Same file and same read order for every F. Only F varies.
- A fresh JVM per F, so the static values are re-derived.
- The 256 MiB file exceeds every cap, so a plateau cannot be caused by running out of data. Run F=288 as an extra point (cap 256 MiB = data size) if a "follows data, not cap" check is wanted: there maxW should approach about 256 MiB.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node with ≥ 8 GB RAM and ≥ 10 GB free **local** disk. JDK 11 and Ant. Build in the copy: `cd /local/ccprobe/cassandra && ant jar`. Use the copy's `bin/` and `conf/`.
- Point `data_file_directories`, `commitlog_directory`, `hints_directory` and `saved_caches_directory` at `/local/ccprobe/node/...`.
- `conf/cassandra-env.sh`: `MAX_HEAP_SIZE=2G`, `HEAP_NEWSIZE=400M`.
- `conf/jvm-server.options`: add `-XX:MaxDirectMemorySize=4G` (so the pool and overflow are not clipped by the default direct limit, which equals the heap) and `-XX:NativeMemoryTracking=summary`.
- `cassandra.yaml`: `file_cache_enabled: true`, `file_cache_size: <F>MiB`, `disk_access_mode: mmap_index_only` (default), `key_cache_size: 0MiB` (removes key-cache noise), and `listen_address`/`rpc_address` 127.0.0.1.

**B3b. Knobs.** `file_cache_size` F ∈ {32, 96, 288, 2080} MiB, each set in yaml followed by a restart (the value is static).
- 32: control, cache disabled.
- 96: cap 64 MiB.
- 288: cap 256 MiB.
- 2080: cap 2 GiB, larger than the dataset. This is the positive control showing the workload alone drives the cache to dataset size.

**B3c. Workload.**
- Load once, with the default table compression (LZ4, 16 KiB chunks, so each cache entry is 16 KiB):
  `tools/bin/cassandra-stress write n=1500000 -col n=FIXED\(1\) size=FIXED\(1024\) -schema "replication(factor=1)" -rate threads=32 -node 127.0.0.1`
  then `bin/nodetool flush && bin/nodetool compact keyspace1`.
- That is about 1.5M × ~1.06 KiB ≈ 1.5 GiB uncompressed, which is about 98k distinct 16 KiB chunks. This is ≥ 6× the 256 MiB cap and below the 2 GiB cap.
- For each F, after a restart:
  `tools/bin/cassandra-stress read n=3000000 -col n=FIXED\(1\) size=FIXED\(1024\) -pop dist=UNIFORM\(1..1500000\) -rate threads=32 -node 127.0.0.1`
  This takes roughly 5–15 min. Uniform point reads touch every data chunk.

**B3d. Observables and instruments.** Sample every 5 s during the read run, plus once 60 s after it ends.
- Cache operand: `bin/cqlsh -e "SELECT name, capacity_bytes, size_bytes, entry_count FROM system_views.caches WHERE name='chunks';"`
- Chunk-cache pool: `bin/nodetool sjk mx -b "org.apache.cassandra.metrics:type=BufferPool,scope=chunk-cache,name=Size" -mg -f Value`, and the same for `name=OverflowSize`.
- Actual direct memory:
  - `bin/nodetool sjk mx -b "java.nio:type=BufferPool,name=direct" -mg -f MemoryUsed`
  - `jcmd <pid> VM.native_memory summary` ("Other" section, which holds direct buffers on JDK 11)
  - `ps -o rss= -p <pid>` for RSS
- `nodetool info` "Chunk Cache" line, as a cross-check.
- Not separable: direct memory of the networking pool and other off-heap users. Handle this by subtracting the F=32 baseline run.

**B3e. Procedure.**
1. Create directories under `/local/ccprobe/node`. Start the node with `bin/cassandra -p /local/ccprobe/node/pid`. Wait for `nodetool status` to show UN.
2. Run the load (B3c), then flush and compact.
3. For F in 32, 96, 288, 2080:
   1. Set yaml, then `kill $(cat pid)` and wait for the process to exit.
   2. Start the node. Wait for UN plus 30 s.
   3. Take a baseline sample.
   4. Start the sampler loop (B3d) to `samples-$F.csv`.
   5. Run the read workload.
   6. Take a 60 s tail sample, then stop the sampler.
4. Stop the node, run `pgrep -f CassandraDaemon` (it must print nothing), then `rm -rf /local/ccprobe/node`.

**B3f. Predictions.**

| F | capacity_bytes | size_bytes plateau | chunk-cache pool Size | direct MemoryUsed vs F=32 baseline |
|---|---|---|---|---|
| 32 | no `chunks` row (cache null) | — | small, from BufferManagingRebufferer buffers (≤ 32 MiB) | baseline B |
| 96 | 67,108,864 | 64 MiB ± 1 chunk, reached within the first minutes, never above 64 MiB + 32 × 16 KiB | ≤ 96 MiB | ≈ B + 64 MiB (± 32 MiB) |
| 288 | 268,435,456 | 256 MiB ± a few chunks | ≤ 288 MiB | ≈ B + 256 MiB (± 32 MiB) |
| 2080 | 2,147,483,648 | ≈ dataset uncompressed size (~1.5 GiB), below capacity | ≤ 2080 MiB | ≈ B + 1.5 GiB |

The relation is that the direct-memory delta between F=288 and F=96 is ≈ 192 MiB. OverflowSize is expected to be ~0 for 96 and 288.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| size_bytes plateaus at F−32 MiB for 96/288 and direct delta ≈ F−32 | claim confirmed |
| size_bytes plateaus at F MiB | reserve not applied: line-49 claim wrong |
| size_bytes or direct delta keeps growing past F−32 (+ tens of MiB) at 96/288 | cap not enforced: refuted |
| size_bytes within cap but direct delta ≫ F (OverflowSize large, or pool Size at F plus overflow) | cache operand capped but real usage not: partial, the overshoot path A3 5c dominates |
| positive control F=2080 grows to ~1.5 GiB while F=288 stays at 256 MiB | workload drives usage; the cap is what binds |
| F=2080 also stays low (≤ 256 MiB) | workload does not reach the cache: not confirmed (check `disk_access_mode`, compression, read path) |

**B3h. Controls.**
- F=32 baseline: the same node, data and workload with the cache disabled.
- F=2080 positive control.
- The same compacted dataset for every F, with restarts between runs.
- Key cache disabled.
- Fixed heap, so the default `file_cache_size` is not in play.
- Compaction finished before the reads, so no compaction readers add pool use.

**B4. Risks and cleanup.**
- **Disk:** unit tier ≤ 256 MiB in the copy's `build/tmp`. Cluster tier ≈ 2 GiB of data plus commit log under `/local/ccprobe/node`. Never use shared storage or the shared source tree.
- **Memory:** F=2080 needs about 2 GiB direct + 2 GiB heap. Skip it on nodes with < 8 GB RAM and use F=1056 (cap 1 GiB) with a 0.75M-row dataset.
- **Processes:** after each tier, `pgrep -f CassandraDaemon`, `pgrep -f junit` and `pgrep -f cassandra-stress` must all be empty. Kill any leftovers.
- **Cleanup:** `rm -rf /local/ccprobe/node /local/ccprobe/cassandra/build/tmp/ccprobe*`. Remove `/local/ccprobe` when finished.

## C. Sources read
- src/java/org/apache/cassandra/cache/ChunkCache.java
- src/java/org/apache/cassandra/utils/memory/BufferPools.java
- src/java/org/apache/cassandra/utils/memory/BufferPool.java
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java
- src/java/org/apache/cassandra/config/Config.java
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java
- src/java/org/apache/cassandra/config/DataStorageSpec.java
- src/java/org/apache/cassandra/io/util/FileHandle.java
- src/java/org/apache/cassandra/io/util/BufferManagingRebufferer.java
- src/java/org/apache/cassandra/io/util/DiskOptimizationStrategy.java
- src/java/org/apache/cassandra/io/util/RandomAccessReader.java
- src/java/org/apache/cassandra/io/util/SimpleChunkReader.java
- src/java/org/apache/cassandra/io/util/FileUtils.java
- src/java/org/apache/cassandra/hints/CompressedChecksummedDataInput.java
- src/java/org/apache/cassandra/metrics/ChunkCacheMetrics.java
- src/java/org/apache/cassandra/metrics/CacheMetrics.java
- src/java/org/apache/cassandra/metrics/BufferPoolMetrics.java
- src/java/org/apache/cassandra/db/virtual/CachesTable.java
- src/java/org/apache/cassandra/tools/nodetool/Info.java
- src/java/org/apache/cassandra/schema/CompressionParams.java
- conf/cassandra.yaml
- conf/jvm-server.options
- test/conf/cassandra.yaml
- build.xml
- .build/parent-pom-template.xml
- CHANGES.txt
- https://www.javadoc.io/doc/com.github.ben-manes.caffeine/caffeine/3.1.8/com.github.benmanes.caffeine/com/github/benmanes/caffeine/cache/Caffeine.html#maximumWeight(long)
- https://issues.apache.org/jira/browse/CASSANDRA-5863
- https://issues.apache.org/jira/browse/CASSANDRA-16036

## D. Stage-4 feedback

**Stage-4 audit amendments (2026-11-11, before any reading; results file `cassandra/stage4-runtime-verification/results/file_cache_size-chunk_cache_eviction-weighted_size--autonomous.md`).** They read as edits of the sections named. No prediction value of B2f or B3f is changed; AM5 and AM6 only give the words of B2g / B3g a numeric meaning.

- **AM1 (A2, A3 step 4; citation).** The chunk-cache pool's slabs are `MACRO_CHUNK_SIZE = 64 × NORMAL_CHUNK_SIZE = 8 MiB` (BufferPool.java:128, :385), not 1 MiB. The pool therefore grows in 8 MiB steps and holds at most `floor(F/8) × 8` MiB of slabs (32 MiB at F=33). Buffers ≤ 128 KiB (`NORMAL_CHUNK_SIZE`) are served from slabs; 64 KiB and 16 KiB chunks both are. The B2f / B3f bounds (`pool Size ≤ F MiB`) are unchanged.
- **AM2 (B3c; runbook).** `cassandra-stress`'s own schema creates the table `WITH compression = {}` when no `compression=` is given (tools/stress/.../SettingsSchema.java:141-145, :211), which `CompressionParams.fromMap` reads as no compression, so the "default table compression (LZ4, 16 KiB)" B3c assumes does not happen. The load command becomes `tools/bin/cassandra-stress write n=1500000 -col n=FIXED\(1\) size=FIXED\(1024\) -schema "replication(factor=1)" compression=LZ4Compressor -rate threads=32 -node 127.0.0.1 -port native=9442 jmx=7599`; the stage-4 run checks `chunk_length_in_kb: 16` in `DESCRIBE TABLE keyspace1.standard1`.
- **AM3 (B2a, B2e, B3a, B3e; environment).** Paths and ports for the shared stage-4 node: the copy is made with `copy-source.sh /mydata/jingsong-cass-s4/o06/src` (not `rsync` from `/users/jason92/...`) and built with `ant build-test`; `/local/ccprobe/cassandra` reads `/mydata/jingsong-cass-s4/o06/src` and `/local/ccprobe/node` reads `/mydata/jingsong-cass-s4/o06/node`. The node binds 127.0.0.1 with `storage_port: 7400`, `ssl_storage_port: 7401`, `native_transport_port: 9442`, JMX 7599 (`JMX_PORT` in the copy's `conf/cassandra-env.sh`); every `nodetool` call takes `-p 7599`, `cqlsh` takes `127.0.0.1 9442`, and `cassandra-stress` takes `-port native=9442 jmx=7599`. Heap 2 GiB + `MaxDirectMemorySize=4G` as filed.
- **AM4 (B2d, B3d; instrument, no prediction change).** Direct evidence that the disallow branch (eviction) fired: the unit probe also prints the cache's miss count (`ChunkCache.instance.metrics.misses`) and the number of evictions (misses − final entries, as nothing else removes entries); the cluster sampler records the `ChunkCache` `Misses` meter and `Entries` beside `Size`. The cluster sampler reads the JMX gauges through one long-lived JMX client every 5 s (instead of one `nodetool sjk` JVM per gauge) and runs `cqlsh`, `jcmd VM.native_memory summary` and `ps -o rss=` in the same 5 s loop.
- **AM5 (B2g; wording).** "maxW plateaus at (F−32) MiB": B2f's bounds for F = 33, 64, 160 hold (≤ cap + 65,536, and ≥ cap − 65,536 for 64 and 160). "maxW > (F−32) MiB + a few chunks": maxW > cap + 4 × 65,536 for some F. "plateaus at F MiB": maxW ≥ F MiB − 65,536 for F = 64 or 160. "well below the cap for all F": maxW < cap − 65,536 for each of 33, 64, 160. Positive control "≈ 4×": maxW(160) / maxW(64) within 3.8–4.2.
- **AM6 (B3g; wording).** "direct delta ≈ F−32": the B3f tolerance, (F−32) ± 32 MiB, with the delta = mean direct `MemoryUsed` over the last minute of the read run minus the same at F=32. "size_bytes ... keeps growing past F−32": any sample of size_bytes > capacity + 32 × 16 KiB at F = 96 or 288, or direct delta > (F−32) + 64 MiB not accounted for by chunk-cache pool Size + OverflowSize. "direct delta ≫ F" (partial row): direct delta > F + 32 MiB with size_bytes within the cap. Positive control "grows to ~1.5 GiB": the F=2080 size_bytes plateau ≥ 1 GiB and below capacity, while the F=288 plateau is ≤ 256 MiB + 32 × 16 KiB. "F=2080 also stays low": its plateau ≤ 256 MiB + 32 × 16 KiB.

A reading that matches no row of B2g / B3g as worded with AM5 / AM6 is "Not confirmed (no matching row)".

**Stage-4 result (2026-11-12, run 1 + self-check; results file above).** Unit **Confirmed — caps** (B2g row 1 and positive-control row): max weightedSize = F − 32 MiB exactly at F = 33 / 64 / 160 (1 / 32 / 128 MiB), cache null at 32, ratio 160:64 = 4.000, overflow 0. Cluster **Confirmed — caps** (B3g row 1 and positive-control row): `size_bytes` = 64 / 256 MiB exactly at F = 96 / 288 and never above; direct-memory delta vs F=32 80 / 253 MiB (steady 80 / 272) within (F−32) ± 32 MiB; F=2080 grows to 1.48 GiB; OverflowSize 0. Outcome class: true positive. Sharpens A3 5(d): the chunk-cache pool's slabs grew to the full F in both tiers (pool Size = F, Used = F − 32, "Maximum memory usage reached" logged) and are never freed, so real direct memory is bounded by F and cached data by F − 32. Open point: the F=288 direct delta depends on the averaging window (results §3, H1). No section of the trace is refuted.
