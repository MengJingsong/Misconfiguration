# memtable-offheap-space-allocate-size--autonomous — stage-4 results  <!-- file: results/memtable-offheap-space-allocate-size--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`memtable-offheap-space-allocate-size--autonomous`](../../stage3-ai-deep-read/cases/memtable-offheap-space-allocate-size--autonomous.md)
>
> **Status:** run 1 done, self-checked, verdict filed (2026-10-26)
>
> **Outcome class:** true positive (estimate positive; effect: caps)
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
| **Case-file version** | The case file at repository HEAD `e776524` plus the uncommitted audit amendments of 2026-10-26 (the orchestrator commits). sha256 of the whole file after the amendments (frozen before any reading): `0fceb2cd22fd3e51a6df74c62ccb07c1b7bcb26954ad0259da4746484650f9ba`. sha256 of the prediction and conclusions text (the `**B2f.` paragraph through the `**B2g.` table, up to `**B2h.`): `0d3b41efb5446a590f402bfa45de76f265d4b047a6358e05efbe2e720fe9c065`; of `**B3f.`-`**B3g.` (up to `**B3h.`): `d6851c7c5fda3486d33d47fd96c2f65c7c6a1d9b1c1082e63ef6a73067e18144` (`awk` from the line starting `**B2f.` to the line before `**B2h.`; the amendment notes of B2f and B3f sit in the paragraph after them and are inside the hashed range; the B2d/B3d notes are outside it; earlier whole-file hashes `5a2037...e1d0` and `074532...6009` and an earlier B2f hash `d8020e...8e9a` were superseded the same day, before any run-1 reading, by rec. 8 (NMT correction) and by two corrections found while checking the unit probe on a 1 MiB pool: the B2f excess bound must include the unfilled remainder of the current region, and the `RssAnon` band needs the +4 MiB JVM warm-up floor and does not apply at L = 1 MiB; those probe-check runs are instrument checks, not readings). The case file changed after run 1 only in section D (feedback); its sha256 then is `1f775436301913840cdc2b441f9b125f5bd48542621b91b239f5dae9f9c8430d`. |
| **Harness** | `harness/memtable-offheap-space-allocate-size--autonomous/` (`OffheapCapProbe.java`, `unit-run.sh`, `make-node-yaml.sh`, `client.py`, `Jmx.java`, `cluster-run.py`, `selfcheck.py`, `README.md`; written after this audit and before run 1; not committed by this agent). Instrument checks before run 1: the probe on a 1 MiB pool against a hand-computed known answer (capacity 2,088,960 in 8 regions, `run1/instrument-check-summary.txt`: 12 checks ok); its first version flagged two of my own wrong bounds (see rec. 9); the cluster chain on `k512` with 1,000,000 rows as a shakedown (§3). |
| **Tiers and values** | Unit (B2): L = 32, 64, 128 MiB x S = 100 B, 1 KiB, 100 KiB, 128 KiB, 128 KiB+1, 1 MiB, blocking-group arm, heap_buffers control, L = 1 MiB control. Cluster (B3): L = 128, 256, 512 MiB with 1 KiB values (3 M rows) and 256 KiB values (3000 rows), heap_buffers control at 256, `memtable_heap_space` binding control (128 MiB). |
| **Audit bottom line** | **Ready after amendments** - 2026-10-26 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: native bytes charged to `SubPool.allocated` (`MemtablePool.java:151-158`), real resource = native memory of memtable regions (`MemoryUtil.allocate`, NMT "Other"). |
| A. Core question | knob varied, >= 3 values incl. default | Partly | B2b/B3b: L = 32/64/128 and 128/256/512 MiB. The default (heap/4 = 512 MiB at -Xmx2G, `DatabaseDescriptor.java:583-584`) equals the largest cluster value (stated by 512); accepted. |
| A. Core question | real resource measured, not only the counter (gap named) | Met after amendment | B2d/B3d named NMT "Other" and RSS; NMT is blind to JNA malloc (rec. 8), so `RssAnon` is the real-resource reading. Gap named in A4/B3d. Amended: RSS read as `RssAnon` with `-XX:+AlwaysPreTouch` (otherwise heap churn dominates). |
| A. Core question | usage driven to the limit and past it | Partly, fixed by amendment | Unit: the fill loop reaches L by construction and a parked extra allocate is the past-limit probe. Cluster: at the default threshold (0.5 L) the peak is 0.5 L plus a rate x flush-time term, not L; amended to `memtable_cleanup_threshold: 0.99` so writers reach L and park (B3a). |
| B. Logic | each step says what it establishes | Met | B2e, B3e (steps numbered with the observable). |
| B. Logic | prediction stated in numbers or a clear relation | Met after amendment | B2f gave a wrong region-tail bound (< 1 MiB) for S = 100 KiB (24 KiB stranded per 1 MiB region, `trySwapRegion` `NativeAllocator.java:156-184`); replaced by the per-region bound. B3f flush point 0.5 L -> 0.99 L. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g cover plateau, oversize path, exceed, accounting mismatch, untracked native growth, charge not reached, bypass, mode control, load too low, flat across L, heap control not binding. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Parked extra allocate (WAITING state) in the unit tier; `BlockedOnAllocation` count and plateau at L in the cluster tier. |
| B. Logic | alternative explanations and their controls | Met | B2h, B3h: heap_buffers mode, 1 MiB L, blocking group, stubbed cleaner; heap-limit positive control. |
| C. Specific | a human can follow it from the intro and B2f/B3f | Met | A1-A3, B1. |
| C. Specific | an AI can run B2/B3 without re-deriving the code path | Partly, fixed | B2e extra thread allocator and the control allocator type were unspecified (`SlabAllocator` has no `NativeAllocator` API); B3c large-value text contradicted itself (2000/3000/2500). Amended. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Met after amendment | Sampling interval for the tracked gauge unspecified: set by the harness to 200 ms (tracked) / 1 s (RssAnon) / 5 s (NMT); stop = workload end + `nodetool flush`. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Closed-case harnesses reused as patterns (`hints-HintsBuffer-put-slabCapacity--autonomous`: node yaml, `Jmx.java`, cluster driver); tree via `copy-source.sh`; JDK 11/Ant on pc07. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met after amendment | 1 KiB: 3 M x ~1.1 KiB = 3.3 GiB = 6.4 x L=512; 256 KiB: 750 MiB = 1.5 x L=512. Data on tmpfs (126 GiB free). Large-value text fixed. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `NativeAllocator.java:47,141,144-145,186`; `MemtableAllocator.java:169-196` (here `:172-196`); `MemtablePool.java` SubPool `tryAllocate :151`, `needsCleaning`/`updateNextClean`; `AbstractAllocatorMemtable.java:82-108`; `DatabaseDescriptor.java:583-584,761-773,4060-4062`; `TableMetrics.java:497-521`. All hold; the case's `~` MemtablePool lines are approximate. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | B2f region-tail bound corrected (excess < regions x S; ~2.4 % at S = 100 KiB) | Applied 2026-10-26 (B2f amendment) | Wrong from the source alone. |
| 2 | B2e/B2h: extra thread uses a second allocator `b`; heap_buffers control drives `SlabAllocator.allocate(S, group)` | Applied 2026-10-26 | The control allocator is not a `NativeAllocator`. |
| 3 | B3a: `memtable_cleanup_threshold: 0.99`; B3f flush point 0.99 L | Applied 2026-10-26 | Default 0.5 L never tests the limit and the 1:2:4 ratio does not hold (peak = 0.5 L + rate x flush time). |
| 4 | B3a: `-XX:+AlwaysPreTouch`, `RssAnon`, tmpfs data, timeouts 30 s / 60 s | Applied 2026-10-26 | Heap RSS growth would swamp L = 128; repo lessons (tmpfs, timeouts). |
| 5 | B3c: large-value workload = 3000 x 256 KiB at every L, protocol 4, 16 threads; stress `-mode native cql3 protocolVersion=4` | Applied 2026-10-26 | Text was inconsistent; native-v5 large frames leave direct buffers. |
| 6 | B3f 256 KiB tolerance peak <= L + 4 MiB | Applied 2026-10-26 | 16 writers x 256 KiB can bypass once via a blocking op group. |
| 8 | B2d/B3d: NMT does not see the regions (`MemoryUtil.allocate` = JNA `Native.malloc`, `MemoryUtil.java:81-83`); real resource = `RssAnon` delta; the probe writes a byte into each 4 KiB page of an allocation | Applied 2026-10-26 (B2d, B3d notes; D summary) | `malloc` pages are resident only when written; NMT "Other" holds `Unsafe.allocateMemory`, not libc malloc. Independent of any reading. |
| 9 | B2f excess bound and `RssAnon` band corrected after the unit-probe instrument check (see Case-file version row) | Applied 2026-10-26 (B2f, B2d notes) | Source arithmetic (the current region's unfilled remainder is part of the capacity sum) and the measured JVM noise floor of the instrument itself, not a prediction reading. |
| 7 | Remaining: B3d wording "poll with nodetool sjk" replaced in practice by a JMX client JVM (`Jmx.java`) | Left for stage 3 (instrument choice, no claim change) | A JVM per `nodetool sjk` call is too slow for 200 ms sampling. |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-26 (unit 09:51-09:53 EDT; cluster 13:53-14:15 UTC) | not done |
| Node (CloudLab name and type) | `pc07` = `node0.jason92-320876...`, 40 cores, 251 GiB; port slot 3 (127.0.3.1, JMX 7130) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy | `~/s4-b7-mo` from `cassandra/cassandra-5.0.9/` (repository commit `e776524`), `copy-source.sh`, `ant build-test` 1 min 11 s; node ran from this tree | |
| Case-file commit / harness commit | `e776524` + uncommitted amendments (sha256 in §1) / harness uncommitted (orchestrator commits) | |
| Storage for node data | tmpfs `/dev/shm/s4-b7-mo` (wiped per lifetime, removed afterwards); unit probe has no storage | |
| Full logs (path, outside the repo) | `~/s4-b7-mo-logs/run1/{unit,unit-attempt1,cluster/<arm>}/` on pc07 (`jmx.csv`, `rss.csv`, `nmt.csv`, `system.log`, `stress.out`, `session.log`) | |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | unit attempt 1 | B2c "cleaner is a stub returning a completed future" | `MemtableCleanerThread` calls `clean()` in a tight loop while `needsCleaning()` stays true (1.8 M calls in 3 s). The garbage it made grew the probe JVM's resident set, which is inside the `RssAnon` reading: 14 of the 24 fill and blocking runs fell outside the RssAnon band (excess 3-40 MiB). All other checks (plateau, exact `used()`, parking, release, capacities) were identical. | The stub sleeps 50 ms per call (20 calls/s); prediction and band unchanged. The tier restarted from its beginning as the run-1 unit tier; attempt 1's output is kept in `run1/unit-attempt1/`. | 2026-10-26: instrument fix, B2f/B2g unchanged | none (probe is in the harness, not the case file) |
| 2 | cluster (shakedown) | B3e | An end-of-run leftover check ran before the node's shutdown hook finished; `mine()` also matched shell command lines. | `mine()` matches `java` processes only and the run waits up to 60 s for the node to exit. | 2026-10-26: harness fix before run 1 | none |

Shakedown (not a reading, discarded): `k512` with 1,000,000 rows on 2026-10-26 09:45 (`~/s4-b7-mo-logs/shake/`) showed that the 0.99 threshold reaches and blocks at the limit and that the harness chain works; no prediction or rule was changed after it.

## 4. Run 1

**Scope:** unit tier: 20 `fill` runs (L = 32/64/128 MiB x S = 100 B, 1 KiB, 100 KiB, 128 KiB, 128 KiB+1, 1 MiB; L = 1 MiB at S = 1 KiB and 128 KiB+1), 2 `blocking`, 4 `control`; cluster tier: arms k128 k256 k512 (3 M x 1 KiB), b128 b256 b512 (3000 x 256 KiB), ctl (heap_buffers), hp (heap-limit positive control). **Command log:** `memtable-offheap-space-allocate-size--autonomous/run1/` (`unit/`, `unit-attempt1/`, `cluster/<arm>/`, `selfcheck.out`, `instrument-check-summary.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit/*.out`; `summary.txt`: 302 checks, 7 MISMATCH, all of them the `RssAnon` band; attempt 1: 14)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| `used()` after the fill = N x S exactly, N = floor(L/S), `used() <= L < used() + S`, `owns()` = `used()` | holds in all 20 fill runs (e.g. L=64, S=1 KiB: 67,108,864 = L; S=128 KiB+1: 66,978,303 = 511 x 131,073, 0.998 L) | `unit/fill-L*-S*.out` (`reading used`, `n`) |
| Extra allocate on a second allocator after the plateau | `WAITING` after 2 s in all 20 runs; `used()` unchanged; after `a.setDiscarding(); a.setDiscarded()` the thread ends and `used() == S` | `extra_state_2s`, `extra_state_after_discard`, `check used==S-after-discard` |
| Oversize path charged (S = 128 KiB+1 and 1 MiB) | plateau at 0.996-0.999 L, same as in-region sizes; capacity sum = `used()` exactly, regions = N | `fill-L*-S131073.out`, `fill-L*-S1048576.out` |
| Region capacity | `capacity_sum >= used()`; excess below the amended bound in all runs; S = 128 KiB excess 0; model replay equals the real capacity in all runs | `check excess<...`, `check instrument-model-capacity` |
| Ceiling follows L | `used()` = 32 / 64 / 128 MiB (within one S) for L = 32 / 64 / 128; L = 1 MiB plateaus at 1 MiB (S = 1 KiB) | `fill-L1-S1024.out` and the above |
| Blocking op group (`issue()` + `markBlocking()`) | writer finishes 10 allocations without parking; `used()` = plateau + 10 x S > L (S = 1 KiB and 128 KiB+1); a non-blocking extra allocate still parks | `unit/blocking-L64-S*.out` |
| `heap_buffers` control (`SlabPool`) | `offHeap.used()` = 0, `onHeap.used()` = N x S, extra allocate not parked, cleaner not invoked | `unit/control-*.out` |
| `RssAnon` delta in `[used - 1 MiB, capacity_sum + 4 MiB]` (L >= 32 MiB) | 13 of 20 inside; 6 above by 0.1-12 MiB (S = 100 B at all L; S = 128 KiB at L = 64, 128; S = 128 KiB+1 at L = 64), 1 below by 0.6 MiB (L = 32, S = 128 KiB+1). NMT "Other" stayed at 4116 KB in every run while the regions grew by 32-128 MiB; NMT total committed grew by 1-14 MiB (JVM internals). | `unit/summary.txt`, `reading nmt_before/after`, `rss_delta` |

**Cluster tier** (tracked = `Table AllMemtablesOffHeapDataSize`, 200 ms; `RssAnon` delta = peak minus the idle baseline; `analysis.txt`, `cluster/<arm>/`)

| Capacity value | Run | Observable | Reading | Evidence (file) |
|---|---|---|---|---|
| L = 128 MiB | k128 (1 KiB) | tracked peak / blocked count / flushes / RssAnon delta | 126.1 MiB (0.985 L) / 2400 / 25 / 302.9 MiB | `k128/{jmx.csv,rss.csv,system-log-excerpt.txt}`, `analysis.txt` |
| L = 256 MiB | k256 | same | 250.5 MiB (0.979 L) / 1226 / 13 / 391.2 MiB | `k256/` |
| L = 512 MiB | k512 | same | 498.1 MiB (0.973 L) / 568 / 7 / 670.8 MiB | `k512/` |
| L = 128 | b128 (256 KiB) | same | 110.8 MiB (0.865 L; 200 ms sampling) / 206 / 6 / 147.8 MiB | `b128/` |
| L = 256 | b256 | same | 241.3 MiB (0.943 L) / 68 / 3 / 287.6 MiB | `b256/` |
| L = 512 | b512 | same | 504.3 MiB (0.985 L) / 16 / 2 / 514.8 MiB | `b512/` |
| control | ctl (heap_buffers, off-heap limit 256) | tracked off-heap / on-heap peak / blocked / RssAnon delta | 0.00 MiB / 1013.8 MiB (heap limit 1024 binds) / 128 / 151.6 MiB | `ctl/` |
| positive control | hp (heap_buffers, `memtable_heap_space` 128MiB) | on-heap peak / blocked / flushes | 126.8 MiB (0.99 x 128) / 1088 / 35 | `hp/` |

All lifetimes: stress `Total errors 0`, 3,000,000 partitions; big client 3000/3000 ok; settings read-back equal to the yaml; JVM flags confirmed; no `ERROR` line in any `system.log`; tracked gauges 0 after the final flush; `AllMemtablesOnHeapDataSize` peaks 46 / 92 / 182 MiB in k128 / k256 / k512 (below the 1024 MiB heap limit, so the heap limit did not bind in the offheap_objects arms).

### 4.2 Conclusion and logic

1. **Validity** — valid. Limit reached in all six offheap_objects arms: [observed: `analysis.txt`] peaks 0.97-0.985 L (k) and 0.87-0.985 L (b), `BlockedOnAllocation` grew (2400 / 1226 / 568; 206 / 68 / 16), 25 / 13 / 7 and 6 / 3 / 2 flushes. Held-fixed settings confirmed [observed: `<arm>/summary.txt` read-back and JVM-flag lines]. Unit tier: fill reached `used() + S > L` in every run [observed: `unit/*.out`]. First-trigger checks passed in all arms.
2. **Readings** — (a) The 200 ms sampling misses the instantaneous top of the sawtooth: b128 shows 0.865 L although writers were blocked 206 times, which requires `used() + 256 KiB > L` at those moments [inferred: `MemtablePool.SubPool.tryAllocate` fails only above the limit]. (b) `BlockedOnAllocation` counts when a wait ends, so its increments sit at the drops of the gauge: in k128 24 increments and 25 drops of more than 0.3 L [observed: `jmx.csv`, recount in `selfcheck`]. (c) The real-resource reading (`RssAnon`) in the 1 KiB arms does not meet the pre-registered relations: delta 303 / 391 / 671 MiB against `1.3 L` = 166 / 333 / 666 (three NO) and ratios 1.29 and 2.21 (not 1:2:4) [observed: `analysis.txt`]; in the 256 KiB arms it does: 148 / 288 / 515 MiB (all within 1.3 L), ratios 1.95 and 3.48 [observed]. The heap_buffers control with the same 1 KiB stress and no off-heap memtable data shows a delta of 151.6 MiB (and its own ctl rule, `<= 0.3 x 256 MiB`, is NO) [observed: `ctl/`]. (d) The unit `RssAnon` band was missed in 7 of 20 fill runs by JVM noise (see 4.1). (e) The unit probe's attempt 1 was invalid for the RSS check (defect 1).
3. **Matched row** — Unit B2g row 1: "`used()` plateaus at `<= L` and extra allocate parks, scaling with L → Claim holds at the operand level" [observed: 20 fill runs, `used()` = N x S, L = 32 / 64 / 128, `WAITING`]; with row 2 "S = 128 KiB+1 also plateaus at L" [observed: 0.996-0.999 L] and the row "Extra thread does not park but `used() > L` only with blocking group → documented soft overshoot (expected)" [observed: `blocking-*`]. The heap_buffers control row [observed: offHeap 0]. Cluster B3g row 1: "Tracked peak <= L, ... blocked count > 0 → Claim confirmed" [observed: peaks, blocked, ordering 126.1 < 250.5 < 498.1 = 1 : 1.99 : 3.95, and 110.8 < 241.3 < 504.3 for 256 KiB]; the RSS part of that row ("NMT/RSS delta tracks L (1:2:4)") holds for the 256 KiB arms and, for the 1 KiB arms, only after subtracting the control's non-memtable growth: delta minus ctl = 151.3 / 239.6 / 519.2 MiB = 1.18 / 0.94 / 1.01 L, ratios 1.58 and 3.43 [inferred: the ctl arm runs the same stress with memtable data on the heap, so its delta is the growth of every other consumer under that load; this subtraction was not a pre-registered rule]. Also "256 KiB values exceed L" (oversize escapes) did not occur: peaks <= L (b arms) [observed]. The heap-limit positive control plateaued at 0.99 x 128 MiB with writers blocked [observed: `hp/`], so the workload can show a binding cap.
4. **Excluded rows** — "Tracked peak > 1.05 L": no, max 0.985 L [observed]. "`used()` > L for a non-blocking group": no [observed]. "`used()` < N x S or independent of S/L": no, exact [observed]. "`used()` stays 0 in offheap_objects": no [observed]. "NMT delta >> capacity sum / grows after the plateau" (unit): no, NMT "Other" did not move while RssAnon followed `used()` within 12 MiB; excess is JVM-internal (NMT total grew) [observed + inferred]. "Peak flat across L": no, ordered and proportional [observed]. "Blocked 0 and peak << L": no [observed]. "heap_buffers control also shows off-heap tracking L": no, 0.00 MiB [observed]. "Tracked peak <= L but RSS grows without bound or >> L-ordered": not matched: growth is bounded and L-ordered (b arms in full; k arms after the control subtraction), but see 6. "Heap-limit positive control did not plateau": no, it did [observed].
5. **Observed vs. inferred** — inferred: (i) the 200 ms sampling understates instantaneous peaks (2a); (ii) the ctl subtraction for the 1 KiB RSS relations (3); (iii) the unit RssAnon excess is JVM-internal growth (NMT total grew, "Other" flat; not separated further); (iv) the blocked-count timer semantics (2b).
6. **Deviations and gaps** — The pre-registered `RssAnon` relations (`<= 1.3 L`; 1:2:4) were NOT met in the 1 KiB arms; they are met only after the post-hoc control subtraction. The B3f bound `L + 0.3 L` never allowed for the other consumers that the same text lists (chunk cache 64 MiB, direct buffers up to 256 MiB; 128 stress connections); measured at 152 MiB under this load. NMT cannot see the regions (JNA malloc): the real resource is read on `RssAnon`. 0.99 cleanup threshold and tmpfs are amendments, not defaults; the default 0.5 threshold was not run (a shakedown showed the limit is reached at 0.99). 256 KiB arms sampled at 200 ms. The unit "Other" NMT checks of the case file could not be made. Run 2 not done.
7. **Core question** — Usage follows the constraint: the tracked memtable native bytes plateau at 97-99 % of L (never above), writers block at the limit (blocked counts, parked allocator), the ceiling moves with L (1 : 1.99 : 3.95 for 1 KiB, 110.8 / 241.3 / 504.3 MiB for 256 KiB) and the oversize path (line 144-145) is charged the same (b arms, unit S = 128 KiB+1), while a heap_buffers pool ignores the off-heap limit. The real memory follows within the stated caveats (the L-attributable `RssAnon` growth is 0.94-1.18 L). So `memtable_offheap_space` caps memtable native memory under `offheap_objects`; `MAX_CLONED_SIZE` is not an escape. Steps: unit parking (3) → cluster blocking and ordering (3) → real resource (2c, 3, 6).

**Conclusion (one line):** Unit: B2g row "`used()` plateaus at `<= L`, extra allocate parks, scales with L" (with the oversize row and the documented blocking-group overshoot) — confirmed; cluster: B3g row "Tracked peak <= L, delta tracks L, blocked > 0" — confirmed, with the 1 KiB RSS relation met only after subtracting the control.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-parsed from the raw files by `harness/.../selfcheck.py` (it does not import `cluster-run.py` and does not read the probe's `check` lines); output `run1/selfcheck.out`.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.out`: 20 fill runs, 0 failing plateau/exact/parked/released/oversize; every cluster arm re-computed from `jmx.csv`/`rss.csv`/`system.log`: peaks, blocked 0 → 2400 etc., flushes, 0 ERROR lines, stress 0 errors / 3,000,000 partitions, big 3000 ok. |
| 2. Readings | yes | Same numbers as `analysis.txt`; the blocked increments (24) vs drops (25) recount in k128 agrees; the unit RssAnon misses are as listed. One selfcheck bug (case of `False`, comma in stress counts) found and fixed before the final print; it concerned the checker, not the data. |
| 3. Matched row | yes, with the caveat in 6 | Operand-level rows hold in both tiers. The RSS part of the cluster row holds in the b arms and after the control subtraction in the k arms; flagged as inferred. |
| 4. Excluded rows | yes | Max tracked/L = 0.985; ctl off-heap 0.00; NMT "Other" flat 95.9 -> 96.5 MiB in k/ctl/hp (rose 13 MiB in b arms, not region-sized). |
| 5. Observed vs. inferred | yes | Five inferred statements listed; the ctl subtraction is the one the verdict depends on for the real-resource clause; the operand-level verdict does not depend on it. |
| 6. Deviations and gaps | yes | Pre-registered RSS relations missed in k arms is stated, not hidden. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1: tracked ceiling follows L; disallow branch fired (parked allocator, blocked counts); entry-point constant not an escape (b arms, S = 128 KiB+1). |

### 5.2 Run 2?

**No** (2026-10-26). The operand-level result is exact and repeats in 20 unit runs and 6 offheap arms; the one inferred step (ctl subtraction) concerns the real-resource clause and would need a changed design (a smaller direct-buffer allowance, fewer stress connections) rather than a repeat; that is left as a recommendation for stage 3 (B3f should state the other-consumer allowance measured here, about 150 MiB under 128 stress threads).

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive. **Outcome class:** true positive (positive, caps).

**Claim tested:** B1: with `memtable_allocation_type: offheap_objects`, memtable native memory (tracked: pool off-heap `used()`; actual: native process memory attributable to memtables) stays at or below `memtable_offheap_space` plus a small bounded slack, writers block at the limit, and changing the limit moves the ceiling proportionally; allocations above 128 KiB (line 144) are charged to the same limit. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — `used()` plateaus at <= L, extra allocate parks, scales with L; oversize path charged; blocking-group overshoot as documented | caps (soft: a blocking op group bypasses once) | run 1 + self-check | 2026-10-26 |
| Cluster | **Confirmed** — tracked peak <= L (0.97-0.985 L), blocked > 0, ordering and proportion with L, 256 KiB values capped; real-resource relation met for 256 KiB values and, for 1 KiB values, after subtracting the control's non-memtable growth | caps | run 1 + self-check | 2026-10-26 |

**Positive control** (a negative-estimate file only): n/a (positive estimate); the `hp` arm (heap limit 128 MiB binding, 126.8 MiB, blocked 1088) showed the workload can show a binding cap.

**Feedback filed:** the case file's section D updated (uncommitted; the orchestrator commits); amendments listed in §1 and section D. Open points for Jingsong: (1) the pre-registered `RssAnon <= 1.3 L` and 1:2:4 checks failed for the 1 KiB arms and the verdict relies on the control subtraction; overrule to "Not confirmed" for the real-resource clause if you want only pre-registered rules; (2) NMT does not see JNA-malloc'd memtable regions (A5 of the case file was wrong); (3) default cleanup threshold 0.5 was not run.
