# Entry-Restriction Pair: memtable_flush_writers — Auto-Sizing Default

**Entry Point:** [`Config.java:184`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L184)  
**Pair ID:** 01  
**Resource Constraint Type:** Concurrency/Throughput (memtable flush thread pool size)

---

## Quick Summary

Configuration parameter `memtable_flush_writers` (default: `0`, auto-sized) controls how many threads flush memtables to disk. The auto-sizing logic sets it to **1 thread for multi-directory setups**, which is severely under-provisioned and becomes a throughput bottleneck. Unlike `memtable_heap_space` (a hard memory cap), this constraint uses an unbounded queue that allows memory exhaustion via flush task accumulation.

---

## Configuration Entry Point

**Location:** [`Config.java:184`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L184)

```java
public int memtable_flush_writers = 0;  // Default: 0 (auto-sized)
```

**Semantics:**
- **Default (0):** Auto-calculated based on data directory count
- **Range:** Must be ≥ 1 (enforced in DatabaseDescriptor)
- **Purpose:** Controls thread pool size for flushing memtables to disk
- **No upper bound check:** Can be misconfigured to any large value

---

## What This Constraint Does

| Component | Detail |
|-----------|--------|
| **Limits** | Maximum concurrent memtable flush operations |
| **Default** | 0 (auto-calculated) |
| **Auto-Calc** | `data_file_directories.length == 1 ? 2 : 1` |
| **Range** | ≥ 1 (validated, no upper bound) |
| **Resource** | Memtable draining throughput to disk |

---

## Three Enforcement Points

### Point 1: Auto-Sizing Logic (Startup)

**Location:** [`DatabaseDescriptor.java:753-765`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L753)

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
```

**Three Auto-Sizing Paths:**

- **Path A: Single Data Directory**
  - Condition: `memtable_flush_writers == 0 AND data_file_directories.length == 1`
  - Result: `conf.memtable_flush_writers = 2`
  - Rationale: More threads justified for single-disk setup

- **Path B: Multiple Data Directories**
  - Condition: `memtable_flush_writers == 0 AND data_file_directories.length > 1`
  - Result: `conf.memtable_flush_writers = 1` ← **BOTTLENECK HERE**
  - Problem: Single thread for potentially N disks (where N = number of data dirs)

- **Path C: Explicit Value**
  - Condition: `memtable_flush_writers != 0`
  - Result: Use as-is (no modification by auto-sizing)
  - Validation: Must be ≥ 1 (no upper bound check)

**Side Effect: Threshold Auto-Calculation**

The cleanup threshold is derived from flush writer count:
```
memtable_cleanup_threshold = 1.0 / (1 + memtable_flush_writers)

With flushWriters = 1: cleanup_threshold = 0.5 (flush at 50% of heap_space)
With flushWriters = 2: cleanup_threshold = 0.333... (flush at 33% of heap_space)
```

**Interaction:** Lower thread count → earlier flushes but with fewer workers → queue builds up.

### Point 2: Global Flush Executor Creation (Startup)

**Location:** [`ColumnFamilyStore.java:206-210`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L206)

```java
private static final ExecutorPlus flushExecutor = DatabaseDescriptor.isDaemonInitialized() 
                                                  ? executorFactory().withJmxInternal().pooled("MemtableFlushWriter", getFlushWriters())
                                                  : null;
```

**What Happens:**
1. Thread pool created with size = `DatabaseDescriptor.getFlushWriters()` (e.g., 1 or 2)
2. Pool name: `"MemtableFlushWriter"` (visible in thread names and JMX)
3. Called once at daemon init (static final) — size **cannot change at runtime**
4. Queue type: unbounded by default (LinkedBlockingQueue with no capacity limit)

### Point 3: Flush Dispatch to Pool (Runtime)

**Location:** [`ColumnFamilyStore.java:1033-1043`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1033)

```java
public Future<CommitLogPosition> switchMemtable(FlushReason reason)
{
    synchronized (data)
    {
        logFlush(reason);
        Flush flush = new Flush(false);
        flushExecutor.execute(flush);                      // <--- DISPATCH TO POOL
        postFlushExecutor.execute(flush.postFlushTask);
        return flush.postFlushTask;
    }
}
```

**Dispatch Behavior:**
- If thread available: Flush task runs immediately
- If no threads available: Task queues in **unbounded queue** (NO depth limit)
- **Memory consequence:** Queued tasks hold old memtables → memory cannot be reclaimed

### Per-Disk Variant (Advanced)

**Location:** [`ColumnFamilyStore.java:219-223`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L219)

```java
private static final PerDiskFlushExecutors perDiskflushExecutors = DatabaseDescriptor.isDaemonInitialized()
                                                                   ? new PerDiskFlushExecutors(DatabaseDescriptor.getFlushWriters(),
                                                                                              DatabaseDescriptor.getNonLocalSystemKeyspacesDataFileLocations(),
                                                                                              DatabaseDescriptor.useSpecificLocationForLocalSystemData())
                                                                   : null;
```

**Result:** One executor pool created per data directory, each with `flushWriters` threads. Example (3 dirs, flushWriters=1):
```
perDiskflushExecutors[0] = pooled("PerDiskMemtableFlushWriter_0", 1)
perDiskflushExecutors[1] = pooled("PerDiskMemtableFlushWriter_1", 1)
perDiskflushExecutors[2] = pooled("PerDiskMemtableFlushWriter_2", 1)
```
Total threads: 3, isolated per directory (but each has only 1 thread per config).

---

## Weakness Analysis

### Proxy Mismatch ⚠

**What's Constrained:** "Number of flush threads"  
**What Matters:** "Memtable draining throughput (MB/s to disk)"

**Problem:** Thread count is a poor proxy for throughput:
- 1 thread flushing fast SSD + low CPU contention = 500 MB/s throughput
- 1 thread flushing slow HDD + high CPU = 10 MB/s throughput
- **Same constraint, 50x difference in actual drain rate**

**Root Cause:** Throughput depends on storage I/O performance and CPU availability, not thread count alone.

**Consequence:** Even if constraint is honored, actual drain rate varies wildly. A 1-thread limit is not predictive of whether memory will accumulate.

### Enforcement-Point Mismatch ⚠

**Check Timing:** Config-time (once at startup in `DatabaseDescriptor`)  
**Enforcement Timing:** Runtime (during flush dispatch in `ColumnFamilyStore`)

**Issues:**
1. **Config-time check:** Pool size decided once at daemon init (static final field)
   - Cannot be tightened at runtime (only loosened via JMX if exposed)
   - RuntimeMXBean changes may not be visible to already-created pool
2. **Queue-time bypass:** No queue depth limit (pool uses unbounded `LinkedBlockingQueue` by default)
   - Pool saturation is silent (tasks queue indefinitely)
   - No rejection policy, no backpressure on callers
3. **Memory hold:** Queued tasks hold old memtables
   - Prevents `memtable_heap_space` hard cap from working correctly
   - OOM occurs via queue, not via direct heap overflow

**Consequence:** 
- Startup check cannot adapt to runtime conditions
- Unbounded queue circumvents the thread-count soft limit
- High write rate + 1 flush writer = silent queue explosion → OOM

### Default-Off ✗

**Default Value:** 0 (auto-sized)  
**For Multi-Dir Setup:** Auto-calc = 1 (minimum allowed)

**Problems:**
1. Default of 1 is **severely under-provisioned** for most workloads
   - Single CPU core for flushing across all tables in keyspace
   - Suitable only for very low write rates (<10K ops/sec)
   - Typical production writes (50K-100K ops/sec) exceed 1-thread drain
2. No upper bound check → can be misconfigured to any large value
   - Administrator error (setting 1 when 8+ needed) creates bottleneck
   - Validation only checks min (≥1), not reasonableness
3. Minimum (1) is mathematically too low
   - For N data directories: should be at least N, not 1
   - Single thread cannot parallelize flushes across disks

**Consequence:** Default + typical multi-directory setup = immediate throughput bottleneck + queue accumulation

---

## Weakness Summary Table

| Aspect | Status | Reasoning |
|--------|--------|-----------|
| **Proxy Mismatch** | ⚠ **Partial** | Threads ≠ throughput; I/O variance affects drain rate by 50x |
| **Enforcement-Point Mismatch** | ⚠ **Partial** | Checked at startup only; unbounded queue at runtime circumvents thread limit |
| **Default-Off** | ✗ **Weakness Present** | Default (0 → 1 for multi-dir) is minimum value, too low for typical workloads |

---

## Resource Exhaustion Attacks

### Attack 1: Throughput Starvation (Primary)

**Scenario:** `memtable_flush_writers = 1` (minimum), high sustained write rate

**Setup:**
```yaml
memtable_flush_writers: 1           # Force minimum (or multi-dir auto-calc)
memtable_heap_space: 2000MiB        # Typical for test node
write_rate: 100,000 ops/sec         # Sustained writes
```

**Sequence:**
1. Memtables generate at ~100 MB/s (100K ops × 1KB avg)
2. Memtable reaches 50% of 2GB heap_space (cleanup threshold with 1 writer)
3. Flush task submitted to flushExecutor pool
4. Single flush thread writes to disk at ~50 MB/s (I/O bound)
5. Write queue backs up → pool queues task
6. New memtable created, fills quickly (100MB in ~1 sec)
7. Next flush task queued while previous still running
8. Queue grows: flush1 (running), [flush2, flush3, flush4, ...] (queued)
9. Memtables accumulate in memory (each 2GB generation waiting for flush)
10. After ~10-20 flush cycles: **OOM despite `memtable_heap_space` limit**

**Root Cause:** Queue depth is unbounded; no backpressure on memtable generation.

---

### Attack 2: Auto-Sizing Bypass

**Scenario:** Config explicitly sets low value despite multiple data directories

**Path:**
1. User sets `memtable_flush_writers = 1` in cassandra.yaml
2. Auto-sizing skipped (only applies if default value 0)
3. Single pool for all data directories
4. Contention on pool threads across directories
5. One slow disk blocks all flush writers

**Code Path:** Config load → validation at `DatabaseDescriptor.java:753` only checks min (≥1), not max → no upper bound validation

---

### Attack 3: Threshold Interaction Compound

**Scenario:** Exploit the `memtable_cleanup_threshold` auto-calculation

**Mechanics:**
1. Config: `memtable_flush_writers = 1` (explicitly low)
2. Auto-calc: `cleanup_threshold = 1.0 / (1 + 1) = 0.5`
   - Flushes at 50% of heap_space instead of 75%
3. Combined with slow flusher:
   - Rapid memtable turnovers (flushing every 50% instead of 75%)
   - Single thread cannot keep up with frequency
   - Increased GC pressure from frequent generation switches
4. Result: Queue builds up faster than in Attack 1

**Code Path:** `DatabaseDescriptor.java:763` → threshold auto-set → used in memtable soft cleanup logic

---

### Attack 4: Per-Disk Pool Bottleneck

**Scenario:** Many data directories but low flush_writers

**Setup:**
- 4 data directories
- `memtable_flush_writers = 1`
- Each directory assigned 1 thread

**Execution:**
1. Each disk gets 1 thread from the per-disk pool
2. If one disk is slower (degraded disk, high I/O latency):
   - Its single thread becomes bottleneck
   - Memtables for that disk queue up
3. Other disks' memtables pile up waiting for shared I/O scheduling
4. Cross-disk contention on system I/O scheduler

**Code Path:** `ColumnFamilyStore.java:3492-3510` → `PerDiskFlushExecutors.createPerDiskFlushWriters()` allocates one pool per directory with same thread count for each

---

## Key Code References

| Code Location | What | Purpose |
|---|---|---|
| [`Config.java:184`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L184) | Field | Config entry |
| [`DatabaseDescriptor.java:753-765`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L753) | Validation + auto-sizing | Soft limit trigger |
| [`ColumnFamilyStore.java:206-207`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L206) | Pool creation | Creates thread pool |
| [`ColumnFamilyStore.java:1033-1043`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1033) | Flush dispatch | Queues task to pool |
| [`ColumnFamilyStore.java:1175+`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1175) | Flush runnable | Actual flush work |

---

## Related Constraints (Interactions)

1. **`memtable_cleanup_threshold`** — Auto-calculated based on `flushWriters`; lower threshold means earlier flushes but with fewer workers → compounds bottleneck
2. **`memtable_heap_space`** — Hard cap on heap usage; low `flushWriters` prevents reaching it (soft cleanup insufficient), causing OOM via queue instead
3. **`memtable_allocation_type`** — Affects which pool is used; with `offheap_buffers`, native OOM occurs instead of JVM OOM

---

## Next Investigation

This pair focuses on the **auto-sizing default and throughput bottleneck**. Two more pairs are planned:
- **Pair 02:** Unbounded queue depth as hard cap bypass
- **Pair 03:** Per-disk pool contention (distributed constraint)

See codepath document for full trace chain.
