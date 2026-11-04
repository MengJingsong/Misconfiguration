# counter_cache_size (startup validation in applySimpleConfig) — verification solution  <!-- file: cases/counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`DatabaseDescriptor.java:838`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L838) (`838#1`, `counterCacheSizeInMiB < 0`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (claude-opus-5-5), Claude Code at Meta (version string not available in the sandbox), 2026-10-25, band D triage |
| Estimate | `positive`: the resolved value is the `maximumWeight` (bytes) of the Caffeine counter cache (`CacheService.java:174-181`), weighted by `CounterCacheKey`/`ClockAndCount` heap estimates, so counter-cache heap is capped by it. The check at line 838 is unreachable from yaml (negatives refused by the `DataStorageSpec` parser; auto value ≥ 1). |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `counter_cache_size`, configuration entry ([`Config.java:479-480`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L479-L480), `LongMebibytesBound`, default `null` = auto; legacy `counter_cache_size_in_mb`), yaml `conf/cassandra.yaml:595` (comment `:590-594`: auto = min(2.5% heap, 50MiB), 0 disables). Auto: `min(max(1, totalMemory*0.025/1MiB), 50)` ([`DatabaseDescriptor.java:834-836`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L834-L836)). Negative → `ConfigurationException` (`:838-845`), unreachable because `DataStorageSpec` rejects negatives at parse (`DataStorageSpec.java:42,72,107-108`). Written back at `:864`; getter `getCounterCacheSizeInMiB()` (`:3947-3950`). Runtime: JMX `setCounterCacheCapacityInMB` ([`CacheService.java:344-350`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/CacheService.java#L344-L350)) / `nodetool setcachecapacity`.


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../../../stage3-ai-deep-read/README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** Heap held by the counter cache. Operand: Caffeine weighted size = Σ (`CounterCacheKey.unsharedHeapSize()` = shell + partition-key array + cell-name array, `CounterCacheKey.java:152-157`) + (`ClockAndCount.unsharedHeapSize()` = shell, `ClockAndCount.java:46-49`).

**A3. Mechanism.**
1. Startup check ([`DatabaseDescriptor.java:834-845`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L834-L845)).
2. `initCounterCache`: `CaffeineCache.create(counterCacheSizeInMiB * 1024 * 1024)` ([`CacheService.java:176-181`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/CacheService.java#L176-L181); [`CaffeineCache.java:51-70`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/CaffeineCache.java#L51-L70)).
3. Each applied counter update puts the new clock/count ([`CounterMutation.java:239`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/CounterMutation.java#L239) → `ColumnFamilyStore.putCachedCounter`, [`ColumnFamilyStore.java:2506-2511`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L2506-L2511)), skipped when capacity is 0 (`:2508-2509`). Caffeine evicts above `maximumWeight`.
- Overshoot: weights are shallow estimates; eviction is amortised. Saved to disk every `counter_cache_save_period` (default 7200s, [`Config.java:481-482`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L481-L482)).

**A4. Other consumers.** Key/row/paxos caches, memtables (counter updates also land in memtables), `saved_caches_directory` on disk.

**A5. Evidence beyond the source.** `conf/cassandra.yaml:590-595`. Caffeine size-based eviction: https://github.com/ben-manes/caffeine/wiki/Eviction#size-based.

## B. Verification solution

**B1. Claim under test.** With `counter_cache_size: C`, the counter cache's weighted size stays ≤ C MiB and its entry count plateaus at ≈ C / (per-entry weight) once more distinct counter cells are updated than fit; usage scales with C, not with distinct counters written.

### B2. Unit tier

**B2a. Environment and build.** As in `key_cache_size-applySimpleConfig-keyCacheSizeInMiB--autonomous.md` B2a (local clone `/local/c509`, `ant jar`, `ConfigProbe` with getter `getCounterCacheSizeInMiB`, CQLTester probe `org.apache.cassandra.probe.CounterCacheCapProbeTest` run with `ant testsome -Dtest.name=…`, knob added as `counter_cache_size: <C>` to the local clone's `test/conf/cassandra.yaml`).

**Amendment 2026-10-25 (step-0 audit) — B2a, this host's paths and the run recipe.** The key-cache file's B2a that this one points to names `/local/c509` and `ant jar`; on this host: clone `C=$W/cassandra-run12` (`W=~/Library/Caches/stage4`; `git clone --branch cassandra-5.0.9 ~/cassandra-src $C`, HEAD `b5f2a54210`), built with `source $W/env.sh; ant -Dlocal.repository=$W/m2 build-test` (`testsome` needs the test classes); every `ant` call takes `-Dlocal.repository=$W/m2`. Probe directory `P=$W/probe-ccs`. `ConfigProbe` is copied unchanged from `harness/key_cache_size-applySimpleConfig-keyCacheSizeInMiB--autonomous/ConfigProbe.java` (the program that file's B2a defines) into this case's harness folder, compiled to `$P/classes`, and run with `$P` as working directory: `java -Xms1G -Xmx1G <the seventeen --add-exports/--add-opens flags of build.xml:244-261> -cp "$C/build/classes/main:$C/build/lib/jars/*:$P/classes" -Dcassandra.config=file://$P/<v>.yaml -Dcassandra.storagedir=$P/data -Dlogback.configurationFile=$C/test/conf/logback-test.xml ConfigProbe getCounterCacheSizeInMiB` (without the flags `FileUtils`' class init fails on JDK 11 before the knob is read). `base.yaml` = `$C/conf/cassandra.yaml` with the five directory keys re-pointed under `$P/data/`; the variants differ from it only in the `counter_cache_size:` line. The mechanism test `CounterCacheCapProbeTest.java` is kept in this case's harness folder and copied to `$C/test/unit/org/apache/cassandra/probe/`. Each knob value is its own `ant testsome -Dtest.name=org.apache.cassandra.probe.CounterCacheCapProbeTest` (own forked JVM), because `daemonInitialization()` runs once per JVM and `CacheService.instance` builds the counter cache once (`CacheService.java:105-113`). `test/conf/cassandra.yaml` has no `counter_cache_size` line: the knob is set by appending `counter_cache_size: <C>` (nothing appended for auto) and restored with `git checkout` after the last value. Every test JVM gets `-Dtest.jvm.args="-Xms1024m -Dstage4.out=<file> -Dstage4.label=<C>"`: `-Xms` equal to the `maxmemory="1024m"` of `build.xml:1153` fixes `Runtime.totalMemory()`, which the auto formula reads (`DatabaseDescriptor.java:834-836`). Harness: `harness/counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous/unit-run.sh`. Reason: B2a's paths do not exist on this host; the JVM split, the auto heap and the module flags were left open.

**B2b. Knobs.** ConfigProbe: `-1MiB` (parse rejection), `0MiB` (accepted, disabled), unset (auto with 1 GiB heap: `min(max(1, 25), 50) = 25`). Test: C ∈ {1MiB, 4MiB}.

**Amendment 2026-10-25 (step-0 audit) — B2b, the default and the disable value added to the test.** The test also runs with `0MiB` (the B2h disable control, which B2h names but B2b did not schedule) and with no `counter_cache_size` line (auto). Auto with `-Xms1024m`: `min(max(1, ⌊totalMemory × 0.025 / 2^20⌋), 50)` = 25 for any `totalMemory` in [1,048,576,000, 1,090,519,040) B, which contains 2^30; 24–26 accepted (B2f's ±1). Values {0MiB, 1MiB, 4MiB, auto}. With N = 300,000 and w = 112 B (B2c amendment) the auto cap (25 MiB = 26,214,400 B < 33,600,000 B) is passed too, so auto is a third eviction arm. Reason: group A asks for at least three values including the default.

**B2c. Workload.** `createTable("CREATE TABLE %s (k int PRIMARY KEY, c counter)")`; for i in 0..N-1 `execute("UPDATE %s SET c = c + 1 WHERE k = ?", i)` with N = 300 000. Per-entry weight w measured as `weightedSize()/size()` after 1000 updates (expected ≈ 100–150 B). 300 000 × ~120 B ≈ 34 MiB > 4 MiB.

**Amendment 2026-10-25 (step-0 audit) — B2c, exact workload and the per-entry weight from the source.** In each JVM: log the knob, `getCapacity()` and `totalMemory()`; `createTable("CREATE TABLE %s (k int PRIMARY KEY, c counter)")`; `CacheService.instance.counterCache.clear()` (size before the clear logged); calibration = `execute("UPDATE %s SET c = c + 1 WHERE k = ?", i)` for i = 0 … 999, then w = `weightedSize()/size()`; main series = the same update for i = 1,000 … 299,999. No flush: the read-before-write of a new cell is served by the memtable. Each update goes through `CounterMutation.applyCounterMutation` (`CounterMutation.java:129-151`), which looks each cell up in the cache when the capacity is not 0 (`:213-219`, `:243-257`) and puts the new `ClockAndCount` (`:230-240` → `ColumnFamilyStore.putCachedCounter`, `ColumnFamilyStore.java:2506-2511`). Per-entry weight derived from the source (compressed oops, 12-byte headers, 8-byte alignment, the JDK 11 defaults at ≤ 32 GiB heap): `CounterCacheKey` shell — header + `tableId`, `indexName` (`CacheKey.java:27-28`), `partitionKey`, `cellName` references — 32 B (`EMPTY_SIZE` is a shallow `MemoryMeter.measure`, `CounterCacheKey.java:46-51`, `ObjectSizes.java:251-254`); `partitionKey` = a copy of the 4-byte int key (`ByteBufferUtil.java:190-195`), `byte[4]` = 24 B; `cellName` = `CompositeType.build` of the single name `c` (2-byte length + 1 byte + end-of-component byte = 4 bytes, `CounterCacheKey.java:70-80`, `CompositeType.java:521-540`), `byte[4]` = 24 B; `ClockAndCount` (header + two longs, `ClockAndCount.java:28-49`) 32 B: **w = 112 B**. 300,000 × 112 B = 33,600,000 B = 32 × the 1 MiB cap, 8 × the 4 MiB cap, 1.28 × the auto cap.

**B2d. Observables and instruments.** `CacheService.instance.counterCache.weightedSize()`, `.size()`, `.getCapacity()` every 10 000 updates.

**Amendment 2026-10-25 (step-0 audit) — B2d, instruments.** At calibration and every 10,000 updates: `counterCache.size()`, `weightedSize()`, `getCapacity()`, own = the number of cached keys whose `tableId` is the test table's (by `keyIterator()`), and the cache metrics `requests`, `hits`, `misses` (marked by `InstrumentingCache.get`). Caffeine stats are not recorded, so evictions are inferred as N − own_final: each of the N distinct cells is put once after its first (missing) lookup and nothing else removes entries after the clear. The unit tier reads the weight, not the retained heap (gap named; the cluster tier carries the heap relation, B3f (vii)).

**B2e. Procedure.** ConfigProbe variants; then per C: edit test yaml, run, collect; restore yaml.

**Amendment 2026-10-25 (step-0 audit) — B2e, order.** ConfigProbe `-1MiB`, `0MiB`, unset, each its own `java -Xms1G -Xmx1G` process; then one test JVM per C in the order 0MiB, 1MiB, 4MiB, auto; per JVM: table → clear → calibration → main series → final line → B2h control (clear, re-update). Harness: `unit-run.sh`.

**B2f. Predictions.** ConfigProbe: `-1MiB` rejected during yaml load (not the `:843` message); `0MiB` → `OK …=0`; auto → `OK …=25` (±1). Test: capacity = C×2^20; weightedSize ≤ C×2^20 + 10w always; size() plateaus ≈ C×2^20/w, ×4 between 1MiB and 4MiB.

**Amendment 2026-10-25 (step-0 audit) — B2f, exact values (prediction unchanged in substance).** ConfigProbe: `-1MiB` → a line starting `REJECT` that contains `only non-negative values are accepted` (`DataStorageSpec.java:42,72-73`) and does not contain `counter_cache_size option was set incorrectly` (the message at `DatabaseDescriptor.java:843-844`); `0MiB` → `OK getCounterCacheSizeInMiB=0`; unset → `OK getCounterCacheSizeInMiB=25` (24–26 accepted). Test, every C: the logged `counterCacheSizeInMiB` is 0 / 1 / 4 / 25 (24–26) and `getCapacity()` = that × 2^20 exactly; w = 112 B (B2c amendment; a different w is recorded, and the relations below use the measured w). At C ∈ {1MiB, 4MiB, auto}: (i) `weightedSize()` ≤ capacity + 10w at every sample; (ii) final `size()` and own within ±10 % of capacity/w (9,362 · 37,449 · 234,057 at w = 112 B and auto = 25); (iii) N − own_final > 0 and misses during the series ≥ N − 1,000; (iv) own_final(4MiB)/own_final(1MiB) within ±10 % of 4, and own_final(auto)/own_final(1MiB) within ±10 % of the auto value in MiB. At 0MiB: B2h (b).

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| plateau ∝ C, weightedSize ≤ C | claim holds |
| size() → N with weightedSize > C | claim wrong |
| size() = 0 with C > 0 | counter path not reaching cache; setup issue |

**Amendment 2026-10-25 (step-0 audit) — B2g, rows added (the rows above are unchanged).** Row 1 ("claim holds") needs B2f (i)–(iv) at 1 MiB, 4 MiB and auto, ConfigProbe as predicted and both B2h controls as predicted. Added rows:
| Observation | Meaning |
|---|---|
| `-1MiB` accepted (OK line) | negative values pass the parser; the Estimate's note on line 838 is wrong |
| `0MiB` rejected, or auto outside 24–26, or capacity ≠ value × 2^20 | the startup value does not reach the cache as traced; Not confirmed |
| ConfigProbe fails for a reason other than the knob | ConfigProbe invalid; runbook defect |
| own ≠ 1,000 after calibration at a C > 0 | setup issue (row 3); runbook defect, not a finding |
| own plateaus but not within ±10 % of capacity/w, or not ∝ C | the weight is not the binding factor; Not confirmed |
| w ≠ 112 B while (i)–(iv) hold | claim holds; B2c's size derivation is off (note for stage 3) |
| a B2h control misses its frozen expectation | tier Invalid |

**B2h. Controls.** N = plateau/2 → size() = N; `0MiB` → size() stays 0 (`ColumnFamilyStore.java:2508`).

**Amendment 2026-10-25 (step-0 audit) — B2h, exact controls.** (a) In every JVM with C > 0, after the main series: `counterCache.clear()`, then re-update k = 0 … M − 1 with M = ⌊own_final/2⌋: expected own = M exactly and `weightedSize()` = M × w (±1 %) — each re-updated cell misses after the clear and is put, and M × w ≤ capacity/2, so nothing is evicted. (b) The `0MiB` JVM: `getCapacity()` = 0, `size()` = `weightedSize()` = 0 at every sample and at the end, and `requests` does not move (`processModifications` skips the cache when the capacity is 0, `CounterMutation.java:213`; `putCachedCounter` returns, `ColumnFamilyStore.java:2508-2509`). Reason: "N = plateau/2" did not say whether the cache starts empty, and the `0MiB` run was not scheduled.

### B3. Cluster tier

**B3a. Environment and build.** Single node as in the key-cache case B3a (`/local/run`, `MAX_HEAP_SIZE=2G`, `HEAP_NEWSIZE=400M`).

**Amendment 2026-10-25 (step-0 audit) — B3a, this host.** Clone `$W/cassandra-run12` (B2a amendment; `build-test` builds `tools/bin/cassandra-stress`; no `ant` while a node runs from it). Node directory `N=$W/node-ccs`: `conf/` copied from the clone, `cassandra.yaml` = the shipped file with the five directory keys and `counter_cache_size` removed and re-added at the end (directories under `$N/`; `counter_cache_size:` empty for auto). `CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$N/logs MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M` (`-Xms2G -Xmx2G`), started as a tracked background `bin/cassandra -f` (macOS has no `setsid`); ready when `nodetool status` shows `UN 127.0.0.1` **and** `nodetool statusbinary` prints `running`; the script fails at once if the daemon dies. Read-back: the `system.log` line `Initializing counter cache with capacity of <C> MiBs` (`CacheService.java:174`) must show 4 / 32 / 50 (auto at 2 GiB: ⌊2^31 × 0.025 / 2^20⌋ = 51 → min(51, 50) = 50, for any `totalMemory` ≥ 2,097,152,000 B). Before each lifetime `pgrep -f CassandraDaemon` is empty and ports 7000/7199/9042/9091 are free; `$N` is wiped before and after. Harness: `cluster-run.sh` (one lifetime), `cluster-chain.sh` (run 1 order, shakedown), `CounterCacheSampler.java`. Reason: B3a's paths do not exist here.

**B3b. Knobs.** `counter_cache_size` ∈ {`4MiB`, `32MiB`}; control unset (auto = min(51, 50) = 50 MiB).

**B3c. Workload.** `cassandra-stress counter_write n=3000000 -pop seq=1..3000000 -rate threads=50 -node 127.0.0.1` (stress's counter table; each partition has several counter cells, each cell one cache entry). Estimated would-be weight ≥ 3 000 000 × 120 B ≈ 340 MiB, above both caps.

**Amendment 2026-10-25 (step-0 audit) — B3c, exact commands and the per-entry weight from the source.** Stress's counter table is `keyspace1.counter1` (`key blob PRIMARY KEY` and counters `"C0"` … `"C4"`, `SettingsSchema.java:163-176`, names `SettingsColumn.java:127`); each `counter_write` op is one `UPDATE counter1 SET "C0"="C0"+?, …, "C4"="C4"+? WHERE KEY=?` (`CqlCounterAdder.java:45-60`; 5 columns, `SettingsColumn.java:170`; 10-byte key, `SettingsCommandPreDefined.java:108`), so one op touches 5 distinct counter cells = 5 cache entries. Commands, in each lifetime: the B3h control `tools/bin/cassandra-stress counter_write n=2000 no-warmup -pop seq=1..2000 -rate threads=50 -node 127.0.0.1`; then the main write `tools/bin/cassandra-stress counter_write n=3000000 no-warmup -pop seq=1..3000000 -rate threads=50 -node 127.0.0.1`; then `nodetool flush keyspace1` (empties the counter memtable before the final histogram; the cache is not touched). `no-warmup`: stress's warm-up ops would otherwise put cells before the control. Per-entry weight (B2c amendment's sizes): shell 32 B + key `byte[10]` 32 B + cell name `"C0"` composite (2 + 2 + 1 = 5 bytes) `byte[5]` 24 B + `ClockAndCount` 32 B = **w_c = 120 B**; 3,000,000 × 5 × 120 B = 1.8 GB of would-be weight, 36 × the auto cap. Disk: counter data and commit log of a few GB at most per lifetime against 149 GiB free.

**B3d. Observables and instruments.** `nodetool info | grep "Counter Cache"` every 30 s; `nodetool sjk mx -mg -b org.apache.cassandra.metrics:type=Cache,scope=CounterCache,name=Size -f Value`; at end `jmap -histo:live <pid> | grep -E 'CounterCacheKey|ClockAndCount'`.

**Amendment 2026-10-25 (step-0 audit) — B3d, instruments.** A one-connection JMX sampler (`CounterCacheSampler.java`, a copy of the key-cache harness's `KeyCacheSampler.java` with `scope=CounterCache`; port 7199) reads every 2 s, from the baseline to the end, `org.apache.cassandra.metrics:type=Cache,scope=CounterCache,name=` `Capacity`, `Size` (= `weightedSize()`, bytes), `Entries` (gauges, `Value`) and `Requests`, `Hits`, `Misses` (meters, `Count`), plus `HeapMemoryUsage.used`, each row labelled with the phase (baseline, control-write, control-done, main-write, main-done, flushed); a phase's reading is its last row. This replaces `nodetool info` every 30 s and `nodetool sjk` (a JVM per read); `nodetool info | grep 'Counter Cache'` is recorded at the baseline, after the control and at the end. `jmap -histo:live` and `jcmd GC.heap_info` at the baseline (node up, before the control) and at the end (after the flush); from the histogram: instances and bytes of `org.apache.cassandra.cache.CounterCacheKey`, `org.apache.cassandra.db.ClockAndCount`, `com.github.benmanes.caffeine.cache.PSMW`, `java.util.concurrent.ConcurrentHashMap$Node`, `[Ljava.util.concurrent.ConcurrentHashMap$Node;`, `[J`, and the live total. `jstat` cannot attach on this machine. Per-entry weight in the node: w_c = Size/Entries at main-done.

**B3e. Procedure.** Per value: wipe, set yaml, start, run stress with sampling, histo, stop, check no process left.

**Amendment 2026-10-25 (step-0 audit) — B3e, order.** Lifetimes in the order 4MiB, 32MiB, auto. Per lifetime: wipe, yaml, start, read-back, start the sampler (phase baseline), wait 6 s, `nodetool info`, baseline histogram, control write (B3h), wait 6 s, `nodetool info`, main write, wait 6 s (main-done), `nodetool flush keyspace1`, wait 6 s (flushed), final `nodetool info`, final histogram, `nodetool drain`, stop, `pgrep` empty, wipe. Before run 1 a shakedown lifetime (2MiB, main write of 100,000 partitions, control of 200 partitions) checks the harness; its readings are not used, except that its w_c is compared with the 120 B the B3f bounds assume, and any bound that depends on it is re-checked before run 1.

**B3f. Predictions.** capacity = C; size ≤ C; entries plateau ≈ C/w (w from the unit tier, adjusted for stress key length), ×8 between 4 and 32 MiB; auto run plateaus at 50 MiB capacity.

**Amendment 2026-10-25 (step-0 audit) — B3f, exact relations (prediction unchanged in substance; a real-heap relation added for group A).** At each C ∈ {4, 32, 50 (auto)} MiB: (i) the read-back line shows C and `Capacity` = C × 2^20 in every row; (ii) `Size` ≤ 1.01 × Capacity at every sample; (iii) at main-done the cache is full, `Size` ≥ 0.9 × Capacity, and `Entries` within ±10 % of Capacity / w_c; (iv) w_c = 120 B ± 2 % in every lifetime (B3c amendment); Entries(32)/Entries(4) within ±10 % of 8 and Entries(auto)/Entries(4) within ±10 % of 12.5; (v) eviction: `Misses` during the main write ≥ 0.99 × 5 × (3,000,000 − 2,000) = 14,840,100 while `Entries` at main-done ≤ 0.05 × 15,000,000; (vi) `CounterCacheKey` and `ClockAndCount` instances in the final histogram each within ±(1 % + 200) of `Entries` at the flushed phase; (vii) real heap, for the pairs (32, 4) and (auto, 4): D = live total(hi) − live total(lo) of the final histograms, S = Size(hi) − Size(lo) at main-done; **D/S within R_pred ± 0.25**, where, derived from the source: each cached entry holds the weighed objects themselves (key shell, its two arrays, the `ClockAndCount`: exactly w_c live bytes) plus two objects the weigher does not count (`CaffeineCache.java:61-70` weighs key + value only) — a Caffeine `PSMW` node, 40 B (header 12 + `key`, `value`, `previousInAccessOrder`, `nextInAccessOrder` references + `queueType`, `weight`, `policyWeight` ints; `javap -p` of `PS`/`PSMW` in `caffeine-3.1.8.jar`, the strong-key, strong-value, weighted node the builder at `CaffeineCache.java:51-58` selects) and a `ConcurrentHashMap$Node` of Caffeine's backing map, 32 B (header + `hash`, `key`, `val`, `next`) — and per cache a CHM table of 4-byte slots, length L(E) = the smallest power of two ≥ 16 with E < 0.75 L (JDK resize at `sizeCtl` = 0.75 n; Caffeine's map starts at 16), and a frequency sketch `long[T]`, T(E) = max(8, ceilPow2(E)) (`BoundedLocalCache$AddTask` calls `FrequencySketch.ensureCapacity(data.mappingCount())` once the weighted size reaches half the maximum, and `ensureCapacity` allocates `long[max(ceilingPowerOfTwo(n), 8)]`, `javap -c` of the same jar); so R_pred = [ΔE × (w_c + 72) + 4 ΔL + 8 ΔT] / ΔS with E = Entries at main-done in each lifetime. At w_c = 120 B and E = Capacity/120 (34,952 · 279,620 · 436,906; L = 65,536 · 524,288 · 1,048,576; T = 65,536 · 524,288 · 524,288): R_pred(32, 4) = 1.787, R_pred(auto, 4) = 1.758. The ± 0.25 is an allowance, set before any reading, for live heap this derivation does not count and that can differ between lifetimes (transient map and buffer state, residual memtable and system-table heap after the flush); it is not taken from another case's readings. The workload is identical across lifetimes, so other heap cancels in D.

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| size ≤ capacity, entries ∝ C | cap governs heap |
| CounterCacheKey instances ≫ C/w | cap not enforced; claim wrong |

**Amendment 2026-10-25 (step-0 audit) — B3g, rows added (the rows above are unchanged).** Row 1 ("cap governs heap") needs B3f (i)–(vii) and both B3h controls as frozen. Added rows:
| Observation | Meaning |
|---|---|
| read-back or Capacity ≠ C | knob not applied; runbook defect, re-run |
| `Size` > 1.01 × Capacity at a sample | cap not enforced at that moment; Refuted if sustained (≥ 3 consecutive samples), else Not confirmed |
| (i)–(vi) hold but (vii) fails | the cap bounds the weight, but the real heap does not follow the derived relation; Not confirmed for the heap part |
| `Size` < 0.9 × Capacity at main-done at some C | limit not reached at that C; Not confirmed |
| w_c ≠ 120 B ± 2 % while the other relations hold (with the measured w_c) | claim holds; B3c's size derivation is off (note for stage 3) |
| stress errors > 0 or fewer ops than requested | workload invalid; re-run |
| a B3h control misses its frozen expectation | tier Invalid |

**B3h. Controls.** Auto (50 MiB) run shows the same workload fills a larger cap; a run with 10 000 partitions stays below every cap.

**Amendment 2026-10-25 (step-0 audit) — B3h, exact controls.** (a) In every lifetime, after the baseline and before the main write: the 2,000-partition `counter_write` (B3c amendment, seq 1..2,000): `Entries` at baseline = 0 (no counter table exists at start; node data wiped, no saved cache) and `Entries`(control-done) − `Entries`(baseline) = 10,000 exactly (5 cells × 2,000 partitions), `Misses` during the control ≥ 10,000; 10,000 × 120 B = 1.2 MB < 4 MiB, so no eviction. B3h's "run with 10 000 partitions stays below every cap" does not: 10,000 × 5 × 120 B = 6 MB > 4 MiB. (b) The auto lifetime is the higher-cap arm of B3f (iv). Reason: the control's size, placement and expected value.

**B4. Risks and cleanup.** Counter data ≤ 1 GiB; check `df -h /local`. Stop node and stress; `pgrep -f CassandraDaemon` empty; restore local test yaml, delete probe test; `rm -rf /local/run /local/probe/data`.

## C. Sources read

src/java/org/apache/cassandra/config/DatabaseDescriptor.java (831-864, 3947-3950)
src/java/org/apache/cassandra/config/Config.java (479-485)
src/java/org/apache/cassandra/config/DataStorageSpec.java (42-108)
src/java/org/apache/cassandra/service/CacheService.java (174-195, 344-350)
src/java/org/apache/cassandra/cache/CaffeineCache.java (51-95)
src/java/org/apache/cassandra/cache/CounterCacheKey.java (46, 152-157)
src/java/org/apache/cassandra/db/ClockAndCount.java (28-49)
src/java/org/apache/cassandra/db/ColumnFamilyStore.java (2499-2511)
src/java/org/apache/cassandra/db/CounterMutation.java (239)
conf/cassandra.yaml (590-595)
https://github.com/ben-manes/caffeine/wiki/Eviction

## D. Stage-4 feedback

**2026-10-25, stage 4 run 1** (Claude Opus 5.5, claude-opus-5-5; advisor's machine; results: [`../../stage4-runtime-verification/results/counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous.md`](../../stage4-runtime-verification/results/counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous.md)). Frozen at sha256 `96274f91…48e8` after fifteen dated audit amendments (above); no runbook fix; uncommitted.
- **Unit: Confirmed — caps** (B2g row 1). `-1MiB` is refused by the parser (`Invalid data storage: -1MiB … only non-negative values are accepted`), never by line 838; `0MiB` → 0, the cache is never consulted (requests 0); auto → 25. w = 112 B as derived; own = ⌊capacity/w⌋ = 9,362 · 37,449 · 234,057 at 1 · 4 · 25 MiB (ratios 4.000, 25.001), weightedSize never above the cap, 290,638 / 262,551 / 65,943 evicted; controls exact.
- **Cluster: Confirmed — caps** (B3g row 1). Entries = Capacity / 120 B = 34,952 · 279,620 · 436,906 at 4 · 32 · 50 MiB (1 : 8 : 12.5), Size ≤ Capacity, `CounterCacheKey`/`ClockAndCount` instances = Entries, control +10,000 exactly. Live heap: live(32) − live(4) = 1.815 × the weight difference (1.772 for auto − 4), inside the audit's band R_pred ± 0.25 (R_pred 1.787 / 1.758 from Caffeine 3.1.8's `PSMW` node 40 B + map node 32 B per entry + table and sketch); the histogram class deltas match each structure of the derivation.
- Recommendations (not applied): A3 could state that the cap is on the weight and the real heap is ≈ weight + 72 B per entry plus table and sketch (≈ 1.8 × C for stress cells); B3h's 10,000-partition control exceeds 4 MiB with 5 cells per partition; B4 `/local` paths.
