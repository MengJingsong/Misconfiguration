# memtable_flush_writers — Pair 02 · Full Code Path

> **Summary:** [memtable_flush_writers-02-summary.md](memtable_flush_writers-02-summary.md) · **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

**Entry point:** memtable_flush_writers  
**Restriction location (this pair):** `ExecutorPlus.pooled():line` — hardcoded unbounded LinkedBlockingQueue factory

---

## Full Continuous Code Path

Unbroken trace from executor factory definition through queue initialization, task submission, and absence of enforcement checks. This pair documents the **unbounded queue capacity** as a separate restriction location from Pair 01 (thread pool sizing). Stages are specific to hardcoded factory defaults and queue behavior rather than configuration parameters.

| Step | Stage | Location (`Class.method:line`) | What happens | Value / State |
|------|-------|--------------------------------|--------------|---------------|
| 1 | factory-definition | [`ExecutorPlus.pooled():~100-150`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/ExecutorPlus.java#L100) | `pooled(name, threads)` method creates ThreadPoolExecutor with hardcoded queue type; no capacity parameter exists | `new LinkedBlockingQueue<>()` with default capacity = `Integer.MAX_VALUE` |
| 2 | queue-instantiation | [`LinkedBlockingQueue():constructor`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/ExecutorPlus.java#L115) | Default constructor invoked; initializes capacity field | `capacity = 2^31 - 1 (Integer.MAX_VALUE)` |
| 3 | global-pool-creation | [`ColumnFamilyStore:206-210`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L206) | Static final executor created via `executorFactory().pooled("MemtableFlushWriter", getFlushWriters())` | `flushExecutor` assigned with 1 or 2 threads (from Pair 01) and unbounded queue |
| 4 | executor-assignment | [`ColumnFamilyStore:206`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L206) | Static final field assignment; executor persists for JVM lifetime | Pool configuration fixed at daemon init; thread count and queue cannot change at runtime |
| 5 | task-submission | [`ColumnFamilyStore:1033-1043`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1033) | `flushExecutor.execute(flush)` called for each memtable flush; delegates to ThreadPoolExecutor | Flush task enqueued or executed immediately depending on thread availability |
| 6 | thread-pool-check | [`ThreadPoolExecutor.execute():implicit`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/ExecutorPlus.java#L100) | Check if thread available; if `getPoolSize() < corePoolSize`, create worker thread | If no thread: falls through to queue check |
| 7 | queue-offer | [`LinkedBlockingQueue.offer():implicit`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/ExecutorPlus.java#L115) | `queue.offer(task)` called; unbounded queue always accepts (no capacity check) | Returns `true`; task enqueued; no backpressure or rejection |
| 8 | no-rejection | [`ThreadPoolExecutor.execute():implicit`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/ExecutorPlus.java#L100) | Rejection policy `AbortPolicy` defined but never triggered because queue never rejects | Write proceeds immediately; caller unaware queue is building up |
| 9 | per-disk-pool-creation | [`ColumnFamilyStore:3492-3510`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3492) | Array of per-disk executors created; each pool calls `pooled(name, flushWriters)` | N independent executors (one per data directory), each with unbounded queue |
| 10 | per-disk-dispatch | [`ColumnFamilyStore:~1000-1200`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1033) | Task routed to disk-specific pool based on table location; each pool's `execute()` uses same unbounded queue logic | Per-disk queues accumulate independently; one slow disk blocks its own queue |
| 11 | queue-depth-no-check | [`ExecutorPlus / ThreadPoolExecutor:implicit`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/ExecutorPlus.java#L100) | No code path checks `queue.size()` against any threshold; no alarm, no backpressure, no metric | Queue grows unbounded with no enforcement |
| 12 | queue-execution-fifo | [`Flush.run():1175-1230`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1175) | Thread picks task from head of queue; runs `Flush.run()` which writes memtable to disk (100-2000ms typically) | Memtable held in memory until task execution; memory freed only after flush completes |
| 13 | memory-hold-duration | [`LinkedBlockingQueue / Flush:implicit`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/ExecutorPlus.java#L115) | Queued memtables remain referenced by queue until thread executes them | At throughput 2 tasks/sec: 50-task queue = 25 seconds of memory hold; queue refills faster than drains |
| 14 | missing-metric-export | [`ExecutorPlus:implicit`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/ExecutorPlus.java#L100) | No metrics for queue size, queue depth, or queue capacity published to metrics registry | Administrator cannot monitor queue buildup via standard monitoring tools |

---

## Path Continuity Notes

### Factory Default vs. Configuration Parameter

**Pair 01 (memtable_flush_writers-01) vs. Pair 02 (this pair):**

Pair 01 traces a **configuration parameter** (`memtable_flush_writers`) from declaration through auto-sizing and validation. Pair 02 traces a **hardcoded factory default** (unbounded LinkedBlockingQueue) that has no configuration entry and no runtime tuning point.

- **Pair 01 enforcement:** Minimum bound check (≥1) at startup in `DatabaseDescriptor.java:755-757`
- **Pair 02 enforcement:** NO enforcement; queue capacity fixed at `Integer.MAX_VALUE` by factory method; no code path ever validates or limits queue depth

**Critical distinction:** Configuration can be changed in `cassandra.yaml`; queue capacity cannot.

### The Queue Capacity Decision

```java
// ExecutorPlus.pooled() — hardcoded factory
public static ExecutorPlus pooled(String name, int threads)
{
    return new ExecutorPlus(
        new ThreadPoolExecutor(
            threads, threads, 0L, TimeUnit.SECONDS,
            new LinkedBlockingQueue<>(),  // ← Hardcoded; no parameter
            new ThreadFactory() { ... },
            new ThreadPoolExecutor.AbortPolicy()  // Never rejects due to unbounded queue
        )
    );
}
```

**Why unbounded?** Design choice to prioritize durability (all tasks queued and eventually executed) over rejection. Rejects tasks would risk losing writes; queueing trades latency for safety. But this creates the bypass: `AbortPolicy` is defined but unreachable because `offer()` always succeeds.

### Compound Weakness: Soft Limit + Unbounded Queue

Pair 01 and Pair 02 together form the compound weakness:

- **Pair 01** (soft limit, 1 thread for multi-dir setup): Threads insufficient to drain writes at typical rates
- **Pair 02** (unbounded queue): No backpressure when threads fall behind
- **Result:** Single-threaded drain + unbounded queue = silent OOM despite memtable_heap_space hard cap

**Timeline Example (memtable_flush_writers=1, 100 MB/s write rate, 1GB memtables):**

```
T=0-500ms:   Thread-0 runs flush_task_1 (1GB)
T=500-1000ms: Thread-0 runs flush_task_2 (1GB) | Queue has 2+ pending
T=1000+ms:   Queue grows faster than thread processes
              → 50 tasks queued after ~10 seconds
              → 50GB held in queue
              → OOM at ~92GB (when JVM limit hit)
              → memtable_heap_space=2GB limit never actually enforced on total
```

### Per-Disk Pools and Slow-Disk Bottleneck

When multiple data directories are configured, each gets its own executor pool:

```
PerDiskFlushExecutors[0] → [Thread-0], queue (unbounded)
PerDiskFlushExecutors[1] → [Thread-0], queue (unbounded)
PerDiskFlushExecutors[2] → [Thread-0], queue (unbounded)
PerDiskFlushExecutors[3] → [Thread-0], queue (unbounded)  ← Slow disk
```

If disk 3 is slow (high I/O latency), its queue backs up independently. Total memory = sum of all queued memtables across all disks. One slow disk can cause global memory exhaustion because:
- Write dispatch routes to all disks simultaneously
- Slow disk's queue grows while others drain
- Total memory = 1 fast disk (empty) + 3 normal disks + 1 slow disk (50GB queued)

### Absence of Queue Monitoring

No metrics are exported for queue state:

```java
// What DOES exist:
metricRegistry.gauge("MemtableFlushWriter.active.count")      // Thread count: 1
metricRegistry.gauge("MemtableFlushWriter.completed.count")   // Completed: 5000

// What DOES NOT exist:
metricRegistry.gauge("MemtableFlushWriter.queue.size")        // ← Missing
metricRegistry.gauge("MemtableFlushWriter.queue.capacity")    // ← Missing
metricRegistry.histogram("MemtableFlushWriter.queue.depth")   // ← Missing
```

**Consequence:** Memory climbs 2GB → 10GB → 50GB with no visible queue metric. Administrator sees "1 thread active" and "5000 tasks completed" but cannot see "50,000 tasks queued, 50GB held." OOM arrives without warning.

---

## Key Code References

| Step | File | Lines | What | Purpose |
|------|------|-------|------|----------|
| 1-2 | [`ExecutorPlus.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/ExecutorPlus.java) | ~100-150 | Factory method `pooled()` creates ThreadPoolExecutor with hardcoded unbounded queue | Defines the hardcoded factory default |
| 3-4 | [`ColumnFamilyStore.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java) | 206-210 | Static final field `flushExecutor` initialized via factory; set once at daemon init | Global flush pool with unbounded queue, fixed for JVM lifetime |
| 5-8 | [`ColumnFamilyStore.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java) | 1033-1043 | Flush dispatch via `flushExecutor.execute(flush)`; falls through to queue (no rejection) | Critical submission point; no backpressure |
| 9-10 | [`ColumnFamilyStore.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java) | 3492-3510 | Per-disk executor array creation; each pool via `pooled(name, flushWriters)` | N independent pools, each with unbounded queue |
| 12-13 | [`ColumnFamilyStore.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java) | 1175-1230 | Flush inner class `run()` method; executes queued memtable flush to disk | Task execution releases memtable from queue; memory freed only then |

---

## Memory / Resource Impact

**Resource Allocated:** Heap memory (via queued memtables and their internal allocations)

**When Allocated:** Memtable object created and queued in `flushExecutor` or `perDiskflushExecutors[]` upon `execute(flush)` call

**When Released:** After `Flush.run()` completes and memtable is written to disk; queue removes task reference

**Synchronization:** Asynchronous. Caller of `execute()` returns immediately (queue accepted task), but memtable not freed until thread processes it seconds or minutes later.

**Timing Problem:** Queue accepts tasks faster than thread processes them.
- Submission rate: ~1 flush per 10 seconds (at 100 MB/s writes, 1GB memtables)
- Thread throughput: ~1 flush per 500ms = 2 per second (disk-limited)
- Ratio: Submission is ~20x slower than thread throughput *until* queue fills

But **simultaneous multiple writes** can trigger rapid flush submissions:
- 100 MB/s write rate × multiple clients = flush every 1-2 seconds
- Single thread can only drain 1 flush per 500ms
- Queue grows by ~1 task every 1-2 seconds
- After 10 seconds: 5-10 tasks queued (5-10GB)
- After 30 seconds: 20-30 tasks queued (20-30GB)

**Relationship to memtable_heap_space hard cap:** Per-memtable limit (memtable_heap_space=2GB) is checked and enforced. But queued memtables are **not** summed against this cap. Each memtable ≤2GB individually, but total queue can grow to 50GB+ without triggering any enforcement.

---

## Uncertainties and Open Questions

- **Queue initial allocation:** LinkedBlockingQueue's internal array grows dynamically on first offer(). Does Cassandra hit any allocation failures if queue reaches tens of thousands of tasks? (Likely not — millions of objects are routinely queued in Java systems — but worth verifying under extreme load.)

- **Memory accounting:** Are queued memtables counted in the metrics `memtable_heap_space_in_bytes` or `memtable_off_heap_memory_used`? Or are they invisible to standard monitoring? (If invisible, administrators are further blind to queue buildup.)

- **Per-disk slow-disk cascade:** When one disk is slow, does its queued tasks hold references to commit log segments, preventing log cleanup and filling the commit log directory? (Likely yes, but untested — could cascade into filesystem-full OOM before JVM heap OOM.)

- **Flush task object retention:** Does `Flush` task object hold references beyond the memtable itself? E.g., does it hold the entire `ColumnFamilyStore`, its memtable collection, or other large structures? If so, queue buildup holds much more than memtables alone.

- **Timing of flush trigger:** The soft cleanup threshold (50% heap) is auto-calculated based on memtable_flush_writers. With flushWriters=1, threshold=0.5. But timing details: is the cleaner thread ever throttled? Can it submit flushes faster than the queue can accept them (no, unbounded queue always accepts), or is the cleaner itself the bottleneck?
