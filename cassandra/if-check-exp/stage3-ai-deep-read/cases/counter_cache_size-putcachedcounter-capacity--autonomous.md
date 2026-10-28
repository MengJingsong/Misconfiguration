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

## B-audit. Stage-4 design-audit amendments (2026-10-27)

Applied by the stage-4 audit session on 2026-10-27, before any reading of the frozen run, next to the text they change (B2/B3 sections above stay as filed; where an item below makes a statement exact, the item governs). The claim (B1) and the prediction lines (B2f, B3f) are not changed except where an item says "made numeric" or "adds". The sha256 of this file after these amendments is recorded in `stage4-runtime-verification/results/counter_cache_size-putcachedcounter-capacity--autonomous.md` section 1. A shakedown of both tiers ran before the freeze (small N, output deleted, not a reading); it is the source of the calibrated entry weight (120 B) below.

**B2i. Unit tier.**
1. *Instrument.* One JUnit class, `CounterCacheCapTest` (copied to `test/unit/org/apache/cassandra/db/` of a private copy; source in `stage4-runtime-verification/harness/<this file's stem>/`), run with `ant testsome -Dtest.name=org.apache.cassandra.db.CounterCacheCapTest` on `tree-base` (unpatched) and on `tree-noguard` (item 6). The test JVM is the harness default (max heap about 1 GiB).
2. *Knob values.* B2b's {0, 1, 4} MiB gain a fourth arm `init`: the unit yaml's auto default, left as `CacheService` built it (2.5 % of the test JVM's total memory, 25 MiB), so the default is among the values. Arm order: init, 0, 1, 4, 4 (the repeat of 4 is the warm-up control). Capacity is set with `CacheService.instance.setCounterCacheCapacityInMB(n)`; the cache is invalidated between arms.
3. *Workload size.* N = max(200,000, 4 x capacity / entry weight), so every arm, the default included, is driven to four times its capacity. The entry weight (`key.unsharedHeapSize() + value.unsharedHeapSize()`, int partition key, one clustering value) is printed as `entryWeight` (120 B in the shakedown).
4. *Slack and ratios.* "Plus small slack" is defined as zero: `weightedSize <= capacity` at the immediate reading and at the settled reading. "Reaches the cap" means `weightedSize >= capacity - 2 x entryWeight`. "Size about 4x" means a ratio of 3.6 to 4.4 between the 4 MiB and 1 MiB arms.
5. *Production path.* A part `U3` drives the real write path (`CounterMutation.apply`, which passes the gates at `CounterMutation.java:213`, `ColumnFamilyStore.java:2501` and `:2508`) with 60,000 updates to distinct partitions at capacities 0, 1 and 4 MiB. Prediction: at 0, `size() == 0`; at 1 and 4, `weightedSize <= capacity` and the cache reaches the cap. Regular-table control: 20,000 plain inserts at 4 MiB leave the counter cache empty and `isCounterCacheEnabled()` false.
6. *Patched-literal arm (the literal cannot be varied by configuration).* `tree-noguard` is a second private copy that differs in exactly the three literals: `ColumnFamilyStore.java:2501` and `:2508` changed to `if (false)` (the `== 0L` guards removed) and `:3269` changed to `getCapacity() >= 0` (the helper no longer treats capacity 0 as disabled). The same test runs on it. Prediction, from the code and stated before it runs: on `tree-noguard` the helper is true at capacity 0, but the cache still retains nothing at capacity 0 after puts (`size() == 0`, `weightedSize() == 0`), because Caffeine's `maximumWeight(0)` evicts every entry. So the bound on usage comes from the weight cap; the literal decides only whether the key objects are built and looked up. If `tree-noguard` retains entries at capacity 0, the literal itself bounds usage and B1 is read accordingly.
7. *Direct evidence that the disallow branch fired.* In part `U2`, the thread's allocated bytes per call (`ThreadMXBean.getThreadAllocatedBytes`) are recorded for the `putCachedCounter` and the `getCachedCounter` loops (`putAllocPerCall`, `getAllocPerCall`). Prediction: on `tree-base` at capacity 0 a call builds no `CounterCacheKey` (no key object, no composite cell name), so its allocation is at least 100 B per call lower than on `tree-base` at 1 MiB and than on `tree-noguard` at capacity 0 (key 32 B plus two byte arrays plus the composite buffer).
8. *Heap.* `heapDelta` is the used heap after three `System.gc()` calls minus the same reading before the puts; it is the real-resource cross-check, expected to exceed `weightedSize` (the weigher omits Caffeine's node and map entry). No threshold is put on it except the cap-0 row where one is stated in B2f below.
9. *Reading of the guard.* `putCachedCounter` is called from `CounterMutation.updateWithCurrentValue`; in the unit test it is called directly with `ClockAndCount.create(i, i)` and an int partition key. B2f's "heap delta ~0" at n=0 is made exact: |`heapDelta`| < 1 MiB over 200,000 calls. The key point of B2d, true retained heap per entry, is read from `heapDelta` at n=1 and 4 and reported as `heapDelta / weightedSize`.

**B2g additions (rows the filed table lacks).**

| Observation | Meaning |
|---|---|
| allocation per call on `tree-base` at capacity 0 is not at least 100 B below the 1 MiB arm and the `tree-noguard` capacity-0 arm | the disallow branch did not fire (the key was built); the gate is not what the cap-0 reading shows |
| `tree-noguard` retains entries at capacity 0 | the literal itself bounds usage |
| `tree-noguard` retains nothing at capacity 0 | usage is bounded by the weight cap; the literal is only the on/off gate (consistent with the estimate's reasoning) |
| production path `U3` at 1 or 4 MiB leaves `weightedSize` above capacity, or at 0 leaves entries | the cap or the gate fails on the real write path; claim refuted |

**B3i. Cluster tier.**
1. *Node.* One node on loopback `127.39.9.1` (tag `cc`), JMX 7439, built from the private copy `tree-base`; heap `-Xms2G -Xmx2G` (G1); data, commit log, hints and saved caches in a private directory on the node's local disk (`~/s4-cc/node`, removed afterwards; never under `/proj`); `row_cache_size: 0MiB`, `key_cache_size` default, `counter_cache_save_period: 3600s`, `auto_snapshot: false`. A fresh node directory per arm (the reload arms excepted).
2. *Workload tool.* `cassandra-stress counter_write` (no driver needed). It creates `keyspace1.counter1` with five counter columns and each operation updates all five of a key's counters; the cache key includes the column, so **each key makes five cache entries**. Pass 1: `counter_write n=600000 no-warmup -pop seq=1..600000 -rate threads=64` = 3,000,000 distinct entries offered (about 343 MiB of weight at 120 B). Pass 2: the last 50,000 keys of pass 1 once more (`-pop seq=550001..600000`, 250,000 entries). The tool's `-pop dist=uniform(...)` form stalled for this operation in the shakedown and is not used. The filed table shape (`id bigint, c counter`) and the 2,000,000-id count are replaced by this (the tool cannot create the filed table).
3. *Knob values.* B3b's {0, 1 MiB, 8 MiB} gain `64MiB` and the unset default (`counter_cache_size:` empty; on a 2 GiB heap the auto size is `min(max(1, 2.5 % of 2048), 50)` = 50 MiB, read from the init log), so the default is among the values. Arms: `c0 c1 c8 c64 cdef`, a repeat `c8b`, and a runtime change `rt64` (start 64 MiB, pass 1, JMX attribute `CounterCacheCapacityInMB` = 8, pass 2).
4. *Instruments.* The gauges `org.apache.cassandra.metrics:type=Cache,scope=CounterCache,name=Size|Capacity|Entries|Hits|Requests` are read over JMX every 10 s (`Jmx.java`; `nodetool info` prints rounded sizes and is not used for numbers). A class histogram (`jcmd GC.class_histogram`, which forces a full GC) and `jcmd GC.heap_info` (used heap right after) are taken at t0, every 60 s and at the end of each pass. `Size` is the weigher's byte sum; `Entries` is the map size.
5. *Real resource.* The histogram rows `CounterCacheKey` and `ClockAndCount` (32 B each per entry) are the "two classes" of B3f. The key's two byte arrays and Caffeine's node (`PSMW`, 40 B) cannot be attributed from a histogram (all `byte[]` are one row), so they are reported separately; the real-resource reading is the whole-heap figure (`GC.heap_info` used heap minus the `c0` arm's reading at the same phase). "Within ~2x of Size" is read as (bytes of `CounterCacheKey` + `ClockAndCount`) / `Size` in [0.5, 2.0].
6. *Predictions made numeric* (entry weight 120 B). Entries at the cap: 1 MiB 8,738 (inside the file's 7,000 to 10,000); 8 MiB 69,905 (8x the 1 MiB arm, accepted 7.2 to 8.8x); 64 MiB 559,240; default 50 MiB 436,906. `Size <= Capacity` at every sample, and `Size >= Capacity - 2 x 120` at the end of pass 1 in every non-zero arm. Pass-2 hit rate = (Hits at end of pass 2 minus Hits at end of pass 1) / (Requests delta); "low" for 1 MiB means at most 20 % and below the 8 MiB arm's; "higher but still partial" for 8 MiB means above the 1 MiB arm's and below 100 %.
7. *Process check and cleanup.* Per-arm stop condition: both passes done with 0 stress errors. The node is stopped by PID (`nodetool drain`, then SIGTERM). "No process left" is checked with `ps -eo cmd | grep '[C]assandraDaemon'` run on the node itself (not `pgrep -f`, which matches its own shell). The node directory and private source copies are removed afterwards.
8. *Regular-table control `r8`* (start 8 MiB, `cassandra-stress write n=300000` into `keyspace1.standard1`): `Entries` and `Size` stay 0 and the histogram has no `CounterCacheKey` (B3h).

**B3g additions.**

| Observation | Meaning |
|---|---|
| whole-heap increase over `c0` does not follow `Size` across 1/8/64 MiB (not within 1.5x to 3x of `Size`, proportional) | counter cache is bounded but the real heap is not proportional; report as overshoot, claim holds for the weighted size only |
| `rt64`: `Size` after the runtime change above 8 MiB | the runtime path does not lower the bound |
| `r8` (regular-table control): `Entries` > 0 | the table gate is not effective |

## C. Sources read

- src/java/org/apache/cassandra/db/ColumnFamilyStore.java (2470-2550)
- src/java/org/apache/cassandra/service/CacheService.java
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (828-846, 3949)
- src/java/org/apache/cassandra/config/Config.java (479-480)
- src/java/org/apache/cassandra/cache/CaffeineCache.java
- src/java/org/apache/cassandra/db/CounterMutation.java (232-262)
- conf/cassandra.yaml (590-596)

## D. Stage-4 feedback

**Stage 4, run 2026-10-27 (pc39, one joint run with the two sibling `counter_cache_size` files; results [`results/counter_cache_size-putcachedcounter-capacity--autonomous.md`](../../stage4-runtime-verification/results/counter_cache_size-putcachedcounter-capacity--autonomous.md)).** Verdict: **unit Confirmed, cluster Confirmed; Effect on the constraint: caps; Outcome class: true positive** (estimate `positive`, effect `caps`).
- Numbers. Unit: after 200,000 `putCachedCounter` calls `weightedSize` 0 / 1,048,560 / 4,194,240 at 0 / 1 / 4 MiB (and 26,214,360 at the 25 MiB default; size 0 / 8,738 / 34,952, ratio 4.000), never above capacity; heap delta at 0 MiB 2,752 B, at 1 and 4 MiB 1.72 and 1.76 x the weighted size. Allocation per call: 104 B at capacity 0, 837 B at 1 MiB, 720 B with the guard removed. Production path (`CounterMutation.apply`, 60,000 updates): 0 / 1,048,560 / 4,194,240. Cluster (`counter_write`, 3,000,000 entries offered): `Size` 1,048,560 / 8,388,600 / 67,108,800 / 52,428,720 (default), `Entries` 8,738 / 69,905 / 559,240 / 436,906; 0 MiB: 0 everywhere; runtime 64 -> 8 MiB: `Size` 8,388,600 from the first sample after the change and the used heap fell 89.6 MiB. Real heap 1.78 to 2.06 x `Size`; the two histogram classes are 0.533 x `Size`.
- The guard's own role: with the `== 0L` guards removed (patched copy) capacity 0 still retains nothing (Caffeine's `maximumWeight(0)`); the guard only avoids building the key (about 600 B per call less). On the real path the guard is reached at capacity 0 (`updateWithCurrentValue` calls `putCachedCounter` for every mark even when the cache read is skipped).
- Amendments applied by the audit ("B-audit", 2026-10-27): default and 64 MiB added, numeric slack/ratios (|heap delta| < 1 MiB at 0), allocation-per-call and patched-literal arm, production-path and regular-table controls, workload via `counter_write` (five entries per key), process check via `ps`.
- For stage 3: the estimate and claim hold; "histogram bytes within a modest factor" is met (two classes 0.53 x, whole heap about 2 x the weighted size).
