# memtable_offheap_space + file_cache_size — convergence case (run 7)

> **Run:** 2026-11-03, node `node0.jason92-323989.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB), same build as runs 1-6 (`~/cassandra-run1`, cassandra-5.0.9, unchanged). Second off-heap pair; both constraints are new to OOM-exp.
>
> **Harness:** [`memtable_offheap_space+file_cache_size/`](memtable_offheap_space+file_cache_size/) (`oom-run.sh`; per-arm summaries, yaml diffs, final readings, stress outputs, the `M_alone` memtable flush lines and the converge arm's `dmesg` kill lines). Per-5-s samples stay on the node in `~/oom-offheap-run7/logs/`.
>
> **Outcome: OOMed.** Each pool alone stayed at 78% of a 3500 MiB cgroup budget. Together, the kernel OOM-killed the JVM 16 s into the write burst (`MutationStage-5` invoked the killer; anon-rss 3465 MiB). Clean case: same budget for every arm, kill attributed by scope and PID.

## 1. Constraints and capacities

| | `memtable_offheap_space` | `file_cache_size` |
|---|---|---|
| if-check-exp | [`memtable_offheap_space-tryAllocate-limit--guided`](../../../../if-check-exp/cassandra/stage3-ai-deep-read/cases/memtable_offheap_space-tryAllocate-limit--guided.md), true positive (also the set-B autonomous `applySimpleConfig` case) | [`file_cache_size-allocateMoreChunks-memoryUsageThreshold--guided`](../../../../if-check-exp/cassandra/stage3-ai-deep-read/cases/file_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md), true positive ("confirmed for the pool") |
| What it caps | Off-heap memtable bytes: with `memtable_allocation_type: offheap_objects`, `NativeAllocator` takes 1 MiB regions via `MemoryUtil.allocate` (malloc); writers park at the limit | The chunk-cache `BufferPool`: direct macro chunks up to `file_cache_size`, never released once reserved; with `file_cache_enabled: true`, `ChunkCache` (Caffeine, `maximumWeight = file_cache_size − 32 MiB`) holds its buffers |
| Standing pool? | Yes: the memtable sits near the limit under sustained writes (`memtable_cleanup_threshold: 0.99`), and glibc keeps freed regions, so `RssAnon` does not fall at a flush (if-check-exp finding) | Yes: a cache, plus a pool whose reservation is kept |
| Setting here | 1200 MiB | 1200 MiB (cache capacity 1.14 GiB) |
| Budget mechanism | Neither is bound by `-Xmx`; the budget is a cgroup v2 `memory.max` on the whole JVM, as in runs 4-6, read as `RssAnon` | same |

Fixed settings in every arm: `-Xmx768M`, `memtable_heap_space: 200MiB` (raised from runs 4-6 to avoid run 6's heap OOM), `memtable_cleanup_threshold: 0.99`, `memtable_allocation_type: offheap_objects`, `file_cache_enabled: true`, budget via `systemd-run --user --scope -p MemoryMax=… -p MemorySwapMax=0`.

## 2. Verification solution

**Workloads.** *preload*: `cassandra-stress write` 800,000 partitions (5 × 1 KiB columns) into `dataks`, flushed, autocompaction disabled. *cachefill*: one read pass over all 800,000 partitions, 64 threads. *memburst*: `cassandra-stress write` up to 2,000,000 partitions into `memks`, 64 threads, 50 retries/op, capped at 240 s.

**Calibration (8000 MiB budget, 600 MiB per pool):** memtable alone +865 MiB, chunk cache alone +808 MiB, both +1536 MiB (92% of the sum) over an idle of about 1300 MiB. About 250 MiB of growth comes from the write load itself (networking buffers, glibc arenas) and is counted once when both run, so at 600 MiB no budget gave both "safe alone" and "exceeds together". Both pools were doubled to 1200 MiB and the dataset to 800,000 partitions.

**Arms (3500 MiB budget in all):** `M_alone` (M = 1200, F = 64, memburst), `F_alone` (M = 64, F = 1200, preload + cachefill), `converge` (M = F = 1200, preload, then cachefill, then memburst: the standing cache first, then the burst, the order run 6 found decisive).

**Prediction:** idle 1290 + 1425 (M alone) + 1432 (F alone) ≈ 4147 MiB (118%) naive; with calibration's 8% overlap discount ≈ 3920 MiB (112%).

## 3. Runtime results

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

## 4. Conclusion

**The pair converges to a real OOM.** Each pool, driven to its own cap alone, left 22% of the budget free; with the chunk cache parked at its cap, the off-heap memtable's first fill pushed the process past the budget, and the kernel killed it from a write thread allocating memtable memory. The kill came well before the memtable reached its 1200 MiB limit: the chunk cache's standing 1.14 GiB, plus the pool and load overhead, left less room than the memtable's own cap.

**Comparison with the first off-heap pair (runs 4-6).** That pair needed engineered timing: the index-summary cap bounds summaries only at a periodic resize, so the overshoot was a transient, and only one schedule killed the node. Here both constraints are hard, standing caps, so the arithmetic alone predicts the outcome; the simple order (fill the cache, then write) was enough on the first try.

**Target-3 note.** This is the most realistic off-heap case so far: two documented yaml knobs an operator might set together when moving memory off-heap ("memtables off-heap at 1.2 GiB, chunk cache at 1.2 GiB"), each sized safely against the node on its own, plus a normal read-then-write workload. The supporting settings are less natural: `memtable_cleanup_threshold: 0.99` (deprecated, used here to park writers at the limit; the default 0.33 flushes earlier) and the cgroup budget standing in for a container limit. The kill happened during the memtable's first fill, so a lower cleanup threshold might delay it but would not change the sum the two caps allow.

## Instrument check and process hygiene

- Kill attribution from `dmesg`: `oom_memcg` equals this arm's scope unit, killed PID equals the node PID in `summary.txt`.
- Both caps confirmed reached in their alone arms from Cassandra's own readings (flush `Usage: … 1.172GiB (100%) off-heap`; `nodetool info` chunk cache size = capacity).
- The "JVM OOM lines: 1" in the calibration summaries is a grep false positive (a `CompileCommand` line naming `OutOfMemoryError`); the grep was tightened before the 1200 MiB arms, which all report 0.
- `memory.current` sits at `memory.max` under load in every arm because page cache counts toward it; `RssAnon` is the reading, `oom_kill`/`dmesg` the outcome signal (as in runs 4-6).
- After every arm, `pgrep` for `CassandraDaemon` and `cassandra-stress` was empty and the scope unit stopped. Data, commit log and logs stayed under `~/cassandra-run1` on local disk; nothing written to `/proj`; the repository's `systems/cassandra/source/` untouched.
