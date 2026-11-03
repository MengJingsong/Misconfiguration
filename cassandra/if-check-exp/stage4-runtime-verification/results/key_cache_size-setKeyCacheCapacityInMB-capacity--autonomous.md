# key_cache_size-setKeyCacheCapacityInMB-capacity--autonomous — stage-4 results  <!-- file: results/key_cache_size-setKeyCacheCapacityInMB-capacity--autonomous.md -->

> **Case:** [`key_cache_size-setKeyCacheCapacityInMB-capacity--autonomous`](../../stage3-ai-deep-read/cases/key_cache_size-setKeyCacheCapacityInMB-capacity--autonomous.md)
>
> **Status:** verdict filed, 2026-10-27. **Unit: Confirmed — caps. Cluster: Confirmed — caps.** No run 2.
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/key_cache_size-setKeyCacheCapacityInMB-capacity--autonomous/`](../harness/key_cache_size-setKeyCacheCapacityInMB-capacity--autonomous/).
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-26/27, on the advisor's machine (`environment-advisor.md`).
> The verdict is against this file's own predictions and conclusions. `KeyCacheSampler.java` was copied unchanged from the
> `key_cache_size-applySimpleConfig-keyCacheSizeInMiB--autonomous` harness; the per-entry layout (88 B for a 10-byte key, Caffeine node `PSMW` 40 B)
> was taken from that case's source derivation, not from its readings.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed as sha256 `170c0311…3b3c` (service batch; checked equal to the filed `_INDEX.md` §4 row before the audit). Frozen after the step-0 audit's seventeen amendments (2026-10-27, before any run-1 reading; hashed 00:07:29 EDT, first run-1 command 00:07:35): sha256 **`3b256bb6cb8090ffda8277e5d2c153093ea42ddce556093fb59dc5040f23cad3`**, a new row in `_INDEX.md` §4. Both tiers' run 1 ran at this version (no runbook defect). Section D was filled after this hash. Nothing committed (no commit was asked for). |
| **Harness** | [`../harness/key_cache_size-setKeyCacheCapacityInMB-capacity--autonomous/`](../harness/key_cache_size-setKeyCacheCapacityInMB-capacity--autonomous/): `KeyCacheCapacityProbeTest.java` (B2c–B2e as amended; sha256 `69cf162c…`), `unit-run.sh` (`110c4eb8…`), `KeyCacheSampler.java` (copied unchanged, `350ed2a4…`), `cluster-run.sh` (B3e as amended, `1f572ebc…` after fix H1). Not committed. Instrument checks before run 1: (i) unit shakedown (N = 20,000) compiled and ran both tests, every output line present ([`shakedown/unit-shake-summary.txt`](key_cache_size-setKeyCacheCapacityInMB-capacity--autonomous/shakedown/unit-shake-summary.txt)); (ii) cluster shakedown (n = 100,000; C = 256, shrink 2, 4, 2, 1; yaml 2) ran every step and left nothing running ([`shakedown/cluster-shake-summary.txt`](key_cache_size-setKeyCacheCapacityInMB-capacity--autonomous/shakedown/cluster-shake-summary.txt)); it found harness defect H1 (§3); (iii) [`run1/selfcheck.py`](key_cache_size-setKeyCacheCapacityInMB-capacity--autonomous/run1/selfcheck.py) was written before any run-1 reading and its parsers exercised on both shakedowns; not changed afterwards. Shakedown readings are not judged. |
| **Tiers and values** | Unit (B2): one `ant testsome` JVM; `guard` (C = −1); `sweep` with N = 200,000 rows (k bigint), one BIG sstable, C = 64 (control), shrink to 1 without invalidation, 4, 2, 1, 0 MiB through `CacheService.setKeyCacheCapacityInMB`. Cluster (B3): one node, `-Xms1G -Xmx1G`, yaml `key_cache_size: 64MiB`; 1,000,000 stress partitions, one BIG sstable; C = 256 (control), shrink to 4 without invalidation, 64, 16, 8, 4 MiB by `nodetool setcachecapacity C 0 0`; then a restart at yaml `8MiB` on the same data. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27. |

### 1.1 Design audit

Citations re-read in `~/cassandra-src` at `cassandra-5.0.9` (`b5f2a54210`), the commit of the run clone, and in the run clone's
`build/lib/jars/caffeine-3.1.8.jar` with `javap -c`.

**What the source says, derived at the audit.**
- *The check* (`CacheService.java:336-342`): `capacity < 0` throws `RuntimeException("capacity should not be negative.")`; otherwise `keyCache.setCapacity(capacity × 2^20)` → `InstrumentingCache` → `CaffeineCache.setCapacity` → `policy.setMaximum` (`CaffeineCache.java:77-80`).
- *A shrink evicts at once.* `BoundedLocalCache$BoundedPolicy$BoundedEviction.setMaximum` takes `evictionLock`, calls `setMaximumSize` then `maintenance(null)` (evicts) before unlocking; `weightedSize()` takes the same lock and runs `maintenance` first if a drain is pending — so the `Size` gauge (`CacheMetrics.java:69-71`, `cache::weightedSize`) can never read above the maximum. Every B2e/B3e pass invalidates before it sets C, so as filed the setter only resized an empty cache; the shrink step was added (amendments B2b/B2e, B3b/B3e).
- *Weights.* Weigher = key + value `unsharedHeapSize()` (`CaffeineCache.java:61-69`); jamm layout: `KeyCacheKey` shell 32 B + key array (bigint `byte[8]` 24 B; stress `byte[10]` 32 B) + plain `RowIndexEntry` 24 B → w = 80 B (unit), 88 B (cluster).
- *Gate.* `ColumnFamilyStore.java:3272-3275` `isKeyCacheEnabled` = caching keys && capacity > 0 (C = 0 caches nothing). `NopCache.setCapacity` throws only for a non-zero value (`NopCacheProvider.java:37-41`), so `setcachecapacity C 0 0` is valid with the row cache off. `nodetool info` prints Size/Capacity through `FileUtils.stringifyFileSize` (`Info.java:93-101`), i.e. rounded.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: on-heap key cache, Caffeine weighted size, plus live class bytes H(C) on the cluster. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | Unit 0/1/2/4 + 64; cluster 4/8/16/64 + 256 and yaml 8. The setter has no default of its own (it takes any value at runtime); the startup default (auto) is the subject of the `applySimpleConfig` case; the starting value (unit auto 24 MiB, cluster yaml 64 MiB) is recorded. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | Unit: weight only (gap named in B2d); cluster: live class histogram H(C) (B3d). |
| A. Core question | usage driven to the limit and past it | Met | Unit 16.0 MB demand vs 1–4 MiB (3.8–15×); cluster 88 MB vs 4–64 MiB (1.3–21×), 256 MiB unbounded. |
| B. Logic | each step says what it establishes | Partly | B2e/B3e list steps; the readings tables carry the meaning. Left for stage 3. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | "≈", "about 80-120 B", "entries ≈ C·2^20/w" given exact bands with w derived (B2f, B3f amendments). |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met after amendment | Rows had meanings without verdicts; no row for an off-band fill/ratio, the shrink, the yaml comparison or an invalid run (B2g, B3g amendments). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Plateau ∝ C plus evictions (N − own with misses ≥ N − own; Entries = Capacity/w after 10^6 distinct reads); the shrink step shows eviction at the set itself. |
| B. Logic | alternative explanations and their controls | Met | C = 64 / 256 controls, invalidation, one sstable, row/counter/chunk caches off, PSMW = Entries attribution (B3h; evidence named in the B2h/B3h amendments). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3 and B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | B2a referred to a "test file below" that is not in the file; written by the harness from B2c–B2e (B2a amendment). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | Output lines, own-table count, exact JMX gauges (nodetool rounds), live histogram without `-all`, order, stop conditions (B2d, B2e, B3c–B3e amendments). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly → Met after amendment | `/local`, Linux, `-p` pid file, `ant jar stress-build`: this host's clone and node dir; stress already built by `build-test` (B2a, B3a, B4 amendments). |
| D. Runnable | workload arithmetic reaches the limit | Met | See A; node data ≈ 0.3 GB of 127 GiB free; 1 GiB heap holds ≈ 0.19 GB of cache at 10^6 entries. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `CacheService.java:101-128, 276-279, 336-342`, `CaffeineCache.java:40-95`, `ColumnFamilyStore.java:3272-3275`, `CacheMetrics.java:66-71`, `SetCacheCapacity.java:30-45`, `NodeProbe.java:1088-1094`, `NopCacheProvider.java:37-41`, `Info.java:93-101`, `Config.java:373, 468-480, 499`, `conf/cassandra.yaml:525, 538, 564, 595, 742`, `SettingsSchema.java:127-168` (no `caching` option), `KeyCacheKey.java:59-62`. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: this host's clone; test file written by the harness; output from the test log | Amendment 2026-10-27 | `/local` paths; the "test file below" does not exist. |
| 2 | B2b/B2e: runtime shrink of a full cache (C = 64 → 1, no invalidation) | Amendment 2026-10-27 | The entry pointer was otherwise exercised only on an empty cache; A3 step 2 untested. |
| 3 | B2c: exact rows, one-BIG-sstable check, w = 80 B derived, own-table count | Amendment 2026-10-27 | "≈ 80-120 B"; system keys can share the cache. |
| 4 | B2d: `KCR` output lines | Amendment 2026-10-27 | Format open. |
| 5 | B2e: order, stop condition, `@After` | Amendment 2026-10-27 | Open. |
| 6 | B2f: bands (i)–(v) | Amendment 2026-10-27 | "≈"; the added step. |
| 7 | B2g/B2h: verdict per row, added rows; control evidence | Amendment 2026-10-27 | Group B. |
| 8 | B3a: this host, node dir, start/stop | Amendment 2026-10-27 | Linux paths, `-p`. |
| 9 | B3b/B3e: shrink 256 → 4 without invalidation | Amendment 2026-10-27 | As 2. |
| 10 | B3c: exact commands; w = 88 B derived | Amendment 2026-10-27 | "≈ 90-130 B". |
| 11 | B3d: JMX sampler every 2 s; histogram without `-all`; H(C) defined | Amendment 2026-10-27 | `nodetool info` rounds Size; `-all` counts unreachable objects. |
| 12 | B3e: order, checks, shakedown | Amendment 2026-10-27 | Open. |
| 13 | B3f: bands (i)–(vi) | Amendment 2026-10-27 | "≈"; the added step. |
| 14 | B3g/B3h/B4: verdict per row, added rows; control evidence; paths | Amendment 2026-10-27 | Group B; `$WORK`. |
| 15 | A negative value on the cluster tier (`nodetool` would parse `-1` as an option; JMX `setAttribute`) | Left for stage 3 | B1's guard clause is tested by the unit tier. |
| 16 | B2e/B3e steps should say what each establishes | Left for stage 3 | Not needed for a valid run. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-26/27 EDT: step E 23:56; clone and build 23:56:44–23:57:43; audit and amendments to ≈ 00:01; unit shakedown 00:02:30–00:02:49; cluster shakedown 00:03:45–00:07:00; harness fix H1 and freeze 00:07:29; **unit run 1 00:07:35–00:08:04; cluster run 1 00:08:50–00:14:33** |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab |
| OS and kernel (step E) | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64 (T6000); 10 cores, 32 GiB RAM (34,359,738,368 B); internal SSD APFS `/dev/disk3s1`, 460 GiB, 127 GiB free; loopback 127.0.0.1, .2, .3 on `lo0` (only .1 used: one node); ports 7000, 7199, 9042, 9091 free; no Cassandra or stress process before |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit: `ant testsome` fork (`-Xmx1024m` from build.xml; start capacity auto = 24 MiB in that JVM). Node: `MAX_HEAP_SIZE=1G HEAP_NEWSIZE=200M` (`-Xms1G -Xmx1G`, read from the process command line) |
| Ant / Python | 1.10.18 / 3.8.11 (self-check, run with `-I`) |
| Local clone commit | `$W/cassandra-run45` = `~/Library/Caches/stage4/cassandra-run45`, fresh `git clone --branch cassandra-5.0.9 ~/cassandra-src`, `b5f2a54210d541339c2e7c17a794195cac0e67c2`; `ant -Dlocal.repository=$W/m2 build-test` `BUILD SUCCESSFUL` in 52 s; `git status` clean after the runs |
| Case-file commit / harness commit | uncommitted (sha256 in §1) |
| Storage for node data | local SSD, `$W/node-kcr45` (data, commit log, hints, saved caches, cdc, logs, conf), wiped before and removed after (≈ 0.3 GB data) |
| Full logs (outside the repo, 6.9 MB) | `~/Library/Caches/stage4/logs/key_cache_size-setKeyCacheCapacityInMB/` — `clone-build-run45.log`, `unit-shake/`, `unit-r1/` (`ant.log`, JUnit XML, `test.log`, `stdout.txt`, `summary.txt`, `commands.log`), `cluster-shake/`, `cluster-r1/` (`commands.log`, `summary.txt`, `system.log`, `node-L1.out`, `node-L2.out`, `samples-L1.csv`, `samples-L2.csv`, `info.txt`, `info-10s-L*.txt`, `histo-<C>.txt` full live histograms, `stress-*.log`, `sstables-L*.txt`, `yaml-tail-*.txt`, `error-warn.txt`), `selfcheck.out` |

Machine facts relied on (from `environment-advisor.md` and the session brief): all files under `$W` (no `mkdir` in `$HOME`); every
`ant` call with `-Dlocal.repository=$W/m2`; commands touching `$W`, Java or the network run outside the tool sandbox; no `setsid`
(node started as a tracked `bin/cassandra -f … < /dev/null &` process, stopped by `nodetool drain` then `kill <pid>`); the daemon and
stress names split in the scripts' `pgrep`/`pkill` patterns (`Cassandra[D]aemon`, `Stres[s]`); BSD `sed -i ''`; no jmxterm (own JMX
sampler; `nodetool sjk` not used); `jstat` not used (live class histogram from `jcmd GC.class_histogram`, after `GC.run`); test stdout read
from `build/test/logs/**/TEST-<class>.log`; the unit yaml's read thresholds are irrelevant here (single-row internal reads); stress reads use
the write's (default) column spec; shakedowns before run 1; long steps in the background, polled; bounds derived from source; `selfcheck.py`
written before readings; node `system.log` times are UTC. No guardrail is on the path (key cache lookups and a JMX/nodetool capacity set; no
guardrail reads `key_cache_size` in 5.0.9), so the authenticator was left as shipped.

## 3. Runbook defects

None in the case file: both tiers ran as amended at the frozen version.

Harness defects (no case-file change, no effect on a reading):

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| H1 | cluster shakedown | B3b/B3e shrink window | `sleep 6` after the `shrink` phase gave exactly 3 sampler rows (2 s cadence); a timing slip could give 2, short of the amendment's "three samples" | `sleep 7` (run 1 got 4 `shrink` rows) | AI, 2026-10-27, before the freeze and run 1 | none |

## 4. Run 1

**Scope:** both tiers, all values in §1. **Command logs:** [`run1/unit/commands.log`](key_cache_size-setKeyCacheCapacityInMB-capacity--autonomous/run1/unit/commands.log),
[`run1/cluster/commands.log`](key_cache_size-setKeyCacheCapacityInMB-capacity--autonomous/run1/cluster/commands.log). Excerpts under
[`run1/`](key_cache_size-setKeyCacheCapacityInMB-capacity--autonomous/run1/) (`unit/`: `summary.txt`, `stdout.txt` with all 1,000 sample lines,
`junit-testsuite.txt`; `cluster/`: `summary.txt`, `samples-L1.csv`, `samples-L2.csv`, `info*.txt`, `histo-<C>-cache-classes.txt`,
`stress-*-results.txt`, `sstables-L*.txt`, `yaml-tail-*.txt`, `system-log-excerpt.txt`, `error-warn.txt`; `selfcheck.out`).

### 4.1 Readings

**Unit tier** (JUnit `Tests run: 2, Failures: 0, Errors: 0`; `KCR done`; one sstable `big/nb`, `caching_keys=true`; 200 samples per pass)

| Test or step | Result | Evidence |
|---|---|---|
| `guard`, C = −1 | `java.lang.RuntimeException`, `capacity should not be negative.`; capacity 25,165,824 before and after | `run1/unit/summary.txt` |
| C = 64 (control) | own = size = **200,000**, weighted 16,000,000 (w = 80.0 B), misses 200,000, hits 0 | `summary.txt` |
| shrink 64 → 1, no invalidation | before: weighted 16,000,000, own 200,000; **right after the call: weighted 1,048,560, size = own 13,107, capacity 1,048,576** | `summary.txt` |

| C (MiB) | capacity | max weighted (200 samples + final) | final weighted (fill) | own = size | C·2^20/80 | own ratio | evicted (N − own, inferred) | misses / hits |
|---|---|---|---|---|---|---|---|---|
| 4 | 4,194,304 | 4,194,240 | 4,194,240 (0.99998) | 52,428 | 52,428.8 | – | 147,572 | 200,000 / 0 |
| 2 | 2,097,152 | 2,097,120 | 2,097,120 (0.99998) | 26,214 | 26,214.4 | 0.5000 | 173,786 | 200,000 / 0 |
| 1 | 1,048,576 | 1,048,560 | 1,048,560 (0.99998) | 13,107 | 13,107.2 | 0.5000 | 186,893 | 200,000 / 0 |
| 0 | 0 | 0 | 0 | 0 | – | – | 200,000 (none cached) | 200,000 / 0 |

**Cluster tier** (read-back `Initializing key cache with capacity of 64 MiBs` then `… 8 MiBs`; `-Xms1G -Xmx1G` in both lifetimes; every stress
run 1,000,000 partitions, 0 errors (write 30 s, reads 24–27 s); `keyspace1.standard1` one sstable `nb-16-big-Data.db` in both lifetimes, every
`Data.db` BIG; 93 + 22 sampler rows, 0 error rows; `system.log` 0 ERROR, 0 `OutOfMemoryError`; row and counter cache capacity `0 bytes` at
start and end of both lifetimes)

| Pass | Capacity (every row) | max Size over the pass's rows | Size / Entries at `<C>-done` | w_c | ⌊C·2^20/88⌋ | `PSMW` / `KeyCacheKey` instances | H(C) (B) | k(C) |
|---|---|---|---|---|---|---|---|---|
| 256 (control) | 268,435,456 | 88,000,080 | 88,000,080 / **1,000,001** | 88.0 | – | 1,000,006 / 1,000,001 | 128,013,664 | – |
| shrink 256 → 4 (4 rows) | 4,194,304 | 4,194,256 (first row after the call) | 4,194,256 / 47,662 | 88.0 | 47,662 | – | – | – |
| 64 | 67,108,864 | 67,108,792 | 67,108,792 / 762,600 | 88.000 | 762,600 | 762,605 / 762,600 | 97,626,616 | 1.4547 |
| 16 | 16,777,216 | 16,777,192 | 16,777,192 / 190,650 | 88.000 | 190,650 | 190,655 / 190,650 | 24,417,016 | 1.4554 |
| 8 | 8,388,608 | 8,388,592 | 8,388,592 / 95,325 | 88.000 | 95,325 | 95,330 / 95,325 | 12,215,416 | 1.4562 |
| 4 | 4,194,304 | 4,194,256 | 4,194,248 / 47,662 | 88.000 | 47,662 | 47,667 / 47,662 | 6,114,552 | 1.4578 |
| yaml 8 (restart) | 8,388,608 | 8,388,600 | 8,388,592 / 95,325 | 88.000 | 95,325 | 95,330 / 95,325 | 12,215,416 | (1.4562) |

H(C) = bytes(`KeyCacheKey`) + bytes(`big.RowIndexEntry`) + Σ bytes(`com.github.benmanes.caffeine.cache.*`) + 32 × instances(`KeyCacheKey`)
(B3d amendment), from the full live histograms; e.g. 64: 24,403,200 + 18,302,400 + 30,504,200 (`PSMW`) + ≈ 13 kB (other Caffeine classes) +
24,403,200. Mean of k(16), k(8), k(4) = 1.4565. `nodetool info` every 10 s (context) shows the same entries with rounded sizes
(`info-10s-L*.txt`), e.g. at the end `entries 47662, size 4 MiB, capacity 4 MiB`.

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — JUnit 2 tests, 0 failures, 0 errors; `KCR done`, no `KCR error`; one BIG sstable; all five passes present with 200 samples
   each [observed: `run1/unit/junit-testsuite.txt`, `stdout.txt`]. The limit is passed: demand 16,000,000 B against 1–4 MiB [observed: C = 64
   pass]. Valid.
2. **Readings** — nothing unusual; every figure equals the derived value to the entry (own = ⌊C·2^20/80⌋).
3. **Matched row** — B2g row 1 with the B2f amendment's (i)–(iv): (i) own 200,000, weight 16,000,000 = N·80; (ii) max weighted ≤ C·2^20 at every
   sample, fill 0.99998, own within 0.002 % of C·2^20/80, ratios 0.5000, misses 200,000 ≥ N − own; (iii) C = 0: 0 at every sample;
   (iv) shrink: 1,048,560 ≤ 2^20 at once, capacity 2^20 [observed: `stdout.txt`]. **Confirmed — caps.**
4. **Excluded rows** — row 2 (weighted > C·2^20 + 2w): max 0.99998·C·2^20 [observed]. Row 3 (own = N at C = 1): 13,107 [observed]. Row 4
   (control < N): 200,000 [observed]. Row 5 (−1 accepted): refused, capacity unchanged [observed]. Added (a) (shrink > 2^20): 1,048,560
   [observed]; (b) (off-band): none [observed]; (c) (invalid): no [observed].
5. **Observed vs. inferred** — evictions are inferred as N − own: every key missed once after the clear (misses 200,000, observed) and
   was inserted, and nothing else removes entries [inferred: source, `KeyCacheSupport.java:80-87`]. The shrink's eviction is observed directly
   (size 200,000 → 13,107 across the call).
6. **Deviations and gaps** — none against the frozen runbook. The tier reads the weight, not the retained heap (gap named in B2d).
7. **Core question** — the runtime setter sets Caffeine's maximum weight: the cached weight never exceeds C·2^20, the entry count is exactly
   ⌊C/80 B⌋ and halves with C, C = 0 caches nothing, a shrink of a full cache evicts at the call, and −1 is refused.

**Conclusion (unit tier):** B2g row 1 — **confirmed — caps**.

**Cluster tier**

1. **Validity** — every B3g added-row (d) condition is absent: 0 stress errors and 1,000,000 partitions in all seven stress runs, read-back
   64 and 8 MiB, one BIG sstable before both lifetimes, node alive throughout (sampler rows without error), yaml tails as amended [observed:
   `run1/cluster/summary.txt`, `stress-*-results.txt`, `sstables-L*.txt`, `yaml-tail-*.txt`, `samples-L*.csv`]. The limit is passed at every
   capped C (control 1,000,001 entries = 88.0 MB > 64 MiB). Valid.
2. **Readings** — nothing unusual. Two `Prepared statement recreation error` WARN lines at the yaml restart (the node dropped stress's
   preloaded statements; stress re-prepared them and its read had 0 errors) [observed: `error-warn.txt`].
3. **Matched row** — B3g row 1 with the B3f amendment's (i)–(vi): (i) control Entries 1,000,001, Size 88,000,080; (ii) Capacity = C·2^20 in every
   row; Size ≤ Capacity in every row after each set; fill ≥ 0.99999; w_c 88.000; Entries = ⌊C·2^20/88⌋ exactly; (iii) H decreasing 97.6 →
   24.4 → 12.2 → 6.1 MB, k 1.4547–1.4578 ∈ [1.0, 2.5], each within 0.1 % of the mean; (iv) `PSMW` = Entries + 5 in every histogram; (v) shrink:
   first row after the call Size 4,194,256 ≤ 4·2^20, Entries 47,662; (vi) yaml 8 = runtime 8 exactly (95,325 entries, 8,388,592 B)
   [observed: `samples-L*.csv`, `histo-*-cache-classes.txt`]. **Confirmed — caps.**
4. **Excluded rows** — row 2 (H not decreasing): decreasing [observed]. Row 3 (Size > Capacity): no row over [observed]. Row 4 (control
   < 10^6): 1,000,001 [observed]. Added (a) (shrink above cap): 4,194,256 [observed]; (b) (off-band): none [observed]; (c) (yaml ≠ runtime):
   identical [observed]; (d) (invalid): no [observed].
5. **Observed vs. inferred** — H(C) includes an estimate for the key arrays (32 B × instances, as the file prescribes: a 10-byte array is
   26 → 32 B), not a measurement of `[B` [inferred: jamm layout]. That the retained heap per stress entry outside the weight is Caffeine's
   `PSMW` node is supported by `PSMW` instances = Entries + 5 [observed]. The backing `ConcurrentHashMap$Node` (32 B per entry) and the
   frequency sketch are outside H(C) by the file's definition, so H(C) is not the whole live-heap cost of the cache (the
   `applySimpleConfig` case measured ≈ 2.15 × the weight for the whole JVM).
6. **Deviations and gaps** — none against the frozen runbook; harness fix H1 before the freeze. Stress's default warmup (as written) reads
   keys of the same population before the counted reads; it adds requests, not distinct keys (control Entries 1,000,001).
7. **Core question** — on a node, `nodetool setcachecapacity` (and the yaml value) caps the key cache: the weighed size never exceeds
   C·2^20, entries plateau at exactly ⌊C/88 B⌋ (762,600 : 190,650 : 95,325 : 47,662 = 16 : 4 : 2 : 1), a shrink of a full 88 MB cache to
   4 MiB takes effect at the call, and the retained key cache objects H(C) follow C linearly at k ≈ 1.456.

**Conclusion (cluster tier):** B3g row 1 — **confirmed — caps**.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

[`run1/selfcheck.py`](key_cache_size-setKeyCacheCapacityInMB-capacity--autonomous/run1/selfcheck.py), written before any run-1 reading and
not changed afterwards; it re-reads the raw test log and JUnit XML (unit) and, for the cluster, the raw `samples-L1/L2.csv`, the full
`histo-<C>.txt`, `stress-*.log`, `system.log`, `sstables-L*.txt`, `yaml-tail-*.txt`, `info.txt` under the full log root, and recomputes every
relation and the row: **92 checks, 92 hold, 0 fail** (unit 30 / 30, row "Confirmed - caps (B2g row 1)"; cluster 62 / 62, row "Confirmed - caps
(B3g row 1)") ([`run1/selfcheck.out`](key_cache_size-setKeyCacheCapacityInMB-capacity--autonomous/run1/selfcheck.out), exit 0). Raw files
re-opened by hand as well: `histo-64.txt` (`PSMW` 762,605 / 30,504,200 B; `KeyCacheKey` 762,600 / 24,403,200 B; `RowIndexEntry` 762,600 /
18,302,400 B; H recomputed 97,626,616), `samples-L1.csv` `shrink-set`/`shrink` rows (the `shrink-set` row, taken before the call returned,
still shows 256 MiB; all four `shrink` rows 4,194,256 / 47,662), an awk count of rows with Size > Capacity in the capped passes (0),
`stress-read-4.log` totals, and the guard line in `test.log`.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | JUnit counts, `KCR done`, sstable line; stress totals, read-back, sstable lists, yaml tails, OOM count, sampler error rows. |
| 2. Readings | yes | Every unit sample and pass line; every cluster sampler row per phase; H from the full histograms. |
| 3. Matched row | yes | Each B2f/B3f amended relation recomputed against its frozen band. |
| 4. Excluded rows | yes | Each excluded row's reading re-read. |
| 5. Observed vs. inferred | yes | The eviction inference rests on observed misses; H's key-array term is the file's estimate, labelled; the verdict does not depend on it (without it k is 1.091–1.094, still within [1.0, 2.5]). |
| 6. Deviations and gaps | yes | H1 only; stress warmup as written. |
| 7. Core question — the steps follow the audited logic | yes | setter → Caffeine maximum → eviction (at the set and on insert) → weight ≤ C, entries ∝ C → retained cache objects ∝ C; controls hold. |

### 5.2 Run 2?

**No** — decided 2026-10-27. Every load-bearing figure is observed and recomputed by an independent script; both tiers match their
derived values to the entry (own and Entries = ⌊C·2^20/w⌋), the cluster yaml and runtime paths give identical readings, and the result
neither refutes the case nor confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive.

**Claim tested (B1):** "For any key cache capacity C set through `setKeyCacheCapacityInMB(C)` (or `key_cache_size: C MiB`), the key cache's
weighted size stays at or below C×2^20 bytes (plus at most a few entries' weight) however many distinct keys are read, and the retained heap of
key cache objects scales linearly with C; a negative C is refused." "Confirmed" means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1: weighted ≤ C·2^20 at every sample for C = 4/2/1 MiB, own = ⌊C·2^20/80⌋ = 52,428 · 26,214 · 13,107 (ratios 0.5000), evicted 147,572 · 173,786 · 186,893; C = 0 caches nothing; a shrink 64 → 1 MiB of a full cache leaves 1,048,560 B at once; −1 refused, capacity unchanged | caps | run 1 + self-check | 2026-10-27 |
| Cluster | **Confirmed** — B3g row 1: Size ≤ Capacity in every sampler row at 64/16/8/4 MiB, Entries = ⌊C·2^20/88⌋ = 762,600 · 190,650 · 95,325 · 47,662 exactly; control 1,000,001 entries at 256 MiB; shrink 256 → 4 MiB effective at the first sample (4,194,256 B); retained key cache objects H(C) 97.6 / 24.4 / 12.2 / 6.1 MB, k = 1.455–1.458; `PSMW` = Entries + 5; yaml 8 identical to runtime 8 | caps | run 1 + self-check | 2026-10-27 |

**Feedback filed:** the case file's section D (uncommitted); the seventeen step-0 amendments are in the case file, dated, with the sha256
as a new row in `_INDEX.md` §4; `_INDEX.md` §1 Stage 4 column updated. The Estimate line is left as filed. No section was
amended for a refutation (none occurred). Recommendations for stage 3, left unapplied: §1.1 #15 and #16; and H(C) as defined leaves out the
backing `ConcurrentHashMap` node and the frequency sketch, so k ≈ 1.46 is a lower bound of the whole live-heap factor (≈ 2.15 in the
`applySimpleConfig` case's whole-JVM measurement).

**End of run:** no `CassandraDaemon`, stress or sampler process; ports 7000/7199/9042/9091 free; `$W/node-kcr45` removed; the probe test
removed from `$W/cassandra-run45` (`git status` clean); no `build/` or log folder in the repository root (2026-10-27, after the self-check).
