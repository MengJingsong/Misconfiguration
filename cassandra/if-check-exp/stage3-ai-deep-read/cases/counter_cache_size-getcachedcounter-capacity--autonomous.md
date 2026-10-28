# counter cache capacity (counter_cache_size == 0 gate in getCachedCounter) — verification solution  <!-- file: cases/counter_cache_size-getcachedcounter-capacity--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the if statement: [`ColumnFamilyStore.java:2501`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L2501) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI, 2026-10-27 |
| Estimate | `positive`: on-heap counter-cache usage is bounded by the capacity (Caffeine `maximumWeight`), and capacity 0 turns the cache off; the check itself is only the "disabled" gate on lookups. |
| Ground | — |

**Type:** non-config (hard-coded constant). The compared value is `counterCache.getCapacity()`, which comes from the yaml entry `counter_cache_size` (or JMX `setCounterCacheCapacityInMB`), but it is compared against the numeric literal `0L`, so the constant rule applies (config entry + literal `0L`).

## A. Constraint trace

**A1. The constraint.** Name: counter cache capacity (`counter_cache_size`); kind: configuration entry (yaml) compared with a literal `0L` at the check. Declared at [`Config.java:480`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L480) (`LongMebibytesBound counter_cache_size = null`, replaces `counter_cache_size_in_mb`). Literal: `0L` at the target line, no named constant. Unit: MiB in yaml, bytes in `getCapacity()`. Default: empty/null = auto, `min(max(1, 2.5% of totalMemory in MiB), 50)` at `DatabaseDescriptor.java:834-836`; negative values rejected (`:838`). Settable: yaml `counter_cache_size` (restart), JMX/nodetool `setCounterCacheCapacityInMB` at runtime (`CacheService.java:344-350`, negative rejected). Value flows to the cache at `CacheService.java:172-185` (`capacity = MiB*1024*1024`, `CaffeineCache.create(capacity)`).

**A2. What it caps.** Heap (on-heap Caffeine cache of `CounterCacheKey` -> `ClockAndCount`). The check compares the cache's maximum weight in bytes (`InstrumentingCache.getCapacity()` at `InstrumentingCache.java:77`, delegating to `CaffeineCache.capacity()` = `policy.getMaximum()`, `CaffeineCache.java:72`) with 0. Entry weight is `key.unsharedHeapSize() + value.unsharedHeapSize()` (`CaffeineCache.java:63-69`). The real cap is the Caffeine `maximumWeight` (`CaffeineCache.java:54`); this `if` is the gate that skips lookup when the maximum is 0.

**A3. Mechanism.** Method `ColumnFamilyStore.getCachedCounter` ([`ColumnFamilyStore.java:2501`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L2501)).
1. If `getCapacity() == 0L`: return `null` (a miss), no key built, no lookup.
2. Otherwise build `CounterCacheKey` and `counterCache.get(...)`.
Sole caller: `CounterMutation.java:249` (`updateWithCurrentValuesFromCache`), reached only when `counterCache.getCapacity() != 0` at `CounterMutation.java:213`; sibling gate in `putCachedCounter` at `ColumnFamilyStore.java:2508`, caller `CounterMutation.java:239`. When capacity is 0 no puts occur, so the cache stays empty. When capacity > 0, puts insert and Caffeine evicts to stay under max weight. Overshoot: Caffeine eviction is asynchronous in general, but the executor is `ImmediateExecutor` (`CaffeineCache.java:56`), so maintenance is run inline; weights are estimates of heap (`unsharedHeapSize`), so true heap can differ from the weighted size. Runtime `setCapacity` shrinks the maximum and Caffeine evicts down.

**A4. Other consumers.** Heap shared with memtables, key/row caches, paxos cache; counter writes also hold the striped counter lock and read from sstables on a miss (`CounterMutation.updateWithCurrentValuesFromCFS`). Saved-cache files on disk (`saved_caches_directory`) hold keys only (`CounterCacheSerializer`), outside this cap.

**A5. Evidence beyond the source.** `conf/cassandra.yaml:585-595` describes the setting ("Set to 0 to disable counter cache"; only the local (clock,count) tuple is cached). No other evidence relied on.

## B. Verification solution

**B1. Claim under test.** Counter-cache heap usage is bounded by the capacity: with `counter_cache_size = 0` the cache stays empty and `getCachedCounter` returns null without lookup, and with a small non-zero capacity the weighted size never exceeds it by more than a small slack while the entry count plateaus.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant, copy of the tag built outside the shared tree (`rsync -a` to a private dir, `ant jar`). A small JUnit test under `test/unit/org/apache/cassandra/cache/` in the private copy; run with `ant testsome -Dtest.name=<Class>`. JVM options: default test options, `-Xmx512m`.

**B2b. Knobs.** Capacity via `CacheService.instance.setCounterCacheCapacityInMB(n)` for n in {0, 1, 4}; the literal `0L` is not variable, so the two arms differ in the capacity (0 vs non-zero), which is the one condition that flips the branch.

**B2c. Workload.** Create a table with a counter column, then call `cfs.putCachedCounter(...)` for N distinct partition keys with `ClockAndCount.create(i, i)`, N = 200,000. Entry weight is roughly 100-150 bytes (`CounterCacheKey.EMPTY_SIZE` plus key bytes plus `ClockAndCount` size), so 1 MiB holds on the order of 7,000-10,000 entries; N far exceeds it for n=1 and n=4. Then call `getCachedCounter` for all keys.

**B2d. Observables and instruments.** `CacheService.instance.counterCache.weightedSize()`, `.size()`, `.getCapacity()`, return value of `getCachedCounter` (null or not). Cannot observe true heap per entry directly; `ObjectSizes` / a heap histogram (`jmap -histo`) can cross-check.

**B2e. Procedure.** 1) Set capacity n. 2) Run the put loop. 3) Record `size()`, `weightedSize()`. 4) Run the get loop and count non-null returns. 5) Repeat for each n, clearing the cache between runs (`counterCache.clear()`).

**B2f. Predictions.** n=0: `size()==0`, `weightedSize()==0`, all gets return null. n=1: `weightedSize() <= 1,048,576` (plus small slack), `size()` far below N, only recently used keys hit. n=4: `weightedSize() <= 4,194,304`, `size()` about 4x the n=1 value.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| weightedSize <= capacity for n=1,4; size scales with n; n=0 empty | claim confirmed |
| weightedSize far above capacity | claim refuted (cap not enforced) |
| n=0 yet size > 0 or gets return non-null | gate/put-gate not effective, refuted |
| N too small to reach capacity | not confirmed, raise N |

**B2h. Controls.** Same keys and table for all n; repeat with n=0 to confirm the gate returns null even after previously cached entries are cleared.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, build the tag in a private dir, private data/commitlog/saved_caches directories, `-Xms2g -Xmx2g`. `counter_cache_size` set in `cassandra.yaml`.

**B3b. Knobs.** `counter_cache_size` = `0MiB`, `1MiB`, `8MiB`, each in a fresh node start (restart needed); optionally runtime change via `nodetool setcachecapacity <key> <row> <counter>`.

**B3c. Workload.** Table `ks.c (id bigint primary key, v counter)`; `cassandra-stress` or a driver script issuing `UPDATE ks.c SET v = v + 1 WHERE id = ?` over 2,000,000 distinct ids, then a second pass over the same ids; each entry about 100-150 B so 2M ids is about 200-300 MB uncapped, far above 8 MiB.

**B3d. Observables and instruments.** `nodetool info` (counter cache entries, size, capacity, hit rate), JMX `org.apache.cassandra.metrics:type=Cache,scope=CounterCache,name=Size/Entries/Capacity/HitRate`, `jcmd <pid> GC.class_histogram` for `CounterCacheKey`/`ClockAndCount` instance bytes, sampled after each pass.

**B3e. Procedure.** 1) Start node with capacity c. 2) Run pass 1 and pass 2. 3) Record the metrics and histogram. 4) Stop the node, check no process remains, delete private dirs. Repeat for each c.

**B3f. Predictions.** c=0: Entries=0, hit rate 0, histogram shows ~0 `CounterCacheKey` instances. c=1MiB: Size <= 1 MiB, Entries about 7-10k, hit rate low on pass 2. c=8MiB: Size <= 8 MiB, Entries about 8x, hit rate higher but still partial.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Size tracks and stays under capacity, histogram bytes proportional to capacity | claim confirmed |
| Histogram bytes or Size grow with workload despite capacity | claim refuted |
| c=0 shows entries | gate ineffective, refuted |
| Entries never reach capacity | not confirmed, increase ids |

**B3h. Controls.** Same workload and heap each run; run a GC (`jcmd GC.run`) before each histogram; compare against c=0 baseline.

**B4. Risks and cleanup.** Disk: counter cache keys saved to private `saved_caches` only; use small dirs under private scratch, remove them after. Stop every Cassandra/cassandra-stress process and confirm with `pgrep -f cassandra`. Never build in the shared tree.

## C. Sources read

- src/java/org/apache/cassandra/db/ColumnFamilyStore.java (2470-2530)
- src/java/org/apache/cassandra/service/CacheService.java
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (831-880)
- src/java/org/apache/cassandra/config/Config.java (479-480)
- src/java/org/apache/cassandra/cache/CaffeineCache.java
- src/java/org/apache/cassandra/cache/InstrumentingCache.java
- src/java/org/apache/cassandra/db/CounterMutation.java (205-255)
- conf/cassandra.yaml (585-596)

## D. Stage-4 feedback

`none yet`
