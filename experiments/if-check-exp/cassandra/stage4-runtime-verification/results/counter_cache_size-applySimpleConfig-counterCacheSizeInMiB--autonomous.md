# counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous — stage-4 results  <!-- file: results/counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous.md -->

> **Case:** [`counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous`](../../stage3-ai-deep-read/cases/counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous.md)
>
> **Status:** verdict filed, 2026-10-25. **Unit: Confirmed — caps** (B2g row 1). **Cluster: Confirmed — caps** (B3g row 1: entries and weighted size capped exactly at C, ratios 1 : 8 : 12.5; the live heap grows by 1.81 / 1.77 × the weighted size, inside the band R_pred ± 0.25 derived at the audit from Caffeine 3.1.8's node and table layout, R_pred = 1.79 / 1.76). No run 2.
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../../../stage4-runtime-verification/README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous/`](../harness/counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous/).
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-25, on the advisor's machine (`environment-advisor.md`).
> The verdict is against this file's own predictions and conclusions; `ConfigProbe`, the JMX sampler and the run scripts were taken
> from the `key_cache_size-applySimpleConfig` harness (copied, then renamed and adapted in the copy). That file's readings are not used as
> evidence here; the live-heap band was derived from the source.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed in commit `0dcdfe0` (sha256 `f9071b77…651d`, checked equal to the filed row before the audit). Frozen after the step-0 audit's fifteen amendments (2026-10-25, before any harness run or reading): sha256 **`96274f9155afca3552795456cec199162361e511ccf13eb856a6c451968148e8`** — new row in `_INDEX.md` §4. Both tiers ran at this version (no runbook fix to the case file). Not committed (no commit was asked for). |
| **Harness** | [`../harness/counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous/`](../harness/counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous/): `ConfigProbe.java` (copied unchanged from the key-cache harness), `CounterCacheCapProbeTest.java` (mechanism test), `unit-run.sh`; `CounterCacheSampler.java` (copy of `KeyCacheSampler.java`, only class name and `scope=CounterCache` changed), `cluster-run.sh` (one node lifetime), `cluster-chain.sh` (run 1 order and the shakedown). Instrument checks before run 1: the three Java files compiled against the run clone (`instrument-compile.log`, rc 0); cluster shakedown at 2 MiB with 100,000 partitions and a 200-partition control (`run1/shakedown/`, a harness check, not a reading; found harness defect H1, §3). **Bound check against the shakedown** (the lesson from the key-cache run): the shakedown measured w_c = 2,097,120 / 17,476 = 120.0 B, the value B3f (iii)–(v) and (vii) were derived with, and the histogram gave 40.0 B per `PSMW` (699,680 / 17,492) and 32.0 B per `ConcurrentHashMap$Node` (1,691,200 / 52,850), the sizes (vii) assumes; no bound needed re-checking. Self-check: [`run1/selfcheck.py`](counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous/run1/selfcheck.py). |
| **Tiers and values** | Unit (B2): ConfigProbe with `-1MiB`, `0MiB`, unset (auto), `-Xms1G -Xmx1G`, each its own `java`; mechanism test with C ∈ {0MiB, 1MiB, 4MiB, auto}, one `ant testsome` JVM per value (`-Xms1024m`), N = 300,000 counter cells, B2h controls in every JVM. Cluster (B3): one node, `MAX_HEAP_SIZE=2G`, `4MiB`, `32MiB`, auto (= 50 MiB), each: 2,000-partition control `counter_write`, 3,000,000-partition main `counter_write` (5 cells each), flush, histogram. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-25. |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: on-heap bytes of the counter cache; operand is the Caffeine weight Σ (`CounterCacheKey.unsharedHeapSize()` + `ClockAndCount.unsharedHeapSize()`) (`CaffeineCache.java:61-70`, `CounterCacheKey.java:152-157`, `ClockAndCount.java:46-49`). |
| A. Core question | knob varied, ≥ 3 values incl. default | Partly → Met after amendment | Cluster had 4/32/auto. The unit test had only 1/4 MiB; auto (25 MiB, which the 300,000-cell workload also passes) and the `0MiB` control (named in B2h, never scheduled) added (amendment B2b). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met after amendment | Unit: weight only (named gap, amendment B2d). Cluster: B3d had a histogram grep but no relation on it; instance relation (vi) and a live-heap relation (vii) with a band derived from the source added (amendments B3d, B3f). |
| A. Core question | usage driven to the limit and past it | Met | Unit 300,000 × 112 B = 32 × / 8 × / 1.28 × the 1 / 4 / 25 MiB caps; cluster 15,000,000 cells × 120 B = 1.8 GB, 36 × the auto cap. |
| B. Logic | each step says what it establishes | Partly | B2e/B3e list steps; the readings tables carry the meaning. Left for stage 3. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | "≈", "w from the unit tier, adjusted for stress key length": per-entry weights derived from the source (112 B, 120 B) and tolerances fixed for every relation (amendments B2c, B2f, B3c, B3f). |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met after amendment | B2g/B3g had two or three rows; no rows for ConfigProbe failure, `0MiB` rejected, limit not reached, weight vs heap mismatch, stress errors, control failure. Added (amendments B2g, B3g). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met (after amendment B2d/B3d) | Plateau ∝ C plus evictions inferred from the `misses` meter and entries left (Caffeine stats not recorded). |
| B. Logic | alternative explanations and their controls | Partly → Met after amendment | B3h's "run with 10 000 partitions stays below every cap" is wrong for stress's 5-cell rows (10,000 × 5 × 120 B = 6 MB > 4 MiB): cut to 2,000 partitions, placed in every lifetime with an exact expected value (amendment B3h); B2h expectations exact (amendment B2h). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3 and B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | JVM split, test-yaml line (none exists), auto heap (`-Xms`), stress counter table and its 5 cells per op, `no-warmup` (amendments B2a, B2c, B3c). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | `nodetool info` every 30 s replaced by a 2 s JMX sampler with phase labels; `nodetool flush` before the final histogram (B3d, B3e). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly → Met after amendment | `/local/...` paths and a pointer to the key-cache file's B2a: this host's clone, probe and node dirs (B2a, B3a); ConfigProbe needs the JDK 11 module flags (applied at the audit). |
| D. Runnable | workload arithmetic reaches the limit | Met | See A; 149 GiB free disk; the 3 M-partition write took 92–94 s per lifetime. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked in `~/cassandra-src` at `cassandra-5.0.9`: `DatabaseDescriptor.java:831-864, 3947-3950`, `Config.java:479-482`, `DataStorageSpec.java:42, 68-73`, `CacheService.java:105-113, 172-191, 344-350`, `CaffeineCache.java:51-70`, `CounterCacheKey.java:46-80, 152-157`, `CacheKey.java:27-28`, `ClockAndCount.java:28-49`, `ObjectSizes.java:251-254`, `ByteBufferUtil.java:190-195`, `CompositeType.java:521-540`, `ColumnFamilyStore.java:2499-2511`, `CounterMutation.java:129-151, 207-257`, `conf/cassandra.yaml:590-595`, stress `SettingsSchema.java:163-176`, `SettingsColumn.java:127, 170`, `SettingsCommandPreDefined.java:108`, `CqlCounterAdder.java:45-60`; `caffeine-3.1.8.jar` (`javap`): `PS`/`PSMW` fields, `BoundedLocalCache$AddTask` → `FrequencySketch.ensureCapacity(mappingCount)`. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: this host's clone and probe dir; ConfigProbe copied with the JDK 11 flags; one `ant testsome` per value; `-Xms1024m` | Amendment 2026-10-25 | Paths did not exist; once-per-JVM initialisation; auto reads `totalMemory()`. |
| 2 | B2b: `0MiB` and auto added to the test | Amendment 2026-10-25 | Group A default; B2h's `0MiB` control was not scheduled. |
| 3 | B2c: exact workload, cache cleared, w = 112 B derived | Amendment 2026-10-25 | "≈ 100–150 B". |
| 4 | B2d: own-table count, metrics meters, eviction inference | Amendment 2026-10-25 | Caffeine stats not recorded. |
| 5 | B2e: order | Amendment 2026-10-25 | Open. |
| 6 | B2f: exact ConfigProbe lines and tolerances (i)–(iv) incl. the auto arm | Amendment 2026-10-25 | "≈" without tolerance. |
| 7 | B2g: seven rows | Amendment 2026-10-25 | Group B. |
| 8 | B2h: exact controls (a), (b) | Amendment 2026-10-25 | Start state open. |
| 9 | B3a: this host, read-back line | Amendment 2026-10-25 | Paths. |
| 10 | B3c: stress's counter table (5 cells per op), exact commands, `no-warmup`, flush, w_c = 120 B derived | Amendment 2026-10-25 | One op = 5 cache entries was not stated; warm-up writes before the control. |
| 11 | B3d: JMX sampler with phases; histogram classes at baseline and end | Amendment 2026-10-25 | `jstat` cannot attach; `sjk` spawns a JVM per read. |
| 12 | B3e: order and shakedown with a bound check | Amendment 2026-10-25 | Open. |
| 13 | B3f: relations (i)–(vii), (vii) a real-heap band from the source | Amendment 2026-10-25 | Group A; entry counts assumed "w from the unit tier". |
| 14 | B3g: seven rows | Amendment 2026-10-25 | Group B. |
| 15 | B3h: 2,000-partition control with exact expected value | Amendment 2026-10-25 | 10,000 stress partitions exceed 4 MiB. |
| 16 | B4 still names `/local` paths | Left for stage 3 | Superseded by B2a/B3a amendments. |
| 17 | B2e/B3e steps do not say what each establishes | Left for stage 3 | Not needed for a valid run. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-25 (unit 10:13–10:14 EDT; shakedown 10:15–10:17; cluster 10:18–10:27 EDT) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64; 10 cores, 32 GiB RAM; internal SSD (APFS, `/dev/disk3s1`, solid state), 149 GiB free at start (re-checked); loopback 127.0.0.1–.3 present (re-checked with `ifconfig lo0`; one node used, 127.0.0.1); ports 7000/7199/9042/9091 free and no `CassandraDaemon` before the run (re-checked at the end, §8) |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). ConfigProbe: `java -Xms1G -Xmx1G` + the 17 JDK 11 module flags. Test: `ant testsome` forks, `-Xmx1024m` (build.xml) + `-Xms1024m` (`totalMemory` = `maxMemory` = 1,056,309,248 B). Node: G1, `-Xms2G -Xmx2G` (`MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`) |
| Ant | 1.10.18 |
| Local `cassandra-src` clone commit | `$W/cassandra-run12` = `~/Library/Caches/stage4/cassandra-run12`, `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`), built with `ant -Dlocal.repository=$W/m2 build-test` (`BUILD SUCCESSFUL`, 50 s); Caffeine `caffeine-3.1.8.jar` |
| Case-file commit / harness commit | filed `0dcdfe0`; amendments, harness and results uncommitted (sha256 in §1) |
| Storage for node data | local SSD, `$W/node-ccs/{data,commitlog,hints,saved_caches,cdc_raw,logs}`, wiped before and after each lifetime; ConfigProbe data under `$W/probe-ccs/data` (removed) |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/counter_cache_size-applySimpleConfig/` — `clone-build-run12.log`, `instrument-compile.log`, `unit-run.out`, `unit/` (`p1-*.out`, `ant-*.log`, `TEST-*.xml`, `stage4.out`, `summary.txt`, `commands.log`, yaml diffs), `shakedown/sd-c2/` (not evidence), `cluster/{c4,c32,cauto}/` (`system.log`, `node.out`, `samples.csv`, `histo-*.txt`, `heapinfo-*.txt`, `stress-*.log`, `tablestats-final.txt`, `summary.txt`, `commands.log`), `cluster/chain.out`, `selfcheck.out` |

## 3. Runbook defects

None in the case file: both tiers ran as amended at the frozen version.

Harness defects (no case-file change, no effect on a reading):

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| H1 | shakedown | B3d (histogram excerpt) | the excerpt grep anchored `[J`, `[B` and the `ConcurrentHashMap` classes at end of line, but JDK 11's histogram appends the module (`[J (java.base@11.0.32.1)`), so they were missing from `histo-excerpt-*.txt` (the full histogram had them) | allow an optional ` (module)` suffix | 2026-10-25, before run 1 | none |

The shakedown (2 MiB, 100,000 partitions, 200 in the control) found no other defect; its readings are not used, except the bound check in §1.

## 4. Run 1

**Scope:** both tiers, every value in §1. **Command logs:** `counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous/run1/unit/commands.log`, `run1/cluster/<label>/commands.log`, `run1/chain.out`.

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`, `stage4.out`, `p1-*.line`, `junit-*.txt`; one JVM per row; all four `ant testsome` rc 0, `Tests run: 1, Failures: 0, Errors: 0`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| ConfigProbe `-1MiB` | `REJECT ConfigurationException: Invalid yaml: file:…/-1MiB.yaml / root: java.lang.IllegalArgumentException: Invalid data storage: -1MiB Accepted units:[MEBIBYTES, GIBIBYTES] where case matters and only non-negative values are accepted` (no `counter_cache_size option was set incorrectly`) | `p1--1MiB.line` |
| ConfigProbe `0MiB` | `OK getCounterCacheSizeInMiB=0` | `p1-0MiB.line` |
| ConfigProbe unset (`-Xms1G -Xmx1G`) | `OK getCounterCacheSizeInMiB=25` | `p1-unset.line` |
| Calibration (C > 0) | own = 1,000 after 1,000 updates; **w = 112 B** (weightedSize 112,000 / size 1,000) = the derived value | `stage4.out` |

| C | counterCacheSizeInMiB / capacity (B) | max weightedSize over 31 readings | final own = size | capacity/w | N − own (evicted, inferred) | series misses | B2h control |
|---|---|---|---|---|---|---|---|
| 0MiB | 0 / 0 | 0 | 0 | — | (none cached) | 0; requests 0 (cache never consulted) | (b) size = weightedSize = requests = 0 at every reading |
| 1MiB | 1 / 1,048,576 | 1,048,544 (≤ cap) | 9,362 | 9,362.3 | 290,638 | 300,000 | (a) M = 4,681 → own 4,681, weight 524,272 = M·w |
| 4MiB | 4 / 4,194,304 | 4,194,288 (≤ cap) | 37,449 | 37,449.1 | 262,551 | 300,000 | (a) M = 18,724 → own 18,724, weight 2,097,088 = M·w |
| auto | 25 / 26,214,400 (`totalMemory` 1,056,309,248) | 26,214,384 (≤ cap) | 234,057 | 234,057.1 | 65,943 | 300,000 | (a) M = 117,028 → own 117,028, weight 13,107,136 = M·w |

own(4MiB)/own(1MiB) = 4.0001; own(auto)/own(1MiB) = 25.0007.

**Cluster tier** (`run1/cluster/<label>/summary.txt`, `samples.csv`, `histo-excerpt-*.txt`, `readback-line.txt`, `stress-*-results.txt`; one node lifetime per value; 66–67 sampler rows each, 0 error rows; every stress run 0 errors with the requested partition count)

| Value | Observable | 4MiB (c4) | 32MiB (c32) | auto (cauto) |
|---|---|---|---|---|
| read-back | `system.log` | `Initializing counter cache with capacity of 4 MiBs` | `… 32 MiBs` | `… 50 MiBs` |
| (i) | `Capacity` (every row) | 4,194,304 | 33,554,432 | 52,428,800 |
| (ii) | max `Size` / Capacity | 4,194,240 (0.99998) | 33,554,400 (0.999999) | 52,428,720 (0.999998) |
| B3h (a) | Entries baseline → control-done; Misses in control | 0 → 10,000; 10,000 | 0 → 10,000; 10,000 | 0 → 10,000; 10,000 |
| (iii) | main-done `Size`, `Entries`, w_c = Size/Entries | 4,194,240; 34,952; 120.00 B | 33,554,400; 279,620; 120.00 B | 52,428,720; 436,906; 120.00 B |
| (v) | Misses in main write; Entries ≤ 750,000? | 14,990,000; yes | 14,990,000; yes | 14,989,995; yes |
| (vi) | `CounterCacheKey` / `ClockAndCount` instances (final histo) | 34,952 / 34,953 | 279,620 / 279,621 | 436,906 / 436,907 |
| (vii) | live total, final histogram | 64,966,880 | 118,243,432 | 150,437,472 |
| — | `nodetool info` final | entries 34952, size 4 MiB, capacity 4 MiB, 10000 hits, 15010000 requests | entries 279620, size 32 MiB, 10000 hits | entries 436906, size 50 MiB, 10005 hits |

Derived (recomputed by `selfcheck.py`): Entries(32)/Entries(4) = 8.0001, Entries(auto)/Entries(4) = 12.5002; w_c = 120.000 B in all three. **D(32 − 4) = 53,276,552 B, S = 29,360,160 B, D/S = 1.815** (R_pred 1.787, band 1.54–2.04); **D(auto − 4) = 85,470,592 B, S = 48,234,480 B, D/S = 1.772** (R_pred 1.758, band 1.51–2.01). Per extra cached entry the live heap grows by 217.8 B (c32) and 212.6 B (cauto) against a weight of 120 B.

Histogram classes, c32 − c4 at the end (`histo-excerpt-1-end.txt`): `PSMW` +244,667 instances (+9,786,680 B, 40.0 B each; ΔE = 244,668); `ConcurrentHashMap$Node` +244,666 (+7,829,312 B, 32.0 B); `[Ljava.util.concurrent.ConcurrentHashMap$Node;` +1,835,008 B (predicted 4ΔL = 1,835,008); `[J` +3,670,000 B (predicted 8ΔT = 3,670,016); `CounterCacheKey` + `ClockAndCount` +15,658,752 B (64 B per entry); `[B` +13,706,520 B (keys and cell names, 56 B × ΔE = 13,701,408). S (the weighed objects, 29,360,160) + `PSMW` + map node + table + `[J` = 52,481,160 of D = 53,276,552 (residual 0.80 MB, 1.5 %). For cauto − c4: table +3,931,392 (predicted 3,932,160), `[J` +3,670,128 (predicted 3,670,016).

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — [observed: `stage4.out`, `p1-*.line`, `junit-*.txt`] the knob read back as set in every JVM (0/1/4 and auto 25 within the frozen 24–26; capacity = value × 2^20 exactly); calibration inserted exactly one entry per counter cell; the cap was passed 32×, 8× and 1.28× at 1 MiB, 4 MiB and auto; both B2h controls met their frozen expectations; only the appended yaml line differed between JVMs (`p2-yaml-diff-*.txt`). Valid.
2. **Readings** — nothing unusual. All 300,000 lookups of a series missed (each cell is new) and hits stayed 0.
3. **Matched row** — B2g row 1, "plateau ∝ C, weightedSize ≤ C" with amended B2f [observed: (i) max weightedSize ≤ cap at every reading (1,048,544 · 4,194,288 · 26,214,384); (ii) own 9,362 · 37,449 · 234,057 = ⌊capacity/w⌋; (iii) evicted 290,638 · 262,551 · 65,943 > 0 with series misses 300,000; (iv) ratios 4.0001 and 25.0007; w = 112 B as derived; ConfigProbe as predicted; controls exact].
4. **Excluded rows** — "size() → N with weightedSize > C": own stays at ⌊capacity/w⌋. "size() = 0 with C > 0": own 1,000 after calibration at every C > 0. Added rows: `-1MiB` not accepted (parser message, not line 843's); `0MiB` accepted and auto in range; ConfigProbe failed for no other reason; the plateau is proportional to C; w = 112 B (so the "w ≠ 112" row does not apply); no control missed.
5. **Observed vs. inferred** — [inferred: no Caffeine stats] evictions are N − own: each of the N distinct cells missed once (series misses = N, observed) and was put, and nothing else removes entries.
6. **Deviations and gaps** — none in the procedure. The unit tier reads the weight, not the retained heap (gap named at the audit; the cluster tier carries the heap part).
7. **Core question** — the startup value becomes the counter cache's maximum weight: cached weight follows the knob (⌊capacity/112⌋ entries, ratios 4 and 25) and never exceeds it, by evicting; `0MiB` disables the cache (it is never consulted); a negative value never reaches the check at `DatabaseDescriptor.java:838`.

**Unit tier conclusion:** B2g row 1 — **confirmed**.

**Cluster tier**

1. **Validity** — [observed: `readback-line.txt`, `samples.csv`, `stress-*-results.txt`, `yaml-overrides.txt`] read-back 4/32/50 MiB and Capacity = C·2^20 in every row; 3,000,000 partitions (15,000,000 cells) written with 0 errors in each lifetime; the cap passed at every value (≥ 14.5 M cells evicted); the B3h control met its frozen expectation in all three lifetimes (0 → 10,000 entries, 10,000 misses); same heap flags and yaml except the knob line. Valid.
2. **Readings** — the auto lifetime shows 10,005 hits instead of 10,000, i.e. one 5-cell update hit a cached row once more (a retried or repeated op); partitions written and errors are as requested and the entry count is exact, so no relation depends on it.
3. **Matched row** — B3g row 1, "size ≤ capacity, entries ∝ C → cap governs heap", which by amendment needs B3f (i)–(vii) and B3h [observed: (i) exact; (ii) max Size/Capacity ≤ 0.99999…; (iii) full, Entries = ⌊Capacity/120⌋; (iv) w_c 120.000 B in all three (predicted 120), ratios 8.0001 and 12.5002; (v) misses ≥ 14,989,995 with ≤ 436,906 entries left; (vi) instances = Entries (+1 `ClockAndCount`, the static `BLANK`); (vii) D/S = 1.815 and 1.772 inside 1.54–2.04 and 1.51–2.01].
4. **Excluded rows** — "CounterCacheKey instances ≫ C/w": instances = Entries exactly. Added rows: read-back matched; Size never above 1.01 × Capacity; Size ≥ 0.9 × Capacity at every value; "(i)–(vi) hold but (vii) fails": (vii) holds; w_c = 120 B so the derivation row does not apply; 0 stress errors; no control missed.
5. **Observed vs. inferred** — [inferred: histogram class counts] the attribution of the heap outside the weight to the Caffeine `PSMW` node (40 B), the backing map's node (32 B), its table and the frequency sketch: the class deltas match the frozen derivation to within 0.05 % for each structure, and the total to 1.5 %. The verdict rests on (vii)'s observed ratio, not on the attribution.
6. **Deviations and gaps** — no heap dump (instances and class totals only); the live heap is compared between lifetimes (D), not against an absolute baseline, as frozen. `nodetool info` read at three points instead of every 30 s, by amendment.
7. **Core question** — usage follows the constraint: entries plateau at exactly Capacity/120 B (1 : 8 : 12.5), the weighted size never passes C, and the excess is evicted. The real live heap also follows the knob linearly and is bounded by it, at ≈ 1.8 × C (the unweighed Caffeine node and map entry per cell plus table and sketch), the factor the audit derived from the source before the run.

**Cluster tier conclusion:** B3g row 1 — **confirmed**.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck.py` (written separately from the harness; re-reads the raw `p1-*.out`, `stage4.out`, `TEST-*.xml`, each lifetime's `system.log`, `samples.csv`, `histo-1-end.txt`, `stress-*.log` under the full log root, and recomputes R_pred with its own L(E)/T(E) functions): **77 relation checks, 77 hold, 0 fail**, exit 0 (`run1/selfcheck.out`).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | knob per JVM and read-back per lifetime, junit counts, calibration one entry per cell, stress partitions and errors, both controls in every JVM/lifetime re-read. |
| 2. Readings | yes | max weightedSize over all unit readings; max Size over all 66–67 rows per lifetime; live totals from the full histograms; the 10,005 hits at auto seen in `summary.txt` and not used by any relation. |
| 3. Matched row | yes | B2f (i)–(iv) each against its frozen tolerance; B3f (i)–(vii) recomputed; D/S = 1.8146 and 1.7720 against R_pred 1.7875 and 1.7576. |
| 4. Excluded rows | yes | every row of B2g/B3g, original and added, addressed in §4.2 with a reading. |
| 5. Observed vs. inferred | yes | the unit eviction inference rests on the `misses` meter (300,000 per series, re-read); the heap attribution is labelled inferred and printed by the self-check as INFO lines, not counted as relations. |
| 6. Deviations and gaps | yes | §3 harness defect H1 affected only the excerpt files; the self-check reads the full histograms. |
| 7. Core question — the steps follow the audited logic | yes | read-back → plateau ∝ C → evictions → instances = entries → live heap vs derived relation → controls, in B2e/B3e's order. |

### 5.2 Run 2?

**No** (decided 2026-10-25). Every load-bearing figure is observed and recomputed by the self-check; the unit result is exact (⌊capacity/w⌋, exact control weights), the cluster relations hold with wide margins at two independent pairs, and the result neither refutes the case nor confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive.

**Claim tested (B1):** With `counter_cache_size: C`, the counter cache's weighted size stays ≤ C MiB and its entry count plateaus at ≈ C / (per-entry weight) once more distinct counter cells are updated than fit; usage scales with C, not with distinct counters written. "Confirmed" means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1: `-1MiB` rejected by the parser (never reaches line 838), `0MiB` → 0 (cache never consulted), auto → 25; weightedSize ≤ cap at every reading, own = ⌊capacity/112 B⌋ = 9,362 · 37,449 · 234,057 at 1 · 4 · 25 MiB (ratios 4.000, 25.001), evicted 290,638 · 262,551 · 65,943; controls exact | caps | run 1 + self-check | 2026-10-25 |
| Cluster | **Confirmed** — B3g row 1: Capacity = C·2^20, Size ≤ Capacity, Entries = Capacity/120 B = 34,952 · 279,620 · 436,906 (1 : 8 : 12.5), instances = Entries, control +10,000 exactly; live(32) − live(4) = 1.815 × the weight difference (1.772 for auto − 4), inside R_pred ± 0.25 (R_pred 1.787 / 1.758 from Caffeine's node and table layout) | caps (entries and weighted size capped exactly at C; real heap bounded and proportional to C at ≈ 1.8 × C, the unweighed Caffeine node, map entry, table and sketch per cell as derived) | run 1 + self-check | 2026-10-25 |

**Feedback filed:** the case file's section D (uncommitted). No section of the case amended after run 1. Recommendations for stage 3, left unapplied: (1) A3's "weights are shallow estimates" could say the cap is on the weight and the real heap per entry is weight + 72 B (Caffeine `PSMW` 40 B + `ConcurrentHashMap$Node` 32 B) + table and sketch, ≈ 1.8 × C for stress-sized cells; (2) B3h's 10,000-partition control exceeds 4 MiB with stress's 5 counter cells per partition; (3) B4 still names `/local` paths.

**End of run:** `pgrep -f CassandraDaemon` empty, no ConfigProbe / stress / sampler process, ports 7000/7199/9042/9091 free, `$W/node-ccs` and `$W/probe-ccs` removed, the probe test removed from `$W/cassandra-run12` and `test/conf/cassandra.yaml` restored (`git status` clean), no `build/` or log folder in the repository root (2026-10-25, checked after the self-check).
