# memtable_offheap_space + file_cache_size — run history

The per-run case file of this case, kept verbatim after the case was verified and consolidated into
[`memtable_offheap_space+file_cache_size.md`](memtable_offheap_space+file_cache_size.md) (filing rule:
protocol *Case evidence and batch status*, amended 2026-11-11). It was filed as run 7 (2026-11-03) in
`convergence/`, moved to `candidates/` as `candidate (pre-protocol)` on 2026-11-11, and received the R1
recheck design, its validation note and amendments on 2026-11-11 before the recheck readings. Only mechanical
changes: every heading is demoted one level, anchors are added, and relative links are repointed for the new
folder depth (the run-7 harness `oom-run.sh` and `logs/` are in this folder; the recheck in
`recheck-2026-11-11/`).

| Part | Original location |
|---|---|
| [Run 7 — 2026-11-03, pc41: filed case (sections 1–4, instrument check)](#run-7) | `cases/convergence/memtable_offheap_space+file_cache_size.md`, then `cases/candidates/memtable_offheap_space+file_cache_size.md` |
| [Recheck design (2026-11-11), validation note, check after the first alone arms, amendment 17:20](#recheck-design) | appended to `cases/candidates/memtable_offheap_space+file_cache_size.md` before the readings |

---

<a id="run-7"></a>

## memtable_offheap_space + file_cache_size — convergence case (run 7)

> **Status (2026-11-11): `candidate (pre-protocol)`.** Moved from `convergence/` to `candidates/`: filed before the 2026-11-06 protocol and does not meet the V1–V5 promotion rule ([protocol](../../../../verification-protocol.md#verification-status-amended-2026-11-11)). Evidence held: converge 1 run; each alone 1 run; no intervention; cgroup OOM-kill record in `dmesg`, no per-pool breakdown at the kill. The OOM recorded below stands; rerun ×3 with matched controls and an intervention ×3 to return it to `convergence/`.

> **Run:** 2026-11-03, node `node0.jason92-323989.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB), same build as runs 1-6 (`~/cassandra-run1`, cassandra-5.0.9, unchanged). Second off-heap pair; both constraints are new to OOM-exp.
>
> **Harness:** [`./`](./) (`oom-run.sh`; per-arm summaries, yaml diffs, final readings, stress outputs, the `M_alone` memtable flush lines and the converge arm's `dmesg` kill lines). Per-5-s samples stay on the node in `~/oom-offheap-run7/logs/`.
>
> **Outcome: OOMed.** Each pool alone stayed at 78% of a 3500 MiB cgroup budget. Together, the kernel OOM-killed the JVM 16 s into the write burst (`MutationStage-5` invoked the killer; anon-rss 3465 MiB). Clean case: same budget for every arm, kill attributed by scope and PID.

### 1. Constraints and capacities

| | `memtable_offheap_space` | `file_cache_size` |
|---|---|---|
| if-check-exp | [`memtable_offheap_space-tryAllocate-limit--guided`](../../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/memtable_offheap_space-tryAllocate-limit--guided.md), true positive (also the set-B autonomous `applySimpleConfig` case) | [`file_cache_size-allocateMoreChunks-memoryUsageThreshold--guided`](../../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/file_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md), true positive ("confirmed for the pool") |
| What it caps | Off-heap memtable bytes: with `memtable_allocation_type: offheap_objects`, `NativeAllocator` takes 1 MiB regions via `MemoryUtil.allocate` (malloc); writers park at the limit | The chunk-cache `BufferPool`: direct macro chunks up to `file_cache_size`, never released once reserved; with `file_cache_enabled: true`, `ChunkCache` (Caffeine, `maximumWeight = file_cache_size − 32 MiB`) holds its buffers |
| Standing pool? | Yes: the memtable sits near the limit under sustained writes (`memtable_cleanup_threshold: 0.99`), and glibc keeps freed regions, so `RssAnon` does not fall at a flush (if-check-exp finding) | Yes: a cache, plus a pool whose reservation is kept |
| Setting here | 1200 MiB | 1200 MiB (cache capacity 1.14 GiB) |
| Budget mechanism | Neither is bound by `-Xmx`; the budget is a cgroup v2 `memory.max` on the whole JVM, as in runs 4-6, read as `RssAnon` | same |

Fixed settings in every arm: `-Xmx768M`, `memtable_heap_space: 200MiB` (raised from runs 4-6 to avoid run 6's heap OOM), `memtable_cleanup_threshold: 0.99`, `memtable_allocation_type: offheap_objects`, `file_cache_enabled: true`, budget via `systemd-run --user --scope -p MemoryMax=… -p MemorySwapMax=0`.

### 2. Verification solution

**Workloads.** *preload*: `cassandra-stress write` 800,000 partitions (5 × 1 KiB columns) into `dataks`, flushed, autocompaction disabled. *cachefill*: one read pass over all 800,000 partitions, 64 threads. *memburst*: `cassandra-stress write` up to 2,000,000 partitions into `memks`, 64 threads, 50 retries/op, capped at 240 s.

**Calibration (8000 MiB budget, 600 MiB per pool):** memtable alone +865 MiB, chunk cache alone +808 MiB, both +1536 MiB (92% of the sum) over an idle of about 1300 MiB. About 250 MiB of growth comes from the write load itself (networking buffers, glibc arenas) and is counted once when both run, so at 600 MiB no budget gave both "safe alone" and "exceeds together". Both pools were doubled to 1200 MiB and the dataset to 800,000 partitions.

**Arms (3500 MiB budget in all):** `M_alone` (M = 1200, F = 64, memburst), `F_alone` (M = 64, F = 1200, preload + cachefill), `converge` (M = F = 1200, preload, then cachefill, then memburst: the standing cache first, then the burst, the order run 6 found decisive).

**Prediction:** idle 1290 + 1425 (M alone) + 1432 (F alone) ≈ 4147 MiB (118%) naive; with calibration's 8% overlap discount ≈ 3920 MiB (112%).

### 3. Runtime results

| Arm | Idle | Peak RssAnon | % of 3500 MiB | Pool reached its cap? | Outcome |
|---|---|---|---|---|---|
| `M_alone` | 1292 | 2717 | 77.6% | yes: every flush enqueued at 100% off-heap (1.172 GiB), writers parked (3,136 write timeouts, burst completed 2,000,000) | alive, no kill |
| `F_alone` | 1289 | 2721 | 77.7% | yes: chunk cache 149,504 entries, 1.14 of 1.14 GiB | alive, no kill |
| `converge` | 1287 | 3114 sampled; **3465 at kill** (`dmesg` anon-rss) | 89% sampled → **killed** | chunk cache full (1.14 GiB) before the burst; memtable still filling at the kill | **kernel OOM-kill** |

**Converge timeline (local time).**
- 17:00:03 to 17:01:06: preload (800,000 writes, 0 errors); `RssAnon` 2470 MiB after flush.
- 17:01:28 to 17:22:28: read pass (800,000 reads, 0 errors; 21 min, slowed by the cgroup sitting at `memory.max`); chunk cache full at 1.14 GiB; `RssAnon` 3067 MiB.
- 17:22:43: write burst starts. Samples: 3067 MiB (m1), 3114 MiB (m2); `memory.current` at `memory.max`.
- 17:22:59: `MutationStage-5 invoked oom-killer`, `constraint=CONSTRAINT_MEMCG`, `oom_memcg=…/oom-run7-1793743155084104664.scope` (this arm's scope); `Killed process 298318 (java) … anon-rss:3548404kB`. PID 298318 is the arm's node. No memtable flush of `memks` had started. No `OutOfMemoryError`, no ERROR line.

### 4. Conclusion

**The pair converges to a real OOM.** Each pool, driven to its own cap alone, left 22% of the budget free; with the chunk cache parked at its cap, the off-heap memtable's first fill pushed the process past the budget, and the kernel killed it from a write thread allocating memtable memory. The kill came well before the memtable reached its 1200 MiB limit: the chunk cache's standing 1.14 GiB, plus the pool and load overhead, left less room than the memtable's own cap.

**Comparison with the first off-heap pair (runs 4-6).** That pair needed engineered timing: the index-summary cap bounds summaries only at a periodic resize, so the overshoot was a transient, and only one schedule killed the node. Here both constraints are hard, standing caps, so the arithmetic alone predicts the outcome; the simple order (fill the cache, then write) was enough on the first try.

**Target-3 note.** This is the most realistic off-heap case so far: two documented yaml knobs an operator might set together when moving memory off-heap ("memtables off-heap at 1.2 GiB, chunk cache at 1.2 GiB"), each sized safely against the node on its own, plus a normal read-then-write workload. The supporting settings are less natural: `memtable_cleanup_threshold: 0.99` (deprecated, used here to park writers at the limit; the default 0.33 flushes earlier) and the cgroup budget standing in for a container limit. The kill happened during the memtable's first fill, so a lower cleanup threshold might delay it but would not change the sum the two caps allow.

### Instrument check and process hygiene

- Kill attribution from `dmesg`: `oom_memcg` equals this arm's scope unit, killed PID equals the node PID in `summary.txt`.
- Both caps confirmed reached in their alone arms from Cassandra's own readings (flush `Usage: … 1.172GiB (100%) off-heap`; `nodetool info` chunk cache size = capacity).
- The "JVM OOM lines: 1" in the calibration summaries is a grep false positive (a `CompileCommand` line naming `OutOfMemoryError`); the grep was tightened before the 1200 MiB arms, which all report 0.
- `memory.current` sits at `memory.max` under load in every arm because page cache counts toward it; `RssAnon` is the reading, `oom_kill`/`dmesg` the outcome signal (as in runs 4-6).
- After every arm, `pgrep` for `CassandraDaemon` and `cassandra-stress` was empty and the scope unit stopped. Data, commit log and logs stayed under `~/cassandra-run1` on local disk; nothing written to `/proj`; the repository's `systems/cassandra/source/` untouched.

<a id="recheck-design"></a>

### Recheck design (2026-11-11) — campaign row R1, pre-protocol recheck (V1–V5)

Written before any reading at the 3500 MiB budget. Only a modest-load instrument validation
(`val_modest`, 8000 MiB budget, 100,000 / 300,000 partitions, 60 s burst) ran before it.

**Node and build (environment change, disclosed).** `pc96` (`node0.jason92-325405…cloudlab.umass.edu`):
2 × Xeon E5-2667 v2, 32 cores, 2 NUMA nodes, 125 GiB RAM, 8 GiB swap (excluded by `MemorySwapMax=0`),
Ubuntu 22.04, kernel 5.15.0-198, glibc 2.35, cgroup v2, OpenJDK 11.0.33 (`/usr/lib/jvm/java-11-openjdk-amd64`).
The filed runs were on `pc41` (40 cores, 251 GiB). Build: `/mydata/oom-recheck/R1/cassandra`, a `cp -a` of
`/mydata/b6/cassandra` (cassandra-5.0.9, HEAD `f2de695`, source tree `b796bcfd…`, clean; stress built). Data,
commit log, saved caches and system logs stay inside that copy on local `/mydata`; arm logs in
`/mydata/oom-recheck/R1/logs/<arm>/`. Derived settings that could differ by node: `MALLOC_ARENA_MAX=4`
(set by `cassandra-env.sh` on both), `MaxDirectMemorySize` = 15872M on both (heap_limit/2, RAM > 63 GiB),
G1 parallel GC threads 23 here vs 28 on pc41, `-XX:+AlwaysPreTouch` (heap resident from start).

**Source re-check (pinned `systems/cassandra/source/`, read-only).**
- Memtable off-heap: `NativeAllocator.allocate` charges `offHeap().allocate(size, opGroup)` (the
  `memtable_offheap_space` sub-pool, which blocks writers at the limit) and then takes memory from 1 MiB
  regions (`MAX_REGION_SIZE`, `NativeAllocator.java:46,138–184`) allocated by `MemoryUtil.allocate` →
  `com.sun.jna.Native.malloc` (`MemoryUtil.java:81–84`), i.e. **glibc malloc via JNA, not tracked by NMT** and not
  in the JDK direct-buffer counter. Regions are freed at `setDiscarded` (after flush). The counter K charges
  the allocation sizes; the physical excess over K is at most one partly used region per live memtable plus
  ≤ 8 stashed race regions per size.
- Chunk cache: `ChunkCache` (Caffeine, `maximumWeight = file_cache_size − 32 MiB`, weigher = buffer capacity,
  `ChunkCache.java:49–50,152–154`) over `BufferPools.forChunkCache()` (`BufferPool` "chunk-cache", threshold
  `file_cache_size`, `BufferPools.java:38–39`). Macro chunks are 1 MiB `ByteBuffer.allocateDirect(1 MiB + page)`
  (`BufferPool.java:438–460,1095–1101`), never returned; above the threshold, buffers come from
  `allocateDirect` as overflow (`BufferPool.java:233–239`). Both routes are **Unsafe.allocateMemory →
  os::malloc, tracked by NMT (category Other) and by the JDK `direct` BufferPoolMXBean**.
- Exposed counters (K): `org.apache.cassandra.metrics:type=Table,name=AllMemtablesOffHeapDataSize` (sum of the
  allocators' off-heap `owns`), `type=BufferPool,scope=chunk-cache,name=Size|UsedSize|OverflowSize`,
  `type=Cache,scope=ChunkCache,name=Size|Entries`.

**Protection map (unchanged from section 1, re-verified above).**

| Domain | Control (C) | Counter K | Independent U |
|---|---|---|---|
| Off-heap memtable (JNA malloc) | `memtable_offheap_space` 1200 MiB, hard (writers park) | `AllMemtablesOffHeapDataSize` | ΔRssAnon over the burst minus Δ(JDK direct) (heap is pre-touched and constant): an upper bound on the memtable's resident growth, compared with ΔK. NMT cannot be used (JNA malloc is not tracked, see validation note) |
| Chunk cache (direct) | `file_cache_size` 1200 MiB pool threshold; cache weight ≤ 1168 MiB | `BufferPool chunk-cache Size`, `ChunkCache Size` | JDK `direct` `MemoryUsed` and NMT `Other` (cover all direct buffers; chunk-cache share = total − idle/networking) |
| Rest (heap 768 MiB pre-touched, metaspace, threads, code, GC, load overhead) | none (baseline) | — | NMT categories; RssAnon |
| Budget | cgroup v2 `memory.max` 3500 MiB, `MemorySwapMax=0`, on the JVM only | — | `RssAnon`, `memory.current`/`memory.stat anon`, `memory.events oom_kill`, `dmesg` |

**Harness (minimal changes, diff in [`recheck-2026-11-11/harness.diff`](recheck-2026-11-11/harness.diff)).**
`oom-run.sh` copied to `/mydata/oom-recheck/R1/oom-run.sh`: paths (`C`, `L`) moved to `/mydata/oom-recheck/R1`;
scope prefix `oom-r1-`; added instruments: (a) `-XX:NativeMemoryTracking=summary` via `JVM_EXTRA_OPTS` in every
arm; (b) `tools/PoolPoller.java` — one JMX connection (outside the cgroup), one CSV row every 2 s for the whole
arm (RssAnon, cgroup current/anon/file/events, heap used, JDK direct used/count, chunk-cache pool
Size/Used/Overflow, ChunkCache size/entries, memtable off-/on-heap counters, memks writes, pending flushes,
`BlockedOnAllocation`); (c) `jcmd VM.native_memory summary` at idle, after preload, after cachefill, every 5 s during
the burst and at the end; (d) overhead check: RssAnon at idle, +30 s without the poller, +30 s with it. Workload,
yaml edits, budget, Xmx and sampling of the original are unchanged.

**Instrument validation (`val_modest`, 14:43–14:47, 8000 MiB, not a condition reading).** Paths, yaml edits,
poller columns and NMT work; memtable flushed at `MEMTABLE_LIMIT` with 1.161 GiB (99%) off-heap; chunk cache
filled to 494 MiB on the 100,000-partition set; 300,000-write burst at 20,443 op/s, 0 errors;
`BlockedOnAllocation` 94. Overhead: RssAnon idle → +30 s without poller +2.1 MiB, → +30 s with poller +1.2 MiB.
**Finding that changed this design before any reading:** NMT `Other` rose to 1015 MB during the preload while
JDK direct stayed at 57 MB, and was 1648 MB at the end (JDK direct 637 MB). The ~1 GB extra is Netty's pooled
arenas (`-Dio.netty.allocator.maxOrder=11` → 16 MiB chunks, 2 × cores = 64 arenas on pc96, 80 on pc41) allocated
through `Unsafe.allocateMemory` and largely untouched. NMT counts malloc'd bytes, not resident pages, so
"RssAnon − NMT committed" is not a valid memtable measure; NMT is kept for heap/thread/class/code/GC committed and
as a per-category record only. JDK direct buffers are zeroed at allocation, hence resident: JDK `direct`
`MemoryUsed` is a resident measure for the chunk cache. The arena count is a further environment difference
(fewer arenas on pc96).

**Exact commands** (all arms: budget 3500, `XMX=768M HEAPMEM=200 N_DATA=800000 N_BURST=2000000 BURST_SECS=240
POLL_MS=2000 NMT=summary`, the harness defaults; run sequentially by `run-all.sh`, detached with `setsid nohup`):

```
bash oom-run.sh arm M_alone-<k>   3500 1200   64 memburst
bash oom-run.sh arm F_alone-<k>   3500   64 1200 preload,cachefill
bash oom-run.sh arm converge-<k>  3500 1200 1200 preload,cachefill,memburst
bash oom-run.sh arm int_F300-<k>  3500 1200  300 preload,cachefill,memburst   # intervention
```

Order: `M_alone-1`, `F_alone-1` → **check** (below) → `converge-1`, `M_alone-2`, `F_alone-2`, `converge-2`,
`M_alone-3`, `F_alone-3`, `converge-3`, `int_F300-1..3`.

**Check after the first alone arms.** If either alone peak RssAnon on pc96 is > 85% of 3500 MiB, or idle +
both alone increments (minus a 250 MiB shared-load allowance) is < 3500 MiB, the filed sizing no longer gives
"safe alone + exceeds together": stop and write a dated amendment with new numbers before any converge arm.
Otherwise keep the filed condition unchanged.

**Predictions** (from the filed run; pc96 idle measured 1250 MiB RssAnon in `val_modest`, ~40 MiB below pc41):
- `M_alone`: memtable reaches its cap (flush lines at ~100% off-heap, writers park, `BlockedOnAllocation` > 0),
  peak RssAnon ≈ 2680 ± 100 MiB (≈ 77%), no kill; burst completes 2,000,000 writes in < 240 s.
- `F_alone`: chunk cache at capacity (1.14 GiB), pool Size ≈ 1200 MiB, JDK direct ≈ 1200 + ~50 MiB,
  peak RssAnon ≈ 2680 ± 100 MiB (≈ 77%), no kill.
- `converge`: chunk cache full before the burst (RssAnon ≈ 3050 MiB), then kernel memcg OOM-kill within
  ≈ 10–60 s of the burst start, with memtable counter K well below 1200 MiB at the kill; ΣU + baseline > 3500.
- Margin: the filed alone arms leave ~22%, below the protocol's 30% starting target; disclosed, not changed.

**Intervention (causal).** Lower `file_cache_size` 1200 → **300 MiB** (cache weight 268 MiB), everything else
identical, including the same preload, the same 800,000-read pass and the same 2,000,000-write burst with
`memtable_offheap_space` still 1200 MiB. Chosen over lowering the memtable because the kill comes from the
burst landing on the standing cache: this keeps the allocation path that triggers the kill unchanged. Predicted
peak RssAnon = M_alone peak + chunk pool 300 MiB + up to ~230 MiB of non-shared read-load overhead ≈ 2980–3210
MiB (85–92%), no kill; contract arithmetic idle 1250 + 1200 + 300 + load overhead ~450 ≈ 3200 < 3500. Write
throughput recorded (stress op rate, completed partitions, server `memks` write count) and compared with
`M_alone` (same memtable cap and burst): predicted within ±25%, burst completes. Read-pass completion and
op rate recorded too.

**Endpoint and pass/fail per V1–V5 (one fixed condition: build, yaml, budget, workload above).**
- V1: `converge` ends in a kernel memcg OOM-kill (`dmesg`: `Memory cgroup out of memory: Killed process <node
  PID>` with `oom_memcg` = the arm's scope) in ≥ 3 runs; report n/N; extend to ≤ 5 only for mixed outcomes.
- V2: `M_alone` ×3 and `F_alone` ×3: no kill, no `OutOfMemoryError`, each pool reaches its cap, peak RssAnon
  stated with its margin.
- V3: per domain U (above) ≤ C in `converge`, and ΣU + baseline > budget at the kill (convergence). A domain with
  U > C would make it bypass/mixed instead. Chunk cache: U = JDK direct − idle direct (resident). Memtable: U ≤
  ΔRssAnon(burst) − Δdirect(burst); with the 1 MiB-region allocator, U ≥ K. Alone arms: same measures at each
  pool's own peak.
- V4: `int_F300` ×3: no kill, burst completes at recorded throughput.
- V5: the `dmesg` record (invoking thread, `oom_memcg`, killed PID, anon-rss) plus, ≤ 2 s before it, the
  poller's per-pool row (chunk-cache pool/direct, memtable counter, heap, RssAnon) and the last NMT summary
  (≤ 5 s). A kernel kill leaves no JVM error or dump; the per-pool rows stand in for the histogram.

**Instrument overhead check.** Poller and `jcmd` run outside the cgroup; inside it they add a JMX/attach
thread and some heap garbage. Accept if idle-poll − idle-nopoll RssAnon ≤ 10 MiB and alone peaks are within
±100 MiB of the filed ones; otherwise disclose.

**Stopping budget.** ≤ 7 h wall from 14:40 EST (stop launching new arms after 20:45), ≤ 18 arm executions
including `val_modest` (12 planned + up to 5 extensions). No escalation after an OOM. After every arm and at
the end: no `CassandraDaemon`/`cassandra-stress`/`PoolPoller` left, scope stopped.

**Labels.** Capacities custom (`memtable_offheap_space` 1200, `file_cache_size` 1200, `memtable_heap_space` 200);
`memtable_allocation_type: offheap_objects` and `file_cache_enabled: true` are documented values. Budget:
deliberately tightened diagnostic cgroup 3500 MiB, `-Xmx768M`. Supporting deviation: `memtable_cleanup_threshold:
0.99` (deprecated; parks writers at the limit). Environment: pc96 instead of pc41; NMT and JMX poller added.
Expected status if V1–V5 hold: `verified-OOM · diagnostic`.

**Check after the first alone arms (2026-11-11 15:03, before any converge reading): passed, filed condition
kept.** `M_alone-1` peak RssAnon 2660 MiB (76.0%; idle 1261, increment 1399), `F_alone-1` 2670 MiB (76.3%; idle
1243, increment 1427); both < 85%, and 1250 + 1399 + 1427 − 250 = 3826 MiB > 3500. Harness hygiene fix applied
from the next arm on (no effect on the measurement): process matching tightened from `[o]rg.apache…` to
`^(/usr/bin/)?java .*org[.]apache…` so that other agents' shell commands on pc96 mentioning those class names can
never be matched or killed.

**Amendment (2026-11-11 17:20, before the reading).** One supplementary arm `converge-noinst` to check that the
instrumentation does not change the outcome: same condition as `converge`, but `NMT=off` (no
`-XX:NativeMemoryTracking`, no `jcmd`) and `POLL_MS=0` (no JMX poller; the harness gains only a switch to skip it).
The original 5 s `/proc` + cgroup sampling and `nodetool` readings stay, as in the filed run. Prediction: kernel memcg
OOM-kill within ≈ 5–20 s of the burst start, as in `converge-1..3`. It is a diagnostic check, not counted in V1. It is
the 14th of at most 18 arm executions.
