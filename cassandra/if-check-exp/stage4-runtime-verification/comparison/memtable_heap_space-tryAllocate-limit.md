# memtable_heap_space-tryAllocate-limit — the two paths side by side

> **Long path:** [`long-path/results/memtable_heap_space-tryAllocate-limit.md`](../long-path/results/memtable_heap_space-tryAllocate-limit.md)
>
> **Short path:** [`short-path/results/memtable_heap_space-tryAllocate-limit.md`](../short-path/results/memtable_heap_space-tryAllocate-limit.md)

Written 2026-10-08 by a separate AI session after both paths' runs were filed and committed (long: closed 2026-09-30; short:
`run-executor.py collect`, 2026-10-06). The rules are in the README's [Two paths, two tiers each](../README.md#two-paths-two-tiers-each).
It edits neither solution nor any results file, and **rates nothing**: it reports.

## 1. Verdicts

| Path | Tier | Verdict (row of that path's own table) | Results file | Date |
|---|---|---|---|---|
| Long | Unit | Consistent with **Confirmed** and **Escape hatch as recorded** (§9a); no Refuted row fired | long §8 | 2026-09-29 |
| Long | Cluster | Consistent with **Confirmed** at 128, 256, 512 MiB and the default; **Escape hatch as recorded** not matched on its own terms (the counter was never read above the limit; the forced bytes were measured by a Byteman trace); not measured: the counter's excess over the limit | long §8 | 2026-09-30 |
| Short | Unit | **Confirmed**: B2g row 1 (the hard-limit check blocks) and row 3 (the `isBlocking()` overshoot, `used()` 120 > 100) | short §8 | 2026-10-06 |
| Short | Cluster | **Confirmed**: B3g row 1 (bounded sawtooth with `MEMTABLE_LIMIT` flushes at 64 MiB) and row 3 (512 MiB control flushes far less, 3 against 24) | short §8 | 2026-10-06 |

All four tiers were run; none was declared `n/a`. Neither path did a run 2.

## 2. Do the conclusions agree?

**Yes, in the claim; the cluster tiers show it through different observables.**

Both paths end with the same claim: `memtable_heap_space` sets `MemtablePool.SubPool`'s limit, `tryAllocate`'s `cur + size > limit`
check makes an ordinary allocation wait at the limit until memory is released, and the one exception is an allocation whose op group
is already blocking (a flush barrier's `markBlocking()`), which goes through and pushes the counter past the limit by its own size.

- **Unit tier: same mechanism, same shape.** Long's `HeapPoolTest` (limit 100 B) shows the waiting writer, the counter holding at the
  limit, the wake-up on `released(50)`, and a forced 1-byte overshoot. Short's `MemtablePoolLimitTest` (limit 100 B) shows the waiting
  writer, the counter holding at 60, the wake-up on `released(60)`, and a forced 30-byte overshoot to 120. The pool differs: long built a
  `HeapPool` (`unslabbed_heap_buffers`) and short a `SlabPool` with a `SlabAllocator` (`heap_buffers`). Both reach the same
  `SubPool`/`SubAllocator` code.
- **Cluster tier: the two designs observe different stages of the same control.**
  - **Long** set `memtable_cleanup_threshold: 0.99`, so the cleaner did not flush until the pool was nearly full. That made writers
    reach the hard check. It reads the check itself: first limit flush at 99.1–99.8 % of the limit at all four values, all 32
    `MutationStage` threads parked at `MemtableAllocator.java:195` in the thread dumps, and the `BlockedOnAllocation` count rising.
  - **Short** kept `memtable_cleanup_threshold: 0.5`, so the cleaner flushed at half the limit (≈ 32 MiB of 64 MiB, ≈ 256 MiB of
    512 MiB). The memtable never got near the hard limit, and no writer wait was read at this tier. What it shows is the knob's
    dose-response through the cleaner's trigger (`cleanup_threshold × limit`): 24 against 3 `MEMTABLE_LIMIT` flushes on an identical
    workload.
  - Long's control (256 MiB, default threshold) matches short's setup most closely. Flushes there started at 33 % of the limit, as in
    short's runs, but at long's heavier workload (256 stress clients) writers still waited. Short's lighter workload
    (20,000 × 8 KiB) did not need to reach the check.

Neither path's readings contradict the other's. Each path's own prediction decided its own rows.

## 3. What only one path's design produced

**Long path only**
- **The wait seen directly at the cluster tier:** thread dumps with 32 frames at `MemtableAllocator.java:195`, plus the
  `BlockedOnAllocation` count and its timer. These come from `cleanup_threshold: 0.99`, the stress load and `jstack`.
- **The peak following the knob at four values including the default:** 127.3, 254.1, 511.1 and 1014.6 MiB at the first limit flush.
  Short had two values and never reached the limit.
- **The escape hatch's size under real load:** 0.02–0.94 % of the limit forced through per run, about 800 B per call. Measured with the
  Byteman rule `escape-hatch.btm` on `SubAllocator.allocated(long)`.
- **Real heap against the counter:** within +37 / −22 MiB of idle + limit once the young generation is subtracted (`GC.run` +
  `GC.heap_info`, a second pass). At the unit tier, `MemtableSizeUnslabbedTest` found the accounting within 0.08 % of jamm's deep size.
- **The default cleanup threshold does not keep writers off the limit under heavy load** (the control column).
- Wait length and client `WriteTimeoutException` counts both grow with the knob.

**Short path only**
- **Flush-count dose-response at the stock-like cleanup threshold 0.5:** 24 flushes at 64 MiB against 3 at 512 MiB, same workload,
  each at `cleanup_threshold × limit`. Long's runs used 0.99, except one control at the default threshold.
- **The `SlabPool` / `heap_buffers` allocation type.** Long ran only `unslabbed_heap_buffers`.
- Every flush's `Reason:` is `MEMTABLE_LIMIT` in both runs. This rules out period and schema flushes (B3h's control).

## 4. Runbook defects

**Long path:** 2 defects, both non-blocking, both fixed in the case file.
1. §9c pointed at `git show e90423c^:…` instead of the committed harness (fixed `745c1ab`).
2. §9d's raw `used` heap figure includes the young generation, which was 4× the limit at 128 MiB end of A. Fixed to read `used` − young
   (`5ad5c16`).

Not defects, but recorded as deviations: the first cluster pass sampled real heap only at idle, a script omission that a second `heap`
pass covered; and `JVM_EXTRA_OPTS` was unset after start so the Byteman agent stayed out of the tool JVMs.

**Short path:** 3 defects, fixed in the harness; the solution is never amended.
1. B2e: the test called `allocate(int, Group)` on the abstract `MemtableAllocator`, which does not compile. Fixed with a cast to
   `SlabAllocator`.
2. B3e: the runbook created `ks.t`, but the stress command writes `keyspace1.standard1`. The observables were repointed.
3. B3a/B3b: the 512 MiB control equals `-Xmx512m`. Fixed by giving the control `-Xmx768m`, while the 64 MiB run stayed at 512m.

Gaps left: B2h's extra controls were not run; B3g row 4 was only partly checked because `jstat` failed, so `jcmd GC.heap_info` was used.
The executor also met a `pgrep -f` self-match over ssh and fixed it with a script file.

**Blindness audit (short path, `collect-report.txt`): `BLINDNESS: FAIL`, 1 EXECUTED hit, 0 REFUSED.**
- The hit is one Bash call on `pc80` that ran `ls -la /proj/misconfiguration-PG0/git-repos/ | head -3`. That is the repository copy on
  the shared mount, which the executor must not list. The executor reported it itself (short §1, "accidental forbidden read"); it says
  the output showed only `.`/`..` permission lines.
- The result was accepted and copied (HANDOFF: "one audit hit accepted").
- Not hits, but in the same record:
  - Before settling on `pc80`, the executor ran read-only checks (`java`, `ant`, `pgrep`, `df`) on `pc66` and `pc72`.
  - `pc80`'s home held the long path's `cassandra-run1`, `stage4-harness-run` and `stage4-logs` at start (preflight P6). The audit shows
    no access to them.

## 5. Cost

| Path | Tier | Runs | JVMs / nodes | Wall-clock |
|---|---|---|---|---|
| Long | Unit | 1 run on `pc66`: `HeapPoolTest` + `MemtableSizeUnslabbedTest` (2 `ant` invocations) | build/test JVMs only | not recorded as a total (2026-09-28) |
| Long | Cluster | instrument check + 5 node runs (128, 256, 512 MiB, default, control) + a second `heap` pass of the same 5 values (A and B only) | 1 node (`pc66`), 10 node starts, `-Xmx4G` | not recorded as a total; node starts on 2026-09-29: 17:54 (128 MiB), 19:43–19:49 (the other four), 21:58–22:05 (heap pass), each run a few minutes |
| Short | Unit | 1 run on `pc80`: `MemtablePoolLimitTest`, 2 `ant test` invocations (after 1 compile failure, defect 1) | build/test JVMs only | inside the session below |
| Short | Cluster | 2 node runs (64 MiB, 512 MiB control) | 1 node (`pc80`), 2 node starts, 3 separate clones built | stress 12 s and 8 s; the whole executor session, both tiers included, 13:35 → collect 14:13 EDT, 2026-10-06 (≈ 38 min) |

Short executor: claude-sonnet-5, Claude Code 2.1.272, 100 tool calls.
