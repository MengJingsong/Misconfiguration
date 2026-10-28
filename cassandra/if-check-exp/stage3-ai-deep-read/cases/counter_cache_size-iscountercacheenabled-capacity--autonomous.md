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

## B-audit. Stage-4 design-audit amendments (2026-10-27)

Applied by the stage-4 audit session on 2026-10-27, before any reading of the frozen run, next to the text they change (B2/B3 sections above stay as filed; where an item below makes a statement exact, the item governs). The claim (B1) and the prediction lines (B2f, B3f) are not changed except where an item says "made numeric" or "adds". The sha256 of this file after these amendments is recorded in `stage4-runtime-verification/results/counter_cache_size-iscountercacheenabled-capacity--autonomous.md` section 1. A shakedown of both tiers ran before the freeze (small N, output deleted, not a reading); it is the source of the calibrated entry weight (120 B) below.

**B2i. Unit tier.**
1. *Instrument.* One JUnit class, `CounterCacheCapTest` (copied to `test/unit/org/apache/cassandra/db/` of a private copy; source in `stage4-runtime-verification/harness/<this file's stem>/`), run with `ant testsome -Dtest.name=org.apache.cassandra.db.CounterCacheCapTest` on `tree-base` (unpatched) and on `tree-noguard` (item 6). The test JVM is the harness default (max heap about 1 GiB).
2. *Knob values.* B2b's {0, 1, 4} MiB gain a fourth arm `init`: the unit yaml's auto default, left as `CacheService` built it (2.5 % of the test JVM's total memory, 25 MiB), so the default is among the values. Arm order: init, 0, 1, 4, 4 (the repeat of 4 is the warm-up control). Capacity is set with `CacheService.instance.setCounterCacheCapacityInMB(n)`; the cache is invalidated between arms.
3. *Workload size.* N = max(200,000, 4 x capacity / entry weight), so every arm, the default included, is driven to four times its capacity. The entry weight (`key.unsharedHeapSize() + value.unsharedHeapSize()`, int partition key, one clustering value) is printed as `entryWeight` (120 B in the shakedown).
4. *Slack and ratios.* "Plus small slack" is defined as zero: `weightedSize <= capacity` at the immediate reading and at the settled reading. "Reaches the cap" means `weightedSize >= capacity - 2 x entryWeight`. "Size about 4x" means a ratio of 3.6 to 4.4 between the 4 MiB and 1 MiB arms.
5. *Production path.* A part `U3` drives the real write path (`CounterMutation.apply`, which passes the gates at `CounterMutation.java:213`, `ColumnFamilyStore.java:2501` and `:2508`) with 60,000 updates to distinct partitions at capacities 0, 1 and 4 MiB. Prediction: at 0, `size() == 0`; at 1 and 4, `weightedSize <= capacity` and the cache reaches the cap. Regular-table control: 20,000 plain inserts at 4 MiB leave the counter cache empty and `isCounterCacheEnabled()` false.
6. *Patched-literal arm (the literal cannot be varied by configuration).* `tree-noguard` is a second private copy that differs in exactly the three literals: `ColumnFamilyStore.java:2501` and `:2508` changed to `if (false)` (the `== 0L` guards removed) and `:3269` changed to `getCapacity() >= 0` (the helper no longer treats capacity 0 as disabled). The same test runs on it. Prediction, from the code and stated before it runs: on `tree-noguard` the helper is true at capacity 0, but the cache still retains nothing at capacity 0 after puts (`size() == 0`, `weightedSize() == 0`), because Caffeine's `maximumWeight(0)` evicts every entry. So the bound on usage comes from the weight cap; the literal decides only whether the key objects are built and looked up. If `tree-noguard` retains entries at capacity 0, the literal itself bounds usage and B1 is read accordingly.
7. *Direct evidence that the disallow branch fired.* In part `U2`, the thread's allocated bytes per call (`ThreadMXBean.getThreadAllocatedBytes`) are recorded for the `putCachedCounter` and the `getCachedCounter` loops (`putAllocPerCall`, `getAllocPerCall`). Prediction: on `tree-base` at capacity 0 a call builds no `CounterCacheKey` (no key object, no composite cell name), so its allocation is at least 100 B per call lower than on `tree-base` at 1 MiB and than on `tree-noguard` at capacity 0 (key 32 B plus two byte arrays plus the composite buffer).
8. *Heap.* `heapDelta` is the used heap after three `System.gc()` calls minus the same reading before the puts; it is the real-resource cross-check, expected to exceed `weightedSize` (the weigher omits Caffeine's node and map entry). No threshold is put on it except the cap-0 row where one is stated in B2f below.
9. *Why a reload test is added to the unit tier.* B2c puts straight into `counterCache`, which does not go through `isCounterCacheEnabled()`; the helper's disallow branch is reached only by the reload. Part `U4`: after the 4 MiB production-path fill and a `submitWrite(Integer.MAX_VALUE)`, `loadSaved()` is called at capacities 0, 1, 4, 0 and init. Prediction: at 0 the helper is false and `loadSaved()` returns 0 and the cache stays empty; at 1 and 4 the helper is true, `loadSaved()` returns the number of saved keys (34,952, the size at save time) and `weightedSize <= capacity` (1 MiB holds 8,738 of them); at init the helper is true. On `tree-noguard` at 0 the helper is true, `loadSaved()` returns a positive count, and `weightedSize` is still 0. `U1` also records `isCounterCacheEnabled()` for the counter table and for the regular table at every capacity; B2f's n=0 and n=1 helper lines are read from it (regular table false at all capacities).

**B3i. Cluster tier.**
1. *Node.* One node on loopback `127.39.9.1` (tag `cc`), JMX 7439, built from the private copy `tree-base`; heap `-Xms2G -Xmx2G` (G1); data, commit log, hints and saved caches in a private directory on the node's local disk (`~/s4-cc/node`, removed afterwards; never under `/proj`); `row_cache_size: 0MiB`, `key_cache_size` default, `counter_cache_save_period: 3600s`, `auto_snapshot: false`. A fresh node directory per arm (the reload arms excepted).
2. *Workload tool.* `cassandra-stress counter_write` (no driver needed). It creates `keyspace1.counter1` with five counter columns and each operation updates all five of a key's counters; the cache key includes the column, so **each key makes five cache entries**. Pass 1: `counter_write n=600000 no-warmup -pop seq=1..600000 -rate threads=64` = 3,000,000 distinct entries offered (about 343 MiB of weight at 120 B). Pass 2: the last 50,000 keys of pass 1 once more (`-pop seq=550001..600000`, 250,000 entries). The tool's `-pop dist=uniform(...)` form stalled for this operation in the shakedown and is not used. The filed table shape (`id bigint, c counter`) and the 2,000,000-id count are replaced by this (the tool cannot create the filed table).
3. *Knob values.* B3b's {0, 1 MiB, 8 MiB} gain `64MiB` and the unset default (`counter_cache_size:` empty; on a 2 GiB heap the auto size is `min(max(1, 2.5 % of 2048), 50)` = 50 MiB, read from the init log), so the default is among the values. Arms: `c0 c1 c8 c64 cdef`, a repeat `c8b`, and a runtime change `rt64` (start 64 MiB, pass 1, JMX attribute `CounterCacheCapacityInMB` = 8, pass 2).
4. *Instruments.* The gauges `org.apache.cassandra.metrics:type=Cache,scope=CounterCache,name=Size|Capacity|Entries|Hits|Requests` are read over JMX every 10 s (`Jmx.java`; `nodetool info` prints rounded sizes and is not used for numbers). A class histogram (`jcmd GC.class_histogram`, which forces a full GC) and `jcmd GC.heap_info` (used heap right after) are taken at t0, every 60 s and at the end of each pass. `Size` is the weigher's byte sum; `Entries` is the map size.
5. *Real resource.* The histogram rows `CounterCacheKey` and `ClockAndCount` (32 B each per entry) are the "two classes" of B3f. The key's two byte arrays and Caffeine's node (`PSMW`, 40 B) cannot be attributed from a histogram (all `byte[]` are one row), so they are reported separately; the real-resource reading is the whole-heap figure (`GC.heap_info` used heap minus the `c0` arm's reading at the same phase). "Within ~2x of Size" is read as (bytes of `CounterCacheKey` + `ClockAndCount`) / `Size` in [0.5, 2.0].
6. *Predictions made numeric* (entry weight 120 B). Entries at the cap: 1 MiB 8,738 (inside the file's 7,000 to 10,000); 8 MiB 69,905 (8x the 1 MiB arm, accepted 7.2 to 8.8x); 64 MiB 559,240; default 50 MiB 436,906. `Size <= Capacity` at every sample, and `Size >= Capacity - 2 x 120` at the end of pass 1 in every non-zero arm. Pass-2 hit rate = (Hits at end of pass 2 minus Hits at end of pass 1) / (Requests delta); "low" for 1 MiB means at most 20 % and below the 8 MiB arm's; "higher but still partial" for 8 MiB means above the 1 MiB arm's and below 100 %.
7. *Process check and cleanup.* Per-arm stop condition: both passes done with 0 stress errors. The node is stopped by PID (`nodetool drain`, then SIGTERM). "No process left" is checked with `ps -eo cmd | grep '[C]assandraDaemon'` run on the node itself (not `pgrep -f`, which matches its own shell). The node directory and private source copies are removed afterwards.

8. *Reload arms (this file's gate).* The helper's only caller is the start-up reload of the saved cache (`CounterCacheSerializer.deserialize`, `CacheService.java:382`), so B3e's restart step is made concrete and varied: arm `sv8` (start 8 MiB, pass 1, `nodetool flush`, JMX `saveCaches`, copy `saved_caches`, stop with the data kept), then arms `rl0`, `rl1`, `rl8` restart the same data directory with the saved file restored and `counter_cache_size` 0, 1 and 8 MiB, no writes, sampled for 30 s after the node is up. Predictions (from `AutoSavingCache.java:199-290`, `CacheService.java:382`): `rl0` the helper is false for the counter table, nothing is submitted, `Entries` and `Size` stay 0 at every sample and the histogram has no `CounterCacheKey`; `rl1` `Entries` = 8,738 and `Size <= 1 MiB` (the saved file holds about 69,905 keys, more than fit); `rl8` `Entries` = 69,905 (at most the capacity's worth). Regular-table control `r8` (start 8 MiB, `cassandra-stress write n=300000` into `keyspace1.standard1`): `Entries` and `Size` stay 0 and the histogram has no `CounterCacheKey` (the `isCounter` conjunct, B3h).

**B2g additions (rows the filed table lacks).**

| Observation | Meaning |
|---|---|
| `U4` reload at capacity 0 returns a positive count or leaves entries | the `> 0` gate does not stop the reload; claim wrong for the gate |
| `U4` reload at 1 or 4 MiB leaves `weightedSize` above capacity | cap does not bind on the reload path; claim refuted |
| `tree-noguard` retains entries at capacity 0 | the literal itself bounds usage (B1's last sentence holds in full) |
| `tree-noguard` retains nothing at capacity 0 | usage is bounded by the weight cap; the literal is only the on/off gate (consistent with the estimate's reasoning) |

**B3g additions.**

| Observation | Meaning |
|---|---|
| `rl0`: `Entries` > 0 at any sample, or `CounterCacheKey` instances > 0 | the `> 0` gate does not stop the reload; claim wrong for the gate |
| `rl1` or `rl8`: `Size` above capacity, or `Entries` above the capacity's worth | cap does not bind on the reload path; claim refuted |
| `r8`: `Entries` > 0 | the `isCounter` conjunct is not effective |
| whole-heap increase over `c0` does not follow `Size` across 1/8/64 MiB (not proportional, within 1.5x to 3x) | counter cache is bounded but the real heap is not proportional; report as overshoot, claim holds for the weighted size only |

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

**Stage 4, run 2026-10-27 (pc39, one joint run with the two sibling `counter_cache_size` files; results [`results/counter_cache_size-iscountercacheenabled-capacity--autonomous.md`](../../stage4-runtime-verification/results/counter_cache_size-iscountercacheenabled-capacity--autonomous.md)).** Verdict: **unit Confirmed, cluster Confirmed; Effect on the constraint: caps; Outcome class: true positive** (estimate `positive`, effect `caps`).
- Numbers. Unit: `isCounterCacheEnabled()` false for both tables at 0 and true for the counter table only at 1, 4 and the 25 MiB unit default; `weightedSize` 0 / 1,048,560 / 4,194,240 (8,738 and 34,952 entries, ratio 4.000), never above capacity. Reload (the helper's only caller, `CacheService.java:382`): at 0 `loadSaved()` returned 0 and nothing was cached; at 1 and 4 MiB it returned all 34,952 saved keys and the cache held 8,738 and 34,952. Cluster (`counter_write`, 3,000,000 entries offered, 2 GiB heap): `Size` 1,048,560 / 8,388,600 / 67,108,800 / 52,428,720 (default 50 MiB), within 80 B of the caps; `Entries` 8,738 / 69,905 / 559,240 / 436,906; 0 MiB: 0 everywhere; reload of a 69,905-key saved file: 0 / 8,738 / 69,905 entries at 0 / 1 / 8 MiB; regular-table writes left the cache empty. Real heap: whole-heap increase 1.78 to 2.06 x `Size` (the weigher omits Caffeine's node and the map entry).
- The literal's own role (patched copy with the helper `>= 0` and the two sibling guards removed): the helper becomes true at capacity 0 and the reload submits all 34,952 keys, but the cache still holds nothing (Caffeine's `maximumWeight(0)`). So B1's last sentence ("flipping capacity ... flips both the helper and the footprint") is true of the knob, but the footprint bound comes from the weight cap, not from the `> 0` test; the helper only decides whether a saved key is reloaded.
- Amendments applied by the audit (section "B-audit", dated 2026-10-27): defaults added to the knob values, numeric definitions of slack/ratios, the reload test (the helper is not on the path of the filed direct puts), the patched-literal arm, workload via `counter_write` (five cache entries per key; `-pop dist=uniform` stalls), JMX `saveCaches` instead of a nonexistent `drainsave`, `ps | grep '[C]assandraDaemon'` instead of `pgrep -f`.
- For stage 3: the estimate and claim hold; note that direct puts into the cache do not exercise this helper, and that the cache key includes the column (5 counters = 5 entries per row).
