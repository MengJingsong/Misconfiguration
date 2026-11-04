# row_cache_size — verification solution  <!-- file: cases/row_cache_size-create-serialized_size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/cache/SerializingCache.java:71` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI (version not exposed to the agent), 2026-10-25 |
| Estimate | `positive` (with a stated overshoot margin): when `SerializingCacheProvider` is the row cache class, off-heap row-cache bytes track `row_cache_size`, because the default weigher charges each entry its serialized size and Caffeine evicts above `maximumWeight`. The cap is approximate (it ignores malloc and map overhead and in-flight entries). |
| Ground | — |

Note on the entry pointer: line 71 is only the 2 GiB guard inside the default weigher lambda (`SerializingCache.java:69-75`). It is not the enforcement point. The cap is `maximumWeight(capacity)` at `SerializingCache.java:52`, fed from `row_cache_size` by `SerializingCacheProvider.java:33`. The guard is also effectively dead code, because `serialize()` already rejects sizes above `Integer.MAX_VALUE` at `SerializingCache.java:94-95`, before any entry reaches the weigher.

## A. Constraint trace

**A1. The constraint.**
- Name: `row_cache_size` (yaml), exposed as `DatabaseDescriptor.getRowCacheSizeInMiB()`. Kind: configuration entry, also changeable at runtime through JMX.
- Declared at `src/java/org/apache/cassandra/config/Config.java:473-474`: `DataStorageSpec.LongMebibytesBound row_cache_size = new ...("0MiB")`. It replaces the old name `row_cache_size_in_mb`.
- Unit: MiB in config. It is converted to bytes at `SerializingCacheProvider.java:33` (`getRowCacheSizeInMiB() * 1024 * 1024`, a `long`).
- Default is `0MiB`, which disables the row cache (`conf/cassandra.yaml:564`; in `CacheService.java:146-147` size 0 selects `NopCacheProvider`). Nothing is derived.
- Setting:
  - yaml key `row_cache_size`.
  - JMX `CacheService.setRowCacheCapacityInMB` (`CacheService.java:327-333`, which calls `rowCache.setCapacity(capacity*1024*1024)`), or `nodetool setcachecapacity <key> <row> <counter>` (`tools/nodetool/SetCacheCapacity.java`, `NodeProbe.java:1092`).
  - Changing the yaml value needs a restart. The JMX route does not, and it rejects negative values.
- Provider selection: `row_cache_class_name` (`Config.java:472`). The default is `OHCProvider`, so `SerializingCache` is on the path only if the node sets `row_cache_class_name: org.apache.cassandra.cache.SerializingCacheProvider` (documented as the legacy implementation, `conf/cassandra.yaml:547-553`). This is a restart-time setting.
- A table is only cached if its CQL option `caching = {'rows_per_partition': 'ALL'|N}` is set and capacity > 0 (`ColumnFamilyStore.java:3259-3262`).

**A2. What it caps.**
- Resource: off-heap native memory. Each cached partition is a `RefCountedMemory`, a `Memory` subclass whose constructor calls `MemoryUtil.allocate` (`Memory.java:64-65`, `MemoryUtil.java:81-84`, native malloc).
- Compared quantity: Caffeine's total weight, the sum over entries of `value.size()`. That is the serialized byte length of the partition, clamped to `int` by the weigher (`SerializingCache.java:69-75`). It is compared with `maximumWeight = row_cache_size` bytes.
- It is read back through `weightedSize()` (`SerializingCache.java:139-142`) and `capacity()` (`:119-122`), and surfaced by the metrics `org.apache.cassandra.metrics:type=Cache,scope=RowCache,name=Size|Capacity|Entries` (`CacheMetrics.java:60-63`).

**A3. Mechanism.**
1. `CacheService.initRowCache` (`CacheService.java:141-169`) instantiates the provider. `SerializingCacheProvider.create` (`:31-34`) calls `SerializingCache.create(bytes, new RowCacheSerializer())`.
2. `create(long, ISerializer)` (`SerializingCache.java:67-76`) builds the weigher. The weigher takes `value.size()` (the allocated `Memory` size) and throws `IllegalArgumentException` if it exceeds `Integer.MAX_VALUE` (line 71-72). Otherwise it returns `(int) size`.
3. The constructor (`:46-60`) builds Caffeine with `.weigher(weigher).maximumWeight(capacity).executor(ImmediateExecutor.INSTANCE)`. The immediate executor means eviction maintenance runs on the calling thread, not asynchronously.
4. `put` (`:166-185`; *amended 2026-10-25, was `:107-126`*) first serializes into a freshly malloc'd `RefCountedMemory` (`serialize`, `:91-117`) and then inserts it. So the allocation happens before Caffeine can evict.
5. When the total weight exceeds the maximum, Caffeine evicts. The removal listener (`:54-58`) calls `mem.unreference()` only if `cause.wasEvicted()`, which drops the refcount to 0 and frees the native memory (`RefCountedMemory.java`, `unreference`). Explicit removes and replaces are handled by hand in `put`/`putIfAbsent`/`replace`/`remove` (`:183-184`, `:205-206`, `:244-246`, `:251-257`; *amended 2026-10-25, were `:121-125`, `:177-183`, `:162-168`*). Note (found at the audit, 2026-10-25): `clear()` (`:144-147`) calls `cache.invalidateAll()`, whose removal cause is EXPLICIT, so `cause.wasEvicted()` is false and the listener does not `unreference()`: the native blocks of every entry present at a `clear()` (nodetool `invalidaterowcache`) appear not to be freed. This does not touch B1 (it is not a way past the cap while the cache is in use) and is tested only as a side finding, B2i.6.
6. Outcomes at the limit:
   - Eviction of cold entries (Caffeine W-TinyLFU), so `weightedSize()` stays at or below the capacity.
   - An entry whose own weight is larger than the maximum is evicted straight away.
   - If malloc fails with `OutOfMemoryError`, `serialize` returns null and the put is silently dropped (`:102-105`, `:169-170`; *amended 2026-10-25, was `:136-138`*).
7. `setCapacity` (`:124-127`, unchanged) calls `setMaximum`, which shrinks the cache on the fly (evicting) when lowered.

Overshoot and bypass paths:
- Counted bytes exclude malloc bookkeeping, `RowCacheKey` objects and the Caffeine node (all on heap and not in the weight). Real native usage is therefore a bit above `weightedSize()`. Heap overhead is per entry and scales with the entry count, not with the capacity.
- In-flight memory: `serialize` allocates before insertion. `putIfAbsent` (`:187-207`; *amended 2026-10-25, was `:128-148`*) allocates and then frees if the key already existed, and `replace` allocates the new value before swapping. Under N concurrent writers the transient overshoot is up to about N times the entry size.
- Weigher given with `int` truncation: the guard at line 71 means no single entry above 2 GiB-1 can be cached.
- `get` deserializes into heap objects (`:78-89`). That heap use is outside the cap.
- The three-arg `create(long, Weigher, ISerializer)` lets callers supply a different weigher (used in `CacheProviderTest` with `singletonWeigher`, i.e. weight 1 per entry, so the "capacity" there counts entries rather than bytes). The production provider uses the byte weigher.

**A4. Other consumers.**
- Off-heap row cache competes with memtables (when `memtable_allocation_type` is off-heap, `offheap_buffers` or `offheap_objects`), the chunk cache, the buffer pool, the key cache's index data (on heap), compression metadata, bloom filters (off-heap) and the OS page cache.
- The default `OHCProvider` has its own cap (OHC, `OHCProvider.java`), unrelated to this class.
- Deserialized partitions on the heap during reads, and `RowCacheKey`/Caffeine nodes on the heap.

**A5. Evidence beyond the source.** In-tree only:
- `test/unit/org/apache/cassandra/cache/CacheProviderTest.java:145-153` (`testSerializingCache` with `CAPACITY = 4` and a singleton weigher; asserts `cache.size() == CAPACITY`).
- `conf/cassandra.yaml:547-575`, whose comment says the OHC implementation "requires some additional off-heap memory" beyond `row_cache_size`.
No external links were relied on.

## B. Verification solution

**B1. Claim under test.** With `SerializingCacheProvider` selected, the bytes held by the row cache never settle above `row_cache_size` (plus a small bounded overshoot): `weightedSize()` is at most the capacity once writers are quiescent, and the real native (off-heap) memory of the process grows with the capacity until the cache fills and then stays flat at about the capacity, however much more data is read. If native memory instead keeps growing past the cap, or does not move when the cap is raised, the claim is wrong.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 11, Ant. Copy the tree to local disk (`rsync -a ~/cassandra-5.0.9/ /local/scratch/c509/`) and never build in the shared tree.
- `cd /local/scratch/c509 && ant jar` (or `ant build-test`).
- Test source: a new JUnit class `test/unit/org/apache/cassandra/cache/SerializingCacheCapTest.java` in the local copy, run with `ant testsome -Dtest.name=org.apache.cassandra.cache.SerializingCacheCapTest`. A plain `main` using the built classpath (`build/classes/main` + `lib/*.jar` + `build/lib/jars/*.jar`) also works.
- JVM options: `-Xmx512m -Xms512m -XX:+AlwaysPreTouch` (a small fixed heap makes heap and off-heap separable). Add `-Dcassandra.config=file:///local/scratch/c509/test/conf/cassandra.yaml`.

**B2b. Knobs.** The `weightedCapacity` argument of `SerializingCache.create(long, ISerializer)` is the unit-tier equivalent of `row_cache_size` (the provider only multiplies MiB by 1048576). Values: 16 MiB, 64 MiB, 256 MiB, plus a runtime `setCapacity(32 MiB)` after filling the 64 MiB cache. The entry size is a second knob: 4 KiB, 256 KiB and 4 MiB values. Set in the test code.

**B2c. Workload.**
- Use a test `ISerializer<byte[]>` that writes the length and then the bytes, with `serializedSize = 4 + len`. Use a `byte[]` value type, which needs no schema and no node.
- For each capacity C and entry size S, `put` N = ceil(4*C/S) distinct keys (4x the capacity, so eviction is forced). For example C = 64 MiB and S = 256 KiB gives N = 1024 (about 256 MiB offered).
- Then `get` all keys once, and run a concurrent phase of 16 threads each putting random keys for 20 s.
- Arithmetic: offered bytes = N*(S+4) = 4C > C, so the limit is reached after about C/(S+4) puts.

**B2d. Observables and instruments.**
- `cache.weightedSize()`, `cache.capacity()`, `cache.size()` (in-process, read after every 64 puts and after joining the threads).
- Native memory: the process RSS from `/proc/self/status` (`VmRSS`), sampled before and after each phase. The heap is held fixed and a `System.gc()` is run first, so the RSS growth is dominated by malloc'd cache bytes. The pages are touched by the serializer writing. Note the allocator may retain freed memory, so also read `VmRSS` after `malloc_trim` is not available from Java; instead compare the peak against the cap and use the peak-over-baseline.
- Not directly observable: exact malloc overhead per block (estimate about 16 bytes per allocation).

**B2e. Procedure.**
1. Build as in B2a.
2. For each (C, S): create the cache, record the baseline RSS, `put` N keys, record `weightedSize`, `size`, RSS delta.
3. Run `get` on all keys and record the hit count (expect `size()` hits at most).
4. Run the 16-thread phase and record the max `weightedSize` seen by a sampler thread every 10 ms, the final value and the RSS peak.
5. Call `setCapacity(C/2)`, record `weightedSize` and the RSS delta.
6. Repeat with a second cache built by the 3-arg `create` with `Weigher.singletonWeigher()` and capacity 4 as the control.

**B2f. Predictions.** (stated before any run)
- For each (C, S): final `weightedSize <= C`, and `weightedSize >= C - S - 4` (cache full, within one entry). `size() ~ C/(S+4)`.
- RSS delta is within `[0.9 C, C + 64 MiB]` for C = 64 MiB and 256 MiB, and for C = 16 MiB within `[0.8 C, C + 48 MiB]` (the JVM and allocator noise dominates at small C).
- Concurrent phase: the sampled max `weightedSize` is at most C. The RSS peak exceeds C by at most about 16 * S (one in-flight entry per thread) plus malloc slack.
- After `setCapacity(C/2)`: `weightedSize <= C/2` immediately (eviction is synchronous through the immediate executor).
- Offering one entry of 2^31 bytes or more must not be cacheable (an `IllegalArgumentException` from `serialize`, line 94-95, before the weigher). This is checked with a synthetic `serializedSize` override, without allocating.
- Control: the singleton-weigher cache holds exactly 4 entries whatever S is.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `weightedSize <= C` after quiescence and RSS delta tracks C across the three capacities | Claim holds: the weigher cap binds the native bytes |
| `weightedSize > C + S` at rest | Claim wrong: eviction does not enforce the weight |
| `weightedSize <= C` but RSS delta keeps growing with N (more than 1.5 C over baseline at C = 64 MiB) | Claim wrong for real memory: freed or evicted blocks are leaking (refcount not reaching zero), or the weigher under-counts |
| RSS delta flat across C values | Not confirmed: the instrument is too coarse, or the allocator retained memory. Repeat with larger S and C |
| Concurrent peak much above C + 16*S | Overshoot is larger than the in-flight model predicts; record it as a finding |
| Singleton-weigher control holds more or fewer than 4 entries | The test harness is faulty; discard the run |
| `clear()` leaves `weightedSize()` 0 but the second fill's `RssAnon` delta is at least 1.7 C (side arm, B2i.6) | Side finding: `clear()` leaks the native blocks (accounting bypass); B1 is judged by the other rows |
| Second fill's `RssAnon` delta is at most C + 64 MiB (side arm) | No leak on `clear()` |

**B2h. Controls.** Singleton-weigher cache (entries counted, bytes ignored). A run at C = 0 where nothing should stay resident. A run with the heap deliberately unchanged (a plain `byte[]` list of the same size is not allocated), so heap is not confused with native memory. Repeat each point three times.

**B2i. Audit amendments, 2026-10-25 (stage 4, before any reading; none changes B1, B2f or B2g except where it says so).**
1. Harness form: a plain `main` class (`SerializingCacheCapTest`) compiled against `build/classes/main` and run with `java -Xmx512m -Xms512m -XX:+AlwaysPreTouch` plus the options of `conf/jvm11-clients.options`; no Ant fork (`ant testsome` forks a 1 GiB JVM and would defeat the fixed heap). `-Dcassandra.config` is not needed because the class touches no `DatabaseDescriptor` call.
2. Native-memory reading is `RssAnon` from `/proc/self/status` (not `VmRSS`; `VmRSS` also counts file-backed pages). `VmRSS` is recorded beside it. The B2f ranges for the RSS delta apply to `RssAnon`.
3. B2f "malloc slack" is fixed at 64 MiB: the concurrent-phase peak `RssAnon` delta is at most C + 16 x (S + 4) + 64 MiB.
4. Exact points: C in {16, 64, 256} MiB crossed with S in {4 KiB, 256 KiB, 4 MiB} (nine points), each three times; keys are `Integer` 0..N-1 with N = ceil(4C/S); values are `byte[S]`; the serializer writes `S` bytes after a 4-byte length so `serializedSize = S + 4`. The sampler reads `weightedSize()` every 10 ms in the concurrent phase.
5. A heap-only control is not run separately: the heap is pre-touched, so a growing `RssAnon` cannot come from touching heap pages; the `System.gc()` before each baseline is logged.
6. Side arm (new row, B2g "clear"): at C = 64 MiB and S = 256 KiB, fill to the cap, call `clear()`, record `weightedSize()` and `RssAnon`, and fill again. Prediction: `weightedSize() == 0` and `size() == 0` after `clear()`. If the blocks are freed, the second fill peaks near C over the baseline (at most C + 64 MiB); if `clear()` leaks them (EXPLICIT removal does not call `unreference()`), the second peak is near 2 C (at least 1.7 C). This arm is a side finding on a bypass of the accounting by `clear()` and does not decide the verdict on B1.
8. Fresh JVM per point: every (C, S, rep) point, every control group and every side-arm repetition runs in its own JVM (`-Xmx512m -Xms512m -XX:+AlwaysPreTouch`, baseline taken after two `System.gc()` calls). Reason (found in a scaled instrument check, not a reading): memory freed by eviction stays in glibc's arenas and a later point reuses it, so a shared JVM would hide the cache's growth and make the `RssAnon` delta depend on point order. The control group (singleton weigher, C = 0, the 2^31 entry) runs once per rep in its own JVM. A shakedown at `scale` 16 (N and phase length divided) ran the whole sequence; its output is not used.
7. Added B2g row: "`clear()` leaves `weightedSize()` 0 but the second fill's `RssAnon` delta is at least 1.7 C: the native blocks of cleared entries leak (accounting bypass, side finding; B1 itself is judged by the other rows)"; and "second-fill delta at most C + 64 MiB: no leak on `clear()`".

### B3. Cluster tier

**B3a. Environment and build.**
- One node (a second node optional) on a Linux host. JDK 11, Ant. Build from a local copy: `rsync -a ~/cassandra-5.0.9/ /local/scratch/c509/ && cd /local/scratch/c509 && ant jar`. Start it from `bin/cassandra -f` in the local copy.
- `data_file_directories`, `commitlog_directory`, `hints_directory` and `saved_caches_directory` all on local disk (for example `/local/scratch/node1/*`, at least 20 GiB free).
- JVM: `-Xms2G -Xmx2G` (`conf/jvm-server.options`), `memtable_allocation_type: heap_buffers` (so memtables do not use native memory), `file_cache_size: 64MiB`, `key_cache_size: 0MiB`, `counter_cache_size: 0MiB`, `commitlog_sync: periodic`, `num_tokens: 1`.
- Row cache config: `row_cache_class_name: org.apache.cassandra.cache.SerializingCacheProvider`, `row_cache_size: <knob>`, `row_cache_save_period: 0s`.

**B3b. Knobs.** `row_cache_size` at 0MiB (control; row cache off), 128MiB, 512MiB and 1024MiB, each set in the yaml followed by a restart. Plus a live change with `nodetool setcachecapacity 0 256 0` and then `0 64 0`. Reason: 128 MiB is well below the data volume, 1024 MiB is above 2x the working set of the second workload, and 0 is the baseline. A second knob is the table option `rows_per_partition`, `ALL` versus `NONE`.

**B3c. Workload.**
- Schema: `CREATE KEYSPACE ks WITH replication={'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE ks.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck)) WITH caching = {'keys':'NONE','rows_per_partition':'ALL'};`
- Load: 8192 partitions, each with 16 rows of a 4 KiB blob. Each partition is about 64 KiB serialized, so about 512 MiB of cacheable data. Use `cassandra-stress` or a small driver script (`cqlsh COPY` is too slow) at CL ONE.
- Read: scan `SELECT * FROM ks.t WHERE pk = ?` over all 8192 partitions twice (the first pass populates, the second pass hits). A third pass with random keys for 10 minutes, 32 client threads.
- Arithmetic: 8192 * 64 KiB = 512 MiB offered, which exceeds the 128 MiB cap (4x) and is at or below the 512 MiB cap only by the serialization overhead. So 128 MiB must evict, 512 MiB is borderline, 1024 MiB holds everything. To get a clean over-cap case at 512 MiB, load 16384 partitions (1 GiB offered).
- Duration: about 15 min per setting.

**B3d. Observables and instruments.**
- JMX metrics `org.apache.cassandra.metrics:type=Cache,scope=RowCache,name=Size`, `Capacity`, `Entries`, `HitRate` (read with `nodetool info` "Row Cache" line, or `jconsole`/`jmxterm` every 10 s).
- Real memory: `/proc/<pid>/status` `VmRSS` and `RssAnon` every 10 s, `pmap -x <pid>` at the end of each phase, and `jcmd <pid> GC.heap_info` for the Java heap and `jcmd <pid> VM.native_memory summary` (needs `-XX:NativeMemoryTracking=summary`) to separate JVM-tracked memory. The cache blocks are malloc'd outside NMT, so (RSS - heap committed - NMT total) isolates them. Run `nodetool flush` first and `jcmd GC.run` before each reading.
- Not directly observable: per-cache native bytes by the OS, so the estimate is by difference. Page cache is excluded (`RssAnon`, not `RssFile`).

**B3e. Procedure.**
1. Prepare local dirs and the yaml with `row_cache_size: 0MiB` (control). Start the node. Create the schema. Load the data, then `nodetool flush`.
2. Record the baseline (`RssAnon`, heap, NMT). Run the two scan passes and the random phase, sampling as in B3d. Record the final values. Stop the node with `nodetool drain` and then kill the process, and check with `pgrep -f CassandraDaemon`.
3. Repeat from step 1 (data kept) for 128MiB, 512MiB and 1024MiB. For each, restart so the cache starts cold.
4. On the 1024MiB run, after the cache is full, run `nodetool setcachecapacity 0 256 0` and re-sample, then `0 64 0`, then `0 1024 0` and re-run the random phase.
5. Repeat the 128MiB point with `rows_per_partition = 'NONE'` (`ALTER TABLE`) as the second control.
6. Delete `/local/scratch/node1` and `/local/scratch/c509` at the end.

**B3f. Predictions.** (stated before any run)
- The `Size` gauge never exceeds `Capacity` once the load is quiescent: `Size <= 128 MiB`, `<= 512 MiB`, `<= 1024 MiB`. `Entries` is about `Size / 64 KiB` (at most about 2000, 8000 and 16384 respectively).
- With 0MiB: `Size = Capacity = 0`, no entries, and `RssAnon` growth after the reads is small (under 100 MiB, the JVM warm-up).
- `RssAnon - (heap committed + NMT total)` at the end of the random phase minus its 0MiB baseline lies in `[0.9 * Size, 1.3 * Size + 64 MiB]`. In particular at 128MiB it is below about 230 MiB, and it is far less than the 1 GiB offered, so the usage is held by the cap and not by the data volume.
- After `setcachecapacity 0 256 0` and `0 64 0` the `Size` falls to at most 256 MiB and then 64 MiB immediately, and the native-memory estimate falls accordingly (it may lag if malloc does not return pages to the OS; the `Size` gauge is authoritative, so compare with a second `pmap`).
- With `rows_per_partition = 'NONE'`: `Size` stays 0 whatever the capacity.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| `Size <= Capacity` at rest and the native-memory estimate scales with the capacity across 128/512/1024 | Claim holds for the real resource |
| Native estimate above `1.3 * Capacity + 64 MiB` at the 128MiB point, or growing during the random phase with `Size` flat | Claim wrong: native bytes exceed what the weigher counts (leak, fragmentation or unaccounted overhead) |
| `Size > Capacity` after quiescence | Claim wrong at the metric level: the eviction does not bind |
| Native estimate does not rise between 128 and 1024 although `Size` does | Inconclusive: instrument failure (allocator not returning memory, or the NMT arithmetic is wrong). Redo with `pmap` and a clean restart |
| 0MiB or `rows_per_partition NONE` run has `Entries > 0` | Setup error (wrong provider or table option); discard |
| `Size` does not move on the live `setcachecapacity` | JMX path not wired to this cache (check which provider is active in the startup log "Initializing row cache with capacity of ...") |

**B3h. Controls.** The 0MiB run and the `rows_per_partition NONE` run give the no-cache baseline under the same workload. Checking the log line `Initializing row cache` and the class in `nodetool info` rules out the default OHC provider being used by mistake. `key_cache_size`, `counter_cache_size` and the chunk cache are fixed small so they do not move the memory reading. The heap is fixed at 2 GiB with heap-allocated memtables. Every point is run twice.

**B3i. Audit amendments, 2026-10-25 (stage 4, before any reading; none changes B1, B3f or B3g except where it says so).**
1. Data volume: B3c loads 8192 partitions (about 520 MiB serialized), which is below the 1024 MiB cap and about equal to the 512 MiB cap, so those two values would never reach their limit. The load is **32768 partitions** x 16 rows x 4 KiB (about 2.1 GiB serialized, about 2.2 GiB on disk), which exceeds all three caps (128, 512, 1024 MiB). B3f's `Entries` upper bounds (about 2000, 8000 and 16384) are unchanged; they are bounds, not the full set.
2. The random phase is 180 s with 128 reads in flight (not 10 min x 32 threads); the two scan passes read all 32768 partitions with 128 reads in flight. The client is a Python driver script (bundled `cassandra-driver` 3.29.0), protocol 4, `SELECT * FROM ks.t WHERE pk = ?` prepared, consistency ONE.
3. `Size`, `Capacity` and `Entries` are read over JMX (`org.apache.cassandra.metrics:type=Cache,scope=RowCache`, attribute `Value`) every 5 s by a small Java client in the harness, not by `nodetool info` (which rounds). `RssAnon` is read from `/proc/<pid>/status` every 5 s; `jcmd <pid> VM.native_memory summary` and `jcmd <pid> GC.heap_info` are read at the end of each scan pass and of the random phase. The node runs with `-XX:NativeMemoryTracking=summary` added to its `jvm11-server.options`. The native-memory estimate of B3f is replaced (instrument check with the cache off, not a reading of the claim): NMT "committed" is not resident memory. With the row cache at 0 MiB the NMT total rose by about 1 GiB (category `Other`: pooled direct buffers reserved but untouched) while `RssAnon` did not, so `RssAnon - NMT total` is meaningless as an estimate. The estimate is **`RssAnon(arm, checkpoint) - RssAnon(c0, same checkpoint)`**: the heap is fully pre-touched in every arm (`AlwaysPreTouch`, same `-Xms2G -Xmx2G`), so the difference is non-heap anonymous memory beyond what the same node holds with the cache off. The B3f band `[0.9 Size, 1.3 Size + 64 MiB]` applies to this difference taken at the end of the random phase (checkpoint `rand`), with `Size` read at the same checkpoint. The within-arm growth `RssAnon(rand) - RssAnon(idle)` and the NMT total and `Other` figures are recorded as diagnostics only. The cache blocks are `Native.malloc` (JNA, libc; `MemoryUtil.java:81-84`), not `Unsafe.allocateMemory`, so NMT does not count them (confirmed: `RefCountedMemory` instances equal `Entries` in `GC.class_histogram` while NMT `Other` is unchanged by them). The provider is confirmed in each cache-on arm by the `RefCountedMemory` count in `GC.class_histogram`, which exists only under `SerializingCacheProvider`.
4. Arms and order: one node lifetime per row-cache value, each with a cold cache and the same data on local disk: `c0` (0MiB, control), `c128`, `c512`, `c1024` (with the live changes of B3e step 4 after the random phase), `n128` (128MiB with `rows_per_partition = 'NONE'`, set with `ALTER TABLE` before the node restarts), and `c128b` (a repeat of `c128` last, for run-to-run spread). B3h's "every point twice" is reduced to this one repeat to bound the run time.
5. Ports and paths (shared node): loopback address 127.0.9.1 for `listen_address`, `rpc_address` and the seed; `storage_port` 7390, `ssl_storage_port` 7391, `native_transport_port` 9390, JMX 7390+9 = 7399; data under `~/s4-rc/node`, source copy `~/s4-rc/cassandra` (replaces `/local/scratch/...`). `-Xms2G -Xmx2G` as in B3a (via `MAX_HEAP_SIZE`/`HEAP_NEWSIZE=512M`); `-XX:+AlwaysPreTouch` is already in `jvm-server.options`, so the heap is fully resident from the start and the `RssAnon` delta excludes heap touching.
6. Live changes (B3e step 4): `nodetool -p 7399 setcachecapacity 0 256 0`, then `0 64 0`, then `0 1024 0`, each followed by a 30 s settle and a `Size` / `RssAnon` / NMT reading, then 60 s of the random phase after the last one.

**B4. Risks and cleanup.**
- Disk: unit tier writes nothing. Cluster tier data is about 1.5 GiB plus commit log (set `commitlog_total_space: 1GiB`), all on local disk with at least 20 GiB free. No shared storage and no source tree in the shared location is touched.
- Memory: keep the node at `-Xmx2G` plus at most about 1.1 GiB of native cache. Do not run on a host with less than 6 GiB free.
- Processes: stop Cassandra with `nodetool drain` and then kill, stop any stress or driver process, then check `pgrep -fa 'CassandraDaemon|cassandra-stress|SerializingCacheCapTest'` returns nothing.
- Cleanup: remove `/local/scratch/node1` and `/local/scratch/c509`.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cache/SerializingCache.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cache/SerializingCacheProvider.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cache/RefCountedMemory.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cache/OHCProvider.java (grep only)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cache/InstrumentingCache.java (grep only)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/service/CacheService.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java (grep)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java (grep)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/Memory.java (grep)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemoryUtil.java (grep)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/CacheMetrics.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java (grep)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/schema/CachingParams.java (grep)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/tools/nodetool/SetCacheCapacity.java (grep)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/tools/NodeProbe.java (grep)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/ImmediateExecutor.java (grep)
- /users/jason92/cassandra-5.0.9/test/unit/org/apache/cassandra/cache/CacheProviderTest.java
- /users/jason92/cassandra-5.0.9/conf/cassandra.yaml
- /users/jason92/cassandra-5.0.9/conf/jvm-server.options (grep)

## D. Stage-4 feedback

Stage 4, 2026-10-25, tag `rc`, node `pc07`. Results: [`results/row_cache_size-create-serialized_size--autonomous.md`](../../stage4-runtime-verification/results/row_cache_size-create-serialized_size--autonomous.md). Frozen version: sha256 `23f4b160fd23a0326d41136393916e0b652fac8d54c9023483e6c8c21e1bb9cd` (this file before D was filled; case file untracked, base commit `627b1ec`).

- **Verdict: Confirmed at both tiers; effect on the constraint: caps. Outcome class: true positive** (estimate `positive`, effect `caps`). B1 held: `weightedSize()` never exceeded the capacity (27 unit points, 49 JMX samples per cluster arm), the cache sat at the capacity with 4x to 16x more data offered, and the process's anonymous memory rose with the capacity (unit: C plus a constant 22-69 MiB; cluster: 129, 448 and 1003 MiB over a cache-off node at 128, 512 and 1024 MiB, flat during further reads).
- **Amendments before the freeze (2026-10-25):** A3 line ranges of `put`, `putIfAbsent`, `replace`, `remove` corrected; B2i (plain `main`, `RssAnon`, fixed slack, exact points, `clear()` side arm and its two B2g rows, one JVM per point) and B3i (32,768 partitions, 180 s random phase, JMX reading, estimate = `RssAnon` difference to the 0 MiB arm instead of the NMT subtraction, arms, ports).
- **Findings carried back (the Estimate line is unchanged):**
  1. The B3d/B3f native-memory estimate `RssAnon - (heap + NMT)` does not work: NMT "committed" is not resident (it rose 1 GiB with the cache off) and the heap was counted twice. The cache blocks are `Native.malloc` (JNA), outside NMT, as A2 says.
  2. Cap is soft under concurrent writers: with 16 threads putting at full speed the entries present reached 1.5 to 3.3 x C transiently (post-hoc diagnostic, C = 64 MiB), because Caffeine's eviction runs behind the writes; the `RssAnon` peak reached 2.8 to 31 x C, mostly freed memory kept by glibc (1.0 to 2.0 x C after `malloc_trim(0)`). The B2f in-flight model (16 x S) was too small.
  3. Confirmed bypass of the accounting, `clear()` (`SerializingCache.java:144-147`): `invalidateAll()` removes with cause EXPLICIT, `wasEvicted()` is false, no `unreference()`; after `clear()` `weightedSize() == 0` but a second fill peaked at 2.36 to 2.48 x C (3 reps). `nodetool invalidaterowcache` on this provider would leak up to `row_cache_size` bytes each call.
  4. Lowering the capacity (`setcachecapacity`) evicts at once (`Size` 1024 -> 64 MiB) but `RssAnon` does not fall until the allocator is trimmed (853 MiB returned by `malloc_trim(0)`), so the process footprint can stay at the old cap.
  5. Prediction misses recorded in the results file: the cache-off node's `RssAnon` grew 200 MiB over the read phases (predicted under 100); `est` was below its lower band at 512 MiB (447.8 against 460.8) and at a repeat of 128 MiB (104.2 against 115.2); two fill-phase deltas exceeded the B2f range by 1.5 and 5.3 MiB.
- **Runbook defect:** after the `rows_per_partition NONE` arm, the next node lifetime re-prepared the client's `SELECT` against the persisted NONE schema and a later `ALTER ... ALL` did not reach that statement, so the cache stayed empty; the arm was rerun (results §3, defect 5).
