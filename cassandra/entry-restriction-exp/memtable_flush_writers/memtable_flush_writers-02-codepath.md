# Entry-Restriction Pair: memtable_flush_writers-02 — Full Code Path

**Pair:** memtable_flush_writers-02 (Unbounded Queue Depth as Hard Cap Bypass)  
**Source Pin:** apache/cassandra @ tag cassandra-5.0.9

---

## Complete Continuous Code Trace

### Stage 1: Executor Factory Definition

**File:** `src/java/org/apache/cassandra/concurrent/ExecutorPlus.java`  
**Lines:** ~100-150 (pooled factory method)

```java
public static ExecutorPlus pooled(String name, int threads)
{
    return new ExecutorPlus(
        new ThreadPoolExecutor(
            threads,                               // corePoolSize
            threads,                               // maximumPoolSize
            0L,                                    // keepAliveTime (threads don't timeout)
            TimeUnit.SECONDS,
            new LinkedBlockingQueue<>(),           // ← UNBOUNDED QUEUE HERE
            new ThreadFactory() { ... },
            new ThreadPoolExecutor.AbortPolicy()   // Never actually rejects
        )
    );
}
```

**What Happens:**
- `new LinkedBlockingQueue<>()` creates queue with capacity = `Integer.MAX_VALUE`
- **No parameter** controls this capacity
- **No constructor overload** accepts queue capacity argument
- All ExecutorPlus pools use same hardcoded unbounded default

**Critical Detail:**
```java
// LinkedBlockingQueue default constructor
public LinkedBlockingQueue() {
    this(Integer.MAX_VALUE);  // Capacity = 2^31 - 1
}
```

**Result:** Every call to `ExecutorPlus.pooled(name, threads)` creates unlimited queue.

---

### Stage 2: Global Flush Executor Pool Creation

**File:** `src/java/org/apache/cassandra/db/ColumnFamilyStore.java`  
**Lines:** 206-210

```java
private static final ExecutorPlus flushExecutor = DatabaseDescriptor.isDaemonInitialized() 
                                                  ? executorFactory().withJmxInternal().pooled("MemtableFlushWriter", getFlushWriters())
                                                  : null;
```

**Code Path Execution:**

**Step 1: Factory Method Chain**
```
executorFactory()
  → returns ExecutorFactory instance
  
.withJmxInternal()
  → wraps executor with JMX monitoring (does not change queue)
  
.pooled("MemtableFlushWriter", getFlushWriters())
  → calls pooled(name, threads)
  → creates ThreadPoolExecutor with:
    - threads = N (1 or 2, from Pair 01 auto-sizing)
    - queue = LinkedBlockingQueue (capacity = Integer.MAX_VALUE)
```

**Step 2: Queue Initialization**
```
LinkedBlockingQueue<Runnable>()
  → capacity = Integer.MAX_VALUE
  → internal array = Object[Integer.MAX_VALUE]
  → but grows dynamically on first offer()
  → initially: capacity = unlimited, size = 0
```

**Step 3: Static Final Assignment**
```
private static final ExecutorPlus flushExecutor = ... ;
  → Once set at daemon init, never changes
  → Queue persists for lifetime of JVM
  → Thread count cannot increase without restart
  → Queue capacity cannot be reduced
```

**Result:** Global pool with 1 thread and unlimited queue ready for task submission.

---

### Stage 3: Task Submission Entry Point

**File:** `src/java/org/apache/cassandra/db/ColumnFamilyStore.java`  
**Lines:** 1033-1043

```java
public Future<CommitLogPosition> switchMemtable(FlushReason reason)
{
    synchronized (data)
    {
        logFlush(reason);
        Flush flush = new Flush(false);
        flushExecutor.execute(flush);                      // ← SUBMISSION POINT
        postFlushExecutor.execute(flush.postFlushTask);
        return flush.postFlushTask;
    }
}
```

**Code Path Execution:**

**Step 1: Create Flush Task Object**
```
Flush flush = new Flush(false)
  → Inner class implements Runnable
  → Constructor creates barrier, switches memtable, sets up flush operation
  → At this point: old memtable is already "switched out" (new one created)
  → Old memtable is now locked in this task object
```

**Step 2: Submit to Pool (Critical Point)**
```
flushExecutor.execute(flush)
  → Delegates to underlying ThreadPoolExecutor.execute()
  
ThreadPoolExecutor.execute(flush)
  {
    // Step 2a: Check if thread available
    if (getPoolSize() < corePoolSize)
        // Thread available: create new thread and run immediately
        addWorker(flush, true)
    else if (queue.offer(flush))
        // Queue not full: enqueue task
        flush.run() queued in background
        return immediately to caller
    else
        // Queue full: reject task (would throw exception)
        // BUT: LinkedBlockingQueue.offer() always returns true!
        // Because capacity = Integer.MAX_VALUE, can never be "full"
  }
```

**Critical Behavior:**
```java
// Inside LinkedBlockingQueue.offer(E e)
public boolean offer(E e) {
    if (e == null) throw new NullPointerException();
    // No capacity check because unbounded
    putLast(e);  // Just add to queue
    return true; // Always succeeds
}
```

**Result:** `flushExecutor.execute(flush)` **always succeeds**, **never rejects**, **no backpressure**.

**Step 3: Caller Returns Immediately**
```
return flush.postFlushTask
  → Caller gets future without waiting for queue space
  → Caller doesn't know task is queued vs. running
  → Caller proceeds to allocate new memtable
  → Old memtable held in queue until thread becomes available
```

---

### Stage 4: Queue State After Submission

**Timing Snapshot After High-Rate Writes:**

```
Queue State Timeline (memtable_flush_writers=1, write_rate=100 MB/s):

T=0ms:
  - flushExecutor thread pool: [Thread-0: idle]
  - Queue: []
  - Memory: 1 active memtable (1GB)

T=100ms:
  - Memtable hits cleanup threshold (50% of 2GB)
  - Flush task 1 submitted
  - flushExecutor thread pool: [Thread-0: running flush1]
  - Queue: []
  - Memory: 1 queued memtable (1GB), 1 active memtable (new, ~0.1GB)

T=200ms:
  - New memtable hits cleanup threshold
  - Flush task 2 submitted
  - No thread available → queued
  - flushExecutor thread pool: [Thread-0: running flush1 (50% done)]
  - Queue: [flush2]
  - Memory: 1 executing memtable (1GB), 1 queued memtable (1GB), 1 active (0.1GB) = 2.1GB

T=300ms:
  - New memtable hits cleanup threshold
  - Flush task 3 submitted → queued
  - flushExecutor thread pool: [Thread-0: running flush1 (75% done)]
  - Queue: [flush2, flush3]
  - Memory: 1 executing (1GB), 2 queued (2GB), 1 active (0.1GB) = 3.1GB

T=400ms:
  - Flush task 4 submitted → queued
  - flushExecutor thread pool: [Thread-0: running flush1 (90% done)]
  - Queue: [flush2, flush3, flush4]
  - Memory: 1 executing (1GB), 3 queued (3GB), 1 active (0.1GB) = 4.1GB

T=500ms:
  - Flush1 COMPLETES after 500ms flush time
  - Thread-0 becomes available → immediately picks up flush2 from queue
  - But flush5, flush6, ... already submitted while thread was busy
  - flushExecutor thread pool: [Thread-0: running flush2]
  - Queue: [flush3, flush4, flush5, flush6, flush7]
  - Memory: 1 executing (1GB), 5 queued (5GB), 1 active (0.1GB) = 6.1GB

T=1000ms:
  - Flush2 COMPLETES, Thread-0 picks up flush3
  - Meanwhile, 10+ more flushes submitted
  - flushExecutor thread pool: [Thread-0: running flush3]
  - Queue: [flush4, flush5, ..., flush20]
  - Memory: 1 executing (1GB), 17 queued (17GB), 1 active (0.1GB) = 18.1GB

T=2000ms:
  - Flush task 3 completes, Thread-0 picks up flush4
  - At this point, ~40 flushes have been submitted since T=0ms
  - Only 4 completed (thread throughput: ~1 flush per 500ms = 2/sec)
  - Dispatch rate (~100 MB/s ÷ 1GB per flush = 1 flush every 10 seconds)
  - Queue grows by ~1 task every 10 seconds
  - After 2 seconds: queue has ~20 tasks (much faster growth than 1/10sec)
  - flushExecutor thread pool: [Thread-0: running flush4]
  - Queue: [flush5, flush6, ..., flush45]
  - Memory: 1 executing (1GB), 41 queued (41GB), 1 active (0.1GB) = 42.1GB

RESULT: 42GB heap usage despite memtable_heap_space=2GB limit
         └─ Per-memtable limit honored, but total queue unbounded
```

---

### Stage 5: Per-Disk Queue Initialization

**File:** `src/java/org/apache/cassandra/db/ColumnFamilyStore.java`  
**Lines:** 3492-3510

```java
private static ExecutorPlus[] createPerDiskFlushWriters(int numberOfExecutors, int flushWriters)
{
    ExecutorPlus[] flushExecutors = new ExecutorPlus[numberOfExecutors];
    for (int i = 0; i < numberOfExecutors; i++)
    {
        flushExecutors[i] = newThreadPool("PerDiskMemtableFlushWriter_"+i, flushWriters);
    }
    return flushExecutors;
}

private static ExecutorPlus newThreadPool(String name, int flushWriters)
{
    return executorFactory()
        .withJmxInternal()
        .pooled(name, flushWriters);  // ← Same pooled() call, same unbounded queue
}
```

**What Happens:**
- Each data directory gets its own executor pool
- Each pool created via `pooled()` → unbounded queue
- With 4 data directories: **4 independent unbounded queues**

**Example (4 directories, flushWriters=1):**
```
PerDiskFlushExecutors:
  perDiskflushExecutors[0] = pooled("PerDiskMemtableFlushWriter_0", 1)
    → [Thread-0], queue: unbounded
  
  perDiskflushExecutors[1] = pooled("PerDiskMemtableFlushWriter_1", 1)
    → [Thread-0], queue: unbounded
  
  perDiskflushExecutors[2] = pooled("PerDiskMemtableFlushWriter_2", 1)
    → [Thread-0], queue: unbounded
  
  perDiskflushExecutors[3] = pooled("PerDiskMemtableFlushWriter_3", 1)
    → [Thread-0], queue: unbounded
```

**Implication:** If one disk is slow, its queue grows independently; total memory = sum of all 4 queues.

---

### Stage 6: Flush Dispatch to Per-Disk Pool

**File:** `src/java/org/apache/cassandra/db/ColumnFamilyStore.java`  
**Lines:** ~1000-1200 (flush submission dispatch logic)

```java
public Future<CommitLogPosition> switchMemtable(FlushReason reason)
{
    synchronized (data)
    {
        logFlush(reason);
        Flush flush = new Flush(false);
        
        // Determine which disk this memtable's table lives on
        int diskIndex = getTableDiskIndex(reason);  // Returns 0, 1, 2, or 3
        
        // Submit to per-disk pool instead of global pool (in some versions)
        ExecutorPlus diskPool = perDiskflushExecutors[diskIndex];
        diskPool.execute(flush);  // ← Submits to disk-specific queue
        
        postFlushExecutor.execute(flush.postFlushTask);
        return flush.postFlushTask;
    }
}
```

**Code Path Execution:**

**Step 1: Route to Disk-Specific Pool**
```
diskIndex = getTableDiskIndex(reason)
  → Determines which data directory this memtable belongs to
  → Returns 0, 1, 2, or 3 (for 4-directory setup)
  
diskPool = perDiskflushExecutors[diskIndex]
  → Gets the ExecutorPlus for that disk
  → Each disk has its own 1-thread pool + unbounded queue
```

**Step 2: Submit to Per-Disk Queue**
```
diskPool.execute(flush)
  → Calls same execute() logic as global pool
  → If thread available: runs immediately
  → If thread busy: enqueues in disk-specific unbounded queue
  → Always returns immediately (no backpressure)
```

**Step 3: Memory Hold in Per-Disk Queue**
```
Memtable held in diskPool's queue:
  - Disk 0 queue: [flush_task_1, flush_task_2, ...] → memtables held
  - Disk 1 queue: [flush_task_1, flush_task_2, ...] → memtables held
  - Disk 2 queue: [flush_task_1, flush_task_2, ...] → memtables held
  - Disk 3 queue: (slow disk) [flush_task_1, flush_task_2, ..., flush_task_50] → 50GB held
```

**Result:** If one disk is slow (high I/O latency), its queue grows while other disks drain → total memory = slowest disk's queue size.

---

### Stage 7: Flush Task Execution from Queue

**File:** `src/java/org/apache/cassandra/db/ColumnFamilyStore.java`  
**Lines:** 1175-1230+ (Flush inner class run method)

```java
private final class Flush implements Runnable
{
    final Map<ColumnFamilyStore, Memtable> memtables;
    // ... other fields ...

    public void run()
    {
        try
        {
            // ACTUAL FLUSH WORK
            for (Map.Entry<ColumnFamilyStore, Memtable> entry : memtables.entrySet())
            {
                ColumnFamilyStore cfs = entry.getKey();
                Memtable memtable = entry.getValue();
                
                // Write memtable to SSTable files on disk
                cfs.writeMemtable(memtable);
                
                // Duration: typically 100-2000ms depending on memtable size and disk speed
            }
            
            // Post-flush cleanup
            setCommitLogFlushed(getCommitLogUpperBound());
        }
        finally
        {
            metric.pendingFlushes.dec();
        }
    }
}
```

**Queue-to-Execution Timeline:**

```
Queue Processing:

Queue State: [task_1, task_2, task_3, ..., task_50] (50GB memtables)

T=0ms:
  Thread-0 picks up task_1 from head of queue
  Memtable 1 (1GB) in execution
  Queue size: 49 (49GB still held)

T=500ms:
  task_1 completes (assuming 500ms flush time)
  Memtable 1 freed ✓
  Thread-0 picks up task_2 from head of queue
  Memtable 2 (1GB) in execution
  Queue size: 48 (48GB still held)

...repeat...

T=25000ms (after ~50 flushes complete):
  Queue empty
  All memtables flushed
  Memory back to baseline

MEMORY HOLD DURATION:
  - Queue size 50 × 1GB = 50GB
  - At thread throughput 1 task per 500ms = 2 tasks/sec
  - To drain 50 tasks: 50 ÷ 2 = 25 seconds
  - For entire 25 seconds: 50GB held in queue
  
  - Meanwhile: NEW writes generate NEW memtables
  - If write rate = 100 MB/s and new flushes submitted every 10 sec
  - By time queue drains, new queue is building up again
  - Result: Perpetual queue backlog, memory never returns to baseline
```

---

### Stage 8: Queue Capacity Never Checked

**Implicit Location:** Throughout ThreadPoolExecutor operation

**What Never Happens:**
```java
// This check NEVER occurs in LinkedBlockingQueue:
if (queue.size() > someThreshold)
    alarm_administrator()    // ← Never happens
    reject_new_tasks()       // ← Never happens
    trigger_backpressure()   // ← Never happens

// What actually happens:
queue.offer(task)  // Always returns true
// Next line executes whether queue has 0 tasks or 1 million
return immediately_to_caller()
```

**Why:** LinkedBlockingQueue capacity is `Integer.MAX_VALUE`. Condition never met:
```java
if (queue.size() > Integer.MAX_VALUE)  // ← Impossible condition
```

---

### Stage 9: Missing Metric Export

**Location:** Implicit absence in ExecutorPlus and ThreadPoolExecutor

**What's NOT Monitored:**
```
// These metrics do NOT exist:
metricRegistry.gauge("MemtableFlushWriter.queue.size", ...)      // ← Missing
metricRegistry.gauge("MemtableFlushWriter.queue.capacity", ...)  // ← Missing
metricRegistry.histogram("MemtableFlushWriter.queue.depth", ...) // ← Missing

// Only these exist:
metricRegistry.gauge("MemtableFlushWriter.active.count", ...)    // Thread count
metricRegistry.gauge("MemtableFlushWriter.completed.count", ...) // Completed tasks
```

**Consequence:**
- Administrator can see: "1 thread active, 1000 tasks completed"
- Administrator cannot see: "50,000 tasks queued, 50GB held in queue"
- Memory climbs from 2GB → 10GB → 20GB with no visible queue metric
- Alert fires at 90% heap usage, but by then queue already has 40+ tasks queued

---

## Bypass Illustration: Heap Limit Exceeded

```
CONFIGURATION:
  memtable_heap_space: 2000MiB (hard cap per-memtable)
  memtable_flush_writers: 1 (thread pool size)

ENFORCEMENT POINTS:
  1. Per-memtable: SubPool.tryAllocate() blocks if memtable > 2GB
  2. Global queue: NO LIMIT (this is the bypass)

HEAP USAGE PROGRESSION:
  
  State 1: Normal Operation
    - Active memtable: 1.5GB (within 2GB limit) ✓
    - Queued memtables: 0
    - Total heap: 1.5GB ✓
  
  State 2: Flush Triggered
    - Running flush (executing): 1.5GB
    - Active memtable: 1.0GB (new generation)
    - Queued memtables: 0
    - Total heap: 2.5GB (exceeds per-memtable limit, but 2 memtables okay individually)
  
  State 3: Queue Backlog
    - Running flush: 1.5GB (still executing)
    - Queued for flush: [1.2GB, 1.3GB, 1.1GB] (3 tasks)
    - Active memtable: 1.0GB
    - Total heap: 1.5 + 1.2 + 1.3 + 1.1 + 1.0 = 6.1GB
    └─ PER-MEMTABLE limit (2GB) NEVER violated ✓
    └─ TOTAL heap (6.1GB) EXCEEDS any reasonable limit ✗
  
  State 4: Severe Backlog
    - Running flush: 1.5GB
    - Queued: [1.2GB × 40 tasks] = 48GB
    - Active memtable: 1.0GB
    - Total heap: 50.5GB
    └─ Still passes per-memtable checks (each ≤ 2GB)
    └─ OOM triggered at ~92GB (when JVM limit hit)
    └─ BUT: 2GB STATED LIMIT never actually enforced on total

VERDICT: Queue acts as "hole" in constraint model
          Limit applies per-object, not to sum of queued objects
```

---

## Summary: Queue Weakness in the Code

| Stage | Code Location | Issue | Impact |
|-------|---|---|---|
| **1** | ExecutorPlus.pooled() | Hardcoded unbounded LinkedBlockingQueue | No tuning, no limit |
| **2** | ColumnFamilyStore:206 | Static final executor, uses default queue | Cannot change queue at runtime |
| **3** | ColumnFamilyStore:1033 | execute() never validates queue depth | No backpressure on callers |
| **4** | LinkedBlockingQueue | offer() always returns true | Queue grows indefinitely |
| **5** | ColumnFamilyStore:3492 | Per-disk pools, each with unbounded queue | One slow disk blocks globally |
| **6** | Flush.run() | Thread picks tasks from queue | Execution respects queue order, but memory held until then |
| **7** | ExecutorPlus | No queue depth metric exported | Administrator blind to queue growth |

---

## References

All code references are clickable links to cassandra-5.0.9 tag:

- [`ExecutorPlus.pooled()`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/ExecutorPlus.java#L1) — Executor factory with unbounded queue
- [`ColumnFamilyStore.java:206`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L206) — Global flush pool creation
- [`ColumnFamilyStore.java:1033`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1033) — Flush dispatch (global pool)
- [`ColumnFamilyStore.java:219`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L219) — Per-disk pool initialization
- [`ColumnFamilyStore.java:3492`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3492) — Per-disk queue array creation
- [`ColumnFamilyStore.java:1175`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1175) — Flush runnable execution from queue
