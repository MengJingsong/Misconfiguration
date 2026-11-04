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

## B-audit. Stage-4 design-audit amendments (2026-10-27)

Applied by the stage-4 audit session on 2026-10-27, before any reading of the frozen run, next to the text they change (B2/B3 sections above stay as filed; where an item below makes a statement exact, the item governs). The claim (B1) and the prediction lines (B2f, B3f) are not changed except where an item says "made numeric" or "adds". The sha256 of this file after these amendments is recorded in `stage4-runtime-verification/results/counter_cache_size-getcachedcounter-capacity--autonomous.md` section 1. A shakedown of both tiers ran before the freeze (small N, output deleted, not a reading); it is the source of the calibrated entry weight (120 B) below.

**B2i. Unit tier.**
1. *Instrument.* One JUnit class, `CounterCacheCapTest` (copied to `test/unit/org/apache/cassandra/db/` of a private copy; source in `stage4-runtime-verification/harness/<this file's stem>/`), run with `ant testsome -Dtest.name=org.apache.cassandra.db.CounterCacheCapTest` on `tree-base` (unpatched) and on `tree-noguard` (item 6). The test JVM is the harness default (max heap about 1 GiB).
2. *Knob values.* B2b's {0, 1, 4} MiB gain a fourth arm `init`: the unit yaml's auto default, left as `CacheService` built it (2.5 % of the test JVM's total memory, 25 MiB), so the default is among the values. Arm order: init, 0, 1, 4, 4 (the repeat of 4 is the warm-up control). Capacity is set with `CacheService.instance.setCounterCacheCapacityInMB(n)`; the cache is invalidated between arms.
3. *Workload size.* N = max(200,000, 4 x capacity / entry weight), so every arm, the default included, is driven to four times its capacity. The entry weight (`key.unsharedHeapSize() + value.unsharedHeapSize()`, int partition key, one clustering value) is printed as `entryWeight` (120 B in the shakedown).
4. *Slack and ratios.* "Plus small slack" is defined as zero: `weightedSize <= capacity` at the immediate reading and at the settled reading. "Reaches the cap" means `weightedSize >= capacity - 2 x entryWeight`. "Size about 4x" means a ratio of 3.6 to 4.4 between the 4 MiB and 1 MiB arms.
5. *Production path.* A part `U3` drives the real write path (`CounterMutation.apply`, which passes the gates at `CounterMutation.java:213`, `ColumnFamilyStore.java:2501` and `:2508`) with 60,000 updates to distinct partitions at capacities 0, 1 and 4 MiB. Prediction: at 0, `size() == 0`; at 1 and 4, `weightedSize <= capacity` and the cache reaches the cap. Regular-table control: 20,000 plain inserts at 4 MiB leave the counter cache empty and `isCounterCacheEnabled()` false.
6. *Patched-literal arm (the literal cannot be varied by configuration).* `tree-noguard` is a second private copy that differs in exactly the three literals: `ColumnFamilyStore.java:2501` and `:2508` changed to `if (false)` (the `== 0L` guards removed) and `:3269` changed to `getCapacity() >= 0` (the helper no longer treats capacity 0 as disabled). The same test runs on it. Prediction, from the code and stated before it runs: on `tree-noguard` the helper is true at capacity 0, but the cache still retains nothing at capacity 0 after puts (`size() == 0`, `weightedSize() == 0`), because Caffeine's `maximumWeight(0)` evicts every entry. So the bound on usage comes from the weight cap; the literal decides only whether the key objects are built and looked up. If `tree-noguard` retains entries at capacity 0, the literal itself bounds usage and B1 is read accordingly.
7. *Direct evidence that the disallow branch fired.* In part `U2`, the thread's allocated bytes per call (`ThreadMXBean.getThreadAllocatedBytes`) are recorded for the `putCachedCounter` and the `getCachedCounter` loops (`putAllocPerCall`, `getAllocPerCall`). Prediction: on `tree-base` at capacity 0 a call builds no `CounterCacheKey` (no key object, no composite cell name), so its allocation is at least 100 B per call lower than on `tree-base` at 1 MiB and than on `tree-noguard` at capacity 0 (key 32 B plus two byte arrays plus the composite buffer).
8. *Heap.* `heapDelta` is the used heap after three `System.gc()` calls minus the same reading before the puts; it is the real-resource cross-check, expected to exceed `weightedSize` (the weigher omits Caffeine's node and map entry). No threshold is put on it except the cap-0 row where one is stated in B2f below.
9. *Reading of the gate.* `getCachedCounter` is reached only from `CounterMutation.updateWithCurrentValuesFromCache` (after the `!= 0` test at `CounterMutation.java:213`); in the unit test it is called directly. B2c's "then call `getCachedCounter` for all keys" is made exact: the loop counts non-null returns (`getHits`) and records whether the first and the last key hit. Prediction: n=0 `getHits` 0; n=1 and n=4 `getHits == size()` (the recent keys hit, the first key misses, the last hits).

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

- src/java/org/apache/cassandra/db/ColumnFamilyStore.java (2470-2530)
- src/java/org/apache/cassandra/service/CacheService.java
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (831-880)
- src/java/org/apache/cassandra/config/Config.java (479-480)
- src/java/org/apache/cassandra/cache/CaffeineCache.java
- src/java/org/apache/cassandra/cache/InstrumentingCache.java
- src/java/org/apache/cassandra/db/CounterMutation.java (205-255)
- conf/cassandra.yaml (585-596)

## D. Stage-4 feedback

**Stage 4, run 2026-10-27 (pc39, one joint run with the two sibling `counter_cache_size` files; results [`results/counter_cache_size-getcachedcounter-capacity--autonomous.md`](../../stage4-runtime-verification/results/counter_cache_size-getcachedcounter-capacity--autonomous.md)).** Verdict: **unit Confirmed, cluster Confirmed; Effect on the constraint: caps; Outcome class: true positive** (estimate `positive`, effect `caps`).
- Numbers. Unit: `weightedSize` 0 / 1,048,560 / 4,194,240 at 0 / 1 / 4 MiB (size 0 / 8,738 / 34,952, ratio 4.000), never above capacity; at 0 `getCachedCounter` returned null for all 200,000 keys, at 1 and 4 MiB non-null only for the cached recent keys. Allocation per `getCachedCounter` call: 72 B at capacity 0, 299 B at 1 MiB, 296 B with the guard removed (the key is built and looked up only when the guard does not fire). Cluster (`counter_write`, 3,000,000 entries offered): `Size` 1,048,560 / 8,388,600 / 67,108,800 / 52,428,720 (default 50 MiB), within 80 B of the caps, `Entries` 8,738 / 69,905 / 559,240 / 436,906; 0 MiB: `Entries` 0, `Hits` 0, `Requests` 0 (3,250,000 in the non-zero arms). Pass-2 hit rate 0.0 / 0.0345 (1 / 8 MiB), not monotone overall (TinyLFU keeps the first-admitted entries). Real heap 1.78 to 2.06 x `Size`.
- The guard's own role: with the `== 0L` guards removed (patched copy) capacity 0 still retains nothing; the guard only skips key construction and lookup. On the real path the guard at line 2501 is not reached at capacity 0, because `CounterMutation.java:213` (`getCapacity() != 0`) already skips `updateWithCurrentValuesFromCache`; the unit tier is the only place its branch is observed, and on the real path it matters only if the capacity is changed between the two checks.
- Amendments applied by the audit ("B-audit", 2026-10-27): default and 64 MiB added, numeric slack/ratios, allocation-per-call and patched-literal arm, production-path and regular-table controls, workload via `counter_write` (five entries per key), process check via `ps`.
- For stage 3: the estimate and claim hold; the hit-rate wording of B3f is not a dose-response measure here.
