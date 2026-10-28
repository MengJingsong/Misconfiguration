# counter cache capacity (enable gate) — verification solution  <!-- file: cases/counter_cache_size-processmodifications-capacity--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`CounterMutation.java:213`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/CounterMutation.java#L213) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI, 2026-10-27 |
| Estimate | `positive`: the gate `getCapacity() != 0` turns the counter cache on or off, and the cache it enables is a Caffeine cache with `maximumWeight` equal to the capacity, so counter-cache heap follows `counter_cache_size`. |
| Ground | — |

**Type:** non-config (runtime-queried; numeric literal `0`). The queried value `counterCache.getCapacity()` is itself derived from the yaml entry `counter_cache_size` (or an auto default and JMX), but the check compares it with the literal `0`, so the constant rule makes this non-config.

## A. Constraint trace

**A1. The constraint.** Name: counter cache capacity (`CacheService.instance.counterCache.getCapacity()`), compared with the literal `0` at [`CounterMutation.java:213`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/CounterMutation.java#L213). Kind: runtime-queried value vs numeric literal `0` (constant rule). The capacity is first set in [`CacheService.java:176`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/CacheService.java#L176) (`DatabaseDescriptor.getCounterCacheSizeInMiB() * 1024 * 1024`) and passed to `CaffeineCache.create(capacity)` (CacheService.java:179). Unit: bytes of weighted entries (`CaffeineCache.create` weigher = `key.unsharedHeapSize() + value.unsharedHeapSize()`, CaffeineCache.java:63-69). Source value: yaml `counter_cache_size` (Config.java:479-480, MiB, replaces `counter_cache_size_in_mb`; `conf/cassandra.yaml:595`). Default when unset: `min(max(1, 2.5% of totalMemory in MiB), 50)` (DatabaseDescriptor.java:834-836). Negative values rejected (DatabaseDescriptor.java:838). Settable by yaml (restart) and at runtime via `CacheService.setCounterCacheCapacityInMB` (CacheService.java:344-349, JMX `setCounterCacheCapacityInMB`). `getCapacity()` = `InstrumentingCache.getCapacity` (InstrumentingCache.java:77) -> `CaffeineCache.capacity()` -> `policy.getMaximum()` (CaffeineCache.java:72-75).

**A2. What it caps.** Heap (Caffeine on-heap map): total weight of cached `CounterCacheKey` -> `ClockAndCount` entries. The `!= 0` check itself decides only whether the cache is consulted; a capacity of 0 means no counter cache (also ColumnFamilyStore.java:2501 treats `== 0L` as "counter cache disabled").

**A3. Mechanism.** Enclosing method: `CounterMutation.processModifications` (CounterMutation.java:207), called on the counter write path (leader apply, `applyCounterMutation`). At [`CounterMutation.java:213`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/CounterMutation.java#L213): if capacity != 0, fetch values from the cache (`updateWithCurrentValuesFromCache`, line 243), return early if all marks hit (217-218); otherwise (or for remaining misses) read from the CFS (222) and treat leftovers as new (225-226). If capacity == 0, the cache lookup is skipped and every mark is read from the CFS. Each updated counter is written to the cache via `cfs.putCachedCounter` (line 239), which is itself gated on capacity at ColumnFamilyStore.java:2501. Overshoot: Caffeine eviction is asynchronous, so transient weight can slightly exceed the maximum; the bound is approximate, not hard. Lowering capacity at runtime shrinks the cache by eviction.

**A4. Other consumers.** Other heap users outside this cap: memtables, key cache, row cache (their own caps), the counter lock stripes (`LOCKS`, CounterMutation.java:~163), and read-path objects built in `updateWithCurrentValuesFromCFS`.

**A5. Evidence beyond the source.** none (source only; cache nodetool `info`/`getcachecapacity` reports counter cache size/capacity, to be used as an instrument).

## B. Verification solution

**B1. Claim under test.** Counter-cache heap usage is bounded by `counter_cache_size` (weighted capacity), and with capacity 0 the cache holds no entries and the cache branch at line 213 is not taken. Falsified if cache weight stays far above the capacity at steady state, or if entries accumulate with capacity 0.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant, local copy of tag outside the shared tree; `ant build`; a JUnit test (in a copy, e.g. `test/unit/org/apache/cassandra/db/CounterCacheCapacityTest.java`) using `CQLTester`; `ant testsome -Dtest.name=CounterCacheCapacityTest`.

**B2b. Knobs.** `CacheService.instance.setCounterCacheCapacityInMB` values 0, 1, 4 (runtime setter; no restart in-test).

**B2c. Workload.** Table `(k int PRIMARY KEY, c counter)`; `UPDATE ... SET c = c + 1 WHERE k = ?` for k in 0..N, N = 200000 (each entry weighs on the order of 100-200 bytes of heap, so about 20-40 MB total, exceeding 4 MiB).

**B2d. Observables and instruments.** `CacheService.instance.counterCache.size()` (entry count), `weightedSize()`/`getCapacity()` where exposed, and `Tracing`/hit counters (`counterCache.getMetrics()`). Not observable directly: Caffeine's transient overshoot between maintenance runs.

**B2e. Procedure.** For each capacity: set capacity, `counterCache.clear()`, run workload, call `cleanUp()` equivalent (small sleep), read entries and weight; then re-run updates on k in 0..99 and read the hit count.

**B2f. Predictions.** Capacity 0: entry count 0, hits 0 (cache branch skipped). Capacity 1 MiB: weight <= ~1 MiB (+ small slack), entries ~ 1 MiB / entry weight. Capacity 4 MiB: weight <= ~4 MiB, roughly 4x the 1 MiB entries.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Weight/entries scale with and stay within capacity; 0 gives no entries | claim confirmed |
| Weight well above capacity at steady state, or entries with capacity 0 | claim wrong |
| N too small to exceed capacity | limit not reached, not confirmed |

**B2h. Controls.** Same workload with capacity 0 vs nonzero; clear the cache between runs; fixed N; confirm key cache/row cache untouched.

### B3. Cluster tier

**B3a. Environment and build.** One node (optionally 2), JDK 11, build from local tag copy via `ant`, run from a separate directory; heap fixed with `-Xms2G -Xmx2G`.

**B3b. Knobs.** yaml `counter_cache_size: 0MiB` / `8MiB` / `32MiB`; `counter_cache_save_period` large to avoid save I/O interfering.

**B3c. Workload.** `cassandra-stress` counter write (`counter_write n=5000000 -rate threads=50` with a wide key population, e.g. `-pop dist=uniform(1..5000000)`) so distinct counters far exceed 32 MiB of cache entries.

**B3d. Observables and instruments.** `nodetool info` (Counter Cache entries, size, capacity), `jcmd <pid> GC.class_histogram` (CounterCacheKey / ClockAndCount instances), `nodetool tablestats`/JMX cache metrics `org.apache.cassandra.metrics:type=Cache,scope=CounterCache`.

**B3e. Procedure.** For each knob value: fresh data dir, start node, run workload, sample `nodetool info` every 30 s and class histogram at the end, stop node, verify no process left (`pgrep -f CassandraDaemon`).

**B3f. Predictions.** 0: size 0, no CounterCacheKey instances beyond transient. 8 MiB: reported size <= ~8 MiB, instance count roughly constant after fill. 32 MiB: reported size <= ~32 MiB, about 4x instances of the 8 MiB run.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Size tracks capacity and plateaus below it; 0 gives empty cache | claim confirmed |
| Size or instance count keeps growing past capacity | claim wrong |
| Workload ends before cache fills | limit not reached, not confirmed |

**B3h. Controls.** Same workload on all three runs; identical heap; compare with capacity 0 run as baseline for non-cache heap.

**B4. Risks and cleanup.** Disk: stress data (a few GB at most); use a private data dir and delete it afterward; kill all started Cassandra/stress processes and verify with `pgrep`; do not build in the shared tree.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/CounterMutation.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/service/CacheService.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cache/CaffeineCache.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cache/InstrumentingCache.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java (grep)
- /users/jason92/cassandra-5.0.9/conf/cassandra.yaml (grep)

## D. Stage-4 feedback

`none yet`
