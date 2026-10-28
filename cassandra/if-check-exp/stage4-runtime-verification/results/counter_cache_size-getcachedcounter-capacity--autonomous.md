# counter_cache_size-getcachedcounter-capacity--autonomous — stage-4 results  <!-- file: results/counter_cache_size-getcachedcounter-capacity--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`counter_cache_size-getcachedcounter-capacity--autonomous`](../../stage3-ai-deep-read/cases/counter_cache_size-getcachedcounter-capacity--autonomous.md)
>
> **Status:** verdict filed (2026-10-27) — run 1 done at both tiers, self-checked, no run 2
>
> **Outcome class:** **true positive** (estimate `positive`, effect `caps`) — [definition](../README.md#outcome-class)
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D. **Run 1 is a joint run for three case files that share the `counter_cache_size` knob** (`counter_cache_size-iscountercacheenabled-capacity--autonomous` and `counter_cache_size-putcachedcounter-capacity--autonomous`): one build, one unit class, one cluster sequence, three separate audits, predictions and verdicts. The raw readings are therefore the same; each file's conclusion below is matched against its own B2f/B2g/B3f/B3g and nothing is copied from a sibling's conclusion.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository commit `6e6cf92` holds the file as filed (sha256 `31e163ad8c8ab032d11885d66594f80d153bcdccb22c05a94bb4c4b7fef400d7`). The audit's amendments (section "B-audit", B2i, B3i, B2g and B3g additions, dated 2026-10-27) are **uncommitted**. **sha256 of the whole file after the amendments: `96a313e24284876d6febb33c4529808f62d974dde47b718314e3afa235461222`**, recorded 2026-10-27 before any reading (a shakedown of small N ran earlier and was deleted; it is where the entry weight 120 B and the stress-tool facts in B3i come from). B2f, B2g, B3f, B3g are frozen at this hash; only section D changes after it. |
| **Harness** | `harness/counter_cache_size-getcachedcounter-capacity--autonomous/` (uncommitted): `CounterCacheCapTest.java`, `unit-run.sh`, `Jmx.java`, `cluster-run.py`, `analyze_unit.py`, `analyze_cluster.py`, `selfcheck.py`, `README.md` (the same files are in the two sibling harness folders). md5s at the start of the run: `run1/harness.md5.start` (identical at the start of the cluster tier, `run1/harness.md5.cluster-start`); after the run `analyze_cluster.py` changed once (the `ClockAndCount` check, §3 item 5) and `selfcheck.py` was added: `run1/harness.md5.final`. The patched source copy's diff: `run1/noguard.diff`. |
| **Tiers and values** | Unit: capacity 0, 1, 4 (twice), 25 MiB (unit default), on the unpatched tree and on `tree-noguard`; production path at 0/1/4; reload (not this file's path; recorded); resize 4 -> 1 -> 0 -> 4. Cluster: `counter_cache_size` 0, 1, 8, 64 MiB, unset (50 MiB), a repeat of 8, a runtime change 64 -> 8 and a regular-table control (8 MiB). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

Estimate `positive` (claim: the counter cache's weight cap bounds heap, with the `getCachedCounter` guard (`ColumnFamilyStore.java:2501`, `getCapacity() == 0L`) as the on/off gate). Not a negative-estimate file, so no positive control is required; B2h/B3h carry their own controls. The literal is not settable, so the design uses two arms that differ in the one condition (B2i.6: a patched-literal source copy) as well as the capacity 0 / non-zero arms.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: on-heap bytes of the counter cache (the weigher's `unsharedHeapSize` sum); real heap via `GC.heap_info` and the class histogram. |
| A. Core question | knob varied, >= 3 values incl. default | Partly -> Met | B2b {0,1,4} and B3b {0,1,8} MiB had no default; B2i.2 adds the unit-yaml default (`init`, 25 MiB) and B3i.3 adds 64 MiB and the unset default (50 MiB on a 2 GiB heap). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly -> Met | B2d/B3d: weighted size is the check's own counter; B2i.8 and B3i.5 add heap after GC and `GC.heap_info`; the gap (histogram cannot attribute `byte[]`, weigher omits Caffeine node and map entry) is named. |
| A. Core question | usage driven to the limit and past it | Partly -> Met | B3c assumed one entry per id; `counter_write` makes five per key (B3i.2). 600,000 keys = 3,000,000 entries (343 MiB at 120 B) against caps of 1 to 64 MiB; unit N = 4 x capacity / weight (B2i.3). |
| B. Logic | each step says what it establishes | Met | B2e/B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Partly -> Met | "small slack", "about 4x", "within ~2x" were undefined; B2i.4 and B3i.5/6 make them numeric before the run. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly -> Met | No row for the production write path, the patched-literal arm or the allocation evidence; added as B2g/B3g additions. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly -> Met | At capacity 0 the cache is empty with or without the guard (Caffeine's `maximumWeight(0)`); the guard's own effect (no key built) is therefore shown by allocation per call (B2i.7) and by the patched-literal arm (B2i.6). |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h plus the regular-table control (`r8`, `U3` control) and the patched arm. |
| C. Specific | a human can follow it from the intro and B1 | Met | A1-A3, B1. |
| C. Specific | an AI can run B2/B3 without re-deriving the code path | Partly -> Met | The stress tool, table and per-key entry count, the JMX bean names and the process check were not exact (`pgrep -f` matches its own shell); supplied in B3i. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly -> Met | B2i/B3i. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Unit test, JMX client, run scripts and analyzers are step-1 work (harness folder); build-test tree, stress, nodetool, jcmd exist. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met (after B3i.2) | 3,000,000 entries offered vs 559,240 at the largest cap; about 30 s to 100 s per pass at 7,500 to 28,000 ops/s; data under 200 MB on the 63 GB local disk; heap 2 GiB. |
| D. Runnable | load-bearing citations spot-checked | Met | Re-read in `cassandra/cassandra-5.0.9/` (clean `git status`): `ColumnFamilyStore.java:2498-2503`; `CacheService.java:172-185, 344-350`; `DatabaseDescriptor.java:834-844`; `Config.java:480`; `InstrumentingCache.java:77`; `CaffeineCache.java:53-57, 61-70, 72-75`; `CounterMutation.java:213, 249`; `conf/cassandra.yaml:585-595`. All hold at the cited lines. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Make the workload exact: `cassandra-stress counter_write`, 600,000 keys, five entries per key, pass 2 on the last 50,000 keys; drop `-pop dist=uniform` (stalls) | Applied, B3i.2, 2026-10-27, before the freeze | The filed table and id count cannot be created by the tool; the entry count per key changes the arithmetic. |
| 2 | Add the default (unit `init`, cluster unset = 50 MiB) and 64 MiB to the knob values | Applied, B2i.2 and B3i.3 | README group A asks for the default among at least three values. |
| 3 | Define slack, "about 4x/8x", "within ~2x" and the hit-rate wording numerically | Applied, B2i.4 and B3i.5/6 | So a reading can contradict the prediction. |
| 4 | Add heap-after-GC and `GC.heap_info` as the real-resource reading, and name the histogram gap | Applied, B2i.8 and B3i.5 | The counter is the weigher's own sum. |
| 5 | Add the production write path (`U3`), the regular-table control and the runtime change (`rt64`) | Applied, B2i.5 and B3i.3/8 | Controls named in B2h/B3h had no instrument. |
| 6 | Add a patched-literal arm (`tree-noguard`) and the allocation-per-call observation | Applied, B2i.6/7 | The literal cannot be varied by configuration; two arms that differ in the one condition show what it does. |
| 7 | Replace the `pgrep -f` process check by `ps -eo cmd \| grep '[C]assandraDaemon'` run on the node | Applied, B3i.7 | `pgrep -f` inside an ssh string matches its own shell. |
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
| Full logs (path, outside the repo) | `pc39:~/s4-cc/run1/{unit-base,unit-noguard,cluster}/` (full `ant.log`, per-arm `system.log.full`, all histograms `hist-*.txt`, stress outputs); `~/s4-cc/logs/build-*.log`; excerpts in `results/counter_cache_size-getcachedcounter-capacity--autonomous/run1/` | |

**Own-tag isolation (tag `cc`):** loopback address `127.39.9.1`, JMX 7439, native 9042 and storage 7000 only on that address, no Byteman; every kill by PID. **Deviations from the filed environment (none changes B1):** the filed `UPDATE ... SET c = c + 1` over 2,000,000 ids is `cassandra-stress counter_write` (five counters per key, B3i.2); the sampler is a JMX client rather than `nodetool info` (rounded); the saved-cache step uses the `saveCaches` JMX operation.

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | audit | B3c | the filed table (`id bigint, c counter`, 2,000,000 ids) cannot be created by `cassandra-stress`; `counter_write` makes five cache entries per key | B3i.2 | 2026-10-27, before the freeze | none (uncommitted) |
| 2 | shakedown (not a reading) | B3c | `-pop dist=uniform(...)` stalls `counter_write` after 2,000 ops | pass 2 uses `-pop seq=550001..600000` (B3i.2) | 2026-10-27, before the freeze | none |
| 3 | shakedown | B3e | no `nodetool drainsave`; the cache MBean is `org.apache.cassandra.db:type=Caches` and its capacity setters are attributes, not operations | `Jmx.java` fixed; B3i.8 | 2026-10-27, before the freeze | none |
| 4 | audit | B3e/B4 | `pgrep -f CassandraDaemon` inside an `ssh` string matches its own shell | `ps -eo cmd \| grep '[C]assandraDaemon'` (B3i.7) | 2026-10-27 | none |
| 5 | run 1, analysis (not a run step) | harness, `analyze_cluster.py` | the first analysis flagged the 0 MiB arm: it required 0 `ClockAndCount` instances, but one static instance (`ClockAndCount.BLANK`) exists in every JVM that has loaded the class (0 `CounterCacheKey`; in the other arms `ClockAndCount` = entries + 1). The threshold was corrected to "at most 1" and the analysis re-run on the unchanged raw files; the first output is kept as `run1/analyze_cluster_get.v1-overstrict-ClockAndCount.out`. | analyzer only; B3f/B3g unchanged | 2026-10-27 | none |

No step of the unit or cluster runbook failed in run 1; neither tier was restarted.

## 4. Run 1

**Scope:** unit tier on the unpatched tree and on the patched-literal tree; cluster tier arms `c0 c1 c8 c64 cdef c8b rt64 r8` and, for the reload path, `sv8 rl0 rl1 rl8` (run for all three files; used as evidence by the file whose gate it is). **Command log:** `counter_cache_size-getcachedcounter-capacity--autonomous/run1/unit/{base,noguard}/session.log`, `run1/cluster/session.log`; analyzer output `run1/analyze_unit_*.out`, `run1/analyze_cluster_get.out`; independent self-check `run1/selfcheck.out`.

### 4.1 Readings

**Unit tier** (`run1/unit/base/unit.txt`, `run1/unit/noguard/unit.txt`; JUnit `BUILD SUCCESSFUL` in both, `ant-tail.log`).

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| U2 `cfs.putCachedCounter` loop, then `cfs.getCachedCounter` over all keys (unpatched tree) | capacity 0: `size` 0, `weightedSize` 0, `getHits` 0 of 200,000; 1 MiB: 1,048,560 / 8,738 entries, `getHits` 8,738 (last key hit, first key missed); 4 MiB (twice): 4,194,240 / 34,952, `getHits` 34,952; 25 MiB unit default (873,813 puts): 26,214,360 / 218,453. `weightedSize` never above capacity (immediate or settled reading); size ratio 4 MiB / 1 MiB = 4.000 | `run1/unit/base/unit.txt` `U2 arm=0..4`; `run1/analyze_unit_get_base.out` (24 PASS, 0 FAIL) |
| U2 heap after GC (`heapDelta`) | 0 MiB: 2,752 B; 1 MiB: 1,808,024 B (1.72 x weight); 4 MiB: 7,390,440 and 7,390,752 B (1.76 x); default: 45,708,008 B (1.74 x) | `unit.txt` `U2`; `analyze_unit_put_base.out` INFO lines |
| U2 allocation per `getCachedCounter` call (`ThreadMXBean.getThreadAllocatedBytes`, 200,000 calls) | unpatched capacity 0: 72 B/call; unpatched 1 MiB: 299 B; patched capacity 0: 296 B. The unpatched capacity-0 call allocates 227 B less than at 1 MiB and 224 B less than the patched copy (both >= 100) | `unit.txt` `U2`; `run1/analyze_unit_compare.out` |
| U3 production path (`CounterMutation.apply`, 60,000 updates, passes the gates at `CounterMutation.java:213`, `ColumnFamilyStore.java:2501/2508`) | `weightedSize` 0 at 0; 1,048,560 at 1 MiB; 4,194,240 at 4 MiB; 20,000 plain inserts into the regular table at 4 MiB leave the cache empty | `unit.txt` `U3` |
| U5 runtime resize | 4 MiB filled (4,194,240); `setCapacity` to 1 MiB: 1,048,560 at the first read; to 0: 0 and `getCachedCounter` of a recent key null; back to 4 MiB: refills to 4,194,240 | `unit.txt` `U5` |
| Patched-literal arm `tree-noguard` (guards `if (false)`, helper `>= 0`) | capacity 0: `size` 0, `weightedSize` 0, `getHits` 0 although the key is built and looked up on every call; other arms identical to the unpatched tree | `run1/unit/noguard/unit.txt`; `run1/analyze_unit_get_noguard.out` (24 PASS, 0 FAIL) |

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

(Files: `cluster/<arm>/hist-end-pass2.excerpt.txt`, `heapinfo-end-pass2.txt`; the ratios are printed by `analyze_cluster_get.out`.)

Pass-2 hit rate (hits delta / requests delta, 250,000 requests): 1 MiB 0.0000, 8 MiB 0.0345 (repeat 0.0714), 64 MiB 0.0000, default 0.0223 (`analyze_cluster_get.out` INFO lines; `samples.csv` `hits`). It is not a dose-response: Caffeine's TinyLFU admission keeps the entries admitted first, not the last keys of pass 1, so the last 50,000 keys mostly miss even when the cache could hold them (64 MiB: 0).

### 4.2 Conclusion and logic

Tag every statement in parts 1–4 as **[observed: `<file>`]** or **[inferred: `<reason>`]**.

1. **Validity** — valid. The limit was reached: in every non-zero arm `Size` stopped within 80 B of the cap at the end of pass 1 (`Size` - `Capacity` between -8 and -80 B, i.e. less than one 120 B entry from full) while 3,000,000 entries (343 MiB) were offered, so the cap, not the workload, ended the growth [observed: `c1`, `c8`, `c64`, `cdef` `samples.csv`]; in the unit tier every arm received 4 x capacity of entries [observed: `unit.txt` `U1`/`U2` `puts`]. Hold-fixed settings: the knob applied in each arm (`Initializing counter cache with capacity of N MiBs` in each arm's init log, and `Capacity` = N x 1,048,576 at every sample; `cdef` says 50 MiBs) [observed: `cluster/<arm>/summary.json` `init_log`, `samples.csv`]; the same stress commands, a fresh node directory per arm, `row_cache_size` 0, heap 2 GiB G1 (`jvm_flags`) [observed: `cassandra.yaml.<arm>`, `session.log`]; no `ERROR` line in any `system.log` [observed: `summary.json` `errors_in_log` 0]; harness files unchanged between the start of the unit tier and the start of the cluster tier [observed: `harness.md5.start`, `harness.md5.cluster-start`].
2. **Readings** — nothing contradicts another. `Entries` x 120 B = `Size` within 240 B in every capped arm; histogram `CounterCacheKey` count = `Entries`; final JMX = last sample [observed: `samples.csv`, `hist-end-pass2.excerpt.txt`, `summary.json`]. At 0 MiB the cache `Requests` counter is 0 after 3,250,000 counter-cell updates, in every non-zero arm it is 3,250,000 (every update looked the cell up) [observed: `c0/samples.csv`, `c1/samples.csv`]. The pass-2 hit rate is 0.0000 (1 MiB), 0.0345 (8 MiB; repeat 0.0714), 0.0000 (64 MiB), 0.0223 (default): not monotone, because TinyLFU admission keeps the first-admitted entries and the last 50,000 keys of pass 1 mostly miss; the file's rows use only 1 MiB < 8 MiB < 100 %.
3. **Matched row** — unit B2g row 1, "weightedSize <= capacity for n=1,4; size scales with n; n=0 empty | claim confirmed": `weightedSize` 0, 1,048,560, 4,194,240 (26,214,360 at the 25 MiB default); `size` 0, 8,738, 34,952 (ratio 4.000) [observed: `unit.txt` `U2`]; at 0 `getCachedCounter` returned null for all 200,000 keys, at 1 and 4 MiB it returned non-null exactly for the cached recent keys (`getHits` = `size`) [observed: `U2` `getHits`]. B2g additions: allocation per `getCachedCounter` call at capacity 0 was 72 B against 299 B at 1 MiB and 296 B on the patched copy (the key is built and looked up only when the guard does not fire) [observed: `analyze_unit_compare.out`]; the patched copy, which builds the key and looks it up at capacity 0, still retained nothing [observed: `noguard/unit.txt`]; the production path held `weightedSize` 0, 1,048,560, 4,194,240 at 0, 1, 4 MiB [observed: `U3`]. Cluster B3g row 1, "Size tracks and stays under capacity, histogram bytes proportional to capacity | claim confirmed", with B3f numbers: c=0 `Entries` 0, hit rate 0 (`Hits` 0, `Requests` 0), 0 `CounterCacheKey`; c=1 MiB `Size` 1,048,560 <= 1 MiB, `Entries` 8,738 (inside 7 to 10 thousand), pass-2 hit rate 0.0; c=8 MiB `Size` 8,388,600 <= 8 MiB, `Entries` 69,905 = 8.000 x, pass-2 hit rate 0.0345 (above the 1 MiB arm, below 100 %); the named classes were 0.533 x `Size` in every arm [observed: `c0/c1/c8 samples.csv`, `hist-end-pass2.excerpt.txt`].
4. **Excluded rows** — unit: "weightedSize far above capacity": no [`U2`]; "n=0 yet size > 0 or gets return non-null": no [`U2` arm 1]; "N too small to reach capacity": no, 4 x capacity offered and the cap reached in every non-zero arm [`U2`]; additions "allocation at 0 not >= 100 B below": no (227 and 224 B below) [`analyze_unit_compare.out`]; "`tree-noguard` retains entries at 0": no; "`U3` above capacity or entries at 0": no. Cluster: "Histogram bytes or Size grow with workload despite capacity": no, pass 2 equals pass 1 in `Size` and `Entries` for all capped arms [`samples.csv`]; "c=0 shows entries": no; "Entries never reach capacity": no; additions "whole-heap increase not proportional": no (1.78 to 2.06 x for 8 MiB and above; 64 / 8 MiB factor ratio 0.91); "`rt64` Size after the change above 8 MiB": no; "`r8` Entries > 0": no. No Refuted row applies.
5. **Observed vs. inferred** — inferred: (a) that the whole-heap difference to the 0 MiB arm is the cache's heap (identical commands in every arm; 8 MiB gives 2.06 and 1.72 in two runs); (b) that the guard at `ColumnFamilyStore.java:2501` is what produces the 72 B/call (no key built) [observed allocation; inferred attribution to the guard because the patched copy differs by exactly that line and allocates 296 B]; (c) that on the real path at capacity 0 the lookup is skipped by `CounterMutation.java:213` before line 2501 is reached (the cluster `Requests` 0 is the combined effect of both gates). Everything else is observed.
6. **Deviations and gaps** — (a) In the cluster the guard at line 2501 is not reachable with capacity 0: `CounterMutation.java:213` already skips `updateWithCurrentValuesFromCache`, so the `Requests` 0 reading cannot be attributed to line 2501 alone; the unit tier calls `getCachedCounter` directly and is the only place the line's own branch is observed (and it matters on the real path only for a capacity change between the two checks). (b) The weigher's 120 B excludes Caffeine's node and the map entry: real heap 1.8 to 2.1 x the weighted size. (c) Each arm ran once, except 8 MiB (identical `Entries`). (d) Hit-rate predictions were met on their letter, but the hit rate is not a clean dose-response (§4.1); the claim does not rest on it. (e) One analyzer threshold was corrected after the run (§3 item 5).
7. **Core question** — usage followed the constraint: with `counter_cache_size` 1, 8, 64 MiB and the 50 MiB default the counter cache's `Size` stopped within one entry of the cap after 3,000,000 entries were offered, `Entries` scaled 1 : 8 : 64, the heap of its classes and the whole-heap difference followed with a stable factor, and with 0 nothing was cached and no lookup was counted (parts 1 and 3). The constraint caps the cache's on-heap use through Caffeine's `maximumWeight`; the `== 0L` guard saves the key construction and lookup at capacity 0 (72 vs 299 B per call) but is not what bounds usage (the patched copy retains nothing at 0 either) (parts 3 and 5).

**Conclusion (one line):** unit B2g row 1 (with the allocation, patched-literal and production-path additions) and cluster B3g row 1 — confirmed; the cap is the weight cap, the guard is the disabled-case short-circuit.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck.out` re-derives the facts by a route independent of `analyze_*.py` (unit lines split by token; cluster values from the dictionaries in `session.log`, `system.log.full` init lines, `stress-*.results` totals, histograms re-parsed with a second parser, `summary.json`): 93 checks hold, 0 fail. I then re-opened the raw files each part cites (the copies under `results/counter_cache_size-getcachedcounter-capacity--autonomous/run1/`):

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `c1`/`c8`/`c64`/`cdef` `samples.csv`: `Size` 1,048,560 / 8,388,600 / 67,108,800 / 52,428,720 at end of pass 1 against capacities 1,048,576 / 8,388,608 / 67,108,864 / 52,428,800 with `Requests` 3,000,000; `unit.txt` `puts` = 4 x capacity / 120; each `summary.json` `init_log` names the knob; `errors_in_log` 0; `harness.md5.start` = `harness.md5.cluster-start`. |
| 2. Readings | yes | `hist-end-pass2.excerpt.txt`: `CounterCacheKey` 8,738 / 69,905 / 559,240 / 436,906 = `Entries`; `ClockAndCount` = `Entries` + 1; `c0` histograms show 0 `CounterCacheKey` and 1 `ClockAndCount`; `heapinfo-end-pass2.txt` used heap 173,718 / 176,833 / 190,619 / 297,240 / 264,911 KB. |
| 3. Matched row | yes | `unit.txt` `U2` rows (arm 1: `getHits=0`, weighted 0; arm 2: 1,048,560 / 8,738; arm 3: 4,194,240 / 34,952) and the allocation columns (`putAllocPerCall` 104 / 837 / 4 MiB 808; `getAllocPerCall` 72 / 299); `noguard/unit.txt` `U2` arm 1: 720 and 296 B/call, weighted 0; `U3` rows; cluster `c0/c1/c8 samples.csv`, `stress-pass*.results` (0 errors). |
| 4. Excluded rows | yes | `rt64/samples.csv`: `after-setcap` rows 8,388,600 / 69,905 from the first sample; `r8/samples.csv` all 0; pass-2 `Size`/`Entries` equal to pass 1 in `c1`, `c8`, `c64`, `cdef`; `analyze_cluster_get.out`: 48 PASS, 0 FAIL. |
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

**Claim tested:** Counter-cache heap usage is bounded by the capacity: with `counter_cache_size = 0` the cache stays empty and `getCachedCounter` returns null without lookup, and with a small non-zero capacity the weighted size never exceeds it by more than a small slack while the entry count plateaus. (B1) "Confirmed" below always means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed — B2g row 1 ("weightedSize <= capacity for n=1,4; size scales with n; n=0 empty") with the additions (patched-literal arm retains nothing at 0; allocation per call shows the guard fired) | caps | run 1 + self-check | 2026-10-27 |
| Cluster | Confirmed — B3g row 1 ("Size tracks and stays under capacity, histogram bytes proportional to capacity") with the additions | caps | run 1 + self-check | 2026-10-27 |

The two tiers agree: `caps`. Nuance recorded, not a change of verdict: the bound is Caffeine's weight cap on the weigher's byte sum; the real heap of the cache is about 1.8 to 2.1 x that sum; the zero test at the checked line only short-circuits the lookup at capacity 0 (with it removed, capacity 0 still retains nothing).

**Feedback filed:** the case file's section D "Stage-4 feedback" updated (uncommitted; no commit made); the audit amendments are in the case file's "B-audit" section (uncommitted); no section of the claim amended.
