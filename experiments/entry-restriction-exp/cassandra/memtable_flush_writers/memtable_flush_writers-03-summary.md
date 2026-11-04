# memtable_flush_writers — Pair 03 · Summary

> **Codepath:** [memtable_flush_writers-03-codepath.md](memtable_flush_writers-03-codepath.md) · **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

**Formatting note:** Link every code reference (`` `File.java:NN` `` or `` `Class.method():NN` ``) to the pinned source on GitHub. Use the format: `` [`File.java:NN`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/<path>#LNN) `` (ranges use `#LNN-LMM`). Place the link *outside* the backticks so code renders as clickable text.

## Identity

| Field | Content |
|-------|---------|
| **Entry Point ID** | MEMTABLE_FLUSH_WRITERS |
| **Name** | memtable_flush_writers (per-disk pool contention) |
| **Type** | Implicit / distributed constraint (one thread pool per data directory) |
| **Declaration Location** | [`Config.java:185`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L185) (`memtable_flush_writers`) — the same parameter sizes **each** per-disk pool independently |
| **Default Value** | `flushWriters` per pool = `data_file_directories.length == 1 ? 2 : 1` ([`DatabaseDescriptor.java:755`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L755)); pool **count** = number of data directories (not tunable independently) |
| **Value Type / Size** | `ExecutorPlus[]` — array of `N` pools, each with `flushWriters` threads and a queue sized `Integer.MAX_VALUE` (unbounded) |
| **Description** | One flush thread pool is created per data directory. A memtable flush is split into one `FlushRunnable` per directory and each is dispatched to its matching per-disk pool; there is no global coordination or aggregate cap across the pools. |
| **Restriction Location** | [`ColumnFamilyStore.PerDiskFlushExecutors`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3474) — per-disk executor array construction ([`createPerDiskFlushWriters():3503-3511`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3503-L3511)) |
| **Pair** | 03 of 03 |

**Restriction character:** Distributed per-disk thread-pool array — the constraint is applied *per directory* with no global (cross-disk) coordination, so the slowest disk gates every flush and its unbounded queue holds memory for the whole node.

## Key Decision Points

_Critical nodes in the distributed enforcement chain (full trace lives in the codepath file). This constraint follows an init → route → per-pool → block → cascade pattern rather than a single check._

1. **pool-array-init:** [`ColumnFamilyStore.java:219-222`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L219-L222) — static `perDiskflushExecutors` built at daemon init from `getFlushWriters()` and the data-directory list
2. **per-disk-pool-creation:** [`ColumnFamilyStore.java:3503-3511`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3503-L3511) — one `pooled(name, flushWriters)` pool per directory, each with its own unbounded queue (inherits Pair 02)
3. **memtable-split:** [`Flushing.java:57-91`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/Flushing.java#L57-L91) — memtable divided by `DiskBoundaries` into one `FlushRunnable` per directory
4. **per-disk-dispatch:** [`ColumnFamilyStore.java:1302-1305`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1302-L1305) — runnable `i` submitted to per-disk pool `i` (`executors[i].submit(...)`)
5. **block-on-all-disks:** [`ColumnFamilyStore.java:1316`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1316) — `FBUtilities.waitOnFutures(futures)` blocks the orchestrator until **every** disk finishes; the whole memtable is retained until then
6. **no-global-cap:** no code path sums queued/in-flight bytes across the `N` per-disk pools or compares that aggregate to `memtable_heap_space`

## Enforcement

| Field | Content |
|-------|---------|
| **Enforcement Point** | Per-disk pool array created at [`ColumnFamilyStore.java:3503-3511`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3503-L3511); routing at [`getExecutorsFor():3525-3529`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3525-L3529); blocking join at [`ColumnFamilyStore.java:1316`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1316) |
| **Action on Breach** | None per-pool (queue is unbounded). Systemic effect: the flush orchestrator blocks on the slowest disk (`waitOnFutures`), so the memtable's memory is released only after the slowest per-disk runnable completes; slow disk → delayed reclamation → more triggered flushes → queues grow on all pools. |

## Failure Mode Analysis

| Mode | Status (✓/✗/⚠) | Notes |
|------|-----------------|-------|
| **Proxy Match** | ✗ | The parameter sizes each pool by **thread count per directory**, a proxy for neither per-disk throughput nor node-wide memory. Total flush concurrency is `flushWriters × N` threads, but held memory is bounded only by the sum of `N` unbounded queues plus in-flight `FlushRunnable`s — a quantity the constraint never measures. One slow disk decorrelates thread count from drain rate entirely. |
| **Enforcement Point** | ✗ | No global enforcement across pools. Each pool inherits Pair 02's unbounded queue (no per-pool depth check), and nothing aggregates memory across pools against `memtable_heap_space`. Because `waitOnFutures` (line 1316) blocks on all disks and the memtable is explicitly not freed incrementally ([`Flushing.java:155-157`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/Flushing.java#L155-L157)), the slowest disk pins the entire memtable in heap. |
| **Default State** | ✗ | Default `flushWriters` is **1 per pool** for any multi-directory node ([`DatabaseDescriptor.java:755`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L755)) — the very configuration that creates multiple per-disk pools gets the *fewest* threads each. Pool count is dictated by disk layout, not by a resource budget, and has no upper bound. |

## Related / Dependent Constraints

- **`memtable_flush_writers`** (Pair 01) — Same parameter; Pair 01 covers the thread-count soft limit and auto-sizing. Pair 03 shows that this single value is applied *independently to every disk*, so its multi-directory default of 1 is the worst case here.
- **`memtable_flush_writers` unbounded queue** (Pair 02) — Each per-disk pool is built by the same `pooled()` factory chain, so every pool carries a queue sized `Integer.MAX_VALUE`. Pair 03 = Pair 02 replicated `N` times with no aggregate cap.
- **`memtable_heap_space`** (memtable_heap_space Pair 01/02) — Global `SubPool` cap. Reclamation of a memtable's bytes is deferred until the slowest disk's runnable completes, so a slow disk keeps `SubPool.used` high, pushing `needsCleaning()` to trigger still more flushes into the already-backed-up pools.
- **`memtable_cleanup_threshold`** — Auto-derived as `1/(1+flushWriters)` ([`DatabaseDescriptor.java:763`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L763)); with the multi-dir default of 1 → 0.5, so flushes trigger early and often, feeding the per-disk queues faster.

## Bypass Potential (Target 3 seed)

**Primary Bypass: Single Slow Disk → Node-Wide Memory Exhaustion**
- Setup: multi-directory node (≥2 `data_file_directories`), default `flushWriters=1` per pool, one disk with elevated I/O latency (degraded SSD, noisy-neighbor volume, RAID rebuild, thermal throttling).
- Mechanism: every memtable flush is split across all disks and the orchestrator blocks on the slowest via `waitOnFutures`. The slow disk's single-threaded pool drains slower than flushes arrive; its unbounded queue accumulates `FlushRunnable`s, each holding its share of a memtable. Because the memtable is not freed incrementally, memory for **all** disks' portions of each in-flight memtable is retained until the slow disk finishes.
- Overshoot: total held memory = Σ over disks of (queued + in-flight runnable bytes); dominated by the slow disk's growing backlog. `memtable_heap_space` never caps this aggregate, so heap can climb well past the configured limit before OOM.

**Secondary Bypass: Orchestrator Thread Starvation**
- `flushExecutor` (the orchestrator pool) is sized `getFlushWriters()` too. Each orchestrator thread stays blocked in `waitOnFutures` for the duration of the slowest disk. With the multi-dir default of 1, a single slow disk can occupy the lone orchestrator thread, stalling *all* flushes node-wide (including for fast disks), which further delays reclamation and accelerates queue growth.

**Attack Vectors:**
- **Targeted slow-disk induction:** drive I/O contention on one volume (heavy compaction, external load, or a workload skewed to one disk's token range) to throttle one per-disk pool.
- **Directory-skew attack:** craft writes whose `DiskBoundaries` concentrate on one directory, overloading a single pool while others idle.
- **Compounding with Pair 01/02:** default 1 thread per pool + unbounded per-pool queue + early cleanup threshold (0.5) maximizes the rate at which the slow pool's backlog grows.

## Verification

| Field | Content |
|--------|---------|
| **Status** | verified |
| **Verified By / Date** | Code review against `cassandra-5.0.9` tag (2026-09-09). Traced `PerDiskFlushExecutors` construction, per-directory memtable split in `Flushing.flushRunnables`, per-disk dispatch and blocking join in `ColumnFamilyStore.Flush.flushMemtable`, and the deferred-reclaim comment in `Flushing.writeSortedContents`. |
| **Notes** | The distributed constraint is *implicit*: there is no config named "per-disk pools." The number of pools follows `data_file_directories`, and each is sized by the single `memtable_flush_writers` value. No aggregate memory accounting exists across pools. |

---

## Notes

- **Why this is a distinct pair from 02:** Pair 02 documents the unbounded queue on the *global* `flushExecutor` / a single pool. Pair 03 documents the *array* of per-disk pools and the cross-disk coordination gap: even if a single pool's queue were bounded, the lack of a global cap plus the blocking `waitOnFutures` slow-disk coupling would remain.
- **Monitoring nuance:** per-disk pools are created via `withJmxInternal().pooled(...)`, so each pool *does* expose pending/active/completed counts over JMX (e.g. `PerDiskMemtableFlushWriter_0`). The gap is not raw per-pool visibility but the absence of any **aggregate** queued-bytes metric and any enforcement that acts on it.
- **System vs non-system keyspaces:** `getExecutorsFor()` routes local system keyspaces to a separate pool only when `useSpecificLocationForLocalSystemData()` is set; otherwise they share disk-0's pool ([`ColumnFamilyStore.java:3499-3500`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3499-L3500)), adding load to one pool.

---

## Correction Log

- 2026-09-10: Verified against local `cassandra-cassandra-5.0.9` clone and corrected three citation errors: (1) `Config.java` declaration line 184 → **185**; (2) Key Decision Point 3 `Flushing.java` range 70-91 → **57-91** (`flushRunnables()` actually starts at line 57); (3) Failure Mode "Enforcement Point" row cited `Flushing.java:150-152` for the "can't clear out the map as-we-go" comment — actual line is **155-157**.
