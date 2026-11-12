# memtable_heap_space + counter_cache_size + key_cache_size — three on-heap pools exhaust a 1 GiB heap; the two caches hold ≈ 1.7–2× their configured size

**Direction:** mixed — convergence of three on-heap pools, with an accounting-omission excess (U > C, K ≤ C) in the counter and key caches that the OOM needs. **Regime:** custom capacities. **Source:** Cassandra 5.0.9 (git tree `b796bcfd…`), single node. **Runs:** run 2 of the 2026-11-02 custom-convergence batch (pc41, 1 failing run; [`history.md`](history.md#run-1)) and the R4 recheck (2026-11-11, apt179, this file §2–§3). **Consolidated:** 2026-11-11.

| Condition | Status (protocol *Verification status*) |
|---|---|
| `memtable_heap_space=350MiB` + `counter_cache_size=250MiB` + `key_cache_size=200MiB`, `-Xmx1024M`, concurrent `write` + `counter_write` + `read` over 500,000 preloaded partitions | **`verified-OOM · diagnostic`** (converge 3/3 OOM; controls 9/9 survive; counter-cache intervention 3/3 survive) |

## Summary

- **Conclusion:** with the memtable pool, counter cache and key cache set to 350, 250 and 200 MiB on a 1 GiB heap, three concurrent workloads (writes, counter writes, reads) drive the heap to ≈ 97 % live and the JVM dies of `OutOfMemoryError: Java heap space` (heap dump written, `-XX:OnOutOfMemoryError=kill -9 %p` kills it) in **3/3** runs, 6.5–15.5 min after the workloads start. Each pool driven alone with its own workload ends at 15–57 % of the heap with 0 errors (3/3 each). Setting `counter_cache_size` back to its default (25 MiB) removes the OOM: no OOM in 3/3, all workloads complete (live heap peaks ≈ 745 MiB), though the node still spends 24–37 % of its time in GC pauses. The budget is a deliberately small diagnostic heap, and the workload is engineered to fill all three pools at once.
- **Root cause:** each control works locally (the memtable pool stops at its 350 MiB limit; neither cache reaches its weight cap), but nothing bounds their sum against the heap, and the two Caffeine caches undercount themselves. Their weigher charges only the key and value objects (`unsharedHeapSize()`), not the Caffeine node, the `ConcurrentHashMap` node and table slot, or the frequency sketch, so a cache really occupies ≈ 1.74× (counter) and ≈ 2.0× (key) the weight it reports. At the OOM the counter cache held ≈ 292 MiB of heap at a reported 168 MiB (configured 250) and the key cache ≈ 222 MiB at a reported 109 MiB (configured 200). By contract the three pools plus baseline need only 857 MiB of the 1024 MiB heap; it is the uncounted cache overhead that makes them not fit.

## 1. Constraints, contracts and protection map

Third pool added to the two-way case [`memtable_heap_space + counter_cache_size`](../memtable_heap_space+counter_cache_size/memtable_heap_space+counter_cache_size.md) (rechecked separately as R3). All three are on-heap, config-type true positives from if-check-exp, sharing one budget, the JVM heap (`-Xms1024M -Xmx1024M`, G1, 16 MiB regions). Pinned source: `systems/cassandra/source/` (read-only).

| Domain | Control (contract C) | Control's own counter K | Physical U measured as | Lifetime |
|---|---|---|---|---|
| Memtable (`memtable_heap_space=350MiB`, `memtable_allocation_type: unslabbed_heap_buffers`, `memtable_cleanup_threshold: 0.99`) | `MemtablePool` on-heap limit: "Total permitted memory to use for memtables. Cassandra will stop accepting writes when the limit is exceeded until a flush completes" (yaml); writers block in `MemtablePool.SubPool` when `allocated` reaches `limit` | `MemtablePool$SubPool.allocated` (live + flushing), each memtable's `allocator.onHeap.owns` | partition data reachable from each memtable's `partitions` map (dump) | standing, self-reclaiming (flush) |
| Counter cache (`counter_cache_size=250MiB`) | `CaffeineCache.create(capacity)` (`service/CacheService.java` `initCounterCache`): Caffeine `maximumWeight = 250 × 2^20`, weigher `key.unsharedHeapSize() + value.unsharedHeapSize()` (`cache/CaffeineCache.java`); yaml: "Maximum size of the counter cache in memory" | Caffeine `weightedSize` (dump), `nodetool info` size | objects exclusively reachable from the cache's `BoundedLocalCache` (dump) | standing, not self-reclaiming |
| Key cache (`key_cache_size=200MiB`) | same mechanism (`initKeyCache`), weigher `KeyCacheKey` (EMPTY_SIZE + key array) + `RowIndexEntry` | as above | as above | standing, not self-reclaiming |

- **Weigher omission (source):** `CounterCacheKey.unsharedHeapSize()` = EMPTY_SIZE + the partition-key and cell-name arrays; `ClockAndCount` = EMPTY_SIZE; `KeyCacheKey` = EMPTY_SIZE + key array. Per entry, Caffeine's node (`PSMW`, 40 B), the `ConcurrentHashMap$Node` (32 B), the table slot and the `FrequencySketch` table are not charged. Measured weight per entry: counter 120 B, key 88 B; measured heap per entry: counter ≈ 209 B, key ≈ 180 B.
- **Aggregate coverage:** none. No check relates the sum of memtable pool and cache capacities to the heap; auto defaults (key `min(5 % heap, 100 MiB)` = 51 MiB, counter `min(2.5 %, 50 MiB)` = 25 MiB, memtable ¼ heap) are each a fraction of the heap, but explicit values are accepted unchecked.
- **Feasibility:** Σ C + baseline = 350 + 250 + 200 + 57 = **857 MiB < 1024 MiB**. By contract the pools fit; an OOM needs U > C somewhere (protocol, *Classification by measurement*).
- **Labels:** capacities **custom**. Budget: **deliberately tightened diagnostic heap** (1 GiB). Supporting deviations: `memtable_allocation_type: unslabbed_heap_buffers` and `memtable_cleanup_threshold: 0.99` (deprecated knob, raised from 1/(1+flush writers)) so the memtable occupies its full pool on heap; an engineered concurrent three-workload mix. Hence `diagnostic`.

## 2. Verification design (recheck, 2026-11-11)

The design below was added to the case file before any recheck reading (verbatim, as written then).

### Recheck design (2026-11-11)

Campaign-plan row **R4** (pre-protocol recheck, V1–V5). Written before any reading on the recheck node.

**Node (environment change, disclosed).** `apt179` = `node1.jason92-325433.misconfiguration-pg0.apt.emulab.net` (APT r320): 1 × Xeon E5-2450 @ 2.1 GHz, 8 cores / 16 threads, 15.5 GiB RAM, 8 GiB swap, `/mydata` 1.6 TB local, Ubuntu 22.04, kernel 5.15.0-198-generic, cgroup v2, OpenJDK 11.0.33 (original: pc41, 40 cores, 251 GiB, OpenJDK 11.0.32.1). Nothing else runs on it. Because `cassandra-env.sh` sets `-XX:ParallelGCThreads`/`ConcGCThreads` to the core count, they resolve to **16** here (40 on pc41); GC work per pause and the stress clients' throughput are therefore lower. The budget is unchanged (`-Xms1024M -Xmx1024M`, no cgroup, as filed).

**Build.** `cp -a ~/cassandra-c1 /mydata/oom-recheck/R4/cassandra` (Cassandra 5.0.9, git tree `b796bcfda7c9640fa41257544a9fe62c1aec634a`, the same pinned source; built tree incl. `build/classes/stress`). Data, commit log, saved caches, logs and heap dumps live under `/mydata/oom-recheck/R4/` (harness logs: `/mydata/oom-recheck/R4/logs/<arm>/`, node logs + `.hprof` moved to `<arm>/node-logs/` at arm end).

**Harness.** `run1/oom-run.sh` copied to `/mydata/oom-recheck/R4/oom-run.sh`; the diff is saved as [`recheck-2026-11-11/harness.diff`](recheck-2026-11-11/harness.diff). Changes: paths (`C`, `L`), `XMX=1024M` pinned (env override removed), saved caches cleared at start, sampling continues every 5 s past sample 90 up to a 30-min cap (the original blindly waited for the clients after sample 90; when the node disappears the clients are stopped), `nodetool info` cache lines every 6th sample (30 s), end-of-arm `nodetool info` + `jcmd GC.class_histogram` (after the final forced-GC sample, only if the node is alive), node logs and dump kept per arm, stress summary extract, and a `validate` subcommand. Workloads, yaml edits and JVM options are unchanged: `memtable_allocation_type: unslabbed_heap_buffers`, `memtable_cleanup_threshold: 0.99` (supporting deviations, as filed), `memtable_heap_space`/`counter_cache_size`/`key_cache_size` per arm; `write n=3000000 -col size=FIXED(1024) threads=256`, `counter_write n=600000 threads=64`, `read n=4000000 -col size=FIXED(1024) -pop seq=1..500000 threads=192` after a 500,000-partition preload + `nodetool flush`; no env overrides (`MAX_HEAP_SIZE=1024M` is set by the harness, `HEAP_NEWSIZE` unset).

**Commands** (on apt179, from `/mydata/oom-recheck/R4`, each block detached with `setsid nohup`):

```
./oom-run.sh baseline                                          # idle heap, knobs 32/1/1
./oom-run.sh validate                                          # modest load: 350/250/200, n = 150k/60k/300k, preload 50k, diag dump
./oom-run.sh arm M_alone-r<k>  350 -   -   write                 # k = 1..3
./oom-run.sh arm C_alone-r<k>  -   250 -   counter
./oom-run.sh arm K_alone-r<k>  -   -   200 read
./oom-run.sh arm converge-r<k> 350 250 200 write,counter,read
./oom-run.sh arm ivC-r<k>      350 ""  200 write,counter,read   # intervention: counter_cache_size unset -> auto 25 MiB
./oom-run.sh arm ivK-r<k>      350 250 ""  write,counter,read   # row's suggestion: key_cache_size unset -> auto 51 MiB
```

("-" = the harness's tiny value: 32 MiB memtable / 1 MiB caches, as filed; `""` = setting left empty in the yaml → Cassandra's auto value, read back from the startup log.) Order: baseline, validate, M/C/K-r1 (sizing gate), converge-r1..r3, M/C/K-r2, M/C/K-r3, ivC-r1..r3, ivK-r1..r3.

**Source re-check** (pinned `systems/cassandra/source/`, read-only): both caches are `CaffeineCache.create(capacity)` (`cache/CaffeineCache.java`) with `maximumWeight = size × 2^20` and weigher `key.unsharedHeapSize() + value.unsharedHeapSize()` (`service/CacheService.java` `initKeyCache`/`initCounterCache`); `CounterCacheKey.unsharedHeapSize()` = EMPTY_SIZE + the two byte arrays, `ClockAndCount` = EMPTY_SIZE, `KeyCacheKey` = EMPTY_SIZE + key array — the weight omits Caffeine's node and the backing `ConcurrentHashMap` node/table per entry. The yaml documents `counter_cache_size` as "Maximum size of the counter cache in memory". Auto values (`config/DatabaseDescriptor.java`): key cache `min(max(1, 5 % of totalMemory), 100)` = 51 MiB, counter cache `min(max(1, 2.5 %), 50)` = 25 MiB at a 1024 MiB heap. Memtable: `memtable_heap_space` is the on-heap `MemtablePool` limit; writers block when it is exhausted until a flush releases memory; flush triggers at `memtable_cleanup_threshold` × limit (0.99 here).

**Protection map / feasibility (protocol, *Classification by measurement*).** Contract capacities C: memtable 350 MiB, counter cache 250 MiB, key cache 200 MiB; baseline ≈ 57 MiB (filed). Σ C + baseline = **857 MiB < 1024 MiB**: by contract the three pools cannot fill the heap, so an OOM requires physical usage above contract in at least one domain (plus transient write/read working sets). Prior measurements (if-check-exp stage 4) put counter-cache physical memory at ≈ 1.8–2.1 × its weight and key cache at ≈ 1.4–2.0 ×. **Predicted classification: mixed** — an accounting-omission excess (U > C, K ≤ C) in the Caffeine caches, chiefly the counter cache, contributing to aggregate exhaustion of a heap shared by three pools; pure convergence only if the dump shows U ≤ C in every domain.

**Predictions per arm** (from the filed run, adjusted for the node):
- baseline: idle heap after GC ≈ 57 MiB (5.6 %).
- M_alone: 0 errors, completes; final forced-GC heap 100–250 MiB (≤ 25 %); transient peaks may reach 90 %+.
- C_alone: counter cache fills to its 250 MiB weight (600k partitions × 5 cells exceeds it); final forced-GC heap 500–600 MiB (49–59 %), i.e. U(counter) ≈ 450–525 MiB.
- K_alone: key cache weight limited by the 500k-key population (≈ 110–120 MiB, below its 200 MiB cap); final 140–220 MiB (≤ 22 %).
- converge: Java-heap `OutOfMemoryError`, heap dump written, `-XX:OnOutOfMemoryError=kill -9 %p` kills the JVM, in 3/3 within the 30-min cap; live heap at the failure ≈ 950–1000 MiB; dump: counter cache ≈ 450–525 MiB exclusive (weight 250 MiB), memtable ≈ 250–400 MiB (pool `allocated` ≤ 350 MiB), key cache ≈ 100–250 MiB (weight ≤ 200 MiB). Slower CPUs may delay it; reaching it later than on pc41 is not a failure of the condition.
- **Intervention (primary) ivC** — counter_cache_size back to auto (25 MiB), same three workloads: predicted live ≈ 57 + ≤ 400 + ≈ 50 + ≤ 250 ≈ 550–750 MiB → **no OOM in 3/3**, workloads complete; counter_write throughput may drop (more read-before-write misses); recorded per arm.
- **Row's suggested intervention ivK** — key_cache_size back to auto (51 MiB): predicted live ≈ 57 + ≤ 400 + ≈ 500 + ≈ 75–100 ≈ 1000 MiB → **does not reliably fit**; expect sustained full GCs and an OOM in at least 1 of 3. Run as a secondary, informative arm (not the V4 intervention) if the arm budget allows.

**Endpoint and pass/fail.** Converge passes a repeat when stdout shows `java.lang.OutOfMemoryError: Java heap space` (or `gc.log` shows the failed allocation + `ReportJavaOutOfMemory`), a `.hprof` is written, and the process is gone without the harness stopping it (`OnOutOfMemoryError` kill), with no kernel OOM-kill in `dmesg`. A control (alone) passes when the workload completes with 0 `ERROR` lines, no OOM and a final forced-GC heap ≤ 70 % of 1024 MiB (30 % margin). An intervention repeat passes when there is no OOM within the cap and all three workloads complete (throughput recorded).

**V1–V5 evidence.** V1: converge-r1..r3. V2: M/C/K_alone-r1..r3. V3: U per domain = exclusive reachable set of each holder in the converge dump (all memtables; `CacheService.counterCache`; `CacheService.keyCache`) from `tools/hprof_holders.py` (python3 -I, standard library; method in the script header), against K read from the same dump (Caffeine `weightedSize`/`maximum`, `MemtablePool$SubPool.allocated`, each memtable's `owns`); in alone arms U from the final class histogram / forced-GC heap and K from `nodetool info`. V4: ivC-r1..r3. V5: first error = the thread HotSpot marks as throwing the OOM in the dump (fake `OutOfMemoryError.<init>` top frame) with its stack, the stdout OOM line and `gc.log` tail, plus the holder histogram from the dump.

**Stopping budget.** ≤ 6 h wall (from 12:33 MST), ≤ 22 arm executions (planned 20: baseline, validate, 9 alone, 3 converge, 3 ivC, 3 ivK); extend a condition to at most 5 repeats only for mixed outcomes, within the 22. Per-arm cap 30 min of sampling. Gate: if M/C/K-r1 show a component no longer safe alone (> 70 %), or a sum that can no longer exceed the heap, write a dated amendment before any converge reading.

**Executed as designed**, with these notes (no amendment was needed: the r1 alone arms kept "safe alone + exceeds together"): the first three alone arms ended at 21 / 57 / 21 % of the heap; arms ran in the planned order, 20 arm executions in total (budget 22), 12:33–17:00 MST (≈ 4.5 h of the 6 h budget); the hprof parser ran niced (`nice -n 19`, one CPU of 16, a few GiB of RAM outside the JVM) on the node while later arms ran; `jcmd`-attach heap samples every ≈ 5.5 s and `nodetool info` every sixth sample were the only instrumentation during workloads. The harness's cap counts 360 samples, which stretches past 30 min when `jcmd` attaches block in GC thrash; for ivK r2–r3 a watcher (`capwatch.sh`) enforced the intended 30-min wall cap by stopping the clients. It acted only in ivK r2, 12.7 min after that arm's first OOM (clients already exiting), so it changed no outcome. Two measurement details changed after the design, before the converge results were read: (1) the parser's first version blocked the outer `AutoSavingCache` objects and found the cache entries reachable via metrics wrappers, so the cache holder root was moved to the Caffeine `BoundedLocalCache` (validated on the `validate` dump); (2) the memtables' exclusive set misses a flushing memtable's partitions, which the flush writer also references, so memtable U is the partition-data reach from each memtable's `partitions` map (exclusive and inclusive sets are reported as well). The JVM's own stdout OOM line is not available (Cassandra closes stdout after startup when not in foreground), so V5 uses `gc.log` and the dump. The harness diff, parser and helper scripts are in [`recheck-2026-11-11/`](recheck-2026-11-11/).

## 3. Results

Full logs: apt179 `/mydata/oom-recheck/R4/logs/<arm>/` (session log, summary, heap samples, stress outputs, `node-logs/` with `system.log`, `gc.log*`, `.hprof` dumps of the six OOM arms, ≈ 1.3–1.4 GB each, and the validate diagnostic dump). Committed excerpts per arm: [`recheck-2026-11-11/logs/`](recheck-2026-11-11/logs/) (summary, yaml diff, JVM args, startup lines, stress results, end-of-arm `nodetool info` and class histogram; for OOM arms the `gc.log` lines at the first OOM and at the kill, stop-the-world share, `system.log` error summary, and the dump report).

### 3.1 Environment and baseline

apt179 vs the original pc41: 16 vs 40 hardware threads (Xeon E5-2450 2.1 GHz), 15.5 vs 251 GiB RAM, OpenJDK 11.0.33 vs 11.0.32.1. Resolved JVM options are the same except `-XX:ParallelGCThreads=16 -XX:ConcGCThreads=16` (40 on pc41) and `-XX:MaxDirectMemorySize=3982M` (15872M; RAM/4, not used by these pools). G1 with `G1NewSizePercent=50`, `MaxGCPauseMillis=300`, `IHOP=70`, `-XX:+HeapDumpOnOutOfMemoryError`, `-XX:OnOutOfMemoryError=kill -9 %p` (from `conf/jvm11-server.options` / `cassandra-env.sh`). Startup logs confirm the resolved values per arm (`Global memtable on-heap threshold is enabled at 350MiB`, `Initializing counter cache with capacity of 250 MiBs`, `Initializing key cache with capacity of 200 MiBs.`; auto 25 / 51 MiB in the interventions). Baseline idle heap after GC (knobs 32/1/1 MiB): **55.5 MiB** (pc41: 56.8 MiB). Cassandra closes its stdout after startup (non-foreground mode), so the JVM's own "java.lang.OutOfMemoryError … Dumping heap" lines are not captured; the OOM evidence is `gc.log`, the dump and the process exit.

**Modest-load validation** (`validate`: filed capacities, n = 150k / 60k / 300k, 50k preload): all three pools engaged with 0 errors (write 6.2k, counter 2.1k, read 8.8k op/s); a diagnostic `jcmd GC.heap_dump` (live objects, 451 MiB) checked the parser against `GC.heap_info` (452.8 MiB used) and gave U vs K at low load: memtable 302 MiB vs pool `allocated` 310 MiB; counter cache 56.9 MiB vs weight 34.3 MiB (1.66×); key cache 16.3 MiB vs weight 8.4 MiB (1.94×).

### 3.2 Controls — each pool alone (×3)

| Arm | Final forced-GC heap (MiB, % of 1024) | Sampled peak (no forced GC) | Workload result | Control counter at end |
|---|---|---|---|---|
| M_alone r1 / r2 / r3 (`write`, M=350) | 213.4 (20.8 %) / 225.8 (22.1 %) / 226.2 (22.1 %) | 89 / 91 / 92 % (young garbage) | 3,000,000 writes in 7:29 / 7:56 / 7:40, 6,673 / 6,302 / 6,511 op/s, 0 errors | — |
| C_alone r1 / r2 / r3 (`counter_write`, C=250) | 583.2 (57.0 %) / 548.9 (53.6 %) / 548.9 (53.6 %) | 93 / 90 / 91 % | 600,000 counter writes in 1:05–1:08, 9,183 / 8,757 / 9,066 op/s, 0 errors | counter cache 2,184,533 entries, **250 MiB = cap** (all three) |
| K_alone r1 / r2 / r3 (`read`, K=200, 500k preload) | 213.7 (20.9 %) / 155.7 (15.2 %) / 213.2 (20.8 %) | 78 / 72 / 66 % | 4,000,000 reads in 1:38–1:47, 40,515 / 37,112 / 39,161 op/s, 0 errors | key cache 801,015 / 500,385 / 798,541 entries, 67.2 / 42.0 / 67.0 MiB |

All nine: 0 `ERROR` lines, no OOM, no kernel OOM-kill, ≥ 43 % of the heap free after a forced GC (declared margin 30 %). As on pc41, alone the key cache cannot reach its cap (the 500k-key population with 1–2 sstables gives ≤ 67 MiB weight) and the memtable drains after the write; the counter cache is the only pool at its cap alone. U alone (end-of-arm class histograms): counter cache ≈ 433 MiB at K = 250 MiB (`PSMW` + `ConcurrentHashMap$Node` + `ClockAndCount` + `CounterCacheKey` alone are 284.5 MiB; plus ≈ 117 MiB key/cell-name arrays and 32 MiB table and sketch) — **U > C already alone, but the heap absorbs it**; key cache ≈ 132 MiB at K = 67 MiB (1.96×).

### 3.3 Converge — all three pools, all three workloads (×3)

| | r1 | r2 | r3 |
|---|---|---|---|
| Workloads launched → first OOM | 13:10:50 → **13:17:20** (6.5 min) | 13:23:32 → **13:39:05** (15.5 min) | 13:41:20 → **13:50:20** (9.0 min) |
| Failing allocation (gc.log) | 1,040 B after `Pause Full (G1 Evacuation Pause) 992M->992M`, heap fully expanded | after the harness's forced `Pause Full (Diagnostic Command) 988M->987M` | 8,589,934,600 B humongous request, after `Pause Full (G1 Humongous Allocation) 991M->991M` (see anomalies) |
| Thread marked as throwing (dump) | `CompactionExecutor:2`, `ByteArrayAccessor.read` ← `Cell$Serializer.deserialize` ← `CompactionIterator` | `Native-Transport-Requests-34`, `AbstractWriteResponseHandler.throwTimeout` ← `StorageProxy.mutate` | `CompactionExecutor:1`, same compaction read path as r1 |
| Heap dump / JVM killed | 1.36 GB / yes, `ReportJavaOutOfMemory` safepoint +248 s | 1.36 GB / yes, +10 s | 1.36 GB / yes, +10 s |
| Stop-the-world share (whole run / last 600 s) | 67 % / 84 % | 76 % / 99.6 % | 63 % / 70 % |
| Clients | all three failed (`NoHostAvailable`/timeouts) after ≈ 1.03M writes, ≈ 0.29M counter writes, ≈ 0.96M reads; no harness intervention | same, failed by 13:31:42, 7.5 min before the OOM | same |
| `system.log` ERRORs | 20 `WriteTimeoutException` (CounterMutationStage) | 35 (same) | 66 (same) |
| Kernel OOM-kill | none | none | none |

**Holders in the dump at the first OOM** (`tools/hprof_holders.py`, shallow sizes with compressed oops; method in the script header). Memtable U = partition data reachable from the memtables' `partitions` maps (shared or not, so a flushing memtable counts); cache U = objects exclusively reachable from the cache's `BoundedLocalCache`; K read from the same dump.

| Domain (C) | r1 U / K | r2 U / K | r3 U / K | U vs C |
|---|---|---|---|---|
| Memtable (350 MiB) | 333.7 / 350.0 MiB (`allocated` at `limit`; 197.8 MiB of it flushing) | 334.3 / 350.0 | 334.2 / 350.2 | **U ≤ C** (0.95 K) |
| Counter cache (250 MiB) | 295.0 / 169.4 MiB (1,479,965 entries) | 292.5 / 167.8 | 290.4 / 166.5 | **U > C, K ≤ C** (1.74 K) |
| Key cache (200 MiB) | 218.9 / 107.2 MiB (1,276,828 entries) | 222.1 / 108.9 | 224.6 / 110.3 | **U > C, K ≤ C** (2.04 K) |
| Everything else live (baseline, working sets) | 79.2 MiB | 72.4 | 76.8 | — |
| Unreachable (garbage) / dump total | 31.7 / 958.5 MiB | 35.2 / 956.5 | 34.9 / 960.9 | — |

Top of the r1 histogram (all objects, MiB): `byte[]` 344.2, Caffeine `PSMW` nodes 105.2 (2,756,800: counter + key cache), `ConcurrentHashMap$Node` 85.2, `long[]` 47.6, `HeapByteBuffer` 47.5, `ClockAndCount` 45.2, `CounterCacheKey` 45.2, `KeyCacheKey` 39.0, `int[]` 35.8, `BufferCell` 32.5, `Object[]` 30.1, `RowIndexEntry` 29.4. r2 and r3 match within 1 % ([dump reports](recheck-2026-11-11/logs/)).

Prediction fit: OOM 3/3 as predicted; live at failure 987–992 MiB (predicted 950–1000); counter cache U 290–295 MiB, below the predicted 450–525 MiB because the cache had not filled (weight 167–169 of 250 MiB); key cache U 219–225 MiB (predicted 100–250), memtable 334 MiB (250–400). Matches pc41 (OOM after a Full GC 989M→989M, key cache weight 111 MiB at the end, kill by `OnOutOfMemoryError`).

**Classification by measurement:** two domains have U > C with K ≤ C (accounting omission in the Caffeine weigher), the third is at its contract. Counterfactuals from the dump: with the caches holding exactly their reported weight the live heap would be ≈ 690 MiB; with both caches full and U = C, ≈ 863 MiB; without the memtable, ≈ 593 MiB. The OOM needs both the cache excess and the other pools → **mixed** (protocol: "a bypass excess plus other domains are both needed for the OOM").

### 3.4 Intervention — `counter_cache_size` back to auto (25 MiB), same workloads (×3)

Same build, heap, `memtable_heap_space=350MiB`, `key_cache_size=200MiB` and the same three workloads; only `counter_cache_size` is left empty, so Cassandra resolves its auto value (startup log: `Initializing counter cache with capacity of 25 MiBs`).

| | r1 | r2 | r3 |
|---|---|---|---|
| OOM / process alive at end | **no** / yes | **no** / yes | **no** / yes |
| Workloads | all complete: 3,000,000 writes, 600,000 counter writes, 4,000,000 reads; 0 client errors | same | same |
| Throughput (op/s) write / counter / read | 2,780 / 819 / 2,087 | 3,365 / 976 / 2,704 | 2,874 / 869 / 3,406 |
| Wall time of the slowest client (read) | 31:56 (cap ≈ 33 min) | 24:39 | 19:34 |
| Highest live heap after a Full GC | 742 MiB (72 %) | 748 MiB (73 %) | 747 MiB (73 %) |
| Final forced-GC heap | 560.9 MiB (54.8 %) | 573.3 MiB (56.0 %) | 627.5 MiB (61.3 %) |
| Stop-the-world share (run / last 600 s) | 24 % / 30 % | 31 % / 22 % | 37 % / 37 % |
| Caches at end (weight) | counter 25 MiB (218,453 entries, at cap); key 127.1 MiB | 25 / 131.3 MiB | 25 / 123.4 MiB |
| `system.log` ERRORs | 37 | 44 | 47 |

**Result: the OOM is removed in 3/3, at full completed load** (all 7.6M operations done, matching the converge arms' offered load; the converge arms completed only ≈ 2.3M before their clients failed). Live heap peaks at ≈ 745 MiB, ≈ 245 MiB below the converge arms' 987–992 MiB, in line with the counter cache shrinking from ≈ 292 MiB of heap at the converge OOM to ≈ 45 MiB (25 MiB weight × ≈ 1.75). The node is still under heavy GC (≈ 750 Full GCs per run, mostly young-gen evacuation failures: `G1NewSizePercent=50` reserves ≥ 512 MiB of young gen next to ≈ 550–750 MiB of old data) and logs 37–47 server-side `WriteTimeoutException`s on `CounterMutationStage` (2 s counter-write timeout), which the clients retried without error. Counter writes run at ≈ 0.8–1.0k op/s (9k alone) — the 25 MiB counter cache misses, so each counter update reads before writing. Prediction (no OOM 3/3, live 550–750 MiB) held.

### 3.5 Row's suggested intervention — `key_cache_size` back to auto (51 MiB) (×3, secondary)

The row's suggestion, run as a pre-registered secondary arm (prediction: does not reliably fit; OOM in ≥ 1 of 3). `key_cache_size` left empty → auto 51 MiB (startup log), everything else as in converge.

| | r1 | r2 | r3 |
|---|---|---|---|
| Workloads launched → first OOM | 15:51:31 → **16:03:29** (12.0 min) | 16:05:51 → **16:23:13** (17.4 min) | 16:40:06 → **16:57:51** (17.8 min) |
| Failing allocation / dump-marked thread | 32 MiB humongous (counter cache's `FrequencySketch.ensureCapacity`, thread `CounterMutationStage-89`) | 32 B / `Native-Transport-Requests-152` (`ByteArrayAccessor.read`) | 8,589,934,600 B humongous request after `Full GC 988M->988M` (as converge r3) / `ReadStage-170` (`ByteBufferUtil.read`) |
| Dump / JVM killed | yes / yes (+9 s) | yes / yes (+14.8 min, after the clients had failed) | yes / yes (+9 s) |
| Caches at the last `nodetool info` | key 51 MiB (cap, 607,697 entries); counter 236.4 MiB (2,065,800) | 51 MiB; 239.4 MiB | 51 MiB; 238.5 MiB |
| Dump: counter cache U / K | 400.0 MiB / 240.0 MiB | 437.4 MiB (inclusive) / ≈ 240 MiB | 436.1 / 242.6 MiB |
| Dump: key cache U / K | 157.0 MiB (inclusive) / 51.0 MiB | 104.7 / 51.0 MiB | 104.7 / 51.0 MiB |
| Dump: memtable data / pool `allocated` | 325.0 / 337.8 MiB | 328.2 MiB / at limit | 329.0 / 342.8 MiB |

**Result: OOM in 3/3 — capping the key cache at its default does not remove the endpoint.** With the key cache held to 51 MiB (≈ 105–157 MiB of heap), the counter cache — no longer competing with a large key cache for the same window — grows to ≈ 240 MiB of weight, i.e. ≈ 400–437 MiB of heap (1.67–1.82× its weight, 1.6–1.75× its configured 250 MiB), and the heap fills again 12–18 min after launch. This matches the prediction (live ≈ 1000 MiB) and shows that the counter cache's uncounted overhead, not the key cache, is the decisive excess at this sizing. In r1 the failing allocation was the counter cache's own frequency-sketch resize (32 MiB `long[]`), another per-cache allocation outside the weight. In two dumps part of a cache's entries was also reachable from outside the cache at the dump instant (exclusive set ≈ 0), so the inclusive measure is quoted there.

### 3.6 Per-condition status and V1–V5

| Arm | n | Endpoint reached | Notes |
|---|---|---|---|
| converge (350/250/200) | 3 | **3/3** heap OOM + dump + JVM killed | r2 OOM followed the harness's forced GC; r3's last failed request was 8 GiB |
| M_alone / C_alone / K_alone | 3 each | 0/3 each | 15–57 % of heap after forced GC, 0 errors |
| ivC: counter_cache_size → auto 25 MiB (V4) | 3 | **0/3** | all 7.6M operations complete; live ≤ 748 MiB; 24–37 % of time in GC pauses |
| ivK: key_cache_size → auto 51 MiB (secondary) | 3 | 3/3 OOM | counter cache refills the heap (U ≈ 400–437 MiB) |

| | Requirement | Evidence | Met |
|---|---|---|---|
| V1 | endpoint ≥ 3 runs from clean starts | converge r1–r3 (3/3), §3.3 | yes |
| V2 | nearest surviving control ≥ 3 | M/C/K_alone r1–r3, 9/9 survive with ≥ 43 % free, §3.2 | yes |
| V3 | U apart from K per domain | converge dumps: memtable data vs `SubPool.allocated`; cache exclusive sets vs Caffeine `weightedSize` (§3.3); alone arms: class histograms vs `nodetool info` (§3.2); validate dump | yes |
| V4 | intervention removes endpoint ≥ 3 at recorded load | ivC r1–r3: `counter_cache_size` → auto 25 MiB, same workloads; 0/3 OOM, all 7.6M operations complete, throughput recorded (§3.4) | yes |
| V5 | first error + holder histogram | r1: `gc.log` failed 1,040 B allocation after `Full GC 992M->992M`, dump-marked thread `CompactionExecutor:2` with stack, holder histogram (§3.3); r2, r3 and ivK r1–r3 likewise (the failing request in r3 and ivK r3 is anomalous, see §4) | yes |

## 4. Conclusion and limits

**Established (V1–V5 met):** on a 1 GiB heap, the memtable pool (350 MiB), counter cache (250 MiB) and key cache (200 MiB) filled concurrently exhaust the heap and kill the JVM (3/3), while each alone leaves ≥ 43 % free (9/9); dropping the counter cache to its default removes the OOM (3/3, all workloads complete, live heap ≤ 748 MiB). Every local control does what its code says: the memtable pool stops at its limit and the caches stay below their weight caps. Two gaps combine: (1) **no aggregate check** — Cassandra accepts any combination of memtable and cache sizes regardless of the heap; (2) **the Caffeine caches undercount themselves** — the weigher omits per-entry container overhead, so the counter cache occupies ≈ 1.74× and the key cache ≈ 2.0× their reported (and configured) size. Gap (2) is what turns a nominally feasible configuration (857 of 1024 MiB) into an OOM, so the case is **mixed**, not pure convergence.

**Interpretation:** configuration-sizing gap (no validation of the sum) plus a documented-unit mismatch that reads as an implementation defect: `counter_cache_size` is documented as "Maximum size of the counter cache in memory", but the weight excludes ≈ 40–50 % of the memory each entry costs. Before any upstream report: check JIRA for the weigher's scope (whether container overhead was deliberately excluded) and measure the ratio at deployment-sized heaps and other key sizes (the ratio depends on key/cell-name length).

**Limits:**
- Diagnostic: 1 GiB heap, `unslabbed_heap_buffers`, cleanup threshold 0.99, and a mix built to fill all three pools in one window. A deployment-sized heap (e.g. 8 GiB with ¼ for memtables) would need cache settings near 1 GiB each; not tested.
- The OOM comes after minutes of GC thrash (63–76 % of the run stopped in GC pauses, 70–99.6 % over the last 10 min; the clients fail first); the precise failing allocation is incidental (compaction read, a request thread, or the unexplained 8 GiB request in converge r3 and ivK r3).
- Memtable U is a reachability measure over partition-data classes; cache U counts objects reachable only through the cache; shallow sizes are estimates (12-byte headers, 4-byte refs, 8-byte alignment). The parser's total matched `GC.heap_info` within 0.4 % on the validation dump.
- Node differs from pc41 (16 vs 40 GC threads, slower CPU); the outcome and holder sizes reproduce the pc41 run. pc41's 1.35 GB run-2 dump was not analysed (node retired); all holder evidence comes from the recheck dumps.
- The intervention lowers the counter cache to its default and removes the OOM at full load, but the node still runs with frequent Full GCs (G1 young-gen sizing at ≈ 70 % old data); a cleaner fix (a weigher that counts container overhead, or a check of Σ pools against the heap) was not tested. Lowering the key cache to its default does not remove the OOM (3/3).

**Anomalies:** (a) In converge r3 and ivK r3 the final failed allocation was logged by G1 as a single 8,589,934,600-byte humongous request (several attempts in the last 1–2 s), while the dump marks a reader thread as throwing (`CompactionExecutor:1` in `ByteArrayAccessor.read`, `new byte[length]`; `ReadStage-170` in `ByteBufferUtil.read`), whose int-length byte-array allocation cannot exceed 2 GiB. The source of an 8 GiB request is not identified (a corrupt length read under GC pressure would be a separate lead; not investigated). Both heaps were 988–991/1024 MiB live after the preceding Full GCs, so they were exhausted independently of that request; the other four OOM arms failed on ordinary allocations (1,040 B; 32 B; a 32 MiB frequency-sketch resize; and in converge r2 an allocation right after the forced GC). (b) In r2 the first OOM came immediately after the harness's end-of-arm `jcmd GC.run` (queued for 7.4 min behind GC thrash after the clients had failed); in r1 and r3 no forced GC was involved. (c) In r1 the `OnOutOfMemoryError` kill fired 248 s after the dump (VM operation queued behind back-to-back Full GCs; pc41 showed a similar 3 min 40 s delay); 10 s in r2 and r3.
