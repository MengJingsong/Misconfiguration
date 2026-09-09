# Entry-Restriction Pair: memtable_flush_writers-02 — Unbounded Queue Depth

**Entry Point:** [`ExecutorPlus.pooled()`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/ExecutorPlus.java#L1) (implicit, executor factory default)  
**Pair ID:** 02  
**Resource Constraint Type:** Queue Depth / Memory Hold (bypass mechanism for `memtable_heap_space` hard cap)

---

## Quick Summary

While `memtable_flush_writers` configures thread pool size, the **executor factory creates an unbounded queue by default**. When flush dispatch rate exceeds thread throughput, tasks queue indefinitely with no depth limit or backpressure. Queued tasks hold old memtables in memory, allowing total memory consumption to exceed `memtable_heap_space` hard cap despite the limit being honored per-memtable. This pair documents the queue as a separate entry point that **silently bypasses** the heap constraint.

---

## Queue Configuration Entry Point

**Location:** [`ExecutorPlus.pooled()`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/ExecutorPlus.java#L1) — executor factory method (implicit default)

**Semantics:**
- **Queue Type:** `LinkedBlockingQueue` with **no capacity limit** (capacity = `Integer.MAX_VALUE`)
- **Rejection Policy:** `ThreadPoolExecutor.AbortPolicy` (standard default) — never rejects, queues instead
- **No configuration parameter:** Queue depth cannot be tuned via `cassandra.yaml`
- **No monitoring:** No metric tracks queue depth or backlog size
- **Result:** Pool saturation is silent; callers never see rejection

---

## What This Constraint Does (Or Fails To Do)

| Component | Detail |
|-----------|--------|
| **Intends to Limit** | Concurrent flush task count via thread pool size |
| **Actually Limits** | Nothing; unbounded queue absorbs all excess submissions |
| **Default Behavior** | Silently queue tasks when threads unavailable |
| **Memory Consequence** | Queued tasks hold references to old memtables → memory not released |
| **Interaction with `memtable_heap_space`** | Hard cap is per-memtable; queued memtables bypass cap checking |

---

## Why Queue Depth is a Separate Entry Point

### 1. Independent from Thread Count

Thread pool size (`memtable_flush_writers`) and queue depth are **orthogonal constraints**:

| Aspect | Thread Count | Queue Depth |
|--------|--------------|-------------|
| **Configured via** | `memtable_flush_writers` | Hardcoded in executor factory (no config) |
| **Enforces** | Max concurrent execution | Max pending tasks held in memory |
| **Bypass when** | High dispatch rate + low threads | Any dispatch rate (queue always unbounded) |
| **Detection** | Visible as thread CPU usage or pool saturation JMX | Silent; no metric or alert |

### 2. Implicit vs. Explicit

- `memtable_flush_writers`: **Explicit configuration** (user-visible, tunable)
- Queue capacity: **Implicit hardcoded default** (no config, no visibility, no tuning path)

This asymmetry means administrators can optimize thread count but cannot constrain queue depth.

### 3. Cascading Memory Hold

Queued tasks create a hold on upstream resources:

```
Write Input Stream
  ↓
Memtable (in-memory)
  ↓
Soft Cleanup Threshold Trigger (50% of heap_space)
  ↓
Flush Task Dispatch
  ↓ [Queues if no thread available]
Unbounded Queue
  ↓
Thread Pool Execution [Eventually runs]
  ↓
Disk (SSTables)
  ↓
Memtable Freed (after flush completes)
```

**Problem:** Once queued, memtable is held indefinitely. Multiple generations can accumulate in queue before any are freed.

---

## Three Enforcement Points (Queue Behavior)

### Point 1: Executor Factory Initialization (Startup)

**Location:** [`ColumnFamilyStore.java:206-210`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L206)

```java
private static final ExecutorPlus flushExecutor = DatabaseDescriptor.isDaemonInitialized() 
                                                  ? executorFactory().withJmxInternal().pooled("MemtableFlushWriter", getFlushWriters())
                                                  : null;
```

**Queue Creation:**
- `executorFactory().pooled(name, threads)` calls [`ExecutorPlus.pooled()`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/ExecutorPlus.java#L1)
- Default implementation wraps `ThreadPoolExecutor` with `LinkedBlockingQueue` (unbounded)
- **No parameter** controls queue capacity
- **No validation** checks or warns about unlimited queue

**Code Path:**
```
executorFactory().pooled(name, threads)
  → ThreadPoolExecutor(threads, threads, ...)
  → new LinkedBlockingQueue() [capacity = Integer.MAX_VALUE]
```

### Point 2: Task Submission with Silent Queuing (Runtime)

**Location:** [`ColumnFamilyStore.java:1033-1043`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1033)

```java
public Future<CommitLogPosition> switchMemtable(FlushReason reason)
{
    synchronized (data)
    {
        logFlush(reason);
        Flush flush = new Flush(false);
        flushExecutor.execute(flush);                      // <--- SUBMISSION POINT
        postFlushExecutor.execute(flush.postFlushTask);
        return flush.postFlushTask;
    }
}
```

**Submission Behavior:**
```java
// Inside ThreadPoolExecutor.execute(task):
if (threads_available >= corePoolSize)
    run_immediately_on_thread()
else
    queue.put(task)  // ← NO CAPACITY CHECK, just enqueues
```

**Critical Observation:**
- No rejection even if queue has thousands of pending tasks
- Caller (`switchMemtable`) proceeds without knowing task is queued
- Memtable switch already happened (new memtable created), old one locked in queue

### Point 3: Memory Hold Duration (Runtime - Ongoing)

**Location:** Implicit in queue lifecycle — tasks held until thread becomes available

**Hold Sequence:**
```
T=0ms:  Task 1 submitted → thread available → runs immediately
T=100ms: Task 2 submitted → no thread available → queues, memtable held
T=200ms: Task 3 submitted → still no thread available → queues, another memtable held
...
T=500ms: Task 1 completes on thread, returns to pool
T=500ms: Task 2 starts, thread busy again
T=501ms: Task 4 submitted → queues, memtable held
...
T=2000ms: Task 2 completes, Task 3 starts
         Meanwhile Tasks 4, 5, 6, ... queued with memtables held
```

**Memory Impact:**
- Each queued task holds a memtable (can be 100MB-2GB each)
- Queue can grow to 10, 50, 100+ tasks under sustained high write rate
- Total heap usage: thread threads × memtable_size + queue depth × memtable_size
- With queue depth → 100 and memtable_size → 2GB: **200GB held in queue alone**

---

## Weakness Analysis

### Proxy Mismatch ⚠

**What's Supposed to Constrain:** "Thread pool size limits concurrent flush operations"  
**What Actually Happens:** "Unbounded queue allows any number of operations to be pending"

**Problem:**
- Thread constraint: N threads → at most N concurrent flushes
- Queue constraint: Unbounded → 1000+ pending flushes queued while 1 thread runs

**Consequence:** Thread-count soft limit is circumvented by queue depth hard limit (which doesn't exist).

### Enforcement-Point Mismatch ✗

**Check Timing:** Startup (executor factory initialization, static final)  
**Enforcement Timing:** Runtime (task submission), but no enforcement occurs

**Issues:**
1. **No capacity check at submission:** `flushExecutor.execute(flush)` does not validate queue depth
2. **No rejection or backpressure:** Tasks queue silently, no exception or warning to caller
3. **No runtime monitoring:** No metric exposes queue depth; administrators blind to backlog
4. **No adaptive behavior:** Queue grows indefinitely; no threshold triggers remediation

**Consequence:**
- Thread count is the only visible limit
- Queue depth grows silently until OOM
- Administrator sees "only 1-2 flush threads in use" and doesn't know 500+ tasks queued behind

### Default-Off ✗

**Default Behavior:** Unbounded queue (no parameter to change it)  
**Consequences:**
1. **Zero visibility:** No configuration, no tuning, no monitoring
2. **Silent failure mode:** Pool saturation causes memory exhaustion without warning
3. **No upper bound:** Can queue millions of tasks if memory allows
4. **Interaction weakness:** Combined with low `memtable_flush_writers` default (1 for multi-dir) → guaranteed queue buildup

---

## Weakness Summary Table

| Aspect | Status | Reasoning |
|--------|--------|-----------|
| **Proxy Mismatch** | ⚠ **Partial** | Thread limit circumvented by unbounded queue; queue depth invisible |
| **Enforcement-Point Mismatch** | ✗ **Weakness Present** | No check, no rejection, no backpressure at submission; queue grows silently |
| **Default-Off** | ✗ **Weakness Present** | Unbounded queue hardcoded with no config, no metric, no monitoring |

---

## Resource Exhaustion Attacks

### Attack 1: Queue Accumulation Under High Write Load

**Scenario:** Sustained high write rate with default `memtable_flush_writers = 1`

**Setup:**
```yaml
memtable_flush_writers: 1           # Default for multi-dir (bottleneck from Pair 01)
memtable_heap_space: 2000MiB
write_rate: 100,000 ops/sec
```

**Sequence:**
1. Writes generate memtables at ~100 MB/s (100K ops × 1KB avg)
2. Memtable reaches cleanup threshold (50% of 2GB = 1GB) after ~10 seconds
3. Flush task submitted to flushExecutor (1-thread pool)
4. Thread picks up task, starts writing to disk (~50 MB/s I/O bound)
5. Meanwhile, new writes continue → new memtable fills in ~20 seconds
6. Cleanup threshold hit again → second flush task submitted
7. No thread available (first flush still running) → **second task queues**
8. New memtable created, continues filling
9. After 20 seconds: first flush completes, thread becomes available
10. Second flush starts immediately
11. But while first two flushes were running, 4-5 more cleanup triggers occurred
12. Queue now has 3-4 pending flush tasks, each holding a ~2GB memtable
13. Total queued memory: 6-8GB (3-4 tasks × 2GB each)
14. After ~5 cycles: queue has 10+ tasks → 20+GB held
15. **OOM triggered despite `memtable_heap_space: 2GB` limit**

**Root Cause:** Queue depth has no limit; dispatch rate (5+ flushes/min) far exceeds thread throughput (1 flush every ~20 sec = 3 flushes/min).

### Attack 2: Queue as Implicit Hard Cap Bypass

**Scenario:** Exploit queue to exceed stated heap limit

**Path:**
1. Config sets `memtable_heap_space = 2000MiB` (hard cap, supposedly enforces max memory)
2. Single memtable reaches hard cap in `SubPool.tryAllocate()` → blocks or throws
3. However, if multiple memtables have already been queued for flush:
   - Old memtable 1 (1GB) queued, awaiting flush thread
   - Old memtable 2 (1GB) queued, awaiting flush thread
   - Current memtable (2GB) running hot, not yet queued
   - Total in queue: 2GB (older) + 2GB (current) = 4GB despite 2GB heap limit
4. The "hard cap" applies per-memtable in the allocator, not to total queued memory
5. Result: **2GB stated limit, 4GB actual heap used**

**Code Path:** `SubPool.tryAllocate()` checks `hasRoom()` per-memtable → allows 2GB per memtable → but doesn't account for queued memtables

### Attack 3: Administrator Blind to Backlog

**Scenario:** Monitor only visible metrics; miss queue explosion

**Observation:**
1. Admin checks JMX: MemtableFlushWriter pool shows 1 thread running (~50% CPU)
2. Thinks: "Pool is active, tasks are being flushed"
3. Doesn't check: queue depth (not exposed in default metrics)
4. Memory steadily climbs: 2GB → 4GB → 8GB → OOM
5. By time alert fires (at 90% heap), queue already has 40+ tasks
6. No way to drain queue except wait for flushes to complete (takes hours at 1 thread)

**Root Cause:** Queue depth is invisible; no metric alerts on queue growth.

### Attack 4: Intentional Queue Poisoning (Slow Disk)

**Scenario:** Deliberately slow down one disk to block its queue

**Setup:**
- 4 data directories
- One disk is slow (e.g., degraded, network storage)
- Per-disk flush executors: each disk gets 1 thread (from Pair 01 `memtable_flush_writers = 1`)

**Execution:**
1. Writes distributed across 4 disks
2. Disk 3 is slow: flush throughput only 10 MB/s (vs. 50 MB/s on others)
3. Disk 3's queue backs up: tasks for Disk 3 accumulate
4. While Disk 3's single thread processes task 1 (10 MB/s = 200 seconds):
   - Tasks 2, 3, 4, ... submitted to queue
   - Each task holds a memtable (2GB each)
   - After 10 tasks: 20GB queued for Disk 3 alone
5. Other disks fine (1-thread each, but faster I/O)
6. Total memory explodes due to Disk 3's queue
7. Result: One slow disk causes cluster-wide OOM

**Code Path:** [`ColumnFamilyStore.java:3492-3510`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3492) → per-disk pools each have independent unbounded queues

---

## Interaction with Other Constraints

1. **`memtable_flush_writers`** — Determines thread count; low value guarantees queue buildup
2. **`memtable_heap_space`** — Hard cap per-memtable, but doesn't account for queued memtables total
3. **`memtable_cleanup_threshold`** — Auto-calculated based on flush_writers; lower threshold triggers more flushes, filling queue faster

---

## Key Code References

| Code Location | What | Purpose |
|---|---|---|
| [`ExecutorPlus.pooled()`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/ExecutorPlus.java#L1) | Queue creation | Hardcoded unbounded LinkedBlockingQueue |
| [`ColumnFamilyStore.java:206-210`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L206) | Pool init | Static final, uses default queue |
| [`ColumnFamilyStore.java:1033-1043`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1033) | Task submission | No validation of queue depth |
| [`ColumnFamilyStore.java:3492-3510`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3492) | Per-disk queues | Each directory's queue also unbounded |

---

## Difference from Pair 01

| Aspect | Pair 01 | Pair 02 |
|--------|---------|---------|
| **Entry Point** | `memtable_flush_writers` config value | Executor factory queue default |
| **What's Configured** | Thread pool size | (Nothing; hardcoded unbounded) |
| **Enforcement** | Auto-sizing logic at startup | Implicit in pool creation |
| **Bypass Vector** | Low thread count creates bottleneck | Unbounded queue absorbs all submissions |
| **Memory Consequence** | Throughput starvation + soft cleanup insufficient | Tasks queued indefinitely, memtables held |
| **Visibility** | Configured value is visible | Queue depth is invisible (no metric) |

---

## Next Investigation

This pair focuses on the **unbounded queue as an independent entry point and bypass mechanism**. The third pair will examine:
- **Pair 03:** Per-disk pool contention (distributed constraint where one slow disk blocks its queue)

See codepath document for full trace chain of queue behavior during task lifecycle.
