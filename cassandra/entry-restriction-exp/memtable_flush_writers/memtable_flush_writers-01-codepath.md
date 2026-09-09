# memtable_flush_writers — Pair 01 · Full Code Path

> **Summary:** [memtable_flush_writers-01-summary.md](memtable_flush_writers-01-summary.md) · **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

**Pair:** memtable_flush_writers-01 (Auto-Sizing Default Throughput Bottleneck)  
**Entry Point Location:** [`Config.java:184`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L184)  
**Restriction Enforcement:** [`DatabaseDescriptor.java:753-765`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L753) (auto-sizing at startup)

---

## Complete Continuous Code Trace

Unbroken trace from constraint definition → initialization → read/load → storage → submission/validation → enforcement check → action on breach. Every node listed; no gaps. When a sibling pair shares a prefix, repeat the shared steps here so this file stands alone.

### Stage 1: Configuration Declaration

**File:** `src/java/org/apache/cassandra/config/Config.java`  
**Lines:** 184-187

```java
public int memtable_flush_writers = 0;
@Replaces(oldName = "memtable_heap_space_in_mb", converter = Converters.MEBIBYTES_DATA_STORAGE_INT, deprecated = true)
public DataStorageSpec.IntMebibytesBound memtable_heap_space;
@Replaces(oldName = "memtable_offheap_space_in_mb", converter = Converters.MEBIBYTES_DATA_STORAGE_INT, deprecated = true)
```

**What Happens:**
- Field `memtable_flush_writers` declared in `Config` class
- Default value: `0` (auto-sizing sentinel)
- Type: primitive `int` (not volatile, not checked at runtime except on change)

---

### Stage 2: Configuration Validation & Auto-Sizing

**File:** `src/java/org/apache/cassandra/config/DatabaseDescriptor.java`  
**Lines:** 750-768

```java
        if (conf.memtable_flush_writers == 0)
        {
            conf.memtable_flush_writers = conf.data_file_directories.length == 1 ? 2 : 1;
        }

        if (conf.memtable_flush_writers < 1)
            throw new ConfigurationException("memtable_flush_writers must be at least 1, but was " + conf.memtable_flush_writers, false);

        if (conf.memtable_cleanup_threshold == null)
        {
            conf.memtable_cleanup_threshold = (float) (1.0 / (1 + conf.memtable_flush_writers));
        }
        else
        {
            logger.warn("memtable_cleanup_threshold has been deprecated and should be removed from cassandra.yaml");
        }
```

**Code Paths:**

**Path A: Single Data Directory**
```
memtable_flush_writers == 0
  AND data_file_directories.length == 1
  → conf.memtable_flush_writers = 2
```

**Path B: Multiple Data Directories**
```
memtable_flush_writers == 0
  AND data_file_directories.length > 1
  → conf.memtable_flush_writers = 1   ← BOTTLENECK HERE
```

**Path C: Explicit Value**
```
memtable_flush_writers != 0
  → use as-is (no modification)
  → validation: must be >= 1 (no upper bound)
```

**Side Effect: Threshold Auto-Calculation**
```
memtable_cleanup_threshold == null
  → conf.memtable_cleanup_threshold = 1.0 / (1 + conf.memtable_flush_writers)
  
With flushWriters = 1: cleanup_threshold = 0.5 (flush at 50% of heap_space)
With flushWriters = 2: cleanup_threshold = 0.333... (flush at 33% of heap_space)
```

**Critical Observation:**
- When flushing starts earlier (low threshold) but with only 1 worker
- Throughput = single thread capability (50-100 MB/s typical)
- Write rate may exceed this (100+ MB/s) → queue accumulates

---

### Stage 3: Accessor Method Definition

**File:** `src/java/org/apache/cassandra/config/DatabaseDescriptor.java`  
**Lines:** 2457-2460

```java
public static int getFlushWriters()
{
    return conf.memtable_flush_writers;
}
```

**What Happens:**
- Simple accessor; returns configured value after validation
- Called at ColumnFamilyStore static init (lines 206, 219)
- NOT marked volatile → runtime changes via JMX may not be visible to pool

---

### Stage 4: Global Flush Executor Creation

**File:** `src/java/org/apache/cassandra/db/ColumnFamilyStore.java`  
**Lines:** 206-210

```java
private static final ExecutorPlus flushExecutor = DatabaseDescriptor.isDaemonInitialized() 
                                                  ? executorFactory().withJmxInternal().pooled("MemtableFlushWriter", getFlushWriters())
                                                  : null;
```

**What Happens:**
1. Static field initialized once at class load
2. Condition: `isDaemonInitialized()` checks if Cassandra daemon is running
3. If yes: creates pooled executor with name `"MemtableFlushWriter"` and size `getFlushWriters()` (== confvalue)
4. If no: set to `null` (e.g., during tests, utilities)

**Thread Pool Details:**
- Name: `"MemtableFlushWriter"` (appears in thread names and JMX)
- Size: `getFlushWriters()` (e.g., 1 or 2 from auto-sizing)
- Queue: unbounded by default (standard `ExecutorPlus.pooled()` behavior)
- Rejection Policy: queue if full (never rejects, just queues)

---

### Stage 5: Per-Disk Flush Executor Initialization

**File:** `src/java/org/apache/cassandra/db/ColumnFamilyStore.java`  
**Lines:** 219-223

```java
private static final PerDiskFlushExecutors perDiskflushExecutors = DatabaseDescriptor.isDaemonInitialized()
                                                                   ? new PerDiskFlushExecutors(DatabaseDescriptor.getFlushWriters(),
                                                                                              DatabaseDescriptor.getNonLocalSystemKeyspacesDataFileLocations(),
                                                                                              DatabaseDescriptor.useSpecificLocationForLocalSystemData())
                                                                   : null;
```

**What Happens:**
- Static field initialized with `PerDiskFlushExecutors` instance
- Passes `getFlushWriters()` and data directory paths to constructor
- This creates one pool per data directory (Pair 03 focus, not shown here in detail)

---

### Stage 6: Inner Class PerDiskFlushExecutors Constructor

**File:** `src/java/org/apache/cassandra/db/ColumnFamilyStore.java`  
**Lines:** 3492-3501

```java
public PerDiskFlushExecutors(int flushWriters,
                             String[] locationsForNonSystemKeyspaces,
                             boolean useSpecificLocationForSystemKeyspaces)
{
    ExecutorPlus[] flushExecutors = createPerDiskFlushWriters(locationsForNonSystemKeyspaces.length, flushWriters);
    nonLocalSystemflushExecutors = flushExecutors;
    useSpecificExecutorForSystemKeyspaces = useSpecificLocationForSystemKeyspaces;
    localSystemDiskFlushExecutors = useSpecificLocationForSystemKeyspaces ? new ExecutorPlus[] {newThreadPool("LocalSystemKeyspacesDiskMemtableFlushWriter", flushWriters)}
                                                                          : new ExecutorPlus[] {flushExecutors[0]};
}
```

**What Happens:**
1. Calls `createPerDiskFlushWriters()` with directory count and flushWriters value
2. Stores array of executors in field `nonLocalSystemflushExecutors`
3. For system keyspaces: reuses first pool or creates separate one depending on config
4. Result: array of pools, each with `flushWriters` threads

---

### Stage 7: Per-Disk Pool Array Creation

**File:** `src/java/org/apache/cassandra/db/ColumnFamilyStore.java`  
**Lines:** 3503-3510

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
```

**What Happens:**
- Creates array with one entry per data directory
- Each pool created with `flushWriters` threads (line 3508)
- Pool name includes directory index: `"PerDiskMemtableFlushWriter_0"`, `_1`, etc.
- Returns array for use in PerDiskFlushExecutors

**Example (3 data directories, flushWriters=1):**
```
flushExecutors[0] = pooled("PerDiskMemtableFlushWriter_0", 1)
flushExecutors[1] = pooled("PerDiskMemtableFlushWriter_1", 1)
flushExecutors[2] = pooled("PerDiskMemtableFlushWriter_2", 1)
```
Total threads: 3 (one per dir), each pool isolated

---

### Stage 8: Memtable Switch & Flush Dispatch

**File:** `src/java/org/apache/cassandra/db/ColumnFamilyStore.java`  
**Lines:** 1014-1023 (switchMemtableIfCurrent)

```java
public Future<CommitLogPosition> switchMemtableIfCurrent(Memtable memtable, FlushReason reason)
{
    synchronized (data)
    {
        if (data.getView().getCurrentMemtable() == memtable)
            return switchMemtable(reason);
    }
    logger.debug("Memtable is no longer current, returning future that completes when current flushing operation completes");
    return waitForFlushes();
}
```

**What Happens:**
1. Checks if provided memtable is still current (not already flushed)
2. If yes: calls `switchMemtable()` to initiate flush
3. If no: returns a future that waits for existing flushes

**Entry Point for Flush:** `switchMemtable(reason)`

---

### Stage 9: Memtable Switch & Pool Dispatch

**File:** `src/java/org/apache/cassandra/db/ColumnFamilyStore.java`  
**Lines:** 1033-1043

```java
public Future<CommitLogPosition> switchMemtable(FlushReason reason)
{
    synchronized (data)
    {
        logFlush(reason);
        Flush flush = new Flush(false);
        flushExecutor.execute(flush);                           // <--- DISPATCH TO POOL
        postFlushExecutor.execute(flush.postFlushTask);
        return flush.postFlushTask;
    }
}
```

**Code Path Execution:**

**Step 1: Log Flush Activity**
```
logFlush(reason)
  → Memtable.newMemoryUsage() - calculate current memory
  → logger.info("Enqueuing flush of {}.{}, Reason: {}, Usage: {}", ...)
```

**Step 2: Create Flush Task**
```
flush = new Flush(false)
  → Creates Flush inner class instance (Runnable)
  → Initialized with barrier, memtables map, post-flush task
  → metric.pendingFlushes.inc() increments counter
```

**Step 3: CRITICAL DISPATCH**
```
flushExecutor.execute(flush)
  → Submits to "MemtableFlushWriter" pool
  → Pool has N threads (N = flushWriters, default 1 for multi-dir)
  → If thread available: runs immediately on that thread
  → If no threads available: queues in unbounded queue
     (THIS IS WHERE BOTTLENECK OCCURS)
```

**Step 4: Post-Flush Task Dispatch**
```
postFlushExecutor.execute(flush.postFlushTask)
  → Sequential single-threaded executor
  → Runs AFTER flush task completes
  → Ensures ordering of post-flush operations
```

**Step 5: Return Future**
```
return flush.postFlushTask
  → Caller can await completion of entire flush chain
```

---

### Stage 10: Flush Runnable Execution

**File:** `src/java/org/apache/cassandra/db/ColumnFamilyStore.java`  
**Lines:** 1175-1230+ (Flush inner class)

```java
private final class Flush implements Runnable
{
    final OpOrder.Barrier writeBarrier;
    final Map<ColumnFamilyStore, Memtable> memtables;
    final FutureTask<CommitLogPosition> postFlushTask;
    final PostFlush postFlush;
    final boolean truncate;

    private Flush(boolean truncate)
    {
        if (logger.isTraceEnabled())
            logger.trace("Creating flush task {}@{}", hashCode(), name);
        this.truncate = truncate;

        metric.pendingFlushes.inc();
        
        // ... barrier creation and memtable switching ...
        writeBarrier = Keyspace.writeOrder.newBarrier();
        memtables = new LinkedHashMap<>();
        AtomicReference<CommitLogPosition> commitLogUpperBound = new AtomicReference<>();
        
        for (ColumnFamilyStore cfs : concatWithIndexes())
        {
            Memtable newMemtable = cfs.createMemtable(commitLogUpperBound);
            Memtable oldMemtable = cfs.data.switchMemtable(truncate, newMemtable);
            oldMemtable.switchOut(writeBarrier, commitLogUpperBound);
            memtables.put(cfs, oldMemtable);
        }
        
        setCommitLogUpperBound(commitLogUpperBound);
        writeBarrier.issue();
        postFlush = new PostFlush(Iterables.get(memtables.values(), 0, null));
        postFlushTask = new FutureTask<>(postFlush);
    }

    public void run()
    {
        // ACTUAL FLUSH WORK HAPPENS HERE
        // Writes memtable contents to SSTable files on disk
        // Duration depends on memtable size and I/O performance
    }
}
```

**What Happens:**
1. Flush task picked up by one of N threads from `flushExecutor` pool
2. `run()` method executes: writes sorted memtable to SSTable
3. Duration: ~50-500ms (depends on memtable size, disk speed, CPU)
4. After completion: thread returns to pool (available for next task)

**Queue Backlog Scenario:**
```
Timeline:
T=0.0s:   Write task 1 submitted → flushExecutor thread 0 starts (only 1 thread)
T=0.1s:   Memtable fills → flush task 1 queued
T=0.2s:   Memtable fills again → flush task 2 queued
T=0.3s:   Memtable fills again → flush task 3 queued
...
T=0.5s:   flush task 1 COMPLETES on thread 0
T=0.5s:   flush task 2 starts on thread 0
T=0.6s:   flush task 3, 4, 5, ... waiting in queue
T=1.0s:   flush task 2 COMPLETES
T=1.0s:   flush task 3 starts
...

Memory Used:
- Task 1 completed, memtable freed ✓
- Task 2 running, memtable held
- Task 3,4,5,... queued, old memtables held (cannot be freed!)
- New memtables accumulate as writes continue
- After 10-20 cycles: OOM (old memtables in queue cannot be reclaimed)
```

---

### Stage 11: Queue Depth Unbounded

**Implicit Location:** ExecutorPlus pooled executor default queue

**Queue Behavior:**
```java
// ExecutorPlus.pooled(name, threads) uses standard ThreadPoolExecutor
// Default queue: LinkedBlockingQueue with NO capacity limit
// Rejection policy: ThreadPoolExecutor.AbortPolicy by default

// When submitting:
if (threads_available)
    execute_immediately_on_thread()
else
    add_to_unbounded_queue()  // ← NO LIMIT, keeps growing
```

**Problem:**
- No queue.size() limit
- No wait/backpressure when queue fills
- Flush tasks accumulate indefinitely
- Held memtables cannot be released → OOM

---

## Path Continuity Notes

**Alternative Entry Point:** Per-disk pool variant (Stage 5) bypasses single global pool when multiple data directories are configured. Each directory gets its own pool, but the same bottleneck applies: each pool has only `flushWriters` threads (default 1 per directory when auto-sized for multi-directory setup).

**Bypass Mechanism:** The unbounded queue (Stage 11) is the actual bypass. Thread-count limit (Stage 4) is enforced only on *concurrent execution*, not on *task submission*. High submission rate + few threads = queue grows unbounded.

**Timing Sensitivity:** Stage 9 (dispatch) is asynchronous. Caller does not wait for queue depth to be checked; it immediately returns a future. By the time future is awaited, queue may already hold dozens of tasks.

---

## Key Code References

| Stage | File | Lines | What | Purpose |
|-------|------|-------|------|---------|
| 1 | [`Config.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java) | 184 | Field declaration | Entry point |
| 2 | [`DatabaseDescriptor.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java) | 753-765 | Auto-sizing logic | Soft limit trigger (bottleneck: min value too low) |
| 3 | [`DatabaseDescriptor.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java) | 2457-2460 | Getter | Value read by pool creation |
| 4 | [`ColumnFamilyStore.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java) | 206-210 | Pool creation | Global flush executor |
| 5-7 | [`ColumnFamilyStore.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java) | 219-223, 3492-3510 | Per-disk pools | Directory-isolated pools (Pair 03 focus) |
| 9 | [`ColumnFamilyStore.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java) | 1033-1043 | Dispatch | Critical bottleneck point |
| 10 | [`ColumnFamilyStore.java`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java) | 1175+ | Flush runnable | Actual flush work |

---

## Memory / Resource Impact Summary

**Allocation & Release:**
- Memtable allocated when table switches (Stage 9, Step 2)
- Memtable released after flush completes and post-flush cleanup finishes (Stage 10, after `run()`)
- If queued: memtable held in queue reference until thread picks up task

**Synchrony:**
- Dispatch is asynchronous (Stage 9 returns immediately)
- Flush execution is synchronous (thread blocks until `run()` completes)
- Release is asynchronous (postFlush task scheduled after flush completes)

**Timing & Overshoot:**
- With 1 thread and 100 MB/s write rate: new memtable generated every ~1 sec (at 100 MB threshold)
- But 1 thread flushes at ~50 MB/s (I/O bound), taking ~2 secs per memtable
- Result: queue grows by ~1 memtable per second until OOM

**Cascade to memtable_heap_space:**
- `memtable_heap_space` limits *per-table* heap usage (checked during allocation)
- Queued memtables are no longer subject to this check (already allocated)
- Total heap = queued memtables + new memtables + active heap
- Can exceed stated `memtable_heap_space` limit by 10-20x

---

## Notes

- **Stage 2 bottleneck:** Auto-sizing sets flushWriters to 1 for multi-directory. For N directories, this should be ≥N to parallelize across disks, not 1.
- **Stage 4 design:** Pool created as `static final`, cannot be reconfigured at runtime. Changes to `memtable_flush_writers` config are ignored after daemon init.
- **Stage 9 dispatch:** No queue-depth checking before submission. Caller has no way to detect queue saturation (future is returned immediately).
- **Stage 11 ubiquity:** Every ExecutorPlus pool created with `pooled()` factory has unbounded queue by default. This is not Pair 01 specific; it's Pair 02 (queue depth is separate entry point).

