# queueLimit (Sampler executor work-queue capacity, 1000 tasks) — verification solution  <!-- file: cases/queueLimit-newBlockingQueue-capacity--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (capacity-set place), **linked**: [`BlockingQueues.java:46`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/concurrent/BlockingQueues.java#L46) (`: new LinkedBlockingQueue<>(capacity);`, the non-zero arm of the conditional at [`BlockingQueues.java:45-46`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/concurrent/BlockingQueues.java#L45-L46)) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.330, 2026-11-24 |
| Estimate | `positive`. Line 46 sets the capacity of the executor work queue; for the Sampler executor that capacity is the hard-coded 1000, and `ThreadPoolExecutor` (core = max = 1) rejects every task offered while the queue holds 1000, and the rejected task is dropped (counted as `_SAMPLE`) and not retained. Usage is therefore capped in **task count**: about 1000 queued tasks plus 1 running. The byte bound is 1000 × the largest retained task, which here is a partition key of up to 64 KiB (about 60 MiB in total). Line 46 also gives a finite cap at two other call sites (TracingStage, 1000; `MonitoringTask`, `-Dcassandra.monitoring_max_operations`, default 50). Every other executor reaches line 46 with `Integer.MAX_VALUE`, which caps nothing. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**

- **What line 46 is.** `BlockingQueues.newBlockingQueue(int capacity)` is a generic factory. Line 46 builds `new LinkedBlockingQueue<>(capacity)` whenever `capacity != 0`. It has three callers in `src/java` (`grep -rn "newBlockingQueue(" src/java`; the other hits call the no-argument overload at `:37-40`):
  - `ThreadPoolExecutorBuilder.newQueue()` (`ThreadPoolExecutorBuilder.java:160-168`)
  - `MonitoringTask.OperationsQueue` (`MonitoringTask.java:207-212`), which calls `newBlockingQueue(maxOperations)` when `maxOperations > 0` (`:210`)
  - `SSTableSimpleUnsortedWriter.java:68`, which passes 0. That case takes line 45 (`SynchronousQueue`), not line 46.
- **Where `capacity` comes from.** In `newQueue()`, `capacity` is the builder's **`queueLimit`**. The field is declared at [`ThreadPoolExecutorBuilder.java:71`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/ThreadPoolExecutorBuilder.java#L71) (`private Integer queueLimit;`) and set by `withQueueLimit(int)` (`:131-135`). When it is unset, the default is derived at `:163-166`:
  - `Integer.MAX_VALUE` when the pool has a finite thread count
  - `0` when `threads == Integer.MAX_VALUE`
- **Finite values that reach line 46.** Every `withQueueLimit` call in `src/java` was enumerated. Together with `MonitoringTask`, three finite, non-zero capacities reach line 46:
  - **1000** for the **Sampler** executor, at [`Sampler.java:103`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/Sampler.java#L103), inside the `samplerExecutor` definition at [`Sampler.java:99-105`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/Sampler.java#L99-L105)
  - **1000** for the **TracingStage**, at `Stage.java:201`
  - **`cassandra.monitoring_max_operations`** (JVM property, default `"50"`, `CassandraRelevantProperties.java:361`; read once into `MAX_OPERATIONS` at `MonitoringTask.java:65`) for the two `OperationsQueue`s of timed-out and slow queries (`MonitoringTask.java:88-91`). A full queue makes `offer` return false and `numDroppedOperations` goes up (`:219-226`). The queue holds `FailedOperation`/`SlowOperation`, each referencing the whole `Monitorable` read command (`:310-345`). A value of 0 or less takes the unbounded `newBlockingQueue()` but `offer` returns early on 0 (`:221-222`).
- **Calls that do not give a finite cap.**
  - Limit 0, which takes line 45 instead: `CommitLogSegmentManagerCDC.java:311`, and `ActiveRepairService.java:216` when the strategy is `reject`.
  - `Integer.MAX_VALUE`: `CompactionManager.java:2038` for every `CompactionExecutor` subclass (`:2015`, `:2113`, `:2127`, `:2135`, `:2158`), `ActiveRepairService.java:216` with `queue`, and every builder that never calls `withQueueLimit` (for example `migrationStage`, `Stage.java:205-211`).
- **The instance this case tests.** This case tests the **Sampler executor's `queueLimit` = 1000**. It was chosen because its queued tasks carry caller-supplied, workload-sized objects: partition keys up to 65,535 B (`Validation.java:51`, `FBUtilities.java:158`), or CQL strings. That makes it the memory-significant instance, and a client can drive it. The TracingStage instance is the same mechanism (A4). The `MonitoringTask` instance is a separate, settable constraint with its own name; it was not chosen because it is fed only by timed-out or slow reads (`MonitorableImpl.java:101`, `:115`), drains every 5 s (`MONITORING_REPORT_INTERVAL_MS`, `CassandraRelevantProperties.java:363`), and holds 50 entries by default, so it is a smaller, harder-to-drive bound than the Sampler's 1000 tasks on the plain read path. It is noted in A4 and is a candidate for its own case.
- **Kind:** a hard-coded constant (an `int` literal handed to a builder field).
- **Unit:** tasks (`Runnable`s), **not bytes**.
- **Default:** 1000, fixed in code, with no derivation.
- **How it can be set:** not settable. There is no yaml key and no `-D` property. JMX (`ThreadPoolExecutorJMXAdapter` / `ResizableThreadPoolMXBean.java:27-41`) exposes core and max thread counts only, not queue capacity. A change needs a source edit, a rebuild and a restart.

**A2. What it caps.**

- **Resource:** heap. Each queued task is a `FutureTask` wrapping the lambda `() -> insert(item, value)` (`Sampler.java:109-113`), and that lambda strongly references `item`:
  - a partition-key `ByteBuffer` for READS, WRITES, WRITE_SIZE, READ_* and CAS_CONTENTIONS
  - a CQL `String` for LOCAL_READ_TIME (`ReadExecutionController.java:238-242`)
- **Compared quantity:** `LinkedBlockingQueue.count`, the number of queued tasks. The JDK compares it against the capacity inside `offer()`.

**A3. Mechanism.**

1. **Submission.** `Sampler.addSample(item, value)` submits `() -> insert(item, value)` to the single static `samplerExecutor` whenever `isEnabled()` is true (`Sampler.java:109-113`). The executor is shared by every table and every sampler type. Callers include:
   - `ColumnFamilyStore.java:1480-1482` (writes)
   - `SinglePartitionReadCommand.java:916-917` and `:1055-1056` (reads)
   - `ReadCommand.java:612-615`
   - `StorageProxy.java:456`
   - `Paxos.java:811`
   - `ReadExecutionController.java:242`
2. **Executor construction.**
   - The executor comes from `withJmxInternal()` → `configureSequential("Sampler")` → `ThreadPoolExecutorBuilder.sequentialJmx` (`ExecutorFactory.java:73`, `:261`).
   - That gives `threads = 1` and core threads that never time out (`ThreadPoolExecutorBuilder.java:45-49`).
   - With `queueLimit = 1000`, `coreThreads()` returns 1 (`:177`) and `maxThreads()` returns 1 (`:180-183`).
3. **The queue itself.**
   - `ThreadPoolExecutorBase.java:75` passes `builder.newQueue()` to the JDK `ThreadPoolExecutor`.
   - `newQueue()` computes `size = 1000` (`ThreadPoolExecutorBuilder.java:163-164`) and calls `newBlockingQueue(1000)` (`:167`).
   - `1000 != 0`, so **[`BlockingQueues.java:46`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/concurrent/BlockingQueues.java#L46)** returns `new LinkedBlockingQueue<>(1000)`.
4. **Rejection handler.**
   - The builder's handler, `recordSelfDroppedMessage(Verb._SAMPLE)` (`Sampler.java:104`), is installed at `ThreadPoolExecutorBase.java:83`. It replaces the default `blockingExecutionHandler` (`:39-66`), so the caller does **not** block.
   - `ThreadPoolExecutorJMXAdapter` then wraps that handler (`ThreadPoolExecutorJMXAdapter.java:137`, `:230-243`). The wrapper increments `TotalBlockedTasks` and `CurrentlyBlockedTasks` (`ThreadPoolMetrics.java:61`, `:87`, `:103`).
5. **The check.** `submit` → `ThreadPoolExecutorPlus.addTask` → `ThreadPoolExecutor.execute` (`ThreadPoolExecutorPlus.java:48-70`). After the single core worker exists, `execute` calls `workQueue.offer(task)`. `LinkedBlockingQueue.offer` returns `false` when `count == capacity`. `addWorker(task, false)` then fails because `maximumPoolSize == 1`, and `reject(task)` runs.
   - **Below the limit:** the task is queued.
   - **At the limit:** the task is dropped. `_SAMPLE` dropped (`MessagingMetrics.java:129-131`) and `TotalBlockedTasks` each go up by 1. The submitter returns at once. The `Future` that `submit` returns is never completed, and `addSample` discards it, so it becomes garbage.
6. **Overshoot and bypass.**
   - **+1 task in progress.** The worker holds one task outside the queue, so at most 1001 tasks are retained.
   - **The cap is on count, not bytes.** Retained bytes = Σ retained size of each task's `item`:
     - A key `ByteBuffer` decoded from a request is an exact-length copy (`CBUtil.readValue`, `CBUtil.java:443-450`).
     - A key returned by `merged.partitionKey()` from a memtable can be a slice of a 1 MiB slab region under `memtable_allocation_type: heap_buffers` (`conf/cassandra.yaml:825`, `SlabAllocator.java:51-52`). A queued task can therefore pin up to 1 MiB, and the byte bound becomes 1000 × that.
     - LOCAL_READ_TIME strings are `command.toCQLString()`, which grows with the key size (hex) and with IN/clustering lists.
     - The constraint bounds none of these sizes.
   - **The Integer.MAX_VALUE path.** Every other executor that reaches line 46 gets `capacity = Integer.MAX_VALUE`, which for heap purposes is unbounded.

**A4. Other consumers.**

- **TracingStage.** It uses the same mechanism with its own 1000-task cap (`Stage.java:196-203`). Its queued tasks hold trace-event `Mutation`s (`TraceStateImpl.java:63-68`, `:104-110`). Its rejected `Future`s stay referenced in the per-session `pendingFutures` set (`TraceStateImpl.java:56`, `:107`) until the trace session ends.
- **`MonitoringTask` queues.** Two more line-46 queues of `cassandra.monitoring_max_operations` (default 50) entries each, holding timed-out or slow read commands until the next 5 s report (`MonitoringTask.java:65-91`, `:207-248`). In the cluster tier they stay empty unless reads time out or exceed `slow_query_log_timeout`; the class histogram would show them as `MonitoringTask$SlowOperation`/`$FailedOperation` instances.
- **Sampler state:** `StreamSummary` (FrequencySampler, capacity ≤ 1024 by `ProfileLoad` validation) and `MinMaxPriorityQueue` (MaxSampler) retain up to `-s` items each, per sampler and table (`FrequencySampler.java:55-61`, `MaxSampler.java:40-49`).
- **Unbounded `LinkedBlockingQueue(Integer.MAX_VALUE)` executors:** compaction, validation, view build, secondary index, cache cleanup and repair.
- **Other heap users:** request frames, memtables, key and row caches, and the chunk cache.

**A5. Evidence beyond the source.**

- `test/unit/org/apache/cassandra/metrics/SamplerTest.java:56-110` (`sampleLoadshedding`) blocks the sampler thread and submits 1002 samples. It asserts 1001 calls to `insert` and exactly 1 `_SAMPLE` drop; the comment at `:101` reads "1000 queued, 1 in progress, 1 to drop". This is direct in-tree evidence of the task-count cap. It says nothing about bytes.
- JDK 11 `ThreadPoolExecutor` docs (queuing and rejected tasks): https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- JDK 11 `LinkedBlockingQueue(int)` and `offer`: https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html
- Git history was not available in the copy (it has no `.git`), and the issue tracker was not consulted.

## B. Verification solution

**B1. Claim under test.**

- **Count claim.** While samples arrive faster than the single sampler thread consumes them, the Sampler executor's queue holds at most 1000 tasks. Every further sample is dropped and counted as `_SAMPLE`.
- **Heap claim.** The heap retained by the sampler queue therefore plateaus at about 1000 × the per-task retained size (≈ 57–60 MiB with 60,000-byte keys) instead of growing with the backlog.
- **What refutes it.** A queue length above 1001, or queue-attributable heap that keeps growing while arrivals exceed service.

### B2. Unit tier

**B2a. Environment and build.**

- **Toolchain:** JDK 11 and Ant.
- **Working copy:** copy the tree to local disk and work only there.
  - `export W=/mydata/ce-o137` (any local disk with ≥ 10 GB free and no shared mount)
  - `rsync -a ~/cassandra-5.0.9/ $W/src/`
- **Build:** `cd $W/src && ant build-test`. This is the full jar plus test classes, and it also resolves test dependencies (jamm, byteman).
- **Test source:** `$W/src/test/unit/org/apache/cassandra/metrics/QueueCapO137Test.java` (code in B2e).
- **JVM:** run through `ant testsome`, which adds the jamm agent and the standard test JVM args (`build.xml:1159`, `:1191`). Pass `-Dtest.jvm.args="-Xmx2G -Xms2G"` (`build.xml:94`, `:1192`) so heap readings are stable and the uncapped arm fits.

**B2b. Knobs.**

- **Part A:** the shipped `Sampler.samplerExecutor`, with its fixed 1000-task limit, unchanged.
- **Part B:** `queueLimit` L ∈ {100, 1000, 10,000, `Integer.MAX_VALUE`}, set through the same builder path. Each L builds an executor with `executorFactory().withJmxInternal().configureSequential("CapO137-"+L).withQueueLimit(L).withRejectedExecutionHandler(...)`, so every one reaches line 46 with `capacity = L`.
  - 1000 is the shipped value.
  - 100 and 10,000 show that the plateau follows the knob.
  - `Integer.MAX_VALUE` is the uncapped **positive control** (the default for every other executor).

**B2c. Workload.**

- **Part A.**
  - Block the sampler thread: the first `insert` waits on a latch.
  - Call `addSample(ByteBuffer.allocate(60_000), 1)` N times, for cumulative N = 500, 1000, 1001, 1002, 2000, 5000.
  - Without a cap, 5000 tasks would retain 5000 × ≈ 60.2 KB ≈ 287 MiB. With the cap, 1001 × 60.2 KB ≈ 57.5 MiB.
- **Part B.**
  - For each L, submit one blocker task (it waits on a latch), then M = 20,000 tasks, each capturing a fresh 16,384-byte `byte[]`.
  - Uncapped: 20,000 × ≈ 16.55 KB ≈ 316 MiB. L = 10,000 → ≈ 158 MiB. L = 1000 → ≈ 15.8 MiB. L = 100 → ≈ 1.6 MiB.
  - M exceeds every finite L, so every finite limit is reached and passed.

**B2d. Observables and instruments.**

- **Queue length:** `getPendingTaskCount()` (= `getQueue().size()`, `ThreadPoolExecutorBase.java:151-154`).
- **Capacity actually installed:** `getQueue().getClass()`, and `getQueue().size() + getQueue().remainingCapacity()`. For a `LinkedBlockingQueue` this equals its capacity, so it is a direct check of the line-46 operand.
- **Running tasks:** `getActiveCount()`.
- **Drops:**
  - Part A: `MessagingService.instance().getDroppedMessages().get("_SAMPLE")`, as a delta (`MessagingMetrics.java:180-186`).
  - Part B: an `AtomicLong` incremented by the test's own rejection handler. The JMX-wrapped `TotalBlockedTasks` is read as well.
- **Heap:** used heap from `ManagementFactory.getMemoryMXBean()`, after three `System.gc()` calls with 200 ms pauses, taken as a delta against a baseline recorded just before submission. The resolution is about ±5 MiB, so the L = 100 plateau (≈ 1.6 MiB) is judged on counts only.
- **Not observable directly:** the per-task object overhead beyond the payload (FutureTask, lambda, queue node). It is estimated as about 150–200 B and absorbed into the ±10% tolerance.

**B2e. Procedure.**

1. Write `$W/src/test/unit/org/apache/cassandra/metrics/QueueCapO137Test.java`:

```java
package org.apache.cassandra.metrics;

import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.concurrent.ExecutorPlus;
import org.apache.cassandra.concurrent.ThreadPoolExecutorBase;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.net.MessagingService;

import static org.apache.cassandra.concurrent.ExecutorFactory.Global.executorFactory;

public class QueueCapO137Test
{
    static CountDownLatch latchA = new CountDownLatch(1);

    static final class BlockingSampler extends Sampler<ByteBuffer>
    {
        protected void insert(ByteBuffer item, long value)
        {
            try { latchA.await(10, TimeUnit.MINUTES); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
        }
        public boolean isEnabled() { return true; }
        public boolean isActive() { return true; }
        public void beginSampling(int capacity, long durationMillis) {}
        public List<Sample<ByteBuffer>> finishSampling(int count) { return null; }
        public String toString(ByteBuffer value) { return ""; }
    }

    @BeforeClass
    public static void init() { DatabaseDescriptor.daemonInitialization(); }

    static long liveHeap() throws InterruptedException
    {
        for (int i = 0; i < 3; i++) { System.gc(); Thread.sleep(200); }
        return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    }

    static int dropped() { Integer d = MessagingService.instance().getDroppedMessages().get("_SAMPLE"); return d == null ? 0 : d; }

    @Test
    public void partA_shippedSamplerExecutor() throws Exception
    {
        ThreadPoolExecutorBase ex = (ThreadPoolExecutorBase) Sampler.samplerExecutor;
        BlockingSampler s = new BlockingSampler();
        long h0 = liveHeap(); int d0 = dropped(); int sent = 0;
        System.out.printf("O137A queueClass=%s capacity=%d%n", ex.getQueue().getClass().getName(),
                          ex.getQueue().size() + ex.getQueue().remainingCapacity());
        for (int target : new int[]{ 500, 1000, 1001, 1002, 2000, 5000 })
        {
            while (sent < target) { s.addSample(ByteBuffer.allocate(60_000), 1); sent++; }
            Thread.sleep(500);
            System.out.printf("O137A N=%d pending=%d active=%d droppedDelta=%d heapDeltaMiB=%.1f%n",
                              sent, ex.getPendingTaskCount(), ex.getActiveCount(), dropped() - d0,
                              (liveHeap() - h0) / 1048576.0);
        }
        latchA.countDown();
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(60);
        while (ex.getPendingTaskCount() > 0 && System.nanoTime() < deadline) Thread.sleep(100);
        System.out.printf("O137A drained pending=%d heapDeltaMiB=%.1f%n", ex.getPendingTaskCount(), (liveHeap() - h0) / 1048576.0);
    }

    @Test
    public void partB_queueLimitSweep() throws Exception
    {
        final int M = 20_000;
        for (int limit : new int[]{ 100, 1000, 10_000, Integer.MAX_VALUE })
        {
            AtomicLong drops = new AtomicLong();
            ExecutorPlus e = executorFactory().withJmxInternal().configureSequential("CapO137-" + limit)
                                              .withQueueLimit(limit)
                                              .withRejectedExecutionHandler((r, x) -> drops.incrementAndGet())
                                              .build();
            ThreadPoolExecutorBase ex = (ThreadPoolExecutorBase) e;
            CountDownLatch latch = new CountDownLatch(1);
            long h0 = liveHeap();
            e.execute(() -> { try { latch.await(10, TimeUnit.MINUTES); } catch (InterruptedException ie) { Thread.currentThread().interrupt(); } });
            Thread.sleep(200);
            for (int i = 0; i < M; i++)
            {
                final byte[] payload = new byte[16_384];
                e.execute(() -> { if (payload.length == 0) throw new AssertionError(); });
            }
            System.out.printf("O137B L=%d queueClass=%s capacity=%d pending=%d active=%d drops=%d heapDeltaMiB=%.1f%n",
                              limit, ex.getQueue().getClass().getName(),
                              ex.getQueue().size() + ex.getQueue().remainingCapacity(),
                              ex.getPendingTaskCount(), ex.getActiveCount(), drops.get(),
                              (liveHeap() - h0) / 1048576.0);
            latch.countDown();
            e.shutdown();
            e.awaitTermination(2, TimeUnit.MINUTES);
            System.out.printf("O137B L=%d afterShutdown heapDeltaMiB=%.1f%n", limit, (liveHeap() - h0) / 1048576.0);
        }
    }
}
```

2. Run it: `cd $W/src && ant testsome -Dtest.name=org.apache.cassandra.metrics.QueueCapO137Test -Dtest.jvm.args="-Xmx2G -Xms2G" 2>&1 | tee $W/unit.log`.
3. Extract the readings: `grep -h O137 $W/unit.log $W/src/build/test/output/TEST-org.apache.cassandra.metrics.QueueCapO137Test.* 2>/dev/null`. stdout is captured in the JUnit report.
4. Repeat steps 2–3 twice more. Use the median of the three heap readings.

**B2f. Predictions.**

**Part A** (shipped executor, `queueClass=java.util.concurrent.LinkedBlockingQueue`, `capacity=1000`):

| N submitted | pending | active | droppedDelta | heapDeltaMiB |
|---|---|---|---|---|
| 500 | 499 | 1 | 0 | ≈ 28.7 (±10%) |
| 1000 | 999 | 1 | 0 | ≈ 57.4 |
| 1001 | 1000 | 1 | 0 | ≈ 57.5 |
| 1002 | 1000 | 1 | 1 | ≈ 57.5 |
| 2000 | 1000 | 1 | 999 | ≈ 57.5 |
| 5000 | 1000 | 1 | 3999 | ≈ 57.5 (not ≈ 287) |
| drained | 0 | — | 3999 | ≈ 0 (±5) |

**Part B** (M = 20,000):

| L | capacity | pending | drops | heapDeltaMiB |
|---|---|---|---|---|
| 100 | 100 | 100 | 19,900 | ≈ 1.6 (within noise) |
| 1000 | 1000 | 1000 | 19,000 | ≈ 15.8 ±10% |
| 10,000 | 10,000 | 10,000 | 10,000 | ≈ 158 ±10% |
| `Integer.MAX_VALUE` | 2147483647 | 20,000 | 0 | ≈ 316 ±10% |

In every arm, heapDelta returns to ≈ 0 after shutdown.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Part A pending plateaus at exactly 1000, droppedDelta = N − 1001, heap flat at ≈ 57.5 MiB from N = 1001 to 5000 | claim confirmed at the unit level |
| Part A pending > 1000, or droppedDelta < N − 1001 | **claim wrong**: the queue is not capped at 1000 (for example the capacity was not 1000, or a second worker started) |
| Part A pending = 1000 but heap keeps rising with N (for example ≈ 287 MiB at 5000) | **claim wrong for heap**: rejected tasks are retained somewhere (for example the rejection path keeps a reference) |
| Part B pending = min(L, M) and heap ∝ min(L, M), with the uncapped control at ≈ 316 MiB | the cap follows the knob, and the positive control shows the workload moves heap when uncapped (confirmed) |
| Uncapped control does not reach ≈ 316 MiB | the measurement is not sensitive (heap reading, GC, payload elided): **not confirmed**, so fix the instrument |
| `capacity` printed ≠ L | line 46 did not receive `queueLimit` (trace wrong) |
| `queueClass` = `SynchronousQueue` for L ≠ 0 | line 45 was taken instead of 46 (trace wrong) |

**B2h. Controls.**

- **The uncapped arm** (`Integer.MAX_VALUE`) is the positive control: it uses the same payload and submission loop, and heap is expected to grow linearly.
- **The drained readings** show the heap delta belongs to queued tasks, not to leaked state.
- **The capacity print** confirms which line-46 operand was installed.
- **Part A's drop counter** is a process-global metric. Part A runs first in a fresh JVM (JUnit method order is not guaranteed, so also read d0 as printed), and the counter is taken as a delta.
- **GC noise** is handled by three `System.gc()` calls and three repeats.

### B3. Cluster tier

**B3a. Environment and build.**

- **Node:** one Linux node with JDK 11 and Ant, using the copy from B2a.
- **Builds.** Make two builds:
  - **stock:** `cd $W/src && ant jar stress-build build-test`. `build-test` puts `byteman-4.0.20.jar` under `build/`, and `find $W/src/build -name 'byteman-4.0.20.jar'` finds it. If it is absent, download `https://repo1.maven.org/maven2/org/jboss/byteman/byteman/4.0.20/byteman-4.0.20.jar` into `$W/bm/`.
  - **uncapped control:** `rsync -a $W/src/ $W/src-uncapped/`. Edit `$W/src-uncapped/src/java/org/apache/cassandra/metrics/Sampler.java:103` to `.withQueueLimit(Integer.MAX_VALUE)`, then `cd $W/src-uncapped && ant jar`.
- **Node configuration.** Edit `conf/cassandra.yaml` in each build.
  - Directories, all on local disk:
    - `data_file_directories: [$W/data/d]`
    - `commitlog_directory: $W/data/cl`
    - `hints_directory: $W/data/h`
    - `saved_caches_directory: $W/data/sc`
    - `cdc_raw_directory: $W/data/cdc`
  - Ports, to avoid clashes on a shared host:
    - `native_transport_port: 19042`
    - `storage_port: 17000`
  - Keep `memtable_allocation_type: heap_buffers` (the default). Reads happen after a flush (B3e), so read keys are not slab slices.
- **JVM.**
  - `export MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M JMX_PORT=17199`
  - `export JVM_EXTRA_OPTS="-javaagent:$BMJAR=script:$W/slow-sampler.btm"`, honored at `conf/cassandra-env.sh:307`.
- **Byteman script** `$W/slow-sampler.btm`. It slows the one sampler thread to a known service rate. This is a lever that makes arrivals exceed service; the queue code path is unchanged.

```
RULE o137 slow FrequencySampler.insert
CLASS org.apache.cassandra.metrics.FrequencySampler
METHOD insert
AT ENTRY
IF true
DO Thread.sleep(2)
ENDRULE
```

**B3b. Knobs.**

| Arm | Build | Byteman | Sampler | Purpose |
|---|---|---|---|---|
| C-base | stock | yes | off (no `profileload`) | heap baseline under the same reads |
| C1 | stock | yes | `profileload -a READS` | the shipped `queueLimit=1000` at the boundary |
| C2 | uncapped | yes | `profileload -a READS` | positive control, with the queue limit removed (`Integer.MAX_VALUE`) |
| C0 | stock | no | `profileload -a READS` | informational: does natural load reach 1000? |

- **Read rate:** fixed at 1000 reads/s. Each read of an existing partition submits exactly one READS sample (`SinglePartitionReadCommand.java:913-917` or `:1054-1056`). The other samplers stay disabled through `-a READS`, so LOCAL_READ_TIME, READ_ROW_COUNT and READ_SSTABLE_COUNT submit nothing.
- **Service rate:** at most 500 inserts/s with the 2 ms sleep (≈ 450–500 including the 60 KB hash).
- **Net backlog growth:** ≈ 500–550 tasks/s.

**B3c. Workload.**

- **Stress profile** `$W/o137.yaml`:

```yaml
keyspace: ce137
keyspace_definition: |
  CREATE KEYSPACE ce137 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};
table: t
table_definition: |
  CREATE TABLE t (k blob PRIMARY KEY, v int) WITH caching = {'keys': 'NONE', 'rows_per_partition': 'NONE'};
columnspec:
  - name: k
    size: fixed(60000)
    population: uniform(1..16)
  - name: v
    population: uniform(1..100)
insert:
  partitions: fixed(1)
  batchtype: UNLOGGED
queries:
  read1:
    cql: select * from t where k = ?
    fields: samerow
```

- **Data:** 16 partitions with 60,000-byte keys, ≈ 1 MB of data. Disk use is negligible.
- **Requests:** each read carries a 60,000-byte bound key, which the server copies exactly (`CBUtil.java:443-450`). Each queued READS task therefore retains ≥ 60,016 B (array) plus about 150 B of wrappers, ≈ 60.2 KB.
- **Arithmetic:**
  - **C1:** the queue reaches 1000 after ≈ 1000 / (1000 − 500) ≈ 2 s, then sheds ≈ 500 samples/s. The predicted plateau is 1000 × 60.2 KB ≈ 57.4 MiB.
  - **C2:** the backlog grows ≈ 500 tasks/s, so 60 s of sampling gives ≈ 30,000 tasks × 60.2 KB ≈ 1.7 GiB. That is below the 4 GiB heap, so it is safe.
- **Durations:**
  - read load: 180 s (60 s baseline, then 90 s with sampling, then 30 s drain)
  - `profileload` window: 60 s in C2 (to bound heap), 90 s in C1 and C0

**B3d. Observables and instruments.**

- **Queue length:** sampled every 1 s with `nodetool -p 17199 sjk mx -mg -b "org.apache.cassandra.metrics:type=ThreadPools,path=internal,scope=Sampler,name=PendingTasks" -f Value` (names from `ThreadPoolMetrics.java:100`, `:123-131`).
- **Drops / blocked:** every 10 s, `nodetool -p 17199 tpstats`. Read the `Sampler` pool row (Pending, Blocked, All time blocked) and the `_SAMPLE` row under dropped messages.
- **Heap (the actual resource):** every 10 s, `jcmd $PID GC.class_histogram > $W/runs/<arm>/histo-<t>.txt`. This forces a full GC, so the histogram counts live objects only. Record:
  - total bytes of `[B`
  - instance count of `java.util.concurrent.LinkedBlockingQueue$Node`
  - the summary line `Total`
- **GC context:** `jstat -gcutil $PID 1000 > $W/runs/<arm>/jstat.txt` for GC activity.
- **Queue-attributable heap** = live heap (or `[B` bytes) in the arm minus C-base at the same phase.
- **Not directly observable:** the retained size of the Sampler queue alone, and which `[B` arrays it holds. It is inferred from the deltas and from the C2 slope (Δ`[B` bytes / Δpending). An optional cross-check: `jcmd $PID GC.heap_dump $W/runs/C1/h.hprof` at plateau, then retained size of the `samplerExecutor` queue in Eclipse MAT (needs about 4 GB of disk).

**B3e. Procedure.** Run each arm from a fresh data directory. For C2, `S=$W/src-uncapped`; otherwise `S=$W/src`.

1. **Prepare the run directory.** `rm -rf $W/data && mkdir -p $W/data $W/runs/<arm>`.
2. **Start the node.**
   - Export the env from B3a; omit `JVM_EXTRA_OPTS` for C0.
   - `$S/bin/cassandra -p $W/runs/<arm>/pid`, then `PID=$(cat $W/runs/<arm>/pid)`.
   - Wait until `$S/bin/nodetool -p 17199 status` shows `UN`.
3. **Populate.** `$S/tools/bin/cassandra-stress user profile=$W/o137.yaml "ops(insert=1)" n=2000 -rate threads=8 -node 127.0.0.1 -port native=19042 jmx=17199`.
4. **Flush and check.**
   - `$S/bin/nodetool -p 17199 flush ce137 t`
   - `$S/bin/cqlsh 127.0.0.1 19042 -e "SELECT count(*) FROM ce137.t"`. It must print 16.
5. **Start the samplers.** Start the 1 s PendingTasks loop, the 10 s tpstats + class-histogram loop, and `jstat`, all in the background with output to `$W/runs/<arm>/`.
6. **Start the reads.** `$S/tools/bin/cassandra-stress user profile=$W/o137.yaml "ops(read1=1)" duration=180s -rate threads=64 fixed=1000/s -node 127.0.0.1 -port native=19042 jmx=17199 > $W/runs/<arm>/stress.txt &`.
7. **Start sampling at t = 60 s** (skip this step for C-base).
   - C1, C0: `$S/bin/nodetool -p 17199 profileload -a READS -s 256 -k 10 ce137 t 90000 > $W/runs/<arm>/profileload.txt`
   - C2: the same command with 60000 instead of 90000
   - It blocks for the window, then disables the sampler, so no new submissions follow.
8. **Abort rule for C2.** Stop the read early if old-gen occupancy (`jstat` O column) exceeds 85%.
9. **Drain.** Let stress finish, then keep sampling for 30 s more to see the queue drain.
10. **Stop.**
    - Stop the sampler loops.
    - `$S/bin/nodetool -p 17199 stopdaemon || kill $PID`, then wait until `kill -0 $PID` fails.
    - `pgrep -f "CassandraDaemon.*$W" || echo clean`
11. **Repeat C1 and C2** once more each.

**B3f. Predictions.**

| Arm | PendingTasks during sampling | `_SAMPLE` dropped / All time blocked | Queue-attributable live heap (vs C-base) |
|---|---|---|---|
| C-base | 0 | 0 | 0 (definition) |
| C1 | rises to 1000 within ≤ 5 s of `profileload` start, then stays in [990, 1000] and **never exceeds 1000** | grows ≈ 450–550/s, ≈ 40,000–50,000 over 90 s | rises to ≈ 57–60 MiB (`[B` +≈ 57 MiB, `LinkedBlockingQueue$Node` +≈ 1000) and stays **flat** until the window ends, then returns to ≈ 0 within ≈ 3 s |
| C2 | rises linearly ≈ 450–550/s, ≈ 27,000–33,000 at 60 s | 0 | rises linearly ≈ 26–33 MiB/s, to ≈ 1.6–1.9 GiB at 60 s, then drains over ≈ 60 s |
| C0 | informational; likely stays well below 1000 at 1000 reads/s, since the sampler thread is not slowed | ≈ 0 | ≈ small (< 10 MiB) |

- **Derived check:** let s = C2 slope (Δheap / Δpending). C1's plateau should be ≤ 1001 × s × 1.1.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| C1 PendingTasks ≤ 1000 throughout, drops ≈ arrival − service, heap delta flat at ≈ 1000 × s; C2 grows as predicted | **claim confirmed**: the cap binds and governs heap |
| C1 PendingTasks > 1000 at any sample | **claim wrong**: the queue cap is not enforced |
| C1 PendingTasks = 1000 but the heap delta keeps growing with time (approaching C2's slope) | **claim wrong for heap**: something outside the queue retains the samples (for example dropped `Future`s or sampler state) |
| C1 heap plateau ≫ 1001 × s (for example several hundred MiB) with PendingTasks = 1000 | count cap holds but per-task retention is larger than the key, for example slab or frame pinning. Report it as **count-capped, byte bound ≠ key bound**. |
| C2 does not grow (pending stays low) | the workload or Byteman lever did not create a backlog: **not confirmed**. Check that the rule fired (C1 pending also stays low) and that reads hit existing keys. |
| C1 PendingTasks never reaches 1000 | the limit was not reached: **not confirmed**. Raise the rate (`fixed=2000/s`) or the sleep (5 ms). |
| C0 reaches 1000 at natural load | extra finding: the cap also binds without fault injection |

**B3h. Controls.**

- **C-base** isolates heap used by the read workload itself.
- **C2** is the positive control. It runs the same workload, the same Byteman delay and the same keys, with the queue limit removed, and shows the workload moves heap by GiBs when nothing caps it.
- **Sampler isolation.** `-a READS` limits the sampler to one type and one submission per read.
- **Clean read keys.** Flushing before reads keeps read keys from being memtable slab slices.
- **No read cache.** `caching = NONE` keeps the key or row cache from adding heap.
- **Live-only heap.** Class histograms force a full GC, so only live objects are counted.
- **Drain check.** The post-window drain to ≈ 0 attributes the plateau to queued tasks.
- **Repeats.** Each arm is repeated.

**B4. Risks and cleanup.**

- **Disk.** Everything goes under `$W` on local disk:
  - data, commit log and hints: < 1 GB
  - logs
  - optional heap dump: up to ≈ 4 GB
  - Nothing goes on shared storage. The shared tree `~/cassandra-5.0.9` is never built in or written to.
- **Memory.** The C2 heap is bounded by the 60 s window and the 85% old-gen abort rule (B3e step 8). The node's 4 GiB heap must fit in free RAM; check `free -g` first.
- **Ports.** 19042, 17000 and 17199 must be free (`ss -ltn`) before starting.
- **Processes.**
  - After each arm: `nodetool stopdaemon` or kill the PID, and kill the background sampler loops (`kill %1 %2 ...`, or by PID files).
  - `pgrep -f CassandraDaemon`, `pgrep -f cassandra-stress` and `pgrep -f "jstat.*$PID"` must return nothing. The unit-tier `ant` JVM exits by itself; check `pgrep -f QueueCapO137Test`.
- **Cleanup.** `rm -rf $W/data $W/runs/*/h.hprof`. Keep `$W/runs/*` text outputs and `$W/unit.log` for the results file. Remove `$W` at the end if it is no longer needed.

## C. Sources read

- src/java/org/apache/cassandra/utils/concurrent/BlockingQueues.java
- src/java/org/apache/cassandra/concurrent/ThreadPoolExecutorBuilder.java
- src/java/org/apache/cassandra/db/monitoring/MonitoringTask.java
- src/java/org/apache/cassandra/db/monitoring/MonitorableImpl.java (grep :101, :115)
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (:361, :363)
- src/java/org/apache/cassandra/concurrent/ThreadPoolExecutorBase.java
- src/java/org/apache/cassandra/concurrent/ThreadPoolExecutorPlus.java
- src/java/org/apache/cassandra/concurrent/SingleThreadExecutorPlus.java
- src/java/org/apache/cassandra/concurrent/ThreadPoolExecutorJMXAdapter.java
- src/java/org/apache/cassandra/concurrent/ExecutorFactory.java
- src/java/org/apache/cassandra/concurrent/ResizableThreadPool.java
- src/java/org/apache/cassandra/concurrent/ResizableThreadPoolMXBean.java
- src/java/org/apache/cassandra/concurrent/Stage.java
- src/java/org/apache/cassandra/metrics/Sampler.java
- src/java/org/apache/cassandra/metrics/FrequencySampler.java
- src/java/org/apache/cassandra/metrics/MaxSampler.java
- src/java/org/apache/cassandra/metrics/ThreadPoolMetrics.java
- src/java/org/apache/cassandra/metrics/MessagingMetrics.java
- src/java/org/apache/cassandra/metrics/TableMetrics.java (topReadPartitionFrequency, :419)
- src/java/org/apache/cassandra/db/compaction/CompactionManager.java (:2010-2160)
- src/java/org/apache/cassandra/db/ReadExecutionController.java
- src/java/org/apache/cassandra/db/ReadCommand.java (:600-620)
- src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java (:905-920, :1045-1058)
- src/java/org/apache/cassandra/db/ColumnFamilyStore.java (grep: :1480-1482, :2056-2063)
- src/java/org/apache/cassandra/service/ActiveRepairService.java (:200-225)
- src/java/org/apache/cassandra/service/StorageProxy.java (grep :456)
- src/java/org/apache/cassandra/service/paxos/Paxos.java (grep :811)
- src/java/org/apache/cassandra/tracing/TraceStateImpl.java
- src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java (grep :311)
- src/java/org/apache/cassandra/io/sstable/SSTableSimpleUnsortedWriter.java (grep :68)
- src/java/org/apache/cassandra/transport/CBUtil.java (:443-463, :555-565)
- src/java/org/apache/cassandra/cql3/QueryOptions.java (grep)
- src/java/org/apache/cassandra/cql3/Validation.java (:51-55)
- src/java/org/apache/cassandra/utils/FBUtilities.java (:158)
- src/java/org/apache/cassandra/utils/memory/SlabAllocator.java (:51-52, :92)
- src/java/org/apache/cassandra/utils/ObjectSizes.java (grep)
- src/java/org/apache/cassandra/tools/nodetool/ProfileLoad.java
- src/java/org/apache/cassandra/tools/NodeProbe.java (:1956-1959)
- src/java/org/apache/cassandra/tools/nodetool/stats/TpStatsHolder.java (grep)
- src/java/org/apache/cassandra/net/Verb.java (:212-213)
- test/unit/org/apache/cassandra/metrics/SamplerTest.java
- test/resources/byteman/stream_failure.btm
- test/unit/org/apache/cassandra/inject/Injections.java (grep :498)
- tools/cqlstress-example.yaml
- tools/stress/src/org/apache/cassandra/stress/settings/SettingsRate.java (grep)
- conf/cassandra.yaml (:825), conf/cassandra-env.sh (grep), conf/jvm11-server.options (grep)
- build.xml, .build/parent-pom-template.xml (grep: test JVM args, jamm/byteman versions)
- https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html

## D. Stage-4 feedback

none yet
