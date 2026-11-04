# slab-region-size-region-allocate-capacity--autonomous — stage-4 results  <!-- file: results/slab-region-size-region-allocate-capacity--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`slab-region-size-region-allocate-capacity--autonomous`](../../stage3-ai-deep-read/cases/slab-region-size-region-allocate-capacity--autonomous.md)
>
> **Status:** verdict filed (run 1 done and self-checked, no run 2) — 2026-10-26
>
> **Outcome class:** true negative (estimate `negative`, effect `does not cap`) — [definition](../README.md#outcome-class)
>
> **Agent:** guided / autonomous (the suffix of the case-file stem). For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Relative links in this template** are written for where a *copy* of it lives
— inside `results/` — not for the template's own location one level up.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../README.md`](../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | The case file at repository HEAD `e776524` plus the uncommitted audit amendments of 2026-10-26 (the file is untracked; the orchestrator commits). sha256 of the whole file after the amendments (frozen before any reading): `da33f4b9700b1508f7649518e356fa70a45707f6e238fd9624050f1c781009cd`. sha256 of the prediction and conclusions text (from `**B2f. Predictions` up to `**B2h.`, then from `**B3f. Predictions` up to `**B3h.`, the two pieces concatenated: B2f, B2g, B3f, B3g): `24cffe3a55171d115e1780aae904a6ff43fdfafa6961893e0773e4e8a8f3831c` (8591 characters). Section D takes the feedback afterwards, so the whole-file hash changes then and the table hash does not. |
| **Harness** | `harness/slab-region-size-region-allocate-capacity--autonomous/` (`replay.py`, `SlabWasteProbe.java`, `unit-run.sh`, `instrument-check.sh`, `make-node-yaml.sh`, `client.py`, `Jmx.java`, `cluster-run.py`, `selfcheck.py`, `README.md`); `replay.py` exists at the freeze, the rest was written after it and before run 1; not committed by this agent (the orchestrator commits). Whole-file hash after the second same-day amendment (B3c/B3d, below): `da33f4b9700b1508f7649518e356fa70a45707f6e238fd9624050f1c781009cd`; the table hash is unchanged by it. Adapted from the `max-cloned-size-allocate-size--autonomous` harness (same node yaml, JMX reader, driver client; code only, no readings read). |
| **Tiers and values** | Unit (B2): S in {116509, 131072, 100000, 4096, 131073}, N = 400, REGION_SIZE 1 MiB (stock), plus 512 KiB and 2 MiB for S = 116509 and 100000; limit tests at L = 64 and 128 MiB (N = 1400), `heap_buffers` limit test, eight-thread rounds. Cluster (B3): arms `a64`, `a128`, `a64b`, `e64`, `f64` (`offheap_buffers`, S = 116509 / 131068 / 131072) and `h64` (`heap_buffers`); 4000 rows each. |
| **Audit bottom line** | **Ready after amendments** - 2026-10-26 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: heap (`heap_buffers`) or direct memory (`offheap_buffers`) held by 1 MiB slab regions; the constant bounds one slab only. |
| A. Core question | knob varied, >= 3 values incl. default — or another approach, with the reason | Met | B2b: `REGION_SIZE` is a compile-time constant (A1), varied in the unit tier at 512 KiB / 1 MiB (default) / 2 MiB; the pool limit (64 / 128 MiB) is the positive-control knob in both tiers. The cluster tier cannot vary the constant (B3b says so). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d: `regionCount` x REGION_SIZE by reflection and the `BufferPoolMXBean` "direct" delta; B3d: direct delta and RssAnon next to the accounted gauge. Gaps named: region count unreadable in the cluster tier; heap secondary only. |
| A. Core question | usage driven to the limit and past it | Not met, fixed by amendment | B3a left `memtable_cleanup_threshold` at 1/3 (2 writers), so the cleaner flushes at ~21 MiB of 64 MiB and the pool limit is never reached; also B2c's N = 700 never reaches L = 128 MiB. Amended to 0.99 / 1 writer and N = 1400. |
| B. Logic | each step says what it establishes | Met | B2e and B3e number the steps and name the observable. |
| B. Logic | prediction stated in numbers or a clear relation | Partly, fixed by amendment | B2f 2 MiB ratio 1.059 was wrong at N = 400 (24 regions, 1.080); B3f's S = 131072 "ratio 1.00" ignores the 4-byte key cloned into the same region (7 rows per region, 1.143), 'a few' and 'about' had no bands. All replaced by exact replay values (`replay.py`, run before any probe) and bands. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly, fixed by amendment | Rows for confirm, refute, flat, limit-not-reached, control-failed existed; missing: replay/instrument mismatch, exact-fit ratio not 1.0, eight-thread accounting, any-other-combination. Added. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly, fixed by amendment | B3g row 1 lacked disallow evidence; amended to need BlockedOnAllocation growth and >= 2 MEMTABLE_LIMIT flush lines per arm. Unit: the worker parked in `SubAllocator.allocate` (stack printed). |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: L = 64 vs 128 MiB (cap that binds), S = 131072 / 131068 exact fit, S = 131073 unslabbed, eight-thread run, both allocation types. |
| C. Specific | a human can follow it from the intro and §9a | Met | A1-A3 and B1; B2f/B2g/B3f/B3g are readable alone. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly, fixed by amendment | N for the limit test, the probe form, how REGION_SIZE variants are built, arms list, row layout and key layout were missing; added. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly, fixed by amendment | Sampling (200 ms), baseline definition, `rho`, peak definitions, row count (4000), compression, compaction, tmpfs paths added to B3a-B3e. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | pc07 has JDK 11, Ant, `~/.m2`; trees by `copy-source.sh`; the closed sibling harness supplies yaml / JMX / client patterns. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met after amendment | 4000 x 116 KB = 466 MB = 7.3 x 64 MiB, 3.6 x 128 MiB; data and commit log on tmpfs (104 GiB free); heap 2 GiB + up to 150 MiB regions fits (213 GiB available). |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `SlabAllocator.java` :51-52 constants, :83-112 allocate, :116-121 setDiscarded, :126-153 getRegion, :197-206 (line 201 the check); `SlabPool.java` allocateOnHeap; `MemtableAllocator.java` :169-196 (A3 says 169-197); `MemtablePool.java` SubPool; `AbstractAllocatorMemtable.java:89,249`; `DatabaseDescriptor.java:772-773`; `Config.java:186-190,524`; `SkipListMemtable.java:115` (key clone). All hold; line nits only. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | B3a `memtable_cleanup_threshold: 0.99`, `memtable_flush_writers: 1`, `commitlog_total_space: 4096MiB`, tmpfs directories | Applied 2026-10-26 | Limit never reached at 1/3; commit log must not force flushes. |
| 2 | B3 row = 4-byte key + value: exact-fit S is 131068; add arms `e64`, `f64`; rewrite B3f | Applied 2026-10-26 | Source: `SkipListMemtable.java:115` clones the key into the same region. |
| 3 | B2f exact replay table (2 MiB: 24 regions, 1.080); add S = 4096, heap, eight-thread, discard rows | Applied 2026-10-26 | Arithmetic from `Region.allocate`. |
| 4 | B2c N = 1400 for the limit test (N = 700 never reaches 128 MiB) | Applied 2026-10-26 | Stall at the 1152nd allocation. |
| 5 | B2a probe class and class-directory variants instead of a JUnit class and rebuilds | Applied 2026-10-26 | `ant testsome` side effects; same class without rebuild. |
| 6 | B3d/B3g reading rules, bands, disallow evidence, row for a missed prediction | Applied 2026-10-26 | Untestable thresholds; protocol requires direct disallow evidence. |
| 7 | B3 runs 6 lifetimes (one repeat) instead of two per setting | Applied 2026-10-26 | Session length; `a64b` estimates the noise. |
| 8a | Second amendment, 2026-10-26, after a shakedown that read no capacity value: B3c/B3d split the workload into a throttled phase A (50 rows/s x 3000) and an unthrottled phase B (2000 rows); relations on phase A | Applied 2026-10-26 (case file section D item 6b) | `AllMemtablesOffHeapDataSize` covers the current memtable only (`TableMetrics.java:876-883`), so flush overlap would inflate every direct/accounted ratio. B3f/B3g unchanged (frozen table hash identical). |
| 8 | Upstream doc candidate: the `SlabAllocator` javadoc (:34-43) does not say that region tails are uncharged | Left for stage 3 | Not needed for a valid run. |

**Bottom line: Ready after amendments** (2026-10-26). The amendments are in section D of the case file and marked in place.

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-26 (unit 10:51-10:52 EDT; cluster 10:52-11:12 EDT) | not done |
| Node (CloudLab name and type) | `pc07` (`node0.jason92-320876`), 40 cores, 251 GiB; run locally | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2, 5.15.0-187-generic | |
| JDK (`java -version`) | openjdk 11.0.32.1 (2026-08-18) | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-b7-sr7` by `copy-source.sh` at repository commit `e776524` (stock; `git describe` = cassandra-5.0.9), `ant jar` 1 min 14 s | |
| Case-file commit / harness commit | uncommitted (orchestrator commits); case file sha256 `da33f4b9…09cd`, table hash `24cffe3a…831c` | |
| Storage for node data | tmpfs `/dev/shm/s4-b7-sr7` (wiped per lifetime) | |
| Full logs (path, outside the repo) | `~/s4-b7-sr7-logs/run1/{unit,cluster}`, first unit attempt `~/s4-b7-sr7-logs/run1-attempt1`; excerpts in `results/slab-region-size-region-allocate-capacity--autonomous/run1/` | |

## 3. Runbook defects

Every step a run could not execute as written. The run stops at the
defect; the fix is made in the case file (dated) if it leaves §9a unchanged,
and the affected tier restarts from its beginning. If the fix would change
§9a, the case goes back to the audit. "None" if there were none.

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | shakedown (no capacity value used) | B3c/B3d | `AllMemtablesOffHeapDataSize` is the current memtable only; with an unthrottled writer the flushing memtable is in the direct reading and not in the gauge (direct 79.5 MiB against a gauge of 0 right after a switch). | Case file B3c/B3d amended (phase A throttled, phase B unthrottled; relations on phase A). B3f/B3g untouched. | 2026-10-26, before run 1 | none yet (uncommitted) |
| 2 | unit attempt 1 (readings discarded; kept in `run1-attempt1`) | B2d | The probe let the returned slices go, so a retired on-heap region was garbage and `heap_buffers` retained heap read 1.5 MB against 52 MB real. | Probe keeps the returned slices (as memtable cells do); the whole unit tier restarted. | 2026-10-26 | n/a (harness) |
| 3 | unit attempt 1 | B2f | The probe applied the stock-build literal check (575 allocations / 72 regions) also under the 512 KiB and 2 MiB class directories (a probe bug; those runs matched their own replay). | Literal check only at REGION_SIZE = 1 MiB. | 2026-10-26 | n/a (harness) |
| 4 | unit attempt 1 | B2d | An RssAnon sanity check (`rss >= direct - 2 MiB`) failed for S = 131073 (48.3 MB against 52.4 MB): glibc reuses memory freed before the baseline. Not a frozen prediction. | Turned into a reading (`rss_minus_direct`). | 2026-10-26 | n/a (harness) |

Attempt 1's other results were identical to run 1's (all B2f table rows, all limit rows).

## 4. Run 1

**Scope:** both tiers, all values of B2/B3 as amended: unit (5 value sizes x stock build, S = 116509 and 100000 on the 512 KiB and 2 MiB builds, 4 limit runs plus 2 on the variants, heap, 20 eight-thread rounds) and cluster (arms `a64 a128 a64b e64 f64 h64`). **Command log:**
`slab-region-size-region-allocate-capacity--autonomous/run1/` (`unit/summary.txt`, `unit/*.out`, `cluster/analysis.txt`, `cluster/<arm>/{summary.txt,phases.json,bigA.out,bigB.out,flush-lines.txt}`, `selfcheck-output.txt`; the first unit attempt is in `attempt1/`).

### 4.1 Readings

**Unit tier** (`unit/summary.txt`: 17 scenarios, 104 probe checks, 2 MISMATCH, both in `heap_buffers` rows, below)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Instrument known answers (1024 x 1 KiB = 1 region; L 4 MiB, S 116509 = 35 allocations in 5 regions; variants report 524288 / 2097152) | ok | `unit/instrument-summary.txt` |
| Waste, stock 1 MiB, N = 400: regionCount / real / owns / real over owns for S = 116509, 131072, 100000, 4096, 131073 | 50 / 52,428,800 / 46,603,600 / 1.12499; 50 / 52,428,800 / 52,428,800 / 1.00000; 40 / 41,943,040 / 40,000,000 / 1.04858; 2 / 2,097,152 / 1,638,400 / 1.28000; 0 / (400 dedicated buffers) 52,429,200 / 52,429,200 / 1.0. Every row equals the B2f table; `onHeap` owns 0; direct delta equals real (count 50, 50, 40, 2, 400) | `unit/stock-waste_offheap_*.out` |
| Waste on the 512 KiB build (S = 116509, 100000) | 100 regions, real 52,428,800, ratio 1.12499; 80 regions, real 41,943,040, ratio 1.04858 | `unit/v512-waste_offheap_*.out`, `unit/v512.diff` |
| Waste on the 2 MiB build | 24 regions, real 50,331,648, ratio 1.07999; 20 regions, real 41,943,040, ratio 1.04858 | `unit/v2048-waste_offheap_*.out` |
| Real against REGION_SIZE at fixed N, S | S = 116509: 52.43 / 52.43 / 50.33 MB for 512 KiB / 1 MiB / 2 MiB (2 MiB over 512 KiB = 0.960); S = 100000: 41.94 MB at all three (1.000); owns identical in every build | `selfcheck-output.txt` |
| Limit, offheap, L = 64 MiB, S = 116509, N = 1400 | worker WAITING in `MemtableAllocator$SubAllocator.allocate` (WaitQueue park); 575 allocations done, owns 66,992,675, 72 regions, real 75,497,472 = 1.125000 L; direct delta equals real | `unit/stock-limit_offheap_64_116509_1400.out` |
| Limit, offheap, L = 128 MiB, S = 116509 | stall after 1151, owns 134,101,859, 144 regions, real 150,994,944 = 1.125000 L | `unit/stock-limit_offheap_128_116509_1400.out` |
| Limit, offheap, L = 64 MiB, S = 131072, N = 700 | stall after 512, owns 67,108,864 = L, 64 regions, real = L | `unit/stock-limit_offheap_64_131072_700.out` |
| Limit under the REGION_SIZE builds (L = 64 MiB, S = 116509) | stall after 575 on both; 144 regions (512 KiB) and 34 regions (2 MiB), real 75,497,472 and 71,303,168 (1.125 L and 1.0625 L); each equals its replay | `unit/v512-limit_*.out`, `unit/v2048-limit_*.out` |
| Eight threads, 20 rounds of 400 x 116509 | owns 46,603,600 and regionCount 50 in every round; final `RACE_ALLOCATED` size 4; direct delta 1,052,770,301 = (1000 + 4) x 1 MiB - 3 B | `unit/stock-threads_116509_20.out` |
| `heap_buffers` waste (S = 116509, N = 400) and limit (L = 64 MiB): counters | on-heap counter stalls at 575 (66,992,675), `offHeap` 0, direct delta 0, regionCount 72 | `unit/stock-limit_heap_*.out`, `unit/stock-waste_heap_*.out` |
| `heap_buffers`: retained heap within 3 MiB of real (B2f bullet) | **missed**: heap delta 104,349,328 against real 52,428,800 (waste run) and 151,025,608 against 75,497,472 (limit run), 2.0 times real. Diagnostic (not a reading): with `-XX:G1HeapRegionSize=8m` the delta is 51,438,008 (0.98 times); with 1m it is 104,321,696 | `unit/stock-waste_heap_*.out`, `unit/heap-waste-G1region{1m,8m}.out` |

**Cluster tier** — phase A = first 60 s at 50 rows/s, phase B = 2000 rows in 1.4-1.9 s; L = `memtable_offheap_space` (`memtable_heap_space` for `h64`). `peak_acc`, `peak_dir`, `rho`, RssAnon over phase A; blocked and flushes over both phases (`cluster/analysis.txt`):

| Capacity value | Run | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| L 64 MiB, S 116509 | a64 | peak_acc; peak_dir; rho (n); RssAnon peak; blocked; MEMTABLE_LIMIT flushes | 63.2 MiB (0.988 L); 76.2 MiB (1.191 L); 1.184 (27); 82.8 MiB; 0 to 120; 8 | `cluster/a64/summary.txt`, `cluster/analysis.txt` |
| L 128 MiB, S 116509 | a128 | same | 126.7 MiB (0.990 L); 146.9 MiB (1.147 L); 1.146 (21); 170.5 MiB; 0 to 76; 4 | `cluster/a128/` |
| L 64 MiB, S 116509 (repeat) | a64b | same | 63.3 MiB (0.990 L); 77.2 MiB; 1.184 (26); 94.4 MiB; 0 to 132; 8 | `cluster/a64b/` |
| L 64 MiB, S 131068 (exact fit) | e64 | same | 63.3 MiB (0.988 L); 68.6 MiB (1.072 L); 1.054 (23); 68.9 MiB; 0 to 193; 9 | `cluster/e64/` |
| L 64 MiB, S 131072 | f64 | same | 63.1 MiB (0.986 L); 78.7 MiB (1.230 L); 1.210 (25); 89.5 MiB; 0 to 192; 9 | `cluster/f64/` |
| heap space 64 MiB, `heap_buffers`, S 116509 | h64 | on-heap peak; off-heap peak; direct peak; blocked; flushes | 63.3 MiB (0.989 L); 0; 1.6 MiB; 0 to 53; 8; class histogram at the 0.9 mark: `[B` 90,488,768 B against baseline 15,983,944 B (growth 71.1 MiB), gauge 60.7 MiB before and 1.4 MiB after (a flush intervened) | `cluster/h64/phases.json`, `cluster/analysis.txt` |
| Relations | | a128 / a64 | peak_acc 2.003; peak_dir 1.927; RssAnon 2.059 | `cluster/analysis.txt`, `selfcheck-output.txt` |
| Relations | | a64 against a64b | peak_acc 63.2 / 63.3 MiB; rho 1.1839 / 1.1836 | same |
| All arms | | client | 5000 rows each, 0 errors; ERROR lines in `system.log`: 0; gauge after the final flush 0, direct back within 0.3 to 5.7 MB of the baseline | `cluster/<arm>/bigA.out`, `bigB.out`, `phases.json` |

### 4.2 Conclusion and logic

1. **Validity** — valid. The limit was reached in the unit tier (stall at 575 / 1151 / 512 allocations, worker parked in `SubAllocator.allocate`) **[observed: `unit/stock-limit_offheap_*.out`]** and in every `offheap_buffers` cluster arm (peak_acc 0.986-0.990 L, `BlockedOnAllocation` grew, 4-9 MEMTABLE_LIMIT flushes) **[observed: `cluster/analysis.txt`, `cluster/<arm>/flush-lines.txt`]**. Settings read-back equalled the yaml in every arm, JVM flags `-Xmx2G`, `AlwaysPreTouch`, NMT summary and `MaxDirectMemorySize=2g` present **[observed: `cluster/<arm>/summary.txt`]**; the first-trigger checks passed; no `ERROR` in any `system.log`; phase A ran 60 s at 50.0 rows/s in all arms **[observed: `bigA.out`]**. The REGION_SIZE builds differ from stock by line 51 only **[observed: `unit/v512.diff`, `unit/v2048.diff`]**.
2. **Readings** — nothing contradicts another. Misses of frozen sub-predictions, reported without change: (a) `f64` rho is 1.210 against the band [1.11, 1.20] **[observed: `cluster/analysis.txt`]**; (b) retained heap for `heap_buffers` is 2.0 times real (B2f heap bullet) **[observed: `unit/stock-waste_heap_116509_400.out`]**; (c) the `h64` `[B` relation (q = 2.29) came out outside [0.9, 1.3] **[observed: `cluster/analysis.txt`]**. The cluster direct readings sit a nearly constant 2.6-4.0 MiB above the model (median of `dir - model x acc` 3.59 / 2.56 / 3.46 / 3.22 / 4.02 MiB for a64 / a128 / a64b / e64 / f64) **[observed: computed from `jmx.csv`, the node-side raw file]**; this offset is why rho of every arm is 0.02-0.07 above its replay value (1.125, 1.125, 1.000, 1.143) and why f64 left its band **[inferred: other direct buffers (flush writers, BufferPool) and the partly filled live region add a few MiB; not separated]**.
3. **Matched row** — unit tier, B2g row 1: "owns() = N x S for every S and REGION_SIZE, regionCount and real match the B2f table, and real/owns varies with S and REGION_SIZE only through the division". **[observed: all nine table rows, `unit/*waste*`]**; together with the limit rows (stall at 575 / 1151 allocations while real is 72 / 144 MiB, ratio 1.125; L moves the stall, REGION_SIZE does not: 575 on all three builds) **[observed: `unit/*limit*`]**. Cluster tier, B3g row 1: `peak_acc` doubles with the limit (2.003, within [1.8, 2.2]), each in [0.90 L, 1.05 L] (0.986-0.990), blocked count grew and 4-9 MEMTABLE_LIMIT flushes in each arm, rho 1.184 / 1.146 / 1.184 at S = 116509 (band [1.10, 1.20]) and 1.054 at S = 131068 (band [0.97, 1.07]) **[observed: `cluster/analysis.txt`]**; `peak_dir` of `a64` is 76.2 MiB against L = 64 MiB (the overshoot-path row) **[observed]**.
4. **Excluded rows** — "real at stall at or below L under every S": excluded, real 1.125 L at S = 116509 (unit) and peak_dir 1.19 L (cluster) **[observed]**. "Real grows with REGION_SIZE (ratio at or above 3.0)": excluded, 0.960 and 1.000 **[observed]**. "owns() changes with REGION_SIZE": excluded, identical in the three builds **[observed]**. "Worker never stalls / control does not move": excluded, stall moved 575 to 1151 and peak_acc doubled **[observed]**. "Ratio 1.000 for every S": excluded, 1.125 / 1.049 / 1.28 **[observed]**. "regionCount or real differs from the table / direct differs from real by over 1 MiB": excluded, exact match, direct within 3 bytes **[observed]**. "Eight-thread direct differs": excluded **[observed]**. Cluster: "usage follows the region size (flat 1 MiB steps)": excluded, `peak_dir` scales 1.93 with the limit and differs with S **[observed]**; "direct at or below the limit for every arm": excluded **[observed]**; "doubling leaves peak_acc unchanged / below 0.9 L / no blocked growth": excluded **[observed]**; "rho at S = 131068 is 1.10 or more": excluded (1.054) **[observed]**.
5. **Observed vs. inferred** — the constant `REGION_SIZE` is varied only in the unit tier; the cluster tier runs at 1 MiB, so "the constant does not cap in the node" is **[inferred: the same allocator code, same accounting; the cluster arms show the limit, not the constant, sets the accounted peak]**. Real bytes in the cluster are the BufferPool direct gauge minus a baseline, with the regions themselves not countable there **[inferred: rho against the replay, with the 3-4 MiB offset unexplained in detail]**. `AllMemtablesOffHeapDataSize` is the live memtable only **[observed: source `TableMetrics.java:876-883`; shakedown behaviour, not used as a reading]**.
6. **Deviations and gaps** — (i) probe uses `SlabPool` directly instead of the factory (same objects); (ii) `REGION_SIZE` variants by one-file class directories, not rebuilds; (iii) one repeat (`a64b`) instead of two runs per setting; (iv) the workload is split in two phases (amendment 6b); (v) the three missed sub-predictions of part 2; (vi) the RssAnon relation held in every arm but RssAnon is not a clean copy of direct (the unit tier shows it can be 8 percent lower); (vii) the heap tier is secondary and its relation missed; (viii) the `isBlocking` bypass (A3) was not run: out of scope for B2/B3.
7. **Core question** — Usage did not follow the 1 MiB region capacity at line 201. In the unit tier the accounted bytes were N x S in every build and the real bytes were set by how S divides the region (1.125, 1.000, 1.049, 1.28; 0.960 to 1.000 across a 4x change of the constant), and the pool limit, not the constant, set the stall (575 to 1151 allocations when L doubled; 575 on all three builds) with real memory at 1.125 L. In the cluster the accounted peak sat at 0.99 L and doubled with the limit while the direct memory sat 5 to 19 percent above it depending on S (rho 1.05 to 1.21). So the check at line 201 does not cap memory use: the cap is on requested bytes, and real use exceeds the limit by the tail waste.

**Conclusion (one line):** unit B2g row 1 and limit rows — confirmed (does not cap); cluster B3g row 1 — confirmed (does not cap); three secondary sub-predictions missed (f64 band, heap retained 2.0x, h64 `[B` relation).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py run1` re-parses the raw `.out`, `jmx.csv`, `rss.csv`, `system.log`, `bigA/B.out` and `phases.json`, with the replay rule and the B2f/B3f literals typed again (`results/.../run1/selfcheck-output.txt`: 2 BAD lines, the two missed sub-predictions: heap retained, f64 band). I also re-read `unit/v512.diff`, `v2048.diff`, `cluster/h64/phases.json` and computed the direct-minus-model offsets from `jmx.csv` by hand.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `summary.txt` of every arm (read-back yes, first trigger yes, nothing left running yes); `bigA.out` rate 50.0; `system.log` ERROR count 0 in all six. |
| 2. Readings | yes | The three misses are real readings, not instrument faults: the heap miss reproduces with G1 region size 1m (104.3 MB) and goes away with 8m (51.4 MB), so it is G1 humongous allocation (a 1 MiB array needs two 1 MiB regions); the h64 relation divides by a gauge mean that straddles a flush (60.7 MiB before, 1.4 MiB after), against the gauge before the histogram it is 1.17; f64 is 0.01 above its band with an offset (4.0 MiB) like the other arms. |
| 3. Matched row | yes | Selfcheck compares every unit row with the typed table (all ok) and re-derives rho, peak_acc, blocked growth and flush counts from raw files (all ok except f64's band). |
| 4. Excluded rows | yes | Ratios 0.960 / 1.000 (REGION_SIZE), owns identical across builds, peak_acc ratio 2.003, rho(e64) 1.054 < 1.10 recomputed from `jmx.csv`. |
| 5. Observed vs. inferred | yes | The inferred statements (cluster constant not varied; direct offset of 3-4 MiB) are the ones the conclusion states as inferred; the verdict does not rest on the offset: rho bands of the confirming row hold without it. |
| 6. Deviations and gaps | yes | Listed in 4.2 part 6; attempt 1 differs from run 1 only in the three harness defects of section 3 (unit rows identical for the B2f table and limits). |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | Hypothesis B1 to B2/B3 steps to B2g/B3g row 1; the positive control (L 64 to 128) moved the stall point and the accounted peak, the constant did not. |

### 5.2 Run 2?

**No** — decided 2026-10-26. Both tiers matched their confirming row with exact unit numbers (equal to the replay to the byte) and a repeat in the cluster (`a64`/`a64b` agree on peak_acc within 0.1 MiB and on rho within 0.0003); the result is neither a refutation nor a bypass. The three missed sub-predictions are secondary and explained by raw files; a run 2 would not change the verdict.

## 6. Run 2 — fresh AI session (optional)

"Not done" if §5.2 says no, and §7 is left out.

**Scope:** the tiers and capacity values actually run. **Command log:**
`slab-region-size-region-allocate-capacity--autonomous/run2/<file>`.

### 6.1 Readings

**Unit tier**

| Test or assertion | Result | Evidence (file) |
|---|---|---|

**Cluster tier**

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|

### 6.2 Matched row

The §9a row these readings match, in one line.

## 7. Comparison — only if run 2 was done

| Observable | Run 1 | Run 2 | Criterion (§1) | Agree? |
|---|---|---|---|---|

**Same §9a row?** yes / no. If no, or if a reading disagrees: the cause, and
how it was resolved (see "Compare and decide" in the README).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its
date and reason.

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap): the stage-4 effect agrees with the estimate.

**Claim tested:** (B1) the 1 MiB region capacity checked at `SlabAllocator.java:201` does not bound the memory a node uses for memtable slabs; real heap or direct bytes held by slab regions track the number of regions created, which is driven by the `memtable_*_space` accounting of requested bytes, and exceed the accounted bytes by uncharged tail waste that depends on value size, not on any limit.
"Confirmed" below always means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 plus the limit rows (accounting ignores REGION_SIZE; stall at 575 / 1151 allocations with real 1.125 L; L moves the stall, REGION_SIZE does not). One secondary sub-prediction (heap retained within 3 MiB of real) missed: 2.0 times real under G1 with 1 MiB regions | does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | **Confirmed** — B3g row 1 (peak_acc 0.99 L, doubling with the limit; rho 1.15 to 1.18 at S = 116509, 1.05 at the exact fit; blocked growth and 4-9 MEMTABLE_LIMIT flushes per arm). Two secondary sub-predictions missed (f64 rho 1.210 against a band to 1.20; h64 `[B` relation) | does not cap | run 1 + self-check | 2026-10-26 |

**Positive control** (a negative-estimate file only): the pool limit. Unit: L 64 to 128 MiB moved the stall from the 576th to the 1152nd allocation (owns 66,992,675 to 134,101,859) with the same code and all three REGION_SIZE builds stalling at 575. Cluster: L 64 to 128 MiB moved peak_acc 63.2 to 126.7 MiB (2.003), peak_dir 76.2 to 146.9 MiB (1.93) and the RssAnon peak 82.8 to 170.5 MiB (2.06). The region constant, varied 4x in the unit tier, moved the real bytes by 4 percent at most (0.960) and the accounted bytes not at all.

**Feedback filed:** the case file's section D "Stage-4 feedback" field updated (uncommitted; the orchestrator commits), with the two same-day amendments recorded there; no further section amended. Findings for stage 3 / upstream: (1) real memory above the `memtable_offheap_space` limit by up to 12.5 percent (S = 116509: 72 regions for 66.99 MB accounted at L = 64 MiB); (2) `heap_buffers` slabs are G1 humongous objects when the G1 region size is 1 MiB (heap under 2 GiB), so the heap holds 2 MiB per slab; (3) the metric `AllMemtablesOffHeapDataSize` ("All memtables") covers only the current memtable; (4) the `SlabAllocator` class comment does not say that region tails are uncharged.

**Leftovers on the node:** none running (`ps` shows no `CassandraDaemon` and no java of this harness); `/dev/shm/s4-b7-sr7` removed by each lifetime; files kept: `~/s4-b7-sr7` (tree), `~/s4-b7-sr7-logs`, `~/s4-b7-sr7-chain.sh`.
