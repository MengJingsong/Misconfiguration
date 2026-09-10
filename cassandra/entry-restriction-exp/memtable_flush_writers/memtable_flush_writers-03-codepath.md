# memtable_flush_writers — Pair 03 · Full Code Path

> **Summary:** [memtable_flush_writers-03-summary.md](memtable_flush_writers-03-summary.md) · **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

**Pair:** memtable_flush_writers-03 (per-disk pool contention — distributed constraint, one flush pool per data directory)
**Entry Point Location:** [`Config.java:185`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L185) (`memtable_flush_writers`)
**Restriction Enforcement:** [`ColumnFamilyStore.PerDiskFlushExecutors`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3474) → per-disk executor array (`createPerDiskFlushWriters`, per-disk dispatch, blocking join)

---

## Full Continuous Code Path

Unbroken trace from the config value → auto-sizing → per-disk pool **array** construction → memtable split by disk → per-disk dispatch → blocking join across all disks → deferred reclamation → cross-disk memory accumulation. Stages are specific to a **distributed / per-directory** constraint. Shared prefix steps (config read, auto-sizing, unbounded-queue factory) are repeated here so this file stands alone.

| Step | Stage | Location (`Class.method:line`) | What happens | Value / State |
|------|-------|--------------------------------|--------------|---------------|
| 1 | config-declaration | [`Config.java:185`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L185) | `memtable_flush_writers` field declared | default `0` (sentinel for auto-size) |
| 2 | auto-sizing | [`DatabaseDescriptor.java:753-755`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L753-L755) | If `0`, set to `data_file_directories.length == 1 ? 2 : 1` | **multi-directory → 1 thread per pool** |
| 3 | validation | [`DatabaseDescriptor.java:758-759`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L758-L759) | Reject `< 1`; **no upper bound**, and no bound relative to disk count | `flushWriters ≥ 1` |
| 4 | derived-threshold | [`DatabaseDescriptor.java:763`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L763) | `memtable_cleanup_threshold = 1/(1+flushWriters)` | with `flushWriters=1` → `0.5` (flush at 50%) |
| 5 | pool-array-field | [`ColumnFamilyStore.java:219-222`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L219-L222) | Static `perDiskflushExecutors` built at daemon init from `getFlushWriters()` + non-local-system data-file locations | one `PerDiskFlushExecutors` for JVM lifetime |
| 6 | constructor | [`ColumnFamilyStore.java:3492-3501`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3492-L3501) | Builds `nonLocalSystemflushExecutors` array; system pool is separate only if `useSpecificLocationForLocalSystemData()`, else shares `flushExecutors[0]` | `N` non-system pools (+ maybe 1 system pool) |
| 7 | per-disk-pool-creation | [`ColumnFamilyStore.java:3503-3511`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3503-L3511) | Loop over directory count: `flushExecutors[i] = newThreadPool("PerDiskMemtableFlushWriter_"+i, flushWriters)` | array length = number of data directories |
| 8 | unbounded-queue-factory | [`ColumnFamilyStore.java:3513-3516`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3513-L3516) → [`ThreadPoolExecutorBuilder.newQueue():159-167`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/ThreadPoolExecutorBuilder.java#L159-L167) | `newThreadPool` → `executorFactory().withJmxInternal().pooled(poolName, size)` — same factory chain as Pair 02 | each pool: `flushWriters` threads + queue sized `Integer.MAX_VALUE` (unbounded) |
| 9 | flush-orchestrator-start | [`ColumnFamilyStore.java:1039`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1039) | `flushExecutor.execute(flush)` submits the `Flush` orchestrator (global pool, also sized `flushWriters`) | orchestrator queued/run on `MemtableFlushWriter` pool |
| 10 | memtable-switch-hold | [`ColumnFamilyStore.java:1229-1246`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1229-L1246) | `Flush.run()` awaits write barrier, then `markFlushing` moves old memtable to the "pending flush" set (still in heap) | memtable bytes still allocated, awaiting flush |
| 11 | memtable-split | [`Flushing.java:57-91`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/Flushing.java#L57-L91) | `flushRunnables()` uses `DiskBoundaries` to cut the memtable into one `FlushRunnable` per directory (`locations.get(i)`) | `runnables.size()` == directory count |
| 12 | per-disk-executor-lookup | [`ColumnFamilyStore.java:1302`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1302) | `executors = perDiskflushExecutors.getExecutorsFor(ks, table)` | non-system → the `N`-pool array |
| 13 | per-disk-dispatch | [`ColumnFamilyStore.java:1304-1305`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1304-L1305) | `for i: futures.add(executors[i].submit(flushRunnables.get(i)))` — runnable `i` → pool `i` | each disk's slice enqueued on its own pool (unbounded) |
| 14 | routing-rule | [`ColumnFamilyStore.java:3525-3529`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3525-L3529) | `getExecutorsFor` sends local system keyspaces to the system pool (if configured), all others to the shared array | shared array serves every user table |
| 15 | block-on-all-disks | [`ColumnFamilyStore.java:1316`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1316) | `FBUtilities.waitOnFutures(futures)` — orchestrator blocks until **every** per-disk runnable completes | completion time = **max** over disks (slowest gates) |
| 16 | deferred-reclaim | [`Flushing.java:155-157`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/Flushing.java#L155-L157) | Comment + logic: map is **not** cleared as-we-go (memtable still serving pending-flush reads); whole memtable retained | no partial release; all disks' slices held until step 17 |
| 17 | reclaim | [`ColumnFamilyStore.java:1391`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1391) | After successful flush of all slices, `reclaim(memtable)` frees the memtable's `SubPool` bytes | `SubPool.used` decremented only now (after slowest disk) |
| 18 | no-aggregate-cap | [`ColumnFamilyStore.PerDiskFlushExecutors`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3474) | No code sums queued/in-flight bytes across the `N` pools or compares to `memtable_heap_space` | cross-disk memory grows unmonitored/unbounded |

---

## Path Continuity Notes

### Distributed constraint: one pool per directory

The number of per-disk pools is not a tunable resource budget — it equals the number of `data_file_directories`. The single `memtable_flush_writers` value is applied **independently** to each pool:

```java
// ColumnFamilyStore.createPerDiskFlushWriters():3503-3511
private static ExecutorPlus[] createPerDiskFlushWriters(int numberOfExecutors, int flushWriters)
{
    ExecutorPlus[] flushExecutors = new ExecutorPlus[numberOfExecutors]; // one per directory
    for (int i = 0; i < numberOfExecutors; i++)
    {
        flushExecutors[i] = newThreadPool("PerDiskMemtableFlushWriter_"+i, flushWriters); // same size each
    }
    return flushExecutors;
}

// newThreadPool():3513-3516 — same factory chain as Pair 02 (ExecutorFactory.pooled() -> ThreadPoolExecutorBuilder)
private static ExecutorPlus newThreadPool(String poolName, int size)
{
    return executorFactory().withJmxInternal().pooled(poolName, size); // queue sized Integer.MAX_VALUE in ThreadPoolExecutorBuilder.newQueue()
}
```

Total flush threads on the node = `flushWriters × N`, but each *disk* still has only `flushWriters` threads. With the multi-directory default (`flushWriters = 1`), every disk is served by a **single** thread draining an **unbounded** queue.

### Split-and-join: the slowest disk gates the flush

A memtable is divided by `DiskBoundaries` into one runnable per directory, dispatched to the matching pool, then the orchestrator blocks on all of them:

```java
// ColumnFamilyStore.Flush.flushMemtable():1300-1316 (abridged)
flushRunnables = Flushing.flushRunnables(cfs, memtable, txn);              // one runnable per directory
ExecutorPlus[] executors = perDiskflushExecutors.getExecutorsFor(ks, name);
for (int i = 0; i < flushRunnables.size(); i++)
    futures.add(executors[i].submit(flushRunnables.get(i)));              // runnable i -> pool i
...
flushResults = Lists.newArrayList(FBUtilities.waitOnFutures(futures));    // block until ALL disks done
```

Because `waitOnFutures` waits for the maximum, one slow disk stretches the whole flush. And per `Flushing.writeSortedContents()`:

```java
// Flushing.java:155-157
// (we can't clear out the map as-we-go to free up memory,
//  since the memtable is being used for queries in the "pending flush" category)
```

...the memtable is **not** freed incrementally, so all disks' portions stay resident until the slow disk finishes and `reclaim()` runs (step 17). Fast disks finish early but their memory is not returned any sooner.

### Slow-disk cascade timeline (multi-dir default: flushWriters=1, 4 directories, disk 3 slow)

```
Steady state: disks 0-2 drain each flush slice in ~500 ms; disk 3 drains in ~5 s (10x slower).

T=0s   memtable A switched out; split into slices A0..A3, dispatched to pools 0..3.
       Orchestrator thread blocks in waitOnFutures until A3 (disk 3) finishes.
T=0.5s A0,A1,A2 written — but memtable A NOT reclaimed (waiting on A3).
T=1s   SubPool still counts A (reclaim deferred) → needsCleaning() stays true →
       cleanup triggers memtable B flush → B0..B3 dispatched.
       Pool 3 queue now holds A3(running) + B3(queued).
T=2-5s More memtables (C, D, ...) triggered because reclamation lags the slow disk.
       Pool 3 queue: A3, B3, C3, D3, ... grows ~1 slice / cleanup interval; queue unbounded.
       Held memory = A + B + C + D + ... (all slices of every in-flight memtable), because
       each memtable is retained whole until ITS slowest slice (always disk 3) completes.
T=Ns   Σ held bytes climbs past memtable_heap_space; no aggregate check fires. → OOM risk.

Compounding: flushExecutor (orchestrator) is also sized flushWriters=1, so its single
thread is stuck in waitOnFutures on the slow disk — new Flush orchestrators queue behind it,
delaying reclamation of already-flushed fast-disk work even further.
```

### Relationship to Pairs 01 and 02

- **Pair 01** (thread-count soft limit / auto-sizing): supplies the per-pool thread count. Its multi-directory default of `1` is the input that makes each per-disk pool single-threaded — worst case for this pair.
- **Pair 02** (unbounded queue): each per-disk pool is created by the same `ExecutorFactory.pooled()` → `ThreadPoolExecutorBuilder` chain, so Pair 02's unbounded queue sizing exists `N` times over. Pair 03 adds the cross-disk dimension Pair 02 does not cover: the **array** of pools, the split/blocking-join coupling, and the absence of any aggregate cap.

### What would close the gap (not present in 5.0.9)

- A global (cross-pool) accounting of queued + in-flight flush bytes, compared against `memtable_heap_space`, with backpressure when exceeded.
- Per-disk pool sizing proportional to disk throughput rather than a single flat `flushWriters`.
- Decoupling reclamation so fast disks' slices are released without waiting on the slow disk (would require the memtable to not serve pending-flush reads as one unit).

## Key Code References

| Stage | File | Lines | What | Purpose |
|-------|------|-------|------|---------|
| 2-4 | [`DatabaseDescriptor.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L753-L763) | 753-763 | Auto-size (1 per pool for multi-dir), validate (no upper bound), derive cleanup threshold | Sets per-pool thread count and flush cadence |
| 5-6 | [`ColumnFamilyStore.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L219-L222) | 219-222, 3492-3501 | `perDiskflushExecutors` field + constructor | Builds the per-disk pool array at daemon init |
| 7-8 | [`ColumnFamilyStore.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3503-L3516) / [`ThreadPoolExecutorBuilder.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/ThreadPoolExecutorBuilder.java#L159-L167) | CFS 3503-3516; builder 159-167 | `createPerDiskFlushWriters` + `newThreadPool`, backed by `ThreadPoolExecutorBuilder.newQueue()` | One unbounded-queue pool per directory, each sized `flushWriters` |
| 11 | [`Flushing.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/Flushing.java#L57-L91) | 57-91 | `flushRunnables` splits memtable by `DiskBoundaries` | One runnable per directory |
| 12-15 | [`ColumnFamilyStore.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1302-L1316) | 1302-1316 | Lookup, per-disk dispatch, blocking `waitOnFutures` | Runnable i → pool i; orchestrator blocks on slowest disk |
| 14 | [`ColumnFamilyStore.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3525-L3529) | 3525-3529 | `getExecutorsFor` routing | System vs non-system pool selection |
| 16-17 | [`Flushing.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/Flushing.java#L155-L157), [`ColumnFamilyStore.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1391) | 155-157, 1391 | Deferred (non-incremental) release; `reclaim()` | Whole memtable held until slowest slice, then freed |

---

## Memory / Resource Impact

**Resource Allocated:** Heap (or off-heap, per `memtable_allocation_type`) memtable memory, retained as queued/in-flight `FlushRunnable` slices across all per-disk pools.

**When Allocated:** At memtable switch (`markFlushing`, step 10) the old memtable is moved to the pending-flush set; its bytes remain accounted in the `SubPool` until reclamation.

**When Released:** Only at `reclaim(memtable)` (step 17), which runs after `waitOnFutures` (step 15) confirms **every** per-disk slice has been written. There is no per-slice/per-disk early release.

**Synchronization:** The orchestrator (`flushExecutor` thread) is synchronous with respect to the flush — it blocks in `waitOnFutures`. Per-disk work is asynchronous across pools but joined at the barrier.

**Timing Problem (overshoot):** Reclamation latency equals the **slowest** disk's completion time. A single slow disk (a) keeps each memtable's full byte count allocated longer, (b) causes `needsCleaning()` to keep firing (deferred reclaim → high `SubPool.used`), triggering more flushes, and (c) accumulates an unbounded backlog in the slow pool's queue. Held memory = Σ over all in-flight memtables of their full size, gated by the slow disk — a quantity `memtable_heap_space` does not bound because it caps per-`SubPool` *live* allocation, not queued+in-flight flush backlog summed across pools.

**Relationship to other constraints:** Directly compounds Pair 01 (per-pool thread count, default 1) and Pair 02 (unbounded per-pool queue), and defeats the intent of `memtable_heap_space` (Pairs mh-01/02) by deferring the reclamation that would keep `SubPool.used` under the cap.

---

## Uncertainties and Open Questions

- **`DiskBoundaries` skew:** how evenly are partitions distributed across directories in practice? A token range concentrated on one disk would overload a single pool even without that disk being physically slow. (Boundary computation lives in `DiskBoundaryManager`; not traced here.)
- **Off-heap accounting:** with `memtable_allocation_type = offheap_buffers/offheap_objects`, the retained slices consume native memory; does deferred reclamation there risk native OOM before JVM heap pressure is visible? (Cross-references the `memtable_allocation_type` candidate entry point.)
- **Commit log coupling:** queued/in-flight flush slices hold `CommitLogPosition` bounds; a slow disk delaying flush completion may pin commit log segments from being recycled, potentially cascading into commit-log-directory pressure before heap OOM. (Untraced.)
- **System-keyspace pool sharing:** when `useSpecificLocationForLocalSystemData()` is false, local system keyspaces share `flushExecutors[0]`; quantify how much extra load this places on disk-0's pool under mixed workloads.
- **`waitOnFutures` failure handling:** on one slice failing, `abortRunnables` aborts the rest — confirm no partial-write memory is leaked vs. reclaimed on the abort path (step at [`ColumnFamilyStore.java:1319-1330`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1319-L1330)).

---

## Correction Log

- 2026-09-10: Verified against the local `cassandra-cassandra-5.0.9` clone and corrected three citation errors:
  1. `Config.java` entry-point line: 184 → **185** (line 184 is blank).
  2. Step 8 / "unbounded-queue-factory": previously implied the queue was constructed inside `ColumnFamilyStore.java` alone; added the actual downstream location, `ThreadPoolExecutorBuilder.newQueue():159-167`, which is where the `Integer.MAX_VALUE` sizing decision is made (same fix as Pair 02).
  3. `Flushing.java` step 11 range: 70-91 → **57-91** (method actually starts at line 57); step 16 comment location: 150-152 → **155-157** (actual line of the "can't clear out the map as-we-go" comment).
