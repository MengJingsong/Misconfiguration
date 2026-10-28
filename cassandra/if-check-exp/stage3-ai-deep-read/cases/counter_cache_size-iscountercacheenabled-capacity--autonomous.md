# counter_cache_size (counter cache enabled gate) — verification solution  <!-- file: cases/counter_cache_size-iscountercacheenabled-capacity--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`ColumnFamilyStore.java:3269`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3269) (`isCounterCacheEnabled()`, defined at 3267) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI, 2026-10-27 |
| Estimate | `positive`: the compared quantity is the counter cache's weighted capacity, which Caffeine enforces as `maximumWeight` on heap-size-weighted entries, so counter-cache heap follows `counter_cache_size`. The helper's own comparison (`> 0`) is only an on/off gate. |
| Ground | — |

**Type:** non-config (hard-coded constant: the numeric literal `0` in `capacity > 0`; the compared capacity itself comes from yaml `counter_cache_size`, and the conjunct `metadata().isCounter()` is a per-table property — both named)

## A. Constraint trace

**A1. The constraint.** The check is `metadata().isCounter() && CacheService.instance.counterCache.getCapacity() > 0` at [`ColumnFamilyStore.java:3269`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3269).
- Literal: `0` at the same line (no named constant). Per the constant rule this makes the row non-config.
- Compared value: `getCapacity()` ([`InstrumentingCache.java:77`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/InstrumentingCache.java#L77)) -> `CaffeineCache.capacity()` -> `policy.getMaximum()` (`CaffeineCache.java:72-75`), i.e. the byte weight passed at construction.
- That capacity is set in `CacheService.initCounterCache()` (`CacheService.java:172-176`): `DatabaseDescriptor.getCounterCacheSizeInMiB() * 1024 * 1024`.
- Declared: yaml `counter_cache_size`, [`Config.java:480`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L480) (`LongMebibytesBound`, default null = auto), derived in [`DatabaseDescriptor.java:834-836`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L834): null -> `min(max(1, 2.5% of totalMemory in MiB), 50)`; negative rejected (838-844). Unit MiB. Yaml (`conf/cassandra.yaml:595`, "Set to 0 to disable").
- Settable: yaml (restart), and at runtime via JMX `CacheService.setCounterCacheCapacityInMB` (`CacheService.java:342-349`), which changes the same capacity the helper reads.
- Other conjunct: `TableMetadata.isCounter()` (`TableMetadata.java:286`) is a table flag (COUNTER), set at CREATE TABLE; not a limit.

**A2. What it caps.** Heap. The counter cache (`CacheService.counterCache`, entries `CounterCacheKey -> ClockAndCount`) is weighted by `key.unsharedHeapSize() + value.unsharedHeapSize()` (`CaffeineCache.java:61-70`) and bounded by `maximumWeight(capacity)`. The helper's operand is that capacity; the helper only tests whether it is nonzero (cache on) and the table is a counter table.

**A3. Mechanism.** Enclosing method `ColumnFamilyStore.isCounterCacheEnabled()` (3267-3270): true iff the table is a counter table and capacity > 0.
- Call sites read: only [`CacheService.java:382`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/CacheService.java#L382) in `CounterCacheSerializer.deserialize` (the `if (!cfs.metadata().isCounter() || !cfs.isCounterCacheEnabled()) return null;`). No other caller in `src/` or `test/`.
- True: the saved counter-cache key is reloaded (a READ-stage task reads the counter value and the pair is inserted into the cache at startup load). False: the saved key is skipped, so a disabled cache (capacity 0) or a non-counter table loads nothing.
- Related, not the helper: the write path gate `CounterMutation.java:213` uses `getCapacity() != 0` directly, and entries are admitted/evicted by Caffeine under the weight bound.
- Bypass/overshoot: with capacity > 0 the weight bound is enforced by Caffeine (approximate/asynchronous eviction, with `ImmediateExecutor`, so little transient overshoot). Capacity 0 means no caching. Per-entry heap is whatever `unsharedHeapSize` reports, so real heap can differ from the weight estimate. Runtime JMX resize changes the cap without restart.

**A4. Other consumers.** Key cache and row cache are separate caches with their own capacities. Counter writes also use the memtable, the per-key counter lock stripes and the read path (sstable/row reads when the cache misses), which are outside this cap. The auto size derives from JVM `totalMemory()` at startup.

**A5. Evidence beyond the source.** `conf/cassandra.yaml:585-595` documents `counter_cache_size` (auto = min(2.5% heap, 50 MiB); 0 disables). No external docs or history relied on.

## B. Verification solution

**B1. Claim under test.** The counter cache's heap footprint is bounded by `counter_cache_size` (capacity > 0 enables it and the footprint stays at or near the capacity under a counter workload larger than the capacity), and with `counter_cache_size: 0` the helper returns false and the cache stays empty. Since the literal `0` is the gate, flipping capacity between 0 and a small positive value flips both the helper and the footprint.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant, a private copy of the tag (`rsync -a` to a scratch dir, never the shared tree); `ant jar` then a JUnit test in the copy's `test/unit/org/apache/cassandra/db/` using `SchemaLoader` with one counter table and one regular table. JVM options: default test options.

**B2b. Knobs.** `CacheService.instance.setCounterCacheCapacityInMB(n)` with n in {0, 1, 4}. 0 tests the literal boundary; 1 and 4 show the cap scaling. A per-test `DatabaseDescriptor.setCounterCacheSizeInMiB` is not available, so use the JMX-equivalent setter.

**B2c. Workload.** Insert N distinct `CounterCacheKey`s with `ClockAndCount` values directly into `CacheService.instance.counterCache` (`put`). Entry weight is about 100-150 B (measure one with `key.unsharedHeapSize()+value.unsharedHeapSize()`), so N = 200,000 puts exceed 4 MiB (200,000 x ~120 B = ~24 MB).

**B2d. Observables and instruments.** `cfs.isCounterCacheEnabled()` for the counter and regular tables; `counterCache.weightedSize()` (or `size()` and `getCapacity()`); entry count. Cannot observe true heap per entry here (only the estimate).

**B2e. Procedure.** For each n: set capacity, call `counterCache.clear()`, assert helper results, put N keys, record `weightedSize()` and `size()`. Run with `ant testsome -Dtest.name=<Class> -Dtest.methods=<m>`.

**B2f. Predictions.** n=0: helper false for both tables, puts retain nothing (size 0, weightedSize 0). n=1: helper true only for the counter table, false for the regular table; weightedSize <= ~1 MiB (+ small slack); n=4: weightedSize <= ~4 MiB (+ slack), size about 4x that for n=1.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Helper flips with n=0 vs 1 and weightedSize <= n MiB (+slack) and scales ~linearly | claim confirmed (usage follows constraint) |
| weightedSize far above n MiB | claim refuted: cap does not bind |
| Helper true at n=0, or false at n=1 for the counter table | helper does not behave as stated |
| Helper true for the regular table | isCounter conjunct not effective |

**B2h. Controls.** Regular table as a control for the `isCounter()` conjunct; same key population across n; clear between runs.

### B3. Cluster tier

**B3a. Environment and build.** One node (Linux, JDK 11), built from a private copy of the tag; heap fixed e.g. `-Xms2G -Xmx2G`; data/saved_caches on a scratch directory. cassandra.yaml: `counter_cache_size` per arm; `counter_cache_save_period: 3600`, `counter_cache_keys_to_save` default.

**B3b. Knobs.** `counter_cache_size` in {0, 1MiB, 8MiB} (yaml, restart per arm); the helper's effect is also seen on restart (saved cache reload).

**B3c. Workload.** One counter table (`id bigint primary key, c counter`); `cassandra-stress` or a driver loop issuing `UPDATE ... SET c = c + 1` over 2,000,000 distinct ids (each cached entry ~100+ B, so 2M entries ~200+ MB demand vs 8 MiB cap), single pass, then a second pass over a hot subset. Then `nodetool drainsave`-equivalent: `nodetool flush` and `nodetool` cache save (`nodetool setcachecapacity` is not used) followed by a restart to exercise the load path.

**B3d. Observables and instruments.** `nodetool info` (Counter Cache line: entries, size, capacity, hit rate); `jcmd <pid> GC.class_histogram` or a heap dump histogram for CounterCacheKey/ClockAndCount instance counts and bytes; JMX `org.apache.cassandra.metrics:type=Cache,scope=CounterCache,name=Size/Entries/Capacity`. Sampled after each pass and after restart. Heap per entry is only estimated by the class histogram.

**B3e. Procedure.** For each arm: start node with the yaml; create the table; run pass 1, pass 2; record the above; run `nodetool flush`, trigger a cache save (wait for `saved_caches/*CounterCache*` or `nodetool` save via JMX `saveCaches`), restart; record entries after the restart load; stop the node and check no Cassandra process remains (`pgrep -f CassandraDaemon`).

**B3f. Predictions.** 0: Capacity 0, Entries 0, no CounterCache class instances in histogram, no saved file entries, and after restart 0 entries. 1 MiB: Size <= ~1 MiB and Entries roughly 1/8 of the 8 MiB arm; histogram bytes of the two classes within ~2x of Size. 8 MiB: Size <= ~8 MiB, entries about 8x the 1 MiB arm; after restart the reload brings back at most the capacity's worth of entries.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Size and histogram bytes scale with the knob and stay at or below it | claim confirmed |
| Size/histogram bytes far exceed the cap (> 2x) | claim refuted |
| 0 arm still holds entries or reloads entries after restart | the `> 0` gate does not disable caching |
| Entries do not rise above a handful in the non-zero arms | workload did not reach the limit; not confirmed |

**B3h. Controls.** Same workload against a regular (non-counter) table must leave the counter cache empty (isCounter conjunct); same heap and JVM flags across arms; same key set.

**B4. Risks and cleanup.** Disk: saved cache files and sstables from 2M counters (a few hundred MB at most) go in a scratch directory that is deleted after the run; no shared storage. Stop every Cassandra and stress process and verify with `pgrep`; delete the private build copy.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java (3259-3275)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/service/CacheService.java (80-190, 340-400)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java (828-865, 3947)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java (479-480)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cache/CaffeineCache.java, InstrumentingCache.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/CounterMutation.java (205-235)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/schema/TableMetadata.java (286)
- /users/jason92/cassandra-5.0.9/conf/cassandra.yaml (585-595)

## D. Stage-4 feedback

`none yet`
