<!-- file: cases/file_cache_size-chunkcache-cachesize--autonomous.md -->
# file_cache_size — verification solution  <!-- file: cases/file_cache_size-chunkcache-cachesize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | where the chunk cache's capacity gets its value (not an if statement), as given, **linked**: [`ChunkCache.java:50`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/ChunkCache.java#L50) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code autonomous subagent, 2026-11-11 |
| Estimate | `positive`. When the chunk cache is on (`file_cache_enabled: true`; it is off by default), `cacheSize = file_cache_size − 32 MiB` is passed to Caffeine as `maximumWeight`, and each entry weighs its buffer's capacity in bytes, so the cache evicts to stay within it. The buffer pool behind it is also capped at `file_cache_size`, so the off-heap memory the cache holds follows the setting. |
| Ground | — |

> **Link rule.** Two places must be links, not plain `file:line`: **the constraint's
> declaration** (A1) and **the if statement** (the check; the Entry pointer row above and
> A3). Use a permalink at the pinned tag. Other citations may stay plain `file:line`.

## A. Constraint trace

**A1. The constraint.**
- **Name:** `file_cache_size` (yaml; the old name `file_cache_size_in_mb` is still accepted via `@Replaces`). It is a configuration entry, declared at [`Config.java:497`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L497) as `DataStorageSpec.IntMebibytesBound file_cache_size`. The `@Replaces` line is Config.java:496.
- **Derived value at the entry pointer:** `ChunkCache.cacheSize` (bytes) `= 1 MiB × max(0, file_cache_size_MiB − RESERVED_POOL_SPACE_IN_MiB)`, where `RESERVED_POOL_SPACE_IN_MiB = 32` (ChunkCache.java:49–50). This is `public static final`, so it is computed once, when the class is initialised.
- **Unit:** MiB (minimum unit MiB, conf/cassandra.yaml:752).
- **Default:** if the setting is absent, `min(512, Runtime.maxMemory()/4 MiB)`, i.e. the smaller of 512 MiB and a quarter of the heap. This is set in `DatabaseDescriptor.applySimpleConfig` (DatabaseDescriptor.java:576–577) and read through `getFileCacheSizeInMiB()` (DatabaseDescriptor.java:3784–3793). With an 8 GiB or larger heap the default `cacheSize` is 480 MiB.
- **Gate:** the cache exists only if `file_cache_enabled && cacheSize > 0` (ChunkCache.java:53–54). `file_cache_enabled` is Config.java:499, defaulting to the system property `cassandra.file_cache_enabled` (CassandraRelevantProperties.java:227), which is **false** unless set. The shipped yaml has it commented out as `false` (conf/cassandra.yaml:742). CASSANDRA-16036 turned the cache off by default (CHANGES.txt:1406). `test/conf/cassandra.yaml:55` turns it on for unit tests.
- **How to set it:** in `cassandra.yaml` (`file_cache_size: 256MiB`, `file_cache_enabled: true`), or for `file_cache_enabled` only, with `-Dcassandra.file_cache_enabled=true`. A change needs a restart: the value is `static final`, and `ChunkCache.setCapacity` throws `UnsupportedOperationException("Chunk cache size cannot be changed.")` (ChunkCache.java:311–314). There is no JMX setter.

**A2. What it caps.**
- **Resource:** memory holding uncompressed SSTable chunks. This is off-heap direct memory for LZ4, Snappy, Zstd and Noop (`preferredBufferType() == OFF_HEAP`, e.g. LZ4Compressor.java:240–242). It is on-heap for Deflate (DeflateCompressor.java:228–231) and for uncompressed files whose `bufferType` is on-heap.
- **Compared quantity (cache):** Caffeine's weighted size, which is the sum over cached entries of `buffer.capacity()` (weigher at ChunkCache.java:154), compared against `maximumWeight(cacheSize)` (ChunkCache.java:152). It is exposed as `CacheMetrics.size` → `ChunkCache.weightedSize()` (ChunkCache.java:323–328, CacheMetrics.java:70).
- **Compared quantity (pool):** the same `file_cache_size` (the full value, without the 32 MiB subtraction) is the `memoryUsageThreshold` of the `chunk-cache` `BufferPool` (BufferPools.java:38–39). The pool compares `memoryAllocated` (its 1 MiB slabs) against it (BufferPool.java:443).

**A3. Mechanism.**
1. Class initialisation computes `cacheSize` ([`ChunkCache.java:50`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/ChunkCache.java#L50)). If `cacheSize == 0`, meaning `file_cache_size ≤ 32 MiB`, or the cache is disabled, `instance` is `null` (ChunkCache.java:53–54).
2. Files are wrapped only when a cache exists with positive capacity. The check is [`FileHandle.java:446`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/FileHandle.java#L446): `if (chunkCache != null && chunkCache.capacity() > 0) return chunkCache.wrap(reader);`. It applies to compressed data files, both standard and mmap (FileHandle.java:411, 423), and to uncompressed non-mmap files (FileHandle.java:428–429). Uncompressed mmapped files use `MmapRebufferer` and bypass the cache (FileHandle.java:417). `SSTable.Builder` defaults to `ChunkCache.instance` (SSTable.java:391; SSTableReaderLoadingBuilder.java:66).
3. **Enforcement of the cap:** the cache is a Caffeine `LoadingCache` built with [`maximumWeight(cacheSize)` and a byte-capacity weigher, `ChunkCache.java:151-157`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/ChunkCache.java#L151-L157). Maintenance and eviction run on the calling thread (`ImmediateExecutor`, line 153). The size comparison itself is inside Caffeine 3.1.8 (`.build/parent-pom-template.xml:1061`): when the weighted size exceeds the maximum, it evicts until the size is under the maximum again.
4. A miss calls `load` (ChunkCache.java:161–175). This takes a buffer of `chunkSize` from the chunk-cache pool and reads and decompresses the chunk into it.
5. **Pool check:** [`BufferPool.java:443`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L443) `if (cur + MACRO_CHUNK_SIZE > memoryUsageThreshold)`.
   - Below the threshold, the pool allocates another 1 MiB direct slab (BufferPool.java:452–460).
   - At the threshold, it logs "Maximum memory usage reached …" and returns `null`. The local pool then falls back to `allocate(size, OFF_HEAP)`: an unpooled `ByteBuffer.allocateDirect` counted in `overflowMemoryUsage` (BufferPool.java:904–923, 233–239).
   - If `allocateDirect` itself throws OOM, the pool logs an error and returns `null` (BufferPool.java:462–468).
6. **Eviction:** `onRemoval` calls `buffer.release()` (ChunkCache.java:177–181). When the refcount reaches 0, the buffer goes back to the pool (lines 140–144), or an overflow buffer is un-counted (BufferPool.java:241–247).
7. **Outcome at the limit:** reads still succeed. The least-valuable entries are evicted, so cached bytes stay ≤ `cacheSize`.
8. **Ways usage can exceed the cap:**
   - (a) An evicted `Buffer` that an in-flight reader still references is not freed until that reader releases it (refcount, lines 112–124). This is bounded by concurrent readers × chunk size.
   - (b) Overflow (unpooled) direct buffers held in the cache count toward the cache weight, but not toward the pool's slab threshold. So the pool's total `Size` (slabs + overflow) can exceed `file_cache_size`. The worst case is about `file_cache_size + cacheSize`, if slabs are fragmented.
   - (c) Per-entry on-heap overhead (`Key`, `Buffer`, Caffeine node) is not weighed. cassandra.yaml:748–750 says it is about 128 B per chunk.
   - (d) Caffeine may hold the weighted size briefly above the maximum between an insert and its synchronous maintenance.

**A4. Other consumers.**
- The same `chunk-cache` BufferPool also serves:
  - `BufferManagingRebufferer`, the per-reader buffers used when a file is not cached (BufferManagingRebufferer.java:45, 52);
  - hint decompression (`CompressedChecksummedDataInput`, hints/CompressedChecksummedDataInput.java:35, 125, 138).
- Off-heap memory outside this constraint:
  - the networking pool, capped by `networking_cache_size` (BufferPools.java:44–45);
  - `CompressedChunkReader`'s thread-local compressed-read buffers (CompressedChunkReader.java:130, 165–166);
  - mmapped index and data regions (page cache, not counted as direct memory);
  - off-heap memtables, Bloom filters, index summaries, Netty, and the OS page cache.

**A5. Evidence beyond the source.**
- conf/cassandra.yaml:740–759: the documentation of `file_cache_enabled`, `file_cache_size` and the 32 MiB reservation.
- CHANGES.txt: CASSANDRA-16036 (disabled by default), CASSANDRA-15229 (separate network and chunk-cache pools, recirculating partially freed chunks), CASSANDRA-5863 (the chunk cache), CASSANDRA-11993.
- https://issues.apache.org/jira/browse/CASSANDRA-16036
- https://issues.apache.org/jira/browse/CASSANDRA-15229
- Caffeine eviction (size-based, weight): https://github.com/ben-manes/caffeine/wiki/Eviction
- JDK 11 `BufferPoolMXBean` (`java.nio:type=BufferPool,name=direct`): https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/BufferPoolMXBean.html
- Native Memory Tracking: https://docs.oracle.com/en/java/javase/11/vm/native-memory-tracking.html

## B. Verification solution

**B1. Claim under test.** With `file_cache_enabled: true`, the uncompressed-chunk memory held by the chunk cache never exceeds `file_cache_size − 32 MiB` (plus at most a few chunks in flight), however much more SSTable data is read. Also, the node's direct memory attributable to the chunk cache grows with `file_cache_size` and stays within `file_cache_size` plus small overflow. With `file_cache_size ≤ 32 MiB`, the cache does not exist.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 11 (`java -version` shows 11), Ant ≥ 1.10.
- Copy the tree to local disk, never building in the shared copy: `rsync -a /users/jason92/cassandra-5.0.9/ $W/cassandra-5.0.9/`, where `W=/mydata/$USER/o07` (or any local disk with ≥ 5 GiB free).
- Build: `cd $W/cassandra-5.0.9 && ant jar build-test`.
- Test source: create `test/unit/org/apache/cassandra/cache/ChunkCacheCapProbeTest.java` in the **copy** (content in B2e). It runs through `ant testsome`.
- JVM options: pass `-Dtest.jvm.args="-Xmx4G -Dcassandra.config=file://$W/yaml/fcNNN.yaml"`. `testsome` itself sets no `cassandra.config` (build.xml:1382–1391), and `test.jvm.args` is appended to the JVM arguments at build.xml:1192.
- > **Amendment A1 (2026-11-11, stage-4 audit).** The working tree is made with `cassandra/stage4-runtime-verification/copy-source.sh $W/src` (the repository's pinned 5.0.9 source; `/users/jason92/cassandra-5.0.9` does not exist on the run node), with `W=/mydata/jingsong-cass-s4/o07`, and built with `ant build-test`. Every `$W/cassandra-5.0.9` below means `$W/src`. `ant testsome` forks its JVM with `maxmemory="1024m"` (build.xml:1153), so the test heap is 1 GiB whatever `-Xmx4G` says, and the default direct-memory limit is also 1 GiB; this is above every pool figure the unit tier can reach (U3 ≈ 210 MiB), and every run sets `file_cache_size` explicitly, so no prediction depends on the heap.

**B2b. Knobs.** `cacheSize` is static, so each value needs a fresh JVM, which means one `ant testsome` run per yaml. Make each yaml as a copy of `test/conf/cassandra.yaml` (it already has `file_cache_enabled: true`, line 55), with a `file_cache_size` line appended.

> **Amendment A2 (2026-11-11, stage-4 audit).** The run node is shared, so each yaml variant also gets `storage_port: 7300`, `ssl_storage_port: 7301` and `native_transport_port: 9342` appended (the same way as `file_cache_size`). These ports do not touch the read path.

| run | `file_cache_size` | expected `cacheSize` | why |
|---|---|---|---|
| U0 | `32MiB` | 0 → `instance == null` | boundary: the reservation consumes everything |
| U1 | `64MiB` | 32 MiB (33,554,432 B) | well below the data read |
| U2 | `128MiB` | 96 MiB (100,663,296 B) | second point, to show proportionality |
| U3 (positive control) | `1024MiB` | 992 MiB | above the data read, so the cache grows to the data size |
| U4 (control) | `128MiB` plus `file_cache_enabled: false` | cache null | only the gate changes |

**B2c. Workload.**
- Table: `CREATE TABLE %s (pk int, ck int, v blob, PRIMARY KEY (pk, ck)) WITH compression = {'class':'LZ4Compressor','chunk_length_in_kb':'16'}`.
- Data: 64 partitions × 200 rows, each with a 16,384-byte random (incompressible) blob, giving 12,800 × 16 KiB ≈ 200 MiB raw. That is about 12,900 uncompressed 16 KiB chunks.
- Insert in 4 batches of 16 partitions, with `flush()` after each batch, so all reads hit SSTables.
- Read every row once in sequence with `SELECT v FROM %s WHERE pk=? AND ck=?`, then repeat the whole pass a second time.
- Each cached entry weighs 16,384 B, so U1 reaches its cap after about 2,048 distinct chunks (≈ 32 MiB), which is 1/6 of the first pass. U2 reaches it after about 6,144 chunks. U3 never reaches its cap: about 200 MiB < 992 MiB.

**B2d. Observables and instruments.** The test calls these in-process after every 256 reads, and once at the end:
- `ChunkCache.instance.weightedSize()` (the operand of the cap);
- `ChunkCache.instance.size()` (number of entries);
- `ChunkCache.instance.capacity()`;
- `BufferPools.forChunkCache().sizeInBytes()`, `.overflowMemoryInBytes()` and `.usedSizeInBytes()`.

It prints CSV lines `SAMPLE,reads,weighted,entries,poolSize,poolOverflow,poolUsed` and a final `MAX,...` line. It cannot observe Caffeine's internal transient above-maximum state between an insert and its maintenance. Each sample is taken after a read has completed.

> **Amendment A3 (2026-11-11, stage-4 audit).** Two additions that change no prediction or reading row. (a) Each `SAMPLE`/`MAX` line also carries `misses`, the count of `ChunkCache.instance.metrics.misses` (each miss is one `load`); with no explicit invalidation, `misses − entries` is the number of entries evicted, the direct evidence that the eviction (disallow) branch fired. `recordEviction` in ChunkCacheMetrics records nothing, so this is the cheapest direct count. (b) The test calls `disableCompaction()` after creating the table, so background compaction cannot replace the SSTables (and invalidate their cached chunks) between the passes.

**B2e. Procedure.**
1. Make the yaml variants:
   ```
   mkdir -p $W/yaml
   for v in 32 64 128 1024; do
     cp test/conf/cassandra.yaml $W/yaml/fc$v.yaml
     echo "file_cache_size: ${v}MiB" >> $W/yaml/fc$v.yaml
   done
   cp $W/yaml/fc128.yaml $W/yaml/fcoff.yaml
   sed -i 's/^file_cache_enabled: true/file_cache_enabled: false/' $W/yaml/fcoff.yaml
   ```
   The memtable block at the end of the test yaml is a mapping. Appending a top-level key after it is valid YAML, as long as the appended line has no indentation.
2. Write the test, extending `org.apache.cassandra.cql3.CQLTester`, with one `@Test public void probe()`:
   - Print `capacity()`, or `CACHE_NULL` if `ChunkCache.instance == null`.
   - Create the table and insert the data per B2c, flushing after each batch.
   - Do the two read passes, sampling per B2d and tracking the maxima.
   - Print the final values. Do not assert on the cap: the readings decide.
   - When `instance == null`, still run the reads and print the pool figures. This shows the uncached path.
3. For each `v` in `32 64 128 1024 off`:
   ```
   ant testsome -Dtest.name=org.apache.cassandra.cache.ChunkCacheCapProbeTest \
     -Dtest.jvm.args="-Xmx4G -Dcassandra.config=file://$W/yaml/fc$v.yaml"
   ```
   Then copy `build/test/output/TEST-org.apache.cassandra.cache.ChunkCacheCapProbeTest.xml` to `$W/out/unit-$v.xml`. Each run gets a fresh JVM.
4. Check the logs for `Global buffer pool limit is X for chunk-cache` (BufferPools.java:49–53) to confirm the value took effect.
5. Delete `build/test/cassandra` (the test data, about 200 MiB per run) between runs.

**B2f. Predictions (stated before any run).**
- **U0:** prints `CACHE_NULL`. The pool's `sizeInBytes` stays ≤ 32 MiB plus overflow, from uncached `BufferManagingRebufferer` use only. It should be a few MiB at most.
- **U1:**
  - max `weighted` ≤ 33,554,432 B, and ≤ cap + 16,384 B at any sample;
  - the final `weighted` is in [0.95 × cap, cap], i.e. 31.9–32 MiB, and `entries` ≈ 2,048 (± 5%);
  - `poolSize` ≤ 64 MiB + `poolOverflow`, and `poolOverflow` ≤ 32 MiB.
- **U2:** the same relations with cap = 100,663,296 B and `entries` ≈ 6,144.
- **U3:** `weighted` grows roughly linearly with the distinct chunks read, to ≈ 200–215 MiB (≈ 12,900 entries), and is the same after the second pass. This is far above the U1 and U2 caps.
- **U4:** `CACHE_NULL`, with pool usage as in U0.
- The ratio of final `weighted` between U2 and U1 is ≈ 3 (96 MiB / 32 MiB).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| U1/U2 final `weighted` ≈ cap and never > cap + 16 KiB; U3 ≈ data size (≫ U1/U2 caps) | Claim confirmed: the cap binds and the workload was able to exceed it. |
| U1 or U2 `weighted` > cap + 16 KiB at any sample, or final `weighted` > cap | **Claim wrong**: Caffeine does not hold the cache to `cacheSize`. |
| U3 also stays near 32 MiB or 96 MiB | Workload or instrument error (e.g. most reads served from memtables), so not confirmed. Check that flushes happened. |
| U1/U2 final `weighted` ≪ cap (< 50%) while U3 is large | The cache is evicting below its cap (e.g. a weight mismatch). The cap holds but does not govern usage, so the claim is partly wrong. |
| `poolSize` > `file_cache_size` + `cacheSize` | Pooled memory overshoots both bounds: the "pool also capped" part of the claim is wrong. |
| U0 shows a non-null cache | The boundary `≤ 32 MiB` is wrong. |

**B2h. Controls.**
- U4 (gate off with the same size) and U0 (boundary) separate the gate from the size.
- U3 is the positive control that the workload moves the operand.
- Random blobs rule out compression shrinking the chunks, and fixed 16 KiB chunks make the weight arithmetic exact.
- The second read pass checks that the size stays at the cap under churn.
- The `Global buffer pool limit` log line confirms the yaml value was applied.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node with ≥ 8 GiB RAM, JDK 11 and Ant. Use the same copy `$W/cassandra-5.0.9` built with `ant jar` (or `ant artifacts`, then use the tarball under `build/`). Run from the copy, with `CASSANDRA_HOME` being the copy.
- In the copy's `conf/cassandra.yaml`, set:
  - `data_file_directories: [$W/data]`, `commitlog_directory: $W/commitlog`, `hints_directory: $W/hints`, `saved_caches_directory: $W/saved_caches`, `cdc_raw_directory: $W/cdc` (all on local disk);
  - `file_cache_enabled: true` and `file_cache_size` per run;
  - leave `disk_access_mode` at its default, so data files are read through `CompressedChunkReader.Standard` and are cacheable.
- Heap: `export MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M` (read by conf/cassandra-env.sh). With a 2 GiB heap the default would be 512 MiB, but every run sets the value explicitly.
- Add `-XX:NativeMemoryTracking=summary` to `conf/jvm11-server.options`.
- Leave `-XX:MaxDirectMemorySize` unset, so its default equals the heap maximum (2 GiB), which is above every value tested.
- > **Amendment A9 (2026-11-11, stage-4 runbook defect D2).** In 5.0.9 `conf/cassandra-env.sh` sets `-XX:MaxDirectMemorySize` itself when `MAX_DIRECT_MEMORY_SIZE` is unset (lines 50–67, 139–158; cluster attempt 1 started with `-XX:MaxDirectMemorySize=15872M`), so "unset" does not give 2 GiB. To get the 2 GiB this line intends, export `MAX_DIRECT_MEMORY_SIZE=2G` with `MAX_HEAP_SIZE`. It is above every value tested; B3f and B3g are unchanged.
- > **Amendment A4 (2026-11-11, stage-4 audit).** The run node is shared with other Cassandra nodes (127.0.0.11–17, ports 7000/9042). The node binds `listen_address: 127.0.0.1`, `rpc_address: 127.0.0.1`, seeds `127.0.0.1:7300`, `storage_port: 7300`, `ssl_storage_port: 7301`, `native_transport_port: 9342`, and `JMX_PORT=7499` (edited in the copy's `conf/cassandra-env.sh`, line 235). Every client is given these ports: `nodetool -p 7499`, `cqlsh 127.0.0.1 9342`, `cassandra-stress … -node 127.0.0.1 -port native=9342 jmx=7499`. Logs go to `CASSANDRA_LOG_DIR=$W/clogs`; data, commit log, hints, saved caches and CDC go under `$W/cdata/`. Heap + direct stays ≤ 4 GiB.

**B3b. Knobs.** One restart per value. The data is kept between runs.

| run | yaml | `cacheSize` |
|---|---|---|
| C0 (control) | `file_cache_enabled: false` | no cache |
| C1 | `file_cache_size: 128MiB` | 96 MiB |
| C2 | `file_cache_size: 256MiB` | 224 MiB |
| C3 (positive control) | `file_cache_size: 1024MiB` | 992 MiB (above the hot set) |

All of these stay below the 2 GiB direct limit.

**B3c. Workload.**
- Load once, with `tools/bin/cassandra-stress write n=500000 -col n=FIXED\(1\) size=FIXED\(1024\) -rate threads=16 -node 127.0.0.1`. Then run `bin/nodetool flush keyspace1` and `bin/nodetool compact keyspace1`. Stress values are random bytes, so the data is ≈ 500,000 × ~1.1 KiB ≈ 550 MiB uncompressed and roughly the same on disk, in 16 KiB LZ4 chunks (CompressionParams.java:48).
  > **Amendment A8 (2026-11-11, stage-4 runbook defect D1).** `cassandra-stress`'s default schema has no compression (`compression = {}`; SettingsSchema.java:141–143, 211: "default:no compression"), so the load as written makes an uncompressed table (cluster attempt 1: `SSTable Compression Ratio: -1`, no `CompressionInfo.db`), not the 16 KiB LZ4 chunks this section and B3f assume. The load command gets `-schema 'compression=LZ4Compressor'` (the default chunk length, 16 KiB, applies), and the run script stops if the table's compression ratio is −1. B3f and B3g are unchanged. The cluster tier restarts from its beginning with fresh data.
- For each run:
  - restart the node;
  - warm and measure with `tools/bin/cassandra-stress read n=2000000 -col n=FIXED\(1\) size=FIXED\(1024\) -pop dist=UNIFORM\(1..500000\) -rate threads=32 -node 127.0.0.1`, which takes about 5–10 minutes;
  - repeat it once more, so the uniform reads have touched every one of the ≈ 35,000 chunks several times.
- The hot set (≈ 550 MiB) is above the C1 and C2 caps and below C3.

**B3d. Observables and instruments.** Sample every 10 s during the reads with a loop writing to `$W/out/cN.csv`:
- the operand, from `bin/cqlsh -e "SELECT name,capacity_bytes,size_bytes,entry_count FROM system_views.caches WHERE name='chunks'"` (CachesTable.java), or from `bin/nodetool info` (the "Chunk Cache" line, Info.java:126–138);
- the pool, with `bin/nodetool sjk mx -mg -b 'org.apache.cassandra.metrics:type=BufferPool,scope=chunk-cache,name=Size' -f Value`, and the same for `name=OverflowSize` and `name=UsedSize`;
- the JVM direct memory, with `bin/nodetool sjk mx -mg -b 'java.nio:type=BufferPool,name=direct' -f MemoryUsed`;
- native memory, with `jcmd $PID VM.native_memory summary`: the "Other" category, where direct buffers are counted in JDK 11;
- RSS, with `ps -o rss= -p $PID`.

Direct memory cannot be attributed to the chunk cache by the JVM itself. Attribute it by difference against C0, and by the Cassandra pool gauges.

> **Amendment A5 (2026-11-11, stage-4 audit).** The JMX gauges are read every 10 s by one sampler JVM in the harness (`JmxSampler.java`, connecting to port 7499) instead of one `nodetool sjk` JVM per gauge, which cannot keep a 10 s cadence. It reads the same beans (`type=BufferPool,scope=chunk-cache,name=Size|OverflowSize|UsedSize`, `java.nio:type=BufferPool,name=direct` `MemoryUsed`) plus the cache operand `org.apache.cassandra.metrics:type=Cache,scope=ChunkCache,name=Size|Entries|Capacity|Misses` (the same `CacheMetrics` that `system_views.caches` reads, CachesTable.java:57–75). `system_views.caches` through `cqlsh` is read at the baseline, after each read pass and at the final sample. NMT and RSS are sampled by the same loop's shell side every 10 s.

**B3e. Procedure.**
1. Build the copy and set up the yaml and env per B3a. Run `df -h $W` and make sure there are ≥ 5 GiB free.
2. Start the node with `bin/cassandra -p $W/cass.pid`, and wait until `bin/nodetool status` shows `UN`.
3. Run the load per B3c, then flush and compact.
4. For each of C0, C1, C2, C3:
   - stop the node (`kill $(cat $W/cass.pid)`, then wait for exit);
   - edit the yaml and start the node;
   - check `grep "Global buffer pool limit" logs/system.log | tail -1`;
   - take a baseline sample;
   - run the read workload twice while sampling;
   - take a final sample after 60 s idle.
5. Stop the node and check that `pgrep -f CassandraDaemon` is empty.
   > **Amendment A6 (2026-11-11, stage-4 audit).** Other people's `CassandraDaemon` processes run on this node, so "stopped" is checked by this run's PID and its directory (`$W/src`), never by `pgrep -f CassandraDaemon` being empty, and only this run's processes are ever signalled.

**B3f. Predictions (stated before any run).**
- C0: `system_views.caches` has no `chunks` row (`nodetool info` prints the chunk-cache line as off), and the chunk-cache pool `Size` is ≤ a few MiB.
- C1: `size_bytes` plateaus in [0.95 × 96 MiB, 96 MiB] and never exceeds 96 MiB + 32 × 16 KiB (in-flight slack). `entry_count` ≈ 6,144. The pool `Size` is ≤ 128 MiB + `OverflowSize`. Direct `MemoryUsed`(C1) − `MemoryUsed`(C0) is ≤ 128 MiB + `OverflowSize` + 8 MiB.
- C2: the same with 224 MiB and 256 MiB. `entry_count` ≈ 14,336.
- C3: `size_bytes` keeps rising to ≈ the hot set (≈ 550–600 MiB, < 992 MiB), and the direct delta versus C0 is ≈ that much.
- Ordering: the direct delta increases from C0 to C1, C2 and C3, and the C2 − C1 delta is ≈ 128 MiB (± 32 MiB).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| C1/C2 `size_bytes` plateau at ≈ cap; the direct delta is ≈ `file_cache_size` and follows the knob; C3 goes well above | Claim confirmed. |
| C1 or C2 `size_bytes` > cap + slack, or the direct delta ≫ `file_cache_size` + `OverflowSize` | **Claim wrong**: the setting does not cap actual off-heap usage. |
| The direct delta is about the same for C1, C2 and C3 | Usage does not follow the knob, or the workload did not touch the cache. Check C3: if C3 did not rise either, the result is not confirmed (e.g. reads were served from the row or key cache, or mmap). |
| `OverflowSize` grows to ≈ `cacheSize` | The pool cap is bypassed by fragmentation (A3 path (b)). The cache cap still holds, but total usage approaches `file_cache_size + cacheSize`. Report it as a partial overshoot. |
| C0 shows a chunks row | The `file_cache_enabled` gate is not effective. |
| C1/C2 `size_bytes` plateau ≪ cap (< 50%) while C3 goes well above *(row added by Amendment A7, 2026-11-11, stage-4 audit, before any reading; mirrors B2g row 4)* | The cache evicts below its cap: the cap holds but does not govern usage, so the claim is partly wrong. |

**B3h. Controls.**
- C0 gives the same workload without the cache: the baseline for direct memory from networking, compression buffers and Netty.
- C3 is the positive control that the workload drives usage beyond the C1 and C2 caps.
- The same data and the same read seeds and distribution are used in every run.
- The `Global buffer pool limit` log line confirms each value.
- The row cache is off by default (`row_cache_size: 0MiB`, conf/cassandra.yaml:564), so it cannot serve reads instead of SSTables.

**B4. Risks and cleanup.**
- Everything stays under `$W`, on local disk: the unit tier adds ≈ 200 MiB per run, and the cluster tier ≈ 1–2 GiB of data, commit log and hints.
- Never write into `/users/jason92/cassandra-5.0.9`.
- After each tier, stop the processes and check that `pgrep -f CassandraDaemon` and `pgrep -f cassandra-stress` show nothing, and that `pgrep -f junit` shows nothing from `ant`.
- Remove `$W/data $W/commitlog $W/hints $W/saved_caches $W/cdc` and `$W/cassandra-5.0.9/build/test/cassandra`.
- Keep `$W/out` for results.
- Run C3 only after `free -g` shows ≥ 4 GiB available: a 2 GiB heap plus ≈ 1.2 GiB direct.

## C. Sources read

- src/java/org/apache/cassandra/cache/ChunkCache.java
- src/java/org/apache/cassandra/config/Config.java
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java
- src/java/org/apache/cassandra/utils/memory/BufferPools.java
- src/java/org/apache/cassandra/utils/memory/BufferPool.java
- src/java/org/apache/cassandra/io/util/FileHandle.java
- src/java/org/apache/cassandra/io/util/BufferManagingRebufferer.java
- src/java/org/apache/cassandra/io/util/SimpleChunkReader.java
- src/java/org/apache/cassandra/io/util/CompressedChunkReader.java
- src/java/org/apache/cassandra/io/compress/LZ4Compressor.java
- src/java/org/apache/cassandra/io/compress/DeflateCompressor.java
- src/java/org/apache/cassandra/io/sstable/SSTable.java
- src/java/org/apache/cassandra/io/sstable/format/SSTableReaderLoadingBuilder.java
- src/java/org/apache/cassandra/hints/CompressedChecksummedDataInput.java
- src/java/org/apache/cassandra/metrics/ChunkCacheMetrics.java
- src/java/org/apache/cassandra/metrics/CacheMetrics.java
- src/java/org/apache/cassandra/metrics/BufferPoolMetrics.java
- src/java/org/apache/cassandra/db/virtual/CachesTable.java
- src/java/org/apache/cassandra/tools/nodetool/Info.java
- src/java/org/apache/cassandra/schema/CompressionParams.java
- conf/cassandra.yaml, conf/cassandra-env.sh, conf/jvm-server.options, conf/jvm11-server.options
- test/conf/cassandra.yaml
- build.xml, .build/parent-pom-template.xml
- CHANGES.txt
- URLs cited from knowledge, not fetched in this session:
- https://github.com/ben-manes/caffeine/wiki/Eviction
- https://issues.apache.org/jira/browse/CASSANDRA-16036
- https://issues.apache.org/jira/browse/CASSANDRA-15229
- https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/BufferPoolMXBean.html
- https://docs.oracle.com/en/java/javase/11/vm/native-memory-tracking.html

## D. Stage-4 feedback

**2026-11-12 — stage 4 run 1 (autonomous file): unit Confirmed — caps; cluster Confirmed — caps; Outcome class true positive.** Results: [`../../stage4-runtime-verification/results/file_cache_size-chunkcache-cachesize--autonomous.md`](../../stage4-runtime-verification/results/file_cache_size-chunkcache-cachesize--autonomous.md). Frozen version (after A1–A9): sha256 `318a204873d832af007704caf534eec3dfe65c0679958fbc52f32ea621474625`; prediction/conclusion tables hash `ffb8fa1b5e414a6dd4c0a177014ad3790b8199226787acb4a20f38127de5612f` (unchanged by A8–A9).
- Unit (B2g row 1): weighted size exactly at the cap, 32.00 MiB (U1) and 96.00 MiB (U2), never above; 33,210 and 16,711 evictions; U3 filled to 200.27 MiB; U0 and U4 had no cache.
- Cluster (B3g row 1): `size_bytes` exactly 96.00 MiB (C1) and 224.00 MiB (C2), millions of evictions; JVM direct memory above C0 +112 / +240 / +496 MiB (C1/C2/C3), C2 − C1 = 128.00 MiB; C3 filled to 505.72 MiB.
- The chunk-cache pool's direct slabs fill to the full `file_cache_size` (not `cacheSize`); overflow stayed 0.
- Runbook defects fixed by A8 (stress default schema is uncompressed) and A9 (cassandra-env.sh sets `MaxDirectMemorySize`); the cluster tier restarted after them.
- For stage 3 (not applied): B3c/B3f data-size arithmetic (500k × 1 KiB stress rows are ≈ 505 MiB uncompressed, not 550–600 MiB) and the C0 pool baseline (16 MiB on a 32-thread read, not "a few MiB") were off; neither is a B3g row.
