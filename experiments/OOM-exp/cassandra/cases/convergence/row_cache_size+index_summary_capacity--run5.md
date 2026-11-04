# row_cache_size + index_summary_capacity — convergence case, retry (run 5)

> **Run:** 2026-11-03, node `node0.jason92-323989.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB), same build as runs 1-4 (`~/cassandra-run1`, cassandra-5.0.9, unchanged). Retry of [run 4](row_cache_size+index_summary_capacity.md), using the two changes run 4's §4 named.
>
> **Harness:** [`row_cache_size+index_summary_capacity--run5/`](row_cache_size+index_summary_capacity--run5/) (a copy of run 4's `oom-run.sh` plus the `RESIZE` variable and a `conc` workload; per-arm summaries, yaml diffs, final RSS/cgroup readings, `dmesg` greps and the converge arm's stress output). The ~360 per-5-s sample files stay on the node in `~/oom-offheap-run5/logs/`.
>
> **Outcome: OOM NOT reached, and the convergence arm did not complete its workload.** No kernel OOM-kill (`oom_kill 0` in every arm), no `OutOfMemoryError`, no ERROR lines in `system.log`. The combined peak (1501 MiB `RssAnon`) was *below* both alone arms, because the concurrent index-summary write burst stalled and timed out instead of building summaries. This is not a clean negative; see §3-§4.

> **Correction (2026-11-03, found in [run 6](row_cache_size+index_summary_capacity--run6.md)):** the converge arm's index-summary burst wrote **zero** partitions. The stress client's own `CREATE TABLE isc.t` timed out right after connecting (the `OperationTimedOutException` in its output), and that arm's `system.log` has no `isc/t-` data file. So this arm tested the row cache alone, and the "burst slowed by reclaim throttling" reading in §3-§4 below is wrong. The arm is void, not an incomplete negative. Run 6 pre-creates the table and re-runs both schedules.

## 1. Constraints and capacities

Unchanged from run 4 (see its §1): `row_cache_size` = 550 MiB (`SerializingCacheProvider`, JNA `Native.malloc`) and `index_summary_capacity` = 100 MiB, `-Xmx384M`, cgroup v2 `memory.max` = 2000 MiB (`systemd-run --user --scope -p MemoryMax=2000M -p MemorySwapMax=0`). `-XX:MaxDirectMemorySize` does not bind either (run 4 §1). Both are config-type, true positive in `if-check-exp`, and standing pools.

## 2. Verification solution

Changes from run 4, both taken from its §4:

1. `index_summary_resize_interval: 30m` (was 1m). The startup log confirms "resize interval of 30 minutes"; no resize ran in any arm.
2. **No sequential index-summary preload.** The 1,500,000-partition `isc.t` write burst (`cassandra-stress user profile=isc-profile.yaml`, 64 threads) starts in the background together with the row-cache read pass (550,000 partitions, 48 threads). The row dataset is still preloaded and flushed first, since a row cache can only fill by reads.

Arms (same budget, yaml, node and cleanup as run 4): `I_alone_noresize` (burst only), `R_alone` (read pass only), `converge_concurrent` (both). A `baseline` run was also made but its idle sample failed ("process gone"); each arm takes its own idle reading, so it is not used.

Naive prediction, from the alone arms below: idle ≈ 880 MiB + 728 (I) + 670 (R) ≈ **2278 MiB against a 2000 MiB budget** (114%), a larger predicted overshoot than run 4's 106%.

## 3. Runtime results

Peak `RssAnon` over all samples (MiB), idle ≈ 880 in every arm:

| Arm | Peak RssAnon | Growth over idle | % of 2000 MiB | OOM-kill / ERROR | cgroup `memory.max` hits | Stress outcome |
|---|---|---|---|---|---|---|
| `I_alone_noresize` | 1608 | +728 | 80% | 0 / 0 | 9,131 | burst finished in 1 m 18 s, 19,035 op/s, 0 errors |
| `R_alone` | 1550 | +670 | 78% | 0 / 0 | 69,909 | row cache full: 110,397 entries, 550 MiB of 550 |
| `converge_concurrent` | 1501 | +615 | 75% | 0 / 0 | 75,741 | **index-summary burst hit `OperationTimedOutException` client errors; ran 14 m 18 s with no completion totals; the 10-minute sampling cap (120 samples) ended the arm** |

- Row cache reached its cap in both arms that read (550 MiB, 110,397 entries), so constraint R was fully loaded in the converge arm.
- The converge arm's index-summary side was **not** loaded to the 1.5M partitions the alone arm reached in 78 s. How many partitions it wrote is not recorded (the stress client printed no totals).
- `memory.current` sat at `memory.max` for the whole of `R_alone` and `converge_concurrent` (page cache counts toward it); `memory.events` `max` counts 69-76k vs 9k for the burst alone. `oom_kill` stayed 0, consistent with run 4's finding that `memory.current` is a poor percent-used metric and `RssAnon` is the one to use.
- The 9 `dmesg` OOM-kill lines in every arm's `dmesg-oom.txt` are the run-4 calibration kills (earlier timestamps); no new line appeared during run 5.
- Process note: during `I_alone_noresize` startup I ran `nodetool stopdaemon` by mistake against what looked like an orphaned node. That arm's node stayed up, finished its burst with 0 errors, and its figures look normal, but the interference is recorded here.

## 4. Conclusion

**The node did not OOM, and this run cannot say whether the pair converges, because the converge arm's second workload did not run to completion.**

- What the data does show: running the burst concurrently with the row-cache fill, in a cgroup already pinned at `memory.max` by page cache, made the burst roughly 10x slower and the client timed out. Peak anonymous memory then came in *below* either alone arm (1501 vs 1608 and 1550), the opposite of additive.
- Likely cause (hypothesis, not isolated): direct reclaim throttling at the cgroup limit (`memory.events` `max` ≈ 76k) starved the write path and flushes, so few index summaries were built. This was not tested separately.
- It is the third result in this group where the pair's *own* mechanism, not the budget, decides the outcome: run 4 (eviction and resize kept usage down), and now run 5 (the budget's reclaim pressure slowed the workload that creates the second pool).

**Retry options, not yet tried** (the group stays **open**): (a) a larger stress-client timeout and fewer threads for the burst, so it completes under pressure; (b) fill the row cache first, then run the burst while the cache is parked at 550 MiB, which removes the contention during the fill; (c) a smaller `-Xmx`/budget ratio is *not* recommended, run 4's calibration kills show the margin is already thin.

**Target-3 note:** still the weakest realism of any case here. It needs a 30-minute resize interval (a second deliberate misconfiguration) and a sustained write burst coinciding with heavy cache reads; the on-heap cases remain the cleaner single-operator story.
