# SEPExecutor maximumPoolSize (concurrent_writes / concurrent_reads / native_transport_max_threads ...) — verification solution  <!-- file: cases/maximumPoolSize-takeTaskPermit-workPermits--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/concurrent/SEPExecutor.java:165` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code agent (CLI version not exposed to the agent), 2026-10-21 |
| Estimate | `negative` — the check at line 165 compares the work-permit count derived from the executor's `maximumPoolSize` (a thread-concurrency limit set from `concurrent_writes`, `concurrent_reads`, `native_transport_max_threads`, ...); it caps how many tasks *run* at once, while the task queue it guards is an unbounded `ConcurrentLinkedQueue` (`getMaxTasksQueued()` returns `Integer.MAX_VALUE`), so lowering it does not lower heap and can only move work from "running" into "queued". |
| Ground | The operand counts threads/work permits, not bytes or objects; nothing in `SEPExecutor` refuses or bounds enqueued tasks (`addTask` always adds, `SEPExecutor.java:119-145`). Memory held by queued work is bounded elsewhere (internode receive-queue reserves, native-transport in-flight bytes, memtable limits), not by this constraint. |

## A. Constraint trace

**A1. The constraint.**
- Name: the per-executor maximum pool size of a shared-pool executor, `SEPExecutor.maximumPoolSize` (`SEPExecutor.java:50`, initialised `:75`; work permits initialised to it at `:77`). The operand at line 165, `workPermits`, is the top 32 bits of `permits` (`:59`, `:403-406`), i.e. `maximumPoolSize − (workers currently holding a permit)`; it becomes negative only after `setMaximumPoolSize` lowers the size below the number of active workers (`:378-387`).
- Kind: configuration entries (startup) plus runtime-settable integer (JMX / nodetool).
- Where it is first declared (one value per executor created through `SharedExecutorPool.newExecutor`, `SharedExecutorPool.java:141-151`, reached via `ExecutorFactory.java:244-247` from `Stage.multiThreadedLowSignalStage`, `Stage.java:229-234`):
  - `concurrent_reads` → `ReadStage` (`Config.java:179`, default 32; `Stage.java:45`)
  - `concurrent_writes` → `MutationStage` (`Config.java:180`, default 32; `Stage.java:46`) — **the instance used in the cluster tier**
  - `concurrent_counter_writes` → `CounterMutationStage` (`Config.java:181`, 32; `Stage.java:47`)
  - `concurrent_materialized_view_writes` → `ViewMutationStage` (`Config.java:182`, 32; `Stage.java:48`)
  - `RequestResponseStage` = `FBUtilities.getAvailableProcessors()` (`Stage.java:50`, not settable by yaml)
  - `native_transport_max_threads` → `Native-Transport-Requests` (`Config.java:283`, default 128; `transport/Dispatcher.java:58-61`)
  - `native_transport_max_auth_threads` → `Native-Transport-Auth-Requests` (`Config.java:287`, default 4; `Dispatcher.java:77-80`)
- Unit: number of worker threads (work permits). Defaults are literals in `Config.java`; `conf/cassandra.yaml:722-723` sets 32/32 and recommends 16×drives / 8×cores (`conf/cassandra.yaml:711-721`).
- How set: yaml keys above (restart; startup validation requires ≥2 for reads/writes/counter writes, `DatabaseDescriptor.java:560-568`); at runtime via `nodetool setconcurrency <StageName> <max>` (`tools/nodetool/SetConcurrency.java:30-61` → `StorageService.setConcurrency`, `StorageService.java:2397-2403` → `Stage.setMaximumPoolSize`, `Stage.java:275-278` → `SEPExecutor.setMaximumPoolSize`, `SEPExecutor.java:368-396`), or JMX `setMaximumPoolSize` on the executor MBean (`SEPExecutor.java:74,79`). Runtime accepts any value ≥0, including 0 (`SEPExecutor.java:373-376`); no restart needed. The listener writes the new value back to `Config` (`DatabaseDescriptor.java:2406-2427`).

**A2. What it caps.** Concurrency (CPU threads) of one stage — the number of tasks of that executor running simultaneously. The quantity compared: `workPermits` (signed) against 0. Resource class: "other" (threads). It does **not** cap heap, off-heap or disk; the queued tasks (`tasks`, `SEPExecutor.java:68`) are unbounded and `getMaxTasksQueued()` returns `Integer.MAX_VALUE` (`SEPExecutor.java:102-106`). Indirectly, each running thread costs one stack (`-Xss`, `jvm_xss`) and per-task working memory, so the cap bounds *running-task* working memory only, not the queue.

**A3. Mechanism.**
1. Enqueue: `execute/submit` → `addTask` (`SEPExecutor.java:243-288`, `:119-145`) unconditionally `tasks.add(task)` and increments the task-permit count (low 32 bits); there is no rejection and no limit (the comment at `:129-130` about "block after the fact if we breached the queue limit" refers to a queue limit that no longer exists in this version).
2. Scheduling a worker: `maybeSchedule` → `takeWorkPermit(true)` (`:110-117`, `:188-203`) succeeds only if `workPermits > 0` and a task is queued; this is where the pool size bounds concurrency. Spinning workers self-assign through the same `takeWorkPermit` (`SEPWorker.java:244-262`).
3. Worker loop (`SEPWorker.java:134-161`): after each task the worker calls `takeTaskPermit(true)` — the target method.
4. Target, `SEPExecutor.java:165`: `if (workPermits < 0 && checkForWorkPermitOvercommit)`:
   - true (pool was shrunk below current active count): CAS `workPermits+1`, return `RETURNED_WORK_PERMIT` (`:170-171`); the worker leaves the executor without taking another task and without returning a permit again (`SEPWorker.java:150-161`). Effect: active workers converge down to the new maximum, one exit per finished task. Queued tasks are untouched.
   - false: if task permits are 0 return `NONE_AVAILABLE` (`:175-176`), else take a task permit and continue with the next queued task (`:177-178`).
   - `shutdownNow` calls it with `false` to drain the queue (`:310-317`).
5. Overshoot/bypass: `maybeExecuteImmediately` (`:217-240`) runs on the caller's thread when a permit is free, otherwise enqueues (still unbounded). Shrinking is lazy: until running tasks finish, active > maximum (observable as `getActiveTaskCount() = maximumPoolSize − workPermits > maximumPoolSize`, `:347-350`). Setting 0 stops all processing of that stage while the queue keeps accepting.

**A4. Other consumers / the real bounds on the same heap.**
- Internode inbound messages destined for `MutationStage` hold receive capacity until processed: capacity is acquired on arrival (`net/AbstractMessageHandler.java:398-435`) and released only in `ProcessMessage.run`'s `finally` after the stage executes it (`net/InboundMessageHandler.java:410-441`; dispatch to stage at `:398-399`). Limits: `internode_application_receive_queue_capacity` 4MiB per connection, `..._reserve_endpoint_capacity` 128MiB, `..._reserve_global_capacity` 512MiB (`Config.java:256-261`; wired at `MessagingService.java:676-681`). This is what bounds a replica's MutationStage backlog in bytes — used as the positive control.
- Client requests on `Native-Transport-Requests`: `native_transport_max_request_data_in_flight` / `_per_ip` (`Config.java:298`) and `native_transport_receive_queue_capacity` (`DatabaseDescriptor.java:3208-3216`).
- Memtables (`memtable_heap_space`, `memtable_allocation_type`, `Config.java:186-187,524`), outbound queues (`Config.java:249-254`), caches, compaction, thread stacks.

**A5. Evidence beyond the source.**
- Unit tests in tree exercising resizing: `test/unit/org/apache/cassandra/concurrent/SEPExecutorTest.java:156-272` (`changingMaxWorkersMeetsConcurrencyGoalsTest`, `stoppedWorkersProcessTasksWhenConcurrencyIncreases`, `assertMaxTaskConcurrency`) — they test concurrency only, never memory.
- CASSANDRA-15277, "Make it possible to resize concurrent read / write thread pools at runtime" (introduced runtime `setMaximumPoolSize` for SEP and the negative work-permit handling): https://issues.apache.org/jira/browse/CASSANDRA-15277
- CASSANDRA-15066 (internode messaging rewrite, 4.0, introduced the receive-queue capacity/reserve limits): https://issues.apache.org/jira/browse/CASSANDRA-15066
- `conf/cassandra.yaml:711-723` describes concurrent_reads/writes purely as concurrency tuning.

## B. Verification solution

**B1. Claim under test.** Lowering an SEP executor's maximum pool size (the value compared at `SEPExecutor.java:165`; `concurrent_writes`/`MutationStage` in the cluster tier) limits the number of concurrently running tasks but does **not** lower the heap held by that stage: retained heap of queued work is independent of the value (or grows as the value drops), and when the stage is stalled the backlog's heap is set by the internode receive-queue limits, not by the pool size. The claim is refuted if retained heap decreases monotonically with the pool size at equal offered load and equal queued work.

### B2. Unit tier

**B2a. Environment and build.** Runner's local clone `~/cassandra-run1` (tag `cassandra-5.0.9`, `ant build-test` done), JDK 11, Ant. Never touch the shared tree. New test file `~/cassandra-run1/test/unit/org/apache/cassandra/concurrent/SEPMemoryProbeTest.java` (same package so `SEPExecutor` and `SharedExecutorPool` are reachable; `SEPExecutor` is public and `getActiveTaskCount/getPendingTaskCount/setMaximumPoolSize` are public). Run with `ant testsome` and `-Dtest.jvm.args="-Xms2g -Xmx2g -XX:+UseG1GC"` (testsome sets no -Xmx of its own, `build.xml:1382-1392`, `:1192`).

Test source (complete):

```java
package org.apache.cassandra.concurrent;

import java.lang.management.ManagementFactory;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.net.ResourceLimits;

public class SEPMemoryProbeTest
{
    static final int PAYLOAD = 64 * 1024;   // bytes retained per task
    static final int M = 2000;              // tasks per run -> 2000 * 64 KiB = 125 MiB

    @BeforeClass
    public static void init() { DatabaseDescriptor.daemonInitialization(); }

    static long usedAfterGc() throws InterruptedException
    {
        for (int i = 0; i < 3; i++) { System.gc(); Thread.sleep(200); }
        return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    }

    static Runnable task(CountDownLatch gate, AtomicInteger running, AtomicInteger peak)
    {
        final byte[] payload = new byte[PAYLOAD];
        payload[PAYLOAD - 1] = 1;
        return () -> {
            int r = running.incrementAndGet();
            peak.accumulateAndGet(r, Math::max);
            try { gate.await(120, TimeUnit.SECONDS); } catch (InterruptedException e) { }
            if (payload[PAYLOAD - 1] != 1) throw new AssertionError();
            running.decrementAndGet();
        };
    }

    // Phase 1: retained heap vs maximum pool size
    @Test
    public void heapVsPoolSize() throws Exception
    {
        for (int n : new int[]{ 1, 4, 32, 128 })
        {
            SharedExecutorPool pool = new SharedExecutorPool("Probe" + n);
            SEPExecutor exec = (SEPExecutor) pool.newExecutor(n, "internal", "probe" + n);
            CountDownLatch gate = new CountDownLatch(1);
            AtomicInteger running = new AtomicInteger(), peak = new AtomicInteger();
            long base = usedAfterGc();
            for (int i = 0; i < M; i++) exec.execute(task(gate, running, peak));
            Thread.sleep(2000);
            long used = usedAfterGc();
            System.out.printf("PROBE phase=1 max=%d active=%d pending=%d running=%d peak=%d heapDeltaMiB=%.1f%n",
                              n, exec.getActiveTaskCount(), exec.getPendingTaskCount(), running.get(), peak.get(),
                              (used - base) / 1048576.0);
            gate.countDown();
            pool.shutdownAndWait(60, TimeUnit.SECONDS);
        }
    }

    // Phase 2: shrink while all workers are busy -> drives workPermits < 0 (SEPExecutor.java:165)
    @Test
    public void shrinkDrivesNegativeWorkPermits() throws Exception
    {
        SharedExecutorPool pool = new SharedExecutorPool("ProbeShrink");
        SEPExecutor exec = (SEPExecutor) pool.newExecutor(32, "internal", "probeShrink");
        CountDownLatch gate1 = new CountDownLatch(1), gate2 = new CountDownLatch(1);
        AtomicInteger running = new AtomicInteger(), peak = new AtomicInteger();
        long base = usedAfterGc();
        for (int i = 0; i < 32; i++) exec.execute(task(gate1, running, peak));
        Thread.sleep(1000);
        for (int i = 0; i < 200; i++) exec.execute(task(gate2, running, peak));
        Thread.sleep(1000);
        long before = usedAfterGc();
        System.out.printf("PROBE phase=2a max=%d active=%d pending=%d running=%d heapDeltaMiB=%.1f%n",
                          exec.getMaximumPoolSize(), exec.getActiveTaskCount(), exec.getPendingTaskCount(), running.get(), (before - base) / 1048576.0);
        exec.setMaximumPoolSize(4);   // workPermits = 4 - 32 = -28
        System.out.printf("PROBE phase=2b max=%d active=%d pending=%d running=%d%n",
                          exec.getMaximumPoolSize(), exec.getActiveTaskCount(), exec.getPendingTaskCount(), running.get());
        gate1.countDown();            // 32 tasks finish; 28 workers must exit via RETURNED_WORK_PERMIT
        Thread.sleep(2000);
        long after = usedAfterGc();
        System.out.printf("PROBE phase=2c max=%d active=%d pending=%d running=%d heapDeltaMiB=%.1f%n",
                          exec.getMaximumPoolSize(), exec.getActiveTaskCount(), exec.getPendingTaskCount(), running.get(), (after - base) / 1048576.0);
        gate2.countDown();
        pool.shutdownAndWait(60, TimeUnit.SECONDS);
    }

    // Phase 3 (positive control): same tasks admitted through a byte limit that is known to bind
    @Test
    public void positiveControlByteLimit() throws Exception
    {
        for (long limitMiB : new long[]{ 16, 64 })
        {
            SharedExecutorPool pool = new SharedExecutorPool("ProbeCtl" + limitMiB);
            SEPExecutor exec = (SEPExecutor) pool.newExecutor(4, "internal", "probeCtl" + limitMiB);
            ResourceLimits.Concurrent limit = new ResourceLimits.Concurrent(limitMiB << 20);
            CountDownLatch gate = new CountDownLatch(1);
            AtomicInteger running = new AtomicInteger(), peak = new AtomicInteger();
            int accepted = 0;
            long base = usedAfterGc();
            for (int i = 0; i < M; i++)
                if (limit.tryAllocate(PAYLOAD)) { exec.execute(task(gate, running, peak)); accepted++; }
            Thread.sleep(2000);
            long used = usedAfterGc();
            System.out.printf("PROBE phase=3 limitMiB=%d accepted=%d pending=%d heapDeltaMiB=%.1f%n",
                              limitMiB, accepted, exec.getPendingTaskCount(), (used - base) / 1048576.0);
            gate.countDown();
            pool.shutdownAndWait(60, TimeUnit.SECONDS);
        }
    }
}
```

**B2b. Knobs.** `maximumPoolSize` passed to `newExecutor` ∈ {1, 4, 32, 128} (1 = minimum useful, 4 = small, 32 = `concurrent_writes`/`concurrent_reads` default, 128 = `native_transport_max_threads` default). Runtime shrink 32 → 4 via `setMaximumPoolSize` (the call `nodetool setconcurrency` makes). Control knob: `ResourceLimits.Concurrent` limit ∈ {16, 64} MiB.

**B2c. Workload.** M = 2000 tasks, each retaining a 64 KiB `byte[]` captured by the Runnable and blocking on a latch, so all M are either running (≤ pool size) or queued. Total retained = 2000 × 65536 B = 125 MiB, below a 2 GiB heap, and far beyond every pool size (2000 ≫ 128), so the pool limit is reached and exceeded by ≥15×. Phase 2: 32 blockers saturate pool 32, then 200 queued; shrink to 4. Phase 3: 16 MiB / 64 KiB = 256 accepted; 64 MiB → 1024.

**B2d. Observables and instruments.** Check operands through public accessors: `getActiveTaskCount()` (= `maximumPoolSize − workPermits`, so `active > max` ⇔ `workPermits < 0`), `getPendingTaskCount()` (task permits), `getMaximumPoolSize()`; `running` and `peak` counters inside tasks (true concurrency); heap used after three `System.gc()` via `MemoryMXBean`, delta from a per-run baseline. Sampled once per phase after a 2 s settle. Not directly observable: the raw `permits` long and which branch each worker took at line 165 (inferred from active/running converging to 4).

**B2e. Procedure.**
1. `cd ~/cassandra-run1 && git status --short` (must show only the new test file afterwards).
2. Write the file above to `test/unit/org/apache/cassandra/concurrent/SEPMemoryProbeTest.java`.
3. `ant testsome -Dtest.name=org.apache.cassandra.concurrent.SEPMemoryProbeTest -Dtest.jvm.args="-Xms2g -Xmx2g -XX:+UseG1GC" 2>&1 | tee ~/sep-unit.log`
4. `grep -h PROBE build/test/output/TEST-org.apache.cassandra.concurrent.SEPMemoryProbeTest*.xml ~/sep-unit.log | sort -u`
5. Repeat step 3 twice more (3 runs total); record each PROBE line.
6. Cleanup: `rm test/unit/org/apache/cassandra/concurrent/SEPMemoryProbeTest.java`; `pgrep -f SEPMemoryProbeTest` must be empty.

**B2f. Predictions (before any run).**
- Phase 1, every n: `active = n` (`= min(n, M)`), `running = peak = n`, `pending = M − n` (1999, 1996, 1968, 1872); `heapDeltaMiB` ≈ 125 (within 110–145, payload + small per-task overhead) and the same across n within ±10 MiB. No monotonic decrease of heap with smaller n.
- Phase 2a: max 32, active 32, pending 200, running 32, heapDelta ≈ 232 × 64 KiB ≈ 14.5 MiB (13–20).
- Phase 2b: max 4, **active 32** (> max, i.e. workPermits = −28), pending 200.
- Phase 2c: active 4, running 4, pending 196, heapDelta ≈ 200 × 64 KiB ≈ 12.5 MiB (11–18): concurrency followed the new limit; retained heap of queued work did not change beyond the 32 finished tasks.
- Phase 3 (control): limit 16 MiB → accepted 256, heapDelta ≈ 16 MiB (14–22); 64 MiB → accepted 1024, heapDelta ≈ 64 MiB (58–75).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Phase 1 heapDelta ≈ 125 MiB for all n, pending = M − n | Claim confirmed at unit level: pool size bounds running tasks, not retained heap. |
| Phase 1 heapDelta falls roughly ∝ n (e.g. ≈ n × 64 KiB) with tasks rejected/blocked at the producer | Claim refuted: the pool size caps queued memory (usage follows the constraint). |
| Phase 2b active = 32 > max = 4, then 2c active = running = 4 | Line 165 branch exercised and working as traced (lazy shrink). |
| Phase 2c running stays 32 or active never drops to 4 | Mechanism not as traced (line 165 not taking effect); report, claim about memory unaffected. |
| Phase 3 heapDelta tracks 16/64 MiB while Phase 1 stays flat at ≈125 MiB | Negative confirmed against a moving positive control. |
| Phase 3 heapDelta does not track the limit, or Phase 1 never queues (pending ≈ 0) | Instrument or workload invalid — not confirmed; fix and rerun. |

**B2h. Controls.** Phase 3 is the positive control (same task shape, a byte limit known to bind). Baseline heap per run removes JVM/classloading drift; three GCs reduce floating garbage; three repetitions give spread. `running/peak` counters cross-check `getActiveTaskCount` independently of the permit encoding. Fresh `SharedExecutorPool` per run prevents worker reuse across runs.

### B3. Cluster tier

**B3a. Environment and build.** One Linux host (40 cores, 251 GiB), two Cassandra nodes on loopback aliases: A = 127.0.0.1 (coordinator, JMX 7199), B = 127.0.0.2 (replica under test, JMX 7299). Both run from the built `~/cassandra-run1` (CASSANDRA_HOME) with separate config dirs. Pick a **local** filesystem with ≥60 GiB free (`df -hT $RUN` must show ext4/xfs, not nfs); below `RUN=/tmp/sep-run` is used—change if /tmp is not local.

```bash
export CH=~/cassandra-run1 RUN=/tmp/sep-run
mkdir -p $RUN/{A,B}/{data,commitlog,hints,saved_caches,cdc_raw,logs}
for N in A B; do cp -r $CH/conf $RUN/$N/conf; done
for N in A B; do IP=$([ $N = A ] && echo 127.0.0.1 || echo 127.0.0.2); Y=$RUN/$N/conf/cassandra.yaml
  sed -i "s/^listen_address:.*/listen_address: $IP/; s/^rpc_address:.*/rpc_address: $IP/; s/- seeds: .*/- seeds: \"127.0.0.1:7000\"/" $Y
  sed -i "s/^hinted_handoff_enabled:.*/hinted_handoff_enabled: false/; s/^auto_snapshot:.*/auto_snapshot: false/" $Y
  cat >> $Y <<EOF
data_file_directories: [$RUN/$N/data]
commitlog_directory: $RUN/$N/commitlog
hints_directory: $RUN/$N/hints
saved_caches_directory: $RUN/$N/saved_caches
cdc_raw_directory: $RUN/$N/cdc_raw
memtable_heap_space: 256MiB
EOF
done
sed -i 's/^JMX_PORT="7199"/JMX_PORT="7299"/' $RUN/B/conf/cassandra-env.sh
```
(Check with `grep -c '^data_file_directories' $RUN/*/conf/cassandra.yaml` that each key appears once; the stock file has them commented out, `conf/cassandra.yaml:395,408,97,611,431`.) Heap: `MAX_HEAP_SIZE=8G` (G1 is the default, `conf/jvm11-server.options:63`, so HEAP_NEWSIZE is not needed). If `tools/bin/cassandra-stress` fails with ClassNotFound, run `cd $CH && ant stress-build`.

Start (from a shell where `cd $CH`):
```bash
CASSANDRA_CONF=$RUN/A/conf CASSANDRA_LOG_DIR=$RUN/A/logs MAX_HEAP_SIZE=8G bin/cassandra -p $RUN/A/pid
# wait until `bin/nodetool -p 7199 status` shows UN 127.0.0.1
CASSANDRA_CONF=$RUN/B/conf CASSANDRA_LOG_DIR=$RUN/B/logs MAX_HEAP_SIZE=8G bin/cassandra -p $RUN/B/pid
# wait until both UN in `bin/nodetool -p 7199 status`
```

**B3b. Knobs.**
- Primary (constraint under test), on B only, at runtime: `bin/nodetool -p 7299 setconcurrency MutationStage <v>` with v ∈ {32 (= concurrent_writes default), 8, 1, 0}. 0 is accepted at runtime (`SEPExecutor.java:373`) and stops MutationStage processing entirely — the strongest possible use of the constraint. Shrinking under load also passes through line 165 when active > v.
- Positive control (a cap known to bind on the same backlog), on B, yaml, restart B: `internode_application_receive_queue_reserve_endpoint_capacity` ∈ {16MiB, 128MiB (default), 512MiB}, with `internode_application_receive_queue_reserve_global_capacity: 1GiB` for the 512MiB run; `internode_application_receive_queue_capacity` left at 4MiB. Each control run uses MutationStage = 0.

**B3c. Workload.** cassandra-stress against A only, RF = 2 so every write is also shipped to B as `MUTATION_REQ` (stage MUTATION, `net/Verb.java:116`), CL=ONE so the client only waits on A:
```bash
tools/bin/cassandra-stress write duration=120s cl=ONE \
  -schema "replication(factor=2)" -col "n=FIXED(5)" "size=FIXED(200)" \
  -rate threads=64 fixed=20000/s -node whitelist 127.0.0.1 -port jmx=7199 \
  -log file=$RUN/stress-<phase>.log
```
Each mutation ≈ 5 × 200 B values + key/overhead ≈ 1.1 KiB serialized (small-message connection, < 64 KiB, `OutboundConnections.java:215`). Offered to B: 20 000/s × 1.1 KiB ≈ 22 MB/s. With B stalled, the default receive bound (4 MiB + 128 MiB = 132 MiB) fills in ≈ 6 s, the 16 MiB variant in ≈ 1 s, the 512 MiB variant in ≈ 24 s — all well inside 120 s. Disk: 120 s × 20 000 × ~1.1 KiB ≈ 2.6 GB of data per phase per node that applies it; ≈7 phases → < 40 GB on the run disk. Duration: 120 s load per phase, sample at t = 90 s.

**B3d. Observables and instruments.** On B (pid `$(cat $RUN/B/pid)`):
- MutationStage Active/Pending/Completed/Dropped: `bin/nodetool -p 7299 tpstats | grep -E 'MutationStage|MUTATION_REQ'` every 5 s (`while sleep 5; do date +%s; bin/nodetool -p 7299 tpstats | grep -E 'MutationStage|MUTATION_REQ'; done > $RUN/tp-<phase>.log &`).
- Actual heap: at t = 90 s, `bin/nodetool -p 7299 flush keyspace1` (empties memtables so they do not confound), then `jmap -histo:live <pidB> > $RUN/histo-<phase>.txt` (forces full GC; record the `Total` bytes and instance counts of `org.apache.cassandra.db.Mutation`, `org.apache.cassandra.db.partitions.PartitionUpdate`, `org.apache.cassandra.net.Message`), then `jcmd <pidB> GC.heap_info` (used after GC). Baseline: same two commands after startup + schema, before any load (`histo-baseline.txt`).
- On A, same histogram once per phase (to see outbound backlog), and stress throughput from its log.
- Not directly observable: per-task heap cost (inferred as ΔlivHeap / pending); bytes held in B's inbound reserve (no nodetool counter; inferred from pending × message size).

**B3e. Procedure.**
1. Start A and B (B3a). `cqlsh 127.0.0.1` is not needed; stress creates `keyspace1.standard1` with RF 2. Do one 20 s warm-up stress run, then `bin/nodetool -p 7199 flush; bin/nodetool -p 7299 flush`, take B baseline histogram.
2. For v in 32, 8, 1, 0 (in that order):
   a. `bin/nodetool -p 7299 setconcurrency MutationStage $v`; verify with `bin/nodetool -p 7299 getconcurrency MutationStage`.
   b. Start the tpstats sampler, start stress (B3c) in background; at t = 90 s run flush + `jmap -histo:live` + `GC.heap_info` on B and histogram on A; wait for stress to end; stop sampler.
   c. `bin/nodetool -p 7299 setconcurrency MutationStage 32`; wait until B MutationStage Pending = 0 (expired messages are discarded on processing, `InboundMessageHandler.java:419-423`); take a post-drain histogram on B.
   d. `cqlsh 127.0.0.1 -e "TRUNCATE keyspace1.standard1"` (only after step c — TRUNCATE needs B's stages), `bin/nodetool -p 7199 clearsnapshot --all; bin/nodetool -p 7299 clearsnapshot --all`, check `du -sh $RUN/*/data`.
3. Positive control: for R in 16MiB, 128MiB, 512MiB: stop B (`kill $(cat $RUN/B/pid)`, wait for exit), set in `$RUN/B/conf/cassandra.yaml` `internode_application_receive_queue_reserve_endpoint_capacity: $R` (and `internode_application_receive_queue_reserve_global_capacity: 1GiB` for 512MiB), restart B, wait UN, take a baseline histogram, then repeat step 2 with v = 0 only.
4. Stop both nodes (B4), collect logs and files.

**B3f. Predictions (before any run).** Let H(v) = B's live heap after flush + full GC at t = 90 s minus baseline, P(v) = MutationStage Pending at t = 90 s.
- v = 32, 8: B keeps up; P ≤ 1 000, H < 100 MiB, Mutation instance count ≤ ~1 000.
- v = 1: one thread may or may not keep up with 20 000/s; either P stays small (H < 100 MiB) or a backlog forms up to the receive bound (H as for v = 0). In no case is H(1) < H(32) by more than noise (±50 MiB).
- v = 0 (default reserves): Active 0; P rises in the first ~6–10 s and plateaus at ≈ 132 MiB / 1.1 KiB ≈ 120 000 (range 90 000–150 000) and stays flat; H ≈ 1–4 × 132 MiB, i.e. 130–550 MiB; Mutation instances ≈ P. A drops/expires further mutations to B (A's outbound backlog ≤ 132 MiB more on A). Heap is therefore larger at v = 0 than at v = 32 — the opposite of a cap.
- Positive control (v = 0): plateau P and H scale with the endpoint reserve: 16MiB → P ≈ 18 000 (≈ 20 MiB / 1.1 KiB), H ≈ 20–80 MiB; 128MiB → as above; 512MiB → P ≈ 480 000, H ≈ 0.5–2 GiB. Ratio H(512)/H(16) ≥ 8.
- Claim wrong if: H decreases monotonically as v goes 32 → 8 → 1 → 0 at equal offered load, or the v = 0 plateau does not depend on the receive reserve but on v.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| H(32) ≈ H(8) small; H(0) ≫ H(32); v = 0 plateau P ≈ reserve/size and H scales with the reserve (control moves) | Claim confirmed: usage does not follow the pool size; it is governed by the receive-queue limits. |
| H(v) decreases with v (smaller pool → less heap) at equal load, with comparable P | Claim refuted: the pool size caps heap. |
| H flat across v **and** flat across the control's reserve values (control did not move) | Not confirmed: workload never built a backlog or instrument insensitive; raise rate / check B received traffic (Completed count on B rising at v = 32). |
| At v = 0, P grows without plateau until B OOMs or until expiry | Unbounded backlog: also confirms the pool size does not cap memory, but contradicts the receive-reserve model in A4 — report. |
| Active on B > v briefly after shrinking, then ≤ v | Line 165 lazy shrink observed in a real node (mechanism check, not a memory result). |

**B3h. Controls.** Positive control via receive reserve (same workload, a byte cap known to bind). Fixed offered rate (`fixed=20000/s`) so phases see equal load. Flush before each heap sample removes memtables (bounded anyway by `memtable_heap_space: 256MiB`); hints disabled so A's disk/heap is not confounded by hint writing; `auto_snapshot: false` so truncation does not keep data. Baseline histogram per B restart. Repeat the v = 32 and v = 0 phases once more at the end to check drift.

**B4. Risks and cleanup.**
- Unit tier: only one added test file in `~/cassandra-run1`; remove it afterwards; build output stays in that clone. 2 GiB test heap.
- Cluster tier: all data, commit logs, hints, logs under `$RUN` on local disk; budget < 40 GB; check `df -h $RUN` before each phase and abort if < 20 GiB free. Never use the shared source clone or shared storage for node data. Heap 8 GiB per node (16 GiB of 251).
- Stop: `kill $(cat $RUN/B/pid) $(cat $RUN/A/pid)`; wait; then `pgrep -af CassandraDaemon` and `pgrep -af cassandra-stress` must print nothing for this user (kill -9 any leftover). Stop background `tpstats` loops (`jobs`, `kill %1`).
- Remove `$RUN` (`rm -rf /tmp/sep-run`) after results are copied. Loopback 127.0.0.2 needs no system change on Linux.

**Audit amendments (stage 4 step 0, 2026-10-21).** Made before any run or reading; B1 is unchanged. Each amendment governs over the text above where they differ. The results file §1.1 gives the reasons. Source citations are against `cassandra-5.0.9` (`b5f2a54210`).

- **R1 (B3c: stress warm-up).** Every stress command gets `no-warmup` after `cl=ONE`. A `duration=` write otherwise first runs 50,000 unthrottled operations (`tools/stress/.../StressAction.java:105-110`), outside `fixed=`. That would put an unthrottled burst into each phase, and at v = 0 it would fill B's reserve before the fixed rate starts.
- **R2 (B2g, B3f, B3g: statistics and terms).**
  - Unit: "the same across n within ±10 MiB" (B2f) is the test for "flat". "Falls roughly ∝ n" (B2g row 2) means heapDelta(1) < heapDelta(128) − 20 MiB.
  - Added B2g row: | the three repetitions differ by more than 10 MiB in any Phase 1 heapDelta | Not confirmed: heap instrument noise |
  - Cluster: H(v) is B's "used" from `GC.heap_info` taken right after `jmap -histo:live` (which runs a full GC), minus the same at the baseline of that node lifetime. P(v) is the tpstats sample nearest t = 90 s. "Noise" is ±50 MiB, as in B3f. In B3g row 1, "H(32) ≈ H(8) small" means both are < 100 MiB, and "H(0) ≫ H(32)" means H(0) − H(32) ≥ 100 MiB. "H scales with the reserve" means H(16 MiB) < H(128 MiB) < H(512 MiB) and H(512)/H(16) ≥ 8. "Decreases with v" (B3g row 2) means H(0) < H(1) < H(8) < H(32) with H(32) − H(0) > 50 MiB.
- **R3 (B3e: the drift repeat).** B3h's "repeat the v = 32 and v = 0 phases once more at the end" runs in a fresh lifetime of B with the default reserve (128 MiB), after the control runs. Its readings must lie within 50 MiB (H) and 25 % (P at v = 0) of the first ones. Added B3g row: | the repeat differs by more than that | Not confirmed: drift |
- **R4 (B2: Phase 4, an instrument check for "running tasks × per-task bytes").** Phase 1 builds each task with its 64 KiB payload already allocated, so queued and running tasks hold the same bytes. It cannot show a component that only *running* tasks hold. That pattern refuted `concurrent_compactors`. One test method is added to B2a's class, `workingMemoryPerRunningTask`. Its tasks capture nothing. A task allocates and touches W = 1 MiB only when it starts running, then waits on the gate. M = 2000, n ∈ {1, 4, 32, 128}, the same heap instrument, and one line per n: `PROBE phase=4 max=n active=… pending=… running=… peak=… heapDeltaMiB=…`. **Prediction:** active = running = n, pending = 2000 − n, heapDelta = n × 1 MiB + at most 2 MiB (1–3 · 4–6 · 32–35 · 128–135 MiB, within 10 % at 128). Phase 4 is **not** a test of B1: its tasks are built to allocate only while running. It is the positive control for the bind arm (R5). It shows that the instrument resolves a per-running-task component and that the pool size bounds that component exactly. Added B2g row: | Phase 4 heapDelta does not follow n × 1 MiB | Invalid for R5's purpose: the instrument cannot see per-running-task memory; the unit verdict rests on Phases 1–3 only |
- **R5 (B3: the bind arm. The pool must bind under load, with each task holding known bytes).** In B3 as filed, v = 32 and 8 never bind at 20,000 × 1.1 KiB writes/s, because B keeps up. Only v = 0 (and perhaps 1) reaches the limit, so "usage = running tasks × per-task bytes" is untested. **Added phases**, after R3, with the same two nodes, workload shape and instruments:
  - **Configuration** (both nodes restarted once for the arm):
    - B: `commitlog_sync: group`, `commitlog_sync_group_window: 5000ms`, and `commitlog_sync_period` removed (`DatabaseDescriptor.java:511-521`). Every MutationStage task then waits in `CommitLog.add` → `finishWriteFor` → `GroupCommitLogService.maybeWaitForSync` (`CommitLog.java:300-338`, `GroupCommitLogService.java:34-41`) for the next sync, about 2.5 s on average. So each task runs for seconds, and B applies only about 2v/5 s⁻¹ writes. That is below the offered rate at every v ≤ 128, so Active = v binds.
    - A and B: `write_request_timeout: 300000ms`. Messages then do not expire during a phase (`InboundMessageHandler.java:413-424`), and the backlog stays bounded by B's receive reserve (4 MiB + 128 MiB) at every v. That is the "equal queued work" of B1.
  - **Two message sizes, through the two inbound paths** (`InboundMessageHandler.java:148-151`; threshold 64 KiB minus the frame header, `OutboundConnections.java:69`):
    - **S**, small: `-col 'n=FIXED(1)' 'size=FIXED(32768)'` at `fixed=400/s`. Deserialized on arrival, on heap, before queueing (`:157-195`). Deserialization also caches the serialized bytes (`Mutation.java:487-520`, limit 1,000,000 B), so each queued mutation holds about 2 × its size.
    - **L**, large: `size=FIXED(262144)` at `fixed=100/s`. Kept as received frames in networking-pool direct buffers until a worker runs the task. The worker then deserializes it on the heap (`:315-385`, `:481-509`; again with the cached serialization).
  - **Procedure, per (size, v), v ∈ {1, 8, 32, 128} (32 = default), order S1 S8 S32 S128 L1 L8 L32 L128:**
    - B in a fresh lifetime, with A up throughout the arm.
    - `nodetool setconcurrency MutationStage v` on B, read back with `getconcurrency`.
    - Flush, then the baseline: `jmap -histo:live`, `GC.heap_info`, JMX direct `MemoryUsed`, networking `BufferPool` `UsedSize`/`OverflowSize`, `system_views.internode_inbound`.
    - Stress against A for 90 s: `tools/bin/cassandra-stress write duration=90s cl=ONE no-warmup -schema "replication(factor=2)" -col … -rate threads=64 fixed=…/s -node <A>`.
    - tpstats on B every 5 s. At t = 60 s, the same sample set as the baseline.
    - After stress: `setconcurrency MutationStage 512`, wait until Pending = 0 at three samples in a row, `TRUNCATE`, `clearsnapshot`, stop B.
  - **Prediction (stated from the trace above, before any run):**
    - (a) Every phase binds: Active ≥ 0.9 v at ≥ 80 % of the tpstats samples in t = 20–60 s, and Pending is at a plateau by t = 30 s.
    - (b) Reserve usage `using_bytes + using_reserve_bytes` from A at t = 60 s is 100–140 MiB at every phase. Pending at t = 60 s is ≈ 132 MiB / message size − v: S ≈ 4,200 − v (3,000–5,500), L ≈ 528 − v (± 25 %).
    - (c) **S:** H_S(v) ≈ 2 × 132 MiB ≈ 264 MiB (185–345) and flat in v: max/min of the four ≤ 1.2.
    - (d) **L:** H_L(v) ≈ v × 2 × 256 KiB = 0.5, 4, 16, 64 MiB. It is increasing over v = 8 < 32 < 128, with H_L(128) − H_L(1) ≥ 40 MiB. The networking pool's used + overflow bytes are ≈ Pending × 256 KiB, larger at v = 1 than at v = 128.
  - **Rows (B3g, added):**
    - | **BIND-1:** (a) holds; H_S and H_L both flat (max/min ≤ 1.2, or every H within 30 MiB of the others) | Confirmed for the binding pool: running tasks × per-task bytes ruled out at this resolution; with the filed row 1, the cluster tier is Confirmed — does not cap |
    - | **BIND-2:** (a) holds; H_S flat; H_L increasing over 8 < 32 < 128 with H_L(128) − H_L(1) ≥ 40 MiB | **Refuted on the large-message path** (B1's refuted-if holds there: heap falls with the pool size at equal, reserve-bound queued work). Usage = running tasks × per-task bytes for large internode mutations; queued small mutations are not capped. Effect: caps only on some paths |
    - | **BIND-3:** (a) holds; H_S also increases with v (H_S(128) − H_S(1) ≥ 40 MiB and monotone) | Refuted: the pool size caps heap on both paths. Effect: caps |
    - | **BIND-4:** (a) fails (Active < 0.9 v at more than 20 % of the samples), or Pending shows no plateau | Not confirmed: the pool did not bind; the filed rows decide the tier, with "running × per-task bytes" recorded as untested |
    - | **BIND-5:** any other pattern (e.g. L flat but S rising, non-monotone L with a large range) | Not confirmed: report |
  - **Combining.** The cluster verdict is the filed B3g row if R5 matches BIND-1 or BIND-4. It is R5's row if R5 matches BIND-2, BIND-3 or BIND-5, because R5 tests B1 under the binding condition that the filed phases lack. **Positive control for R5:** the filed reserve control (B3b; same instruments; the reserve moves H) and Phase 4 (R4). **Budget:** S writes ≈ 1.2 GB per phase on A and L ≈ 2.4 GB; each phase is truncated; B uses 8 GiB of heap. TRUNCATE runs on `MutationStage` (`Verb.java:134`), so B must be drained (v = 512) before it.

**Runbook fixes (stage 4 run 1, 2026-10-21; B1 and B2f–B3g unchanged; the affected tier restarts from its beginning).** Results file §3 has the evidence.

- **D1 (B2e step 3: the test JVM does not start).** `-XX:+UseG1GC` in `test.jvm.args` clashes with the testsome JVM's own `-XX:+UseConcMarkSweepGC` (`build.xml` test macro), so the JVM exits with "Multiple garbage collectors selected" before any test. **Fix:** `-Dtest.jvm.args="-Xms2g -Xmx2g -XX:-UseConcMarkSweepGC -XX:+UseG1GC"`. This keeps G1 as B2a intended. The unit tier restarts. **Second attempt, same step (2026-10-21):** the macro's `maxmemory="1024m"` (`build.xml:1153`) is placed after `test.jvm.args`, so `-Xmx1024m` wins and `-Xms2g` stops the JVM ("Initial heap size set to a larger value than the maximum heap size"). B2a's premise that "testsome sets no -Xmx of its own" is wrong. **Fix:** `-Dtest.jvm.args="-XX:-UseConcMarkSweepGC -XX:+UseG1GC"`, so the test heap is ant's 1 GiB. The largest phase holds about 125 MiB (Phase 1) or 128 MiB (Phase 4), well inside 1 GiB, so B2f's MiB predictions are unaffected. Phase 4 logs the JVM's max heap. The unit tier restarts again.
- **D2 (R5: group commit cannot make the pool bind; found in cluster attempt 1 and two bind-arm instrument checks, before any R5 reading).**
  - (i) At the start of R5, B restarted under `commitlog_sync: group` and hung in `SystemKeyspaceMigrator41.migrate` (`CassandraDaemon.java:275`). The main thread was parked in `GroupCommitLogService.maybeWaitForSync` (`:39`) and never signalled, so B never reached UN. Cluster attempt 1 stopped here, and its filed-phase readings are not counted.
  - (ii) On a freshly wiped pair, group commit slowed B's Gossip and Migration stages by minutes. B had no `keyspace1` schema when S started, so every small mutation was dropped as "incompatible schema" (`InboundMessageHandler.java:171-175`).
  - (iii) Group-commit waits were far shorter than the 5 s window: B completed about 40 writes/s at v = 8. At v ≥ 32 the pool would not bind at 100/s or 400/s, so R5 could not be executed as written.
  - **Fix:** R5 keeps the periodic commit log, and B (only in R5) runs a Byteman rule (`harness/…/hold-mutation.btm`; agent through `JVM_EXTRA_OPTS` on B's start command, no listener). The rule sleeps 2 s at the entry of `MutationVerbHandler.doVerb`. The message is deserialized before that call (`InboundMessageHandler.java:427-429`), so each running task holds its deserialized mutation for 2 s. B then applies at most v/2 writes/s (≤ 64/s at v = 128), and the pool binds at every v against 400/s (S) and 100/s (L).
  - `write_request_timeout: 300000ms` on A and B, the sizes, the rates, the order, B in a fresh lifetime per phase, the samples, the predictions (a)–(d) and rows BIND-1 to BIND-5 are unchanged.
  - **Instrument definition:** R5(b)'s "using_bytes + using_reserve_bytes" double-counts. `using_bytes` is the handlers' `queueSize`, which already includes the part borrowed from the reserves (`InboundMessageHandlers.java:321-329`). R5(b) reads `using_bytes` alone, with the band unchanged.
  - The cluster tier restarts from its beginning.

## C. Sources read

- src/java/org/apache/cassandra/concurrent/SEPExecutor.java
- src/java/org/apache/cassandra/concurrent/SEPWorker.java
- src/java/org/apache/cassandra/concurrent/SharedExecutorPool.java
- src/java/org/apache/cassandra/concurrent/Stage.java
- src/java/org/apache/cassandra/concurrent/ExecutorFactory.java
- src/java/org/apache/cassandra/transport/Dispatcher.java
- src/java/org/apache/cassandra/config/Config.java
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java
- src/java/org/apache/cassandra/service/StorageService.java
- src/java/org/apache/cassandra/tools/nodetool/SetConcurrency.java
- src/java/org/apache/cassandra/net/InboundMessageHandler.java
- src/java/org/apache/cassandra/net/AbstractMessageHandler.java
- src/java/org/apache/cassandra/net/ResourceLimits.java
- src/java/org/apache/cassandra/net/MessagingService.java
- src/java/org/apache/cassandra/net/OutboundConnections.java
- src/java/org/apache/cassandra/net/Verb.java
- test/unit/org/apache/cassandra/concurrent/SEPExecutorTest.java
- tools/stress/src/org/apache/cassandra/stress/settings/SettingsNode.java, SettingsSchema.java, SettingsColumn.java
- conf/cassandra.yaml, conf/cassandra-env.sh, conf/jvm11-server.options, bin/cassandra, bin/cassandra.in.sh, build.xml
- https://issues.apache.org/jira/browse/CASSANDRA-15277
- https://issues.apache.org/jira/browse/CASSANDRA-15066

## D. Stage-4 feedback

**2026-10-21: run 1 closed. Unit Confirmed — does not cap; cluster Not confirmed (R5 row BIND-5) — undetermined.** No run 2.
- Results: [`results/maximumPoolSize-takeTaskPermit-workPermits--autonomous.md`](../../stage4-runtime-verification/results/maximumPoolSize-takeTaskPermit-workPermits--autonomous.md). Harness: `stage4-runtime-verification/harness/maximumPoolSize-takeTaskPermit-workPermits--autonomous/`.
- Run on `pc07` with A/B on 127.0.0.21/.22 and JMX 7221/7222, clone `~/cassandra-mps` (an environment deviation).
- Version used: the audit amendments R1–R5 and the runbook fixes D1–D2 above (sha256 `e50549b2…`).

- **Unit (B2g rows 1, 3, 5).**
  - Queued heap was 125.2–125.3 MiB at n = 1 · 4 · 32 · 128 in three repetitions.
  - Line 165 exercised: after `setMaximumPoolSize(4)`, active stayed at 32 (`workPermits` = −28), then converged to 4 running with 196 pending.
  - The byte cap held 16.0 / 64.1 MiB.
  - R4's Phase 4 read 2.0 × n MiB per running task, not the predicted n × 1 MiB. The likely cause is G1 humongous regions at a 1 GiB heap. By R4's row this is "invalid for R5's purpose".
- **Cluster.**
  - v = 0: 134,432 queued mutations, H 374.9 MiB.
  - Control (reserve 16 / 128 / 512 MiB): H 101.2 / 427.7 / 1,515.5 MiB, so the queue is bounded by the receive reserve, not by the pool.
  - H never decreases with v, so the Refuted row is excluded.
  - The filed "H(32), H(8) < 100 MiB" missed (146.3 / 261.4: the write load's own heap), and the R3 repeat drifted (146.3 vs 432.1).
  - **R5:** the pool bound at every v (Active = v, Pending at the reserve, `using_bytes` 132 MiB).
    - Small (32 KiB) mutations: heap flat at 238.8–258.9 MiB.
    - Large (256 KiB) mutations: heap 5.5 · 57.4 · 53.9 · 86.2 MiB by `GC.heap_info`, and 5.5 · 9.4 · 21.9 · 70.2 MiB of live bytes. `Mutation` instances = v exactly. The queue sat in direct frame buffers (+222–240 MiB).
  - The frozen statistic is non-monotone at 8 → 32 by 3.5 MiB, and on live bytes the small arm's max/min is 1.2001. That gives BIND-5, so the tier is Not confirmed.
- **"Running tasks × per-task bytes".** Tested with the pool binding. It holds for large internode mutations: they are deserialized only when a worker runs them (`InboundMessageHandler.java:481-509`), so their heap is ≈ v × 2 × size. Their total memory (heap + direct) stays bounded by the receive reserve. It does not hold for small mutations, whose queue is on heap. So lowering `concurrent_writes` lowers *heap* on the large-message path but not memory, and it never bounds the queue.
- **Defects in this file found by stage 4.**
  - Before run 1, applied above: R1 the stress warm-up; R2 undefined terms and no repeat row; R3 the drift repeat's configuration; R4 and R5, the knob never bound at v ≥ 8 in B3.
  - D1: testsome's JVM arguments (`-XX:+UseG1GC` clashes with CMS; `maxmemory="1024m"` overrides `-Xmx2g`).
  - D2: group commit could not make the pool bind (restart hang in `SystemKeyspaceMigrator41`, schema lag, short waits), so it was replaced by a Byteman 2 s hold.
  - Found in the readings, not fixed:
    - In 5.0 the internode mutation deadline is capped by `native_transport_timeout` (`transport/Dispatcher.java:238-245, 270`), so `write_request_timeout: 300000ms` did not stop expiry. The backlog stayed reserve-bound anyway.
    - B3d's flush-then-sample does not remove the write load's heap at v ≥ 1 under 20,000 writes/s.
- **Recommendations.**
  - Read R5 by histogram live bytes with a stated tolerance.
  - Raise `native_transport_timeout` with `write_request_timeout`.
  - Stop the load before sampling the filed phases.
  - Give `ReadStage` and `Native-Transport-Requests` their own designs (this file runs only `MutationStage`).
