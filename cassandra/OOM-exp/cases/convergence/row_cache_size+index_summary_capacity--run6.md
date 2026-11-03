# row_cache_size + index_summary_capacity — convergence case, retries A and B (run 6)

> **Run:** 2026-11-03, node `node0.jason92-323989.misconfiguration-pg0.cloudlab.umass.edu`, same build as runs 1-5 (`~/cassandra-run1`, cassandra-5.0.9, unchanged). Runs the two retries named in [run 5](row_cache_size+index_summary_capacity--run5.md)'s conclusion.
>
> **Harness:** [`row_cache_size+index_summary_capacity--run6/`](row_cache_size+index_summary_capacity--run6/) (`oom-run.sh` with the `after` workload token, `ISC_THREADS`/`ISC_RETRIES`, the `isc.t` pre-create step and per-table `tablestats`; per-arm summaries, yaml diffs, final readings, stress output, and for arm B the last RSS samples, the kill's `dmesg` lines and the `system.log` tail). Per-5-s samples stay on the node in `~/oom-offheap-run5/logs/`.
>
> **Outcome: OOMed in schedule B (kernel cgroup OOM-kill of the JVM); not reached in schedule A (peak 93% of budget).** The deciding factor was whether the index-summary flush/compaction transient after the write burst landed while the row cache was already full.

## 1. Constraints and capacities

Unchanged from runs 4-5: `row_cache_size` = 550 MiB (`SerializingCacheProvider`, JNA `Native.malloc`), `index_summary_capacity` = 100 MiB, `-Xmx384M`, `memtable_heap_space: 220MiB` stabilizer, cgroup v2 `memory.max` = 2000 MiB (`-p MemorySwapMax=0`). `index_summary_resize_interval: 120m`, so no resize could run in any arm; none did. Both constraints are config-type true positives in `if-check-exp`, and both are standing pools. `-XX:MaxDirectMemorySize` does not bind either (run 4 §1), so `RssAnon` is the reading and the cgroup kill is the outcome signal.

## 2. Verification solution

| Arm | Workload schedule | Burst settings |
|---|---|---|
| `A_I_alone_slow` | index-summary burst alone (control for A) | 16 threads, 50 retries/op |
| `A_converge_slow` | row preload; then burst and row read pass started together | 16 threads, 50 retries/op |
| `A_converge_slow_precreated` | same as above, with `isc.t` created by `cqlsh` on the idle node first | 16 threads, 50 retries/op |
| `B_converge_rowfirst` | row preload; read pass in the foreground until the row cache is at its cap; then the burst, with `isc.t` created by the stress client (on a node not yet under burst load) | 64 threads, 50 retries/op |

Controls for B are run 5's `I_alone_noresize` (64 threads, peak +728 MiB over idle) and `R_alone` (+670 MiB); B differs only in the retry count, which matters only when operations fail, and none failed. Burst size is 1,500,000 partitions with ~200-char keys in every arm (`isc-profile.yaml`, `min_index_interval=1`); row dataset 550,000 partitions of 1 KiB.

**Harness defect found and fixed during this run.** `A_converge_slow` wrote **zero** index-summary partitions: the stress client's own `CREATE TABLE isc.t` timed out (12 s driver timeout) under the concurrent read load, and `-errors retries` does not cover the schema step. `tablestats` reported `Unknown tables: [t] in keyspace: isc`, and that arm's `system.log` has no `isc/t-` data file. The same failure applies to run 5's `converge_concurrent` (same stack trace right after "Connected to cluster", no `isc/t-` file in its log); run 5's case file is corrected accordingly. `A_converge_slow_precreated` is the valid A arm.

Predictions (naive addition of the alone arms' growth over idle):

- **A:** idle 866 + 497 (16-thread burst alone) + 670 (row cache alone) ≈ **2033 MiB, 102%** of budget.
- **B:** idle 881 + 728 (64-thread burst alone) + 670 ≈ **2279 MiB, 114%** of budget.

## 3. Runtime results

| Arm | Idle | Peak RssAnon | % of 2000 MiB | Burst | Row cache | Outcome |
|---|---|---|---|---|---|---|
| `A_I_alone_slow` | 873 | 1370 | 69% | 1.5M in 52 s, 0 errors | off (1 MiB) | alive |
| `A_converge_slow` | 869 | 1520 | 76% | **0 written** (schema timeout) | 550 MiB of 550 | alive; void (harness defect) |
| `A_converge_slow_precreated` | 866 | **1866** | **93%** | 1.5M in 1 m 42 s, 0 errors | 550 MiB of 550 (read pass took 25 m 51 s) | alive, `oom_kill 0` |
| `B_converge_rowfirst` | 881 | **1940** sampled; **1973** at kill (`dmesg` anon-rss) | **97% → killed** | 1.5M in 1 m 58 s, 0 errors | 550 MiB of 550 before the burst began | **OOM-killed** |

**Arm B, timeline.**
- 14:42:31 to 14:55:47: the read pass fills the row cache to 550 MiB (110,397 entries); `RssAnon` is 1489 MiB.
- 14:55:47: the burst starts. `RssAnon` climbs about 18 MiB per 5 s sample: 1561 (t5), 1643 (t10), 1727 (t15), 1833 (t20), 1883 (t23), 1940 (t24).
- About 14:57:45: the burst completes all 1,500,000 inserts with 0 errors. `isc.t` flushes are still running (`system.log`: "Completed flushing … isc/t-…/nb-15-big-Data.db" at 19:57:53 UTC), with old-gen GCs of 350-510 ms.
- 14:57:58: the kernel logs `CompactionExecu invoked oom-killer`, `constraint=CONSTRAINT_MEMCG`, `oom_memcg=…/oom-offheap5-1793734756127….scope` (this arm's scope), and `Killed process 243295 (java) … anon-rss:2020764kB`. PID 243295 is the arm's node (`summary.txt`). No `OutOfMemoryError` and no ERROR in `system.log`; the process is gone from sample 26.

**Arm A (precreated), timeline.** The burst started with the read pass and finished in 1 m 42 s, while the row cache was still mostly empty. `RssAnon` was 1499 MiB at t25 and fell to 1398 MiB by t30 (flush and compaction of `isc.t`: 4 sstables, then 9, to 3). The row read pass then ran for 26 minutes under the cgroup ceiling (`memory.events` `max` 95,295) and filled the cache to 550 MiB. `RssAnon` rose slowly to 1866 MiB, where both pools sat fully loaded together: row cache 550/550 MiB, index summaries 303 MiB off-heap (`tablestats`: 317,703,624 bytes, 1,506,602 partitions estimated, 3 sstables). There was no kill.

The "OutOfMemoryError mentions: 1" line in every arm's `summary.txt` is a grep false positive: it matches the `-XX:+HeapDumpOnOutOfMemoryError` flag in the logged JVM arguments.

## 4. Conclusion

**The pair converges to a real OOM when the index-summary write burst, and its flush/compaction tail, lands on a row cache already parked at its cap (B).** Each was safe alone: 78% (row cache) and 80% (64-thread burst) of the 2000 MiB budget. Together the node was killed by the kernel at 1973 MiB anonymous memory. The killing allocation came from `CompactionExecutor` during the post-burst flush/compaction, where old and new sstables' index summaries briefly coexist; `index_summary_capacity` only bounds summaries at a periodic resize, and none ran in the 120-minute interval.

**Concurrent schedule (A) did not OOM.** Both pools ended fully loaded together (93%), but the burst finished in under two minutes, while the row-cache fill took 26 minutes. The compaction transient therefore came and went before the cache was full, and the steady state (550 + 303 MiB) fits under the budget. This matches runs 4-5: the outcome depends on whether the two constraints' *transient* peaks coincide, not on their steady-state sum.

**Why runs 4 and 5 did not show this:** run 4's 1-minute resize trimmed summaries before the row cache filled. Run 5's burst never wrote anything (the schema timeout above), so run 5 tested only the row cache.

**Target-3 note.** Schedule B is a plausible operator story: a large row cache that is warm, then a bulk load into a table with dense index sampling (`min_index_interval=1`). It still needs `index_summary_resize_interval` well above default, or a burst that finishes before the next resize tick (the default is 60 minutes, so a 2-minute burst usually does), and an unrealistically fine-grained sampling setting to make the summaries large. It is less of a pure two-knob misconfiguration than the on-heap cases, but the kill itself is genuine.

**Group status:** the `row_cache_size` + `index_summary_capacity` pair is **closed (OOMed)**. The off-heap group stays open only for candidates not yet tried (`memtable_offheap_space`, the networking `BufferPool` family, `file_cache_size`); see `_constraint-groups.md`.

## Instrument check and process hygiene

- The kill is attributed from `dmesg` (`oom_memcg` path equals this arm's scope unit; killed PID equals the arm's node PID), not from the process merely disappearing.
- No `OutOfMemoryError`, no ERROR line, and no resize line in any arm; `index_summary_resize_interval=120m` was confirmed in each startup log.
- After every arm, `pgrep` for `CassandraDaemon` and `cassandra-stress` returned empty, and the scope unit was stopped. Node data, commit log and logs lived under `~/cassandra-run1` on local disk; nothing was written to `/proj`, and the repository's `cassandra/cassandra-5.0.9/` was not touched.
