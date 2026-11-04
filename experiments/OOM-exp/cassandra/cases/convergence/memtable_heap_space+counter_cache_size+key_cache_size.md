# memtable_heap_space + counter_cache_size + key_cache_size — convergence case

> **Run:** 2026-11-02, node `node0.jason92-323989.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB, local disk `/dev/sda3` 63 GB), Ubuntu 22.04.2, kernel `5.15.0-198-generic`, OpenJDK 11.0.32.1, Ant 1.10.12. Third constraint added to the closed [`memtable_heap_space+counter_cache_size`](memtable_heap_space+counter_cache_size.md) case, on the same shared budget.

> **Harness:** [`memtable_heap_space+counter_cache_size+key_cache_size/run1/oom-run.sh`](memtable_heap_space+counter_cache_size+key_cache_size/run1/oom-run.sh). Full logs on the node at `~/oom-exp-logs/{baseline3,M_alone,C_alone,K_alone,converge}/`; small excerpts under [`memtable_heap_space+counter_cache_size+key_cache_size/run1/`](memtable_heap_space+counter_cache_size+key_cache_size/run1/).

> **Outcome: OOM reached — and this time the JVM actually died.** The convergence arm (`memtable_heap_space=350MiB` + `counter_cache_size=250MiB` + `key_cache_size=200MiB`, three concurrent workloads — write, counter_write, read — at `-Xmx1024M`) drove the heap to 989 MiB/1024 MiB (96.6%) right after a forced full GC, with a 72-byte allocation request failing because "heap already fully expanded"; the JVM threw a genuine `OutOfMemoryError`, wrote a 1.35 GB heap dump, and `-XX:OnOutOfMemoryError=kill -9 %p` **actually fired this time** and killed the process outright. All three control arms (each constraint alone, same heap, same per-constraint workload) ran to completion with 0 errors and 46–87% heap free.

## 1. Constraints and capacities

Extends the closed 2-constraint case with a third on-heap, config-type **true positive** from if-check-exp: `key_cache_size` ([`key_cache_size-create-size--autonomous`](../../../../if-check-exp/cassandra/stage3-ai-deep-read/cases/key_cache_size-create-size--autonomous.md), stage-4 result [`key_cache_size-create-size--autonomous.md`](../../../../if-check-exp/cassandra/stage4-runtime-verification/results/key_cache_size-create-size--autonomous.md)). All three constraints are config-type true positives and draw on the same single-node JVM heap:

| | `memtable_heap_space` | `counter_cache_size` | `key_cache_size` |
|---|---|---|---|
| Caps | on-heap memtable pool (soft, self-reclaiming — writers block, a flush drains it) | on-heap counter cache (Caffeine weight, non-self-reclaiming) | on-heap key cache (Caffeine weight, non-self-reclaiming) |
| Default / how set | yaml `memtable_heap_space` (default: 1/4 heap); restart-only | yaml `counter_cache_size` (default: null → auto `min(max(1, 2.5% heap), 50)` MiB); restart or JMX | yaml `key_cache_size` (default: null → auto `min(max(1, 5% heap), 100)` MiB); restart or JMX |
| Prior finding relied on (not re-derived) | real on-heap usage tracks the limit almost exactly, excess +1–18% (`-Xmx4G` source experiment) | real heap increase ≈1.8–2.1× the weighted size (2 GiB heap) | real on-heap bytes attributable to cached entries track the weight with a constant factor, 1.417× for the counted classes, 1.9–2.0× for the whole-heap increase (`key_cache_size` stage-4, `C` = 4/16/64 MiB on a `-Xmx1024M`-scale heap) |

**Why a 3rd constraint, and why `key_cache_size` and not `row_cache_size`/`index_summary_capacity`:** the HANDOFF's open follow-up suggested `row_cache_size` and `index_summary_capacity` as candidates, but checking their stage-4 results (not previously checked) shows both are **off-heap** (`row_cache_size`: `Native.malloc` bytes measured via `RssAnon`; `index_summary_capacity`: off-heap index-summary size) — a different budget from `-Xmx`, not a clean 3rd on-heap constraint. `key_cache_size` is on-heap, config-type, true positive, and (like `counter_cache_size`) a non-self-reclaiming Caffeine-weighted cache, making it the closer analog.

**Shared budget and node total:** single-node JVM heap, `-Xms1024M -Xmx1024M` (same budget as the closed 2-constraint case, for comparability).

## 2. Verification solution

### 2.1 Baseline

Started the node with `memtable_heap_space=32MiB`, `counter_cache_size=1MiB`, `key_cache_size=1MiB` (all tiny/off), `memtable_allocation_type: unslabbed_heap_buffers`, `memtable_cleanup_threshold: 0.99`, no load, waited 5 s after "listening for CQL clients", then `jcmd GC.run` + `jcmd GC.heap_info`.

> `garbage-first heap total 1048576K, used 58190K ...` — [`memtable_heap_space+counter_cache_size+key_cache_size/run1/baseline3/heap-idle.txt`](memtable_heap_space+counter_cache_size+key_cache_size/run1/baseline3/heap-idle.txt)

Idle used heap = 58,190 K ≈ **56.8 MiB**, matching the closed case's baseline (58,194 K) almost exactly — adding `key_cache_size=1MiB` to the tiny-knob baseline changes nothing measurable. **Baseline b ≈ 60 MiB** (same rounding as before, re-confirmed rather than assumed).

### 2.2 Sizing

Overhead/excess multipliers taken from the if-check-exp findings (not re-derived): memtable ×1.1 (conservative within the 1–18% range), counter cache ×2.1 (within 1.8–2.1×), key cache ×2.0 (within the 1.9–2.0× whole-heap-increase range, the more conservative of the two reported factors).

Chose smaller individual values than the closed 2-constraint case (M=350, C=250, K=200 instead of M=550, C=300) specifically so that **no pairwise subset is already at risk of overshoot** — the point of this case is that it takes all three together, not that any two of them already do it (as M=550+C=300 alone would have, per the closed case's own numbers).

**Each alone, safe (≥30% free required):**

- **M alone** (`memtable_heap_space=350MiB`, write only): predicted = 60 + 350×1.1 = 60 + 385 = **445 MiB = 43.5% of 1024 MiB → 56.5% free.**
- **C alone** (`counter_cache_size=250MiB`, counter_write only): predicted = 60 + 250×2.1 = 60 + 525 = **585 MiB = 57.1% → 42.9% free.**
- **K alone** (`key_cache_size=200MiB`, read only): predicted = 60 + 200×2.0 = 60 + 400 = **460 MiB = 44.9% → 55.1% free.**

**Combined** (M+C+K together, all three workloads concurrent):

predicted = 60 + 385 + 525 + 400 = **1370 MiB = 133.8% of the 1024 MiB `-Xmx`**, i.e. 346 MiB (34%) over budget before running anything — a comparable overshoot magnitude to the closed case's 126% prediction. §3 reports what was actually measured.

### 2.3 Workload

One `cassandra-stress` workload per constraint:

- **write** (memtable): `write n=3000000 no-warmup -col 'size=FIXED(1024)' -rate threads=256`, same as the closed case.
- **counter_write** (counter cache): `counter_write n=600000 no-warmup -rate threads=64`, same as the closed case.
- **read** (key cache): key cache only engages on reads that hit an sstable, not the memtable, so every arm whose workload includes `read` first preloads and flushes **500,000 partitions** (`write n=500000 no-warmup -col 'size=FIXED(1024)'` + `nodetool flush`) under that arm's own already-running node, re-samples idle heap, then runs `read n=4000000 no-warmup -col 'size=FIXED(1024)' -pop 'seq=1..500000' -rate threads=192` against that preloaded range. (The `-col` on the read must match the preload write's or `cassandra-stress` reports "Data returned was not validated" and aborts early — hit this on the first `K_alone` attempt, fixed before the result below.)
- **Convergence arm:** all three launched as background processes in the same window against the same node.

### 2.4 Instruments

Same as the closed case: `jcmd <pid> GC.run` + `GC.heap_info` at idle, after preload (read arms), and every 5 s during the workload window; `ps -o args=` to confirm `-Xmx1024M`; the node's own startup log for the resolved M/C/K values; `grep ERROR`/`OutOfMemoryError` in `system.log`; `sudo dmesg -T` for kernel OOM-kills; process/port checks before and after every arm.

### 2.5 Procedure (as executed)

```
oom-run.sh baseline
oom-run.sh arm M_alone      350 -   -   write
oom-run.sh arm C_alone      -   250 -   counter
oom-run.sh arm K_alone       -   -  200 read
oom-run.sh arm converge     350 250 200 write,counter,read
```

Each arm: fresh `conf/cassandra.yaml` from the pinned tag + the stated edits, clean `data/`, start the node, confirm `-Xmx1024M` from the running process's own args, confirm the resolved on-heap/cache values from the node's own startup log, idle heap sample (plus a post-preload sample for `read`-workload arms), launch the workload(s) in the background, sample heap every 5 s (up to 90 samples / 450 s) until the requested workloads exit, final forced-GC heap sample, log/dmesg/process checks, stop the node.

## 3. Runtime results

### 3.1 Control arm 1 — `memtable_heap_space=350MiB` alone

- Node confirmed at `-Xmx1024M`; startup log: `Global memtable on-heap threshold is enabled at 350MiB`.
- Transient samples during the write burst ran as high as 963,652 K (92% of `-Xmx`) — expected GC churn under a 256-thread write burst — but **final forced-GC heap: `used 132799K`** ≈ **129.7 MiB = 12.7% of `-Xmx` → 87.3% free** [`memtable_heap_space+counter_cache_size+key_cache_size/run1/M_alone/heap-final.txt`](memtable_heap_space+counter_cache_size+key_cache_size/run1/M_alone/heap-final.txt): once the write finished and the memtable pool drained (self-reclaiming), the heap settled well below the 56.5% free predicted — more margin than predicted, same direction as the closed case.
- `ERROR` lines in `system.log`: **0**. The one `OutOfMemoryError` string match in this arm's grep is the JVM's own `-XX:+HeapDumpOnOutOfMemoryError`/`-XX:OnOutOfMemoryError` flag names in the startup-args log line, not a thrown exception. No kernel OOM-kill, node stopped cleanly.

### 3.2 Control arm 2 — `counter_cache_size=250MiB` alone

- Node confirmed at `-Xmx1024M`; startup log: `Initializing counter cache with capacity of 250 MiBs`.
- **Final forced-GC heap: `used 563576K`** ≈ **550.4 MiB = 53.7% of `-Xmx` → 46.3% free** [`memtable_heap_space+counter_cache_size+key_cache_size/run1/C_alone/heap-final.txt`](memtable_heap_space+counter_cache_size+key_cache_size/run1/C_alone/heap-final.txt) — close to the 42.9% free predicted (actual ran with a little more margin).
- `ERROR` lines in `system.log`: **0** (same false-positive flag-name match as arm 1). No kernel OOM-kill, node stopped cleanly.

### 3.3 Control arm 3 — `key_cache_size=200MiB` alone

- Node confirmed at `-Xmx1024M`; startup log: `Initializing key cache with capacity of 200 MiBs`.
- Preload (500,000 partitions, flush) ran under this arm's own node: idle 58,188 K → after-preload 75,453 K (still tiny; the write+flush itself leaves almost nothing on-heap once drained).
- `read n=4000000` against the preloaded range completed in 30 s, **0 errors**, 4,000,000 partitions read, after an initial attempt failed with "Data returned was not validated" (fixed by matching `-col` between the preload write and the read — see §2.3).
- **Final forced-GC heap: `used 161279K`** ≈ **157.5 MiB = 15.4% of `-Xmx` → 84.6% free** [`memtable_heap_space+counter_cache_size+key_cache_size/run1/K_alone/heap-final.txt`](memtable_heap_space+counter_cache_size+key_cache_size/run1/K_alone/heap-final.txt) — far safer than the 55.1% free predicted; key cache's real-heap overhead for this workload ran well under the conservative 2.0× used in sizing.
- `ERROR` lines in `system.log`: **0** (same flag-name false positive). No kernel OOM-kill, node stopped cleanly.

### 3.4 Convergence arm — all three at capacity, all three workloads concurrent

- Node confirmed at `-Xmx1024M`; startup log confirms all three resolved values: `Global memtable on-heap threshold is enabled at 350MiB`, `Initializing counter cache with capacity of 250 MiBs`, `Initializing key cache with capacity of 200 MiBs`.
- Preload (500,000 partitions, flush) ran first under this arm's own node (idle 58,322 K → after-preload 88,441 K), then `write`, `counter_write`, and `read` were launched together as background processes in the same window.
- Heap climbed steadily and did **not** drain back down the way the M-alone control did: by the 78th 5-second sample it was at 993,103 K (94.7% of `-Xmx`); the last few samples before the node went unresponsive were 995,366 K, 996,687 K, and **998,697 K (95.2%)** at sample 88 [`memtable_heap_space+counter_cache_size+key_cache_size/run1/converge/summary.txt`](memtable_heap_space+counter_cache_size+key_cache_size/run1/converge/summary.txt). The sampling loop ran its full 90 iterations (450 s) without either seeing "all workloads finished" or the daemon going down — the node was still technically alive and answering `jcmd` through most of this window, just saturated.
- `system.log` recorded 30 `ERROR` lines, all `WriteTimeoutException: Operation timed out — received only 0 responses` on `CounterMutationStage` threads starting at 19:47:23 — coordinator-side timeouts caused by GC pauses, not literal heap-space throws; the key cache's own `StatusLogger` line right before the end showed `Size 116,825,736 / Capacity 209,715,200` (111.4 / 200 MiB, still filling, not yet at its cap when the node died).
- The final forced-GC heap sample is where the case diverges from the closed 2-constraint case: `jcmd GC.run` was issued at 14:58:29 and did not return until **14:58:29 + 3m40s** later; `GC.heap_info` immediately failed with `java.io.IOException: Premature EOF` — the attach itself failed because the process was already gone. `logs/gc.log`'s last entries confirm why: `Pause Full (G1 Evacuation Pause) 989M->989M(1024M) 850.958ms`, then `Attempt heap expansion (allocation request failed). Allocation request: 72B` → `Did not expand the heap (heap already fully expanded)` → `Entering safepoint region: ReportJavaOutOfMemory` [`memtable_heap_space+counter_cache_size+key_cache_size/run1/converge/heap-final.txt`](memtable_heap_space+counter_cache_size+key_cache_size/run1/converge/heap-final.txt), [`memtable_heap_space+counter_cache_size+key_cache_size/run1/converge/gc-run-final.txt`](memtable_heap_space+counter_cache_size+key_cache_size/run1/converge/gc-run-final.txt). A genuine `OutOfMemoryError` fired — the JVM could not satisfy a 72-byte allocation even after a forced full GC left the heap at 989 MiB/1024 MiB (96.6%), with the heap already at its maximum expansion.
- The crash left a **1.35 GB heap dump** on disk (`logs/cassandra-1793648650-pid44684.hprof`, from `-XX:+HeapDumpOnOutOfMemoryError`), and this time, unlike the closed 2-constraint case, `-XX:OnOutOfMemoryError=kill -9 %p` **actually fired**: `pgrep -f CassandraDaemon` came back empty with no `stopdaemon` needed — the process was gone on its own.
- `sudo dmesg -T` shows no kernel-level OOM-kill or "Killed process" entries anywhere near the run's time window — this was a JVM self-termination from genuine heap exhaustion at a 1,048,576 KB `-Xmx` ceiling, not a kernel-level OOM-kill (consistent with the node's 251 GiB of physical RAM being nowhere near exhausted; the constraint is the deliberately small `-Xmx`, not the node).

**Matching the prediction (§2.2):** predicted combined usage was 1370 MiB (133.8% of `-Xmx`, 346 MiB over budget). As in the closed case, the JVM cannot report `used` above `-Xmx` by construction, so the raw predicted number isn't directly observable once the heap is actually full — what the prediction correctly anticipated is the *direction and scale* of the overshoot: each control arm left 46–87% of the 1024 MiB free, while the combined arm climbed past 95% and then genuinely ran out, this time crossing all the way into a real crash rather than surviving with caught exceptions.

## 4. Conclusion

**The node OOMed, more severely than the 2-constraint case.** `memtable_heap_space=350MiB`, `counter_cache_size=250MiB`, and `key_cache_size=200MiB`, each driven alone against the identical `-Xmx1024M` heap and its own matching workload, left 46.3–87.3% of the heap free with zero errors. Driven **together** — `cassandra-stress write`, `counter_write`, and `read` running concurrently against the same node — heap usage climbed past 95% of `-Xmx`, a forced full GC still left it at 96.6% with a 72-byte allocation failing, and the JVM threw a genuine `OutOfMemoryError`. This time `-XX:OnOutOfMemoryError=kill -9 %p` fired and killed the process outright (the closed 2-constraint case's JVM survived its caught `OutOfMemoryError`s; this one did not), leaving a 1.35 GB heap dump as direct evidence of the crash.

**This answers the HANDOFF's open follow-up** ("a 3rd heap-budget constraint, to make a convergence case with three constraints instead of two"): three on-heap config-type true positives converge into an OOM at smaller individual values than two did (M=350/C=250/K=200 here vs. M=550/C=300 in the closed case), and the three-way combination crashed the JVM rather than merely stressing it, consistent with three independent pools competing for the same fixed heap being strictly worse than two.

**Target-3 note:** realistic from a single operator's misconfiguration, same caveat as the closed case — three independent yaml knobs (`memtable_heap_space`, `counter_cache_size`, `key_cache_size`) set without checking their combined sum against `-Xmx` is a plausible "give every cache/pool more room" mistake, and none of the three values here is unusual on its own (`key_cache_size=200MiB` is well inside the range the if-check-exp source experiment exercised at larger heaps). The engineered part is again the workload: three concurrent, sustained traffic patterns (plain writes, counter writes, and reads against existing data) are needed to fill all three pools in the same window; a cluster carrying genuinely mixed read/write/counter traffic under sustained load would reach the same state without deliberate orchestration.

## Instrument check and process hygiene

- Baseline, all three control arms, and the convergence arm each confirmed `-Xmx1024M`/`-Xms1024M` from the running process's own `ps -o args=` output before any reading, and the resolved yaml values from the node's own startup log (`Global memtable on-heap threshold is enabled at <M>MiB`, `Initializing counter cache with capacity of <C> MiBs`, `Initializing key cache with capacity of <K> MiBs`).
- After every control arm: `ps -eo cmd | grep '[C]assandraDaemon'` returned empty and `ss -ltn` showed none of ports 7000/7199/9042 in use before the next arm started. After the convergence arm, the same check returned empty because the process had already self-terminated (confirmed via `logs/gc.log`'s `ReportJavaOutOfMemory` safepoint entry and the 1.35 GB `.hprof` file, not because the harness's `stopdaemon` had to intervene).
- Node data (`data/`), commit log, and logs lived under `~/cassandra-run1` on local disk (`/dev/sda3`); nothing was written to `/proj`. The repository's `systems/cassandra/source/` was never touched.
- `sudo dmesg -T` was checked after the convergence arm specifically to rule out a kernel-level OOM-kill given the process's disappearance; it showed none (the kernel log's only entries near this time window are unrelated NIC driver messages from this node's own earlier boot) — the death is a JVM self-kill triggered by `-XX:OnOutOfMemoryError`, not the OS reclaiming memory, consistent with 1024 MiB being a tiny fraction of the node's 251 GiB.
- The one `read`-arm harness bug hit and fixed during this run (cassandra-stress validation failure from a `-col` mismatch between the preload write and the read command, §2.3) is recorded here rather than hidden: `K_alone`'s first attempt failed fast (2 samples, ~10 s) with repeated "Data returned was not validated" errors before the fix; the result reported in §3.3 is the corrected re-run.
