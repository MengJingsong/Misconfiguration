# memtable_heap_space + counter_cache_size — convergence case

> **Playbook:** [`../../../convergence-playbook.md`](../../../convergence-playbook.md)
>
> **Run:** 2026-11-02, node `node0.jason92-323989.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB, local disk `/dev/sda3` 63 GB), Ubuntu 22.04.2, kernel `5.15.0-198-generic`, OpenJDK 11.0.32.1, Ant 1.10.12.
>
> **Source:** `systems/cassandra/source` at repository commit `0be49fb6`, copied to local disk `~/cassandra-run1` via `copy-source.sh` (`git describe` = `cassandra-5.0.9`), built with `ant build-test` (2 min 12 s, `BUILD SUCCESSFUL`). Nothing was built in or added to the repository's `systems/cassandra/source/`.
>
> **Harness:** [`memtable_heap_space+counter_cache_size/run1/oom-run.sh`](memtable_heap_space+counter_cache_size/run1/oom-run.sh). Full logs on the node at `~/oom-exp-logs/{baseline,M_alone,C_alone,converge}/`; small excerpts under [`memtable_heap_space+counter_cache_size/run1/`](memtable_heap_space+counter_cache_size/run1/).
>
> **Outcome: OOM reached.** The convergence arm (`memtable_heap_space=550MiB` + `counter_cache_size=300MiB`, both workloads driven concurrently at `-Xmx1024M`) produced 14 genuine `java.lang.OutOfMemoryError: Java heap space` throws in the node's own log, across several unrelated thread pools, while both control arms (each constraint alone, same heap, same workload) ran to completion with 0 errors and a safe heap margin.

## 1. Constraints and capacities

Both constraints are config-type, **true positive** at if-check-exp stage 4 (usage measured to follow the constraint at runtime), and both draw on the same shared budget: **on-heap JVM heap** (`-Xmx`/`-Xms`) of the single Cassandra node.

| | `memtable_heap_space` | `counter_cache_size` |
|---|---|---|
| if-check-exp case file | [`memtable_heap_space-tryAllocate-limit--guided.md`](../../../../if-check-exp/cassandra/stage3-ai-deep-read/cases/memtable_heap_space-tryAllocate-limit--guided.md) | [`counter_cache_size-iscountercacheenabled-capacity--autonomous.md`](../../../../if-check-exp/cassandra/stage3-ai-deep-read/cases/counter_cache_size-iscountercacheenabled-capacity--autonomous.md) |
| if-check-exp stage-4 results | [`memtable_heap_space-tryAllocate-limit--guided.md`](../../../../if-check-exp/cassandra/stage4-runtime-verification/results/memtable_heap_space-tryAllocate-limit--guided.md) | [`counter_cache_size-iscountercacheenabled-capacity--autonomous.md`](../../../../if-check-exp/cassandra/stage4-runtime-verification/results/counter_cache_size-iscountercacheenabled-capacity--autonomous.md) |
| Outcome class | true positive | true positive |
| Capacity check | [`MemtablePool.SubPool.tryAllocate():156`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L156) — `(allocated + size) > limit` | [`ColumnFamilyStore.isCounterCacheEnabled():3269`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3269) gates the reload path; the weight cap itself is Caffeine's `maximumWeight(capacity)` set in `CacheService.initCounterCache()` |
| What it caps | On-heap bytes of the memtable pool (`unslabbed_heap_buffers` allocation path) | On-heap bytes of the counter cache (Caffeine-weighted `CounterCacheKey → ClockAndCount` entries) |
| Default / how set | yaml `memtable_heap_space` (default: 1/4 heap); restart-only | yaml `counter_cache_size` (default: null → auto `min(max(1, 2.5% heap), 50)` MiB); restart or JMX `setCounterCacheCapacityInMB` |
| Prior finding relied on (not re-derived) | At capacity L, real on-heap usage tracks L almost exactly: observed excess +10 to +37 MiB over idle-heap+L at L = 128/256/512/1024 MiB (`-Xmx4G`). Writers **block**, not fail, when full — a flush drains the pool (self-reclaiming soft cap). Requires `memtable_cleanup_threshold: 0.99` to actually reach the limit (otherwise the default threshold reclaims early). | At capacity C, cache `Size` stops within one entry of C; real heap increase over a 0-capacity baseline is ~1.8–2.1× C (measured C = 1/8/64 MiB and the 50 MiB default on a 2 GiB heap). Does **not** self-reclaim — once full it just evicts LRU-ish via Caffeine and holds steady at ~1.8–2.1× C. |
| **Capacity chosen for this case** | **M = 550 MiB** | **C = 300 MiB** |

**Shared budget and node total:** single-node JVM heap, `-Xms1024M -Xmx1024M` (chosen for this experiment — not the node's 251 GiB physical RAM; see §2 for why this value and the baseline measurement that justified it).

## 2. Verification solution

### 2.1 Picking `-Xmx` and measuring the baseline

Chose **`-Xmx1024M` / `-Xms1024M`** (within the suggested 768–1536 MiB band): large enough to host both constraints' capacities with margin, small enough that 550+300 MiB is a plausible single-operator misconfiguration relative to it, and round for arithmetic.

**Baseline measurement** (not assumed from the source experiments, which ran at `-Xmx4G` and `-Xmx2G`): started the node with `memtable_heap_space: 32MiB` and `counter_cache_size: 1MiB` (both tiny/off), `memtable_allocation_type: unslabbed_heap_buffers`, `memtable_cleanup_threshold: 0.99`, no load, waited 5 s after "listening for CQL clients", then `jcmd GC.run` + `jcmd GC.heap_info`.

> `garbage-first heap total 1048576K, used 58194K ... region size 16384K, 1 young (16384K), 0 survivors (0K)` — [`memtable_heap_space+counter_cache_size/run1/baseline/heap-idle.txt`](memtable_heap_space+counter_cache_size/run1/baseline/heap-idle.txt)

Idle used heap = **58,194 K ≈ 56.8 MiB** (including one 16 MiB young region; metaspace is reported separately and not counted against `-Xmx`). **Baseline b ≈ 60 MiB** (rounded up for margin).

### 2.2 Sizing

Per-constraint excess factors are taken from the if-check-exp findings above (not re-derived): memtable's real-heap excess over idle+limit was 1–18% in the source experiment, so a conservative **1.1×** multiplier is used on M; the counter cache's real-heap increase was 1.8–2.1× the weighted size, so a conservative **2.1×** multiplier is used on C.

**Each alone, safe (≥30% free required):**

- **M alone** (`memtable_heap_space=550MiB`, `counter_cache_size=1MiB`, write workload only): predicted usage = b + M×1.1 = 60 + 550×1.1 = 60 + 605 = **665 MiB = 65% of 1024 MiB → 35% free.** ≥30% margin met.
- **C alone** (`memtable_heap_space=32MiB`, `counter_cache_size=300MiB`, counter workload only): predicted usage = b + C×2.1 = 60 + 300×2.1 = 60 + 630 = **690 MiB = 67% of 1024 MiB → 33% free.** ≥30% margin met.

**Combined, predicted to exceed the budget:**

predicted usage = b + M×1.1 + C×2.1 = 60 + 605 + 630 = **1295 MiB = 126% of the 1024 MiB `-Xmx`**, i.e. **271 MiB (26%) over budget** — before running anything. This arithmetic is the prediction; §3 reports what was actually measured.

### 2.3 Workload

One `cassandra-stress` workload per constraint, reusing the if-check-exp cluster-tier commands at smaller scale appropriate to the smaller heap:

- **Memtable-pressure workload** (`write`): `cassandra-stress write n=3000000 no-warmup -col 'size=FIXED(1024)' -rate threads=256` against `keyspace1.standard1` (`durable_writes=false`). At `-Xmx4G` with `memtable_heap_space` up to 1024 MiB, the source case reached its limit flush within 7–10 s of stress start with `n=2000000`; `n=3000000` at `COLSIZE=1024` comfortably exceeds the 550 MiB cap many times over in bytes offered.
- **Counter-cache-pressure workload** (`counter_write`): `cassandra-stress counter_write n=600000 no-warmup -rate threads=64`, which (per the source case) creates 5 cache entries per key = 3,000,000 entries ≈ 343 MiB at the source case's measured 120 B/entry — enough to overfill a 300 MiB cap.
- **Convergence arm:** both commands launched as background processes **in the same window** against the same node (not sequential).

### 2.4 Instruments

- `jcmd <pid> GC.run` + `jcmd <pid> GC.heap_info` at idle and at the end of each arm (forces a full GC, then reads `used`/region counts — the "real heap" reading used throughout if-check-exp stage 4).
- A periodic sampler: `jcmd <pid> GC.heap_info` every 5 s while the workload(s) run (no forced GC per sample, to avoid disturbing the run; the final reading is the only forced-GC sample), up to 60 samples (5 min), then the script `wait`s on the stress process(es) however long they take.
- `grep '^ERROR' logs/system.log` and `grep -i OutOfMemoryError logs/system.log logs/debug.log` for the JVM's own evidence of an actual `OutOfMemoryError` throw (not just a timeout symptom).
- `sudo dmesg -T | grep -iE 'out of memory|oom-kill|killed process'` for a kernel OOM-kill.
- `ps -eo cmd | grep '[C]assandraDaemon'` after every arm, run on the node directly (not `pgrep -f` inside an `ssh` string).

### 2.5 Procedure (as executed)

```
# baseline (§2.1): memtable_heap_space=32MiB, counter_cache_size=1MiB, no load
oom-run.sh baseline

# control arm 1: M alone
oom-run.sh arm M_alone 550 -   write     # "-" = tiny default (counter_cache_size=1MiB)

# control arm 2: C alone
oom-run.sh arm C_alone  -  300 counter   # "-" = tiny default (memtable_heap_space=32MiB)

# convergence arm: both together, both workloads concurrent
oom-run.sh arm converge 550 300 both
```

Each arm: fresh `conf/cassandra.yaml` from the pinned tag + the stated edits, clean `data/`, start the node, confirm `-Xmx1024M` from the running process's own args, confirm the resolved on-heap/counter-cache values from the startup log, idle heap sample, launch the workload(s) in the background, sample heap every 5 s until both requested workloads exit (or 5 min, whichever is later — the script then blocks on `wait` for the actual workload exit), final forced-GC heap sample, log/dmesg/process checks, stop the node (`nodetool drain` then `stopdaemon`, SIGKILL fallback), verify no `CassandraDaemon` process remains.

## 3. Runtime results

### 3.1 Control arm 1 — `memtable_heap_space=550MiB` alone

- Node confirmed at `-Xmx1024M`; startup log: `Global memtable on-heap threshold is enabled at 550MiB`.
- `cassandra-stress write n=3000000` ran to completion: **0 errors**, total operation time 4:58, 420 GC events, 29.8 s total GC time. [`memtable_heap_space+counter_cache_size/run1/M_alone/stress-write-tail.txt`](memtable_heap_space+counter_cache_size/run1/M_alone/stress-write-tail.txt)
- Final forced-GC heap: `used 638789K`, `3 young (49152K)` → non-young ≈ 589,637 K ≈ **575.8 MiB**; total used 638,789 K ≈ 623.8 MiB. [`memtable_heap_space+counter_cache_size/run1/M_alone/heap-final.txt`](memtable_heap_space+counter_cache_size/run1/M_alone/heap-final.txt)
- **Free margin:** 1024 − 623.8 = 400.2 MiB free ≈ **39% free** (prediction was 35% free; actual ran a bit lower than predicted usage, i.e. more margin than predicted — consistent, within the stated tolerance).
- `ERROR` lines in `system.log`: **0**. [`memtable_heap_space+counter_cache_size/run1/M_alone/error-count.txt`](memtable_heap_space+counter_cache_size/run1/M_alone/error-count.txt) No kernel OOM-kill, node stopped cleanly, no `CassandraDaemon` left.
- **Safe alone: confirmed.**

### 3.2 Control arm 2 — `counter_cache_size=300MiB` alone

- Node confirmed at `-Xmx1024M`; startup log: `Initializing counter cache with capacity of 300 MiBs` (cross-checked against the baseline's `1 MiBs` line, same format).
- `cassandra-stress counter_write n=600000 -rate threads=64` ran to completion in ~64 s (12 samples at 5 s = 60 s, plus start-up/shutdown).
- Final forced-GC heap: `used 643749K`, `1 young (16384K)` → non-young ≈ 627,365 K ≈ **612.7 MiB**; total used ≈ 628.7 MiB.
- **Free margin:** 1024 − 628.7 = 395.3 MiB free ≈ **38.6% free** (prediction was 33% free — actual ran with slightly more margin than predicted, same direction as arm 1).
- `ERROR` lines in `system.log`: **0**. No kernel OOM-kill, node stopped cleanly, no `CassandraDaemon` left.
- **Safe alone: confirmed.**

### 3.3 Convergence arm — both at capacity, both workloads concurrent

- Node confirmed at `-Xmx1024M`; both startup lines present (`550MiB` memtable threshold, `300 MiBs` counter cache).
- Both `cassandra-stress` processes launched together at 13:14:52 local. Heap was sampled every 5 s; representative samples (full set in [`memtable_heap_space+counter_cache_size/run1/converge/heap-samples-excerpt.txt`](memtable_heap_space+counter_cache_size/run1/converge/heap-samples-excerpt.txt)): sample 7 (used 952,489 K), sample 21 (962,001 K), sample 50 (962,224 K), sample 58 (978,692 K) — heap repeatedly approached 93–95% of the 1,048,576 K `-Xmx` throughout the run, far above either control arm's peak.
- The sampling loop's 60-iteration (5 min) budget elapsed with **both workloads still running**; the script then blocked on `wait` for their actual completion, which took until ~13:28:00 (**~13 minutes total**, vs. ~5 min for the write workload alone and ~1 min for the counter workload alone) — itself a sign of severe contention/GC pressure, not present in either control.
- `counter_write` **did not finish cleanly**: it exited `FAILURE` after repeated `NoHostAvailableException`/`BusyPoolException: Pool is busy (no available connection and the queue has reached its max size 256)` — the native-protocol connection pool backed up under load. [`memtable_heap_space+counter_cache_size/run1/converge/stress-counter-tail.txt`](memtable_heap_space+counter_cache_size/run1/converge/stress-counter-tail.txt)
- `write` finished its 3,000,000 partitions with the client reporting 0 errors, but at far degraded throughput: **6,046 op/s** average (vs. 10,041 op/s alone), latency max 24,243 ms (vs. 10,855 ms alone), **496 GC events / 107.9 s total GC time** (vs. 420 / 29.8 s alone) — GC overhead roughly **3.6× higher** than the control. [`memtable_heap_space+counter_cache_size/run1/converge/stress-write-tail.txt`](memtable_heap_space+counter_cache_size/run1/converge/stress-write-tail.txt)
- **41 `ERROR` lines** in `system.log`. [`memtable_heap_space+counter_cache_size/run1/converge/error-count.txt`](memtable_heap_space+counter_cache_size/run1/converge/error-count.txt); of these, 41 are `org.apache.cassandra.exceptions.WriteTimeoutException` wrapped in `RuntimeException` on `CounterMutationStage` threads (lock-acquisition timeouts, a symptom of overload — [`memtable_heap_space+counter_cache_size/run1/converge/error-lines-head.txt`](memtable_heap_space+counter_cache_size/run1/converge/error-lines-head.txt)).
- **Separately, 14 genuine `java.lang.OutOfMemoryError: Java heap space` throws** appear in `logs/system.log` (and the same 14 in `logs/debug.log`), at `2026-11-02T18:29:36` (13:29:36 local), across **`Native-Transport-Requests-*` (11 threads), `BatchlogTasks:1`, and `GossipTasks:1`** — unrelated thread pools throwing concurrently, which is the signature of true heap exhaustion rather than one code path's bug. One `GossipTasks:1` thread's OOM cascaded into a secondary `IllegalMonitorStateException` while releasing a lock it never fully acquired. Full excerpt: [`memtable_heap_space+counter_cache_size/run1/converge/system-log-oom-excerpt.txt`](memtable_heap_space+counter_cache_size/run1/converge/system-log-oom-excerpt.txt); representative line:

  ```
  ERROR [Native-Transport-Requests-5] 2026-11-02T18:29:36,791 JVMStabilityInspector.java:123 - OutOfMemory error letting the JVM handle the error:
  java.lang.OutOfMemoryError: Java heap space
  ```

- Final forced-GC heap, taken right after this burst: `jcmd GC.run` itself took **14 s** to return (vs. <1 s in both control arms) and the following `GC.heap_info` took **74 s** to return — both far slower than in either control arm, itself evidence of GC thrashing. Result: `used 1012655K`, **`0 young (0K)`** — [`memtable_heap_space+counter_cache_size/run1/converge/heap-final.txt`](memtable_heap_space+counter_cache_size/run1/converge/heap-final.txt). Used heap = 1,012,655 K ≈ **989.0 MiB = 96.6% of the 1024 MiB `-Xmx`**, with **no young generation left to allocate from at all** even immediately after a forced full GC.
- `sudo dmesg -T | grep -iE 'out of memory|oom-kill|killed process'`: **no output** — no kernel-level OOM-kill; this stayed a JVM heap exhaustion, not a cgroup/kernel RSS kill. [`memtable_heap_space+counter_cache_size/run1/converge/dmesg-oom.txt`](memtable_heap_space+counter_cache_size/run1/converge/dmesg-oom.txt) (empty)
- The node did **not** crash outright: `JVMStabilityInspector` caught each `OutOfMemoryError` and logged it rather than invoking `-XX:OnOutOfMemoryError=kill -9 %p` (that JVM flag apparently did not fire for these particular throws), and the node was still responsive enough afterward for the script's own `nodetool drain`/`stopdaemon` to succeed cleanly, with `ps -eo cmd | grep '[C]assandraDaemon'` empty afterward.

**Matching the prediction (§2.2):** predicted combined usage was 1295 MiB (126% of `-Xmx`, 271 MiB over budget). The actual final forced-GC reading, 1,012,655 K ≈ 989 MiB, is below `-Xmx` itself (the JVM cannot report `used` above `-Xmx`, by construction) — so the prediction's raw number cannot be read off literally once the JVM is actually out of room: the heap saturates at (and the JVM throws against) the 1024 MiB ceiling rather than growing past it the way the prediction's linear arithmetic implied. What the prediction correctly anticipated, and what distinguishes this arm from both controls, is the **direction and scale of the overshoot**: each control left 33–39% of the 1024 MiB free, while combining them left effectively none (0 young regions after a forced full GC) and pushed the JVM into repeatedly throwing real `OutOfMemoryError`s. The qualitative prediction — "combined, this should exceed the budget" — is confirmed; the specific post-OOM number is capped by `-Xmx` itself, which is exactly the expected shape of a genuine convergence OOM rather than a measurement error.

## 4. Conclusion

**The node OOMed.** Both `memtable_heap_space=550MiB` and `counter_cache_size=300MiB`, driven alone against the identical `-Xmx1024M` heap and workload sizing, left a comfortable ≥33% free margin with zero errors. Driven **together**, with `cassandra-stress write` and `cassandra-stress counter_write` running concurrently against the same node, the JVM threw 14 genuine `OutOfMemoryError: Java heap space` exceptions across unrelated subsystems (native-transport request handling, batchlog, gossip) within the same ~5-minute window that both control arms individually completed without incident, and the forced-GC heap reading afterward showed 0 young generation left — i.e., no further room to allocate even right after a full collection.

This is a **capability gap**: Cassandra has no mechanism that caps the *combined* on-heap usage of the memtable pool and the counter cache. Each has its own capacity check (`MemtablePool.SubPool.tryAllocate()` for the memtable pool; Caffeine's `maximumWeight()` for the counter cache) and each is individually enforced — confirmed again here by the two control arms staying safe — but nothing sums the two pools (or any other on-heap consumer) against the JVM's actual `-Xmx`. Reaching each pool's own, individually-safe capacity *at the same time* was enough to exhaust the shared heap and throw real `OutOfMemoryError`s, even though neither pool's own accounting ever showed anything wrong. **Minimum sizing found to reproduce it:** `-Xmx1024M`/`-Xms1024M`, `memtable_heap_space=550MiB` (with `memtable_cleanup_threshold=0.99` and `memtable_allocation_type=unslabbed_heap_buffers`) plus `counter_cache_size=300MiB`, driven by concurrent `cassandra-stress write n=3000000 -col 'size=FIXED(1024)' -rate threads=256` and `cassandra-stress counter_write n=600000 -rate threads=64`. No smaller combination was tried (one well-executed combination was the priority for this run; see the batch log for what is left to explore).

**Target-3 note:** this combination is realistic from a single operator's misconfiguration, with a caveat. Setting two independent yaml knobs (`memtable_heap_space`, `counter_cache_size`) without checking their sum against `-Xmx` is exactly the kind of mistake an operator tuning "give the memtable more room" and, separately, "give the counter cache more room" could make — no single knob here is unusual or extreme on its own (550 MiB and 300 MiB are both well inside the range exercised, individually, by the source if-check-exp cases at larger heaps). The one deliberately-engineered part of this case is the **workload**: it needed two concurrent, sustained write-heavy workloads (one plain, one counter) to actually fill both pools at once in the same window — a single quiet workload that only touches one table would not have converged them. A real cluster with mixed counter and non-counter write traffic under sustained load would reach the same state without any deliberate orchestration.

---

## Instrument check and process hygiene

- Baseline, control arms, and the convergence arm each confirmed `-Xmx1024M`/`-Xms1024M` from the running process's own `ps -o args=` output before any reading, and the resolved yaml values from the node's own startup log (`Global memtable on-heap threshold is enabled at <M>MiB`, `Initializing counter cache with capacity of <C> MiBs`).
- After every arm: `ps -eo cmd | grep '[C]assandraDaemon'` returned empty (checked directly on the node, not through an `ssh`-wrapped `pgrep -f`), and `ss -ltn` showed none of ports 7000/7199/9042 in use before the next arm started.
- Node data (`data/`), commit log, and logs lived under `~/cassandra-run1` on local disk (`/dev/sda3`); nothing was written to `/proj`. The repository's `systems/cassandra/source/` was never touched (`git status --short` on it was empty before the run and is unaffected by this run).
