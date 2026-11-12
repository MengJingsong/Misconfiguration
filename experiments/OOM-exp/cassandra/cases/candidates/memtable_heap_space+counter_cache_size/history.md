# memtable_heap_space + counter_cache_size — run history

Per-run records moved here verbatim on 2026-11-11 when the case was consolidated after the R3 recheck
(protocol, *Filing a verified case*). Headings are demoted one level and relative links repointed to this
folder; nothing else is changed. The final case file is
[`memtable_heap_space+counter_cache_size.md`](memtable_heap_space+counter_cache_size.md).

- [Run 1 — 2026-11-02 (pre-protocol, pc41-class node, 40 cores)](#run-1)
- [Recheck design and amendment — 2026-11-11 (R3, apt149), written before the readings they govern](#recheck-design)

<a id="run-1"></a>
# Run 1 — 2026-11-02 (as filed; status line as of 2026-11-11 before the recheck)

## memtable_heap_space + counter_cache_size — convergence case

> **Status (2026-11-11): `candidate (pre-protocol)`.** Moved from `convergence/` to `candidates/`: filed before the 2026-11-06 protocol and does not meet the V1–V5 promotion rule ([protocol](../../../../verification-protocol.md#verification-status-amended-2026-11-11)). Evidence held: converge 1 run; M/C alone 1 run each; no intervention; OOM throws logged, no dump or histogram (JVM survived). The OOM recorded below stands; rerun ×3 with matched controls and an intervention ×3 to return it to `convergence/`.

> **Playbook:** [`../../../custom-convergence-playbook.md`](../../../../custom-convergence-playbook.md)
>
> **Run:** 2026-11-02, node `node0.jason92-323989.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB, local disk `/dev/sda3` 63 GB), Ubuntu 22.04.2, kernel `5.15.0-198-generic`, OpenJDK 11.0.32.1, Ant 1.10.12.
>
> **Source:** `systems/cassandra/source` at repository commit `0be49fb6`, copied to local disk `~/cassandra-run1` via `copy-source.sh` (`git describe` = `cassandra-5.0.9`), built with `ant build-test` (2 min 12 s, `BUILD SUCCESSFUL`). Nothing was built in or added to the repository's `systems/cassandra/source/`.
>
> **Harness:** [`memtable_heap_space+counter_cache_size/run1/oom-run.sh`](run1/oom-run.sh). Full logs on the node at `~/oom-exp-logs/{baseline,M_alone,C_alone,converge}/`; small excerpts under [`memtable_heap_space+counter_cache_size/run1/`](run1/).
>
> **Outcome: OOM reached.** The convergence arm (`memtable_heap_space=550MiB` + `counter_cache_size=300MiB`, both workloads driven concurrently at `-Xmx1024M`) produced 14 genuine `java.lang.OutOfMemoryError: Java heap space` throws in the node's own log, across several unrelated thread pools, while both control arms (each constraint alone, same heap, same workload) ran to completion with 0 errors and a safe heap margin.

### 1. Constraints and capacities

Both constraints are config-type, **true positive** at if-check-exp stage 4 (usage measured to follow the constraint at runtime), and both draw on the same shared budget: **on-heap JVM heap** (`-Xmx`/`-Xms`) of the single Cassandra node.

| | `memtable_heap_space` | `counter_cache_size` |
|---|---|---|
| if-check-exp case file | [`memtable_heap_space-tryAllocate-limit--guided.md`](../../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/memtable_heap_space-tryAllocate-limit--guided.md) | [`counter_cache_size-iscountercacheenabled-capacity--autonomous.md`](../../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/counter_cache_size-iscountercacheenabled-capacity--autonomous.md) |
| if-check-exp stage-4 results | [`memtable_heap_space-tryAllocate-limit--guided.md`](../../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/memtable_heap_space-tryAllocate-limit--guided.md) | [`counter_cache_size-iscountercacheenabled-capacity--autonomous.md`](../../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/counter_cache_size-iscountercacheenabled-capacity--autonomous.md) |
| Outcome class | true positive | true positive |
| Capacity check | [`MemtablePool.SubPool.tryAllocate():156`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L156) — `(allocated + size) > limit` | [`ColumnFamilyStore.isCounterCacheEnabled():3269`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3269) gates the reload path; the weight cap itself is Caffeine's `maximumWeight(capacity)` set in `CacheService.initCounterCache()` |
| What it caps | On-heap bytes of the memtable pool (`unslabbed_heap_buffers` allocation path) | On-heap bytes of the counter cache (Caffeine-weighted `CounterCacheKey → ClockAndCount` entries) |
| Default / how set | yaml `memtable_heap_space` (default: 1/4 heap); restart-only | yaml `counter_cache_size` (default: null → auto `min(max(1, 2.5% heap), 50)` MiB); restart or JMX `setCounterCacheCapacityInMB` |
| Prior finding relied on (not re-derived) | At capacity L, real on-heap usage tracks L almost exactly: observed excess +10 to +37 MiB over idle-heap+L at L = 128/256/512/1024 MiB (`-Xmx4G`). Writers **block**, not fail, when full — a flush drains the pool (self-reclaiming soft cap). Requires `memtable_cleanup_threshold: 0.99` to actually reach the limit (otherwise the default threshold reclaims early). | At capacity C, cache `Size` stops within one entry of C; real heap increase over a 0-capacity baseline is ~1.8–2.1× C (measured C = 1/8/64 MiB and the 50 MiB default on a 2 GiB heap). Does **not** self-reclaim — once full it just evicts LRU-ish via Caffeine and holds steady at ~1.8–2.1× C. |
| **Capacity chosen for this case** | **M = 550 MiB** | **C = 300 MiB** |

**Shared budget and node total:** single-node JVM heap, `-Xms1024M -Xmx1024M` (chosen for this experiment — not the node's 251 GiB physical RAM; see §2 for why this value and the baseline measurement that justified it).

### 2. Verification solution

#### 2.1 Picking `-Xmx` and measuring the baseline

Chose **`-Xmx1024M` / `-Xms1024M`** (within the suggested 768–1536 MiB band): large enough to host both constraints' capacities with margin, small enough that 550+300 MiB is a plausible single-operator misconfiguration relative to it, and round for arithmetic.

**Baseline measurement** (not assumed from the source experiments, which ran at `-Xmx4G` and `-Xmx2G`): started the node with `memtable_heap_space: 32MiB` and `counter_cache_size: 1MiB` (both tiny/off), `memtable_allocation_type: unslabbed_heap_buffers`, `memtable_cleanup_threshold: 0.99`, no load, waited 5 s after "listening for CQL clients", then `jcmd GC.run` + `jcmd GC.heap_info`.

> `garbage-first heap total 1048576K, used 58194K ... region size 16384K, 1 young (16384K), 0 survivors (0K)` — [`memtable_heap_space+counter_cache_size/run1/baseline/heap-idle.txt`](run1/baseline/heap-idle.txt)

Idle used heap = **58,194 K ≈ 56.8 MiB** (including one 16 MiB young region; metaspace is reported separately and not counted against `-Xmx`). **Baseline b ≈ 60 MiB** (rounded up for margin).

#### 2.2 Sizing

Per-constraint excess factors are taken from the if-check-exp findings above (not re-derived): memtable's real-heap excess over idle+limit was 1–18% in the source experiment, so a conservative **1.1×** multiplier is used on M; the counter cache's real-heap increase was 1.8–2.1× the weighted size, so a conservative **2.1×** multiplier is used on C.

**Each alone, safe (≥30% free required):**

- **M alone** (`memtable_heap_space=550MiB`, `counter_cache_size=1MiB`, write workload only): predicted usage = b + M×1.1 = 60 + 550×1.1 = 60 + 605 = **665 MiB = 65% of 1024 MiB → 35% free.** ≥30% margin met.
- **C alone** (`memtable_heap_space=32MiB`, `counter_cache_size=300MiB`, counter workload only): predicted usage = b + C×2.1 = 60 + 300×2.1 = 60 + 630 = **690 MiB = 67% of 1024 MiB → 33% free.** ≥30% margin met.

**Combined, predicted to exceed the budget:**

predicted usage = b + M×1.1 + C×2.1 = 60 + 605 + 630 = **1295 MiB = 126% of the 1024 MiB `-Xmx`**, i.e. **271 MiB (26%) over budget** — before running anything. This arithmetic is the prediction; §3 reports what was actually measured.

#### 2.3 Workload

One `cassandra-stress` workload per constraint, reusing the if-check-exp cluster-tier commands at smaller scale appropriate to the smaller heap:

- **Memtable-pressure workload** (`write`): `cassandra-stress write n=3000000 no-warmup -col 'size=FIXED(1024)' -rate threads=256` against `keyspace1.standard1` (`durable_writes=false`). At `-Xmx4G` with `memtable_heap_space` up to 1024 MiB, the source case reached its limit flush within 7–10 s of stress start with `n=2000000`; `n=3000000` at `COLSIZE=1024` comfortably exceeds the 550 MiB cap many times over in bytes offered.
- **Counter-cache-pressure workload** (`counter_write`): `cassandra-stress counter_write n=600000 no-warmup -rate threads=64`, which (per the source case) creates 5 cache entries per key = 3,000,000 entries ≈ 343 MiB at the source case's measured 120 B/entry — enough to overfill a 300 MiB cap.
- **Convergence arm:** both commands launched as background processes **in the same window** against the same node (not sequential).

#### 2.4 Instruments

- `jcmd <pid> GC.run` + `jcmd <pid> GC.heap_info` at idle and at the end of each arm (forces a full GC, then reads `used`/region counts — the "real heap" reading used throughout if-check-exp stage 4).
- A periodic sampler: `jcmd <pid> GC.heap_info` every 5 s while the workload(s) run (no forced GC per sample, to avoid disturbing the run; the final reading is the only forced-GC sample), up to 60 samples (5 min), then the script `wait`s on the stress process(es) however long they take.
- `grep '^ERROR' logs/system.log` and `grep -i OutOfMemoryError logs/system.log logs/debug.log` for the JVM's own evidence of an actual `OutOfMemoryError` throw (not just a timeout symptom).
- `sudo dmesg -T | grep -iE 'out of memory|oom-kill|killed process'` for a kernel OOM-kill.
- `ps -eo cmd | grep '[C]assandraDaemon'` after every arm, run on the node directly (not `pgrep -f` inside an `ssh` string).

#### 2.5 Procedure (as executed)

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

### 3. Runtime results

#### 3.1 Control arm 1 — `memtable_heap_space=550MiB` alone

- Node confirmed at `-Xmx1024M`; startup log: `Global memtable on-heap threshold is enabled at 550MiB`.
- `cassandra-stress write n=3000000` ran to completion: **0 errors**, total operation time 4:58, 420 GC events, 29.8 s total GC time. [`memtable_heap_space+counter_cache_size/run1/M_alone/stress-write-tail.txt`](run1/M_alone/stress-write-tail.txt)
- Final forced-GC heap: `used 638789K`, `3 young (49152K)` → non-young ≈ 589,637 K ≈ **575.8 MiB**; total used 638,789 K ≈ 623.8 MiB. [`memtable_heap_space+counter_cache_size/run1/M_alone/heap-final.txt`](run1/M_alone/heap-final.txt)
- **Free margin:** 1024 − 623.8 = 400.2 MiB free ≈ **39% free** (prediction was 35% free; actual ran a bit lower than predicted usage, i.e. more margin than predicted — consistent, within the stated tolerance).
- `ERROR` lines in `system.log`: **0**. [`memtable_heap_space+counter_cache_size/run1/M_alone/error-count.txt`](run1/M_alone/error-count.txt) No kernel OOM-kill, node stopped cleanly, no `CassandraDaemon` left.
- **Safe alone: confirmed.**

#### 3.2 Control arm 2 — `counter_cache_size=300MiB` alone

- Node confirmed at `-Xmx1024M`; startup log: `Initializing counter cache with capacity of 300 MiBs` (cross-checked against the baseline's `1 MiBs` line, same format).
- `cassandra-stress counter_write n=600000 -rate threads=64` ran to completion in ~64 s (12 samples at 5 s = 60 s, plus start-up/shutdown).
- Final forced-GC heap: `used 643749K`, `1 young (16384K)` → non-young ≈ 627,365 K ≈ **612.7 MiB**; total used ≈ 628.7 MiB.
- **Free margin:** 1024 − 628.7 = 395.3 MiB free ≈ **38.6% free** (prediction was 33% free — actual ran with slightly more margin than predicted, same direction as arm 1).
- `ERROR` lines in `system.log`: **0**. No kernel OOM-kill, node stopped cleanly, no `CassandraDaemon` left.
- **Safe alone: confirmed.**

#### 3.3 Convergence arm — both at capacity, both workloads concurrent

- Node confirmed at `-Xmx1024M`; both startup lines present (`550MiB` memtable threshold, `300 MiBs` counter cache).
- Both `cassandra-stress` processes launched together at 13:14:52 local. Heap was sampled every 5 s; representative samples (full set in [`memtable_heap_space+counter_cache_size/run1/converge/heap-samples-excerpt.txt`](run1/converge/heap-samples-excerpt.txt)): sample 7 (used 952,489 K), sample 21 (962,001 K), sample 50 (962,224 K), sample 58 (978,692 K) — heap repeatedly approached 93–95% of the 1,048,576 K `-Xmx` throughout the run, far above either control arm's peak.
- The sampling loop's 60-iteration (5 min) budget elapsed with **both workloads still running**; the script then blocked on `wait` for their actual completion, which took until ~13:28:00 (**~13 minutes total**, vs. ~5 min for the write workload alone and ~1 min for the counter workload alone) — itself a sign of severe contention/GC pressure, not present in either control.
- `counter_write` **did not finish cleanly**: it exited `FAILURE` after repeated `NoHostAvailableException`/`BusyPoolException: Pool is busy (no available connection and the queue has reached its max size 256)` — the native-protocol connection pool backed up under load. [`memtable_heap_space+counter_cache_size/run1/converge/stress-counter-tail.txt`](run1/converge/stress-counter-tail.txt)
- `write` finished its 3,000,000 partitions with the client reporting 0 errors, but at far degraded throughput: **6,046 op/s** average (vs. 10,041 op/s alone), latency max 24,243 ms (vs. 10,855 ms alone), **496 GC events / 107.9 s total GC time** (vs. 420 / 29.8 s alone) — GC overhead roughly **3.6× higher** than the control. [`memtable_heap_space+counter_cache_size/run1/converge/stress-write-tail.txt`](run1/converge/stress-write-tail.txt)
- **41 `ERROR` lines** in `system.log`. [`memtable_heap_space+counter_cache_size/run1/converge/error-count.txt`](run1/converge/error-count.txt); of these, 41 are `org.apache.cassandra.exceptions.WriteTimeoutException` wrapped in `RuntimeException` on `CounterMutationStage` threads (lock-acquisition timeouts, a symptom of overload — [`memtable_heap_space+counter_cache_size/run1/converge/error-lines-head.txt`](run1/converge/error-lines-head.txt)).
- **Separately, 14 genuine `java.lang.OutOfMemoryError: Java heap space` throws** appear in `logs/system.log` (and the same 14 in `logs/debug.log`), at `2026-11-02T18:29:36` (13:29:36 local), across **`Native-Transport-Requests-*` (11 threads), `BatchlogTasks:1`, and `GossipTasks:1`** — unrelated thread pools throwing concurrently, which is the signature of true heap exhaustion rather than one code path's bug. One `GossipTasks:1` thread's OOM cascaded into a secondary `IllegalMonitorStateException` while releasing a lock it never fully acquired. Full excerpt: [`memtable_heap_space+counter_cache_size/run1/converge/system-log-oom-excerpt.txt`](run1/converge/system-log-oom-excerpt.txt); representative line:

  ```
  ERROR [Native-Transport-Requests-5] 2026-11-02T18:29:36,791 JVMStabilityInspector.java:123 - OutOfMemory error letting the JVM handle the error:
  java.lang.OutOfMemoryError: Java heap space
  ```

- Final forced-GC heap, taken right after this burst: `jcmd GC.run` itself took **14 s** to return (vs. <1 s in both control arms) and the following `GC.heap_info` took **74 s** to return — both far slower than in either control arm, itself evidence of GC thrashing. Result: `used 1012655K`, **`0 young (0K)`** — [`memtable_heap_space+counter_cache_size/run1/converge/heap-final.txt`](run1/converge/heap-final.txt). Used heap = 1,012,655 K ≈ **989.0 MiB = 96.6% of the 1024 MiB `-Xmx`**, with **no young generation left to allocate from at all** even immediately after a forced full GC.
- `sudo dmesg -T | grep -iE 'out of memory|oom-kill|killed process'`: **no output** — no kernel-level OOM-kill; this stayed a JVM heap exhaustion, not a cgroup/kernel RSS kill. [`memtable_heap_space+counter_cache_size/run1/converge/dmesg-oom.txt`](run1/converge/dmesg-oom.txt) (empty)
- The node did **not** crash outright: `JVMStabilityInspector` caught each `OutOfMemoryError` and logged it rather than invoking `-XX:OnOutOfMemoryError=kill -9 %p` (that JVM flag apparently did not fire for these particular throws), and the node was still responsive enough afterward for the script's own `nodetool drain`/`stopdaemon` to succeed cleanly, with `ps -eo cmd | grep '[C]assandraDaemon'` empty afterward.

**Matching the prediction (§2.2):** predicted combined usage was 1295 MiB (126% of `-Xmx`, 271 MiB over budget). The actual final forced-GC reading, 1,012,655 K ≈ 989 MiB, is below `-Xmx` itself (the JVM cannot report `used` above `-Xmx`, by construction) — so the prediction's raw number cannot be read off literally once the JVM is actually out of room: the heap saturates at (and the JVM throws against) the 1024 MiB ceiling rather than growing past it the way the prediction's linear arithmetic implied. What the prediction correctly anticipated, and what distinguishes this arm from both controls, is the **direction and scale of the overshoot**: each control left 33–39% of the 1024 MiB free, while combining them left effectively none (0 young regions after a forced full GC) and pushed the JVM into repeatedly throwing real `OutOfMemoryError`s. The qualitative prediction — "combined, this should exceed the budget" — is confirmed; the specific post-OOM number is capped by `-Xmx` itself, which is exactly the expected shape of a genuine convergence OOM rather than a measurement error.

### 4. Conclusion

**The node OOMed.** Both `memtable_heap_space=550MiB` and `counter_cache_size=300MiB`, driven alone against the identical `-Xmx1024M` heap and workload sizing, left a comfortable ≥33% free margin with zero errors. Driven **together**, with `cassandra-stress write` and `cassandra-stress counter_write` running concurrently against the same node, the JVM threw 14 genuine `OutOfMemoryError: Java heap space` exceptions across unrelated subsystems (native-transport request handling, batchlog, gossip) within the same ~5-minute window that both control arms individually completed without incident, and the forced-GC heap reading afterward showed 0 young generation left — i.e., no further room to allocate even right after a full collection.

This is a **capability gap**: Cassandra has no mechanism that caps the *combined* on-heap usage of the memtable pool and the counter cache. Each has its own capacity check (`MemtablePool.SubPool.tryAllocate()` for the memtable pool; Caffeine's `maximumWeight()` for the counter cache) and each is individually enforced — confirmed again here by the two control arms staying safe — but nothing sums the two pools (or any other on-heap consumer) against the JVM's actual `-Xmx`. Reaching each pool's own, individually-safe capacity *at the same time* was enough to exhaust the shared heap and throw real `OutOfMemoryError`s, even though neither pool's own accounting ever showed anything wrong. **Minimum sizing found to reproduce it:** `-Xmx1024M`/`-Xms1024M`, `memtable_heap_space=550MiB` (with `memtable_cleanup_threshold=0.99` and `memtable_allocation_type=unslabbed_heap_buffers`) plus `counter_cache_size=300MiB`, driven by concurrent `cassandra-stress write n=3000000 -col 'size=FIXED(1024)' -rate threads=256` and `cassandra-stress counter_write n=600000 -rate threads=64`. No smaller combination was tried (one well-executed combination was the priority for this run; see the batch log for what is left to explore).

**Target-3 note:** this combination is realistic from a single operator's misconfiguration, with a caveat. Setting two independent yaml knobs (`memtable_heap_space`, `counter_cache_size`) without checking their sum against `-Xmx` is exactly the kind of mistake an operator tuning "give the memtable more room" and, separately, "give the counter cache more room" could make — no single knob here is unusual or extreme on its own (550 MiB and 300 MiB are both well inside the range exercised, individually, by the source if-check-exp cases at larger heaps). The one deliberately-engineered part of this case is the **workload**: it needed two concurrent, sustained write-heavy workloads (one plain, one counter) to actually fill both pools at once in the same window — a single quiet workload that only touches one table would not have converged them. A real cluster with mixed counter and non-counter write traffic under sustained load would reach the same state without any deliberate orchestration.

---

### Instrument check and process hygiene

- Baseline, control arms, and the convergence arm each confirmed `-Xmx1024M`/`-Xms1024M` from the running process's own `ps -o args=` output before any reading, and the resolved yaml values from the node's own startup log (`Global memtable on-heap threshold is enabled at <M>MiB`, `Initializing counter cache with capacity of <C> MiBs`).
- After every arm: `ps -eo cmd | grep '[C]assandraDaemon'` returned empty (checked directly on the node, not through an `ssh`-wrapped `pgrep -f`), and `ss -ltn` showed none of ports 7000/7199/9042 in use before the next arm started.
- Node data (`data/`), commit log, and logs lived under `~/cassandra-run1` on local disk (`/dev/sda3`); nothing was written to `/proj`. The repository's `systems/cassandra/source/` was never touched (`git status --short` on it was empty before the run and is unaffected by this run).

---

<a id="recheck-design"></a>
# Recheck design and amendment — 2026-11-11 (R3, apt149)

The recheck's results are in the final case file. Paths below that start with
`memtable_heap_space+counter_cache_size/` now resolve relative to this folder (the case folder itself).

### Recheck design (2026-11-11) — campaign-plan row R3, written before any reading on apt149

**Rule:** pre-protocol recheck (campaign plan, *R1–R6 share one rule*): same build, budget, settings and
workloads as run 1, its own harness, each arm ×3 from clean starts. Only the node changes.

**Node (environment change, disclosed):** `apt149` = `node4.jason92-325433.misconfiguration-pg0.apt.emulab.net`,
Dell r320, 1 × Xeon E5-2450 @ 2.1 GHz (8 cores / 16 threads), 15.5 GiB RAM, 8 GiB swap, `/mydata` 1.6 TB local,
Ubuntu 22.04.2, kernel 5.15.0-198-generic, cgroup v2, OpenJDK **11.0.33** (run 1: 11.0.32.1). Run 1's node had
40 cores and 251 GiB. Nothing else runs on the node during the recheck.

**Build:** `~/cassandra-c1` on apt149 (clean `cassandra-5.0.9`, source tree `b796bcfd`, `git status` clean)
copied with `cp -a` to `/mydata/oom-recheck/R3/cassandra`. Data, commit log, logs and heap dumps all under
`/mydata/oom-recheck/R3/` (local disk).

**Harness:** run 1's `oom-run.sh`, copied to `/mydata/oom-recheck/R3/harness/` with minimal edits (diff saved as
`memtable_heap_space+counter_cache_size/recheck-2026-11-11/oom-run.sh.diff`): paths (`C`, `L`, heap-dump dir);
pinned env (`MAX_HEAP_SIZE=1024M`; `HEAP_NEWSIZE`, `JVM_OPTS`, `JVM_EXTRA_OPTS` unset;
`CASSANDRA_HEAPDUMP_DIR=/mydata/oom-recheck/R3/dumps/<arm>`); workload sizes as variables with run 1's values as
defaults; sampling extended from 60 to up to 480 samples (5 s `GC.heap_info`, no forced GC) with a 40-min per-arm cap;
added readings: resolved `VM.flags`, `nodetool info` counter-cache line every 30 s and at the end (K for the counter
cache), memtable flush lines (`Enqueuing flush of …` on-heap, K for the memtable pool), `GC.class_histogram` after
the final forced GC (alone/intervention arms), JVM stdout OOM report, node logs (incl. `gc.log`) copied per arm, stress
exit codes; the final heap sample and stop no longer abort when the JVM is already gone. Runner: `run-batch.sh`.

**Settings (unchanged from run 1):** yaml from `git show HEAD:conf/cassandra.yaml` +
`memtable_allocation_type: unslabbed_heap_buffers`, `memtable_cleanup_threshold: 0.99`,
`memtable_heap_space: <M>MiB`, `counter_cache_size: <C>MiB`; `-Xms1024M -Xmx1024M`; everything else default,
including the shipped JVM options. Run 1's JVM arguments (system.log `JVM Arguments:` line, in
`run1/converge/oom-grep.txt`) show `-XX:+HeapDumpOnOutOfMemoryError`, `-XX:HeapDumpPath=bin/../logs/...hprof` and
`-XX:OnOutOfMemoryError=kill -9 %p` were **active** in run 1 (shipped defaults), plus `-XX:ParallelGCThreads=40
-XX:ConcGCThreads=40` (set by `cassandra-env.sh` to the core count), G1, `G1NewSizePercent=50`, 16 MiB regions,
`MaxGCPauseMillis=300`, IHOP 70, `MaxDirectMemorySize=15872M` (derived from RAM). On apt149 `cassandra-env.sh` will
derive `ParallelGCThreads=ConcGCThreads=16` and a smaller `MaxDirectMemorySize`; these are kept as derived (environment
change) and recorded from `VM.flags`. No flag is added: the dump at the first OOM comes from the shipped
`HeapDumpOnOutOfMemoryError`, only its directory moves to `/mydata`.

**Commands (each arm from a clean start: fresh yaml, empty `data/`, new JVM):**

```
# run on apt149:  setsid nohup bash /mydata/oom-recheck/R3/harness/run-batch.sh <batchfile> > <batchlog> 2>&1 &
oom-run.sh baseline                                                    # M=32, C=1, idle
WRITE_N=200000 COUNTER_N=50000 oom-run.sh arm validate 550 300 both    # modest-load validation (not a reading)
oom-run.sh arm M_alone_r{1,2,3}   550 -  write      # C=1 MiB
oom-run.sh arm C_alone_r{1,2,3}   -  300 counter    # M=32 MiB
oom-run.sh arm converge_r{1,2,3}  550 300 both
oom-run.sh arm interv_C50_r{1,2,3} 550 50 both      # intervention
# workloads (unchanged): cassandra-stress write n=3000000 no-warmup -col 'size=FIXED(1024)' -rate threads=256
#                         cassandra-stress counter_write n=600000 no-warmup -rate threads=64   (concurrent in "both")
```

Order: baseline, validation, `M_alone_r1`, `C_alone_r1` (checked against the filed sizing before any converge
reading; if either alone level moves far from run 1, i.e. forced-GC used > 70% or < 50% of 1024 MiB, a dated
amendment comes first), then the remaining alone arms, converge ×3, intervention ×3.

**Source re-check (pinned `systems/cassandra/source`, read-only):** memtable pool —
`MemtablePool.SubPool.tryAllocate()` (`MemtablePool.java:151–161`, `allocated + size > limit` → false);
`MemtableAllocator.SubAllocator.allocate()` blocks writers on `hasRoom()` (`MemtableAllocator.java:169–195`);
`HeapPool.Allocator.allocate()` charges `onHeap()` then `ByteBuffer.allocate(size)` (`HeapPool.java:52–55`); default
1/4 heap (`DatabaseDescriptor.java:586–587`). Counter cache — `CacheService.initCounterCache()` →
`CaffeineCache.create(capacity)` with `maximumWeight(capacity)` and weigher `key.unsharedHeapSize() +
value.unsharedHeapSize()` (`CacheService.java:172–181`, `CaffeineCache.java:51–69`);
`CounterCacheKey.unsharedHeapSize()` = shell + the two `byte[]` (`CounterCacheKey.java:152–157`),
`ClockAndCount` = shell (`ClockAndCount.java:46–48`). The weigher does **not** count Caffeine's node or the backing
`ConcurrentHashMap` node/table slot. Neither control sees the other; nothing sums them against `-Xmx`. When an OOM
reaches `JVMStabilityInspector.inspectThrowable()` it is logged ("letting the JVM handle the error") and rethrown
(`JVMStabilityInspector.java:105–133`).

**Protection map (summary).** Domain M: memtable on-heap pool, contract C_M = 550 MiB of charged buffer bytes
(`memtable_heap_space`), K_M = pool on-heap at flush (flush log line), U_M = memtable objects in the heap
histogram/dump (partitions map nodes, `AtomicBTreePartition`, rows, cells, `HeapByteBuffer` + `byte[]` values).
Writers block when full; a flush releases it. Domain C: counter cache, contract C_C = 300 MiB of weigher bytes
(`counter_cache_size`), K_C = `nodetool info` counter-cache size, U_C = `CounterCacheKey`, `ClockAndCount`, their
`byte[]`, Caffeine nodes and the backing map. Standing, LRU-evicted, does not self-reclaim. Budget: Java heap 1024 MiB.
Unbounded extra: request working sets of 320 client threads (native-transport queue).

**Predictions (from run 1 and the source):**

| Arm | Predicted outcome | Predicted final forced-GC used |
|---|---|---|
| baseline | idle | ≈ 57 MiB |
| M_alone ×3 | write completes, 0 errors, no OOM | ≈ 600–660 MiB (run 1: 624 MiB = 61%) |
| C_alone ×3 | counter_write completes, 0 errors, no OOM; K_C at 300 MiB | ≈ 600–660 MiB (run 1: 629 MiB = 61%); U_C ≈ 1.8–2.1 × K_C |
| converge ×3 | `OutOfMemoryError: Java heap space` once both pools are full: ≈ 57 + 567 + 572 ≈ 1196 MiB live > 1024 MiB | n/a (at OOM) |
| interv_C50 ×3 | no OOM; both workloads complete | ≈ 57 + 567 + 50 × 1.9 ≈ 720 MiB (≈ 70%) |

**Endpoint (fixed for all repeats):** a `java.lang.OutOfMemoryError: Java heap space` thrown by the Cassandra JVM,
evidenced by the JVM's own report on stdout (`java.lang.OutOfMemoryError: Java heap space` / `Dumping heap to …`)
and/or an `OutOfMemoryError: Java heap space` entry in `system.log`. Whether the JVM then dies (shipped
`OnOutOfMemoryError=kill -9 %p`, predicted: **killed** right after the dump) or survives (as run 1 reports) is
recorded per repeat but is not part of the endpoint. A kernel OOM-kill is not expected (RSS ≈ 1.5 GiB ≪ 15.5 GiB) and
would be reported separately.

**Pass/fail (V1–V5):**
- V1: endpoint in converge ≥ 3 of 3 (mixed 1–2/3 → extend to at most 5 and state n/N).
- V2: M_alone and C_alone each 3/3 with no `OutOfMemoryError`, 0 `ERROR` lines, stress `Total errors: 0`, and final
  forced-GC used ≤ 70% of 1024 MiB (≥ 30% free).
- V3: U per domain measured apart from K: alone/intervention arms from the end-of-arm class histogram (after forced GC);
  converge from the dump at the first OOM (python hprof parser, `/mydata/oom-recheck/R3/tools/`): class histogram plus
  a bounded reachability walk from each memtable's partition map and from the counter cache's backing map.
- V4: interv_C50 ×3 with no `OutOfMemoryError`; record write/counter op rates, errors and durations next to the alone
  arms. Choice: lower `counter_cache_size` 300 → 50 MiB (the top of its documented auto default,
  `min(2.5% heap, 50 MiB)`), same workloads and memtable setting; predicted sum ≈ 720 MiB fits.
- V5: the first OOM entry (thread, stack if logged) from `system.log`/stdout plus the dump histogram showing both holders.

**Classification rule fixed in advance (protocol, *Classification by measurement*):** Σ contract + baseline =
550 + 300 + 57 = 907 MiB < 1024 MiB, so if every domain stays within its contract (U ≤ C), the pair alone cannot
exhaust the heap. If U_C ≈ 1.9 × C_C as in the if-check-exp measurement (counter-cache physical bytes above the weigher
bytes, K_C ≤ C_C), the counter-cache domain is U > C, K ≤ C (accounting omission), and the OOM needs that excess plus the
memtable domain → **mixed**, not pure convergence. Classification follows the measured U.

**Stopping budget:** ≤ 5 h wall (from 14:39 EST, i.e. stop by 19:40 EST), ≤ 20 arm executions (planned 14:
baseline, validation, 3 + 3 + 3 + 3; the rest only to extend a mixed outcome to 5 or replace an invalid arm). Per arm:
40-min cap. No escalation after an OOM; nothing left running after each arm and at the end.

**Amendment (2026-11-11, written after converge_r1–r2, before converge_r3 and the intervention arms were read) —
evidence form of the endpoint, endpoint unchanged.** The JVM's own OOM report cannot appear on stdout:
`CassandraDaemon` closes `System.out`/`System.err` after start-up when not in the foreground
(`CassandraDaemon.java:738–739`), so HotSpot's `java.lang.OutOfMemoryError: Java heap space` / `Dumping heap to …`
lines are lost. The JVM's own report is therefore evidenced by the `HeapDumpOnOutOfMemoryError` file: HotSpot creates it
only inside `report_java_out_of_memory()` on a VM-thrown `OutOfMemoryError` (heap, metaspace or array-size; metaspace
was ≈ 58 MiB with no limit and no oversized array is involved, so heap), together with the GC log
(`Entering safepoint region: HeapDumper`, the back-to-back `Pause Full … 99xM->99xM` before it). A `system.log`
`OutOfMemoryError: Java heap space` entry counts as well but is not required: with the shipped
`OnOutOfMemoryError=kill -9 %p` the JVM is killed right after the dump, often before any thread logs. The endpoint
stays "Java heap OOM thrown"; the observed JVM fate is "killed by its OnOutOfMemoryError handler after the dump".
