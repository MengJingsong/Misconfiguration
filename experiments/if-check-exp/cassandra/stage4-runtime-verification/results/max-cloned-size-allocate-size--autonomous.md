# max-cloned-size-allocate-size--autonomous — stage-4 results  <!-- file: results/max-cloned-size-allocate-size--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`max-cloned-size-allocate-size--autonomous`](../../stage3-ai-deep-read/cases/max-cloned-size-allocate-size--autonomous.md)
>
> **Status:** run 1 done, self-checked, verdict filed (2026-10-26)
>
> **Outcome class:** true negative (estimate negative; effect of `MAX_CLONED_SIZE` on the constraint: does not cap)
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
| **Case-file version** | The case file at repository HEAD `e776524` (untracked there) plus the audit amendments of 2026-10-26 (the orchestrator commits). sha256 of the whole file after the amendments (frozen before any reading): `b9b52d27f4c4017795c03973f9635077232caecc7321c2147f15f1ff7c99fa2e`. sha256 of the prediction and conclusions text of B2 (`awk` from the line starting `**B2f.` to the line before `**B2h.`): `a48b28f2500ca043997029c895dbf5fd36c903ffef50c644cd202686d9b427f0`; of B3 (from `**B3f.` to the line before `**B3h.`): `ec7d937592a4dbb4d98357c8f78b277ed63ec848ddf9f27d1c8ebbe5f88f40b3`. The case file changes after run 1 only in section D (feedback); its sha256 then is `c6f1126fa507b3e2abdcc9e71caf80d575b10b8ea8b87189f9e9766d3bc83186` (B2/B3 prediction hashes unchanged, verified after the run). |
| **Harness** | `harness/max-cloned-size-allocate-size--autonomous/` (`SlabCapProbe.java`, `unit-run.sh`, `make-node-yaml.sh`, `client.py`, `Jmx.java`, `cluster-run.py`, `selfcheck.py`, `README.md`; written after this audit and before run 1; not committed by this agent). Instrument checks before run 1: the probe at L = 4 MiB against hand-computed known answers (S = 116736: 17 allocations in 3 regions, plateau 35 in 5 regions = 5 MiB; S = 131073: 31 dedicated buffers, 4,063,263 B), both ok (`run1/instrument-check-summary.txt`); `blocking` and `control` modes run once at L = 4 MiB (all checks ok); the cluster chain on `s128` with 1,500 rows as a shakedown (not a reading, discarded). |
| **Tiers and values** | Unit (B2): L = 32 / 64 / 128 MiB x S = 65536, 102400, 116736, 131072, 131073, 163840, 262144 (fill), blocking-group arm (S = 102400, 262144 at L = 64), heap_buffers control (S = 102400, 131072, 131073, 262144 at L = 64). Cluster (B3): L = 128 / 256 / 512 MiB x V = 102400 (slab path) and 204800 (dedicated path), heap_buffers control arms `cs`/`cd`, heap-limit positive control `hp`. |
| **Audit bottom line** | **Ready after amendments** - 2026-10-26 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: bytes charged to `SubPool.allocated` (`MemtablePool.java:151-158`) by `SlabAllocator.allocate` line 89; real resource = direct `ByteBuffer`s (`allocateDirect`, lines 97, 139) in offheap_buffers mode. The constant itself (128 KiB) is not a cap; the claim is that it is a routing threshold. |
| A. Core question | knob varied, >= 3 values incl. default — or another approach, with the reason | Met after amendment | `MAX_CLONED_SIZE` is a `private static final` (A1): the design uses two arms that differ in one condition (V = 100 KiB slab path vs 200 KiB dedicated path), and the real cap `memtable_offheap_space` as the varied knob. B2b gave L = 64 / 128 only; amended to 32 / 64 / 128 (unit) and B3b to 128 / 256 / 512 (512 = default at -Xmx2g, `DatabaseDescriptor.java:583-587`). |
| A. Core question | real resource measured, not only the counter (gap named) | Met after amendment | B2d/B3d: `BufferPool` "direct" + RSS. Amended: `RssAnon` (not `VmRSS`/`ps rss`), net of a `heap_buffers` control for the non-memtable growth the sibling case measured at ~150 MiB; the global gauge `MemtableOffHeapDataSize` is mis-registered (`TableMetrics.java:507`), so `AllMemtablesOffHeapDataSize` is read. |
| A. Core question | usage driven to the limit and past it | Met after amendment | Unit: allocate to `used()+S > L`, then a parked extra allocate is the past-limit probe. Cluster: 1.91 GiB payload = 3.7 L at L = 512; the default cleanup threshold would flush at 0.5 L, so `memtable_cleanup_threshold: 0.99` (already in B3a) and `commitlog_total_space` 4096MiB (1024MiB would flush first at L = 512) are required. |
| B. Logic | each step says what it establishes | Met | B2e, B3e numbered steps, each with its observable. |
| B. Logic | prediction stated in numbers or a clear relation | Met after amendment | B2f gave an upper bound 1.123 L for the direct delta at the plateau that is wrong from the source alone (S = 116736, L = 64 MiB: 72 regions = 1.125 L); replaced by the exact region formula. B3f 'peak' made sampling-aware and the net-of-control bands stated. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g / B3g cover plateau equal across the threshold, plateau differs, no plateau move with L (control failed), waste bounds, unmodelled uncharged memory, limit not reached, blocking-group overshoot, wrong allocation type. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Parked extra allocate (WAITING) and `BlockedOnAllocation` growth; plateau moves with L (the positive control: the pool limit binds on the same resource with the same instruments). |
| B. Logic | alternative explanations and their controls | Met after amendment | B2h/B3h: stubbed cleaner, blocking group, heap_buffers control, DEBUG log line. Added: control arms `cs`/`cd` for non-memtable direct growth (rule fixed before any reading), and the mode control in the unit tier; the DEBUG log line replaced by settings read-back plus gauges. |
| C. Specific | a human can follow it from the intro and B2f/B3f | Met | A1-A3, B1. |
| C. Specific | an AI can run B2/B3 without re-deriving the code path | Partly, fixed | B2c phase 2 had the worker allocate on the allocator being discarded; the blocking group lacked `markBlocking()`; B3c table `ks.t` and row counts approximate. Amended. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Met after amendment | Sampling 200 ms (gauges, `RssAnon`), 5 s (NMT); rows exactly 20,000 x 102,400 B and 10,000 x 204,800 B; stop = client done + 10 s + `nodetool flush`. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Sibling harness (`memtable-offheap-space-allocate-size--autonomous`) as pattern; tree `~/s4-b7-mc` by `copy-source.sh`, `ant jar` 1 min 13 s; JDK 11.0.32.1, Ant 1.10.12 on pc07. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met after amendment | 1.91 GiB per arm vs L <= 512 MiB (3.7 L); a 1500-row shakedown at L = 128 reached blocking within 1.1 s, so the full run takes ~15-30 s per arm; tmpfs 123 GiB free; JVM 2 GiB heap + 576 MiB direct at L = 512. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | See section D of the case file: all hold, minor line drift (`MemtablePool` `~157-166` is `151-158`; `MemtableAllocator` `169-199` is `169-197`). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | B2f: direct delta at the plateau = exact region formula, not "<= 1.123 L" | Applied 2026-10-26 (B2f) | Wrong from the source alone. |
| 2 | B2a: throttled cleaner stub (50 ms) | Applied 2026-10-26 (B2a) | Sibling defect: a spinning cleaner thread pollutes `RssAnon`. |
| 3 | B2b/B2c/B2e: L = 32 / 64 / 128; `markBlocking()`; extra allocate on a second allocator; phases in one JVM; mode control | Applied 2026-10-26 | Unrunnable or incomplete as written. |
| 4 | B2d: `BufferPool` direct + `RssAnon` (+ NMT as a reading); band | Applied 2026-10-26 | `RssAnon` not `VmRSS`; sibling noise floor of 4 MiB. |
| 5 | B3a: `commitlog_total_space` 4096MiB, tmpfs, caches off, timeouts, protocol 4, `AlwaysPreTouch`, NMT | Applied 2026-10-26 | A 1024MiB commit log flushes before L = 512 MiB; the rest from the repo lessons. |
| 6 | B3b/B3c: L = 128 / 256 / 512; control arms `cs`/`cd`; exact row counts | Applied 2026-10-26 | Three knob values incl. the default; non-memtable direct growth would otherwise swamp the reading (sibling: ~150 MiB). |
| 7 | B3d/B3f: gauge `AllMemtablesOffHeapDataSize`; sampling-aware reached rule; net bands and ratios | Applied 2026-10-26 | The global `MemtableOffHeapDataSize` is registered under the on-heap name (`TableMetrics.java:507`); 200 ms sampling misses sawtooth tops. |
| 8 | B3h: DEBUG allocation-type log line | Left for stage 3 (replaced in practice by the settings read-back plus gauges; no claim change) | The shipped logback has no DEBUG logger for the memtable package. |
| 9 | B3d wording "poll with nodetool/jmxterm" | Left for stage 3 (a JMX client JVM, `Jmx.java`, is used) | One JVM per `nodetool` call is too slow for 200 ms sampling. |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-26 (unit 10:27-10:30 EDT; cluster 10:30-10:52 EDT) | not done |
| Node (CloudLab name and type) | `pc07` = `node0.jason92-320876...`, 40 cores, 251 GiB; port slot 4 (127.0.4.1, JMX 7140) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy | `~/s4-b7-mc` from `cassandra/cassandra-5.0.9/` (repository commit `e776524`), `copy-source.sh`, `ant jar` 1 min 13 s; node and probe ran from this tree | |
| Case-file commit / harness commit | `e776524` + uncommitted amendments (sha256 in §1) / harness uncommitted (orchestrator commits) | |
| Storage for node data | tmpfs `/dev/shm/s4-b7-mc` (wiped per lifetime, removed afterwards); the unit probe has no storage | |
| Full logs (path, outside the repo) | `~/s4-b7-mc-logs/run1/{unit,cluster/<arm>}/` on pc07 (`jmx.csv`, `rss.csv`, `nmt.csv`, `system.log`, `big.out`, `session.log`) | |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | audit | B2f / B1 / B2g | The pre-registered waste bound "<= ~12.3 % / 1.123 x accounted" (B1, B2g rows 5-6; B2f before amendment) ignores the unfilled remainder of the last region. B2f was corrected by amendment before any reading (exact region formula); **B1 and the B2g rows were not**, and the numeric threshold of B2g row 6 trips on the readings (S = 116736: 12.57-12.67 % at L = 128, 64, 32 whenever the last region is partly filled). | None possible after the freeze. The readings are matched against the B2f formula (byte-exact in all 21 fill runs); the B2g text is left as filed and the defect is recorded in the case file's section D for stage 3. | 2026-10-26 | none (feedback in section D) |
| 2 | unit | B2g "RssAnon" | The `RssAnon` band `[accounted - 1 MiB, direct delta + 4 MiB]` is missed in 11 of 23 fill and blocking runs, all above the band, by 0.04 to 3.4 MiB. | Recorded as JVM noise (see 4.1); no rule rests on it, the exact `BufferPool` reading does. | 2026-10-26 | none |

Shakedown (not a reading, discarded): `s128` with 1,500 rows on 2026-10-26 10:24 (`~/s4-b7-mc-logs/shake/`) showed the chain works; no prediction or rule was changed after it. Probe `blocking` and `control` modes were run once at L = 4 MiB (all checks ok) before the freeze.

## 4. Run 1

**Scope:** unit tier: 21 `fill` runs (L = 32 / 64 / 128 MiB x S = 65536, 102400, 116736, 131072, 131073, 163840, 262144), 2 `blocking` (S = 102400, 262144 at L = 64), 4 `control` (heap_buffers, S = 102400, 131072, 131073, 262144 at L = 64); cluster tier: arms s128 s256 s512 (V = 102400), d128 d256 d512 (V = 204800), cs, cd, hp. **Command log:** `max-cloned-size-allocate-size--autonomous/run1/` (`unit/`, `cluster/<arm>/`, `analysis.txt`, `selfcheck.out`, `instrument-check-summary.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit/*.out`; `summary.txt`: 407 checks, 13 MISMATCH: 11 `RssAnon` band, 2 `control-no-direct-buffers`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| `used()` after the fill = N x S exactly, N = floor(L/S), `used() <= L < used() + S`, `owns()` = `used()` | holds in all 21 fill runs; `used()/L` is 0.9961 to 1.0000 on both sides of the threshold (L = 64: S = 131072 -> 67,108,864; S = 131073 -> 66,978,303 = 511 x 131,073) | `unit/fill-L*-S*.out` (`reading n`, `used`) |
| Plateau follows L | for every S, `used` at L = 32 / 64 / 128 is in the ratio 1 : 2.000-2.005 : 4.000-4.015 (one S of rounding) | `run1/selfcheck.out` |
| Extra allocate on a second allocator after the plateau | `WAITING` after 2 s in all 21 runs; `used()` and the direct delta unchanged; after `a.setDiscarding(); a.setDiscarded()` the thread ends, `used() == S`, direct delta = one region (1 MiB) or one dedicated buffer (S) | `extra_state_2s`, `extra_state_after_discard`, `direct_delta_after_discard` |
| `BufferPool` direct delta at the plateau | equals the region formula byte for byte in all 21 runs: S <= 131072 -> ceil(n / floor(1 MiB / S)) x 1 MiB (count = regions); S > 131072 -> n x S, count n, equal to `used()`. Excess over `used()`: S = 65536, 131072, 262144, 131073, 163840: 0; S = 102400: 2.4-3.3 %; S = 116736: 12.57-12.67 % | `direct_delta`, `count_delta`, `selfcheck.out` (`direct_formula`, `waste_pct`) |
| Phase 1 (below the limit), 21 runs | `used()` = N1 x S, direct delta = model, `onHeap.used()` = 0 | `p1_*` readings |
| Blocking op group | writer finishes K = 164 (S = 102400) / 64 (S = 262144) allocations without parking; `used()` = 83,865,600 / 83,886,080 > 67 MB plateau + K x S (= L + 16 MiB); a non-blocking extra allocate still `WAITING` | `unit/blocking-L64-S*.out` |
| `heap_buffers` control (`SlabPool(L, 0)`) | `offHeap.used()` = 0, `onHeap.used()` = floor(L/S) x S for all four S (also 131073 and 262144, the `ByteBuffer.allocate` path), extra allocate `WAITING`; direct delta 0 (-3 B / -3 buffers in two runs: JVM-internal buffers freed) | `unit/control-*.out` |
| `RssAnon` delta in `[used - 1 MiB, direct delta + 4 MiB]` | 12 of 23 inside; 11 above by 0.04-3.4 MiB (e.g. L = 128, S = 131073: 2.65 MiB; L = 32, S = 102400: 3.39 MiB); none below. NMT "Other" rose by the direct delta (L = 128, S = 102400: 4116 KB -> 138,260 KB = +131 MiB = 1.024 x L) | `unit/summary.txt`, `nmt_before/nmt_after` |

**Cluster tier** (tracked = `Table AllMemtablesOffHeapDataSize` (on-heap gauge for heap_buffers arms), 200 ms; `direct` = `BufferPool` direct `MemoryUsed` peak minus the idle baseline; `analysis.txt`, `selfcheck.out`, `cluster/<arm>/`)

| Capacity value | Run | Observable | Reading | Evidence (file) |
|---|---|---|---|---|
| L = 128 MiB | s128 (100 KiB) | tracked peak / blocked / flushes / direct delta / RssAnon delta | 126.5 MiB (0.988 L) / 618 / 16 / 144.1 MiB / 174.8 MiB | `s128/{jmx.csv,rss.csv,system-log-excerpt.txt}` |
| L = 256 | s256 | same | 251.7 MiB (0.983 L) / 203 / 8 / 270.9 / 343.4 MiB | `s256/` |
| L = 512 | s512 | same | 488.5 MiB (0.954 L) / 52 / 4 / 539.0 / 600.1 MiB | `s512/` |
| L = 128 | d128 (200 KiB) | same | 125.0 MiB (0.977 L) / 662 / 16 / 148.8 / 160.1 MiB | `d128/` |
| L = 256 | d256 | same | 253.1 MiB (0.989 L) / 225 / 8 / 272.1 / 303.3 MiB | `d256/` |
| L = 512 | d512 | same | 484.4 MiB (0.946 L) / 80 / 4 / 525.6 / 559.4 MiB | `d512/` |
| control | cs (heap_buffers, 100 KiB) | tracked off-heap / on-heap peak / blocked / direct delta / RssAnon delta | 0.00 MiB / 480.7 MiB (heap limit 512) / 48 / 6.2 MiB / 45.4 MiB | `cs/` |
| control | cd (heap_buffers, 200 KiB) | same | 0.00 / 500.5 MiB / 48 / 10.5 MiB / 53.6 MiB | `cd/` |
| positive control | hp (heap_buffers, `memtable_heap_space` 128MiB) | on-heap peak / blocked / flushes | 126.4 MiB (0.99 x 128) / 241 / 16 | `hp/` |

Net of the control of the same V (arm minus cs / cd; rule fixed before any reading): direct 137.9 / 264.7 / 532.7 MiB (s: 1.077 / 1.034 / 1.041 L) and 138.3 / 261.7 / 515.1 MiB (d: 1.080 / 1.022 / 1.006 L); RssAnon 129.4 / 298.0 / 554.7 MiB (s) and 106.5 / 249.7 / 505.8 MiB (d). Tracked peak ratios 256/128 and 512/128: 1.990 and 3.863 (s), 2.025 and 3.875 (d). Peaks of V = 100 KiB and 200 KiB differ by 1.2 % / 0.6 % / 0.8 % at L = 128 / 256 / 512. All lifetimes: client `ok == rows`, `err == 0`; settings read-back equal to the yaml; JVM flags confirmed; no `ERROR` line in any `system.log`; tracked gauge below 1 MiB after the final flush. Of the pre-registered relations, all 9 arms' tracked, bound, reached, blocked, flush and net-direct relations are `yes`; **the net `RssAnon` relations are partly `NO`**: d128 is 106.5 MiB against a floor of 0.9 L = 115.2 MiB, and the 256/128 ratio is 2.30 (s) and 2.34 (d) against an upper bound of 2.3 (512/128 for d: 4.75, inside 4.8).

### 4.2 Conclusion and logic

1. **Validity** — valid. The limit was reached in all six offheap_buffers arms: [observed: `analysis.txt`] peaks 0.946-0.989 L, `BlockedOnAllocation` grew (618 / 203 / 52; 662 / 225 / 80), 16 / 8 / 4 flushes each. Held-fixed settings confirmed [observed: `<arm>/summary.txt` read-back and JVM-flag lines; client `ok == rows`]. The allocation type is confirmed by the read-back and by the gauges: off-heap gauge 0.00 MiB in `cs`/`cd`/`hp`, on-heap gauge ~0 in the offheap_buffers arms [observed]. Unit: every fill reached `used() + S > L` [observed: `unit/*.out`]. First-trigger checks passed in both tiers.
2. **Readings** — (a) The 200 ms sampling can miss the instantaneous top of the sawtooth (L = 512: 0.946-0.954 L although writers blocked 52 / 80 times) [inferred: `tryAllocate` refuses only above the limit, `MemtablePool.java:151-158`]. (b) The net `RssAnon` relation was not met in two places (4.1); the exact `BufferPool` reading was met everywhere. `RssAnon` is a coarse reading here: the control arms' own `RssAnon` delta varies by 45-70 MiB between `cs`, `cd`, `hp`, and the subtraction inherits that noise [inferred]. (c) The net direct delta (arm minus control) over the tracked peak is 1.03-1.11 for both V, including V = 200 KiB where no slab waste exists; the excess is the second memtable held while one is flushing and the non-aligned instants of the two samples [inferred, not separated]. (d) Unit `RssAnon` band: 11 misses, all above, <= 3.4 MiB [observed]; the `BufferPool` delta is exact. (e) The B2g text on the waste bound is wrong at S = 116736 (Runbook defect 1) [observed: 12.57-12.67 % against 12.3 %, equal to the formula].
3. **Matched row** — Unit B2g: "`used() == N*S` and plateau `== floor(L/S)*S` on both sides of 131072/131073 → Claim confirmed" [observed: 21 fill runs, `used()` = N x S, `WAITING`, plateau 0.996-1.000 L at S = 131072 and 131073 alike]; "Plateau halves when L halves, at every S → Positive control: the pool limit binds and is the real cap" [observed: ratios 2.000-2.005 and 4.000-4.015]; "Direct delta > accounted for S in slab range ... matching the region formula → Expected slab waste; not a cap" [observed: byte-exact formula in all 21 runs; the numeric bound 12.3 % is exceeded at S = 116736, see defect 1]; "Blocking group allocates past L → Documented overshoot path; not a refutation" [observed: `blocking-*`]. Mode control: heap_buffers charges `onHeap`, plateaus at L, never touches `offHeap` [observed]. Cluster B3g: "Peak memtable off-heap tracks L (doubles from 128 to 256 MiB), roughly equal for V=100 and 200 KiB → Claim confirmed; L doubling is the positive control" [observed: 126.5 / 251.7 / 488.5 and 125.0 / 253.1 / 484.4 MiB, ratios 1.99 / 2.03 and 3.86 / 3.88; equal within 1.2 %]; "Peak direct memory minus baseline tracks accounted peak within 1.0 to 1.13x" [observed for the direct pool net of the control: 1.006-1.080 L, and 1.03-1.11 x the tracked peak; the RssAnon net failed two pre-registered relations, 4.1].
4. **Excluded rows** — Unit: "Plateau differs beyond one S between S = 131072 and 131073, or 100 KiB and 200 KiB at equal L" no: gaps <= 0.004 L = one S [observed]. "Direct delta > 1.123x accounted -> unmodelled uncharged memory": the number is exceeded at S = 116736 but the direct delta equals the formula exactly, so no unmodelled memory [observed + the formula is the B2f amendment]. "Direct delta > accounted for S > 131072": no, equal [observed]. "Worker never reaches WAITING": no [observed]. "Plateau does not move when L changes": no [observed]. Cluster: "Peaks differ markedly between V = 100 and 200 KiB (> 25 %)": no, <= 1.2 % [observed]. "Direct memory grows beyond ~1.15 L net / without bound": no, max 1.080 L net [observed]. "Peaks do not change with L": no [observed]. "Memtable never approaches L": no, blocked and 4-16 flushes [observed]. "Heap grows with L in offheap_buffers mode": no, on-heap gauge 0.4-2.5 MiB [observed]. "Heap-limit positive control did not plateau": no, 126.4 MiB with 241 blocks [observed].
5. **Observed vs. inferred** — inferred: (i) 200 ms sampling understates instantaneous peaks (2a); (ii) the net-of-control subtraction as a measure of memtable-attributable memory; it was fixed before any reading but rests on the control's non-memtable growth equalling the arm's (2b); (iii) the 1.03-1.11 direct/tracked excess is a second live memtable (2c); (iv) `RssAnon` unit misses are JVM noise (4.1 unit); (v) the bytes of `Region`/`allocateDirect` are the only uncharged memory (supported by the exact formula at the unit tier, not separated in the cluster).
6. **Deviations and gaps** — Pre-registered net `RssAnon` relations missed in 2 places (d128 below the floor; ratio 256/128 slightly above 2.30). The B2g/B1 waste-bound text is wrong (defect 1). `memtable_cleanup_threshold` 0.99 and tmpfs are amendments, not defaults; the default threshold (0.5) was not run, so how early flushes start at the default was not read. The DEBUG log line for the allocation type was replaced by settings read-back plus gauges. `MAX_CLONED_SIZE` itself cannot be varied (hard-coded); the two-arm design (slab vs dedicated path) stands in for it, as the case file says. A single memtable-pool table; the Netty/BufferPool share of direct memory (55-67 MB at idle) is a baseline, not subtracted from the control. Run 2 not done.
7. **Core question** — The 128 KiB constant does not cap usage and usage does not follow it: the pool is charged before the branch (line 89), so the accounted plateau is identical either side of the threshold (unit: 0.996-1.000 L at S = 131072 and 131073; cluster: 126.5 vs 125.0, 251.7 vs 253.1, 488.5 vs 484.4 MiB for 100 vs 200 KiB values) and writers block at that plateau (parked allocator, `BlockedOnAllocation` growth). What the constant changes is the physical layout: slab tail waste up to 12.6 % of real direct memory over accounted at S = 116736 (2.4 % at 100 KiB), none above the threshold; the waste is a bounded layout effect (exact formula), not a cap and not a bypass. The cap is `memtable_offheap_space`: the ceiling moves 1 : 2 : 4 with it (positive control) and `heap_buffers` ignores it. Steps: unit plateau and parking (3) -> cluster blocking and ordering (3) -> real resource (2b, 2c, 6).

**Conclusion (one line):** Unit B2g row "`used()` and plateau equal either side of 131072/131073, move 1 : 2 : 4 with L; waste matches the region formula" — confirmed; cluster B3g row "peak tracks L, equal for 100 and 200 KiB, net direct within 1.0-1.13 x" — confirmed (net `RssAnon` relations partly missed). Effect of `MAX_CLONED_SIZE`: does not cap.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-parsed from the raw files by `harness/.../selfcheck.py` (it does not import `cluster-run.py`, does not read the probe's `check` lines and recomputes the region formula); output `run1/selfcheck.out`. The unit `.out` files and every arm's `jmx.csv`, `rss.csv`, `phases.json`, `system.log` and `big.out` were re-opened.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.out`: 21 fill runs, 0 failing plateau / exact / direct-formula / parked / released / oversize / on-heap; every cluster arm re-computed from `jmx.csv` / `rss.csv` / `system.log`: tracked peaks, blocked 0 -> N, flush counts 16 / 8 / 4, 0 ERROR lines, client `ok == rows`, gauges ~0 after the final flush; the `analyze` numbers equal the self-check numbers. |
| 2. Readings | yes | Same numbers in `analysis.txt` and `selfcheck.out`. The two `RssAnon` misses and the unit band misses are as listed. The `control-no-direct-buffers` -3 B is checked: it is a drop of three JVM-internal direct buffers, with `offHeap_used` 0. |
| 3. Matched row | yes, with caveats | Operand-level rows hold in both tiers. Caveat 1: the B2g waste-bound number is exceeded at S = 116736 though the direct delta equals the formula exactly (defect 1). Caveat 2: the net `RssAnon` relations are partly missed; the verdict rests on the B3g direct-memory row. |
| 4. Excluded rows | yes | Max net direct 1.080 L; max peak gap between V = 100 and 200 KiB 1.2 %; max waste 12.67 %; off-heap gauge 0.00 in the three heap_buffers arms. |
| 5. Observed vs. inferred | yes | Five inferred statements listed; none changes the operand-level verdict. |
| 6. Deviations and gaps | yes | RSS misses and the wrong waste-bound text are stated, not hidden. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1: accounted plateau equal either side of the threshold; disallow branch fired (parked allocator, blocked counts); real memory exceeds accounted by exactly the modelled slab waste. |

### 5.2 Run 2?

**No** (2026-10-26). The operand-level result is exact and repeats in 21 unit runs and 6 offheap_buffers arms; the peaks of the two V arms agree within 1.2 %. The two gaps (net `RssAnon` noise and the wrong waste-bound text) would not be closed by a repeat: the first needs a design with fewer non-memtable consumers, the second is an arithmetic slip in the case file recorded for stage 3.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** B1: memtable usage does NOT follow `MAX_CLONED_SIZE`: for the same payload the pool's `used()` is identical whether allocations are just below or just above 128 KiB, the plateau where writers block is set by `memtable_offheap_space` alone, and real memory differs from accounted only by slab tail waste, never by a threshold-dependent cap. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — `used()` and the blocking plateau equal either side of 131072/131073 and scale 1 : 2 : 4 with L; direct delta = slab waste per the region formula; heap_buffers mode control behaves as predicted. (The B2g/B1 12.3 % waste number is exceeded at S = 116736, the formula is exact: defect 1) | does not cap (`MAX_CLONED_SIZE`; the pool limit caps) | run 1 + self-check | 2026-10-26 |
| Cluster | **Confirmed** — tracked peaks 0.95-0.99 L, equal within 1.2 % for 100 and 200 KiB values, 1 : 2 : 4 across L; net direct memory 1.01-1.08 L; heap_buffers controls and heap-limit positive control as predicted. (Net `RssAnon` relations partly missed) | does not cap (`MAX_CLONED_SIZE`; the pool limit caps) | run 1 + self-check | 2026-10-26 |

**Positive control:** `memtable_offheap_space` moved the plateau 1 : 2 : 4 (unit 32 / 64 / 128 MiB, cluster 128 / 256 / 512 MiB) with the same workload and instruments; the heap-limit arm `hp` (`memtable_heap_space` 128MiB, 126.4 MiB, 241 blocks) showed the workload can show a binding cap.

**Feedback filed:** the case file's section D updated (uncommitted; the orchestrator commits); amendments listed in §1 and in section D. Open points for Jingsong: (1) the B1 / B2g waste bound "12.3 %" is wrong when the last region is partly filled (12.57-12.67 % at S = 116736); the verdict treats the exact formula as the governing prediction, you may overrule to "Not confirmed" for the literal row; (2) the net `RssAnon` relations of B3f missed twice (d128 floor, 256/128 ratio 2.30-2.34), the verdict rests on the exact `BufferPool` reading; (3) the default cleanup threshold 0.5 was not run; (4) upstream candidate: the global `MemtableOffHeapDataSize` gauge is registered under the name `MemtableOnHeapDataSize` (`TableMetrics.java:507`).

**Leftovers on the node (pc07):** nothing running (checked `ps` for `s4-b7-mc`, `ss` for 127.0.4.x); tmpfs `/dev/shm/s4-b7-mc` removed by the harness; kept: tree `~/s4-b7-mc` (471 MB), logs `~/s4-b7-mc-logs/` (`run1/`, `shake/`, `instrument-1/`, `sk/`, `classes/`), `~/s4-b7-mc-chain.sh`, `~/s4-b7-mc-build.log`.
