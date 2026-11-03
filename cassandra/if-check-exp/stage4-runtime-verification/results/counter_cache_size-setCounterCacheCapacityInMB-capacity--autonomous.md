# counter_cache_size-setCounterCacheCapacityInMB-capacity--autonomous — stage-4 results  <!-- file: results/counter_cache_size-setCounterCacheCapacityInMB-capacity--autonomous.md -->

> **Case:** [`counter_cache_size-setCounterCacheCapacityInMB-capacity--autonomous`](../../stage3-ai-deep-read/cases/counter_cache_size-setCounterCacheCapacityInMB-capacity--autonomous.md)
>
> **Status:** verdict filed, 2026-10-27. **Unit: Confirmed — caps. Cluster: Confirmed — caps.** No run 2.
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/counter_cache_size-setCounterCacheCapacityInMB-capacity--autonomous/`](../harness/counter_cache_size-setCounterCacheCapacityInMB-capacity--autonomous/).
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-27, on the advisor's machine (`environment-advisor.md`).
> The verdict is against this file's own predictions and conclusions. Reused harness tools: `CounterCacheSampler.java` copied unchanged from
> the `counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous` harness; `unit-run.sh`, `cluster-run.sh` and the probe test
> adapted from the `key_cache_size-setKeyCacheCapacityInMB-capacity--autonomous` harness (structure only). Every weight, band and expected value
> was derived in this session from the pinned source and the Caffeine jar, not taken from another case file or results file.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed as sha256 `b3bea7cd…fc31` (service batch; checked equal to the filed `_INDEX-advisor.md` §2 row before the audit). Frozen after the step-0 audit's seventeen amendments (2026-10-27, before any run-1 reading; hashed 00:32:27 EDT, first run-1 command 00:32:43): sha256 **`5a021af5383d67586183c310ce7baf662efdeb040da81c5d9b1a047938d63869`**, a new row in `_INDEX-advisor.md` §2. Both tiers' run 1 ran at this version (no runbook defect). Section D was filled after this hash. Nothing committed (no commit was asked for). |
| **Harness** | [`../harness/counter_cache_size-setCounterCacheCapacityInMB-capacity--autonomous/`](../harness/counter_cache_size-setCounterCacheCapacityInMB-capacity--autonomous/): `CounterCacheCapacityProbeTest.java` (B2c–B2e as amended; sha256 `6648c136…`), `unit-run.sh` (`5d5fcd8d…`), `CounterCacheSampler.java` (copied unchanged, `c24b7224…`), `cluster-run.sh` (B3e as amended, `99cc7c23…`). None changed after the shakedowns. Not committed. Instrument checks before run 1: (i) unit shakedown (N = 20,000) compiled and ran both tests, every output line present ([`shakedown/unit-shake-summary.txt`](counter_cache_size-setCounterCacheCapacityInMB-capacity--autonomous/shakedown/unit-shake-summary.txt)); (ii) cluster shakedown (n = 40,000; C = 64, shrink 1, 4, 2, 1; yaml 2) ran every step, read back both capacities and left nothing running ([`shakedown/cluster-shake-summary.txt`](counter_cache_size-setCounterCacheCapacityInMB-capacity--autonomous/shakedown/cluster-shake-summary.txt)); (iii) [`run1/selfcheck.py`](counter_cache_size-setCounterCacheCapacityInMB-capacity--autonomous/run1/selfcheck.py) was written before any run-1 reading and run on both shakedowns; it had a format-string bug that crashed its cluster part, which I did not notice until run 1 (fix S1, §3). Shakedown readings are not judged. |
| **Tiers and values** | Unit (B2): one `ant testsome` JVM; `guard` (C = −1); `sweep` with N = 200,000 distinct counter cells (`k int`, one `counter` column), C = 64 (control), shrink to 1 without invalidation, then 4, 2, 1, 0 MiB through `CacheService.setCounterCacheCapacityInMB`. Cluster (B3): one node, `-Xms2G -Xmx2G`, yaml `counter_cache_size: 64MiB`; per pass `cassandra-stress counter_write n=400000` (2,000,000 distinct cells); C = 256 (control), shrink to 8 without invalidation, then 32, 16, 8 MiB by `nodetool setcachecapacity 0 0 C`; then a restart at yaml `16MiB` with one more pass. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27. |

### 1.1 Design audit

Citations re-read in `~/cassandra-src` and in the run clone at `cassandra-5.0.9` (`b5f2a54210`), and in the run clone's
`build/lib/jars/caffeine-3.1.8.jar` with `javap -c -p`.

**What the source says, derived at the audit.**
- *The check* (`CacheService.java:344-350`): `capacity < 0` throws `RuntimeException("capacity should not be negative.")`; otherwise `counterCache.setCapacity(capacity × 2^20)` → `InstrumentingCache.setCapacity` → `CaffeineCache.setCapacity` → `policy.setMaximum` (`CaffeineCache.java:77-80`).
- *A shrink evicts at once.* `BoundedEviction.setMaximum` takes `evictionLock`, calls `setMaximumSize` then `maintenance(null)` before it unlocks; `weightedSize()` takes the same lock and runs `maintenance` if a drain is pending. So the `Size` gauge (`CacheMetrics.java:70`) cannot read above the maximum. As filed, every pass invalidates before it sets C, so the setter only resized an empty cache. I added a shrink step (amendments B2b/B2e, B3b/B3e).
- *Inserts.* Every applied counter update looks the cell up in the cache (`CounterMutation.java:213-216`) and then puts the new (clock, count) (`updateWithCurrentValue`, 231-240 → `ColumnFamilyStore.putCachedCounter`, 2506-2511). Both are skipped when capacity is 0. The CQLTester internal path reaches the same `CounterMutation.apply()` (`ModificationStatement.java:691-692`, `SingleTableUpdatesCollector.java:107`).
- *Weights.* Weigher = key + value `unsharedHeapSize()` (`CaffeineCache.java:61-69`); the jamm shallow layout gives `CounterCacheKey` 32 B + partition key array + cell-name array (`CompositeType.build`: 2-B length + name + 1 end byte) + `ClockAndCount` 32 B. That is w = 112 B in the unit test (`byte[4]`, `byte[4]`) and 120 B for stress (`byte[10]`, `byte[5]`). The Caffeine node `PSMW` is 40 B (`javap -p`).

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: on-heap counter cache; Caffeine weighted size, plus live class bytes H(C) on the cluster. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | Unit 0/1/2/4 + 64; cluster 8/16/32 + 256 and yaml 16. The runtime setter has no default of its own. The startup default (auto) is the subject of the `applySimpleConfig` case. The starting value (unit auto 12 MiB, cluster yaml 64 MiB) is recorded. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | Unit: weight only (gap named in B2d). Cluster: live class histogram H(C) (B3d). |
| A. Core question | usage driven to the limit and past it | Met | Unit demand 22.4 MB against 1–4 MiB (5.3–21×). Cluster demand 240 MB against 8–32 MiB (7.2–28.6×); 256 MiB is unbounded. |
| B. Logic | each step says what it establishes | Partly | B2e/B3e list steps; the readings tables carry the meaning. Left for stage 3. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | "≈", "w ≈ 80-130 B" and "entries ≈ C·2^20/w" were given exact bands with w derived (B2f, B3f amendments). |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met after amendment | Rows had meanings without verdicts. There was no row for the guard, an off-band value, the shrink, the yaml comparison or an invalid run (B2g, B3g amendments). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Plateau ∝ C plus evictions (misses = all cells offered, entries = ⌊C/w⌋). The shrink step shows eviction at the set itself. |
| B. Logic | alternative explanations and their controls | Met | C = 64 / 256 controls, invalidation, key/row/chunk caches off, and `PSMW` = `ClockAndCount` = Entries attribution (B3h; evidence named in the B2h/B3h amendments). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3 and B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | The test file and the output format were not given (B2a, B2d amendments). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | Added: the output lines, the own-table count, exact JMX gauges (`nodetool info` rounds), a live histogram without `-all` (the filed `-all` counts unreachable objects), H(C)'s array term from the source, the order and the stop conditions (B2d, B2e, B3c–B3e amendments). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly → Met after amendment | The filed design used `/local`, Linux, a `-p` pid file and `ant jar stress-build`. Replaced by this host's clone and node directory; `build-test` already builds stress (B2a, B3a, B4 amendments). |
| D. Runnable | workload arithmetic reaches the limit | Partly → Met after amendment | Demand reaches every capped C. The control's live cost (≈ 208 B × 2·10^6 ≈ 0.42 GB, derived) is ≈ 65 % of the filed 1 GiB heap with memtables, so the heap was raised to 2 GiB (B3a amendment; no prediction depends on it). Node data ≈ 0.33 GB of 126 GiB free. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `CacheService.java:103-105, 172-196, 319-322, 344-350`, `CaffeineCache.java:51-95`, `InstrumentingCache.java:77-95`, `CounterCacheKey.java:46-81, 152-157`, `ClockAndCount.java:28-49`, `CacheKey.java:27-28`, `ByteBufferUtil.java:182-204`, `CompositeType.java:509-541`, `CounterMutation.java:153-156, 207-240`, `ColumnFamilyStore.java:2499-2511`, `CacheMetrics.java:69-75`, `Info.java:114-124`, `SetCacheCapacity.java:30-44`, `NodeProbe.java:1088-1094`, `NopCacheProvider.java:37-44`, `Config.java:479-483`, `DatabaseDescriptor.java:832-845`, stress `SettingsSchema.java:166-180`, `SettingsColumn.java:124-138, 170`, `SettingsCommandPreDefined.java:107-108`, `CqlCounterAdder.java`. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: this host's clone; test file written by the harness; output from the test log | Amendment 2026-10-27 | `/local` paths; no test file in the case file. |
| 2 | B2b/B2e: runtime shrink of a full cache (C = 64 → 1, no invalidation) | Amendment 2026-10-27 | The entry pointer was otherwise exercised only on an empty cache; A3 step 2 untested. |
| 3 | B2c: exact workload, w = 112 B derived, own-table count | Amendment 2026-10-27 | "≈ 80-130 B". |
| 4 | B2d: `CCR` output lines | Amendment 2026-10-27 | Format open. |
| 5 | B2e: order, stop condition, `@After` | Amendment 2026-10-27 | Open. |
| 6 | B2f: bands (i)–(v) | Amendment 2026-10-27 | "≈"; the added step. |
| 7 | B2g/B2h: verdict per row, added rows; control evidence | Amendment 2026-10-27 | Group B. |
| 8 | B3a: this host, node directory, heap 2 GiB, start/stop | Amendment 2026-10-27 | Linux paths, `-p`; heap arithmetic at the control. |
| 9 | B3b/B3e: shrink 256 → 8 without invalidation | Amendment 2026-10-27 | As 2. |
| 10 | B3c: exact commands; w_c = 120 B derived | Amendment 2026-10-27 | "≈ 160-260 MB". |
| 11 | B3d: JMX sampler every 2 s; histogram without `-all`; H(C) array term 56 B | Amendment 2026-10-27 | `nodetool info` rounds Size; `-all` counts unreachable objects; the cell-name array is 24 B, not 32 B. |
| 12 | B3e: order, checks, shakedown | Amendment 2026-10-27 | Open. |
| 13 | B3f: bands (i)–(vi) | Amendment 2026-10-27 | "≈"; the added step. |
| 14 | B3g/B3h/B4: verdict per row, added rows; control evidence; paths | Amendment 2026-10-27 | Group B; `$WORK`. |
| 15 | A negative value on the cluster tier (through JMX `setAttribute`; `nodetool` would read `-1` as an option) | Left for stage 3 | B1's guard clause is tested by the unit tier. |
| 16 | B2e/B3e steps should say what each establishes | Left for stage 3 | Not needed for a valid run. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 EDT: step E 00:19:50; clone and build 00:19:57–00:20:59; audit and amendments to ≈ 00:26; unit shakedown 00:27:10–00:27:30; cluster shakedown 00:28:52–00:31:59; freeze 00:32:27; **unit run 1 00:32:43–00:33:20; cluster run 1 00:33:55–00:38:01**; self-check 00:38–00:41 |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab |
| OS and kernel (step E) | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64 (T6000); 10 cores, 32 GiB RAM (34,359,738,368 B); internal SSD APFS `/dev/disk3s1`, 460 GiB, 126 GiB free; loopback 127.0.0.1, .2, .3 on `lo0` (only .1 used: one node); ports 7000, 7199, 9042, 9091 free; no Cassandra or stress process before |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit: `ant testsome` fork (`-Xmx1024m` from build.xml; start capacity auto = 12 MiB in that JVM). Node: `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=200M` (`-Xms2G -Xmx2G`, read from the process command line), G1 |
| Ant / Python | 1.10.18 / 3.8.11 (self-check, run with `-I`) |
| Local clone commit | `$W/cassandra-run46` = `~/Library/Caches/stage4/cassandra-run46`, fresh `git clone --branch cassandra-5.0.9 ~/cassandra-src`, `b5f2a54210d541339c2e7c17a794195cac0e67c2`; `ant -Dlocal.repository=$W/m2 build-test` `BUILD SUCCESSFUL` in 55 s; `git status` clean after the runs |
| Case-file commit / harness commit | uncommitted (sha256 in §1) |
| Storage for node data | local SSD, `$W/node-ccr46` (data, commit log, hints, saved caches, cdc, logs, conf), wiped before and removed after (331 MB data) |
| Full logs (outside the repo, 6.4 MB) | `~/Library/Caches/stage4/logs/counter_cache_size-setCounterCacheCapacityInMB/`: `clone-build-run46.log`, `unit-shake/`, `unit-r1/` (`ant.log`, JUnit XML, `test.log`, `stdout.txt`, `summary.txt`, `commands.log`), `cluster-shake/`, `cluster-r1/` (`commands.log`, `summary.txt`, `system.log`, `node-L1.out`, `node-L2.out`, `samples-L1.csv`, `samples-L2.csv`, `info.txt`, `info-10s-L*.txt`, the full live histograms `histo-<C>.txt`, `stress-write-*.log`, `yaml-tail-*.txt`, `error-warn.txt`), `selfcheck.out` |

Machine facts I relied on (from `environment-advisor.md` and the session brief):
- All files are under `$W` (no `mkdir` in `$HOME`). Every `ant` call passes `-Dlocal.repository=$W/m2`. Commands touching `$W`, Java or the network ran outside the tool sandbox.
- No `setsid`: the node runs as a tracked `bin/cassandra -f … < /dev/null &` process and is stopped by `nodetool drain` then `kill <pid>`. The scripts' `pgrep`/`pkill` patterns split the daemon and stress names (`Cassandra[D]aemon`, `Stres[s]`).
- BSD `sed -i ''`. No jmxterm (a JMX sampler instead; `nodetool sjk` not used). `jstat` not used: live class histograms come from `jcmd GC.class_histogram` after `GC.run`, read by column, not by a regex on `[`.
- Test stdout is read from `build/test/logs/**/TEST-<class>.log`. The unit yaml's read thresholds do not matter here: no large reads, since counter updates read single cells internally.
- Shakedowns ran before run 1. Long steps ran in the background and were polled. Bounds were derived from source. `selfcheck.py` was written before readings. Node `system.log` times are UTC.
- No guardrail is on the path: counter updates by an internal or AllowAll superuser client, and a JMX/nodetool capacity set; no guardrail reads `counter_cache_size` in 5.0.9. So the authenticator stayed as shipped.
- `cassandra-env.sh`/`JVM_EXTRA_OPTS`, loopback aliases and the Python driver were not needed.

## 3. Runbook defects

None in the case file: both tiers ran as amended at the frozen version.

Self-check script defect (no case-file change, no effect on a reading or a check's logic):

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| S1 | self-check (shakedown and run 1) | `selfcheck.py` line 226, the label of the B3f(iii) k-spread check | `'… within 15% of mean %.4f' % mean`: the unescaped `% o` made Python raise `TypeError` before the check, so the cluster part stopped at that check, before the shrink, yaml and row checks. The same crash happened on the cluster shakedown. I missed it there because I grepped only FAIL/ROW/TOTAL lines (the shakedown output shows no `CLUSTER ROW` line). | Escaped as `15%%` in the label string only; sha256 `edc21561…` → `ed38c83f…`. No other line changed. Re-run on run 1: 93 / 93 hold. Re-run on the shakedowns: only the expected parameter and small-N fails. | AI, 2026-10-27, after the run-1 readings | none |

## 4. Run 1

**Scope:** both tiers, all values in §1. **Command logs:** [`run1/unit/commands.log`](counter_cache_size-setCounterCacheCapacityInMB-capacity--autonomous/run1/unit/commands.log),
[`run1/cluster/commands.log`](counter_cache_size-setCounterCacheCapacityInMB-capacity--autonomous/run1/cluster/commands.log). Excerpts are under
[`run1/`](counter_cache_size-setCounterCacheCapacityInMB-capacity--autonomous/run1/):
- `unit/`: `summary.txt`, `stdout.txt` (all 1,000 sample lines), `junit-testsuite.txt`.
- `cluster/`: `summary.txt`, `samples-L1.csv`, `samples-L2.csv`, `info*.txt`, `histo-<C>-cache-classes.txt`, `stress-write-*-results.txt`, `yaml-tail-*.txt`, `system-log-excerpt.txt`, `error-warn.txt`.
- `selfcheck.out`.

### 4.1 Readings

**Unit tier** (JUnit `Tests run: 2, Failures: 0, Errors: 0`; `CCR done`; no `CCR error`; 200 samples per pass)

| Test or step | Result | Evidence |
|---|---|---|
| `guard`, C = −1 | `java.lang.RuntimeException`, `capacity should not be negative.`; capacity 12,582,912 before and after | `run1/unit/summary.txt` |
| C = 64 (control) | own = size = **200,000**, weighted 22,400,000 (w = 112.0 B), misses 200,000, hits 0 | `summary.txt` |
| shrink 64 → 1, no invalidation | before: weighted 22,400,000, own 200,000. **Right after the call: weighted 1,048,544, size = own 9,362, capacity 1,048,576** | `summary.txt` |

| C (MiB) | capacity | max weighted (200 samples + final) | final weighted (fill) | own = size | C·2^20/112 | own ratio | evicted (N − own, inferred) | misses / hits |
|---|---|---|---|---|---|---|---|---|
| 4 | 4,194,304 | 4,194,288 | 4,194,288 (0.999996) | 37,449 | 37,449.1 | – | 162,551 | 200,000 / 0 |
| 2 | 2,097,152 | 2,097,088 | 2,097,088 (0.99997) | 18,724 | 18,724.6 | 0.5000 | 181,276 | 200,000 / 0 |
| 1 | 1,048,576 | 1,048,544 | 1,048,544 (0.99997) | 9,362 | 9,362.3 | 0.5000 | 190,638 | 200,000 / 0 |
| 0 | 0 | 0 | 0 | 0 | – | – | 200,000 (none cached) | 0 / 0 (cache skipped) |

**Cluster tier**

Validity context:
- Read-back: `Initializing counter cache with capacity of 64 MiBs`, then `… 16 MiBs`. `-Xms2G -Xmx2G` in both lifetimes.
- Every stress run wrote 400,000 partitions with 0 errors, 21–25 s each at 26–31 k op/s.
- 70 + 21 sampler rows, 0 error rows. `system.log` has 0 ERROR lines and 0 `OutOfMemoryError`.
- Key and row cache capacity `0 bytes` at the start and end of both lifetimes (`info.txt`).

| Pass | Capacity (every write/done row) | max Size over the pass's rows | Size / Entries at `<C>-done` | w_c | ⌊C·2^20/120⌋ | `CounterCacheKey` / `ClockAndCount` / `PSMW` instances | H(C) (B) | k(C) |
|---|---|---|---|---|---|---|---|---|
| 256 (control) | 268,435,456 | 240,000,000 | 240,000,000 / **2,000,000** | 120.0 | – | 2,000,000 / 2,000,001 / 2,000,003 | 320,013,768 | – |
| shrink 256 → 8 (4 rows) | 8,388,608 | 8,388,600 (first row after the call) | 8,388,600 / 69,905 | 120.0 | 69,905 | – | – | – |
| 32 | 33,554,432 | 33,554,400 | 33,554,400 / 279,620 | 120.000 | 279,620 | 279,620 / 279,621 / 279,623 | 44,755,208 | 1.3338 |
| 16 | 16,777,216 | 16,777,200 | 16,777,200 / 139,810 | 120.000 | 139,810 | 139,810 / 139,811 / 139,813 | 22,385,608 | 1.3343 |
| 8 | 8,388,608 | 8,388,600 | 8,388,600 / 69,905 | 120.000 | 69,905 | 69,905 / 69,906 / 69,908 | 11,200,808 | 1.3352 |
| yaml 16 (restart) | 16,777,216 | 16,777,200 | 16,777,200 / 139,810 | 120.000 | 139,810 | 139,810 / 139,811 / 139,813 | 22,383,648 | (1.3342) |

How H(C) is computed:
- H(C) = bytes(`CounterCacheKey`) + bytes(`ClockAndCount`) + Σ bytes(`com.github.benmanes.caffeine.cache.*`) + 56 × instances(`CounterCacheKey`), from the full live histograms (B3d amendment).
- Example, C = 32: 8,947,840 + 8,947,872 + 11,200,776 (of which `PSMW` 11,184,920) + 15,658,720 = 44,755,208.
- The mean of k(32), k(16), k(8) is 1.3344. The derived per-entry value is 160 B / 120 B = 1.333. The control's H is 160.007 B per entry.

Context, not part of any prediction:
- Sampler misses per pass equal the 2,000,000 cells. Hits come from stress's warm-up (50,000 operations on the same population): 250,000 at 256 and 32, 137,411 at 16, 58,502 at 8, 69,942 at yaml 16. W-TinyLFU kept part of the warm-up's cells when they no longer all fit.
- Whole-JVM live totals: 543.5 / 275.8 / 178.8 / 230.6 MB at 256 / 32 / 16 / 8. These include memtables and are not monotone in C, so they are not a measure of the cache.
- `[B` instance counts drop by 3,867,355 between 256 and 8, against 2 × (2,000,000 − 69,905) = 3,860,190. Between 32 → 16 and 16 → 8 they drop by 279,477 and 139,745, against 279,620 and 139,810. This is consistent with two arrays per entry, but the arrays' bytes cannot be separated from other byte arrays.

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — JUnit 2 tests, 0 failures, 0 errors; `CCR done`, no `CCR error`; all five passes present with 200 samples each [observed: `run1/unit/junit-testsuite.txt`, `stdout.txt`]. The limit is passed: demand is 22,400,000 B against 1–4 MiB [observed: C = 64 pass]. Valid.
2. **Readings** — nothing unusual. Every figure equals the derived value to the entry (own = ⌊C·2^20/112⌋) [observed].
3. **Matched row** — B2g row 1, with the B2f amendment's (i)–(v):
   - (i) own 200,000, weight 22,400,000 = N·112, misses 200,000, hits 0.
   - (ii) max weighted ≤ C·2^20 at every sample; fill ≥ 0.99997; own within 0.001 % of C·2^20/112; ratios 0.5000; misses 200,000.
   - (iii) C = 0: 0 at every sample, 0 misses.
   - (iv) shrink: 1,048,544 ≤ 2^20 at once, capacity 2^20, own 9,362.
   - (v) −1 refused, capacity unchanged.

   All observed in `stdout.txt` and `summary.txt`. **Confirmed — caps.**
4. **Excluded rows** — each is ruled out by an observed reading:
   - Row 2 (weighted > C·2^20 + 2w): the maximum is 0.99997·C·2^20.
   - Row 3 (own = N at C = 1): own is 9,362.
   - Row 4 (control < N): own is 200,000.
   - Added (a) (shrink > 2^20): 1,048,544.
   - Added (b) (−1 accepted): refused.
   - Added (c) (off-band): none.
   - Added (d) (invalid): no.
5. **Observed vs. inferred** — evictions are inferred as N − own [inferred: source, `CounterMutation.java:213-240`]. The inference rests on three things: every cell missed once after the clear (misses 200,000, observed), every missed cell is put, and nothing else removes entries. The shrink's eviction is observed directly (size 200,000 → 9,362 across the call).
6. **Deviations and gaps** — none against the frozen runbook. The tier reads the weight, not the retained heap (gap named in B2d).
7. **Core question** — the runtime setter sets Caffeine's maximum weight. The cached weight never exceeds C·2^20, the entry count is exactly ⌊C/112 B⌋ and halves with C, C = 0 caches nothing, a shrink of a full cache evicts at the call, and −1 is refused.

**Conclusion (unit tier):** B2g row 1 — **confirmed — caps**.

**Cluster tier**

1. **Validity** — none of the B3g added row (d) conditions occurred [observed: `run1/cluster/summary.txt`, `stress-write-*-results.txt`, `yaml-tail-*.txt`, `samples-L*.csv`, `system-log-excerpt.txt`]:
   - all five stress runs: 0 errors and 400,000 partitions;
   - read-back 64 and 16 MiB;
   - node alive throughout (sampler rows without error), no OOM;
   - yaml tails as amended.

   The limit is passed at every capped C: the control holds 2,000,000 entries = 240 MB, more than 32 MiB. Valid.
2. **Readings** — nothing unusual. Two `Prepared statement recreation error` WARN lines appeared at the yaml restart. The node dropped stress's preloaded statement, stress re-prepared it, and its write had 0 errors [observed: `error-warn.txt`, `stress-write-y16-results.txt`].
3. **Matched row** — B3g row 1, with the B3f amendment's (i)–(vi), all observed in `samples-L*.csv` and `histo-*-cache-classes.txt`:
   - (i) control Entries 2,000,000, Size 240,000,000 = 120 × Entries.
   - (ii) Capacity = C·2^20 in every write/done row; Size ≤ Capacity in every row (0 rows over, awk recount); fill ≥ 0.999999; w_c 120.000; Entries = ⌊C·2^20/120⌋ exactly; ratios 0.5000.
   - (iii) H decreasing 44.8 → 22.4 → 11.2 MB; k 1.3338–1.3352 ∈ [1.0, 2.5], each within 0.07 % of the mean.
   - (iv) `ClockAndCount` = Entries + 1 and `PSMW` = Entries + 3 in every histogram.
   - (v) shrink: first row after the call Size 8,388,600 ≤ 8·2^20, Entries 69,905.
   - (vi) yaml 16 = runtime 16 exactly (139,810 entries, 16,777,200 B).

   **Confirmed — caps.**
4. **Excluded rows** — each is ruled out by an observed reading:
   - Row 2 (H not decreasing, or k out of band): H is decreasing and k is in band.
   - Row 3 (Size > Capacity): no row over.
   - Row 4 (control < 1,980,000): 2,000,000.
   - Added (a) (shrink above cap): 8,388,600.
   - Added (b) (off-band): none.
   - Added (c) (yaml ≠ runtime): identical.
   - Added (d) (invalid): no.
5. **Observed vs. inferred** — H(C)'s array term (56 B × instances) is the source-derived size, not a measurement of `[B` bytes [inferred: jamm layout; `[B` instance deltas track 2 × Entries, observed]. Without the term, k is 0.867–0.869, below the filed band's lower edge of 1.0. The filed estimate (2 × 32 B) would give k ≈ 1.40. So row 1's k-band holds only with an array term, and the term is derived, not measured. That the retained heap per entry outside the weight is Caffeine's `PSMW` node is supported by `PSMW` instances = Entries + 3 [observed]. The backing `ConcurrentHashMap$Node` (32 B per entry; 2,035,346 instances at the control, observed) and the frequency sketch are outside H(C) by the file's definition. So H(C) is not the whole live-heap cost of the cache.
6. **Deviations and gaps** — none against the frozen runbook. The heap is 2 GiB, not the filed 1 GiB (B3a amendment, before the freeze). Stress's default warm-up (as written) adds requests on the same population, not distinct cells (control Entries 2,000,000).
7. **Core question** — on a node, `nodetool setcachecapacity` (and the yaml value) caps the counter cache:
   - the weighed size never exceeds C·2^20;
   - entries plateau at exactly ⌊C/120 B⌋ (279,620 : 139,810 : 69,905 = 4 : 2 : 1);
   - a shrink of a full 240 MB cache to 8 MiB takes effect at the call;
   - the retained counter-cache objects H(C) follow C linearly at k ≈ 1.334.

**Conclusion (cluster tier):** B3g row 1 — **confirmed — caps**.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

[`run1/selfcheck.py`](counter_cache_size-setCounterCacheCapacityInMB-capacity--autonomous/run1/selfcheck.py) was written before any run-1 reading. After the readings it changed only by fix S1 (§3), a label escape.

It re-reads these raw files under the full log root and recomputes every relation and the row:
- unit: the test log and the JUnit XML;
- cluster: `samples-L1/L2.csv`, the full `histo-<C>.txt`, `stress-write-*.log`, `system.log`, `yaml-tail-*.txt` and `info.txt`.

Result: **93 checks, 93 hold, 0 fail**, exit 0 ([`run1/selfcheck.out`](counter_cache_size-setCounterCacheCapacityInMB-capacity--autonomous/run1/selfcheck.out)):
- unit 38 / 38, row "Confirmed - caps (B2g row 1)";
- cluster 55 / 55, row "Confirmed - caps (B3g row 1)".

Raw files re-opened by hand as well:
- `histo-32.txt`: `PSMW` 279,623 / 11,184,920 B; `ClockAndCount` 279,621 / 8,947,872 B; `CounterCacheKey` 279,620 / 8,947,840 B.
- An awk count of rows with Size > Capacity in the capped, shrink and yaml passes: 0.
- `stress-write-8.log` totals.
- The guard line and the count of 1,000 sample lines in `test.log`.
- The `[B` and `ConcurrentHashMap$Node` rows of all five histograms (context in §4.1).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | JUnit counts, `CCR done`; stress totals, read-back, yaml tails, OOM count, sampler error rows. |
| 2. Readings | yes | Every unit sample and pass line; every cluster sampler row per phase; H from the full histograms. |
| 3. Matched row | yes | Each B2f/B3f amended relation recomputed against its frozen band. |
| 4. Excluded rows | yes | Each excluded row's reading re-read. |
| 5. Observed vs. inferred | yes | The eviction inference rests on observed misses. H's array term is the frozen, source-derived estimate, labelled as such. The k-band verdict depends on it: without it k ≈ 0.87. The relation H ∝ C (k equal within 0.07 %) and the decrease of H do not depend on it. |
| 6. Deviations and gaps | yes | Heap 2 GiB by amendment; S1 is a self-check label fix; stress warm-up as written. |
| 7. Core question — the steps follow the audited logic | yes | setter → Caffeine maximum → eviction (at the set and on insert) → weight ≤ C, entries ∝ C → retained cache objects ∝ C; controls hold. |

### 5.2 Run 2?

**No** — decided 2026-10-27. Every load-bearing figure is observed and recomputed by an independent script. Both tiers match their derived
values to the entry (own and Entries = ⌊C·2^20/w⌋), and the cluster's yaml and runtime paths give identical readings. The one inferred
term (H's array bytes) is fixed by the frozen file and the source, so a second run would reproduce it rather than test it. The result neither refutes
the case nor confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive.

**Claim tested (B1):** "For any counter cache capacity C set by `setCounterCacheCapacityInMB(C)` (or `counter_cache_size: C MiB`), the
counter cache's weighted size stays ≤ C×2^20 bytes (plus a few entries) no matter how many distinct counter cells are updated, and the
retained heap of counter cache objects scales linearly with C; a negative C is refused." "Confirmed" means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1: weighted ≤ C·2^20 at every sample for C = 4/2/1 MiB, own = ⌊C·2^20/112⌋ = 37,449 · 18,724 · 9,362 (ratios 0.5000), evicted 162,551 · 181,276 · 190,638; C = 0 caches nothing; a shrink 64 → 1 MiB of a full cache leaves 1,048,544 B at once; −1 refused, capacity unchanged | caps | run 1 + self-check | 2026-10-27 |
| Cluster | **Confirmed** — B3g row 1: Size ≤ Capacity in every sampler row at 32/16/8 MiB, Entries = ⌊C·2^20/120⌋ = 279,620 · 139,810 · 69,905 exactly; control 2,000,000 entries (240 MB) at 256 MiB; shrink 256 → 8 MiB effective at the first sample (8,388,600 B); retained counter-cache objects H(C) 44.8 / 22.4 / 11.2 MB, k = 1.334–1.335; `ClockAndCount` = Entries + 1, `PSMW` = Entries + 3; yaml 16 identical to runtime 16 | caps | run 1 + self-check | 2026-10-27 |

**Feedback filed:**
- The case file's section D (uncommitted).
- The seventeen step-0 amendments are in the case file, dated; their sha256 is a new row in `_INDEX-advisor.md` §2.
- `_INDEX-advisor.md` §1 Stage 4 column updated.
- The Estimate line is left as filed. No section was amended for a refutation (none occurred).

Recommendations for stage 3, not applied:
- §1.1 #15 and #16.
- H(C) as defined leaves out the backing `ConcurrentHashMap` node (32 B per entry) and the frequency sketch, so k ≈ 1.33 is a lower bound of the whole live-heap factor.
- The filed band [1.0, 2.5] holds only with the array term, which is derived, not measured.

**End of run (2026-10-27, after the self-check):**
- No `CassandraDaemon`, stress or sampler process; ports 7000/7199/9042/9091 free.
- `$W/node-ccr46` removed.
- The probe test removed from `$W/cassandra-run46` (`git status` clean).
- No `build/` or log folder in the repository root.
