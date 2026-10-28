# counter_cache_size (counter cache disabled guard in putCachedCounter) — verification solution  <!-- file: cases/counter_cache_size-putcachedcounter-capacity--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`ColumnFamilyStore.java:2508`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L2508) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI, 2026-10-27 |
| Estimate | `positive`: counter-cache heap follows `counter_cache_size` (Caffeine max weight); the guard only short-circuits the disabled (0) case, so at 0 nothing is stored and above 0 the weighted size is bounded by the capacity. |
| Ground | — |

**Type:** non-config (hard-coded constant): the check `getCapacity() == 0L` compares a yaml-derived capacity (`counter_cache_size`) against the numeric literal `0L`; per the widened constant rule the literal makes it non-config. Both are named: yaml entry `counter_cache_size` and literal `0L`.

## A. Constraint trace

**A1. The constraint.** Compared value: `CacheService.instance.counterCache.getCapacity()`, derived from yaml `counter_cache_size` (kind: configuration entry; declared at [`Config.java:480`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L480)). Literal in the check: `0L` ([`ColumnFamilyStore.java:2508`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L2508)), no named constant. Unit: MiB in yaml, bytes in the cache (`* 1024 * 1024`, CacheService.java:176). Default: unset (null) means auto, `min(max(1, 2.5% of totalMemory in MiB), 50)` MiB (DatabaseDescriptor.java:834-836; conf/cassandra.yaml:595 comment). Set via yaml `counter_cache_size` (restart) and at runtime via JMX `CacheService.setCounterCacheCapacityInMB` (CacheService.java:344-349, rejects negatives), which calls Caffeine `policy.setMaximum`. Value < 0 is rejected at startup (DatabaseDescriptor.java:838-844).

**A2. What it caps.** Heap (on-heap Caffeine cache). Quantity: the cache's weighted size, sum over entries of `key.unsharedHeapSize() + value.unsharedHeapSize()` (CaffeineCache.java:61-69), compared by Caffeine against `maximumWeight(capacity)` (CaffeineCache.java:54). The `== 0` check itself tests only "disabled".

**A3. Mechanism.** `initCounterCache` builds `CaffeineCache.create(capacity)` with capacity = `getCounterCacheSizeInMiB() * 1024 * 1024` (CacheService.java:176-179). In [`putCachedCounter`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L2508) (enclosing method, ColumnFamilyStore.java:2506-2511): if capacity == 0 the method returns without inserting (true outcome: nothing cached, no key object allocated); otherwise it builds a `CounterCacheKey` and `put`s it, and Caffeine evicts to keep weight <= capacity (executor is `ImmediateExecutor`, CaffeineCache.java:56). Sibling guard at ColumnFamilyStore.java:2501 (`getCachedCounter`) is identical. Callers: `CounterMutation.updateWithCurrentValue` (CounterMutation.java:239) after reading/updating a counter, and `getCachedCounter` at CounterMutation.java:249. Overshoot: weights are estimates (`unsharedHeapSize`), and Caffeine's bound is a soft eviction bound, so real heap can differ slightly from the weighted size; the key/value objects are not counted beyond that estimate. Bypass: if capacity is raised at runtime via JMX, the guard stops short-circuiting immediately; lowering it makes Caffeine evict down to the new maximum.

**A4. Other consumers.** Heap shared with memtables, key/row caches, and compaction; the counter cache's `AutoSavingCache` saved-keys file on disk (`saved_caches_directory`) is a separate disk consumer (CacheService.java:183-189), not governed by this check. Counter reads from sstables (`updateWithCurrentValuesFromCFS`) are unaffected.

**A5. Evidence beyond the source.** conf/cassandra.yaml:590-596 (doc comment: "Set to 0 to disable counter cache"). No other external evidence relied on.

## B. Verification solution

**B1. Claim under test.** Counter-cache heap usage is bounded by `counter_cache_size`: with `0` no entries are retained, and with a small positive value the cache's weighted size stays <= capacity (modulo estimate error) however many distinct counters are updated.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant; copy the tag to a private directory (`rsync -a cassandra-5.0.9/ ~/work/cass-unit/`), `ant jar`, then write a small JUnit-style test class (outside the shared tree) that runs with `DatabaseDescriptor.daemonInitialization()` and a table `CREATE TABLE ks.c (k int, ck int, v counter, PRIMARY KEY (k, ck))` via `SchemaLoader`. JVM: `-Xmx512m`.

**B2b. Knobs.** Capacity via `CacheService.instance.setCounterCacheCapacityInMB(n)` for n in {0, 1, 4}. Because the check literal 0 cannot be varied, the two arms are capacity 0 vs capacity > 0 (this exercises both outcomes of the guard).

**B2c. Workload.** Call `cfs.putCachedCounter(key, clustering, column, null, ClockAndCount.create(1L, 1L))` for N = 200,000 distinct keys. Entry weight is on the order of 100-200 bytes, so 200,000 entries is roughly 20-40 MiB, well beyond 1 and 4 MiB.

**B2d. Observables and instruments.** `counterCache.size()`, `counterCache.weightedSize()` (CaffeineCache.java:87-95, via `getCapacity()` and the AutoSavingCache wrapper), plus `Runtime.totalMemory()-freeMemory()` after `System.gc()`. True retained heap is only visible via a heap histogram (`jcmd GC.class_histogram`).

**B2e. Procedure.** For each n: set capacity, clear cache, run the loop, record size, weightedSize, heap used after gc; also `getCachedCounter` for the first key.

**B2f. Predictions.** n=0: size == 0, `getCachedCounter` returns null, heap delta ~0. n=1: weightedSize <= 1 MiB (1,048,576) and size far below N. n=4: weightedSize <= 4 MiB, about 4x the n=1 entry count.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| size 0 at n=0; weightedSize <= capacity at n=1 and n=4 | claim confirmed |
| size > 0 at n=0 | guard not effective; claim wrong |
| weightedSize far above capacity | cap does not bind; claim wrong |
| N entries never exceed capacity (e.g. N too small) | limit not reached, not confirmed |

**B2h. Controls.** Same JVM and key set for all arms; run n=4 first and last to rule out warm-up effects; explicit `System.gc()` before each heap reading.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, built from a private copy of the tag; `data_file_directories`, `commitlog_directory`, `saved_caches_directory` under a private run directory; `-Xms2G -Xmx2G`. Run three times with yaml `counter_cache_size: 0MiB`, `1MiB`, `8MiB`.

**B3b. Knobs.** `counter_cache_size` in yaml (restart per run); optionally JMX `setCounterCacheCapacityInMB` for a live change.

**B3c. Workload.** Table with a counter column; `cassandra-stress` (or a script) issuing `UPDATE ks.c SET v = v + 1 WHERE k=? AND ck=?` over 2,000,000 distinct (k, ck) pairs, 4 client threads, until all pairs are written once, then repeated reads of counters once more. At roughly 150 bytes per entry this is about 300 MB of offered weight, far above 8 MiB.

**B3d. Observables and instruments.** `nodetool info` (Counter Cache line: entries, size, capacity, hit rate), JMX `org.apache.cassandra.metrics:type=Cache,scope=CounterCache,name=Size/Entries/HitRate`, and `jcmd <pid> GC.class_histogram` for `CounterCacheKey`/`ClockAndCount` retained bytes; sampled every 10 s.

**B3e. Procedure.** For each setting: start node, create schema, run workload, sample, record, then `nodetool drain`, stop the node, confirm no process left (`pgrep -f CassandraDaemon`), delete the run directory.

**B3f. Predictions.** 0MiB: Entries 0, Size 0, hit rate 0 (no `CounterCacheKey` instances in histogram). 1MiB: Size <= 1 MiB, Entries about 7,000-10,000. 8MiB: Size <= 8 MiB, Entries about 8x the 1MiB case; histogram bytes for the two key/value classes track Size within a modest factor.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Size at or under capacity at each setting, Entries scaling with capacity, zero at 0 | claim confirmed |
| Entries > 0 at 0MiB | guard fails; claim wrong |
| Size grows beyond capacity with workload | usage does not follow the constraint; claim wrong |
| Histogram bytes much larger than Size | weigher underestimates; note as overshoot, claim holds for weighted size only |
| workload never fills 1MiB | not confirmed |

**B3h. Controls.** Same schema/workload/heap across runs; disable key/row caches interplay by leaving them default in all runs; restart node between runs.

**B4. Risks and cleanup.** Disk: a few hundred MB per run in the private run directory (saved counter cache file is small); delete after each run, never use shared storage. Stop every Cassandra and stress process and verify none remain.

## C. Sources read

- src/java/org/apache/cassandra/db/ColumnFamilyStore.java (2470-2550)
- src/java/org/apache/cassandra/service/CacheService.java
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (828-846, 3949)
- src/java/org/apache/cassandra/config/Config.java (479-480)
- src/java/org/apache/cassandra/cache/CaffeineCache.java
- src/java/org/apache/cassandra/db/CounterMutation.java (232-262)
- conf/cassandra.yaml (590-596)

## D. Stage-4 feedback

`none yet`
