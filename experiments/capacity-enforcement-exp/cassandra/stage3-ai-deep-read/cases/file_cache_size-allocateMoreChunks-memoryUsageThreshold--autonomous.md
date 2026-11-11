# file_cache_size (and networking_cache_size) — verification solution  <!-- file: cases/file_cache_size-allocateMoreChunks-memoryUsageThreshold--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`BufferPool.java:445`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L445) (`if (memoryUsageThreshold > 0)`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (claude-opus-5-5[1m]), Claude Code CLI, 2026-10-26 (Band D triage batch) |
| Estimate | `positive`. The operand `memoryUsageThreshold` is `file_cache_size` (chunk-cache pool) or `networking_cache_size` (networking pool) converted to bytes. The enclosing check at `BufferPool.java:443` refuses a new 1 MiB macro chunk once `memoryAllocated + 1 MiB > memoryUsageThreshold`, so the **pooled slab memory** stays at or below the setting. Caveat: the target line itself only decides whether the "Maximum memory usage reached" message is logged. It returns `null` either way, and requests the pool cannot serve go to unpooled direct buffers, which no limit bounds. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- `file_cache_size`: a configuration entry, [`Config.java:497`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L497) (`DataStorageSpec.IntMebibytesBound`; the old name `file_cache_size_in_mb` is accepted through `@Replaces`, [`Config.java:496`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L496)). Unit is MiB, minimum unit MiB (`conf/cassandra.yaml:744-753`). Default: if the key is not set, it is `min(512, maxHeap/4 MiB)` ([`DatabaseDescriptor.java:576-577`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L576-L577)). It is read once by `DatabaseDescriptor.getFileCacheSizeInMiB()` ([`DatabaseDescriptor.java:3784-3793`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L3784-L3793), which returns 0 in client mode) and frozen into the `static final FILE_MEMORY_USAGE_THRESHOLD = MiB*1024*1024` ([`BufferPools.java:38`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPools.java#L38)). That value is passed to `new BufferPool("chunk-cache", ..., true)` ([`BufferPools.java:39`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPools.java#L39)), so a change needs a restart. It is not settable through JMX.
- `networking_cache_size`: [`Config.java:494`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L494), default `min(128, maxHeap/16 MiB)` ([`DatabaseDescriptor.java:573-574`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L573-L574)). It becomes `NETWORKING_MEMORY_USAGE_THRESHOLD` and is passed to `new BufferPool("networking", ..., false)` ([`BufferPools.java:44-45`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPools.java#L44-L45)). The rest is the same as above.
- The pool stores the value in `BufferPool.memoryUsageThreshold` (`BufferPool.java:142,186-189`) and exposes it as the `Capacity` gauge ([`BufferPoolMetrics.java:58`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/BufferPoolMetrics.java#L58)).


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../../../stage3-ai-deep-read/README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** Off-heap (direct) memory: the bytes of 1 MiB macro chunks the pool has allocated, `memoryAllocated` (`BufferPool.java:158`). The check compares `memoryAllocated + MACRO_CHUNK_SIZE` (1 MiB, `BufferPool.java:385`) against `memoryUsageThreshold` (`BufferPool.java:443`). It does **not** cap `overflowMemoryUsage` (`BufferPool.java:148`), the unpooled direct or heap buffers that the pool hands out when it cannot serve a request.

**A3. Mechanism.**
1. `LocalPool.get(size)` calls `tryGet` ([`BufferPool.java:903-910`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L903-L910)). For sizes over 128 KiB it returns `null` at once (`:938-942`). Otherwise the local chunks are tried, then a normal chunk is taken from `GlobalPool.get()` (`:410-416`).
2. `GlobalPool.getInternal` polls the free `chunks` queue first. If that is empty it calls `allocateMoreChunks()`, then polls `chunks` once more, then `partiallyFreedChunks` (`:418-433`).
3. `allocateMoreChunks` (`:439-485`): in a CAS loop, if `cur + 1 MiB > memoryUsageThreshold` (`:443`) the target branch runs. **Target `:445`:** when `memoryUsageThreshold > 0` it writes a NoSpamLogger INFO "Maximum memory usage reached (...) for <name> buffer pool, cannot allocate chunk of 1 MiB", at most once per 15 min (`:131,447-448`). With a threshold of 0 it stays silent. Both outcomes `return null` (`:450`). Otherwise `memoryAllocated` is CAS-increased by 1 MiB **before** the allocation (`:452`). `allocateDirectAligned(1 MiB)` allocates `1 MiB + pageSize` bytes (`:1096-1103`). The slab is split into 8 normal chunks of 128 KiB (`:476-483`).
4. If the slab cannot be had, `LocalPool.get` falls back to `allocate(size, OFF_HEAP)` → `ByteBuffer.allocateDirect(size)` and `overflowMemoryUsage += size` (`:233-239,912-924`). This path is unbounded except by `-XX:MaxDirectMemorySize`. Config `buffer_pool_use_heap_if_exhausted` ([`Config.java:514`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L514)) is declared but not referenced anywhere in `src/java`, so the fallback is always off-heap.
5. If `allocateDirectAligned` throws OOM, the CAS increment is **not** rolled back (`:458-468`), so `memoryAllocated` can count bytes that were never allocated. That error path wastes capacity but cannot overshoot it.
6. Overshoot per slab: `memoryAllocated` never exceeds the threshold. Real native memory per slab is 1 MiB plus one page of alignment padding. A threshold that is not a multiple of 1 MiB is effectively rounded down (`floor(T / 1 MiB)` slabs).
7. Chunks are never freed back to the OS while the pool lives (`macroChunks`, `:468`). Recycling only returns them to `chunks` or `partiallyFreedChunks` (`:487-499`), so `memoryAllocated` only grows.

**A4. Other consumers.** Unpooled overflow buffers from the same pool (step 4). Buffers larger than 128 KiB are always unpooled (`:938-942`). Every other `ByteBuffer.allocateDirect` in the node: Netty's own allocator, memtable `offheap_buffers` slabs, `MemoryUtil`/`Memory` native allocations (bloom filters, index summaries, compression offsets), and the hints and commitlog buffers. The chunk cache keeps buffers from this pool up to `file_cache_size - 32 MiB` of weight (`ChunkCache.java:49-54,152`). The other 32 MiB is left for transient reader buffers (`BufferManagingRebufferer` and `CompressedChecksummedDataInput`, both of which use `forChunkCache()`). Users of the networking pool are in `net/*` (`FrameEncoder`, `BufferPoolAllocator`, `ShareableBytes`, and others) and `CassandraStreamWriter`.

**A5. Evidence beyond the source.** `conf/cassandra.yaml:730-759` (comments: "Maximum memory to use ... This pool is allocated off-heap ... Memory is only allocated when needed"). `test/unit/org/apache/cassandra/utils/memory/BufferPoolTest.java:43,162` builds pools with 8 MiB and with ½ MiB thresholds (the ½ MiB pool can never allocate a slab). JDK `java.nio.BufferPoolMXBean` (https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/BufferPoolMXBean.html) and NMT (https://docs.oracle.com/en/java/javase/11/vm/native-memory-tracking.html) are used for the instruments.

## B. Verification solution

**B1. Claim under test.** For a BufferPool with threshold T bytes, the pooled slab memory (`Size - OverflowSize`, which equals `memoryAllocated`) never exceeds `floor(T/1 MiB)·1 MiB`, and it reaches that ceiling when demand is larger. Demand beyond the ceiling appears as `OverflowSize` (unpooled direct memory) and is not capped. The target branch (`:445`) writes the "Maximum memory usage reached" message exactly when T > 0 and the cap is hit, and stays silent for T = 0.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant. `git clone --branch cassandra-5.0.9 --depth 1 <local mirror of the shared clone> /local/tmp/c509 && cd /local/tmp/c509 && ant jar build-test`. Put the new test at `test/unit/org/apache/cassandra/utils/memory/BufferPoolCapProbeTest.java` (package `org.apache.cassandra.utils.memory`, so the package-private `GlobalPool.MACRO_CHUNK_SIZE` and `unsafeFree` are visible). No `DatabaseDescriptor` initialisation is needed: `BufferPoolTest` builds `BufferPool` directly. The default `build.xml` test JVM options are enough. The direct memory needed is at most about 40 MiB.

> **Amendment U1 (2026-10-27, stage-4 audit; host clone and build).** On the advisor's Mac (macOS 27 arm64, JDK 11.0.32.1, Ant
> 1.10.18; no `/local`): `source ~/Library/Caches/stage4/env.sh; git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run63`
> (a full clone) and `ant -Dlocal.repository=$W/m2 build-test` in it. The test is
> `harness/file_cache_size-allocateMoreChunks-memoryUsageThreshold--autonomous/BufferPoolCapProbeTest.java`; `unit-run.sh` in that
> folder copies it to the path above, runs U2's commands and removes it again.

**B2b. Knobs.** The threshold T is passed to `new BufferPool("probe-" + T, T, false)`. Values: `0`, `1.5 MiB` (1572864, not a multiple of 1 MiB), `4 MiB`, `8 MiB`, `16 MiB`. T = 0 tests the silent branch of `:445`. 1.5 MiB tests the rounding-down. The other three show that pooled memory follows T.

**B2c. Workload.** In one thread, call `pool.get(65536, BufferType.OFF_HEAP)` 384 times and keep every buffer (384 × 64 KiB = 24 MiB of demand, larger than every T). Then put all of them back. Repeat for each T with a fresh pool. Each 64 KiB request takes 32 of the 64 slots of a 128 KiB normal chunk (unit = 2 KiB), so 16 requests fill 1 MiB and one slab serves 16 buffers. For T = 4 MiB, the 4 slabs serve 64 buffers and the other 320 overflow (20 MiB).

**B2d. Observables and instruments.** After the gets, read `pool.sizeInBytes()`, `pool.overflowMemoryInBytes()` and `pool.usedSizeInBytes()`. Pooled = size − overflow. Also check that the INFO line `Maximum memory usage reached` with name `probe-<T>` is present in `build/test/logs/TEST-org.apache.cassandra.utils.memory.BufferPoolCapProbeTest.log` (the root level is DEBUG, `test/conf/logback-test.xml:74`). Native memory is not observed in this tier.

**B2e. Procedure.**
1. Write the test with one `@Test` per T. Each test asserts nothing and only prints `T, pooled, overflow, used, buffersServedFromPool`. Count a buffer as served from the pool when `BufferPool.Chunk.getParentChunk(buf) != null` (`BufferPool.java` Chunk API).
2. Release all buffers, then call `pool.unsafeFree()` in `@After`.
3. `ant testsome -Dtest.name=org.apache.cassandra.utils.memory.BufferPoolCapProbeTest`.
4. `grep -c "Maximum memory usage reached" build/test/logs/TEST-*BufferPoolCapProbeTest*.log`, then grep for each pool name.

> **Amendment U2 (2026-10-27, stage-4 audit; one JVM per value, the default value, exact procedure).** (a) The message at `:447`
> goes through one `static` NoSpamLogger (`BufferPool.java:135`) whose statements are keyed by the format string
> (`NoSpamLogger.java:212, 252`), so in one JVM only the first pool that hits its cap logs within 15 min. Each T therefore runs as its
> own method in its own JVM: `ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.utils.memory.BufferPoolCapProbeTest
> -Dtest.methods=<m> -Dtest.jvm.args=-XX:MaxDirectMemorySize=2g`, m ∈ {`t0`, `t1_5MiB`, `t4MiB`, `t8MiB`, `t16MiB`, `t512MiB`}, in
> that order. Each method's TEST log is copied as `TEST-<m>.log` and step 4's grep is run on it. (b) Step 2: `BufferPool` has no
> `unsafeFree()`; `@After` calls `pool.unsafeReset()`, which calls `globalPool.unsafeFree()` (`BufferPool.java:1628-1635`).
> (c) **Default value added.** T = 512 MiB (536,870,912), the default `min(512, maxHeap/4 MiB)` for any heap of 2 GiB or more
> (`DatabaseDescriptor.java:576-577`) and the shipped yaml's value (`conf/cassandra.yaml:753`). Its demand is 16,384 × 64 KiB = 1 GiB
> (2·T), so the cap is passed; `-XX:MaxDirectMemorySize=2g` because the test JVM's default direct limit equals its 1 GiB heap
> (`build.xml:1153`). Prediction, by B1's formula: pooled 512 MiB, overflow 512 MiB, used 1 GiB, log line present.
> (d) Output lines (one `System.out.println` each): `FCSU T=<T> threshold=<memoryUsageThreshold()> n=<gets> demand=<n·65536>
> size=<sizeInBytes> overflow=<overflowMemoryInBytes> pooled=<size−overflow> used=<usedSizeInBytes> served=<getParentChunk ≠ null>
> unpooled=<n−served>` after the gets; `FCSU-AFTER T=<T> size= overflow= used=` after the puts; `FCSU-ENV` (the pool constants and
> the JVM arguments). (e) In B2f "used = 24 MiB" and "pooled + overflow = 24 MiB" read "= demand" (1 GiB for T = 512 MiB).

**B2f. Predictions.**

| T | pooled | overflow | log line for this pool |
|---|---|---|---|
| 0 | 0 | 24 MiB | absent |
| 1.5 MiB | 1 MiB | 23 MiB | present |
| 4 MiB | 4 MiB | 20 MiB | present |
| 8 MiB | 8 MiB | 16 MiB | present |
| 16 MiB | 16 MiB | 8 MiB | present |

In every row, used = 24 MiB and pooled + overflow = 24 MiB. A small deviation of at most one 128 KiB chunk is allowed if the local pool keeps a partly used chunk, but pooled must never exceed `floor(T/1 MiB)` MiB.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Pooled equals `floor(T/1 MiB)` MiB for each T, and overflow takes the rest | Claim confirmed at unit level |
| Pooled > `floor(T/1 MiB)` MiB for any T | Claim refuted: the check does not cap slabs |
| Pooled flat (the same for every T > 0) | Claim refuted: the threshold has no effect |
| Log line present for T = 0, or absent for T > 0 at the cap | The `:445` branch behaves other than traced |
| Pooled < `floor(T/1 MiB)` MiB while overflow > 0 | The cap binds below T (for example from local-pool fragmentation); note it as a partial result |

> **Amendment U3 (2026-10-27, stage-4 audit; verdict words and order).** Checked in this order; the first that applies is the
> verdict. Ceil(T) means `floor(T/1 MiB)·1 MiB` as B1 states it. (1) **Invalid**: a method did not run (ant exit ≠ 0 or no `FCSU`
> line), `threshold` ≠ T, `used` ≠ demand, or `overflow` = 0 at some T (the demand did not pass the cap). (2) **Refuted — does not
> cap** (row 2): pooled > Ceil(T) at any T. (3) **Refuted — does not cap** (row 3): pooled equal for every T > 0. (4) **Refuted**
> (row 4, the target branch): the message naming `probe-<T>` present at T = 0, or absent at a T > 0 whose overflow > 0; the Effect is
> **caps** if pooled ≤ Ceil(T) everywhere and differs between T values. (5) **Not confirmed** (row 5, "partial result"): pooled <
> Ceil(T) − 128 KiB (beyond B2f's allowance) at some T while overflow > 0; Effect **caps** if pooled ≤ Ceil(T) everywhere and differs
> between T values, else undetermined. (6) **Confirmed — caps** (row 1): every B2f row, with U2(c)'s row, holds within B2f's
> allowance; the direct disallow evidence is overflow > 0 with the message present at every T > 0. (7) Otherwise **Not confirmed —
> undetermined**.

**B2h. Controls.** The T = 16 MiB row is the positive control: the same workload moves pooled memory when the cap is higher. Overflow > 0 in every row shows that demand really exceeded the cap. Using a fresh pool per T avoids carry-over, because chunks are never freed.

### B3. Cluster tier

**B3a. Environment and build.** One Linux node, JDK 11, built from the local clone (`ant jar`). Data, commitlog, hints and saved_caches go on a local disk with at least 20 GB free. In `conf/jvm-server.options` / `jvm11-server.options` set: `-Xms2G -Xmx2G -XX:MaxDirectMemorySize=2G -XX:NativeMemoryTracking=summary`. In `cassandra.yaml` set: `file_cache_enabled: true`, `concurrent_reads: 32`, `disk_access_mode: standard` (so reads go through the rebufferer and chunk cache, not mmap), and `memtable_allocation_type: heap_buffers` (keeps memtable data off the direct-memory accounting).

> **Amendment C1 (2026-10-27, stage-4 audit; host node, paths and cleanup).** One node on 127.0.0.1 from `$W/cassandra-run63` (U1's
> build; `ant build-test` includes the jar and stress). `make-node-conf.sh` (harness folder) writes `$W/node-fcs/conf` from the
> clone's conf with the node's paths under `$W/node-fcs/` and B3a's four yaml lines (`file_cache_enabled: true`, `concurrent_reads:
> 32`, `disk_access_mode: standard`, `memtable_allocation_type: heap_buffers`) plus `file_cache_size` (C2). Heap and options are
> passed at start, not by editing the jvm options files: `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M` (-Xms2G -Xmx2G, G1 from
> `conf/jvm11-server.options:63`) and `JVM_EXTRA_OPTS="-XX:MaxDirectMemorySize=2G -XX:NativeMemoryTracking=summary
> -javaagent:<clone>/build/lib/jars/byteman-4.0.20.jar=script:<harness>/fcs-node.btm"` (a later flag wins over `cassandra-env.sh`'s).
> The node runs as a tracked background process (`nohup bin/cassandra -f … &`; no `setsid` here). Data on the internal SSD (APFS,
> 118 GiB free). B4 on this host: the script wipes `$W/node-fcs` at the end and checks `ps -eo command | grep '[C]assandraDaemon'`, the
> stress JVM and the sampler; the clone's `git status` is left clean.

**B3b. Knobs.** `file_cache_size` set to `48MiB`, `96MiB` and `192MiB` (chunk cache weight 16, 64 and 160 MiB). One extra run uses `file_cache_size: 0MiB`, which disables the chunk cache (`ChunkCache.java:50-53`) and makes every reader buffer overflow. That run exercises the silent branch of `:445`. A restart is needed per value.

**B3c. Workload.** Load: `tools/bin/cassandra-stress write n=8000000 -col size=FIXED\(512\) n=FIXED\(1\) -schema "replication(factor=1)" compression=LZ4Compressor -rate threads=64`. That is about 4 GB of raw data in 64 KiB compressed chunks. Then `nodetool flush` and `nodetool compact`. Read: `tools/bin/cassandra-stress read duration=10m -pop dist=UNIFORM\(1..8000000\) -rate threads=128`. A uniform spread over about 4 GB touches far more than 160 MiB of distinct chunks, so the chunk cache fills to its weight in every run, and the 128 client threads plus 32 read threads keep thread-local chunks busy on top of that. The demand on the chunk-cache pool is at least cache weight + per-thread local chunks (up to 3 × 128 KiB per reading thread), which is more than the knob at 48 and 96 MiB.

> **Amendment C2 (2026-10-27, stage-4 audit; the default value and exact commands).** (a) **Default value added**: a fifth read run with
> `file_cache_size` absent, which is 512 MiB here (`DatabaseDescriptor.java:576-577`; G1 reports maxMemory = 2 GiB at -Xmx2G). Expected
> `Capacity` 536,870,912. Prediction by B3f's own pattern: pooled ≤ 512 MiB and greater than the 192 MiB run's pooled; the log line is
> not required (cache weight 480 MiB). B3g row 1 reads "increases from 48 to 96 to 192 to the default". (b) Commands:
> `tools/bin/cassandra-stress write n=8000000 -col 'size=FIXED(512)' 'n=FIXED(1)' -schema 'replication(factor=1)'
> compression=LZ4Compressor -rate threads=64 -node 127.0.0.1` and, per run, `tools/bin/cassandra-stress read duration=10m -pop
> 'dist=UNIFORM(1..8000000)' -col 'size=FIXED(512)' 'n=FIXED(1)' -rate threads=128 -node 127.0.0.1`. The read gets the write's `-col`
> spec, without which stress reads a different column set than was written. (c) Arithmetic: 8,000,000 × (512 B + key) ≈ 4.2 GB of
> data (plus stress's n/4 warm-up writes to the same key range), against 118 GiB free; five read runs of 10 min plus restarts ≈ 1 h.

**B3d. Observables and instruments.** Sample every 10 s:
- `nodetool sjk mx -mg -b "org.apache.cassandra.metrics:type=BufferPool,scope=chunk-cache,name=Size" -f Value`, the same for `name=OverflowSize` and `name=Capacity`, and the same three for `scope=networking`. Pooled = Size − OverflowSize.
- `nodetool sjk mx -mg -b "java.nio:type=BufferPool,name=direct" -f MemoryUsed` for all direct memory in the JVM.
- `jcmd <pid> VM.native_memory summary` at the end (category "Other" holds direct buffers).
- `grep "Maximum memory usage reached" logs/system.log`.
- What cannot be observed: `memoryAllocated` alone (it is derived from the gauges), and which caller owns an overflow buffer.

> **Amendment C3 (2026-10-27, stage-4 audit; instruments that see the quantity).** (a) `nodetool sjk mx` (one JVM per call; exits 0
> on failure on this host) is replaced by `FcsSampler.java` (harness folder): one JMX connection to 127.0.0.1:7199, a line every 10 s
> with chunk-cache `Size`, `OverflowSize`, `Size` again, `UsedSize`, `Capacity`, the same four for `networking`, and
> `java.nio:type=BufferPool,name=direct` `MemoryUsed`, `Count`, `TotalCapacity`. (b) **Pooled.** `Size` and `OverflowSize` are read one
> after the other and `OverflowSize` moves with every in-flight read, so `Size − OverflowSize` carries a read-to-read error. Pooled is
> therefore judged on **pooled_exact** = `memoryAllocated` printed by the observe-only Byteman rule at `BufferPool.java:460` (`BMFC SLAB
> <pool> <memoryAllocated> <threshold>`, once per slab, after the CAS at `:452` succeeded): the last chunk-cache value of the run, 0 if
> there is none. Because `memoryAllocated` never decreases (A3.7), this is also the plateau. The gauge pooled is reported; at the last
> quiet sample (read finished, the two `Size` reads equal) it must equal pooled_exact, else the run is Invalid (instrument).
> (c) Direct disallow evidence: `BMFC CAP chunk-cache` (first execution of `:447`, the target branch body, reached only when T > 0)
> and `BMFC REFUSE chunk-cache` (first `return null` at `:450`, any T). (d) The message shares one NoSpamLogger statement with the
> networking pool (U2(a)). If the networking pool logged first in the same JVM, an absent chunk-cache line is not evidence against the
> branch, and `BMFC CAP chunk-cache` decides B3g row 5 instead. (e) "OverflowSize > 0 and growing" (B3f 48 MiB; B3g row 5) = chunk-cache
> `OverflowSize` > 0 in at least one sample of the read window. (f) system.log is read from its byte offset at each start. NMT summary
> and `nodetool info` are taken at the end of each run (for information).

> **Runbook-defect fix D1 (2026-10-27, cluster shakedown before run 1; C3(b) wording).** Each `BMFC SLAB` line reads
> `memoryAllocated` when it prints, after its own CAS, so two threads that allocate slabs together can print the same value and print out
> of order (shakedown at 48 MiB: `16777216` twice, six lines, largest `50331648`). pooled_exact is therefore the **largest** chunk-cache
> SLAB value of the run, not the last line. Since every slab's line reads the counter after its own increment and the counter never
> decreases, the largest value equals `memoryAllocated` at the end of the run. The number of SLAB lines is reported as the slab count.
> B3f, B3g and C5 are unchanged.

**B3e. Procedure.** For each knob value:
1. Stop the node, edit the yaml, clear nothing (the data set is reused), and start the node.
2. Check that `Capacity` equals knob × 1048576 and that system.log has "Global buffer pool limit is ... for chunk-cache".
3. Run the read workload for 10 min while sampling.
4. Record the plateau of pooled memory, the final OverflowSize and the direct MemoryUsed, then grep the log.
5. Stop the node.

Load the data once, before the first run, with the default `file_cache_size`.

> **Amendment C4 (2026-10-27, stage-4 audit; exact sequence and stop conditions).** `cluster-run.sh r1 8000000 10m 48MiB 96MiB 192MiB
> default 0MiB`: (1) LOAD with `file_cache_size` absent: start; C2's write; `nodetool flush keyspace1`; `nodetool compact keyspace1
> standard1`; wait until no compaction is listed; tablestats; stop. (2) For each value in that order: conf; start (wait for `UN` and
> `statusbinary` running); check `Capacity` = value × 1,048,576 (536,870,912 for the default) and the `Global buffer pool limit is …
> for chunk-cache` line; start the sampler; C2's read; keep sampling 22 s more (two quiet samples); stop the sampler; NMT summary,
> `nodetool info`, greps of system.log from the offset (`Maximum memory usage reached`) and of the node's stdout (`BMFC`); stop the node
> (`drain`, then kill). (3) ERROR count, cleanup checks, wipe. Stops at once (abort, then cleanup) if a node dies or is not up within
> 600 s, the capacity check fails, a stress command fails, or the node is not idle within 1 h. Shakedown before run 1, not judged:
> `cluster-run.sh shake 400000 60s 48MiB 0MiB`.

**B3f. Predictions.**
- 48 MiB: pooled plateaus at ≤ 48 MiB (expected exactly 48 MiB), OverflowSize > 0 and growing during reads, log line present.
- 96 MiB: pooled ≤ 96 MiB, expected ≥ 64 MiB (the cache weight), log line likely present.
- 192 MiB: pooled ≤ 192 MiB and > 96 MiB.
- 0 MiB: pooled = 0, the overflow gauge goes up and down with in-flight reads, and **no** log line for chunk-cache.
- In every run, direct MemoryUsed ≥ pooled, and it increases with the knob.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Pooled ≤ knob in all runs and increases from 48 to 96 to 192 | Claim confirmed |
| Pooled > knob in any run | Claim refuted |
| Pooled the same in all runs although overflow > 0 at 48 MiB | Claim refuted: the cap does not follow the knob |
| Pooled < knob and OverflowSize = 0 at 48 MiB | Limit never reached; not confirmed, so raise the read threads or the data set |
| Log line present at 0 MiB, or absent at 48 MiB with overflow growing | The target branch is not as traced |
| Direct MemoryUsed much larger than pooled + overflow | Other direct consumers dominate (A4); does not refute the pool claim |

> **Amendment C5 (2026-10-27, stage-4 audit; verdict words and order).** Pooled means C3(b)'s pooled_exact. Checked in this order; the
> first that applies is the verdict. (1) **Invalid**: a node did not start, the capacity check of C4(2) failed, a stress read exited ≠ 0,
> a run with `file_cache_size` > 0 has no `BMFC` line at all (agent not loaded), or the quiet-sample check of C3(b) failed.
> (2) **Refuted — does not cap** (row 2): pooled > knob in any run (for 0 MiB: pooled > 0). (3) **Refuted — does not cap** (row 3):
> pooled equal in the 48, 96 and 192 MiB runs while overflow > 0 at 48 MiB. (4) **Refuted** (row 5, the target branch): at 0 MiB a
> `BMFC CAP chunk-cache` line or a chunk-cache log line; or at 48 MiB with overflow growing, no `BMFC CAP chunk-cache` line, or no
> chunk-cache log line unless C3(d) masks it. The Effect is **caps** if (2) and (3) did not apply. (5) **Not confirmed — undetermined**
> (row 4, limit never reached): at 48 MiB pooled < 48 MiB and chunk-cache `OverflowSize` = 0 in every sample. (6) **Confirmed — caps**
> (row 1): pooled ≤ knob in every run and strictly increasing 48 → 96 → 192 → default, with `BMFC CAP chunk-cache` at 48 MiB as the
> direct disallow evidence. (7) Otherwise **Not confirmed**: Effect **caps** if pooled ≤ knob in every run, else undetermined. Row 6 and
> B3f's direct-memory sentence are reported and are not verdict inputs.

**B3h. Controls.** The 192 MiB run is the positive control: the same workload moves pooled memory above the smaller caps. The networking-pool gauges serve as the unchanged control across the runs. `memtable_allocation_type: heap_buffers` and `disk_access_mode: standard` remove the main confounders. Each run starts with a fresh JVM, so the pool state is not shared.

**B4. Risks and cleanup.** The unit tier uses only a local clone, so `rm -rf /local/tmp/c509` cleans it up. The cluster tier uses about 5 GB of local disk for data, so delete the data directories afterwards. Run `nodetool stopdaemon` (or kill the PID), stop cassandra-stress, and check `pgrep -f CassandraDaemon` and `pgrep -f cassandra-stress` both return nothing. Do not build in, or write into, the shared clone.

## C. Sources read

src/java/org/apache/cassandra/utils/memory/BufferPool.java
src/java/org/apache/cassandra/utils/memory/BufferPools.java
src/java/org/apache/cassandra/metrics/BufferPoolMetrics.java
src/java/org/apache/cassandra/cache/ChunkCache.java
src/java/org/apache/cassandra/config/Config.java
src/java/org/apache/cassandra/config/DatabaseDescriptor.java
conf/cassandra.yaml
conf/jvm-server.options
test/unit/org/apache/cassandra/utils/memory/BufferPoolTest.java
test/conf/logback-test.xml
test/conf/cassandra.yaml
https://docs.oracle.com/en/java/javase/11/docs/api/java.management/java/lang/management/BufferPoolMXBean.html
https://docs.oracle.com/en/java/javase/11/vm/native-memory-tracking.html

## D. Stage-4 feedback

**2026-10-27, stage 4 run 1 on the advisor's Mac (Claude Opus 5.5, claude-opus-5-5[1m]); results in
[`../../stage4-runtime-verification/results/file_cache_size-allocateMoreChunks-memoryUsageThreshold--autonomous.md`](../../stage4-runtime-verification/results/file_cache_size-allocateMoreChunks-memoryUsageThreshold--autonomous.md) (uncommitted).**

- **Version run.** Audit: Ready after amendments U1–U3 and C1–C5 (frozen `10148c88…`). Runbook defect D1 (pooled_exact = the largest SLAB value) was found by the cluster shakedown and fixed before run 1. Both tiers ran at `89b5f6fe…`.
- **Unit: Not confirmed — caps** (B2g row 5, U3(5)).
  - Pooled was 0 / 0 / 0 / 8,388,608 / 16,777,216 / 536,870,912 at T = 0 / 1.5 MiB / 4 MiB / 8 MiB / 16 MiB / 512 MiB. Overflow took the rest of the 24 MiB (1 GiB at 512 MiB), and used = demand.
  - The message was absent at T = 0 and present once at every T > 0 (one JVM per T).
  - B2f missed at 1.5 and 4 MiB (predicted 1 and 4 MiB). Pooled never exceeded B1's ceiling and equals T at every multiple of 8 MiB.
- **Cluster: Confirmed — caps** (B3g row 1, C5(6)).
  - pooled_exact (the observe-only Byteman read of `memoryAllocated`) = 48 / 96 / 192 / 512 MiB exactly at `file_cache_size` 48 / 96 / 192 MiB / default, and 0 at 0 MiB. The chunk cache sat at its weight (knob − 32 MiB).
  - Overflow was > 0 in every sample of every capped run, up to 41 MB.
  - Disallow evidence: `BMFC CAP chunk-cache` and the "Maximum memory usage reached (…) for chunk-cache" message at every knob > 0. At 0 MiB the silent branch ran: a REFUSE line, no CAP line, no message.
  - JVM direct memory rose with the knob (45 / 101 / 152 / 259 / 592 MB at 0 / 48 / 96 / 192 / 512 MiB).
- **Findings for stage 3.**
  - (1) **Claim error:** `MACRO_CHUNK_SIZE = 64 * NORMAL_CHUNK_SIZE` is **8 MiB**, not 1 MiB (`BufferPool.java:128, 385`; the Javadoc at `:384` says 1 MiB, the log prints "chunk of 8.000MiB"). So the ceiling is `floor(T/8 MiB)·8 MiB`. A slab is 64 normal chunks (A3.3 says 8) and serves 128 buffers of 64 KiB (B2c says 16), and a pool with T < 8 MiB never pools anything. This is why the unit tier is Not confirmed. Found from source at the audit, left unamended, and decided by the run.
  - (2) The message at `:447` goes through one static NoSpamLogger statement shared by every pool in the JVM (`BufferPool.java:135`; `NoSpamLogger.java:212, 252`). Only the first pool to hit its cap logs within 15 min, so B1's "exactly when the cap is hit" holds per JVM, not per pool.
  - (3) `BufferPool` has no `unsafeFree()` (B2e step 2); use `unsafeReset()`.
  - (4) B3d's gauge difference `Size − OverflowSize` is not atomic. On the node it exceeded the knob in 106 of 320 samples, by up to 8.55 MB, with no extra slab. It cannot decide "pooled > knob"; an exact read of `memoryAllocated` is needed.
  - (5) Gap: the pool's own direct bytes are seen only through its counter; the JVM direct total includes about 45 MB of other consumers.
- **No section amended by the result.**
