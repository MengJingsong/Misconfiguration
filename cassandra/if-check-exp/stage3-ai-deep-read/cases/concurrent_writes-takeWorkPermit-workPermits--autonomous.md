# concurrent_writes — verification solution  <!-- file: cases/concurrent_writes-takeWorkPermit-workPermits--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/concurrent/SEPExecutor.java:196` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code autonomous agent (subagent), 2026-10-21 |
| Estimate | `negative`. Line 196 checks whether a *work permit* (a concurrency slot) is free, so `concurrent_writes` limits how many mutations run at the same time. It does not limit how much memory they take: tasks that find no permit go into an unbounded queue that stays on the heap. |
| Ground | The operand `workPermits` is a thread or slot count, with no byte accounting (`SEPExecutor.java:57-60, 194-198`). When it is 0, the task is added to an unbounded `ConcurrentLinkedQueue` (`SEPExecutor.java:68, 123, 221-223`). The advertised queue limit is `Integer.MAX_VALUE` (`SEPExecutor.java:102-106`), and `addTask` never blocks or rejects (`SEPExecutor.java:129-133`). A lower value therefore leaves *more* mutations, each holding its column values on the heap, waiting in the queue. The only memory the knob bounds directly is the stacks of at most N worker threads (N × `-Xss256k`, `conf/jvm-server.options:123`). That is 8 MiB at the default N = 32, which is not significant. |

## A. Constraint trace

**A1. The constraint.**
- **Name and kind:** `concurrent_writes`, a configuration entry (cassandra.yaml), applied at runtime as the `maximumPoolSize` of the `MutationStage` SEP executor.
- **Declared:** `src/java/org/apache/cassandra/config/Config.java:180` (`public int concurrent_writes = 32;`). It also appears in `conf/cassandra.yaml:723`, documented at `conf/cassandra.yaml:719-721`.
- **Unit and default:** a count of concurrent tasks (no byte unit). The default is the constant 32. Nothing derives it, although the yaml comment recommends 8 × cores.
- **Validation:** `DatabaseDescriptor.java:565-567` rejects values below 2 at startup.
- **Getter and setter:** `DatabaseDescriptor.java:2415-2427`. The setter accepts any value ≥ 0, so 0 is allowed at runtime.
- **How it reaches line 196:**
  1. `Stage.MUTATION` passes `DatabaseDescriptor::getConcurrentWriters` (`Stage.java:46`).
  2. `Stage.multiThreadedLowSignalStage` (`Stage.java:229-235`) calls `ExecutorFactory...shared(...)` (`ExecutorFactory.java:244-247`).
  3. That calls `SharedExecutorPool.SHARED.newExecutor(threads, ...)` (`SharedExecutorPool.java:146-151`).
  4. The `SEPExecutor` constructor stores it in `maximumPoolSize` and initialises `permits = combine(0, maximumPoolSize)` (`SEPExecutor.java:70-77`).
- **How it is set:**
  - yaml `concurrent_writes`, which needs a restart.
  - At runtime without a restart, through `nodetool setconcurrency MutationStage <n>` (`tools/nodetool/SetConcurrency.java:39-58`). The path is `StorageService.setConcurrency` (`StorageService.java:2397-2403`), then `Stage.setMaximumPoolSize` (`Stage.java:275-278`), then `SEPExecutor.setMaximumPoolSize` (`SEPExecutor.java:368-396`). That method moves the work-permit count by the delta (`:387`) and calls the listener `DatabaseDescriptor::setConcurrentWriters` (`:395`). The runtime path accepts 0 (`SEPExecutor.java:373`), which the yaml path does not.
- **Same line, other limits:** line 196 serves every SEP-backed stage. These are `concurrent_reads` (`Stage.java:45`), `concurrent_counter_writes` (`:47`), `concurrent_materialized_view_writes` (`:48`), `REQUEST_RESPONSE` (number of processors, `:50`), and `native_transport_max_threads` / `native_transport_max_auth_threads` (`transport/Dispatcher.java:58, 77`). I traced it as `concurrent_writes` because the client write path reaches line 196 directly. `StorageProxy.performLocally` calls `Stage.MUTATION.maybeExecuteImmediately` (`StorageProxy.java:229, 1569, 1676`), which calls `takeWorkPermit(false)` (`SEPExecutor.java:221`). The analysis holds for the other stages with only the name changed.

**A2. What it caps.**
- **Quantity compared:** `workPermits = workPermits(permits)`, the top 32 bits of `permits` (`SEPExecutor.java:194, 403-406`). It equals `maximumPoolSize − activeTasks`, as `getActiveTaskCount` shows (`SEPExecutor.java:347-350`). The check is `workPermits <= 0 || taskPermits == 0` (`:196`).
- **What that bounds:** the number of `MutationStage` tasks executing at once, which also means the number of shared-pool worker threads assigned to this executor.
- **Resource:** this is CPU and concurrency. The only memory directly tied to it is about N thread stacks. It does **not** bound heap or disk. The bytes waiting for a permit (queued `Mutation`s) are not counted against anything in this check.

**A3. Mechanism.**
1. **Submission.**
   - `execute`/`submit` (`SEPExecutor.java:242-288`) always call `addTask`. `addTask` enqueues first (`:123`), then increments the task-permit count in a CAS loop (`:125-133`).
   - The comment at `:129-130` says "block after the fact if we breached the queue limit", but no blocking code follows. The queue-limit notion survives only in the comment at `:58` and the constant `getMaxTasksQueued() = Integer.MAX_VALUE` (`:102-106`).
   - `addTask` then may start a spinning worker (`:135-143`).
2. **Caller-runs path (local writes).**
   - `maybeExecuteImmediately` (`:217-240`) calls `takeWorkPermit(false)`.
   - If line 196 finds `workPermits <= 0`, the method returns false (`:197`) and the task is queued with `addTask` (`:223`), unbounded.
   - Otherwise one work permit is taken by CAS (`:198`), the task runs on the caller's thread (the Native-Transport-Requests SEP worker), the permit is returned (`:233`), and `maybeSchedule()` is called (`:237`).
3. **Worker scheduling.**
   - `maybeSchedule()` (`:110-117`) calls `takeWorkPermit(true)`. That needs both a work permit and a queued task; it decrements both and schedules a `Work` on the shared pool (`SharedExecutorPool.java:101-117`). The pool may create a new `SEPWorker` thread (`SharedExecutorPool.java:114`, `SEPWorker.java:54-62`).
   - Workers also self-assign through `takeWorkPermit(true)` (`SEPWorker.java:245-260`).
   - A worker then drains tasks while `takeTaskPermit(true)` returns `TOOK_PERMIT` (`SEPWorker.java:135-155`), and returns its work permit at the end (`:160-161`).
4. **When the limit is reached.** Nothing is rejected and the producer is not blocked. The task waits in `tasks` until a permit frees up.
5. **What happens to a waiting local mutation.**
   - It is a `LocalMutationRunnable` holding the decoded `Mutation`. Bound values are heap copies: `CBUtil.readBoundValue` and `readValue` call `ByteBuffer.wrap(readRawBytes(...))` (`CBUtil.java:443-450, 466-`).
   - When it is finally dequeued after its deadline (`StorageProxy.java:2634-2657`), it is counted as dropped. If `shouldSendHints()` (`transport/Dispatcher.java:258-261`, true unless `enforce_native_deadline_for_hints`), it is re-submitted to `Stage.MUTATION` as a `HintRunnable` (`StorageProxy.java:2645-2654, 2822-2828`).
   - So expiry does not remove a queued mutation before it reaches a worker. It stays on the heap until a worker dequeues it, and can then be queued again.
6. **Ways around it or past it.**
   - (a) `takeTaskPermit(true)` lets a running worker keep taking queued tasks without re-checking line 196 (`SEPWorker.java:150`). This is correct accounting, not an overshoot.
   - (b) When the pool shrinks at runtime, `workPermits` goes negative (`SEPExecutor.java:59, 165-172`), so for a short time more than the new N workers can be active.
   - (c) The work-permit cap is per executor. The shared pool's thread count is bounded only by the sum over executors, plus spinning workers (`SharedExecutorPool.java:132-139`).
   - None of these is relevant to memory, because the check has no byte dimension at all.

**A4. Other consumers.**

The heap held by pending or in-flight writes is controlled elsewhere, if at all:
- **Native-transport in-flight bytes.**
  - Limits: `native_transport_max_request_data_in_flight` and `native_transport_max_request_data_in_flight_per_ip` (`Config.java:296-298`). They default to heap/10 and heap/40 (`DatabaseDescriptor.java:649-657`).
  - Enforced by `ResourceLimits.Concurrent` (`transport/ClientResourceLimits.java:42, 160`; acquired in `transport/CQLMessageHandler.java:200, 223`).
  - Released when the response is flushed (`CQLMessageHandler.java:497-507`). That includes a WriteTimeout response after `write_request_timeout` (2000 ms, `conf/cassandra.yaml:1330`). A mutation still waiting in `MutationStage` therefore stops being counted after the timeout, even though it is still on the heap.
- **Other bounds on the backlog.**
  - `native_transport_max_threads`: on this path the request threads block in `responseHandler.get()` (`StorageProxy.java:906`), so this limits the arrival rate into `MutationStage`.
  - The internode receive-queue reserves (`Config.java:256-261`) cover replica writes arriving over messaging.
- **Memory and disk the write itself uses:**
  - memtable space: `memtable_heap_space`, `Config.java:186-187`
  - commit log: `commitlog_total_space`, `Config.java:389-390`
  - data disk and compaction, plus the node's other stages, caches and so on.

**A5. Evidence beyond the source.**
- `test/unit/org/apache/cassandra/concurrent/SEPExecutorTest.java`: the existing tests exercise shutdown and resizing (the `BusyExecutor` with `maximumPoolSize = 0`). None of them asserts any queue or memory bound. The test sets up with `SharedExecutorPool(String)` plus `newExecutor` and `DatabaseDescriptor.daemonInitialization()`, and I reuse that setup.
- The `conf/cassandra.yaml:711-721` comment presents `concurrent_*` as concurrency and IO-depth tuning, not memory tuning.
- The git history at the pinned clone is shallow (one commit), so I could not use history.
- No external URL was relied on.

## B. Verification solution

**B1. Claim under test.** `concurrent_writes` (`MutationStage` maximum pool size) does
**not** cap the memory held by pending writes. It caps only the number of mutations
running at once (`activeTasks ≤ N`). Heap held by queued mutations keeps growing with
the backlog, whatever N is, and is no lower for smaller N. With N = 0 at runtime it
grows past the native-transport in-flight cap.

### B2. Unit tier

**B2a. Environment and build.**
- **JDK and Ant:** JDK 11 (`java -version` must report 11) and Ant 1.10+.
- **Clone:** clone to local disk, never into the shared clone:
  ```
  LOCAL=/local/$USER   # or any local, non-shared dir with >= 10 GiB free; check with df -h
  git clone --branch cassandra-5.0.9 --depth 1 /users/jason92/cassandra-s3 $LOCAL/c509
  cd $LOCAL/c509 && ant jar build-test
  ```
- **Test source:** the new file `$LOCAL/c509/test/unit/org/apache/cassandra/concurrent/SEPQueueHeapProbeTest.java`. It goes in package `org.apache.cassandra.concurrent` so it can cast to `SEPExecutor`.
- **JVM options:** unit tests run with `-Xmx4G` (`build.xml:1245-1255`, the `maxMemory` 4G default). That fits the 500 MiB maximum payload below.

```java
package org.apache.cassandra.concurrent;

import java.lang.management.ManagementFactory;
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.BeforeClass;
import org.junit.Test;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.net.ResourceLimits;

public class SEPQueueHeapProbeTest
{
    static final int S = 64 * 1024;                       // payload per task
    static final int M = Integer.getInteger("probe.tasks", 4000);
    static volatile long sink;

    @BeforeClass public static void init() { DatabaseDescriptor.daemonInitialization(); }

    static long liveHeap() throws InterruptedException
    {
        for (int i = 0; i < 3; i++) { System.gc(); Thread.sleep(300); }
        return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    }

    /** capBytes <= 0: no producer-side cap (claim arm); > 0: positive control gated by ResourceLimits. */
    static void probe(int n, long capBytes) throws Exception
    {
        SharedExecutorPool pool = new SharedExecutorPool("Probe" + n + "_" + capBytes);
        SEPExecutor sep = (SEPExecutor) pool.newExecutor(n, "probe", "ProbeStage" + n + "_" + capBytes);
        ResourceLimits.Concurrent cap = capBytes > 0 ? new ResourceLimits.Concurrent(capBytes) : null;
        CountDownLatch gate = new CountDownLatch(1);
        long base = liveHeap();
        int submitted = 0, rejected = 0;
        for (int i = 0; i < M; i++)
        {
            if (cap != null && !cap.tryAllocate(S)) { rejected++; continue; }
            final byte[] payload = new byte[S];
            Arrays.fill(payload, (byte) i);
            sep.execute(() -> { try { gate.await(); } catch (InterruptedException e) { } sink += payload[0]; });
            submitted++;
        }
        long until = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (sep.getActiveTaskCount() < Math.min(n, submitted) && System.nanoTime() < until) Thread.sleep(10);
        // caller-runs path through line 196: must NOT run inline when all permits are taken
        AtomicBoolean ranInline = new AtomicBoolean();
        Thread caller = Thread.currentThread();
        int pendingBefore = sep.getPendingTaskCount();
        sep.maybeExecuteImmediately(() -> ranInline.set(Thread.currentThread() == caller));
        int pendingAfter = sep.getPendingTaskCount();
        long live = liveHeap() - base;
        System.out.printf("PROBE n=%d cap=%d submitted=%d rejected=%d active=%d pending=%d maxPool=%d " +
                          "mei_inline=%b mei_pendingDelta=%d liveDeltaMiB=%.1f payloadMiB=%.1f%n",
                          n, capBytes, submitted, rejected, sep.getActiveTaskCount(), pendingAfter,
                          sep.getMaximumPoolSize(), ranInline.get(), pendingAfter - pendingBefore,
                          live / 1048576.0, (long) submitted * S / 1048576.0);
        gate.countDown();
        pool.shutdownAndWait(1, TimeUnit.MINUTES);
    }

    @Test public void claim() throws Exception { for (int n : new int[]{ 0, 2, 32, 128 }) probe(n, 0); }
    @Test public void positiveControl() throws Exception { for (long c : new long[]{ 16L << 20, 64L << 20 }) for (int n : new int[]{ 2, 128 }) probe(n, c); }
}
```

**B2b. Knobs.**
- **N = `maximumPoolSize`**, passed to `newExecutor(n, ...)`, the same value `concurrent_writes` supplies in production. Values:
  - 0: the boundary where line 196 always fails; reachable in production via `nodetool setconcurrency`.
  - 2: the yaml minimum.
  - 32: the default.
  - 128: 4 × the default.
- **Producer-side byte cap (positive control):** 16 MiB and 64 MiB, through `ResourceLimits.Concurrent`. This is the class Cassandra uses for the native in-flight limit (`ClientResourceLimits.java:42`).
- **Workload size M (sensitivity):** 4000 and 8000 (`-Dprobe.tasks`).

**B2c. Workload.**
- **Tasks:** M tasks, each capturing a 64 KiB `byte[]` and blocking on a latch, so none finishes during the measurement.
- **Arithmetic:**
  - Active tasks reach `min(N, M)` and every later submission is queued. For each N ≤ 128 < M = 4000 the limit is reached, and exceeded by 4000 − N tasks.
  - Payload held = 4000 × 64 KiB = 250 MiB (500 MiB at M = 8000).
  - With the cap, held payload is at most 16 MiB (256 tasks) or 64 MiB (1024 tasks).

**B2d. Observables and instruments.**
- **Check operands:** `getActiveTaskCount()` = `maximumPoolSize − workPermits` (`SEPExecutor.java:347-350`), and `getPendingTaskCount()` = task permits (`:335-339`).
- **Caller-runs behaviour at line 196:** whether `maybeExecuteImmediately` ran inline, and how much pending changed.
- **Live heap delta:** `MemoryMXBean` heap used after 3 × `System.gc()`, minus the pre-submission baseline. Sampled once per configuration, after the active count has settled.
- **Not directly observable:** per-object retention. The delta also includes the lambda, `FutureTask` and queue-node overhead (about 100 B per task, under 1 MiB in total).

**B2e. Procedure.**
1. Write the test file above into the local clone.
2. Run `cd $LOCAL/c509 && ant testsome -Dtest.name=org.apache.cassandra.concurrent.SEPQueueHeapProbeTest`.
3. Run again with `-Dtest.jvm.args=-Dprobe.tasks=8000`. Alternatively edit the default of `M` to 8000 and rerun.
4. Collect the `PROBE` lines with `grep PROBE build/test/output/TEST-org.apache.cassandra.concurrent.SEPQueueHeapProbeTest*.xml` (or the console output).
5. Confirm no JVM is left with `pgrep -f junit` (it should print nothing).

**B2f. Predictions (before any run).**

Claim arm, M = 4000:

| N | active | pending | maybeExecuteImmediately | liveDelta |
|---|---|---|---|---|
| 0 | 0 | 4001 | `mei_inline=false`, pendingDelta 1 | ≈ 250 MiB (±10%) |
| 2 | 2 | 3999 | `false`, 1 | ≈ 250 MiB |
| 32 | 32 | 3969 | `false`, 1 | ≈ 250 MiB |
| 128 | 128 | 3873 | `false`, 1 | ≈ 250 MiB |

- `payloadMiB` = 250 in every row.
- liveDelta does not fall with N. Across N it varies by at most 10%, with no downward trend as N falls.
- At M = 8000, every row shows ≈ 500 MiB.

Positive control (both N values give the same result):

| cap | submitted | rejected | liveDelta |
|---|---|---|---|
| 16 MiB | 256 | 3744 | ≈ 16 MiB (±4) |
| 64 MiB | 1024 | 2976 | ≈ 64 MiB (±8) |

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| active = min(N, M), pending = M − N, liveDelta ≈ M × 64 KiB for every N, and the control's liveDelta tracks its cap | Claim confirmed. N caps concurrency and the heap is flat in N, while a byte cap binds on the same workload. |
| liveDelta grows with N, or pending is capped at some value independent of M (submissions block or are rejected) | Claim refuted. Usage follows the knob, or a queue bound exists. |
| `mei_inline=true` while active = N | The trace of line 196 is wrong. Re-trace before concluding anything. |
| active < N after 5 s (limit never reached), or the control's liveDelta does not follow 16 vs 64 MiB | Not confirmed. The instrument or setup is not sensitive; fix it and rerun. |
| liveDelta does not double from M = 4000 to M = 8000 | Not confirmed. The heap instrument is not measuring the queue. |

**B2h. Controls.**
- **Same workload with a byte cap:** shows the heap instrument can see a binding cap.
- **M = 4000 vs 8000:** shows sensitivity to queue size.
- **`maximumPoolSize` read back:** confirms N took effect.
- **Fresh pool per configuration plus `shutdownAndWait`:** prevents carry-over between configurations.
- **Repeat for GC noise:** run the claim test twice and require both runs to agree within 10%.

### B3. Cluster tier

**B3a. Environment and build.**
- **Node and clone:** one Linux node. Use the same local clone, built with `cd $LOCAL/c509 && ant jar stress-build`.
- **Local directories (≥ 20 GiB free local disk):**
  ```
  N=$LOCAL/node1; mkdir -p $N/{data,commitlog,saved_caches,hints,cdc,logs}
  ```
- **Edits to `$LOCAL/c509/conf/cassandra.yaml`** (the local copy):
  - `data_file_directories: [$N/data]`
  - `commitlog_directory: $N/commitlog`
  - `saved_caches_directory: $N/saved_caches`
  - `hints_directory: $N/hints`
  - `cdc_raw_directory: $N/cdc`
  - `commitlog_total_space: 2GiB`
  - `listen_address` and `rpc_address: 127.0.0.1`
  - `native_transport_max_request_data_in_flight: 256MiB`
  - `native_transport_max_request_data_in_flight_per_ip: 256MiB`
  - `concurrent_writes:` as in B3b
- **Heap and logs:**
  ```
  export MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_LOG_DIR=$N/logs
  ```
  Add `-XX:HeapDumpPath=$N/logs` to `conf/jvm-server.options`, so a heap dump on OOM stays on local disk.
- **Start, schema and PID:**
  ```
  bin/cassandra -p $N/pid
  bin/nodetool status        # wait for UN
  bin/cqlsh 127.0.0.1 -e "CREATE KEYSPACE IF NOT EXISTS keyspace1 WITH replication={'class':'SimpleStrategy','replication_factor':1};"
  PID=$(cat $N/pid)
  ```
  RF = 1 makes every write take the local `maybeExecuteImmediately` path.

**B3b. Knobs.**

All runs use the same workload.

| Run | Value | How set | Why |
|---|---|---|---|
| R2, R32, R128 | `concurrent_writes` = 2, 32, 128 | yaml, restart between runs | Steady-state load with the queue normally drained |
| R0 | `MutationStage` max pool = 0 for 120 s, then back to 32 | `bin/nodetool setconcurrency MutationStage 0` then `... 32`, at runtime | Forces line 196 to fail on every submission |
| PC | `native_transport_max_request_data_in_flight_per_ip: 4MiB` | yaml, with `concurrent_writes: 32` | Positive control: a byte cap known to bind on this workload |

**B3c. Workload.**
```
tools/bin/cassandra-stress write duration=120s cl=ONE -col n=FIXED(1) size=FIXED(65536) \
  -rate threads=128 -errors ignore retries=0 -mode native cql3 -node 127.0.0.1 \
  -log file=$N/logs/stress-<run>.log
```
- **R2, R32 and R128** add `throttle=400/s` to bound disk. That is 400 × 64 KiB = 25 MiB/s, or 3 GiB per run.
- **R0 runs unthrottled.** No write is applied, so nothing reaches the disk.
  - Native request threads block about 2 s each in `responseHandler.get()` until WriteTimeout.
  - Arrival ≈ min(128 client threads, 128 native threads) / 2 s ≈ 64 mutations/s ≈ 4 MiB/s.
  - Over 120 s that is about 7700 queued mutations ≈ 480 MiB of heap, far above the native in-flight usage, which stays ≤ 128 × 64 KiB = 8 MiB. Each request's capacity is released once its timeout is answered.
- **PC:** 128 threads × 64 KiB = 8 MiB of demand against a 4 MiB cap, so the cap binds.

**B3d. Observables and instruments.**

Sample each every 5 s with a shell loop that appends to `$N/logs/samples-<run>.txt`:
- **Usage-side operand:** `bin/nodetool tpstats | grep -E 'MutationStage'`, giving Active and Pending.
- **Actual heap:** `jcmd $PID GC.run; jcmd $PID GC.heap_info`. Record "used" after the forced full GC (G1, `conf/jvm11-server.options:63`). Sample every 15 s to limit GC perturbation.
- **Native in-flight bytes:** JMX `org.apache.cassandra.metrics:type=Client,name=RequestsSize` (`metrics/ClientMetrics.java:129`), read with `bin/nodetool sjk mx -b org.apache.cassandra.metrics:type=Client,name=RequestsSize -mg -f Value`. If sjk is unavailable, use jconsole or jmxterm.
- **Disk:** `du -sb $N/data $N/commitlog $N/hints`.
- **Drops:** `bin/nodetool tpstats` dropped `MUTATION` count, and the stress log.
- **Not directly observable:** the bytes held by the queue specifically. It is inferred as heap-used(R0) − baseline, and cross-checked against Pending × ~65 KiB.

**B3e. Procedure.**
1. Start the node with `concurrent_writes: 32` (B3a), record 3 baseline samples, and keep the loader idle.
2. **R0:**
   - Start stress, unthrottled.
   - At t = 10 s run `bin/nodetool setconcurrency MutationStage 0`, and check `bin/nodetool getconcurrency MutationStage` reports 0.
   - Sample until t = 130 s, then run `bin/nodetool setconcurrency MutationStage 32`.
   - Keep sampling until Pending = 0, then 60 s more.
   - Stop stress if it is still running.
3. **R32:** run stress with the throttle and sample throughout.
4. **R2 and R128:** for each value, run `bin/nodetool stopdaemon` (or `kill $PID`, waiting until `pgrep -f CassandraDaemon` is empty), set `concurrent_writes`, restart, and repeat step 3.
5. **PC:** restart with `per_ip: 4MiB` and `concurrent_writes: 32`, then run R32's workload unthrottled for 60 s.
6. **Cleanup:**
   - Stop the node and run `pgrep -f 'CassandraDaemon|cassandra-stress'`. It must print nothing.
   - `rm -rf $N`.

**B3f. Predictions (before any run).**
- **R0** (pool size 0):
  - `MutationStage` Active = 0, and Pending rises roughly linearly to ≈ 7700 (±30%) by t = 130 s.
  - Heap used after GC rises by ≈ Pending × 65 KiB ≈ 480 MiB (±30%) above baseline.
  - RequestsSize stays ≤ 8 MiB, which is below the 256 MiB native cap. So heap exceeds every write-related byte cap by more than 400 MiB.
  - After restoring 32, Pending falls to 0 and heap returns to within 50 MiB of baseline, plus the memtable growth from the re-applied mutations.
- **R2, R32 and R128:**
  - Active ≤ N at every sample.
  - Pending is not lower for smaller N; R2 has Pending ≥ R32's.
  - Heap used after GC is not lower for smaller N. It should be within 20% across runs, or higher for R2. A cap would make it lower.
- **PC:** RequestsSize plateaus ≤ 4 MiB, compared with ≈ 8 MiB in the unthrottled R0 / R32 traffic. The client-side throughput drop confirms the cap binds.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| R0: Pending grows and heap grows ≈ Pending × 64 KiB beyond 256 MiB. R2 / R32 / R128 heaps are not ordered as "smaller N gives less heap". PC clamps RequestsSize to ≤ 4 MiB. | Claim confirmed: usage is flat in, or opposite to, the knob, while a byte cap on the same workload binds. |
| Heap after GC rises with N across R2 < R32 < R128, or R0 heap stays flat while Pending grows | Claim refuted: usage follows the knob, or queued mutations do not hold the heap. |
| R0 Pending is capped (stops growing while load continues) or writes are rejected at enqueue | Claim refuted: a queue bound exists that the source reading missed. |
| R0 Pending never grows (setconcurrency did not take effect, or writes bypassed `MutationStage`), or PC does not clamp RequestsSize | Not confirmed: the boundary was not reached or the instrument is insensitive. |
| OOM in R0 | Consistent with the claim (nothing caps the queue), but rerun with 60 s to obtain readings. |

**B3h. Controls.**
- **Baseline samples** before load.
- **R0 drain:** restoring 32 with load stopped attributes the heap to the queue and not to memtables.
- **PC:** shows a binding byte cap moving the in-flight bytes metric.
- **Same stress command** in all runs.
- **`getconcurrency` read back** after each change.
- **Memtable separation:** `nodetool tablestats keyspace1` memtable data size is sampled, so memtable growth is not mistaken for the queue. In R0 it should stay flat until the drain.

**B4. Risks and cleanup.**
- **Unit tier:**
  - About 500 MiB of heap in a 4 GiB test JVM.
  - Files are only in the local clone's `build/`.
  - Check `pgrep -f junit` after the run.
- **Cluster tier:**
  - All data, commit log, hints, caches, logs and heap dumps go under `$N` on local disk. Allow ≥ 20 GiB, with `commitlog_total_space` set to 2 GiB.
  - The throttled runs write about 3 GiB each.
  - R0 can OOM the 2 GiB heap if it is left running beyond 120 s; `HeapDumpOnOutOfMemoryError` writes up to 2 GiB to `$N/logs`. Keep R0 to 120 s, and restore concurrency even if stress fails.
  - Stop the node (`nodetool stopdaemon` or kill the PID), then stop the stress JVM.
  - `pgrep -f 'CassandraDaemon|cassandra-stress'` must be empty. Then `rm -rf $N`, and remove the local clone when done.
- **Shared clone:** never build in or write to `/users/jason92/cassandra-s3`.

**Audit amendments (stage 4 step 0, 2026-10-21).** Made before any run or reading; each leaves B1 and the claim as filed. Where an amendment adds a row, defines a term or changes a step, it says so, and it governs over the text above (the results file §1.1 gives the reason for each).

- **R1 (B3c: stress warm-up).** Add `no-warmup` to the stress command (after `cl=ONE`). A duration-based `write` otherwise runs a 50,000-operation warm-up first, unthrottled (`tools/stress/.../StressAction.java:105-110`): 50,000 × 64 KiB = 3.05 GiB outside the throttle, and in R0 the warm-up would still be running at t = 10 s.
- **R2 (B3e steps 3–5: one fresh lifetime per steady-state run).** R32, R2, R128, PC0 (R3) and PC each start in a fresh node lifetime: on the running node `TRUNCATE keyspace1.standard1` and `nodetool clearsnapshot --all`, then stop it, set the yaml, start, take 3 baseline samples, then the run. R32 no longer follows R0 in R0's lifetime, so R0's drained mutations and memtables do not enter R32's heap. Order: R0 (own lifetime, as step 1–2), R32, R2, R128, PC0, PC.
- **R3 (B3b, B3e step 5, B3f: PC reference arm).** Add **PC0**: the PC workload (unthrottled, 60 s, `concurrent_writes: 32`) with the B3a in-flight limits (256 MiB). B3f's PC comparison ("≈ 8 MiB in unthrottled traffic", "the client-side throughput drop") is read against PC0: PC's peak RequestsSize ≤ 4 MiB while PC0's is above 4 MiB, and PC's stress op rate lower than PC0's.
- **R4 (B3f, B3g: statistics).** "Heap used after GC" of a run = the **mean** of the post-GC samples taken while stress runs (the maximum is also reported). "Pending" of a run = its maximum sample. B3g row 2's "heap rises with N across R2 < R32 < R128" means strictly increasing **and** R128 > 1.2 × R2 (outside B3f's 20 % band); anything else is "not ordered". B3f's "within 20 % across runs" compares max/min of the three means.
- **R5 (B3g: added row).** | R0: Pending and heap grow together (heap ≈ Pending × 64 KiB) but the heap rise stays below 256 MiB | Not confirmed: the in-flight cap was not exceeded (arrival lower than B3c's estimate); R0 may be repeated once with 240 s at pool size 0 |
- **R6 (B2e, B2g: repeat and terms).** B2e step 2 is run **twice** (B2h's GC-noise repeat). B2g gains a row: | the two M = 4000 runs differ by more than 10 % in any claim-arm liveDelta | Not confirmed: heap instrument noise |. "liveDelta grows with N" means liveDelta(128) > 1.10 × min(liveDelta(0), liveDelta(2)) with the N = 128 value the largest; "doubles" from M = 4000 to 8000 means a ratio in [1.8, 2.2] for every N.

**Runbook fixes (stage 4, 2026-10-21, found by the cluster instrument check before run 1; B1 and B2f–B3g unchanged; the cluster tier starts from its beginning with them).** Results file §3 has the evidence.

- **D1 (B3b PC, R3's PC0: the per-IP cap cannot bind as filed).** A CQL connection takes a request's bytes from its own receive queue first (`native_transport_receive_queue_capacity`, 1 MiB per connection, `Config.java:302`) and borrows from the per-IP and global reserves only the excess (`net/AbstractMessageHandler.java:411-436`; the queue test at `:419`, the reserves at `:428-431`). `RequestsSize` reads the global reserve only (`ClientResourceLimits.java:74-76`). Stress opens 8 connections (`connectionsPerHost` default 8, `tools/stress/.../SettingsMode.java:139`), so its 128 × 64 KiB = 8 MiB in flight fits in 8 × 1 MiB of per-connection queues and never reaches a 4 MiB per-IP reserve. The closed `native_transport_max_concurrent_connections` case found the same. **Fix:** PC and PC0 also set `native_transport_receive_queue_capacity: 0B`, so every in-flight byte is charged to the reserves; PC keeps `native_transport_max_request_data_in_flight_per_ip: 4MiB`, PC0 keeps 256 MiB. B3f's PC prediction is read as filed (RequestsSize ≤ 4 MiB in PC, above it in PC0; lower op rate in PC).
- **D2 (B3d/B3h: reading the queue's heap in R0).** R0's first 10 s are unthrottled writes at pool size 32, which fill the memtable before the pool goes to 0. B3h already samples the memtable "so memtable growth is not mistaken for the queue"; the queue's heap is therefore read as (heap after GC − memtable data size) at a sample minus the same at the baseline, and both this and the raw rise over the baseline are reported. The B3f numbers are unchanged.

## C. Sources read

- /proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/playbook-autonomous.md
- /proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/concurrent/SEPExecutor.java
- src/java/org/apache/cassandra/concurrent/SharedExecutorPool.java
- src/java/org/apache/cassandra/concurrent/SEPWorker.java (lines 40-260)
- src/java/org/apache/cassandra/concurrent/Stage.java (lines 40-80, 229-240, 270-280)
- src/java/org/apache/cassandra/concurrent/ExecutorFactory.java (lines 225-260)
- src/java/org/apache/cassandra/config/Config.java (grep: concurrent_*, native_transport_*, internode_application_*, memtable_heap_space, commitlog_total_space)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (lines 560-568, 649-657, 2410-2430, 3127-3134)
- src/java/org/apache/cassandra/service/StorageProxy.java (lines 229, 1490-1570, 1625-1700, 2623-2668, 2708-2733, 2822-2828; grep)
- src/java/org/apache/cassandra/service/StorageService.java (lines 2397-2403)
- src/java/org/apache/cassandra/tools/nodetool/SetConcurrency.java
- src/java/org/apache/cassandra/transport/Dispatcher.java (grep; lines 58, 77, 238-261)
- src/java/org/apache/cassandra/transport/CQLMessageHandler.java (grep)
- src/java/org/apache/cassandra/transport/ClientResourceLimits.java (grep)
- src/java/org/apache/cassandra/transport/CBUtil.java (lines 443-478, 555-565)
- src/java/org/apache/cassandra/cql3/QueryOptions.java (lines 610-640)
- src/java/org/apache/cassandra/net/ResourceLimits.java (grep)
- src/java/org/apache/cassandra/net/Verb.java (line 116)
- src/java/org/apache/cassandra/metrics/ClientMetrics.java (grep)
- src/java/org/apache/cassandra/metrics/ThreadPoolMetrics.java (grep)
- test/unit/org/apache/cassandra/concurrent/SEPExecutorTest.java (lines 1-120)
- conf/cassandra.yaml (lines 700-730, 1020-1080, 1320-1335; grep)
- conf/jvm-server.options, conf/jvm11-server.options (grep)
- build.xml (grep: testsome, maxMemory, stress-build)
- tools/stress/src/org/apache/cassandra/stress/settings/SettingsErrors.java, SettingsRate.java (grep)

## D. Stage-4 feedback

**2026-10-21 — run 1 closed: unit Confirmed, cluster Confirmed — does not cap** (the negative estimate held; no run 2). Results: [`results/concurrent_writes-takeWorkPermit-workPermits--autonomous.md`](../../stage4-runtime-verification/results/concurrent_writes-takeWorkPermit-workPermits--autonomous.md); harness `stage4-runtime-verification/harness/concurrent_writes-takeWorkPermit-workPermits--autonomous/`. Run on `pc07`, which another stage-4 session shared. The node was on 127.0.0.11 with JMX 7211, and the clone was `~/cassandra-sep` (an environment deviation; the design is unchanged). Run 1 used the version after the audit amendments R1–R6 and runbook fixes D1–D2 above (sha256 `12fb743b…`).

- **Unit (B2g row 1).**
  - For N = 0 · 2 · 32 · 128: active = min(N, M), pending = M − N + 1, and line 196 queued the caller-runs task every time.
  - Live heap was 249.8–250.3 MiB at M = 4000 (two reps) and 499.9–500.7 MiB at M = 8000, flat in N (max/min 1.002).
  - The byte-cap control held 15.3–16.0 MiB at 16 MiB and 63.6–64.4 MiB at 64 MiB.
- **Cluster (B3g row 1).**
  - Pool 0 for 120 s: Active 0, Pending 172 → 7296 at 63.7/s, never falling.
  - Queue heap: 887.5 MiB above the baseline, net of the memtable, against a `RequestsSize` of at most 0.07 MiB.
  - Pool 2 / 32 / 128 at 400 writes/s: heap after GC 240.8 / 241.8 / 237.9 MiB.
  - PC (per-IP 4 MiB, receive queue 0B): `RequestsSize` ≤ 3.88 MiB, against 8.01 MiB in PC0.
- **Missed sub-predictions.**
  - B3f's "≈ Pending × 65 KiB ≈ 480 MiB": each queued mutation holds 131.5 KiB, about 2 × its value. A class histogram counts 7296 `Mutation` and 7296 `Mutation$CachedSerialization`. The coordinator's size check (`SingleTableUpdatesCollector.java:112` → `Mutation.validateSize`) caches a serialized copy below `CACHEABLE_MUTATION_SIZE_LIMIT` (`Mutation.java:451-456`). The miss is towards more uncapped heap.
  - PC's throughput drop was 1.4 %.
- **Defects in this file found by stage 4.**
  - Before run 1, applied above: R1 the stress warm-up; R2 R32 in R0's lifetime; R3 no PC reference; R4–R6 undefined statistics and missing rows; D1 the per-IP cap cannot bind with 8 connections × 1 MiB receive queues; D2 the memtable filled in R0's first 10 s.
  - Harness only: the filed stress command's unquoted `FIXED(…)` is a shell syntax error; the test's `PROBE` lines reach the logs one printf argument per line.
- **Trace note (A3 item 2).** Line 196 also returns false when no task is queued (`taskPermits == 0`), whatever `takeTaskPermit` is. So `maybeExecuteImmediately` runs inline only when a task is already queued and a permit is free; on an idle stage it always enqueues. A supplementary unit test confirmed this 5/5. It is not load-bearing for the claim.
- **Not tested.** At 400 writes/s Active never exceeded 1, so the knob did not bind in R2/R32/R128. A per-running-task memory that scales with N (the `concurrent_compactors` pattern, usage = tasks × per-task bytes) is not ruled out by this run. Only `SEPExecutor.java:196` was tested, not the other SEP lines bundled in `predicted-negative.md` §10.
