# counter_cache_size-iscountercacheenabled-capacity--autonomous — stage-4 results  <!-- file: results/counter_cache_size-iscountercacheenabled-capacity--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`counter_cache_size-iscountercacheenabled-capacity--autonomous`](../../stage3-ai-deep-read/cases/counter_cache_size-iscountercacheenabled-capacity--autonomous.md)
>
> **Status:** verdict filed (2026-10-27) — run 1 done at both tiers, self-checked, no run 2
>
> **Outcome class:** **true positive** (estimate `positive`, effect `caps`) — [definition](../README.md#outcome-class)
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D. **Run 1 is a joint run for three case files that share the `counter_cache_size` knob** (`counter_cache_size-getcachedcounter-capacity--autonomous` and `counter_cache_size-putcachedcounter-capacity--autonomous`): one build, one unit class, one cluster sequence, three separate audits, predictions and verdicts. The raw readings are therefore the same; each file's conclusion below is matched against its own B2f/B2g/B3f/B3g and nothing is copied from a sibling's conclusion.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository commit `6e6cf92` holds the file as filed (sha256 `12bb88094055c48210c1c3271444b8a2e719815630dd2871911eaf8174625333`). The audit's amendments (section "B-audit", B2i, B3i, B2g and B3g additions, dated 2026-10-27) are **uncommitted**. **sha256 of the whole file after the amendments: `14118ec19638a869d529b18eaa59b12ae770b16c7831667c5039350cf709b3e1`**, recorded 2026-10-27 before any reading (a shakedown of small N ran earlier and was deleted; it is where the entry weight 120 B and the stress-tool facts in B3i come from). B2f, B2g, B3f, B3g are frozen at this hash; only section D changes after it. |
| **Harness** | `harness/counter_cache_size-iscountercacheenabled-capacity--autonomous/` (uncommitted): `CounterCacheCapTest.java`, `unit-run.sh`, `Jmx.java`, `cluster-run.py`, `analyze_unit.py`, `analyze_cluster.py`, `selfcheck.py`, `README.md` (the same files are in the two sibling harness folders). md5s at the start of the run: `run1/harness.md5.start` (identical at the start of the cluster tier, `run1/harness.md5.cluster-start`); after the run `analyze_cluster.py` changed once (the `ClockAndCount` check, §3 item 5) and `selfcheck.py` was added: `run1/harness.md5.final`. The patched source copy's diff: `run1/noguard.diff`. |
| **Tiers and values** | Unit: capacity 0, 1, 4 (twice), 25 MiB (unit default), on the unpatched tree and on `tree-noguard`; production path at 0/1/4; reload at 0/1/4/0/default (this file's gate); resize 4 -> 1 -> 0 -> 4. Cluster: `counter_cache_size` 0, 1, 8, 64 MiB, unset (50 MiB), a repeat of 8, a runtime change 64 -> 8, a regular-table control (8 MiB) and reload arms at 0/1/8 MiB after a save. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

Estimate `positive` (claim: the counter cache's weight cap bounds heap, with the `isCounterCacheEnabled()` gate (`ColumnFamilyStore.java:3269`, `getCapacity() > 0`) as the on/off gate). Not a negative-estimate file, so no positive control is required; B2h/B3h carry their own controls. The literal is not settable, so the design uses two arms that differ in the one condition (B2i.6: a patched-literal source copy) as well as the capacity 0 / non-zero arms.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: on-heap bytes of the counter cache (the weigher's `unsharedHeapSize` sum); real heap via `GC.heap_info` and the class histogram. |
| A. Core question | knob varied, >= 3 values incl. default | Partly -> Met | B2b {0,1,4} and B3b {0,1,8} MiB had no default; B2i.2 adds the unit-yaml default (`init`, 25 MiB) and B3i.3 adds 64 MiB and the unset default (50 MiB on a 2 GiB heap). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly -> Met | B2d/B3d: weighted size is the check's own counter; B2i.8 and B3i.5 add heap after GC and `GC.heap_info`; the gap (histogram cannot attribute `byte[]`, weigher omits Caffeine node and map entry) is named. |
| A. Core question | usage driven to the limit and past it | Partly -> Met | B3c assumed one entry per id; `counter_write` makes five per key (B3i.2). 600,000 keys = 3,000,000 entries (343 MiB at 120 B) against caps of 1 to 64 MiB; unit N = 4 x capacity / weight (B2i.3). |
| B. Logic | each step says what it establishes | Met | B2e/B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Partly -> Met | "small slack", "about 4x", "within ~2x" were undefined; B2i.4 and B3i.5/6 make them numeric before the run. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly -> Met | No row for the reload path (the helper's only caller), the patched-literal arm, or the regular-table control; added as B2g/B3g additions. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly -> Met | B2c puts straight into `counterCache` and never passes the helper; the disallow branch is reached only by the reload (`CacheService.java:382`). B2i.9 adds `U4` and B3i.8 adds `sv8`/`rl0`/`rl1`/`rl8`; B2i.6 adds the patched-literal arm. |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h plus the regular-table control (`r8`, `U3` control) and the patched arm. |
| C. Specific | a human can follow it from the intro and B1 | Met | A1-A3, B1. |
| C. Specific | an AI can run B2/B3 without re-deriving the code path | Partly -> Met | The stress tool, table and per-key entry count, the JMX bean names and the process check were not exact (`pgrep -f` matches its own shell, `nodetool drainsave` does not exist); supplied in B3i. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly -> Met | B2i/B3i. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Unit test, JMX client, run scripts and analyzers are step-1 work (harness folder); build-test tree, stress, nodetool, jcmd exist. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met (after B3i.2) | 3,000,000 entries offered vs 559,240 at the largest cap; about 30 s to 100 s per pass at 7,500 to 28,000 ops/s; data under 200 MB on the 63 GB local disk; heap 2 GiB. |
| D. Runnable | load-bearing citations spot-checked | Met | Re-read in `cassandra/cassandra-5.0.9/` (clean `git status`): `ColumnFamilyStore.java:3267-3270`; `CacheService.java:172-185, 344-350, 382`; `DatabaseDescriptor.java:834-844`; `Config.java:480`; `InstrumentingCache.java:77`; `CaffeineCache.java:53-57, 61-70, 72-75`; `CounterMutation.java:213`; `TableMetadata.java:286`; `conf/cassandra.yaml:585-595`. The helper has exactly one caller (`CacheService.java:382`; `grep` over `src` and `test`). All hold at the cited lines. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Make the workload exact: `cassandra-stress counter_write`, 600,000 keys, five entries per key, pass 2 on the last 50,000 keys; drop `-pop dist=uniform` (stalls) | Applied, B3i.2, 2026-10-27, before the freeze | The filed table and id count cannot be created by the tool; the entry count per key changes the arithmetic. |
| 2 | Add the default (unit `init`, cluster unset = 50 MiB) and 64 MiB to the knob values | Applied, B2i.2 and B3i.3 | README group A asks for the default among at least three values. |
| 3 | Define slack, "about 4x/8x", "within ~2x" and the hit-rate wording numerically | Applied, B2i.4 and B3i.5/6 | So a reading can contradict the prediction. |
| 4 | Add heap-after-GC and `GC.heap_info` as the real-resource reading, and name the histogram gap | Applied, B2i.8 and B3i.5 | The counter is the weigher's own sum. |
| 5 | Add the production write path (`U3`), the regular-table control and the runtime change (`rt64`) | Applied, B2i.5 and B3i.3/8 | Controls named in B2h/B3h had no instrument. |
| 5b | Add the reload test (`U4` unit, `sv8`/`rl0`/`rl1`/`rl8` cluster) | Applied, B2i.9 and B3i.8 | The helper's only caller is the start-up reload; the filed steps never reached it. |
| 6 | Add a patched-literal arm (`tree-noguard`) and the allocation-per-call observation | Applied, B2i.6/7 | The literal cannot be varied by configuration; two arms that differ in the one condition show what it does. |
| 7 | Replace the `pgrep -f` process check by `ps -eo cmd \| grep '[C]assandraDaemon'` run on the node and the nonexistent `nodetool drainsave` by the JMX `saveCaches` operation | Applied, B3i.7/8 | `pgrep -f` inside an ssh string matches its own shell. |
| 8 | Case-file sources list names `/users/jason92/cassandra-5.0.9/...` paths | Left for stage 3 | Cosmetic. |

**Agreement criteria** — not applicable (no run 2).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-27 (unit 20:59 to 21:03 MDT; cluster 21:03 to 21:46 MDT) | not done |
| Node (CloudLab name and type) | `pc39` = `node1.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1; node JVM G1, `-Xms2G -Xmx2G` (`jcmd VM.flags`, in `cluster/*/summary.json`) | |
| Ant (`ant -version`) | 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-cc/tree-base` made by `copy-source.sh` from repository commit `6e6cf92` (local baseline `e0d60ab`, `git describe` = `cassandra-5.0.9`), `ant build-test` 1 min 13 s; `~/s4-cc/tree-noguard` the same plus the three one-line edits in `ColumnFamilyStore.java` (`run1/noguard.diff`). The unit test was added under `test/unit/org/apache/cassandra/db/`; the cluster node ran from `tree-base/build`. Nothing was built in the repository's `cassandra/cassandra-5.0.9/` (its `git status` is empty). `~/cassandra-run1` on the node was not touched. | |
| Case-file commit / harness commit | `6e6cf92` as filed; amendments and harness uncommitted (sha256 §1) | |
| Storage for node data | `/dev/sda3`, 63 GB local; node data under `~/s4-cc/node` (156 MB at the end; removed afterwards) | |
| Full logs (path, outside the repo) | `pc39:~/s4-cc/run1/{unit-base,unit-noguard,cluster}/` (full `ant.log`, per-arm `system.log.full`, all histograms `hist-*.txt`, stress outputs); `~/s4-cc/logs/build-*.log`; excerpts in `results/counter_cache_size-iscountercacheenabled-capacity--autonomous/run1/` | |

**Own-tag isolation (tag `cc`):** loopback address `127.39.9.1`, JMX 7439, native 9042 and storage 7000 only on that address, no Byteman; every kill by PID. **Deviations from the filed environment (none changes B1):** the filed `UPDATE ... SET c = c + 1` over 2,000,000 ids is `cassandra-stress counter_write` (five counters per key, B3i.2); the sampler is a JMX client rather than `nodetool info` (rounded); the saved-cache step uses the `saveCaches` JMX operation.

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | audit | B3c | the filed table (`id bigint, c counter`, 2,000,000 ids) cannot be created by `cassandra-stress`; `counter_write` makes five cache entries per key | B3i.2 | 2026-10-27, before the freeze | none (uncommitted) |
| 2 | shakedown (not a reading) | B3c | `-pop dist=uniform(...)` stalls `counter_write` after 2,000 ops | pass 2 uses `-pop seq=550001..600000` (B3i.2) | 2026-10-27, before the freeze | none |
| 3 | shakedown | B3e | no `nodetool drainsave`; the cache MBean is `org.apache.cassandra.db:type=Caches` and its capacity setters are attributes, not operations | `Jmx.java` fixed; B3i.8 | 2026-10-27, before the freeze | none |
| 4 | audit | B3e/B4 | `pgrep -f CassandraDaemon` inside an `ssh` string matches its own shell | `ps -eo cmd \| grep '[C]assandraDaemon'` (B3i.7) | 2026-10-27 | none |
| 5 | run 1, analysis (not a run step) | harness, `analyze_cluster.py` | the first analysis flagged the 0 MiB arm: it required 0 `ClockAndCount` instances, but one static instance (`ClockAndCount.BLANK`) exists in every JVM that has loaded the class (0 `CounterCacheKey`; in the other arms `ClockAndCount` = entries + 1). The threshold was corrected to "at most 1" and the analysis re-run on the unchanged raw files; the first output is kept as `run1/analyze_cluster_is.v1-overstrict-ClockAndCount.out`. | analyzer only; B3f/B3g unchanged | 2026-10-27 | none |

No step of the unit or cluster runbook failed in run 1; neither tier was restarted.

## 4. Run 1

**Scope:** unit tier on the unpatched tree and on the patched-literal tree; cluster tier arms `c0 c1 c8 c64 cdef c8b rt64 r8` and, for the reload path, `sv8 rl0 rl1 rl8` (run for all three files; used as evidence by the file whose gate it is). **Command log:** `counter_cache_size-iscountercacheenabled-capacity--autonomous/run1/unit/{base,noguard}/session.log`, `run1/cluster/session.log`; analyzer output `run1/analyze_unit_*.out`, `run1/analyze_cluster_is.out`; independent self-check `run1/selfcheck.out`.

### 4.1 Readings

**Unit tier** (`run1/unit/base/unit.txt`, `run1/unit/noguard/unit.txt`; JUnit `BUILD SUCCESSFUL` in both, `ant-tail.log`).

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| U1 helper `isCounterCacheEnabled()` per arm, counter table / regular table (unpatched tree) | capacity 0: false / false; 1, 4 and the 25 MiB default: true / false; regular table false in all five arms | `run1/unit/base/unit.txt` lines `U1 arm=0..4` |
| U1 direct puts into `counterCache`, N = max(200,000, 4 x cap / 120 B) | settled `weightedSize` = 0 at 0; 1,048,560 at 1 MiB (8,738 entries); 4,194,240 at 4 MiB (34,952 entries, twice); 26,214,360 at the 25 MiB default (218,453 entries). Never above capacity, immediate or settled. Size ratio 4 MiB / 1 MiB = 4.000 | `unit.txt` `U1`; `analyze_unit_is_base.out` (30 PASS, 0 FAIL) |
| U1 heap after GC (`heapDelta`) | 0 MiB: -70,744 B; 1 MiB: 1,785,880 B (1.70 x weight); 4 MiB: 7,374,464 B (1.76 x); default: 49,106,360 B (1.87 x) | `unit.txt` `U1` |
| U3 production path (`CounterMutation.apply`, 60,000 updates) | `weightedSize` 0 at 0; 1,048,560 at 1 MiB; 4,194,240 at 4 MiB. Regular-table control: 20,000 inserts at 4 MiB leave `size` 0, helper false | `unit.txt` `U3` |
| U4 reload after saving the 4 MiB cache (34,952 keys) | capacity 0 (twice): helper false, `loadSaved()` returned 0, `size` 0; 1 MiB: helper true, returned 34,952, `weightedSize` 1,048,560 (8,738 entries); 4 MiB: returned 34,952, 4,194,240; default: returned 34,952, 4,194,240 | `unit.txt` `U4` |
| U5 runtime resize | 4 MiB filled (4,194,240); `setCapacity` to 1 MiB: 1,048,560 at the first read; to 0: 0; back to 4 MiB: refills to 4,194,240 | `unit.txt` `U5` |
| Patched-literal arm `tree-noguard` (helper `>= 0`, guards `if (false)`) | helper true at capacity 0, regular false; direct puts at 0: `weightedSize` 0, `size` 0; other arms identical to the unpatched tree; reload at 0 (twice): helper true, `loadSaved()` returned 34,952, `weightedSize` 0, `size` 0; reload at 1 and 4: as the unpatched tree | `run1/unit/noguard/unit.txt`; `analyze_unit_is_noguard.out` (28 PASS, 0 FAIL) |

**Cluster tier** — data: `cassandra-stress counter_write`, 600,000 keys x 5 counters (3,000,000 cache entries offered in pass 1, 250,000 in pass 2), 0 stress errors in every pass (`stress-pass*.results`; 4,760 to 28,066 ops/s), node heap 2 GiB G1, `Size` is the weigher's byte sum, entry weight 120 B.

| `counter_cache_size` | Observable (B3d) | Reading (pass 1 end -> pass 2 end unless stated) | Evidence (file) |
|---|---|---|---|
| 0 | `Size`, `Entries`, `Hits`; `CounterCacheKey` instances | 0, 0, 0 at every sample (9 samples, 3,000,000 + 250,000 entries offered); 0 `CounterCacheKey` and 1 `ClockAndCount` (the static `BLANK`) in all 3 histograms | `run1/cluster/c0/samples.csv`, `hist-*.excerpt.txt` |
| 1 MiB | `Capacity`; `Size`; `Entries`; max Size - Capacity | 1,048,576; 1,048,560 -> 1,048,560; 8,738 -> 8,738; -16 | `c1/samples.csv` (14 samples) |
| 8 MiB | same | 8,388,608; 8,388,600 -> 8,388,600; 69,905; -8 (ratio of entries to the 1 MiB arm 8.000) | `c8/samples.csv` (14 samples) |
| 64 MiB | same | 67,108,864; 67,108,800; 559,240; -64 | `c64/samples.csv` |
| default (unset; init log says 50 MiBs) | same | 52,428,800; 52,428,720; 436,906; -80 | `cdef/samples.csv`, `cdef/summary.json` |
| 8 MiB (repeat) | same | 8,388,600; 69,905 (identical entries to `c8`) | `c8b/samples.csv` |
| 64 -> 8 MiB at run time (JMX attribute) | `Size`, `Entries` | 67,108,800 / 559,240 before; 8,388,600 / 69,905 at the first sample after the call and at the end; used heap after GC 293,970 KB -> 202,204 KB (-89.6 MiB) | `rt64/samples.csv`, `heapinfo-end-pass1.txt`, `heapinfo-after-setcap-hist.txt` |
| 8 MiB, regular-table writes only (300,000 rows into `standard1`) | `Entries`, `Size`, `CounterCacheKey` | 0, 0, 0 at every sample (5) and in both histograms | `r8/samples.csv`, `stress-regular.results` (0 errors) |

Heap, from the live class histogram (`GC.class_histogram`, full GC first) and `GC.heap_info` (used heap right after), end of pass 2:

| `counter_cache_size` | `CounterCacheKey` instances | (`CounterCacheKey` + `ClockAndCount` bytes) / `Size` | Used heap after GC | Increase over the 0 MiB arm (173,718 KB) | Increase / `Size` |
|---|---|---|---|---|---|
| 1 MiB | 8,738 | 0.533 | 176,833 KB | 3.0 MiB | 3.04 (noise-dominated: the increase is smaller than the heap's own variation) |
| 8 MiB | 69,905 | 0.533 | 190,619 KB | 16.5 MiB | 2.06 (repeat `c8b`: 1.72) |
| 64 MiB | 559,240 | 0.533 | 297,240 KB | 120.6 MiB | 1.88 |
| default 50 MiB | 436,906 | 0.533 | 264,911 KB | 89.1 MiB | 1.78 |

(Files: `cluster/<arm>/hist-end-pass2.excerpt.txt`, `heapinfo-end-pass2.txt`; the ratios are printed by `analyze_cluster_is.out`.)

Pass-2 hit rate (hits delta / requests delta, 250,000 requests): 1 MiB 0.0000, 8 MiB 0.0345 (repeat 0.0714), 64 MiB 0.0000, default 0.0223 (`analyze_cluster_is.out` INFO lines; `samples.csv` `hits`). It is not a dose-response: Caffeine's TinyLFU admission keeps the entries admitted first, not the last keys of pass 1, so the last 50,000 keys mostly miss even when the cache could hold them (64 MiB: 0).

| Reload arm (saved file from `sv8`: 1,677,736 bytes, 69,905 keys) | Observable | Reading | Evidence (file) |
|---|---|---|---|
| `rl0` (`counter_cache_size: 0MiB`) | `Entries`, `Size` over 13 samples (0 to 60 s after start); `CounterCacheKey` instances | 0, 0 at every sample; 0 instances; the log shows the node did read the file (`Reading saved cache: ...CounterCache-g.db`) | `rl0/samples.csv`, `system.log.excerpt`, `hist-reload-end.excerpt.txt` |
| `rl1` (1 MiB) | same | `Entries` 8,738 and `Size` 1,048,560 from the first sample on; capacity 1,048,576 | `rl1/samples.csv` |
| `rl8` (8 MiB) | same | `Entries` 69,905 (the whole saved file), `Size` 8,388,600 | `rl8/samples.csv` |

### 4.2 Conclusion and logic

Tag every statement in parts 1–4 as **[observed: `<file>`]** or **[inferred: `<reason>`]**.

1. **Validity** — valid. The limit was reached: in every non-zero arm `Size` stopped within 80 B of the cap at the end of pass 1 (`Size` - `Capacity` between -8 and -80 B, i.e. less than one 120 B entry from full) while 3,000,000 entries (343 MiB) were offered, so the cap, not the workload, ended the growth [observed: `c1`, `c8`, `c64`, `cdef` `samples.csv`]; in the unit tier every arm received 4 x capacity of entries [observed: `unit.txt` `U1`/`U2` `puts`]. Hold-fixed settings: the knob applied in each arm (`Initializing counter cache with capacity of N MiBs` in each arm's init log, and `Capacity` = N x 1,048,576 at every sample; `cdef` says 50 MiBs) [observed: `cluster/<arm>/summary.json` `init_log`, `samples.csv`]; the same stress commands, a fresh node directory per arm, `row_cache_size` 0, heap 2 GiB G1 (`jvm_flags`) [observed: `cassandra.yaml.<arm>`, `session.log`]; no `ERROR` line in any `system.log` [observed: `summary.json` `errors_in_log` 0]; harness files unchanged between the start of the unit tier and the start of the cluster tier [observed: `harness.md5.start`, `harness.md5.cluster-start`].
2. **Readings** — nothing contradicts another. `Entries` x 120 B = `Size` to within 240 B in every capped arm; the histogram's `CounterCacheKey` count equals `Entries` in every arm; the final JMX values equal the last sample [observed: `samples.csv`, `hist-end-pass2.excerpt.txt`, `summary.json` `jmx_final`]. The 0 MiB arm shows one `ClockAndCount` in each histogram, the class's static `BLANK` (the other arms show `Entries` + 1); this is not a cache entry (§3 item 5). The 1 MiB heap-increase ratio (3.04) is noise on a 3 MiB difference; the 8, 64 and default arms give 2.06, 1.88 and 1.78 (the repeat of 8 MiB gives 1.72). The pass-2 hit rate is not a dose-response (0.0 at 1 and 64 MiB, 3.5 % and 7.1 % at 8 MiB, 2.2 % at the default): TinyLFU admission keeps the first-admitted entries; B3f of this file does not use it.
3. **Matched row** — unit B2g row 1, "Helper flips with n=0 vs 1 and weightedSize <= n MiB (+slack) and scales ~linearly | claim confirmed (usage follows constraint)": the helper was false for both tables at 0 and true for the counter table only at 1, 4 and the default [observed: `unit.txt` `U1`]; `weightedSize` was 0, 1,048,560, 4,194,240 (and 26,214,360 at the 25 MiB default), never above the capacity, with the 4 MiB / 1 MiB size ratio exactly 4.000 [observed: `U1`]. B2g addition rows: the reload at capacity 0 returned 0 and left the cache empty; at 1 and 4 MiB it returned all 34,952 saved keys and held 8,738 and 34,952 entries, within the cap [observed: `U4`]; on the patched tree the helper was true at capacity 0, the reload returned 34,952, and `weightedSize` was still 0 [observed: `noguard/unit.txt` `U1`, `U4`]: "`tree-noguard` retains nothing at capacity 0 | usage is bounded by the weight cap; the literal is only the on/off gate". Cluster B3g row 1, "Size and histogram bytes scale with the knob and stay at or below it | claim confirmed": `Size` 1,048,560 / 8,388,600 / 67,108,800 / 52,428,720 (default) against capacities 1 / 8 / 64 / 50 MiB, `Entries` 8,738 / 69,905 / 559,240 / 436,906 (1 : 8.000 : 64.0 : 50.0), the two named classes at 0.533 x `Size` in every arm, whole-heap increase 1.78 to 2.06 x `Size` for 8 MiB and above [observed: `samples.csv`, `hist-end-pass2.excerpt.txt`, `heapinfo-end-pass2.txt`]. Cluster B3g additions: `rl0` held 0 entries at all 13 samples after reading the saved file; `rl1` held 8,738 and `rl8` 69,905 entries, both at or below the capacity's worth; `r8` (regular-table writes) held 0 entries and no `CounterCacheKey` [observed: `rl0/rl1/rl8/r8 samples.csv`, `system.log.excerpt`].
4. **Excluded rows** — unit: "weightedSize far above n MiB": no, never above [observed `U1`]; "Helper true at n=0, or false at n=1 for the counter table": no [`U1`]; "Helper true for the regular table": no, false in all five arms [`U1`]; additions "reload at capacity 0 returns a positive count or leaves entries": no [`U4`]; "reload at 1 or 4 MiB leaves weightedSize above capacity": no [`U4`]; "`tree-noguard` retains entries at capacity 0": no [`noguard/unit.txt`]. Cluster: "Size/histogram bytes far exceed the cap (> 2x)": no (two-class ratio 0.533; whole-heap 1.78 to 2.06 x `Size`, inside the 1.5 to 3.0 x band of the whole-heap addition row) [observed `analyze_cluster_is.out`]; "0 arm still holds entries or reloads entries after restart": no (`c0` and `rl0`); "Entries do not rise above a handful in the non-zero arms": no (8,738 and up); additions "`rl1`/`rl8` above capacity": no; "`r8` Entries > 0": no. No Refuted row applies.
5. **Observed vs. inferred** — inferred: (a) that the weighted size plus the two named classes, and the whole-heap difference to the 0 MiB arm, represent the cache's retained heap (the whole-heap figure includes any other difference between arms, e.g. memtable and JIT state; the arms ran identical commands, and 8 MiB repeated gives 2.06 and 1.72); (b) that the footprint bound comes from the weight cap and not from the literal [inferred: patched copy retains nothing at 0 and `maximumWeight(0)` evicts everything; the bound at 1 MiB and above is the same cap]. Everything else is observed.
6. **Deviations and gaps** — (a) The helper is exercised only by the reload; its effect on heap is the number of keys re-admitted (the cache then holds at most the capacity). The cluster reload used one saved file (69,905 keys) and three capacities; larger files than the cache were tested only at 1 MiB (8,738 of 69,905 kept). (b) The weigher's 120 B excludes Caffeine's node and the map entry; the real heap is 1.8 to 2.1 x the weighted size (a measured overshoot of the *weighted* estimate, not of the cap's ordering). (c) The heap-increase figure at 1 MiB is noise-limited. (d) Each arm ran once, except 8 MiB (repeated, identical entries). (e) Counters with a clustering key or collection columns (larger cell names) were not run. (f) One analyzer threshold was corrected after the run (§3 item 5); the raw files were not touched.
7. **Core question** — usage followed the constraint: with `counter_cache_size` 1, 8, 64 MiB and the 50 MiB default the cache's `Size` stopped within one entry of the cap after 3,000,000 entries were offered, entries scaled 1 : 8 : 64, and the heap of the cache's classes and the whole-heap difference followed with a stable factor (parts 1 and 3); with 0 the cache held nothing, on the write path (`c0`) and on the reload path (`rl0`), and the saved file was read but nothing admitted. The constraint caps the counter cache's on-heap use through Caffeine's `maximumWeight`; the `> 0` helper decides only whether a saved key is reloaded, and the patched copy shows that removing the zero test does not let entries stay at capacity 0 (parts 3 and 5).

**Conclusion (one line):** unit B2g row 1 (with the reload and patched-literal additions) and cluster B3g row 1 (with the `rl0`/`rl1`/`rl8`/`r8` additions) — confirmed; the cap is the weight cap, the literal is the on/off gate.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck.out` re-derives the facts by a route independent of `analyze_*.py` (unit lines split by token; cluster values from the dictionaries in `session.log`, `system.log.full` init lines, `stress-*.results` totals, histograms re-parsed with a second parser, `summary.json`): 93 checks hold, 0 fail. I then re-opened the raw files each part cites (the copies under `results/counter_cache_size-iscountercacheenabled-capacity--autonomous/run1/`):

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `c1`/`c8`/`c64`/`cdef` `samples.csv`: `Size` 1,048,560 / 8,388,600 / 67,108,800 / 52,428,720 at end of pass 1 against capacities 1,048,576 / 8,388,608 / 67,108,864 / 52,428,800 with `Requests` 3,000,000; `unit.txt` `puts` = 4 x capacity / 120; each `summary.json` `init_log` names the knob; `errors_in_log` 0; `harness.md5.start` = `harness.md5.cluster-start`. |
| 2. Readings | yes | `hist-end-pass2.excerpt.txt`: `CounterCacheKey` 8,738 / 69,905 / 559,240 / 436,906 = `Entries`; `ClockAndCount` = `Entries` + 1; `c0` histograms show 0 `CounterCacheKey` and 1 `ClockAndCount`; `heapinfo-end-pass2.txt` used heap 173,718 / 176,833 / 190,619 / 297,240 / 264,911 KB. |
| 3. Matched row | yes | `unit.txt` `U1` helper lines (false, true, true, true, true for the counter table; false for the regular table); `U4` rows (capacity 0: returned 0, size 0; 1 and 4 MiB: returned 34,952); `noguard/unit.txt` `U4` capacity 0: helper true, returned 34,952, weighted 0; `rl0/samples.csv` all zeros, `rl1` 8,738, `rl8` 69,905; `rl0/system.log.excerpt` shows the CounterCache file was read. |
| 4. Excluded rows | yes | `r8/samples.csv` 5 samples all 0 and `r8/hist-*.excerpt.txt` without `CounterCacheKey`; `c0` as above; no sample of any arm has `Size` > `Capacity` (`analyze_cluster_is.out`: 57 PASS, 0 FAIL). |
| 5. Observed vs. inferred | yes | The inferred statements are limited to the attribution of the whole-heap difference and (for the guard) to the patched copy differing by one line; neither is needed for the matched row, which rests on `Size`, `Entries`, histogram instances and `weightedSize`. |
| 6. Deviations and gaps | yes | Listed in §4.2 part 6; none changes a count. The `ClockAndCount` analyzer correction is in §3 item 5 with the first output kept. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | Knob varied (0, 1, 4, 8, 25/50 default, 64, runtime change), usage measured as the weigher's sum and as live heap, the disallow evidence taken at the unit tier (allocation, patched arm) and, for the reload gate, at both tiers, controls moved as predicted. |

### 5.2 Run 2?

**No** — 2026-10-27. The conclusion rests on observed counts that repeat to the entry across arms and across the unit and cluster tiers, the one inferred attribution (whole heap) does not carry the matched row, and no result refutes the case or confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive. **Outcome class:** true positive (positive, caps).

**Claim tested:** The counter cache's heap footprint is bounded by `counter_cache_size` (capacity > 0 enables it and the footprint stays at or near the capacity under a counter workload larger than the capacity), and with `counter_cache_size: 0` the helper returns false and the cache stays empty. Since the literal `0` is the gate, flipping capacity between 0 and a small positive value flips both the helper and the footprint. (B1) "Confirmed" below always means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed — B2g row 1 ("Helper flips with n=0 vs 1 and weightedSize <= n MiB (+slack) and scales ~linearly") with the additions (patched-literal arm retains nothing at 0; the reload at 0 loads nothing, at 1 and 4 MiB stays within the cap) | caps | run 1 + self-check | 2026-10-27 |
| Cluster | Confirmed — B3g row 1 ("Size and histogram bytes scale with the knob and stay at or below it") with the additions | caps | run 1 + self-check | 2026-10-27 |

The two tiers agree: `caps`. Nuance recorded, not a change of verdict: the bound is Caffeine's weight cap on the weigher's byte sum; the real heap of the cache is about 1.8 to 2.1 x that sum; the zero test at the checked line only decides whether a saved key is reloaded (with it removed, capacity 0 still retains nothing).

**Feedback filed:** the case file's section D "Stage-4 feedback" updated (uncommitted; no commit made); the audit amendments are in the case file's "B-audit" section (uncommitted); no section of the claim amended.
