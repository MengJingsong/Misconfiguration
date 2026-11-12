<!-- file: cases/file_cache_size-chunkcache-weightedsize--autonomous.md -->
# file_cache_size — verification solution

| Field | Value |
|---|---|
| Entry pointer | [`ChunkCache.java:151`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/ChunkCache.java#L151) (the target line builds the Caffeine cache; its `maximumWeight(cacheSize)` is on the next line, [`ChunkCache.java:152`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/ChunkCache.java#L152)) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code autonomous subagent, 2026-11-11 |
| Estimate | `positive`: when the chunk cache is enabled, the off-heap buffers it holds are capped by Caffeine's size-based eviction at `file_cache_size − 32 MiB`, with each entry weighed at its buffer's real capacity, so the cache's memory follows the setting. Overshoot comes only from evicted buffers that readers still reference, from buffers being loaded at the same moment, and from the pool keeping up to `file_cache_size` of slabs allocated. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `file_cache_size`, a `cassandra.yaml` configuration entry. It is declared at
[`Config.java:497`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L497)
(`public DataStorageSpec.IntMebibytesBound file_cache_size;`). The old name `file_cache_size_in_mb` is still accepted (`Config.java:496`).
- Unit: mebibytes (`IntMebibytesBound`, "Min unit: MiB", `conf/cassandra.yaml:752`).
- Default: `null` in `Config`. `DatabaseDescriptor.applySimpleConfig` sets it to `min(512, maxHeap/4 MiB)` (`DatabaseDescriptor.java:576-577`). With `-Xmx2G` that is 512 MiB, and with `-Xmx1G` it is 256 MiB. It is read through `DatabaseDescriptor.getFileCacheSizeInMiB()` (`DatabaseDescriptor.java:3784-3793`).
- Derived value: [`ChunkCache.java:50`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/ChunkCache.java#L50) sets `cacheSize = 1 MiB × max(0, file_cache_size − RESERVED_POOL_SPACE_IN_MiB)`, and `RESERVED_POOL_SPACE_IN_MiB = 32` (`ChunkCache.java:49`). The same setting is also the chunk-cache **buffer pool** limit, with no subtraction: `FILE_MEMORY_USAGE_THRESHOLD = file_cache_size × 1 MiB` (`BufferPools.java:38-39`).
- Gate: the cache only exists when `file_cache_enabled` is true **and** `cacheSize > 0` (`ChunkCache.java:53-54`). `file_cache_enabled` defaults to the system property `cassandra.file_cache_enabled`, which is false unless set (`Config.java:499`, `CassandraRelevantProperties.java:227`, `conf/cassandra.yaml:742`; disabled by default since CASSANDRA-16036). So `file_cache_size ≤ 32` turns the chunk cache off.
- How to set it: `file_cache_size: <N>MiB` in `cassandra.yaml`. You can also pass `-Dcassandra.config` with such a yaml, or call `DatabaseDescriptor.daemonInitialization(Supplier<Config>)` in a test. It cannot be changed at runtime: the values are `static final` and computed when the class initializes, and `setCapacity` throws `UnsupportedOperationException` (`ChunkCache.java:311-314`). A change needs a restart.

**A2. What it caps.** Off-heap (direct) memory: the uncompressed SSTable chunks held by the chunk cache. These are `ByteBuffer`s from the `chunk-cache` `BufferPool`, or on-heap buffers for compressors whose preferred type is `ON_HEAP`, such as Deflate (`DeflateCompressor.java:231`). The quantity compared against the limit is Caffeine's **weighted size**: the sum, over cached entries, of `buffer.capacity()` (weigher at `ChunkCache.java:154`). Cassandra exposes it as `ChunkCache.weightedSize()` (`ChunkCache.java:323-327`), as the metric `org.apache.cassandra.metrics:type=Cache,scope=ChunkCache,name=Size` (`CacheMetrics.java:70`), and in `nodetool info` "Chunk Cache … size" (`tools/nodetool/Info.java:129-133`).

**A3. Mechanism.**
1. Construction: [`ChunkCache.java:151-157`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/ChunkCache.java#L151-L157) builds a Caffeine `LoadingCache` with `.maximumWeight(cacheSize)` (L152), `.executor(ImmediateExecutor.INSTANCE)` (L153, so maintenance runs on the calling thread), the capacity weigher (L154) and `removalListener(this)` (L155). The instance is created once, at class initialization (`ChunkCache.java:54`).
2. Wiring: `FileHandle.Builder.complete` wraps the data-file reader with `maybeCached(...)`. This happens for compressed files under `mmap` (`FileHandle.java:411`), compressed files under standard I/O (`FileHandle.java:424`), and uncompressed files under standard I/O (`FileHandle.java:428-429`, chunk size rounded to a power of two between 4 and 64 KiB). Uncompressed mmapped files bypass the cache (`FileHandle.java:415-417`). `maybeWrap` returns the raw reader when the cache is disabled (`ChunkCache.java:193-199`).
3. Read path: `CachingRebufferer.rebuffer` calls `cache.get(new Key(file, alignedPos)).reference()` (`ChunkCache.java:241`). On a miss, `load` takes a buffer of `chunkSize()` bytes from the chunk-cache pool and reads the chunk into it (`ChunkCache.java:161-175`, pool call at L163).
4. **The enforcing check** is inside Caffeine (3.1.8, the version pinned in `.build/parent-pom-template.xml:1059-1061`). After a write, `afterWrite` schedules `maintenance` (`BoundedLocalCache.java:1528`, `:1707`), which calls `evictEntries()` (`:705`). Then [`BoundedLocalCache.evictFromMain`: `while (weightedSize() > maximum())`](https://github.com/ben-manes/caffeine/blob/v3.1.8/caffeine/src/main/java/com/github/benmanes/caffeine/cache/BoundedLocalCache.java#L768) evicts victims until the weighted size is ≤ `cacheSize`. Cassandra's own link in that chain is the configuration of the bound, [`ChunkCache.java:152`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/ChunkCache.java#L152). Because the executor is `ImmediateExecutor`, eviction runs synchronously on the thread that inserted.
5. Outcome when the limit is reached: the victim is removed, `onRemoval` → `Buffer.release()` (`ChunkCache.java:177-181`). When the reference count reaches 0, the buffer goes back to the pool (`ChunkCache.java:140-144`). Reads never fail. They just miss more often.
6. Second, separate check, on the pool: `BufferPool.GlobalPool.allocateMoreChunks` refuses a new 1 MiB macro-chunk when `memoryAllocated + 1 MiB > file_cache_size` (`BufferPool.java:443`). The caller then falls back to a plain `ByteBuffer.allocateDirect`, counted as "overflow" (`BufferPool.java:923`, `:233-239`, `:261-264`). The pool limit therefore does not bound memory. It only decides between pooled and unpooled buffers.

**Overshoot and bypass paths:**
- (a) An evicted `Buffer` that a reader still references is not freed until the last `release()` (`ChunkCache.java:142-143`). The overshoot is bounded by the number of concurrent readers × chunk size.
- (b) Caffeine documents that the cache "may temporarily exceed the threshold" during eviction. Concurrent loads by many threads add at most about (threads × chunk) above the cap.
- (c) Pool slabs, once allocated, are retained up to `file_cache_size` (`memoryAllocated` is never reduced except by `unsafeReset`, `BufferPool.java:1630-1632`). Process-level direct memory can therefore stay at about `file_cache_size` even after the cache empties.
- (d) Heap overhead per entry (`Key`, `Buffer`, Caffeine node, roughly 128 B per chunk per `conf/cassandra.yaml:748-750`) is not weighed.
- (e) Uncompressed mmapped data files (`disk_access_mode: mmap`) are not cached at all.

**A4. Other consumers.** Off-heap memory that this constraint does not control:
- The `networking` buffer pool (`networking_cache_size`, `BufferPools.java:44-45`) and Netty's allocator.
- Off-heap memtables (`memtable_offheap_space`).
- Bloom filters, compression metadata (offsets), and the index summary / BTI partition index.
- mmapped index files (page cache, outside the process's direct memory).
- `CompressedChunkReader.Standard`'s compressed-input buffers.
- Hints and commit-log compression buffers.
- The key, row and counter caches (heap or off-heap).
- JVM internals (thread stacks, code cache, metaspace).

**A5. Evidence beyond the source.**
- `conf/cassandra.yaml:744-753`: the documentation of the 32 MiB reservation and the default.
- CHANGES.txt: CASSANDRA-5863 (cache introduced), CASSANDRA-16036 (disabled by default), CASSANDRA-15229 (separate chunk-cache pool), CASSANDRA-13897 (power-of-two rounding).
- Caffeine `maximumWeight` javadoc: https://javadoc.io/doc/com.github.ben-manes.caffeine/caffeine/3.1.8/com.github.benmanes.caffeine.cache/com/github/benmanes/caffeine/cache/Caffeine.html#maximumWeight(long). It says the cache "may evict an entry before this limit is exceeded or temporarily exceed the threshold while evicting".
- Caffeine source at v3.1.8: `BoundedLocalCache.java` (lines cited above).

## B. Verification solution

**B1. Claim under test.** With `file_cache_enabled: true`:
- The chunk cache's weighted size (the sum of its buffers' capacities) never exceeds `cacheSize = (file_cache_size − 32) MiB` by more than (concurrent loading/reading threads × chunk size).
- The off-heap memory the node actually uses for the chunk-cache pool rises with `file_cache_size` and stays within about `file_cache_size` (+ the same small slack), however much data is read.

The claim is wrong if the weighted size or the pool's `Size` grows past these bounds as more distinct data is read.

### B2. Unit tier

**B2a. Environment and build.**
- Platform: Linux, JDK 11, Ant.
- Copy the tree to local disk first: `rsync -a <source>/ /local/o05/cassandra-5.0.9/` (never build in the shared tree). Then run `cd /local/o05/cassandra-5.0.9 && ant jar build-test` (once).
- Test source to add **in the copy**: `test/unit/org/apache/cassandra/io/util/ChunkCacheCapTest.java`. It goes in this package because `SimpleChunkReader`'s constructor is package-private (`SimpleChunkReader.java:30`).
- JVM options are passed through `-Dtest.jvm.args` (`build.xml:1192`).

```java
package org.apache.cassandra.io.util;

import java.nio.file.Files;
import java.util.*;
import org.junit.*;
import org.apache.cassandra.cache.ChunkCache;
import org.apache.cassandra.config.*;
import org.apache.cassandra.io.compress.BufferType;
import org.apache.cassandra.utils.memory.BufferPools;

public class ChunkCacheCapTest
{
    static final int FCS = Integer.getInteger("fcs.mib", 64);           // knob: file_cache_size in MiB
    static final int FILE_MIB = Integer.getInteger("file.mib", 2 * FCS + 64);
    static final int HOLD = Integer.getInteger("hold.chunks", 0);       // chunks kept referenced (overshoot probe)
    static final int CHUNK = 65536;

    @BeforeClass
    public static void setup()
    {
        DatabaseDescriptor.daemonInitialization(() -> {
            Config c = DatabaseDescriptor.loadConfig();
            c.file_cache_enabled = true;
            c.file_cache_size = new DataStorageSpec.IntMebibytesBound(FCS);
            return c;
        });
    }

    @Test
    public void cap() throws Exception
    {
        if (FCS <= ChunkCache.RESERVED_POOL_SPACE_IN_MiB) { System.out.println("O05 instance=" + ChunkCache.instance); return; }
        File f = FileUtils.createTempFile("o05", ".bin");
        byte[] block = new byte[1 << 20]; new Random(5).nextBytes(block);
        try (java.io.OutputStream o = Files.newOutputStream(f.toPath()))
        { for (int i = 0; i < FILE_MIB; i++) o.write(block); }
        long max = 0; List<Rebufferer.BufferHolder> held = new ArrayList<>();
        try (ChannelProxy ch = new ChannelProxy(f))
        {
            RebuffererFactory rf = ChunkCache.maybeWrap(new SimpleChunkReader(ch, f.length(), BufferType.OFF_HEAP, CHUNK));
            Rebufferer rb = rf.instantiateRebufferer(false);
            for (int pass = 0; pass < 2; pass++)
                for (long pos = 0, i = 0; pos < f.length(); pos += CHUNK, i++)
                {
                    Rebufferer.BufferHolder h = rb.rebuffer(pos);
                    if (pass == 0 && i < HOLD) held.add(h); else h.release();
                    max = Math.max(max, ChunkCache.instance.weightedSize());
                    if (i % 256 == 0)
                        System.out.printf("O05 pass=%d i=%d w=%d entries=%d poolSize=%d overflow=%d%n", pass, i,
                                          ChunkCache.instance.weightedSize(), ChunkCache.instance.size(),
                                          BufferPools.forChunkCache().sizeInBytes(), BufferPools.forChunkCache().overflowMemoryInBytes());
                }
            System.out.printf("O05 FINAL fcs=%d cacheSize=%d maxW=%d w=%d entries=%d poolSize=%d overflow=%d held=%d%n",
                              FCS, ChunkCache.cacheSize, max, ChunkCache.instance.weightedSize(), ChunkCache.instance.size(),
                              BufferPools.forChunkCache().sizeInBytes(), BufferPools.forChunkCache().overflowMemoryInBytes(), held.size());
            held.forEach(Rebufferer.BufferHolder::release);
            ChunkCache.instance.invalidateFile(ch.filePath());
        }
        finally { f.tryDelete(); }
    }
}
```

**B2b. Knobs.** `fcs.mib` (the value of `file_cache_size`), one JVM per value, because the value is read once when the class initializes:
- `32`: `cacheSize = 0`, so the cache is disabled. Control.
- `33`: `cacheSize = 1 MiB`, the smallest possible.
- `64`: 32 MiB.
- `128`: 96 MiB.
- `256`: 224 MiB.

The values span roughly a factor of 200 in `cacheSize`, so the relation between the setting and usage is visible. A separate overshoot probe: `fcs.mib=64` with `hold.chunks=1024` (64 MiB referenced, twice the cap).

**B2c. Workload.** One sequential pass, then a second pass, over a file of `2·FCS + 64` MiB of random bytes in 64 KiB chunks. Each chunk is a distinct key, so a pass inserts `(2·FCS+64)·16` entries of 65536 B each. The weight inserted per pass is `2·FCS + 64` MiB, which is more than `cacheSize = FCS − 32` MiB by over 2×, so eviction must run. For example, with FCS=64 the file is 192 MiB (3072 chunks) against a 32 MiB cap (512 chunks). The file sits in `build/tmp` in the local copy (≤ 576 MiB).

**B2d. Observables and instruments.**
- Usage-side (the check's own operand), printed every 256 chunks and at the end:
  - `ChunkCache.instance.weightedSize()` (the operand).
  - `size()` (entries).
  - The running maximum of the weighted size after every `rebuffer`.
  - `BufferPools.forChunkCache().sizeInBytes()` and `overflowMemoryInBytes()` (the pool's allocated memory).
- Limit side: `ChunkCache.cacheSize` (printed).
- Cannot be observed: Caffeine's internal transient state while one insert is being evicted (sampling happens after `rebuffer` returns). The heap overhead per entry is not measured in this tier.

**B2e. Procedure.**
1. `cd /local/o05/cassandra-5.0.9`
2. Add the test file above.
3. `ant build-test`
4. For each N in 32 33 64 128 256, run:
   `ant testsome -Dno-build-test=true -Dtest.name=org.apache.cassandra.io.util.ChunkCacheCapTest -Dtest.jvm.args="-Dfcs.mib=N -Xmx2G -XX:MaxDirectMemorySize=2G" 2>&1 | tee /local/o05/unit-N.log`
5. Overshoot probe: `... -Dtest.jvm.args="-Dfcs.mib=64 -Dhold.chunks=1024 -Xmx2G -XX:MaxDirectMemorySize=2G"`
6. Extract the results: `grep 'O05 FINAL' /local/o05/unit-*.log`
7. Check that `build/tmp` has no `o05*.bin` left, and that `pgrep -f ChunkCacheCapTest` returns nothing.

**B2f. Predictions** (stated before any run; the test is single-threaded, so the slack is one chunk = 65536 B):

| fcs.mib | cacheSize (B) | maxW | final entries | poolSize |
|---|---|---|---|---|
| 32 | 0 | n/a: prints `instance=null` | — | — |
| 33 | 1 048 576 | ≤ 1 048 576 (+65 536) | ≤ 16 | ≤ 33 MiB, overflow 0 |
| 64 | 33 554 432 | ≤ 33 554 432 (+65 536); ends at ≥ 0.9× cap | ≤ 512 | ≤ 64 MiB, overflow 0 |
| 128 | 100 663 296 | ≤ cap (+65 536) | ≤ 1536 | ≤ 128 MiB, overflow 0 |
| 256 | 234 881 024 | ≤ cap (+65 536) | ≤ 3584 | ≤ 256 MiB, overflow 0 |

Probe (64, hold 1024):
- `maxW` stays ≤ 32 MiB (+65 536). Held entries are evicted from the cache but not freed.
- `poolSize` reaches 64 MiB (the pool limit), and `overflow` > 0, about ≥ 32 MiB at the moment the 1024 chunks are held. This shows path A3(a): the operand stays capped while the real buffer memory exceeds it.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `maxW` ≤ cacheSize + 65 536 for every N, and final w within 10 % of cacheSize | Mechanism works as traced; supports the claim |
| `maxW` grows with file size past cacheSize (e.g. ≈ 192 MiB for N=64) | Claim wrong: the weight bound is not enforced |
| final w far below cacheSize (< 50 %) for all N | Cache evicts too aggressively or keys collide; the cap holds but usage does not *follow* the setting; investigate |
| `instance=null` for N=32, and a non-null instance whose w grows up to its cap for N≥33 | Gate works; positive control that the workload does move the operand |
| `poolSize` > N MiB with overflow 0 | Pool limit check (`BufferPool.java:443`) broken |
| Probe: overflow > 0 while maxW ≤ cap | Confirms the referenced-buffer overshoot path A3(a) |

**B2h. Controls.**
- N=32 shows that the gate disables the cache, and the run must print `instance=null`.
- The first pass of each run shows w rising from 0 to about the cap (positive control: the workload moves the operand where the cap binds).
- The second pass shows w stays flat, so it is not a one-off.
- `ChunkCache.cacheSize` is printed, so the derived cap is read and not assumed.
- The file is random, so its content is irrelevant to the cached weight, which depends only on chunk size.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node, JDK 11, built from the local copy with `ant jar`. tools/bin/cassandra-stress comes from the same build.
- Data, commit log, hints and saved caches go on local disk with ≥ 15 GiB free (e.g. `/local/o05/node/{data,commitlog,hints,saved_caches}`). Logs go in `/local/o05/node/logs` (`CASSANDRA_LOG_DIR`).
- `conf/cassandra.yaml` (in the copy) changes:
  - `file_cache_enabled: true`
  - `file_cache_size: <N>MiB`
  - `disk_access_mode: mmap_index_only` (default; compressed data goes through the cache in any mode)
  - the directory keys above
  - `listen_address`/`rpc_address: 127.0.0.1`
  - `key_cache_size: 0MiB` and `row_cache_size: 0MiB` (removes other caches)
- `conf/jvm-server.options` (or env): `MAX_HEAP_SIZE=2G` (so the default would be 512 MiB), `-XX:MaxDirectMemorySize=4G` (direct-memory headroom, so the pool is never limited by the JVM), and `-XX:NativeMemoryTracking=summary`.

**B3b. Knobs.** One node restart per value (no runtime change possible):
- `file_cache_enabled: false` (baseline).
- `file_cache_size: 64MiB`, `256MiB` and `512MiB` (cacheSize 32 / 224 / 480 MiB).

**B3c. Workload.**
1. Write: `tools/bin/cassandra-stress write n=4000000 -col n=FIXED(5) size=FIXED(200) -rate threads=32 -node 127.0.0.1`. The rows are about 1 KiB each, with random column values. That gives about 4 GiB of uncompressed data, roughly 260 000 distinct 16 KiB LZ4 chunks (`CompressionParams.java:48`) against at most 30 720 cacheable chunks at 512 MiB.
2. Then `nodetool flush keyspace1`.
3. Read: `cassandra-stress read duration=10m -pop dist=UNIFORM(1..4000000) -rate threads=32`. Each read touches at least one data chunk. 10 minutes at even 5k op/s is 3M reads, and that covers the cache (≥ 30 720 distinct chunks) many times over.

**B3d. Observables and instruments** (sample every 30 s during the read phase with a shell loop writing to `/local/o05/s-N.csv`):
- Operand: `nodetool info | grep 'Chunk Cache'` gives entries, size and capacity.
- Pool: `nodetool sjk mx -mg -b 'org.apache.cassandra.metrics:type=BufferPool,scope=chunk-cache,name=Size' -f Value`, and the same for `name=OverflowSize`, and for `scope=networking,name=Size`.
- Actual resource:
  - `nodetool sjk mx -mg -b 'java.nio:type=BufferPool,name=direct' -f MemoryUsed` (all direct buffers in the JVM).
  - `jcmd <pid> VM.native_memory summary | grep -A2 '^-  *Other'` (direct `ByteBuffer`s are under "Other" in JDK 11).
  - RSS from `ps -o rss= -p <pid>`.
- Cannot observe directly: which direct bytes belong to the chunk cache, as opposed to the networking pool, Netty and the compression scratch buffers. This is handled by subtracting the `enabled:false` baseline and the networking pool `Size`.

**B3e. Procedure.**
1. Set up the copy, build, and set the yaml. Start with `bin/cassandra -p /local/o05/node/pid`. Wait until `nodetool status` shows UN.
2. Run the write workload and flush. Record the disk use with `du -sh /local/o05/node/data`.
3. For each knob value:
   1. Stop the node (`kill $(cat pid)` and wait).
   2. Set the yaml and start the node (the data is kept).
   3. Wait for UN, then sample for 60 s (idle).
   4. Run the read workload for 10 minutes while sampling.
   5. Sample for 60 s after it ends.
4. Stop the node. Check with `pgrep -f CassandraDaemon` and `pgrep -f cassandra-stress` (both must be empty). Remove `/local/o05/node`.

**B3f. Predictions** (stated before any run):

| setting | Chunk Cache capacity | Chunk Cache size (steady, during reads) | chunk-cache pool Size | direct MemoryUsed vs baseline |
|---|---|---|---|---|
| disabled | line absent / error | — | 0 | baseline B |
| 64 MiB | 32 MiB | 29–32 MiB (≤ 32 MiB + 32 × 16 KiB) | ≤ 64 MiB + OverflowSize; OverflowSize ≈ 0 | ≈ B + 32..64 MiB |
| 256 MiB | 224 MiB | 200–224 MiB | ≤ 256 MiB, overflow ≈ 0 | ≈ B + 224..256 MiB |
| 512 MiB | 480 MiB | 430–480 MiB | ≤ 512 MiB, overflow ≈ 0 | ≈ B + 480..512 MiB |

The increase over the baseline should be monotone in N and never exceed N + 16 MiB. The claim is wrong if the cache size or the direct memory keeps rising during the 10 minutes past these bounds. For example, at 64 MiB, a direct-memory delta > 100 MiB, or a Chunk Cache size > 33 MiB on any sample.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Chunk Cache size plateaus at about capacity for each N, and the direct-memory delta is about N | Claim confirmed: the cap governs real off-heap use |
| size plateaus but the direct delta grows far beyond N (overflow climbing) | Operand capped but actual usage not; overshoot via referenced buffers / overflow (A3 a–c) dominates; claim refuted for the actual resource |
| size exceeds capacity persistently | Caffeine bound not enforced; claim refuted |
| delta for 512 MiB ≈ delta for 64 MiB | Usage does not follow the setting (e.g. the cache is not on the read path); investigate whether reads hit the cache (Requests/Misses counters) |
| Chunk Cache size rises from 0 to capacity in the first minutes of reading (positive control) | Workload moves usage where the cap binds |
| Requests counter does not grow | Workload did not exercise the cache; result not confirmed |

**B3h. Controls.**
- The baseline (`enabled:false`) removes the other off-heap consumers (A4). The networking pool `Size` is read separately.
- The key and row caches are off.
- The same dataset and the same read workload are used for every setting.
- The idle samples taken before reading show that the cache memory appears only under reads.
- The `Requests`/`Misses` counters show the cache is on the read path.
- `-XX:MaxDirectMemorySize=4G` ensures the JVM direct limit is not the cap being observed.

**B4. Risks and cleanup.**
- Disk: the unit tier writes ≤ 576 MiB to `build/tmp` of the local copy and deletes it in `finally`. The cluster tier writes about 4–6 GiB of data plus the commit log under `/local/o05/node`, on local disk with ≥ 15 GiB free.
- Nothing goes on shared storage, and the shared source tree is untouched (everything happens in the copy).
- Processes: after each tier, check `pgrep -f ChunkCacheCapTest`, `pgrep -f CassandraDaemon` and `pgrep -f cassandra-stress`, and kill any leftovers.
- Cleanup: `rm -rf /local/o05/node /local/o05/cassandra-5.0.9/build/tmp/o05*`. Keep the logs and CSVs.

## C. Sources read

- /users/jason92/writeup-ext/playbook-autonomous.md
- /users/jason92/writeup-ext/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/cache/ChunkCache.java
- src/java/org/apache/cassandra/config/Config.java
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java
- src/java/org/apache/cassandra/utils/memory/BufferPools.java
- src/java/org/apache/cassandra/utils/memory/BufferPool.java
- src/java/org/apache/cassandra/metrics/ChunkCacheMetrics.java
- src/java/org/apache/cassandra/metrics/CacheMetrics.java
- src/java/org/apache/cassandra/metrics/BufferPoolMetrics.java
- src/java/org/apache/cassandra/io/util/FileHandle.java
- src/java/org/apache/cassandra/io/util/DiskOptimizationStrategy.java
- src/java/org/apache/cassandra/io/util/CompressedChunkReader.java
- src/java/org/apache/cassandra/io/util/SimpleChunkReader.java
- src/java/org/apache/cassandra/io/util/ChannelProxy.java
- src/java/org/apache/cassandra/io/util/FileUtils.java
- src/java/org/apache/cassandra/io/util/File.java
- src/java/org/apache/cassandra/io/util/Rebufferer.java
- src/java/org/apache/cassandra/io/compress/LZ4Compressor.java
- src/java/org/apache/cassandra/io/compress/DeflateCompressor.java
- src/java/org/apache/cassandra/schema/CompressionParams.java
- src/java/org/apache/cassandra/tools/nodetool/Info.java
- conf/cassandra.yaml
- conf/cassandra-env.sh
- test/conf/cassandra.yaml
- build.xml
- .build/parent-pom-template.xml
- CHANGES.txt
- NEWS.txt
- https://raw.githubusercontent.com/ben-manes/caffeine/v3.1.8/caffeine/src/main/java/com/github/benmanes/caffeine/cache/BoundedLocalCache.java
- https://javadoc.io/doc/com.github.ben-manes.caffeine/caffeine/3.1.8/com.github.benmanes.caffeine.cache/com/github/benmanes/caffeine/cache/Caffeine.html#maximumWeight(long) (cited for the documented contract; not fetched)

## D. Stage-4 feedback

**Stage-4 audit amendments (2026-11-11, before any reading; results file [`file_cache_size-chunkcache-weightedsize--autonomous`](../../stage4-runtime-verification/results/file_cache_size-chunkcache-weightedsize--autonomous.md) §1).** They apply to the sections named; where a prediction cell changes (AM2) the reason is in the source, not in any reading. The text of B2f, B2g, B3f and B3g above is unchanged.

- **AM1 (A3 step 6, B2f probe; citation).** The pool's macro-chunk is **8 MiB**, not 1 MiB: `MACRO_CHUNK_SIZE = 64 * NORMAL_CHUNK_SIZE` with `NORMAL_CHUNK_SIZE = 128 KiB` (`BufferPool.java:128`, `:385`; the comment on `:384` says 1 MiB). `allocateMoreChunks` refuses when `memoryAllocated + 8 MiB > file_cache_size` (`:443`), so the pooled part grows in 8 MiB steps up to `floor(N/8)·8` MiB. `sizeInBytes()` (the B2d `poolSize` and the B3d pool `Size`) is `memoryAllocated + overflow` (`:274-277`). The bounds "poolSize ≤ N MiB, overflow 0" are unchanged.
- **AM2 (B3f, row `disabled`, column pool Size).** Read "**small, not 0: a multiple of 8 MiB, ≤ 32 MiB**" instead of `0`. With the cache disabled, compressed data files are read through `BufferManagingRebufferer`, whose per-reader buffer comes from the same `chunk-cache` pool (`BufferManagingRebufferer.java:45`, `CompressedChunkReader.java:95`), and `memoryAllocated` never shrinks (A3(c)). The baseline subtraction of B3h is unchanged; the direct-memory baseline B already includes these buffers.
- **AM3 (B3c; runbook).** The write uses `-schema "replication(factor=1)" compression=LZ4Compressor` so the data is LZ4 with 16 KiB chunks as B3c assumes (cassandra-stress otherwise writes `WITH compression = {}`, `SettingsSchema.java:141-145`). The read uses the same `-col n=FIXED(5) size=FIXED(200)`. Both use `-node 127.0.0.1 -port native=9342 jmx=7499`.
- **AM4 (B3e step 2; runbook).** After the flush, wait until `nodetool compactionstats` shows 0 pending tasks before the first read phase, so every setting reads the same SSTables; record `nodetool tablestats keyspace1.standard1` (SSTable count, space used, compression ratio).
- **AM5 (B3d; instruments).** One JMX sampler (`O05Jmx.java` in the harness) every 30 s reads the same MBeans exactly, in bytes: `ChunkCache` `Capacity`, `Size`, `Entries`, `Requests`, `Misses`; `BufferPool` `chunk-cache` `Size`, `OverflowSize`, `UsedSize`; `BufferPool` `networking` `Size`; `java.nio:type=BufferPool,name=direct` `MemoryUsed`, `Count`. With it each sample records `jcmd VM.native_memory summary` "Other" (committed) and `RssAnon`. `nodetool info` is taken once per phase as a cross-check. This replaces `nodetool info | grep` and the `sjk` calls (one JVM per attribute).
- **AM6 (B2a, B2e, B3a, B3e; environment).** `/local/o05` is `/mydata/jingsong-cass-s4/o05` on the run node. Node ports: storage 7300, ssl 7301, JMX 7499, native 9342. `MAX_HEAP_SIZE=2G` with G1 (no `HEAP_NEWSIZE`). `ant testsome` forks its JVM with `maxmemory=1024m` (`build.xml:1153`), which overrides `-Xmx2G`; the unit tier holds its cached data off-heap, so the heap size does not bear on the readings.
- **AM7 (B2a test; instrument only).** The test also prints one line `O05 EVID fcs=N misses=<ChunkCache metrics misses> requests=<requests>` after the FINAL line, as direct evidence that the disallow branch (eviction) ran: misses (= loads = insertions) far above the final entry count. The FINAL line is unchanged.
- **AM8 (B3g; terms defined).** "Plateaus at about capacity": every sample of the read phase from minute 3 to the end lies within the B3f band for that N (64: 29 MiB to 32 MiB + 512 KiB; 256: 200 MiB to 224 MiB + 512 KiB; 512: 430 MiB to 480 MiB + 512 KiB). "Exceeds capacity persistently": any read-phase sample above capacity + 512 KiB (32 × 16 KiB). "Direct-memory delta about N": the median of the steady read samples of `direct MemoryUsed` minus the median of the steady read samples of the disabled baseline lies within [cacheSize − 16 MiB, N + 16 MiB], and the deltas rise with N. "Delta for 512 ≈ delta for 64": the two deltas differ by less than 64 MiB. "Overflow climbing": `OverflowSize` above 16 MiB on any read sample or rising by more than 16 MiB from minute 3 to the end. A reading that matches no row is "Not confirmed (no matching row)".
- **AM9 (B2e step 6; runbook defect D1, 2026-11-11, found by unit attempt 1; prediction and conclusions unchanged).** The test's `printf` reaches the junit log one write at a time, each as its own `SubstituteLogger` line, so `grep 'O05 FINAL'` shows only the label `O05 FINAL fcs=` without the values. Extract the readings by joining the fragments (the harness's `unit-analyze.py`, or `grep -A20 'O05 FINAL'`). The unit tier restarted from its beginning after this fix.

**Stage-4 verdict (2026-11-11, results file [`file_cache_size-chunkcache-weightedsize--autonomous`](../../stage4-runtime-verification/results/file_cache_size-chunkcache-weightedsize--autonomous.md)).** Unit tier **Confirmed — caps** (B2g row 1, with rows 4 and 6): for N = 33, 64, 128, 256 the weighted size peaked exactly at `cacheSize` and the pool at N MiB with no overflow; one B2f probe cell missed (overflow 6.7 MiB, not about ≥ 32 MiB, because the cached entries were a subset of the held ones). Cluster tier **Confirmed — caps** (B3g row 1, with row 5): Chunk Cache Size held exactly at 32 / 224 / 480 MiB through 10 minutes of uniform reads, OverflowSize 0, direct memory above the disabled baseline 47.9 / 240.0 / 496.2 MiB. Outcome class: **true positive**. Notes for A3: the pool's macro-chunk is 8 MiB (AM1), and real off-heap use is about `file_cache_size` (the pool fills its 32 MiB headroom), not `file_cache_size − 32`.
