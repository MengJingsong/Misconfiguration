# key_cache_size / counter_cache_size (Caffeine maximumWeight) — verification solution  <!-- file: cases/key_cache_size-create-size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/cache/CaffeineCache.java:65` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude (Sonnet 5.5), Claude Code CLI, 2026-10-25 |
| Estimate | `positive` for the cap that this line is part of (`key_cache_size`, and likewise `counter_cache_size`): the Caffeine `maximumWeight` bounds the sum of `unsharedHeapSize()` of the entries, which tracks on-heap use up to a per-entry overhead factor. The line-65 check itself (the 2 GiB per-entry guard) is not a usable cap and is practically unreachable (see Ground). |
| Ground | Only for line 65 as a stand-alone limit: it bounds one entry's weight, not the total, and key/counter cache entries are far below 2 GiB (key <= 64 KiB, value small or a bounded index structure). The total is bounded by `maximumWeight`, not by this line. |

## A. Constraint trace

**A1. The constraint.** Two constraints meet at the target.
(a) The per-entry weight limit `Integer.MAX_VALUE` (constant, `CaffeineCache.java:65-67`, because Caffeine's `Weigher` returns `int`; unit bytes; not settable).
(b) The cache capacity `weightedCapacity` passed to `Caffeine.newBuilder().maximumWeight(...)` (`CaffeineCache.java:53-57`). It is supplied by two callers of the one-arg `create(long)` (`CaffeineCache.java:61-70`), the only users of this weigher in `src/java`:
 - key cache: `CacheService.initKeyCache`, `keyCacheInMemoryCapacity = getKeyCacheSizeInMiB() * 1024 * 1024` (`CacheService.java:123,128`);
 - counter cache: `CacheService.initCounterCache`, `capacity = getCounterCacheSizeInMiB() * 1024 * 1024` (`CacheService.java:176,179`).
 The configuration entries are `key_cache_size` (`Config.java:467-468`, `conf/cassandra.yaml:525`) and `counter_cache_size` (`Config.java:479-480`, `conf/cassandra.yaml:595`), unit MiB.
 Defaults (empty = "auto"): key cache `min(max(1, 5% of Runtime.totalMemory() in MiB), 100)` (`DatabaseDescriptor.java:814-817`); counter cache `min(max(1, 2.5% of totalMemory in MiB), 50)` (`DatabaseDescriptor.java:834-836`). Note it uses `totalMemory()` (currently committed heap at startup), not `maxMemory()`. Value `0` disables the cache (yaml comments). Negative is rejected (`DatabaseDescriptor.java:819-820, 838-839`).
 Settable by yaml (restart) and at runtime by JMX `CacheService.setKeyCacheCapacityInMB` / `setCounterCacheCapacityInMB` (`CacheService.java:336-350`), exposed as `nodetool setcachecapacity` (`tools/nodetool/SetCacheCapacity.java`). Runtime change calls `policy.setMaximum` (`CaffeineCache.java:77-80`). The row cache does not use this class by default (it uses `OHCProvider`/`NopCacheProvider`, `CacheService.java:143-157`).
 The rest of this case takes `key_cache_size` as the primary constraint; `counter_cache_size` is the same mechanism and is a variation.

**A2. What it caps.** On-heap memory (Caffeine is an on-heap map; class doc `CaffeineCache.java:31-33`). The quantity compared against the limit is the cache's total weight, `policy.weightedSize()` (`CaffeineCache.java:92-95`), the sum over entries of `(int)(key.unsharedHeapSize() + value.unsharedHeapSize())` (`CaffeineCache.java:63-69`), exposed as metric `Cache.<KeyCache|CounterCache>.Size` (`metrics/CacheMetrics.java:70`) and `Capacity` (`:69`). Both are estimates computed by `ObjectSizes`, not measured heap.

**A3. Mechanism.**
1. `create` builds `Caffeine.newBuilder().maximumWeight(cap).weigher(w).executor(ImmediateExecutor.INSTANCE).build()` (`CaffeineCache.java:53-57`). The constructor requires a weighted, size-bounded cache (`:43-45`).
2. On every `put`/`putIfAbsent`/`replace` (`CaffeineCache.java:107-120`) Caffeine calls the weigher. The weigher sums key and value `unsharedHeapSize()`; if the sum exceeds `Integer.MAX_VALUE` it throws `IllegalArgumentException` (`:64-67`, the target line), otherwise it truncates to `int` (`:68`).
   - Key side: `KeyCacheKey.unsharedHeapSize() = EMPTY_SIZE + sizeOfArray(key)` (`cache/KeyCacheKey.java:59-62`).
   - Value side (key cache): `AbstractRowIndexEntry`; for the BIG format `RowIndexEntry` returns `EMPTY_SIZE` (`io/sstable/format/big/RowIndexEntry.java:200-203`), `IndexedEntry` returns `BASE_SIZE + sum(IndexInfo.unsharedHeapSize()) + sizeOfReferenceArray(columnsIndex.length)` (`:613-621`), `ShallowIndexedEntry` returns `BASE_SIZE` (`:767-770`). The `int[] offsets` of `IndexedEntry` (`:496`) is not counted, so weight slightly undercounts.
   - Value side (counter cache): `ClockAndCount.unsharedHeapSize() = EMPTY_SIZE` (`db/ClockAndCount.java:46-49`); key `CounterCacheKey` = `EMPTY_SIZE + two byte[]` (`cache/CounterCacheKey.java:152-157`).
3. When total weight exceeds `maximumWeight`, W-TinyLFU evicts. Because the executor is `ImmediateExecutor` (`:56`) eviction maintenance runs on the calling thread, so overshoot is short-lived; Caffeine may still briefly exceed the maximum between a write and its maintenance run (Caffeine docs: the bound is applied "eventually", and an entry heavier than the maximum can be evicted immediately).
4. Outcomes at the limit: total weight above max triggers eviction of cold entries (not an error). A single entry with weight above `Integer.MAX_VALUE` makes the `put` throw to the caller (the read path `KeyCacheSupport.cacheKey`, `io/sstable/keycache/KeyCacheSupport.java:80-87`, would propagate it). An entry heavier than the whole capacity is admitted then evicted.
5. Population: key cache is filled on exact index lookups (`BigTableReader.java:343`, `:393`, and `BigTableWriter.java:191` on flush/compaction migration); counter cache on counter writes/reads.

Bypass/overshoot: (i) real heap per entry = weight + Caffeine node/`ConcurrentHashMap` node overhead and frequency-sketch/queue structures, which the weigher does not count; (ii) the Caffeine frequency sketch is sized by the max weight; (iii) `getCachedPosition`/`AutoSavingCache` loading from saved cache at startup goes through the same `put`; (iv) `IndexedEntry.offsets` undercount (above). So heap use should be roughly linear in, and above, the weighted size, not exactly equal.

**A4. Other consumers.** Heap used by memtables, index summaries, bloom filters (off-heap since 4.x config but heap by default for some), chunk cache (off-heap, `file_cache_size`), row cache (off-heap OHC), metadata caches, prepared statements cache, and general garbage. The key cache keeps `ByteBuffer`-backed key arrays as `byte[]` (heap). Object headers of Caffeine internals (see A3 bypass).

**A5. Evidence beyond the source.** Caffeine documentation for `Caffeine.maximumWeight` / `Policy.Eviction` (https://github.com/ben-manes/caffeine/wiki/Eviction, https://www.javadoc.io/doc/com.github.ben-manes.caffeine/caffeine/): weights are relative, eviction is size-approximate, `int` weigher. Not re-read in this session beyond what the source comments say; treat as background. Cassandra tests in `test/unit/org/apache/cassandra/cache/` (`AutoSavingCacheTest.java`, `CacheProviderTest.java`) exist and could be used as templates (listed only, not read).

## B. Verification solution

**B1. Claim under test.** (1) With `key_cache_size = S MiB`, the key cache's weighted size never settles above S MiB (after eviction catches up) and the real on-heap bytes attributable to cached entries are within a constant factor of that weighted size, independent of how many distinct partitions are read. (2) The per-entry check at line 65 triggers only when one entry's key+value `unsharedHeapSize` exceeds `Integer.MAX_VALUE`, and then `put` throws `IllegalArgumentException` instead of caching.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a /users/jason92/cassandra-5.0.9/ /tmp/c509/`; never build in the shared copy). `cd /tmp/c509 && ant jar` (or `ant build-test`). Put a JUnit test `test/unit/org/apache/cassandra/cache/CaffeineCacheWeightTest.java` in the local copy; run `ant testsome -Dtest.name=org.apache.cassandra.cache.CaffeineCacheWeightTest`. JVM options: `-Xmx1g -Xms1g`; `DatabaseDescriptor.daemonInitialization()` in `@BeforeClass` only if a Cassandra class needing config is touched.

**B2b. Knobs.** Capacity passed to `CaffeineCache.create(long)`: 1 MiB, 8 MiB, 64 MiB (spaced 8x so weight ratios are unambiguous). Value type: (a) a stub `IMeasurableMemory` whose `unsharedHeapSize()` returns a settable `long`; (b) real `KeyCacheKey`/`RowIndexEntry` for realism. Stub weight values for the guard test: `Integer.MAX_VALUE - key`, `Integer.MAX_VALUE`, `Integer.MAX_VALUE + 1L`.

**B2c. Workload.** (1) Put N stub entries of fixed weight w = 1 KiB with distinct keys, N chosen so N*w = 4x capacity (4096 for 1 MiB, 32768 for 8 MiB, 262144 for 64 MiB), from 1 and from 8 threads. (2) `setCapacity` down from 64 MiB to 8 MiB after filling. (3) Guard: one `put` with weight at, below, and above `Integer.MAX_VALUE`.

**B2d. Observables and instruments.** `cache.weightedSize()`, `cache.size()`, `cache.capacity()` (`CaffeineCache.java:72-95`); after each batch call `Thread.sleep(50)` or a second `put` to let maintenance run, then read. Exception class/message from the guard `put`. Heap attribution (optional): `jcmd <pid> GC.class_histogram` or JOL `GraphLayout` on the cache object; JOL is not in the tree, so only the first two are assumed. Not observable directly: Caffeine's internal node overhead.

**B2e. Procedure.** 1. Build as above. 2. For each capacity create `CaffeineCache.create(cap, stubWeigher)` where `stubWeigher` equals the one at `CaffeineCache.java:63-69`, but also run the real one-arg `create(cap)`. 3. Insert the workload; record `weightedSize`, `size`. 4. `setCapacity(8MiB)` on the 64 MiB cache, record again. 5. Run the three guard puts, record exception. 6. Repeat with real `KeyCacheKey` (random 16-byte key) and a `RowIndexEntry` built via the BIG serializer or stub subclass, if constructing one is awkward use the stub.

**B2f. Predictions.** For every capacity C: after maintenance, `weightedSize <= C` (strictly, plus at most one entry's weight if observed mid-maintenance); `size` ~= C / 1 KiB (+-1%), i.e. 1024, 8192, 65536 entries. After `setCapacity(8MiB)`: weightedSize drops to <= 8 MiB. Guard: weight `MAX-key` ok (cached or immediately evicted as larger than capacity, no exception); `MAX_VALUE` exactly: no exception; `MAX_VALUE + 1`: `IllegalArgumentException("Serialized size cannot be more than 2GiB/Integer.MAX_VALUE")`, and `containsKey` is false. The claim is wrong if `weightedSize` stays above C after maintenance, or the over-limit entry is cached.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| weightedSize <= C after maintenance and size ~= C/w for all three C | Mechanism works as traced (claim 1, unit level) |
| weightedSize > C persistently (more than one entry above) | Cap not enforced; claim wrong |
| `setCapacity` lowers weightedSize | Runtime change is effective |
| exception only at weight > MAX_VALUE | Line 65 guard behaves as read |
| exception at or below MAX_VALUE, or none above it | Guard misread (e.g. weight overflow before check); claim 2 wrong |
| weightedSize is much below C with size < C/w | Admission policy rejecting (TinyLFU) or maintenance not run; rerun with extra puts before judging |

**B2h. Controls.** Stub entry with weight 0 never evicts by weight (shows the weigher is the operand); a cache built with a different weigher (constant 1) caps entry count, not bytes (shows that the weigher, not the count, drives the bound); repeat single-threaded vs 8 threads to rule out concurrency effects.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, built from a local copy (`/tmp/c509`, `ant jar`). Heap `-Xms2G -Xmx2G` (`conf/jvm11-server.options` / `JVM_EXTRA_OPTS`), G1 with default flags. Data, commitlog, `saved_caches` on local disk of known size (>= 10 GB free, e.g. `/tmp/node1/...`). `conf/cassandra.yaml`: `key_cache_size` as per B3b; `key_cache_save_period: 0s` isn't valid, set `key_cache_save_period: 1h` and `key_cache_keys_to_save` default; `row_cache_size: 0`; `counter_cache_size: 0` (to isolate); `sstable.selected_format: big` (key cache only for BIG, `cassandra.yaml:531`); `concurrent_compactors: 1`; disable auto compaction on the test table (`nodetool disableautocompaction`) after load; `column_index_cache_size` default (2KiB).

**B3b. Knobs.** `key_cache_size`: `0`, `4`, `16`, `64` MiB (0 is the negative-cache control; 4x steps so differences are above noise; 64 > what the workload needs, so the cap does not bind). Set by yaml and restart for each run; additionally `nodetool setcachecapacity 16 0 0` at runtime in one run (arg order key, row, counter) to test the dynamic path.

**B3c. Workload.** Table `ks.t (pk text PRIMARY KEY, v blob)` with `caching = {'keys':'ALL','rows_per_partition':'NONE'}`, `compression` off to keep reads simple. Load P = 1,000,000 partitions with 24-byte keys and 10-byte values with `cassandra-stress` (`write n=1000000 -pop seq=1..1000000`) then `nodetool flush` and `nodetool disableautocompaction ks t`. Read phase: `cassandra-stress read n=3000000 -pop dist=uniform(1..1000000)` at `threads=32` for 10 minutes (key cache is filled by each exact partition-index lookup that passes the bloom filter). Arithmetic: per entry weight is roughly the sum of `KeyCacheKey` empty size, a 24-byte-key array, and a `RowIndexEntry` (a few dozen to ~100 bytes each, so on the order of 150-250 B), so 4 MiB holds ~20-30k entries, 16 MiB ~100k, 64 MiB ~250-400k. All are below P = 1M distinct keys (1M x ~150-250 B = ~150-250 MiB), so uniform reads over P make all three non-zero caps bind. For a non-binding control add `key_cache_size=512`, which exceeds the whole key set. Duration: 10 minutes per run, long enough for >= 3M lookups, i.e. several passes over the cap-sized working set.

**B3d. Observables and instruments.** (1) JMX/`nodetool`: `nodetool info` (Key Cache entries, size, capacity), or MBean `org.apache.cassandra.metrics:type=Cache,scope=KeyCache,name=Size|Capacity|Entries|HitRate` read with `nodetool sjk mx` or `jmxterm`; sampled every 10 s. (2) Actual heap: `jcmd <pid> GC.class_histogram` (forces GC, "live" instances) every 2 min: bytes of `KeyCacheKey`, `RowIndexEntry` (+`$IndexedEntry`/`$ShallowIndexedEntry`), `byte[]` retained, and `com.github.benmanes.caffeine.cache.*Node*` classes; sum of Caffeine node classes is the overhead not counted by the weigher. (3) Total used heap after forced GC: `jcmd <pid> GC.run` then `jstat -gc`. Not observable: per-object retained size by owner (histogram sums classes, not ownership).

**B3e. Procedure.** 1. Build, configure a fresh data dir, start node, wait `nodetool status` UN. 2. Create schema, load P, flush, disable autocompaction. 3. Restart the node (clears the key cache, which load can fill via flush migration `BigTableWriter.java:191`) with the knob under test. 4. Record t0 histogram and metrics. 5. Run the read phase; every 10 s sample metrics, every 2 min histogram. 6. After the phase, `nodetool info`, final histogram, `GC.run`, `jstat -gc`. 7. For the runtime path: restart at 64, run 3 min, `nodetool setcachecapacity 16 0 0`, run 3 more, compare Size and histogram. 8. `nodetool drain; kill` the node, repeat for each knob value. Order runs 0, 4, 16, 64, 512 (increasing), then re-run 16 once to check repeatability.

**B3f. Predictions.** Metric `Size` <= `Capacity` = knob * 1048576 at all samples after warm-up (rising for a short period at most one entry past it). `Entries` x average weight ~ `Size`. For 4, 16, 64: `Size` plateaus at about the cap, entries ratio ~1 : 4 : 16 (the same average weight). For 0: `Size` 0, `Entries` 0, no KeyCacheKey instances in the histogram. For 512: `Size` keeps growing to ~P x weight (below the cap) and does not plateau at 512 MiB. Histogram bytes of key-cache classes (KeyCacheKey + RowIndexEntry + their byte[] + Caffeine nodes) at plateau: between 1.0x and ~2.5x of `Size` (the factor being node overhead, sketch and uncounted fields), and the same factor across 4/16/64 (within +-25%). The claim is wrong if histogram bytes rise with the number of distinct keys read after `Size` has plateaued, or if the factor grows with the knob.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| `Size` plateaus at <= cap and histogram bytes scale ~linearly with cap with a stable factor | Cap governs actual heap (claim confirmed), with factor = uncounted overhead |
| Histogram bytes grow after `Size` plateaus | Real usage not bounded by weight; claim refuted |
| `Size` > cap persistently (more than a few entries over) | Cap not enforced |
| Factor differs a lot between 4 and 64 MiB | Weigher undercounts something that scales (e.g. `IndexedEntry.offsets` or wide partitions); investigate which class |
| Cap=0 still shows entries | disable path not working as read |
| 512 run plateaus before 512 MiB | Entries evicted by something other than weight (admission policy or compaction invalidation); reconcile |
| Runtime `setcachecapacity 16` lowers `Size` and histogram bytes | Dynamic path effective |

**B3h. Controls.** Cap=0 run (no key-cache objects); non-binding 512 MiB run (shows growth is not a plateau artifact); identical workload and heap for all runs, with `GC.run` before each histogram so garbage does not inflate counts; row/counter cache off so only the key cache differs; repeat the 16 MiB run to estimate noise. For the guard (line 65), it is unreachable by this workload (largest key cache value is bounded by the `column_index_cache_size` / index-entry sizes); the unit tier covers it, and a cluster alternative is not available short of patching the weigher.

**B4. Risks and cleanup.** Unit tier: only `/tmp/c509` build output; delete with `rm -rf /tmp/c509`. Cluster tier: data = P x (key 24 B + value 10 B + overhead) ~ <1 GB plus commitlog; keep all directories on local disk under `/tmp/node1`, never on shared storage; set `commitlog_total_space` small (e.g. 1 GiB). Heap histograms pause the JVM (do not take them during timed throughput measurements). At the end: `nodetool drain`, kill the node and cassandra-stress, `pgrep -fl 'CassandraDaemon|cassandra-stress'` must be empty, `rm -rf /tmp/node1`.

**B-audit. Stage-4 audit amendments (2026-10-25, before any reading; the sha256 recorded in the results file is of the file after these).** None changes a claim, a prediction or a conclusions row; they make the design runnable.

B2i (unit tier).
1. Entries are stubs implementing `IMeasurableMemory` (key weight settable, 0 unless stated; value weight settable); the production weigher is used through `CaffeineCache.create(long)`, so the target line is the one executed. `CaffeineCache` has no `containsKey`: "not cached" in B2f means `get(key) == null`.
2. B2c(3) guard values: key weight `kw` in {0, 16}; value weight such that `kw + vw` is `Integer.MAX_VALUE - 1`, `Integer.MAX_VALUE`, `Integer.MAX_VALUE + 1`, and `3 x Integer.MAX_VALUE`. The capacity is 64 MiB, below the weights, so a non-throwing put is admitted then evicted at once (B2f: "cached or immediately evicted"). After the rejected puts one normal put must still succeed.
3. Calibration (not a prediction): the same test builds the real `KeyCacheKey` (24-byte key) and BIG `RowIndexEntry` and records their `unsharedHeapSize()` and the average weight in a real-class cache; the cluster tier's per-entry weight is then known before it runs. The test writes its numbers to a file; the verdict is made by a separate analyzer from that file.

B3i (cluster tier).
1. Load with `cassandra-stress user` and a profile for `ks.t (pk text PRIMARY KEY, v blob)` (`pk` fixed 24 characters, `v` fixed 10 bytes, `caching = {'keys':'ALL','rows_per_partition':'NONE'}`, compression off), `n=1000000` with `-pop seq=1..1000000`, then `nodetool flush` and `nodetool compact ks t` once, so that every run reads one sstable and no compaction runs in a run. The data directory is then reused read-only by every knob value (reads change no file); `saved_caches` is emptied before every start so that no saved key cache is loaded.
2. Read phase: `cassandra-stress user profile=... 'ops(read1=1)' n=3000000 -pop dist=uniform(1..1000000) -rate threads=32` run twice in a row (6,000,000 reads, coverage of the 1,000,000 keys 1 - e^-6 = 99.8 %); the 10 minutes in B3c is an upper bound, not the plan. The profile query is `select * from t where pk = ?`.
3. Attribution of heap (B3d): the class histogram cannot attribute `byte[]` to the cache, so the key-cache bytes are the sum of the histogram's `KeyCacheKey`, `RowIndexEntry` (BIG) and Caffeine node-class rows, plus `Entries` x (16-byte array header + 24-byte key, rounded to 8) for the key arrays. Ratio = this sum / `Size`.
4. Isolation on the shared node: own source tree, loopback address, JMX port and data directory (`~/s4-kc/`); `nodetool -p <jmx port> -h <address>`. Heap `-Xms2G -Xmx2G`.
5. The per-entry weight (about 100 to 250 B, B3c) is replaced by the unit-tier calibration of B2i.3; the caps 4, 16, 64 MiB must each lie below 1,000,000 x that weight, else the 64 MiB value is recorded as non-binding and the arm is read as a control, not as a cap.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/cache/CaffeineCache.java
- src/java/org/apache/cassandra/service/CacheService.java (lines 100-200, grep for 320-350)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (lines 808-848, grep)
- src/java/org/apache/cassandra/config/Config.java (grep)
- conf/cassandra.yaml (lines 515-540, 588-600; grep)
- src/java/org/apache/cassandra/cache/KeyCacheKey.java, CounterCacheKey.java (grep)
- src/java/org/apache/cassandra/db/ClockAndCount.java (grep)
- src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java (excerpts)
- src/java/org/apache/cassandra/io/sstable/format/big/BigTableReader.java (lines 322-350, grep)
- src/java/org/apache/cassandra/io/sstable/keycache/KeyCacheSupport.java (grep excerpt)
- src/java/org/apache/cassandra/metrics/CacheMetrics.java (grep)
- directory listing of test/unit/org/apache/cassandra/cache/

## D. Stage-4 feedback

**Stage-4 feedback (2026-10-25; results: `stage4-runtime-verification/results/key_cache_size-create-size--autonomous.md`; the case file is untracked, so no commit).**
- **Verdict: Confirmed at both tiers, effect `caps`, outcome class true positive** (estimate `positive`). Unit: B2g rows 1 to 4 (`weightedSize` = C exactly after 4 x C of 1 KiB puts at 1, 8, 64 MiB and 1 or 8 threads; `setCapacity` 64 -> 8 MiB lowers it at once; the line-65 guard throws only when key+value weight exceeds `Integer.MAX_VALUE`, and an entry heavier than the capacity but not above `Integer.MAX_VALUE` is admitted then evicted). Cluster: B3g row 1 (`key_cache_size` 4 / 16 / 64 MiB: `Size` 4,194,240 / 16,777,152 / 67,108,800 B, 64 B under the cap, entries 43,690 / 174,762 / 699,050; heap of the key cache's classes 1 : 4.00 : 15.99 with factor 1.417; cap 0 held nothing; 512 MiB ended at the key set, 95.8 MB, 997,581 entries; runtime `setcachecapacity 16 0 0` from 64 lowered `Size` to 16,777,152 within 30 s).
- **Amendments made before the first reading (section "B-audit", sha256 in the results file §1):** stub entries and `get` instead of the non-existent `containsKey` (B2i.1-2); real-class calibration (B2i.3); stress profile, one compacted sstable, saved caches emptied, two read passes (B3i.1-2); histogram attribution (B3i.3); own ports (B3i.4); binding check from the measured weight (B3i.5).
- **Corrections to the trace:** the per-entry weight of a key-cache entry for a 24-byte key and a small partition is 96 B (`KeyCacheKey` 72 + `RowIndexEntry` 24), not the 150 to 250 B estimated in B3c; the arithmetic still holds (1,000,000 keys = 91.6 MiB, so 4, 16 and 64 MiB bind). The factor of the counted classes over `Size` is 1.417; counting the whole live-heap increase (`ConcurrentHashMap$Node` and the other Caffeine structures) it is 1.9 to 2.0, both inside the predicted 1.0 to 2.5.
- **Findings for Target 3 (not chased):** after a runtime shrink (`setcachecapacity`) the counted classes fall to the new cap's figures, but the live heap stayed 17.3 MB above a fresh run at that cap (larger `int[]`, `long[]` and `ConcurrentHashMap$Node[]` rows; the owner of the generic arrays is inferred to be Caffeine's tables sized for the old maximum, not proven). Not tested: wide partitions (`IndexedEntry.offsets` is not weighed, A3), the counter cache, and any cluster reach of the line-65 guard (unreachable by a workload, as B3h says).
- **Defects:** none in the case file's claim, predictions or conclusions rows; the harness's first cluster launch stopped on its own `count(*)` timeout (harness only, results §3).
