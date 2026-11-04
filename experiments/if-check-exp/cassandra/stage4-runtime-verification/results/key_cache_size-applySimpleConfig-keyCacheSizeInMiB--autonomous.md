# key_cache_size-applySimpleConfig-keyCacheSizeInMiB--autonomous — stage-4 results  <!-- file: results/key_cache_size-applySimpleConfig-keyCacheSizeInMiB--autonomous.md -->

> **Case:** [`key_cache_size-applySimpleConfig-keyCacheSizeInMiB--autonomous`](../../stage3-ai-deep-read/cases/key_cache_size-applySimpleConfig-keyCacheSizeInMiB--autonomous.md)
>
> **Status:** verdict filed, 2026-10-25. **Unit: Confirmed — caps** (run 1). **Cluster: Confirmed — caps** (cluster re-run
> "run 1b" of 2026-10-25 at the re-frozen version `59fe55f8…45ce`, after the user-authorised amendment of B3f (v), (vii) and the
> B3g rows that depend on them; §7, §8). The run-1 cluster verdict below (Not confirmed) stays on record as filed.
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/key_cache_size-applySimpleConfig-keyCacheSizeInMiB--autonomous/`](../harness/key_cache_size-applySimpleConfig-keyCacheSizeInMiB--autonomous/).
>
> **Run-1 status (as filed 2026-10-25):** verdict filed, 2026-10-25. **Unit: Confirmed — caps** (B2g row 1). **Cluster: Not confirmed — caps** (B3g added row "(i)–(v) hold but (vi) or (vii) fails": entry count and weighted size follow the knob exactly and never pass it, but the real live heap grows by ≈ 2.17 × the weighted size, outside the frozen 0.5–2.0 band; B3f (v) as written also fails at auto). No run 2.
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-25, on the advisor's machine (`environment-advisor.md`).
> The verdict is against this file's own predictions and conclusions; `ConfigProbe` and the JMX sampler pattern were taken from the
> `prepared_statements_cache_size-applySimpleConfig` and `memtable_heap_space-applySimpleConfig` harnesses (copied, not modified).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed in commit `0dcdfe0` (sha256 `cbb132a9…e1f3`, checked equal to the filed row before the audit). Frozen after the step-0 audit's fifteen amendments (2026-10-25, before any harness run or reading): sha256 **`3a87b7148a2c8babdcafec87f2eb0a6ed1009f75b1f69273fa50189f73e7389c`** — new row in `_INDEX.md` §4. Both tiers ran at this version (no runbook fix to the case file). Not committed (no commit was asked for). |
| **Harness** | [`../harness/key_cache_size-applySimpleConfig-keyCacheSizeInMiB--autonomous/`](../harness/key_cache_size-applySimpleConfig-keyCacheSizeInMiB--autonomous/): `ConfigProbe.java` (copied unchanged from `harness/prepared_statements_cache_size-applySimpleConfig-preparedStatementsCacheSizeInMiB--autonomous/`), `KeyCacheCapProbeTest.java` (mechanism test), `unit-run.sh`; `KeyCacheSampler.java` (one-connection JMX sampler, modelled on the `memtable_heap_space-applySimpleConfig` `Sampler.java`), `cluster-run.sh` (one node lifetime), `cluster-chain.sh` (run 1 order and the shakedown). Instrument checks before run 1: both Java test/probe files compiled against the run clone (`instrument-compile.log`, rc 0); cluster shakedown at 2 MiB with 100,000 partitions (`run1/shakedown/`, a harness check, not a reading; found harness defects H1–H2, §3). Self-check: [`run1/selfcheck.py`](key_cache_size-applySimpleConfig-keyCacheSizeInMiB--autonomous/run1/selfcheck.py). |
| **Tiers and values** | Unit (B2): ConfigProbe with `-1MiB`, `0MiB`, unset (auto), `-Xms1G -Xmx1G`, each its own `java`; mechanism test with C ∈ {0MiB, 1MiB, 4MiB, auto}, one `ant testsome` JVM per value (`-Xms1024m`), N = 200,000 partitions, B2h controls in every JVM. Cluster (B3): one node, `MAX_HEAP_SIZE=2G`, `8MiB`, `64MiB`, auto (= 100 MiB), each: stress write 2,000,000, flush, compact, B3h control read of 20,000, main read of 2,000,000. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-25. |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: on-heap bytes of the key cache; operand is the Caffeine weight Σ (`KeyCacheKey.unsharedHeapSize()` + `RowIndexEntry.unsharedHeapSize()`) (`CaffeineCache.java:61-70`, `KeyCacheKey.java:59-62`, `RowIndexEntry.java:199-203`). |
| A. Core question | knob varied, ≥ 3 values incl. default | Partly → Met after amendment | Cluster had 8/64/auto. The unit test had only 1/4 MiB; auto and the `0MiB` control (named in B2h, never scheduled) added (amendment B2b). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | Unit: weight only (named gap, amendment B2d). Cluster: `KeyCacheKey` instances and the live total from `jmap -histo:live` (B3d), with a relation on the live-heap difference added (amendment B3f (vii)). |
| A. Core question | usage driven to the limit and past it | Met | Unit 200,000 × ≈ 80–100 B ≥ 3.8 × 4 MiB; cluster 2,000,000 × ≈ 88–120 B ≈ 1.7–2.3 × the 100 MiB auto cap. The unit auto arm (≈ 50 MiB) is not reached and is recorded as the below-cap default point. |
| B. Logic | each step says what it establishes | Partly | B2e/B3e list steps; the readings tables carry the meaning. Left for stage 3. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | "≈", "±10 %" for the plateau only, entry counts assuming w = 120 B: tolerances fixed for every relation with w measured (amendments B2f, B3f). |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met after amendment | No rows for a ConfigProbe failure unrelated to the knob, `0MiB` rejected, a non-BIG SSTable, a counter/heap mismatch, limit not reached, control failure. Added (amendments B2g, B3g). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met (after amendment B2d/B3d) | Plateau ∝ C plus inferred evictions (distinct keys inserted − entries left; Caffeine stats are not recorded, so the eviction count is inferred from the `Misses` meter and `Entries`). |
| B. Logic | alternative explanations and their controls | Partly → Met after amendment | B2h/B3h controls named; starting state and expected values derived from the source (amendments B2h, B3h). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3 and B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Cache clear before the series, JVM split, test-yaml line (none exists), auto heap (`-Xms`), stress warm-up (amendments B2a, B2c, B2e, B3c, B3e). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | `nodetool info` every 30 s replaced by a 2 s JMX sampler with phase labels (B3d); `no-warmup` on stress reads (B3c). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly → Met after amendment | `/local/...` paths, network clone: this host's clone, probe and node dirs (B2a, B3a); ConfigProbe needs the JDK 11 module flags (known from the prepared-statements run; applied at the audit). |
| D. Runnable | workload arithmetic reaches the limit | Met | See A; 149 GiB free disk; node data 487 MB per lifetime. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked in `~/cassandra-src` at `cassandra-5.0.9`: `DatabaseDescriptor.java:812-829, 3881-3884`, `Config.java:373, 467-468`, `DataStorageSpec.java:42, 58-73`, `CacheService.java:101-136, 336-342`, `CaffeineCache.java:51-70`, `KeyCacheKey.java:59-62`, `RowIndexEntry.java:199-203`, `KeyCache.java`, `KeyCacheSupport.java:79-86`, `BigTableReader.java:265-343`, `BigSSTableReaderLoadingBuilder.java:74-75`, `BigTableWriter.java:177`, `CacheMetrics.java:69-75`, `InstrumentingCache.java:56-65`, `StressAction.java:105-129`, `conf/cassandra.yaml:519-525, 1171-1172`. **SSTable format: BIG is the default write format at this tag** (`Config.java:373` `selected_format = BigFormat.NAME`; no `sstable:` section in either yaml); both tiers observed `nb`/BIG SSTables only. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: this host's clone and probe dir; ConfigProbe copied with the JDK 11 flags; one `ant testsome` per value; `-Xms1024m`; BIG format stated and checked | Amendment 2026-10-25 | Paths did not exist; once-per-JVM initialisation; auto reads `totalMemory()`. |
| 2 | B2b: `0MiB` and auto added to the test | Amendment 2026-10-25 | Group A default; B2h's `0MiB` control was not scheduled. |
| 3 | B2c: exact workload, cache cleared before the series | Amendment 2026-10-25 | System-table entries and start state. |
| 4 | B2d: own-table count, metrics meters, eviction inference | Amendment 2026-10-25 | Caffeine stats not recorded. |
| 5 | B2e: order | Amendment 2026-10-25 | Open. |
| 6 | B2f: exact ConfigProbe lines and tolerances (i)–(iv), auto arm | Amendment 2026-10-25 | "≈" without tolerance. |
| 7 | B2g: seven rows | Amendment 2026-10-25 | Group B. |
| 8 | B2h: exact controls (a) and (b) | Amendment 2026-10-25 | Start state open. |
| 9 | B3a: this host, read-back line, format listing | Amendment 2026-10-25 | Paths. |
| 10 | B3c: exact commands, `no-warmup` on reads | Amendment 2026-10-25 | Stress warm-up reads extra keys before the control. |
| 11 | B3d: JMX sampler with phases; histogram at baseline and end | Amendment 2026-10-25 | `jstat` cannot attach; `sjk` spawns a JVM per read. |
| 12 | B3e: order and shakedown | Amendment 2026-10-25 | Open. |
| 13 | B3f: relations (i)–(vii) with w measured | Amendment 2026-10-25 | Entry counts assumed w = 120 B. |
| 14 | B3g: seven rows | Amendment 2026-10-25 | Group B. |
| 15 | B3h: control placement and expected value | Amendment 2026-10-25 | Open. |
| 16 | B4 still names `/local` paths | Left for stage 3 | Superseded by B2a/B3a amendments. |
| 17 | B2e/B3e steps do not say what each establishes | Left for stage 3 | Not needed for a valid run. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-25 (unit 09:41–09:43 EDT; shakedown 09:45–09:47; cluster 09:49–09:58 EDT) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64 (T6000); 10 cores, 32 GiB RAM; internal SSD (APFS, `/dev/disk3s1`), 150 GiB free at start (149 GiB during the cluster runs); loopback 127.0.0.1–.3 present (re-checked with `ifconfig lo0`; one node used, 127.0.0.1); ports 7000/7199/9042/9091 free and no `CassandraDaemon` before the run (rechecked at the end, §8) |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). ConfigProbe: `java -Xms1G -Xmx1G` + the 17 JDK 11 module flags. Test: `ant testsome` forks, `-Xmx1024m` (build.xml) + `-Xms1024m` (`totalMemory` = `maxMemory` = 1,056,309,248 B). Node: G1, `-Xms2G -Xmx2G` (`MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`) |
| Ant | 1.10.18 |
| Local `cassandra-src` clone commit | `$W/cassandra-run11` = `~/Library/Caches/stage4/cassandra-run11`, `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`), built with `ant -Dlocal.repository=$W/m2 build-test` (`BUILD SUCCESSFUL`, 52 s) |
| Case-file commit / harness commit | filed `0dcdfe0`; amendments, harness and results uncommitted (sha256 in §1) |
| Storage for node data | local SSD, `$W/node-kcs/{data,commitlog,hints,saved_caches,cdc_raw,logs}`, wiped before and after each lifetime (487 MB data per main lifetime); ConfigProbe data under `$W/probe-kcs/data` (removed) |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/key_cache_size-applySimpleConfig/` — `clone-build-run11.log`, `instrument-compile.log`, `unit-run.out`, `unit/` (`p1-*.out`, `ant-*.log`, `TEST-*.xml`, `stage4.out`, `summary.txt`, `commands.log`, yaml diffs), `shakedown/sd-k2/` (not evidence), `cluster/{k8,k64,kauto}/` (`system.log`, `node.out`, `samples.csv`, `histo-*.txt`, `heapinfo-*.txt`, `stress-*.log`, `sstables-list.txt`, `tablestats-after-compact.txt`, `summary.txt`, `commands.log`), `cluster/chain.out`, `selfcheck.out` |

## 3. Runbook defects

None in the case file: both tiers ran as amended at the frozen version.

Harness defects (no case-file change, no effect on a reading):

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| H1 | shakedown | B3e (harness summary) | the `OOM:` count grepped `OutOfMemoryError` and matched the JVM-arguments line (`-XX:+HeapDumpOnOutOfMemoryError`), giving 1 | grep `java.lang.OutOfMemoryError` | 2026-10-25, before run 1 | none |
| H2 | shakedown | B3a format listing | the SSTable names were only in the harness summary, not a raw file | write `sstables-list.txt` | 2026-10-25, before run 1 | none |
| H3 | unit run 1 | B2e step 1 | ConfigProbe ran with the repository as working directory, so `logback-test.xml` created an empty `build/test/logs/cassandra.testtag_IS_UNDEFINED/TEST-suitename_IS_UNDEFINED.log` (0 bytes) in the repository root | removed the folder; `unit-run.sh` now runs the probe from `$P` | 2026-10-25, after run 1 (the readings are on stdout, unaffected) | none |
| R1 | cluster run 1 (reading, not a runbook defect) | B3f (v), (vii) | (v)'s "< 1,000,000 entries" (set on the file's 120 B estimate) failed at auto (1,191,563), and (vii)'s 0.5–2.0 band (an estimate, not derived) failed at both pairs (2.173, 2.168); the cluster tier was Not confirmed (§4.2) | **Re-freeze, authorised by the user (Yang, the advisor) on 2026-10-25:** dated amendments `Amendment 2026-10-25 (after run 1, authorised by the user) — B3f (v), (vii)` (w_s = 88 B and Entries within ±0.5 % of ⌊Capacity/88⌋; D/S within R_pred ± 0.25, R_pred derived from Caffeine 3.1.8 `PSMW` 40 B + `ConcurrentHashMap$Node` 32 B + map table + frequency sketch: 2.006 and 2.063) and `… — B3g, rows that depend on B3f (v), (vii)`; new sha256 `59fe55f8…45ce` as a new row in `_INDEX.md` §4; the whole cluster tier re-run from its beginning in a fresh clone (§7). B1, B3f (i)–(iv), (vi), B3h and the unit tier unchanged | user, 2026-10-25 | uncommitted (no commit asked for) |
| H4 | cluster re-run | B3a paths | the harness's node directory and log root were fixed to run 1's (`$W/node-kcs`, `…/cluster`) | `cluster-run.sh`: `N=${KCS_NODE:-$W/node-kcs}`; `cluster-chain.sh`: `O=${KCS_OUT:-…/cluster}` (defaults reproduce run 1; the clone was already `C=${C:-…}`). No change for the amendment itself: the amended relations use readings the harness already recorded (Entries, Size, full histograms) | AI, 2026-10-25 | n/a (harness) |

The shakedown (2 MiB, 100,000 partitions, 5,000 in the control) found no other defect; its readings are not used.

## 4. Run 1

**Scope:** both tiers, every value in §1. **Command logs:** `key_cache_size-applySimpleConfig-keyCacheSizeInMiB--autonomous/run1/unit/commands.log`, `run1/cluster/<label>/commands.log`, `run1/chain.out`.

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`, `stage4.out`, `p1-*.line`, `junit-*.txt`; one JVM per row; all four `ant testsome` rc 0, `Tests run: 1, Failures: 0, Errors: 0`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| ConfigProbe `-1MiB` | `REJECT ConfigurationException: Invalid yaml: file:…/-1MiB.yaml / root: java.lang.IllegalArgumentException: Invalid data storage: -1MiB Accepted units:[MEBIBYTES, GIBIBYTES] where case matters and only non-negative values are accepted` (no `key_cache_size option was set incorrectly`) | `p1--1MiB.line` |
| ConfigProbe `0MiB` | `OK getKeyCacheSizeInMiB=0` | `p1-0MiB.line` |
| ConfigProbe unset (`-Xms1G -Xmx1G`) | `OK getKeyCacheSizeInMiB=51` | `p1-unset.line` |
| Format (every JVM) | `selected_format=big`; the test table's live SSTables `{big/nb/BigTableReader=2}` | `stage4.out` (`STAGE4 run`, `STAGE4 table`) |
| Calibration (C > 0) | own = 1,000 after 1,000 reads; **w = 80 B** (weightedSize 80,000 / size 1,000) | `stage4.out` |

| C | keyCacheSizeInMiB / capacity (B) | max weightedSize over 21 readings | final own = size | C·2^20/w | N − own (evicted, inferred) | series misses | B2h control |
|---|---|---|---|---|---|---|---|
| 0MiB | 0 / 0 | 0 | 0 | — | 200,000 (none cached) | 200,573 (all 201,585 lookups since the clear missed) | (b) size = weightedSize = 0 at all 22 readings |
| 1MiB | 1 / 1,048,576 | 1,048,560 (≤ cap) | 13,107 | 13,107.2 | 186,893 | 200,596 | (a) M = 6,553 → own 6,553, weight 524,240 = M·w |
| 4MiB | 4 / 4,194,304 | 4,194,240 (≤ cap) | 52,428 | 52,428.8 | 147,572 | 200,608 | (a) M = 26,214 → own 26,214, weight 2,097,120 = M·w |
| auto | 50 / 52,428,800 (`totalMemory` 1,056,309,248) | 16,000,000 | 200,000 = N | 655,360 (not reached) | 0 | — | (a) M = 100,000 → own 100,000, weight 8,000,000 |

own(4MiB)/own(1MiB) = 4.000. At 1 MiB the plateau is reached by the second sample (20,000 reads) and stays at 13,107 to the end; at 4 MiB it is reached by 60,000 reads.

**Cluster tier** (`run1/cluster/<label>/summary.txt`, `samples.csv`, `histo-*.txt`, `readback-line.txt`, `stress-*-results.txt`, `sstables-list.txt`; one node lifetime per row; 35 sampler rows each, 0 error rows; every stress run 0 errors with the requested partition count; `keyspace1.standard1` one SSTable `nb-16-big-Data.db` after the compaction, all 19 `Data.db` files of the node BIG)

| Value | Observable | 8MiB (k8) | 64MiB (k64) | auto (kauto) |
|---|---|---|---|---|
| read-back | `system.log` | `Initializing key cache with capacity of 8 MiBs` | `… 64 MiBs` | `… 100 MiBs` |
| (i) | `Capacity` (every row) | 8,388,608 | 67,108,864 | 104,857,600 |
| (ii) | max `Size` / Capacity | 8,388,600 (0.99999) | 67,108,800 (0.99999) | 104,857,544 (0.99999) |
| B3h (a) | Entries baseline → control-done; Misses in control | 85 → 20,085 (+20,000); 20,000 | 85 → 20,085 (+20,000); 20,000 | 85 → 20,085 (+20,000); 20,000 |
| (iii) | main-done `Size`, `Entries`, w_c = Size/Entries | 8,388,600; 95,325; 88.00 B | 67,108,792; 762,600; 88.00 B | 104,857,536; 1,191,563; 88.00 B |
| (v) | Misses in main read; Entries < 1,000,000? | 1,980,000; yes | 1,979,978; yes | 1,979,967; **no (1,191,563)** |
| (vi) | `KeyCacheKey` / `RowIndexEntry` instances (final histo) | 95,325 / 95,325 | 762,600 / 762,600 | 1,191,563 / 1,191,563 |
| (vii) | live total, baseline → end | 51,649,816 → 70,487,664 | 53,703,272 → 198,087,448 | 54,089,120 → 279,662,448 |
| — | `nodetool info` final | entries 95325, size 8 MiB, capacity 8 MiB | entries 762600, size 64 MiB, capacity 64 MiB | entries 1191563, size 100 MiB, capacity 100 MiB |

Derived (recomputed by `selfcheck.py`): Entries(64)/Entries(8) = 8.000, Entries(auto)/Entries(8) = 12.500; w_c = 88.000 B in all three; **D = live(64) − live(8) = 127,599,784 B = 2.173 × (Size(64) − Size(8)) = 2.173 × 58,720,192**; D(auto − 8) = 209,174,784 B = 2.168 × 96,468,936. Per extra cached entry the live heap grows by 191.2 B (k64) and 190.8 B (kauto), against a weight of 88 B.

Histogram classes, k64 − k8 at the end (`histo-1-end-top20.txt`): `com.github.benmanes.caffeine.cache.PSMW` +667,275 instances (+26,691,000 B, 40 B each); `ConcurrentHashMap$Node` +667,243 (+21,351,776 B, 32 B); `KeyCacheKey` +21,352,800 B (32 B); `RowIndexEntry` +16,014,600 B (24 B); `[B` +23,472,256 B; `[J` +7,337,960 B; `[Ljava.util.concurrent.ConcurrentHashMap$Node;` +3,669,936 B.

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — [observed: `stage4.out`, `p1-*.line`, `junit-*.txt`] the knob read back as set in every JVM (0/1/4 and auto 50 within the frozen 50–52; capacity = value × 2^20 exactly); every live SSTable BIG; calibration inserted exactly one entry per read; the cap was passed 15× and 3.8× at 1 and 4 MiB; both B2h controls met their frozen expectations; only the appended yaml line differed between JVMs (`p2-yaml-diff-*.txt`). Valid.
2. **Readings** — nothing unusual. The auto value is 50 in the test JVM and 51 in ConfigProbe because `totalMemory()` is 1,056,309,248 B under `ant`'s G1 fork and 2^30 B under the plain `java -Xms1G`; both are inside the frozen 50–52.
3. **Matched row** — B2g row 1, "plateau ≈ C/w, weightedSize ≤ C, scales with C" with amended B2f [observed: (i) max weightedSize ≤ cap at every sample (1,048,560 and 4,194,240); (ii) own 13,107 and 52,428 vs C/w 13,107.2 and 52,428.8; (iii) evicted 186,893 and 147,572 > 0 with series misses ≥ 199,000; (iv) ratio 4.000; auto own = N, weight = N·w; ConfigProbe as predicted; controls exact].
4. **Excluded rows** — "size() keeps growing to ≈ N with weightedSize > C": own stays at ⌊C/w⌋ from the second sample on. "size() stays 0": own 1,000 after calibration at every C > 0. "-1MiB reaches line 819 message": the `-1MiB` line carries the parser's message, not `key_cache_size option was set incorrectly`. Added rows: `-1MiB` not accepted; `0MiB` accepted and auto in range; ConfigProbe failed for no other reason; all SSTables BIG; the plateau is proportional to C; auto had no eviction; no control missed.
5. **Observed vs. inferred** — [inferred: no Caffeine stats] evictions are N − own: each of the N distinct keys missed at least once after the clear (series misses ≥ N − 1,000, observed) and was inserted, and nothing else removes entries.
6. **Deviations and gaps** — none in the procedure. The unit tier reads the weight, not the retained heap (gap named at the audit; the cluster tier carries the heap part). Harness defect H3 (§3) left an empty folder in the repository, removed.
7. **Core question** — the startup value becomes the key cache's maximum weight: the cached weight follows the knob (⌊C/w⌋ entries, ratio 4.000) and never exceeds it, by evicting; `0MiB` disables caching (nothing stays in the cache); a negative value never reaches the check at `DatabaseDescriptor.java:819`.

**Unit tier conclusion:** B2g row 1 — **confirmed**.

**Cluster tier**

1. **Validity** — [observed: `readback-line.txt`, `samples.csv`, `stress-*-results.txt`, `sstables-list.txt`] read-back 8/64/100 MiB and Capacity = C·2^20 in every row; 2,000,000 partitions written and read with 0 errors in each lifetime; one BIG SSTable for the table; the cache was passed at every value (evicted ≥ 0.8 M entries); the B3h control met its frozen expectation in all three lifetimes (+20,000 entries, 20,000 misses); same heap flags and yaml except the knob line (`yaml-overrides.txt`). Valid.
2. **Readings** — the whole-JVM live heap grows by about 191 B per extra cached entry while the weigher counts 88 B; the entry count and weight are exact.
3. **Matched row** — B3g added row "(i)–(v) hold but (vi) or (vii) fails → the cap bounds the weight estimate, not the real heap; Not confirmed for the heap part" [observed: (i) exact; (ii) max Size/Capacity 0.99999; (iii) full, Entries = Capacity/w_c; (iv) w_c 88.00 in all three, ratios 8.000 and 12.500; (vi) instances = Entries exactly; **(vii) D/S = 2.173 and 2.168, outside 0.5–2.0**]. (v) holds at 8 and 64 MiB and **fails as written at auto**: Entries 1,191,563 is not < 1,000,000 (its eviction part holds: 1,979,967 misses against 1,191,563 entries left). The 1,000,000 bound was set at the audit on the file's 120 B estimate; the shakedown's w_c of 88 B, read before run 1, already implied ≈ 1.19 M entries at 100 MiB and was not noticed. It is not amended (a reading exists); the tier is Not confirmed through (vii) whatever (v) says.
4. **Excluded rows** — row 1 ("cap governs actual heap use"): needs (vii) (and (v)); not met. "entries ≈ 2,000,000 at 8 MiB": 95,325. "entries ≈ 0": 95,325–1,191,563. Added rows: read-back matched; Size never above 1.01 × Capacity (so "cap not enforced" does not apply); Size ≥ 0.9 Capacity at every value; all SSTables BIG; 0 stress errors; no control missed.
5. **Observed vs. inferred** — [inferred: histogram class counts] the heap outside the weight is Caffeine's per-entry node (`PSMW`, 40 B, instances = entries + 5) and the backing `ConcurrentHashMap` node (32 B) plus its table and Caffeine's frequency sketch (`[J`, grows with the maximum): k64 − k8 these add ≈ 59.0 MB, ≈ 1.0 × S; with the weighed objects (`KeyCacheKey` 32 B + key `byte[]` 32 B + `RowIndexEntry` 24 B = 88 B) they account for ≈ 120 of the 127.6 MB of D. The weigher counts the key and value objects but not the cache's own structure (`CaffeineCache.java:61-70`).
6. **Deviations and gaps** — no heap dump (instances and class totals only). (v)'s 1,000,000 bound is a design slip in the frozen relation (point 3). `nodetool info` read at three points instead of every 30 s, by amendment.
7. **Core question** — usage follows the constraint: entries plateau at exactly Capacity/88 B (1 : 8 : 12.5), the weighted size never passes C, and the excess is evicted. The real live heap also follows the knob linearly and is bounded by it, but at ≈ 2.17 × C, not C: the knob caps the cache, with a constant factor the weigher does not count.

**Cluster tier conclusion:** B3g added row "(vi) or (vii) fails" — **not confirmed** (for the heap part; entry count and weighted size behave as claimed).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck.py` (written separately from the harness; re-reads the raw `p1-*.out`, `stage4.out`, `TEST-*.xml`, each lifetime's `system.log`, `samples.csv`, `histo-1-end.txt`, `stress-*.log`, `sstables-list.txt`, `tablestats-after-compact.txt` under the full log root): **75 relation checks, 72 hold, 3 fail** — exactly the three the conclusion names (`kauto (v)`, `(vii)` k64–k8, `(vii)` kauto–k8); its consistency block confirms "unit tier all relations hold" and "cluster failures are exactly the ones the conclusion names", exit 0 (`run1/selfcheck.out`).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | knob per JVM and read-back per lifetime, junit counts, formats, calibration one entry per read, stress partitions and errors, one BIG SSTable, both controls in every JVM/lifetime re-read. |
| 2. Readings | yes | max weightedSize over all unit samples; max Size over all 35 rows per lifetime; live totals from the full histograms. |
| 3. Matched row | yes | B2f (i)–(iv) each against its frozen tolerance; B3f (i)–(vii) recomputed; D/S = 2.173 and 2.168 recomputed from the `Total` lines and the last main-done rows. |
| 4. Excluded rows | yes | every row of B2g/B3g with the added rows addressed in §4.2 with a reading. |
| 5. Observed vs. inferred | yes | the unit eviction inference rests on the `misses` meter (≥ 199,000 per series, re-read); the heap attribution rests on histogram class counts and is labelled inferred; the verdict (Not confirmed) does not depend on it, only on (vii)'s observed ratio. |
| 6. Deviations and gaps | yes | §3 harness defects; (v) bound slip recorded, not amended. |
| 7. Core question — the steps follow the audited logic | yes | read-back → plateau ∝ C → evictions → instances = entries → live heap vs weight → controls, in B2e/B3e's order. |

### 5.2 Run 2?

**No** (decided 2026-10-25). Every load-bearing figure is observed and recomputed by the self-check; the unit result is exact (⌊C/w⌋, exact control weights), and the cluster's Not confirmed rests on an observed ratio (2.17) that is the same at two independent pairs (64 − 8 and auto − 8) and far from the band edge; run 2 would not change the matched row.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 7. Cluster re-run ("run 1b") after the B3f (v), (vii) amendment — 2026-10-25

Added by a stage-4 session, Claude Opus 5.5 (claude-opus-5-5), 2026-10-25, **authorised by the user (Yang, the advisor) on 2026-10-25**.
Sections 1–6 above are run 1 as filed and are not changed; run 1's excerpts under `run1/` are untouched. The unit tier is closed and
was not re-run.

### 7.1 Frozen version and harness

| Field | Content |
|---|---|
| **Why** | Run 1's cluster tier was Not confirmed through two frozen relations that did not come from the source: (v)'s "< 1,000,000 entries" at auto (set on the file's 120 B estimate; 1,191,563 cached) and (vii)'s 0.5–2.0 band (an estimate; 2.173 and 2.168 read) (§4.2). README: a wrong §9a "is a dated amendment to the case file and the affected tier starts again". The user authorised the amendment and a re-run of the whole cluster tier on 2026-10-25. |
| **Amendment** | `Amendment 2026-10-25 (after run 1, authorised by the user) — B3f (v), (vii)`, placed under the B3f amendment, and `… — B3g, rows that depend on B3f (v), (vii)`, under the B3g amendment. It says plainly that it follows run 1's readings. **Per-entry weight from the source:** weigher = key + value `unsharedHeapSize()` (`CaffeineCache.java:61-69`), jamm layout (`ObjectSizes.java:31,56-59,251-254`; header 12 B, reference 4 B, array header 16 B, 8-byte alignment): `KeyCacheKey` shell (`tableId`, `indexName`, `desc`, `key`: `CacheKey.java:27-28`, `KeyCacheKey.java:31,33,37`) 28 → **32 B**; key `byte[10]` (stress `fixed(10)`, `SettingsCommandPreDefined.java:82,108`; `KeyCacheKey.java:43,59-62`) 26 → **32 B**; plain `RowIndexEntry(position)` for an unindexed partition (`RowIndexEntry.java:141,199-203,341-348`, `AbstractRowIndexEntry.java:33`, cached at `BigTableReader.java:325,343`) 20 → **24 B**; **w_s = 88 B** (any key of 9–16 B weighs the same). **(v):** main-read misses ≥ 1,960,200 and Entries within **±0.5 %** of ⌊Capacity/88⌋ = 95,325 · 762,600 · 1,191,563 (tolerance: < 1 entry of evictor slack, `AddTask.run` → `evictEntries`; ≤ 200 system-table keys of other lengths, each displacing ≤ 2 entries, ≤ 0.42 % at 8 MiB). **(vii):** D/S within **R_pred ± 0.25**, R_pred = [ΔE × 160 + 4 ΔL + 8 ΔT] / S, from `caffeine-3.1.8.jar` (`javap`): node class **`PSMW`** (strong keys and values, weighted maximum, no expiry/refresh; `NodeFactory.getClassName`) 12 + 4 refs + 3 ints = **40 B**; backing `ConcurrentHashMap$Node` (`hash`, `key`, `val`, `next`) 28 → **32 B**; no key/value wrapper with strong references; map table `Node[L]`, 4 B per slot, L = smallest power of two ≥ 32 with E < 0.75 L (JDK 11 resize at 0.75 n); frequency sketch `long[T]`, T = max(8, ceilPow2(mappingCount)) (`AddTask.run` → `FrequencySketch.ensureCapacity` once weighted size ≥ max/2). At E = E_s: **R_pred = 2.006 (64, 8), band 1.756–2.256; 2.063 (auto, 8), band 1.813–2.313.** The ± 0.25 is an allowance for reachable heap outside the cache that differs between lifetimes, taken over unchanged from the counter-cache file's pre-reading band (the source does not fix it). The amendment states that run 1's 2.173 / 2.168 and 1,191,563 entries lie inside the new values, so it is tested by the re-run, not by run 1. B1, B3f (i)–(iv), (vi), B3h and the unit tier unchanged. |
| **Case-file version** | sha256 **`59fe55f86846d144d02624ee192116309954d199066b714bf6aa9b0f035045ce`** (new row in `_INDEX.md` §4, "re-frozen after run 1 for cluster re-run (B3f (v), (vii)), authorised by the user"); earlier rows (`cbb132a9…`, `3a87b714…`) kept. Hashed at 16:41 EDT, before any re-run reading (first re-run command 16:42:22); section D was filled afterwards. Nothing committed. |
| **Harness** | Run 1's harness with change H4 (§3) only (node and log paths). sha256 prefixes at the re-run: `cluster-run.sh` `dbbeaa46` (run 1 `08ecce93`), `cluster-chain.sh` `0beb45ad` (run 1 `ab02489c`); unchanged `KeyCacheSampler.java` `350ed2a4`. Command: `C=$W/cassandra-run18 KCS_NODE=$W/node-kcs2 KCS_OUT=$W/logs/key_cache_size-applySimpleConfig/cluster-run2 cluster-chain.sh` (lifetimes 8MiB, 64MiB, auto in the frozen order, each with the B3h (a) control; no shakedown — the harness was checked before run 1). Self-check: [`run1b-cluster/selfcheck.py`](key_cache_size-applySimpleConfig-keyCacheSizeInMiB--autonomous/run1b-cluster/selfcheck.py) (extends `run1/selfcheck.py`; `--relations amended` or `run1`). |

### 7.2 Environment

Same host and storage as run 1 (§2). Cluster tier 2026-10-25 16:42:22 – 16:50:51 EDT. Fresh clone `$W/cassandra-run18` from `~/cassandra-src`,
`b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`), no local change (`git status` clean), `ant -Dlocal.repository=$W/m2
build-test` `BUILD SUCCESSFUL` in 51 s; `build/lib/jars/caffeine-3.1.8.jar`, `jamm-0.4.0.jar`. Node `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`, data
under `$W/node-kcs2` (wiped before and after each lifetime; removed at the end). Free disk 145 GiB. Pre-check: no `CassandraDaemon` or stress
process, ports 7000/7199/9042/9091 free; the same at the end. Full logs (3.8 MB): `~/Library/Caches/stage4/logs/key_cache_size-applySimpleConfig/cluster-run2/`
(`clone-build-run18.log`, `driver.out`, `chain.out`, `k8/`, `k64/`, `kauto/` as run 1, `selfcheck.out`). Excerpts:
[`run1b-cluster/`](key_cache_size-applySimpleConfig-keyCacheSizeInMiB--autonomous/run1b-cluster/) (`chain.out`, `driver.out`, `selfcheck.out`,
`cluster/<label>/` with the same files as run 1's `run1/cluster/<label>/`).

### 7.3 Readings

From `run1b-cluster/cluster/<label>/summary.txt`, `samples.csv`, `histo-totals.txt`, `histo-1-end-cache-classes.txt`, `readback-line.txt`,
`stress-*-results.txt`, `sstables-list.txt`; recomputed by `selfcheck.py`. Every stress run 2,000,000 / 20,000 / 2,000,000 partitions, 0 errors;
`keyspace1.standard1` one SSTable `nb-16-big-Data.db` after the compaction, all 19 `Data.db` files BIG; 35–36 sampler rows per lifetime, 0 error rows;
0 `java.lang.OutOfMemoryError`; the four WARN lines per lifetime are start-up notices (crypto provider, jemalloc, JMX remote, new host ID).

| Value | Observable | 8MiB (k8) | 64MiB (k64) | auto (kauto) |
|---|---|---|---|---|
| read-back | `system.log` | `… capacity of 8 MiBs` | `… 64 MiBs` | `… 100 MiBs` |
| (i) | `Capacity` (every row) | 8,388,608 | 67,108,864 | 104,857,600 |
| (ii) | max `Size` / Capacity | 8,388,600 (0.99999) | 67,108,800 (0.99999) | 104,857,544 (0.99999) |
| B3h (a) | Entries baseline → control-done; Misses in control | 85 → 20,085 (+20,000); 20,000 | 85 → 20,085 (+20,000); 20,000 | 85 → 20,085 (+20,000); 20,000 |
| (iii) | main-done `Size`, `Entries`, w_c | 8,388,600; 95,325; 88.00 B | 67,108,792; 762,600; 88.00 B | 104,857,536; 1,191,563; 88.00 B |
| (v) amended | Misses in main read; Entries vs ⌊Cap/88⌋ | 1,979,999; 95,325 = 95,325 (0.000 %) | 1,979,978; 762,600 = 762,600 (0.000 %) | 1,979,967; 1,191,563 = 1,191,563 (0.000 %) |
| (vi) | `KeyCacheKey` / `RowIndexEntry` instances (final histo) | 95,325 / 95,325 | 762,600 / 762,600 | 1,191,563 / 1,191,563 |
| (vii) | live total, baseline → end | 52,774,304 → 71,609,120 | 51,934,920 → 197,754,232 | 52,701,864 → 279,493,344 |

Derived (`selfcheck.py`): Entries(64)/Entries(8) = 8.000, Entries(auto)/Entries(8) = 12.500; w_c = 88.000 B in all three. **(vii): D(64 − 8) =
126,145,112 B, S = 58,720,192 B, D/S = 2.148** (R_pred 2.006, band 1.756–2.256); **D(auto − 8) = 207,884,224 B, S = 96,468,936 B, D/S = 2.155**
(R_pred 2.063, band 1.813–2.313). Per extra cached entry the live heap grew by 189.0 B (k64) and 189.6 B (kauto); the derivation gives 160 B
plus the table and sketch steps (≈ 176 B and ≈ 182 B per entry with them).

Class growth hi − k8 at the end (information, not a frozen relation): `PSMW` +667,275 / +1,096,238 instances (40 B each, = ΔEntries exactly);
`ConcurrentHashMap$Node` +667,293 / +1,096,258 (32 B); `[Ljava.util.concurrent.ConcurrentHashMap$Node;` +3,145,728 / +7,340,032 B (derived
3,670,016 / 7,864,320); `[J` +7,342,208 / +15,730,200 B (derived 7,340,032 / 15,728,640).

### 7.4 Cluster re-run — conclusion and logic

1. **Validity.** The re-run used the re-frozen version (`59fe55f8…`, hashed before the first command) and ran every value and control of B3
   from the beginning in the frozen order in a fresh clone [observed: `run1b-cluster/driver.out` first line, `chain.out`]. Read-back 8/64/100 MiB
   and Capacity = C·2^20 in every row; 2,000,000 partitions written and read with 0 errors per lifetime; one BIG SSTable; the cap was passed at
   every value (≥ 0.8 M entries evicted); B3h (a) met its frozen expectation in all three lifetimes; the yaml differed only in the knob line
   (`yaml-overrides.txt`). Valid.
2. **Readings.** The cache readings repeat run 1's exactly (Entries, Size, instances, control); the live totals differ from run 1's by ≤ 1.2 MB
   per lifetime, giving D/S 2.148 and 2.155 against run 1's 2.173 and 2.168.
3. **Matched row.** B3g row 1, "cap governs actual heap use", read with the amended relations [observed: (i) exact; (ii) max Size/Capacity
   0.99999; (iii) full, Entries = Capacity/w_c; (iv) w_c 88.00 in all three, ratios 8.000 and 12.500; **(v) amended: Entries = ⌊Capacity/88⌋
   exactly at every C, misses ≥ 1,979,967**; (vi) instances = Entries; **(vii) amended: 2.148 ∈ [1.756, 2.256] and 2.155 ∈ [1.813, 2.313]**;
   B3h (a) and (b) hold]. **Tier rule: Confirmed.**
4. **Excluded rows.** "entries ≈ 2,000,000 at 8 MiB": 95,325. "entries ≈ 0": 95,325–1,191,563. Read-back or Capacity ≠ C: no. `Size` > 1.01 ×
   Capacity: never. "(i)–(v) hold but (vi) or the amended (vii) fails": both hold. "the amended (v) fails": entries exact, misses above 1,960,200.
   `Size` < 0.9 × Capacity at main-done: no. non-BIG SSTable: no. stress errors: 0. control missed: no.
5. **Observed vs. inferred.** Observed: every relation. Inferred: that the live-heap growth per entry is the cache's own structure — supported
   by the class counts (`PSMW` and `ConcurrentHashMap$Node` grow by exactly ΔEntries). Two terms of the derivation did not match the histogram
   exactly: the CHM-table class grew by 524,288 B less than derived at both pairs — the k8 lifetime's end histogram has 1,332,256 B of CHM tables
   against run 1's 807,968 B, i.e. one table of 262,144 slots instead of 131,072 there, consistent with the key cache's map having transiently passed
   the 98,304-entry resize point (the amendment had argued from the 2,048-entry write buffer that it would not); and ≈ 8.9 MB (64, 8) / 9.4 MB (auto, 8) of D
   (13.3 / 8.6 B per extra entry) is outside the derived terms (byte arrays and other classes), as in run 1. Both are inside the ± 0.25 allowance; neither
   changes the matched row.
6. **Deviations and gaps.** None against the re-frozen runbook. The amendment was written after run 1's readings were known (it says so), and
   run 1's ratios also lie inside the new bands; the re-run is an independent repeat of the whole tier at the re-frozen version, but the bands
   were not set blind. The ± 0.25 allowance is borrowed, not derived. No heap dump (class totals only).
7. **Core question.** The knob caps the key cache: entries plateau at exactly ⌊C/88 B⌋ (1 : 8 : 12.5), the weighed size never passes C, and the
   excess is evicted. The real live heap follows the knob linearly at ≈ 2.15 × the weighed size, which the source accounts for (88 B weighed +
   72 B Caffeine node and map entry per key, plus power-of-two table and sketch) within the frozen allowance.

**Conclusion (one line):** B3g row 1 with the amended B3f (v), (vii) — confirmed.

### 7.5 Self-check of the cluster re-run — AI

`selfcheck.py` (copied from `run1/selfcheck.py`, unit part dropped, the amended (v) and (vii) added under `--relations amended`, the run-1
relations kept under `--relations run1`; it re-reads `system.log`, `samples.csv`, `histo-1-end.txt`, `stress-*.log`, `sstables-list.txt`,
`tablestats-after-compact.txt` under the full log root, not the harness summaries). Output: [`run1b-cluster/selfcheck.out`](key_cache_size-applySimpleConfig-keyCacheSizeInMiB--autonomous/run1b-cluster/selfcheck.out).
- **Pass 1 (re-run raw files, amended relations):** 44 checks, **44 hold, 0 fail**.
- **Pass 2 (known answer, run 1's raw files, run-1 relations):** 41 checks, 38 hold, 3 fail — the 41 cluster lines are **identical** to
  `run1/selfcheck.out`'s cluster lines (same three failures: kauto (v), (vii) at both pairs), so the copied reader reproduces run 1.
- **Pass 3 (information, run 1's raw files, amended relations):** 44 / 44 hold — recorded because the amendment was written knowing run 1.

Raw files re-opened by hand: `kauto/samples.csv` (last main-done row: Size 104,857,536, Entries 1,191,563), `k64/histo-1-end.txt` (`Total` 197,754,232;
`PSMW` 762,605 instances), `k8/histo-1-end.txt` and run 1's (CHM tables 1,332,256 vs 807,968 B), `k8/readback-line.txt`, `driver.out` (frozen hash
before the first command).

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | re-frozen hash recorded before the run; read-backs, stress counts, SSTable formats, controls re-read |
| 2. Readings | yes | max Size over every row; live totals from the full histograms |
| 3. Matched row | yes | every B3f relation recomputed; R_pred recomputed from the measured Entries |
| 4. Excluded rows | yes | |
| 5. Observed vs. inferred | yes | the CHM-table step and the unexplained ≈ 9 MB are stated; the verdict rests on the observed ratios |
| 6. Deviations and gaps | yes | non-blind bands and the borrowed allowance stated |
| 7. Core question | yes | caps; usage and real heap follow the knob |

**Run 2?** No — 2026-10-25. The re-run repeats run 1's cache readings exactly and its heap ratios within 0.025; a further run would not change the row.

### 7.6 Verdict of the cluster re-run

**Confirmed — caps** (B3g row 1 with the amended B3f (v), (vii); controls hold). Filed in §8 as a new cluster row; the run-1 cluster row
(Not confirmed) is kept.

**End of the re-run:** no `CassandraDaemon` or `cassandra-stress` process, ports 7000/7199/9042/9091 free, `$W/node-kcs2` removed, `$W/cassandra-run18`
clean (no file added), no `build/` or log folder in the repository root (2026-10-25, after the self-check).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive.

**Claim tested (B1):** With `key_cache_size: C`, the key cache's weighted size never exceeds C MiB (beyond transient slack of a few entries) and its entry count plateaus at ≈ C / (per-entry weight) once more distinct partitions are read than fit, so key-cache heap scales with C, not with the number of keys read. A negative value is rejected at parse time (before line 819). "Confirmed" means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1: `-1MiB` rejected by the parser (never reaches line 819), `0MiB` → 0 (nothing cached), auto → 51 / 50; weightedSize ≤ cap at every sample, own = ⌊C/w⌋ = 13,107 · 52,428 (w = 80 B), ratio 4.000, evicted 186,893 · 147,572; auto (50 MiB) not reached, own = N; controls exact | caps | run 1 + self-check | 2026-10-25 |
| Cluster | **Not confirmed** — B3g added row "(i)–(v) hold but (vi) or (vii) fails": Capacity = C·2^20, Size ≤ Capacity, Entries = Capacity/88 B = 95,325 · 762,600 · 1,191,563 (1 : 8 : 12.5), instances = Entries, control +20,000; but live(64) − live(8) = 2.173 × the weight difference (2.168 for auto − 8), outside the frozen 0.5–2.0; B3f (v)'s "< 1,000,000 entries" fails as written at auto (a bound set on w = 120 B) | caps (entries and weighted size capped exactly at C; real heap bounded and proportional to C at ≈ 2.17 × C, the Caffeine node and map entry per key not being weighed) | run 1 + self-check | 2026-10-25 |
| Cluster (re-run at `59fe55f8…`, after the user-authorised B3f (v), (vii) amendment) | **Confirmed** — B3g row 1 with the amended relations: Capacity = C·2^20, Size ≤ Capacity at every sample, Entries = ⌊Capacity/88⌋ = 95,325 · 762,600 · 1,191,563 exactly (amended (v), ±0.5 %), instances = Entries, ratios 8.000 / 12.500, control +20,000; real heap D/S = 2.148 (64 − 8, band 1.756–2.256 around R_pred 2.006) and 2.155 (auto − 8, band 1.813–2.313 around 2.063) | caps (entries and weighed size capped exactly at C; the real heap follows the source-derived per-entry structure, ≈ 2.15 × the weighed size: 88 B weighed + 72 B Caffeine node and map entry per key, plus table and sketch) | cluster re-run (§7) + self-check | 2026-10-25 |

**Feedback filed:** the case file's section D (uncommitted). No section of the case amended after run 1. Recommendations for stage 3, left unapplied: (1) the claim "key-cache heap scales with C" holds in shape, but the cap is on the weight, and the real heap is ≈ 2.2 × C for small keys (Caffeine `PSMW` node 40 B + `ConcurrentHashMap$Node` 32 B + table and sketch per entry, against 88 B weighed) — A3's "weights are estimates" could name this factor; (2) B3f-type bounds on entry counts should be written in terms of the measured w, not a fixed number; (3) B4 still names `/local` paths.

**Feedback filed for the cluster re-run (2026-10-25):** the amendments `Amendment 2026-10-25 (after run 1, authorised by the user) — B3f (v), (vii)` and `… — B3g, rows that depend on B3f (v), (vii)` in the case file; a new `_INDEX.md` §4 row (`59fe55f8…`); the case file's section D (new entry); the §1 Stage 4 column (unit and cluster Confirmed — caps). The coverage count is unchanged (the case was already closed). No refutation, so no other case section is amended. Recommendation (1) above is answered by the amended (vii), which now derives the factor in B3f.

**End of run:** `pgrep -f CassandraDaemon` empty, no ConfigProbe / stress / sampler process, ports 7000/7199/9042/9091 free, `$W/node-kcs` and `$W/probe-kcs` removed, the probe test removed from `$W/cassandra-run11` and `test/conf/cassandra.yaml` restored (`git status` clean), no `build/` or log folder in the repository root (2026-10-25 09:59 EDT).
