# SEPExecutor maximumPoolSize (native_transport_max_threads, concurrent_reads/writes/counter_writes/materialized_view_writes) — verification solution  <!-- file: cases/sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`SEPExecutor.java:196`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SEPExecutor.java#L196) (primary). The same constraint also covers `SEPExecutor.java:165#1`, `SEPExecutor.java:373#1`, `SEPExecutor.java:384#1` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (claude-opus-5-5), Claude Code at Meta (version string not available), 2026-10-26 |
| Estimate | `undetermined`. The work-permit check caps how many tasks of one stage run at once. Because a new SharedPool thread is created only when no idle worker exists, it also roughly caps the number of SharedPool worker threads, which hold per-thread stack memory and thread-local memory. But the knob exists to limit concurrency, not memory. The task queue behind it is unbounded (`SEPExecutor.java:103-106`, `:123`). Threads are never freed after a shrink. So whether node memory follows the knob by a significant amount is open. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `SEPExecutor.maximumPoolSize`: an `AtomicInteger` field ([`SEPExecutor.java:50`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SEPExecutor.java#L50)), set in the constructor (`:75`), which also sets the initial work permits to that value (`:77`). It is a runtime-queried limit whose unit is a count of concurrently running tasks (worker permits). These configuration entries feed it:
- `concurrent_reads` (ReadStage), `concurrent_writes` (MutationStage), `concurrent_counter_writes` (CounterMutationStage), `concurrent_materialized_view_writes` (ViewMutationStage). Each defaults to 32 ([`Config.java:179-182`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L179-L182), `conf/cassandra.yaml:722-728`). They are wired in [`Stage.java:45-48`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/Stage.java#L45-L48) through `multiThreadedLowSignalStage` → `.shared(...)` ([`Stage.java:228-235`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/Stage.java#L228-L235)) → `SharedExecutorPool.SHARED.newExecutor` ([`ExecutorFactory.java:244-247`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/ExecutorFactory.java#L244-L247)).
- `REQUEST_RESPONSE`: fixed at the available processor count ([`Stage.java:50`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/Stage.java#L50)). It is not settable.
- `native_transport_max_threads` (default 128, [`Config.java:283`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L283)) is used for the `Native-Transport-Requests` executor. `native_transport_max_auth_threads` (default 4, [`Config.java:287`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L287)) is used for `Native-Transport-Auth-Requests`, with `max(1, …)`. Both are in [`Dispatcher.java:58-80`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Dispatcher.java#L58-L80).

How each value can be set:
- yaml, which needs a restart.
- At runtime, `setMaximumPoolSize` ([`SEPExecutor.java:369-396`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SEPExecutor.java#L369-L396)):
  - For the stages: `nodetool setconcurrency <stage> <max>` ([`SetConcurrency.java:41-52`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/tools/nodetool/SetConcurrency.java#L41-L52) → [`StorageService.java:2397-2403`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L2397-L2403)).
  - For the native-transport executors: only through the JMX MBean `org.apache.cassandra.transport:type=Native-Transport-Requests` (`SEPExecutor.java:74,79`; `SEPExecutorMBean extends ResizableThreadPool`). `Stage.fromPoolName` does not know these executors.

`concurrent_reads` must be at least 2 at startup ([`DatabaseDescriptor.java:560-562`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L560-L562)). At runtime only a negative value is rejected ([`SEPExecutor.java:373-376`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SEPExecutor.java#L373-L376), [`DatabaseDescriptor.java:2408-2411`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L2408-L2411)).


**Limit type (2026-10-29).** non-config: runtime-queried. The traced constraint decides ([README §6](../../../stage3-ai-deep-read/README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** The direct quantity is the per-executor count of work permits in use. The code compares the top 32 bits of `permits` (`SEPExecutor.java:57-60`) against 0. Indirectly it caps:
- (i) the number of tasks of that executor running at once, and with them their in-flight working memory on heap;
- (ii) the number of SharedPool worker threads (`SEPWorker` → `FastThreadLocalThread`, `src/java/org/apache/cassandra/concurrent/SEPWorker.java:58`). Each thread costs native memory for its stack (`-Xss256k`, `conf/jvm-server.options:123`) plus thread-local buffers.

It does **not** cap queued tasks. `tasks` is an unbounded `ConcurrentLinkedQueue` (`SEPExecutor.java:68`), `getMaxTasksQueued()` returns `Integer.MAX_VALUE` (`:103-106`), and the blocking behaviour was removed by CASSANDRA-16186 (`CHANGES.txt:1374`). The comment at `:129-130` ("block after the fact if we breached the queue limit") is stale.

**A3. Mechanism.**
1. `addTask` always enqueues and increments task permits ([`SEPExecutor.java:123-133`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SEPExecutor.java#L123-L133)). If the queue was empty it starts a spinning worker (`:135-143` → [`SharedExecutorPool.java:132-139`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SharedExecutorPool.java#L132-L139)).
2. A worker can start work on an executor only through `takeWorkPermit`. `if (workPermits <= 0 || taskPermits == 0) return false;` ([`SEPExecutor.java:196-197`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SEPExecutor.java#L196-L197)) is the cap. On success it decrements the work permits (`:198`). Callers:
   - `maybeSchedule` (`:110-117`);
   - `SEPWorker.selfAssign` ([`SEPWorker.java:250-263`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SEPWorker.java#L250-L263));
   - `maybeExecuteImmediately` ([`SEPExecutor.java:221`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SEPExecutor.java#L221)). If no permit is available, the task is queued instead (`:221-224`).
3. While a worker holds a permit it keeps draining the queue through `takeTaskPermit(true)` ([`SEPWorker.java:150`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SEPWorker.java#L150)). If the pool was shrunk, `workPermits < 0` ([`SEPExecutor.java:165`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SEPExecutor.java#L165)) makes the worker give its permit back and leave (`:170-171`, [`SEPWorker.java:160-161`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SEPWorker.java#L160-L161)). This is how a runtime shrink takes effect.
4. `setMaximumPoolSize` rejects negative values ([`SEPExecutor.java:373`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SEPExecutor.java#L373)), does nothing when the delta is 0 (`:384`), adds the delta to the work permits (`:387`, which may go negative), and starts a spinner (`:393`).
5. Thread creation: `SharedExecutorPool.schedule` reuses a worker from the `spinning` or `descheduled` maps and creates a new `SEPWorker` only when both maps are empty ([`SharedExecutorPool.java:107-116`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SharedExecutorPool.java#L107-L116)). Every working thread holds a permit, so the live thread count is about Σ maximumPoolSize over SharedPool executors, plus a few spinners.

Overshoot and bypass paths:
- (a) A worker that is between states is in neither map: it has finished its task and returned its permit, but is not yet spinning ([`SEPWorker.java:157-174`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SEPWorker.java#L157-L174)), or its `putIfAbsent` clashed (`:302-303`). In that window `schedule` can create an extra thread.
- (b) Threads are never terminated. A descheduled worker parks ([`SEPWorker.java:116-118`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SEPWorker.java#L116-L118)) and stays alive in `pool.descheduled` (`:228-230`). The run loop only returns on pool shutdown (`:102-103`). So after a shrink, or after load drops, the thread count stays at its high-water mark. This contradicts the yaml comment that "idle threads are stopped after 30 seconds" (`conf/cassandra.yaml:1033-1034`).
- (c) Queued tasks are unbounded (A2).

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — A3, derived from the source for the runs.**
- (i) **One count(\*) holds one NTR permit for its whole run.** `Dispatcher.dispatch` submits every non-auth request to the `Native-Transport-Requests` executor ([`Dispatcher.java:123-125`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Dispatcher.java#L123-L125)). The query runs on that worker. Each page of a local range read is queued on ReadStage (`Stage.READ.execute`, [`RangeCommandIterator.java:205-208`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/reads/range/RangeCommandIterator.java#L205-L208)), and the NTR worker blocks until the page returns. So a running count(\*) holds one NTR permit plus, while a page is read, one ReadStage task.
- (ii) **The filed timeouts would shed the load.** `native_transport_timeout` is 12 s by default ([`Config.java:1399`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L1399)). A request that waited longer in the NTR queue is answered with `OverloadedException` when it is dequeued ([`Dispatcher.java:364-368`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Dispatcher.java#L364-L368)). Every read's deadline is min(start + verb timeout, enqueue + `native_transport_timeout`) ([`Dispatcher.java:238-245`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Dispatcher.java#L238-L245)), with `cql_start_time: REQUEST` ([`Config.java:1391`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L1391)). Raising only the read and range timeouts (filed B3a) leaves the 12 s client deadline. With 400 requests outstanding, most would time out and be re-fired. B3a therefore also raises `native_transport_timeout`.
- (iii) **The worker-thread count W never falls within one JVM.** A worker's run loop returns only on pool shutdown or after a `Throwable` ([`SEPWorker.java:102-103`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SEPWorker.java#L102-L103), `:177-206`). A descheduled worker parks (`:116-118`). So W after a phase is the high-water mark of every earlier phase in that JVM. A control with low demand must run **before** the high-demand load on a fresh JVM, or it reads the earlier high-water mark (B3e amendment).
- (iv) **Threads are reused before new ones are made.** `schedule` hands work to a spinning worker, then to a descheduled one, and creates a thread only when both maps are empty ([`SharedExecutorPool.java:107-116`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SharedExecutorPool.java#L107-L116)). Hence W_max = max(W before the phase, the peak number of workers needed at once). At C = 400 that need is: NTR running (≤ knob) + ReadStage running (≤ 32) + other SharedPool stages (idle here) + spinners.
- (v) **NTR `Active` is the permit counter itself.** `getActiveTaskCount()` = `maximumPoolSize − workPermits` ([`SEPExecutor.java:347-350`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SEPExecutor.java#L347-L350)). So `Active ≤ knob` holds by construction whenever `workPermits ≥ 0`, which is always except after a shrink. An independent observable is added in B3d: the number of threads whose stack holds `org.apache.cassandra.transport.Dispatcher$RequestProcessor.run` in `jcmd Thread.print` (R_ntr), which counts NTR tasks actually running.
- (vi) **A shrink under load takes effect only as tasks finish.** After `setMaximumPoolSize(16)` from 256 with 256 tasks running, `workPermits` = −240, and `Active` reads 256 until those tasks finish. Each finishing worker returns its permit and leaves its executor ([`SEPExecutor.java:165-171`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SEPExecutor.java#L165-L171), [`SEPWorker.java:150-161`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SEPWorker.java#L150-L161)). "NTR Active ≤ 16 under new load" is therefore read after the in-flight tasks have drained (B3e amendment).
- (vii) **NMT on this host (instrument probe at the audit, not a case reading:** `stage4-runtime-verification/results/<stem>/audit/nmt-probe.txt`). A plain JVM with 200 extra parked threads was run on this JDK:
  - NMT `Thread` → `stack: reserved` grows by 268 KiB per thread at `-Xss256k` and by 1,036 KiB per thread at `-Xss1m`, i.e. Xss + 12 KiB.
  - `committed` equals `reserved` for thread stacks. JDK 11 finds committed stack pages only on Linux (`mincore`), so on macOS NMT's committed figure cannot show how much of a stack is touched. That is a named gap: B3d's "committed" proxy is not available here.
  - `ps` RSS grows by about 115 KiB per parked thread, whatever the Xss.
- (viii) **`nodetool tpstats` has no `MaxPoolSize` column.** Its columns are Pool Name, Active, Pending, Completed, Blocked and All time blocked ([`TpStatsPrinter.java:55`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/tools/nodetool/stats/TpStatsPrinter.java#L55)). The read-back of the knob is done through JMX (B3b amendment).
- Reason: the cluster runbook depends on (i)–(viii), and none of them depends on a reading of this case.

**A4. Other consumers.**
- All other heap use, including the request payloads waiting in the unbounded queues.
- Non-SharedPool threads: Netty event loops, compaction, and the `multiThreadedStage` pools (`Stage.java:212-218`, which use their own `ThreadPoolExecutor`).
- Native-transport in-flight byte limits, which are separate constraints.

**A5. Evidence beyond the source.**
- `CHANGES.txt:1374`: CASSANDRA-16186, which removed the blocking behaviour.
- `CHANGES.txt:1223`: CASSANDRA-16668, spin up workers when permits grow.
- `test/unit/org/apache/cassandra/concurrent/SEPExecutorTest.java:156-272`: existing concurrency tests using `assertMaxTaskConcurrency`.
- https://issues.apache.org/jira/browse/CASSANDRA-16186

## B. Verification solution

**B1. Claim under test.** With demand above the cap, the number of tasks of an SEP executor that run at once never exceeds its `maximumPoolSize`. The SharedPool worker-thread count, and with it the JVM's native thread memory (NMT "Thread"), rises with the knob and is bounded by about Σ maximumPoolSize + 2. Memory held by queued tasks does **not** follow the knob, and threads are not released when the knob is lowered.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B1, made falsifiable and split into three findings.** The filed sentence stays as the summary. It is tested as three findings, each with its own rows and controls:
- **F1 — running tasks are capped.** With demand above the cap, the number of tasks of one SEP executor running at once never exceeds `maximumPoolSize`, and it reaches it. The disallow branch shows as tasks left queued while the running count equals the cap. Running working memory follows the knob.
  - Unit: exact high-water `maxRunningFinal` = min(N, M); `pending` = M − min(N, M); running heap ≈ N MiB.
  - Cluster: NTR `Active` ≤ knob and R_ntr ≤ knob in every sample, with median `Active` = knob and NTR `Pending` ≈ 400 − knob.
  - Refuted if any reading exceeds the cap.
- **F2 — worker threads (and their stack memory) are capped by, and follow, the knob, and are not released.**
  - Unit: live pool threads ∈ [min(N, M), min(N, M) + 2]; threads ≥ 64 35 s after a shrink from 64 to 1.
  - Cluster: W_max ∈ [knob, knob + 144] and strictly increasing over the four knob values; W_max(256) − W_max(16) ≥ 200; NMT stack reserved per added thread ≈ Xss + 12 KiB; W does not drop 60 s after a runtime shrink.
  - Refuted if threads exceed the band by a wide margin (≥ 2N in the unit tier, > knob + 144 on the node), or if threads drop after a shrink or idle period.
  - "About Σ maximumPoolSize + 2" in the filed sentence means these exact bands.
- **F3 — memory held by queued tasks is not capped.**
  - Unit: the 64 MiB carried by 256 queued payloads appears in full whatever N is.
  - Cluster: the count only; NTR `Pending` holds the whole excess (400 − knob) at every knob.
  - Refuted if the queued memory shrinks with N (tasks blocked or dropped).

**Tier verdict.**
- **Confirmed:** every "supported" row of F1, F2 and F3 holds, and the controls hold.
- **Refuted:** any refuting row fires.
- **Not confirmed:** the limit is not reached, a control fails, or a reading falls outside a band without reaching a refuting row.
- **Invalid run:** a positive control of an instrument does not move (the Q phase in B2, the `-Xss1m` arm in B3).

**Effect on the constraint.** Threads and their stack memory: **caps** if F1 and F2 hold. Queued-task memory: **does not cap** if F3 holds. The overall Effect is "caps only on some paths (bypass)" when F1, F2 and F3 all hold (the queue is the bypass). It is "caps" if F3 is refuted and F1 and F2 hold, and "does not cap" if F1 or F2 is refuted.

Reason: the filed claim used "about" and gave no refuted-if per part. The caller asked that B1 be falsifiable and that the three quantities be kept apart.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 11, Ant.
- `git clone --branch cassandra-5.0.9 --depth 1 <shared-clone-path> /local/c509` (on local disk), then `cd /local/c509 && ant build-test`.
- Test source: `/local/c509/test/unit/org/apache/cassandra/concurrent/SEPMaxPoolSizeFootprintTest.java`. It is in the same package, so it can reach the package-private `SharedExecutorPool.threadGroup`.
- JVM options are the test defaults from build.xml.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B2a, this host.** macOS arm64, JDK 11.0.32.1, Ant 1.10.18. Run clone `$W/cassandra-run29` (`W=~/Library/Caches/stage4`; `git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run29`, a full clone at `b5f2a54210`, then `ant -Dlocal.repository=$W/m2 build-test`). The test is `harness/sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/SEPMaxPoolSizeFootprintTest.java`; `unit-run.sh` copies it into the clone's `test/unit/org/apache/cassandra/concurrent/`. The test JVM uses CMS under JDK 11 (`build.xml:231-240`), so a 1 MiB `byte[]` is an ordinary object (no G1 humongous rounding). Reason: B2a named a CloudLab path.

**B2b. Knobs.** `maxConcurrency` N ∈ {1, 4, 16, 64}, passed to `pool.newExecutor(N, "internal", "fp"+N)`. The values span 1 to 64 so that a linear relation is visible. Then, in a second phase, a runtime shrink `exec.setMaximumPoolSize(1)` from N = 64.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B2b, values and a control.** N ∈ {1, 4, 16, 32, 64, 128}. 32 (the stage default) and 128 (the NTR default) are added, so the defaults are among the values; M = 256 still exceeds every N. The shrink phase stays at N = 64. **Control D (demand below the cap):** N = 64 with M = 8 tasks, no payload. Threads and running tasks should follow the demand (8), not the knob. Reason: group A asks for the default among the values; F1 and F2 need a demand-below-cap control.

**B2c. Workload.** M = 256 blocking tasks per N, so M > N for every N and the cap binds.
- Each running task allocates and holds a 1 MiB `byte[]`, so running memory is N MiB.
- Phase Q (positive control): each task also carries a 256 KiB `byte[]`, allocated at submission. That is 256 × 256 KiB = 64 MiB of queued memory, whatever N is.

Code sketch (complete enough to type in):

```java
package org.apache.cassandra.concurrent;
import java.lang.management.*; import java.util.concurrent.*; import java.util.concurrent.atomic.*;
import org.junit.*; import org.apache.cassandra.config.DatabaseDescriptor;
public class SEPMaxPoolSizeFootprintTest {
  @BeforeClass public static void init() { DatabaseDescriptor.daemonInitialization(); }
  static long heapUsed() { for (int i=0;i<3;i++) System.gc(); return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed(); }
  static int liveThreads(SharedExecutorPool p) { Thread[] t = new Thread[4096]; int n = p.threadGroup.enumerate(t); int c=0; for (int i=0;i<n;i++) if (t[i].isAlive()) c++; return c; }
  void run(int N, boolean queuedPayload) throws Exception {
    SharedExecutorPool pool = new SharedExecutorPool("FP" + N + (queuedPayload ? "Q" : ""));
    LocalAwareExecutorPlus ex = pool.newExecutor(N, "internal", "fp" + N + (queuedPayload ? "q" : ""));
    AtomicInteger running = new AtomicInteger(), maxRunning = new AtomicInteger();
    CountDownLatch release = new CountDownLatch(1); long h0 = heapUsed();
    for (int i = 0; i < 256; i++) {
      final byte[] carried = queuedPayload ? new byte[256 << 10] : null;
      ex.execute(() -> { int r = running.incrementAndGet(); maxRunning.accumulateAndGet(r, Math::max);
        byte[] held = new byte[1 << 20]; try { release.await(30, TimeUnit.SECONDS); } catch (InterruptedException e) {}
        if (held.length + (carried == null ? 0 : carried.length) < 0) System.out.print(""); running.decrementAndGet(); });
    }
    Thread.sleep(2000);
    System.out.printf("N=%d Q=%b maxRunning=%d active=%d pending=%d threads=%d heapDeltaMiB=%.1f%n", N, queuedPayload,
      maxRunning.get(), ((SEPExecutor) ex).getActiveTaskCount(), ((SEPExecutor) ex).getPendingTaskCount(), liveThreads(pool), (heapUsed()-h0)/1048576.0);
    release.countDown(); while (((SEPExecutor) ex).getCompletedTaskCount() < 256) Thread.sleep(50);
    if (N == 64 && !queuedPayload) { ex.setMaximumPoolSize(1); Thread.sleep(2000);
      System.out.printf("after shrink to 1: threads=%d%n", liveThreads(pool)); }
    pool.shutdownAndWait(10, TimeUnit.SECONDS);
  }
  @Test public void sweep() throws Exception { for (int N : new int[]{1,4,16,64}) { run(N,false); run(N,true); } }
}
```

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B2c, the code as run.** The sketch is kept, with these changes:
- `run(N, M, queuedPayload, shrink)` takes M (256, or 8 for control D).
- The sample line prints `SEPFP N= M= Q= settleMs= maxRunning= active= pending= threads= heapDeltaBytes=`. If `maxRunning < min(N, M)` after 2 s, the test waits 3 s more and prints `settleMs=5000` (B2h).
- After all tasks complete, `SEPFP-DONE … maxRunningFinal=` gives the exact high-water over the whole run, including the release.
- After the shrink, the test reads back `getMaximumPoolSize()` and waits **35 s** (more than the 30 s of the yaml comment at `conf/cassandra.yaml:1033-1034`; the filed 2 s could not test it). It then prints `SEPFP-SHRINK max= threads= waitMs=35000`.
- The sweep runs N = 1, 4, 16, 32, 64, 128, each without and then with the payload, and then control D.

Reason: the M parameter and the control; the filed 2 s wait could not separate "parked forever" from "stopped after 30 s".

**B2d. Observables and instruments.**
- `maxRunning`: the exact high-water count of running tasks.
- `getActiveTaskCount()` (`SEPExecutor.java:347-350`) and `getPendingTaskCount()` (`:336-339`).
- Live threads in the pool's `ThreadGroup`.
- Heap used after three `System.gc()` calls (`MemoryMXBean`).

Each is sampled once, 2 s after submission, and the thread count once more after the shrink. Per-thread native stack memory cannot be seen here; it is measured in B3.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B2d, where the readings are read.** The unit JVM sends `System.out` to `build/test/logs/**/TEST-org.apache.cassandra.concurrent.SEPMaxPoolSizeFootprintTest.log`. Every reading is read from the lines starting `SEPFP` in that file; JUnit pass and fail counts come from the XML in `build/test/output/`. Reason: the closed cases on this machine found the output there.

**Amendment 2026-10-26 (stage 4 unit attempt 0, runbook defect 1; Claude Opus 5.5, claude-opus-5-5) — B2d, one line per reading.** The test JVM logs every write to `System.out` as its own line, with an `INFO  [main] <timestamp> ` prefix. The sketch's `printf` writes each format piece separately, so attempt 0 (three runs, JUnit passing) produced every reading split over about twenty log lines, and the harness's `^SEPFP` filter found none. Each reading is now printed by one `System.out.println(String.format(…))`, with the same fields. It is read from the text from `SEPFP` to the end of its log line. B2f–B2h are unchanged. The attempt-0 values were not read, and the unit tier restarts from r1. Reason: B2 could not run as written on this build.

**B2e. Procedure.**
1. Clone and build as in B2a.
2. Add the test file.
3. Run `ant testsome -Dtest.name=org.apache.cassandra.concurrent.SEPMaxPoolSizeFootprintTest`.
4. Collect the printed lines from `build/test/output/TEST-*.xml`, or from stdout.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B2e, the procedure as run.** `harness/sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/unit-run.sh r1`, then `r2` and `r3`: three runs of the same test, one JVM each. Each run copies the class into the clone and runs `ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.concurrent.SEPMaxPoolSizeFootprintTest`. It copies the XML, the test log and the `SEPFP` lines to `$W/logs/sep_maximum_pool_size-takeWorkPermit/unit-<run>/`. After r3 the class and `build/test/cassandra` are removed from the clone. Reason: procedure on this host; three runs show that the exact readings repeat.

**B2f. Predictions.**
- For each N: `maxRunning == N`, `active == N`, `pending == 256 − N`, and `threads ∈ [N, N+2]`.
- heapDelta without Q ≈ N MiB (±4 MiB).
- heapDelta with Q ≈ N MiB + 64 MiB, so the extra 64 MiB is the same for all N.
- After the shrink from 64 to 1, threads stay ≥ 64 (no reclamation).

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B2f, exact values.** The filed predictions stay. For every run and every (N, M):
- `maxRunningFinal` = `maxRunning` = `active` = min(N, M); `pending` = M − min(N, M); `threads` ∈ [min(N, M), min(N, M) + 2].
- No payload, M = 256: `heapDelta` ∈ [N − 4, N + 4] MiB.
- ΔQ(N) = heapDelta(Q) − heapDelta(no Q) ∈ [60, 68] MiB for every N. The derived value is 256 × 256 KiB = 64 MiB.
- After the shrink: read-back `max` = 1, and `threads` ≥ 64 after 35 s.
- Control D: `maxRunningFinal` = 8 and `threads` ∈ [8, 10].
- r1, r2 and r3 give the same `maxRunningFinal`, `active` and `pending`.

Reason: group B asks for numbers or a clear relation.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| maxRunning = N and threads ∈ [N, N+2] for all N; heapDelta (no Q) rises with N | Mechanism works as traced; thread count and running memory follow the knob (claim supported) |
| maxRunning > N for any N | Cap is not enforced: claim wrong |
| threads > N+2 persistently (e.g. ≥ 2N) | The thread count is not bounded by the knob: the thread-memory part of the claim is wrong |
| Q phase adds ~64 MiB for every N | Queued memory is independent of the knob (positive control moves; confirms the unbounded-queue part) |
| Q phase adds no memory | Instrument insensitive; run not usable |
| threads drop to ~1 after the shrink | Threads are reclaimed: claim (b) of A3 wrong |
| maxRunning < N | Workload did not reach the cap; not confirmed |

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B2g, rows by finding.** The filed rows stay and map as follows; rows marked + are added.

| Finding | Observation | Meaning |
|---|---|---|
| F1 | `maxRunningFinal` = min(N, M) and `pending` = M − min(N, M) for every N, in all three runs; heapDelta (no Q) in [N − 4, N + 4] MiB | Running tasks capped and running memory follows the knob: **F1 supported** |
| F1 | `maxRunningFinal` > N for any N in any run | Cap not enforced: **F1 refuted** |
| F1 + | `maxRunning` < min(N, M) after 5 s | Limit not reached: **Not confirmed** |
| F1 + | heapDelta (no Q) outside [N − 4, N + 4] MiB for some N, F1 counts exact | Running memory does not follow the knob as derived: F1 memory part **Not confirmed** |
| F2 | `threads` ∈ [min(N, M), min(N, M) + 2] for every N and for control D | Thread count follows the knob when demand exceeds it, and the demand when it does not: **F2 supported** |
| F2 + | `threads` > min(N, M) + 2 but < 2N for some N | Outside the derived band: **F2 Not confirmed** |
| F2 | `threads` ≥ 2N (N ≥ 4) in any run | Threads not bounded by the knob: **F2 refuted** |
| F2 | `threads` ≥ 64 35 s after the shrink | No reclamation: supports A3 (b), against the yaml comment |
| F2 | `threads` < 64 after the shrink | Threads reclaimed: **A3 (b) refuted** (F2's no-release part) |
| F3 | ΔQ ∈ [60, 68] MiB for every N | Queued memory independent of the knob: **F3 supported** (positive control moves) |
| F3 + | ΔQ outside [60, 68] for some N but ≥ 8 for all N | **F3 Not confirmed** (band missed) |
| F3 + | ΔQ < 60 at small N and rising with N (queued payloads missing) | The queue is bounded: **F3 refuted** |
| F3 | ΔQ < 8 MiB for every N | Instrument insensitive: **Invalid run** |

Tier verdict and Effect: as in the B1 amendment. Reason: group B needs a row per outcome and per finding.

**B2h. Controls.**
- A fresh `SharedExecutorPool` per run isolates the thread count from `SHARED`.
- M is fixed while N varies.
- The Q phase is the positive control for the heap instrument.
- The 2 s settle time allows workers to be scheduled. If `maxRunning < N`, repeat with 5 s.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B2h, the added control.** Control D (N = 64, M = 8) separates demand from the knob for running tasks and threads. The three runs r1–r3 check that the exact readings repeat. Reason: B1 amendment.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node, JDK 11, built from `/local/c509` with `ant jar`.
- Local disk with ≥ 10 GiB free for `data_file_directories`, `commitlog_directory`, `hints_directory`, and `saved_caches_directory`, all under `/local/c509-data/`.
- Heap: `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`.
- `JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary -Dcassandra.set_sep_thread_name=false"`. The property is defined at `src/java/org/apache/cassandra/config/CassandraRelevantProperties.java:492`. With it, all workers keep the name `SharedPool-Worker-<id>` (`SEPWorker.java:58,124-125`).
- yaml: `read_request_timeout: 120000ms`, `range_request_timeout: 120000ms`. All other `concurrent_*` stay at 32.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B3a, this host.**
- **Node and directories.** One node on `127.0.0.1` from the run clone `$W/cassandra-run29`; node directories under `$W/node-sep/` (data, commitlog, hints, saved_caches, cdc_raw). The conf is the clone's `conf/` with the tag's `cassandra.yaml` plus the lines below, rebuilt by `harness/sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/cluster-run.sh` for each start; a key already in the yaml is removed first.
- **yaml lines.** `cluster_name: sep`, `num_tokens: 16`, addresses `127.0.0.1`, the directories, `native_transport_max_threads: <knob>`, and `read_request_timeout: 300000ms`, `range_request_timeout: 300000ms`, **`native_transport_timeout: 300s`** (A3 amendment (ii); the filed 120 000 ms is raised to 300 s, so that neither the per-request timeout nor the client deadline ends a query while it waits behind 400 others). All other `concurrent_*` stay at 32, and read thresholds stay at the node default (off).
- **JVM.** `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M` (G1; the new size is ignored with G1). `JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary -Dcassandra.set_sep_thread_name=false"` (plus `-Xss1m` in the control arm), scoped to the `bin/cassandra` command. The shipped `-XX:+AlwaysPreTouch` keeps the heap resident from the start, so RSS changes are native.
- **Start and stop.** `nohup bin/cassandra -f > node.out &` with `disown` (no `setsid` here), the pid from `$!`. Up means `nodetool status` shows `UN` and `nodetool statusbinary` prints `running`. Stop with `nodetool drain`, then `kill`, then a wait.
- **Instrument check per start.** `jcmd <pid> VM.flags` records `ThreadStackSize`, and the command line records the options.

Reason: B3a named CloudLab paths; the timeout change follows from A3 amendment (ii).

**Amendment 2026-10-28 (after run 1, authorised by the user) — B3a, a fresh clone for the cluster re-run.** This amendment follows run 1's readings (see the B3f amendment of 2026-10-28). The re-run uses a fresh clone, `$W/cassandra-run72`: `git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run72`, then `ant -Dlocal.repository=$W/m2 build-test`. The node directories are under `$W/node-sep72/`. `cluster-run.sh` takes the clone and the node directory from `SEP_C` and `SEP_NODE`; without them it uses run 1's paths. Commands: `SEP_C=$W/cassandra-run72 SEP_NODE=$W/node-sep72 cluster-run.sh shake-run2 shake` (shakedown), then `… cluster-run.sh run2 run1` (the run-1 plan, unchanged). The yaml lines, JVM options, start/stop and instrument checks are unchanged. Reason: a separate clone per run (`HANDOFF-ADVISOR.md` §7.1).

**B3b. Knobs.** `native_transport_max_threads` ∈ {16, 64, 256}, set in yaml and applied with a restart for each value. The values bracket the default of 128, and 256 is still below the client concurrency C = 400, so the cap binds at every value. In a second phase, at 256: a runtime shrink to 16 through JMX:

```
bin/nodetool sjk mx -b 'org.apache.cassandra.transport:type=Native-Transport-Requests' -f MaximumPoolSize -ms -v 16
```

Check the flags first with `nodetool sjk mx --help`. Confirm the value with `-mg` and with the `MaxPoolSize` column of `nodetool tpstats`.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B3b, values and read-back.**
- **Values.** `native_transport_max_threads` ∈ {16, 64, **128**, 256}. The default, 128, is added (group A asks for the default among the values). Each value gets a fresh start; the data is reused.
- **Runtime shrink.** At 256, after the C = 400 load has drained, the knob is set to 16 with the harness's JMX client (`harness/sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/Jmx.java`). It sets the same MBean attribute as the filed sjk command: `set org.apache.cassandra.transport:type=Native-Transport-Requests MaximumPoolSize int:16`. `nodetool sjk mx --help` on this build prints a `NullPointerException` and a generic usage, so the filed sjk syntax is not used.
- **Read-back** at every start and after the shrink: the MBean attribute `MaximumPoolSize`, and the gauge `org.apache.cassandra.metrics:type=ThreadPools,path=transport,scope=Native-Transport-Requests,name=MaxPoolSize`. `tpstats` has no such column (A3 amendment (viii)).

Reason: group A; the read-back named a column that does not exist.

**B3c. Workload.**
1. Populate: `tools/bin/cassandra-stress write n=2000000 -rate threads=64 -schema 'replication(factor=1)'`. That is about 2M rows, under 1 GiB on disk. Then run `nodetool flush`.
2. Load: a Python 3 script that uses the bundled driver (`sys.path.insert(0, '/local/c509/lib/cassandra-driver-internal-only-3.29.0.zip')`). If the import fails, use a venv on local disk with `pip install cassandra-driver==3.29.0`. The script keeps C = 400 concurrent `session.execute_async("SELECT count(*) FROM keyspace1.standard1", timeout=300)` in flight for 180 s, firing a new query whenever one completes. Each count(*) pages through the whole table on the coordinator's Native-Transport-Requests thread (dispatch: `Dispatcher.java:123-124`), so it holds a permit for seconds. Demand is 400 > 256, so the knob is reached.
3. Control load: C = 8 with the same query.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B3c, the workload as run.**
- **Populate** in a separate start, before the knob starts, at the default knob: `tools/bin/cassandra-stress write n=200000 no-warmup -rate threads=64 -schema 'replication(factor=1)' -node 127.0.0.1`, run with its working directory in `$W`. Then `nodetool flush keyspace1` and `nodetool compact keyspace1`, a `count(*)` to record the row count, and a stop.
  - The populate gets its own start because its writes would otherwise raise the knob start's thread high-water mark (A3 amendment (iii)).
  - n is reduced from 2 M to 200 k rows. Under 400 outstanding queries, a request's latency is about 400 × (cost of one scan) / (cores). At 2 M rows that approaches the 300 s timeouts on 10 cores, and a full drain would take minutes.
  - The load-bearing property is that each query holds an NTR permit long after the client turnaround. Every completed query is replaced at once, so with demand at 400 the running count stays at the cap whatever one scan costs (A3 amendment (i)). The shakedown checks it.
- **Client.** `harness/sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/loadclient.py` with the bundled driver (`lib/cassandra-driver-internal-only-3.29.0.zip`), protocol 5, `DCAwareRoundRobinPolicy`, `token_metadata_enabled=False`, `schema_metadata_enabled=False`, CL ONE, request timeout 300 s. Each statement is `SELECT count(*) FROM keyspace1.standard1`.
  - **C = 400:** 4 processes × 100 queries in flight, one `Cluster` (one connection to the host) per process. All start at a common epoch, and each completed query is re-fired from its callback until the end time.
  - **C = 8:** 1 process × 8.
  - On an error, the process logs it and re-fires after 0.2 s. On a connection-level error (`ConnectionShutdown`, `NoHostAvailable`, `OperationTimedOut`, `ConnectionException`), it rebuilds its session (the ENOBUFS lesson). After the end time it waits for its outstanding queries (up to 330 s).
  - Each process writes one line per completed query and its in-flight count every second.
  - Client sizing: 4 processes with 4 connections (plus 4 control connections). The tiny requests and responses keep the client far below its limits; `ulimit -n` 1,048,576 and `kern.ipc.somaxconn` 128 are recorded in step E.

Reason: the populate would contaminate the high-water mark; the filed size cannot finish within any timeout here; the caller asked for a client sized so that the server is the bottleneck.

**Amendment 2026-10-26 (stage 4 cluster run 1 attempt 0, runbook defect 4; Claude Opus 5.5, claude-opus-5-5) — B3c, the client's heartbeat.** In attempt 0, at knob 16 under C = 400, one of the four client processes lost its connection: `ConnectionShutdown … Connection heartbeat timeout after 30 seconds`, 100 queries failed (5.9% of the phase), and the process reconnected about 100 s later (`cluster-run1-attempt0/k16/C400/w01.lines`).
- **Cause.** The driver's idle heartbeat is an `OPTIONS` request, and it waits in the same NTR queue as the count(\*) queries. At knob 16, about 384 requests wait in that queue, so the heartbeat waited longer than its 30 s timeout. The driver then closed the connection, and `Cluster.shutdown()` blocked the process's rebuild.
- **The same would recur.** At knob 64 and 128 the queue wait is still near or above 30 s; the client cannot keep 400 queries outstanding as B3c requires.
- **Fix.** `loadclient.py` sets `idle_heartbeat_interval=0` (no heartbeat requests), shuts an old session down in a thread for at most 5 s, and writes its `inflight` lines from a separate reporter thread. A rebuild can then no longer hide a gap in the in-flight record. The self-check gains a stricter coverage check: per process, `inflight` lines on ≥ 90% of the seconds of each C400 window.

B3f–B3h are unchanged. Attempt 0 was stopped at knob 128, and its readings are not used. The cluster tier restarts from its beginning. Reason: B3 could not run as written; the fix changes only the client.

**B3d. Observables and instruments.** Sampled every 5 s by a shell loop during the 180 s:
- `jcmd <pid> Thread.print | grep -c '"SharedPool-Worker-'`: the SharedPool thread count W.
- `jcmd <pid> VM.native_memory summary | grep -A2 -- '- *Thread'`: thread count, and reserved and committed thread memory.
- `bin/nodetool tpstats | grep -E 'Native-Transport-Requests|ReadStage'`: Active, Pending, MaxPoolSize.
- `ps -o rss= -p <pid>`.

How much of a thread's stack is touched cannot be seen directly; NMT's committed figure is the proxy.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B3d, instruments as run.** A bash sampler takes a sample every 5 s (all phases, including idle and drain). Each sample stores the raw outputs under `<start>/samples/` and one CSV line. A sample holds:
- `jcmd <pid> Thread.print`. From it: W = count of `"SharedPool-Worker-`; **R_ntr** = count of `Dispatcher$RequestProcessor.run` frames (NTR tasks running; A3 amendment (v)); R_read = count of `StorageProxy$LocalReadRunnable` frames.
- `jcmd <pid> VM.native_memory summary`. From it, the `Thread` block: reserved, committed, thread #, and `stack: reserved` / `committed`.
- `nodetool tpstats`: Active and Pending of `Native-Transport-Requests` and `ReadStage`.
- `ps -o rss= -p <pid>`.

The current phase name is stamped on each line, and each phase's start and end epoch go to `phases.txt`. The full thread dumps are kept, so every count can be recomputed. Reason: an independent running-task count, and raw files for the self-check.

**Amendment 2026-10-26 (stage 4 cluster shakedown, before cluster run 1, runbook defect 2; Claude Opus 5.5, claude-opus-5-5) — B3d, Active and Pending from one persistent JMX connection.** Under the C = 400 load, one `nodetool tpstats` took 12–27 s on this host, because a new JVM and its JMX session compete with a node that uses every core. `jcmd Thread.print` took up to 5.6 s and `VM.native_memory` up to 4.6 s (`cluster-timing/k16/sample-timing.txt`). The shell loop therefore sampled every 11–38 s instead of every 5 s. As fixed:
- NTR and ReadStage `Active` and `Pending` are read once a second by `harness/sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/TpPoll.java`. It reads the same gauges that `tpstats` prints (`NodeProbe.getThreadPoolMetric`, `NodeProbe.java:1851-1854`: `org.apache.cassandra.metrics:type=ThreadPools,path=<path>,scope=<pool>,name=ActiveTasks|PendingTasks`), plus NTR `MaxPoolSize`, and writes one line per poll to `<start>/tpjmx.log`.
- Each 5 s sample takes the two `jcmd` outputs in parallel and pairs them with the poll nearest in time. "Every sample" in B3f for `Active` also covers every 1 s poll of the phase.
- `nodetool tpstats` is still used for the drain check, after the load.

B3f–B3h are unchanged. The shakedown is repeated. Reason: B3 could not run as written on this host; the fix reads the same quantities.

**Amendment 2026-10-26 (stage 4 second cluster shakedown, before cluster run 1, runbook defect 3; Claude Opus 5.5, claude-opus-5-5) — B3d, the diagnostic commands without process spawns.** With defect 2 fixed, the loaded samples still came every 8–36 s (`cluster-shake2/*/samples.csv`). Under the saturated CPU, each process spawn costs 0.2–2 s on this host (a profile under artificial load: `jcmd` 0.9–2.5 s each, a `grep` + `ps` pair 0.3–1.9 s, a `perl` clock call 0.2–1.3 s), and the shell sampler spawns about 25 processes per sample. As fixed:
- One persistent Java sampler, `harness/sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/Sampler.java` (it replaces `TpPoll.java`), holds the JMX connection.
- Every 1 s it reads the `tpstats` gauges as in the defect-2 fix.
- Every 5 s it runs the **same diagnostic commands** `Thread.print` and `VM.native_memory summary` through the JVM's `com.sun.management:type=DiagnosticCommand` MBean (operations `threadPrint` and `vmNativeMemory`, the DCmds `jcmd` invokes). It saves their raw text as before and spawns only `ps -o rss=`.

The observables, their parsing and B3f–B3h are unchanged. The shakedown is repeated. Reason: B3 could not run as written on this host; the fix runs the same commands in-process.

**B3e. Procedure.**
1. Clone, build, and configure as in B3a.
2. For each knob value:
   1. Set it in yaml.
   2. Start with `bin/cassandra -p /local/c509-data/pid`.
   3. Wait for `nodetool status` to show UN.
   4. Populate (first time only; later runs reuse the data).
   5. Take an idle sample.
   6. Run the C = 400 load with sampling.
   7. Run the C = 8 control load with sampling.
   8. Stop with `kill $(cat /local/c509-data/pid)`.
3. At knob 256, after the C = 400 run: shrink to 16 through JMX, wait 60 s, and sample W and NMT Thread again.
4. Positive control for the memory instrument: at knob 256, restart with `-Xss1m` added to `JVM_EXTRA_OPTS` and repeat the C = 400 run.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B3e, the procedure as run** (`harness/sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous/cluster-run.sh run1`; `shake` for the shakedown).
1. **Pre-checks:** no Cassandra process, ports 7000, 7199, 9042 and 9091 free, at least 20 GiB free.
2. **Populate start** (B3c amendment), then stop.
3. **For each knob in 16, 64, 128, 256**, a fresh start on the same data:
   1. Read back the knob and `ThreadStackSize`.
   2. **idle** 30 s (6 samples; drift control).
   3. **C8** load 180 s, then **drain**: sample until NTR and ReadStage show Active = Pending = 0 twice in a row, at most 600 s.
   4. **C400** load 180 s, then drain.
   5. At 256 only, then: shrink to 16 and read back; **postshrink-idle** 60 s; **postshrink-C400** load 60 s; drain.
   6. Stop.
   - The C = 8 control now runs **before** the C = 400 load (A3 amendment (iii)): run after it, it would read the earlier high-water mark.
4. **Control X:** knob 256 with `-Xss1m`: idle 30 s, C400 180 s, drain, stop.
5. **End:** wipe `$W/node-sep` and check that no Cassandra or stress process is left.

A **shakedown** (`shake`) runs before run 1. It populates, then knob 256 and knob 16 with 40 s loads, including the shrink. It checks that the client keeps 400 queries outstanding without errors, that each instrument and the JMX set work, that a drain finishes, and that the query latency stays far below the 300 s timeouts. Its readings are not used. Reason: order of the control; the post-shrink check needs new load after the drain (A3 amendment (vi)).

**B3f. Predictions.** Here nproc = the core count, and R = active ReadStage ≤ 32.
- NTR `Active` ≤ knob in every sample, and NTR `Pending` ≈ 400 − knob.
- W_max(knob) ∈ [knob, knob + 32·4 + nproc + 4 + 2]. In practice expect W_max ≈ knob + R + small.
- W_max(256) − W_max(16) ≥ 200.
- NMT Thread reserved grows by about ΔW × 0.26 MiB, so ≈ 60 MiB reserved from 16 to 256. Committed grows by less, but by at least ΔW × 16 KiB ≈ 4 MiB.
- At C = 8, W_max ≤ 8 + 32 + nproc + 6 whatever the knob (threads are created on demand).
- After the runtime shrink, W does not drop (no reclamation), while NTR `Active` ≤ 16 under any new load.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B3f, exact values.** nproc = 10. The C = 400 "steady window" of a phase is its samples from 30 s after the start to the end time. The "peak sample" of a phase is its sample with the largest W (the latest, if tied).
- **F1.**
  - In every C400 sample, NTR Active ≤ knob and R_ntr ≤ knob.
  - In the steady window, median Active = knob, median R_ntr ≥ knob − 4, and median NTR Pending ∈ [400 − knob − 40, 400 − knob + 8]. The +8 allows the drivers' heartbeat and control requests.
  - In every C8 sample, Active ≤ 10 and R_ntr ≤ 10 (8 queries plus up to 2 driver requests).
  - In every postshrink-C400 sample, Active ≤ 16 and R_ntr ≤ 16, with median Active = 16.
- **F2.**
  - W_max(C400, knob) ∈ [knob, knob + 144] (= knob + 4·32 + nproc + 4 + 2), and W_max(16) < W_max(64) < W_max(128) < W_max(256).
  - W_max(256) − W_max(16) ≥ 200. The expected value is W_max ≈ knob + R + a few, with R ≤ 32 ReadStage workers.
  - W_max(C8) ≤ max(W_idle, 56) at every knob (56 = 8 + 32 + nproc + 6).
  - W in the postshrink-idle samples ≥ W at the end of the preceding drain. Threads are never released, so equality is expected.
- **Thread memory (F2).** S = NMT `stack: reserved`, T = NMT `thread #`, both at the peak samples of C400.
  - ΔS(16→256) / ΔT(16→256) ∈ [256, 320] KiB per thread (probe: 268), and ΔS(16→256) ≥ 50 MiB (≈ 200 × 256 KiB; the expected value is ≈ 240 × 268 KiB ≈ 63 MiB).
  - Committed is reported against the filed lower bound ΔW × 16 KiB, but on this host it equals reserved (A3 amendment (vii)).
  - **Control X:** slope = (S_peak − S_idle) / (T_peak − T_idle) within one JVM, with the idle value from the last idle sample. slope(X) / slope(256) ∈ [3.0, 4.0], with T_peak − T_idle ≥ 100 in both. The probe ratio is 3.87; GC or compiler threads created during the load lower it.
  - **Drift control:** in each idle phase, W is constant and S varies by ≤ 4 MiB.
- **F3 (count only).** NTR Pending as in F1, at every knob.
- **Significance, informational** (does not enter the verdict): ΔRSS(16→256) between the C400 peak samples, against 1% of the heap (20.48 MiB). The NMT committed figure is not used for significance here (A3 amendment (vii)).
- **Validity.** In every C400 phase, the client's median in-flight count is ≥ 390, and fewer than 1% of the completed queries are errors.

Reason: group B asks for numbers; the NMT relations are derived from the source and the probe.

**Amendment 2026-10-28 (after run 1, authorised by the user) — B3f, the idle drift control restated from the source.** This amendment follows run 1's readings. In run 1 the drift control "in each idle phase, W is constant" failed by one thread (W 0 → 1) in three of five starts, and the cluster tier was Not confirmed through that control alone (results §4.2). The user (Yang, the advisor) authorised on 2026-10-28 that this control be restated from the source and the cluster tier re-run from its beginning. B1, every F1/F2/F3 relation above, the S part of the drift control, the validity rule, B3g and the unit tier are unchanged.
- **Which internal task creates a SharedPool worker after start-up, and when** (from the source):
  1. `CassandraDaemon.java:406` calls `StorageService.doAuthSetup` once (`StorageService.java:1442-1451`; with `joinRing` true, the call at `:1058` is not reached, and `:1444` guards repeats). It calls `CassandraRoleManager.setup()` (`CassandraRoleManager.java:165-171`; `role_manager: CassandraRoleManager`, `conf/cassandra.yaml:232`). This schedules the default-role setup task on `ScheduledExecutors.optionalTasks` after `AuthKeyspace.SUPERUSER_SETUP_DELAY` (`CassandraRoleManager.java:485-504`, `AuthKeyspace.java:69`). The delay is 10,000 ms by default (`cassandra.superuser_setup_delay_ms`, `CassandraRelevantProperties.java:538`), and the harness does not set it.
  2. The task, `setupDefaultRole` (`:443-461`), calls `hasExistingRoles()` (`:473-482`). In every knob start the role `cassandra` already exists: the populate start inserted it (`:450-455`), and the data directory is reused (B3c amendment). So only the first query runs (`:480`; `||` stops there). It is one single-partition CL ONE read of `system_auth.roles`, local on this one-node ring.
  3. That read reaches `Stage.READ.maybeExecuteImmediately` (`AbstractReadExecutor.java:165`). `takeWorkPermit(false)` returns false whenever `taskPermits == 0`, whatever its argument (`SEPExecutor.java:196`). So on an idle executor the task is queued (`:221-223`). The queue was empty, so `addTask` calls `pool.maybeStartSpinningWorker()` (`:135-142`). With no spinning worker, that calls `schedule(Work.SPINNING)` (`SharedExecutorPool.java:137-138`). With the `spinning` and `descheduled` maps empty, `schedule` creates one `SEPWorker` (`:108-116`). The worker runs the read, then spins, is descheduled and parks (`SEPWorker.java:116-118`, `:228-230`). It is never stopped (A3 amendment (iii)).
  4. **How many workers.** The task creates **exactly one** worker if no SharedPool worker exists when it runs, and **none** otherwise, because an existing spinning or descheduled worker is reused (`SharedExecutorPool.java:108-112`). A rerun of the task creates none either: it finds the parked worker. A rerun happens after a not-safe read (`CassandraRoleManager.java:489-493`) or after an exception, which is logged as "Setup task failed with error, rescheduling" (`:501`).
  5. **When.** The task runs at T_auth + 10,000 ms. T_auth lies between two INFO lines of the start's `system.log`, both before "Startup complete" (`CassandraDaemon.java:744`):
     - T_ar: "Auto-repair service is disabled via JVM property, skipping setup" (`StorageService.java:1466`). It comes from `finishJoiningRing` (`:1438`) during `initServer`, which precedes `CassandraDaemon.java:406`.
     - T_pw: "Prewarming of auth caches is disabled" (`CassandraDaemon.java:450`), after `:406`.

     So the worker appears in [T_ar + 10 s, T_pw + 10 s + the task's own run time]. That is about 10 s after "Startup complete", inside B3e's 30 s idle phase, which starts once `nodetool` sees the node up.
  6. **No other source in the idle phase.** These are the other submitters to SharedPool executors (`grep` of `Stage.{READ,MUTATION,COUNTER_MUTATION,VIEW_MUTATION,REQUEST_RESPONSE}` and `SharedExecutorPool.SHARED`), and why none creates a worker here:
     - Commit-log replay (`CommitLogReplayer.java:331`) runs before "Startup complete".
     - The counter-cache and row-cache loads (`CacheService.java:385`, `:414`) submit nothing here: there is no counter table and the row cache is off.
     - Range reads (`RangeCommandIterator.java:207`), coordinator reads and writes, and both native-transport executors (`Dispatcher.java:58`, `:77`) need a client request. In the idle phase the harness uses only JMX.
     - Internode verbs need a peer, and the ring has one node.
     - The batchlog replay at `RING_DELAY` uses internal paging (`BatchlogManager.java:114-115`, `:223`). The size-estimate recorder at 30 s writes internally (`CassandraDaemon.java:371`). The view rebuild at `RING_DELAY` (`CassandraDaemon.java:401`) has no views to build.

     In any case, a sequential internal task that finds the parked worker reuses it (item 4).
  - **Instrument check** (2026-10-28, before this amendment; a diagnostic start, not a case reading): `stage4-runtime-verification/results/<stem>/run1b-cluster/instrument/`. Observe-only Byteman rules (`harness/<stem>/sep-worker-origin.btm`, `TestScript: no errors`) ran in one knob-16 start on populated data, 90 s idle, in the re-run clone. They recorded exactly one SEP `addTask` and exactly one `new SEPWorker` during the start. The creator was `OptionalTasks:1`, with the stack `SharedExecutorPool.schedule:114` ← `maybeStartSpinningWorker:138` ← `SEPExecutor.addTask:142` ← `maybeExecuteImmediately:223` ← `AbstractReadExecutor.makeRequests:165` ← … ← `CassandraRoleManager.hasExistingRoles:480` ← `setupDefaultRole:450` ← the `scheduleSetupTask` lambda `:497`. The task started 10,006 ms after `doAuthSetup`. This confirms items 1–5; the relations below come from the source.
- **Restated drift control.** It replaces "in each idle phase, W is constant"; the S part stays. In each knob start's `idle` phase:
  - **(d1)** W never decreases. It rises at most once, by exactly 1, and only from 0 to 1: this is the one worker of item 4. If W ≥ 1 at the first idle sample, W is constant.
  - **(d2)** No idle sample whose thread dump ended before T_ar + 10,000 ms shows W ≥ 1, because the task cannot have run yet. T_ar is read from the start's `system.log`. The dump's end is the sample time plus its `td` duration in `sample-timing.txt`.
  - **(d3)** S varies by ≤ 4 MiB (unchanged). One thread adds Xss + 12 KiB = 268 KiB (A3 amendment (vii)).
  - Also checked: `system.log`'s JVM arguments do not set `cassandra.superuser_setup_delay_ms`.
  - Reported, not conditions: the time of the 0 → 1 step relative to T_pw + 10 s, and the number of "Setup task failed" lines.
  - A failed (d1)–(d3) is "a control fails", so the tier is Not confirmed (B1 amendment), as before.
- **Why an allowance and not a wait.**
  - The task's run time cannot be read from the node. It logs nothing when the role exists (`CassandraRoleManager.java:449-457`). A not-safe rerun is logged only at TRACE (`:491`), and each rerun moves the task by 10 s. A wait past it would need a margin with no source basis.
  - The number of workers the task can add is fixed by the source (item 4).
  - The allowance leaves B3e's timeline unchanged, so the re-run repeats run 1's procedure step for step.
- **What was known of run 1 when this was written, and would run 1 pass?**
  - All of run 1's results (results §4–§5) were known. That includes the idle readings: W 0 → 1 between the samples about 7 and 12 s after "Startup complete" in k16, k64 and X; W = 1 throughout in k128 and k256; S drift ≤ 2,072 KiB; and no log line naming the task (`run1/cluster/NOTE-idle-W.txt`). Run 1's raw `system.log` files were not opened for T_ar or T_pw before this was written.
  - Run 1's readings are a single 0 → 1 step, so they are expected to pass (d1) and (d3). (d2) was not evaluated in advance. The self-check's known-answer pass on run 1's raw files gives the answer (results §7.5).
  - The allowance of one worker comes from item 4, not from run 1's count. The 10,000 ms comes from `AuthKeyspace.java:69`.

Reason: run 1's frozen drift control did not allow for a worker that the source creates after start-up. The control is restated from the source, as the user authorised.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| NTR Active ≤ knob; W_max and NMT Thread rise with knob within predicted bands | Constraint caps thread count and thread memory (claim supported; estimate → positive for threads) |
| NTR Active > knob | Cap not enforced: claim wrong |
| W_max ≫ knob + Σ other caps | Threads not bounded by the knob: claim wrong |
| NMT Thread delta between 16 and 256 is < 1% of heap (≲ 20 MiB committed) | Bounded but not memory-significant, so the estimate should go to negative ("does not bound a memory-significant object") |
| `-Xss1m` control raises NMT Thread reserved about 4× per thread | Instrument sensitive (positive control moves) |
| `-Xss1m` control shows no change | Instrument useless; run not usable |
| W drops after the shrink | Threads reclaimed; contradicts A3(b) |
| NTR Active < knob at C = 400 | Demand did not reach the cap; not confirmed |

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B3g, rows by finding.** The filed rows stay and map as follows; rows marked + are added.

| Finding | Observation | Meaning |
|---|---|---|
| F1 | Every C400 sample has Active ≤ knob and R_ntr ≤ knob; steady median Active = knob, R_ntr ≥ knob − 4, Pending in band, at all four knobs; C8 ≤ 10; postshrink ≤ 16 | Running tasks capped, with queued excess as disallow evidence: **F1 supported** |
| F1 | Any sample with NTR Active > knob or R_ntr > knob (or > 16 after the shrink) | Cap not enforced: **F1 refuted** |
| F1 | Steady median Active < knob at C = 400, or client in-flight median < 390 | Demand did not reach the cap: **Not confirmed** |
| F2 | W_max in [knob, knob + 144], strictly increasing, ΔW ≥ 200; C8 W_max ≤ max(W_idle, 56) | Threads capped by the knob and created on demand: **F2 supported** (threads) |
| F2 | W_max > knob + 144 at any knob | Threads not bounded by the knob: **F2 refuted** |
| F2 + | ΔW < 200 or not increasing, with F1's limit reached | Threads do not follow the knob as derived: **F2 Not confirmed** |
| F2 + | C8 W_max > max(W_idle, 56) | Threads not created on demand: **F2 Not confirmed** |
| F2 | W after the shrink + 60 s ≥ W before | No reclamation: supports A3 (b) |
| F2 | W drops after the shrink | Threads reclaimed: **A3 (b) refuted** |
| F2 (memory) | ΔS/ΔT in [256, 320] KiB and ΔS ≥ 50 MiB, with control X's ratio in [3.0, 4.0] | Thread stack reservation follows the thread count, so it follows the knob: **F2 memory supported** |
| F2 (memory) + | Control X's ratio in [1.5, 3.0) or > 4.0, or ΔS/ΔT outside the band | **F2 memory Not confirmed** |
| F2 (memory) | Control X's ratio < 1.5 (no change) | Instrument useless: **Invalid run** for the memory part |
| F3 | Pending ≈ 400 − knob at every knob | The queue holds all excess demand: queue not capped by the knob (count; bytes tested in B2) |
| informational | ΔRSS(16→256) < 20.48 MiB | Bounded but not memory-significant: stage-3 note toward a negative estimate (filed row 4; read on RSS here, because NMT committed = reserved on this host) |

Tier verdict and Effect: as in the B1 amendment. Reason: group B; the caller asked that the conclusions keep "running tasks", "threads and stack memory" and "queued-task memory" apart, each with its controls.

**B3h. Controls.**
- C = 8 separates demand-driven thread creation from the knob.
- Fixed data, fixed client concurrency, and fixed other `concurrent_*` values.
- The idle sample gives the baseline thread count.
- The `-Xss` control validates NMT.
- The sep-thread-name property keeps the worker count by name exact.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B3h, controls as run.**
- **C8 before C400** on each fresh JVM: separates demand-driven thread creation from the knob.
- **Idle phase:** baseline and drift.
- **Control X (`-Xss1m`):** positive control of the NMT instrument.
- **Postshrink-C400:** the cap after a runtime change.
- **Fixed data, client and other `concurrent_*`.**
- **R_ntr from the thread dumps:** a running-task count that does not come from the permit counter.

Reason: B3e amendment.

**Amendment 2026-10-28 (after run 1, authorised by the user) — B3h, the idle control.** This amendment follows run 1's readings (see the B3f amendment of 2026-10-28). "Idle phase: baseline and drift" now means the restated drift control (d1)–(d3) of that amendment: the idle phase still gives the baseline (its last sample, as before), and it shows that, apart from the one ReadStage worker the default-role setup task can create (`CassandraRoleManager.java:485-504`, `:480`; `AbstractReadExecutor.java:165`; `SEPExecutor.java:196`, `:221-223`, `:135-142`; `SharedExecutorPool.java:108-116`), nothing in the idle node creates SharedPool workers or stack memory. The other controls are unchanged. Reason: B3f amendment of 2026-10-28.

**B4. Risks and cleanup.**
- Unit tier: build only in `/local/c509`, never in the shared clone; the tier uses no disk beyond the build.
- Cluster tier: all data under `/local/c509-data` (< 2 GiB).
- After each run, check `pgrep -f CassandraDaemon` and `pgrep -f cassandra-stress` and kill anything left over.
- At the end: `rm -rf /local/c509-data /local/c509` and remove any venv.
- Do not leave a JMX-modified node running.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B4, this host.**
- **Unit:** after r3, remove the test class and `build/test/cassandra` from `$W/cassandra-run29`, and check that `git status` shows no change to tracked files (the test yaml is never edited).
- **Cluster:** `cluster-run.sh` stops every node it starts, wipes `$W/node-sep` at the end, and checks that `ps -eo command | grep '[C]assandraDaemon'` and the stress search are empty. Full logs stay in `$W/logs/sep_maximum_pool_size-takeWorkPermit/`. No JMX-modified node is left: the shrunk node is stopped at the end of its start.

Reason: B4 named CloudLab paths.

**Amendment 2026-10-28 (after run 1, authorised by the user) — B4, paths of the cluster re-run.** This amendment follows run 1's readings (see the B3f amendment of 2026-10-28). The cluster re-run uses the clone `$W/cassandra-run72` and the node directory `$W/node-sep72`; `cluster-run.sh` wipes `$W/node-sep72` at the end, and the clone's `git status` must be clean afterwards. Logs: `$W/logs/sep_maximum_pool_size-takeWorkPermit/cluster-run2/` (shakedown `cluster-shake-run2/`). Everything else in B4 is unchanged. Reason: a fresh clone and node for the re-run.

## C. Sources read

- src/java/org/apache/cassandra/concurrent/SEPExecutor.java
- src/java/org/apache/cassandra/concurrent/SEPWorker.java
- src/java/org/apache/cassandra/concurrent/SharedExecutorPool.java
- src/java/org/apache/cassandra/concurrent/SEPExecutorMBean.java
- src/java/org/apache/cassandra/concurrent/Stage.java
- src/java/org/apache/cassandra/concurrent/ExecutorFactory.java
- src/java/org/apache/cassandra/transport/Dispatcher.java
- src/java/org/apache/cassandra/service/StorageService.java (setConcurrency)
- src/java/org/apache/cassandra/tools/nodetool/SetConcurrency.java
- src/java/org/apache/cassandra/config/Config.java, DatabaseDescriptor.java, CassandraRelevantProperties.java (excerpts)
- conf/cassandra.yaml, conf/jvm-server.options (excerpts)
- test/unit/org/apache/cassandra/concurrent/SEPExecutorTest.java
- CHANGES.txt (grep for SEP)
- https://issues.apache.org/jira/browse/CASSANDRA-16186 (cited, not fetched)

## D. Stage-4 feedback

**2026-10-26, stage 4 run 1 (Claude Opus 5.5, claude-opus-5-5), on the advisor's machine.** Results: [`stage4-runtime-verification/results/sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous.md`](../../stage4-runtime-verification/results/sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous.md). Uncommitted.

**Version history.** The file was frozen after nineteen audit amendments at sha256 `d5d2f122…3a25`. The unit tier ran at `f8eb812b…5605` (defect 1). The cluster tier ran at `b60d5475…7770` (defects 2 and 3 at `1ccbf2d4…`/`e9ce4c6c…`, then defect 4). No prediction, band or row changed.

**Verdicts.**
- **Unit: Confirmed — caps only on some paths (bypass).** maxRunning = min(N, M) and pending = M − N for N = 1…128, with running heap ≈ N MiB. Threads = N (8 at the demand-below-cap control). 64 threads were still alive 35 s after a shrink to 1. Queued payloads added 64.3–65.4 MiB at every N. Three identical runs.
- **Cluster: Not confirmed** by the tier mapping: the frozen idle drift control "W constant" failed by one thread in 3 of 5 starts, from an internal task about 10–12 s after start-up. Every F1/F2/F3 "supported" row holds:
  - Running NTR tasks (independent thread-dump count) = knob exactly at 16/64/128/256 and at 16 after a runtime shrink, with Pending = 400 − knob.
  - SharedPool workers 34/96/160/288 (knob + ReadStage + 2), 17 at C = 8 whatever the knob, and still 288 after the shrink.
  - NMT stack reservation +268 KiB per thread (+66.7 MiB from 16 to 256); `-Xss1m` control ratio 3.87.
  - RSS +20.8 MiB from 16 to 256 (informational, noisy).
- **Effect:** running tasks and worker threads (with their stack reservation) are capped and follow the knob; queued-task memory does not follow the knob (bypass through the unbounded queue).

**Runbook defects.**
1. The unit JVM logs each `System.out` write as a separate line, so `printf` split the readings.
2. `nodetool tpstats` takes 12–27 s under this load; the gauges are read through persistent JMX.
3. Process spawns cost 0.2–2 s under the saturated CPU; the diagnostic commands now run through the DiagnosticCommand MBean.
4. The driver's 30 s heartbeat queues behind the NTR backlog and times out; heartbeats are off.

**For stage 3.**
- (a) The yaml comment at `conf/cassandra.yaml:1033-1034` ("idle threads are stopped after 30 seconds") is wrong at this tag. Stopped workers park forever at `SEPWorker.java:116-118`, and both tiers observed threads kept well past 30 s.
- (b) The filed design missed four things:
  - the 12 s `native_transport_timeout` (it sheds a queued load);
  - that the thread count never falls within a JVM (so the C = 8 control must run first, and the populate needs its own start);
  - that NTR `Active` is the permit counter itself;
  - that `tpstats` has no MaxPoolSize column.
- (c) On macOS, NMT reports stack committed = reserved, so the filed "committed" proxy is unavailable. A Linux run would show touched stack pages.
- (d) Per added worker the node reserved 268 KiB of stack (about 115 KiB resident per parked thread in a probe). From knob 16 to 256 that is about 1–3% of a 2 GiB heap. The estimate stays as filed (`undetermined`).

**2026-10-28, stage 4 cluster re-run "run 1b" (Claude Opus 5.5, claude-opus-5-5), authorised by the user (Yang, the advisor).** Results: same file, §7 and §8. Uncommitted.

**Version history.** Four dated amendments `Amendment 2026-10-28 (after run 1, authorised by the user)` (B3a, B3f drift control, B3h, B4) gave sha256 `83890d4b…33f8` (new `_INDEX.md` §4 row). They restate the idle drift control from the source. The default-role setup task (`CassandraRoleManager.java:485-504`, 10,000 ms after `doAuthSetup`) makes one read (`:480`). `Stage.READ.maybeExecuteImmediately` queues it, because `takeWorkPermit` needs a queued task (`SEPExecutor.java:196`, `:221-223`), and `addTask` starts exactly one worker if none exists (`:135-142`, `SharedExecutorPool.java:108-116`). The control is now: (d1) W rises at most once, 0 → 1; (d2) not before T_ar + 10 s; (d3) S ≤ 4 MiB. The amendments were written knowing run 1's readings, and run 1's raw files pass them too (98/98). B1, the F rows, B3g and the unit tier are unchanged. An observe-only Byteman check in a separate start confirmed the creator's stack.

**Verdict (cluster re-run): Confirmed — caps only on some paths (bypass).**
- Running NTR tasks = knob exactly (16/64/128/256; 16 after the shrink), with Pending = 400 − knob.
- Workers 33/104/160/288, 17 at C = 8, still 288 after the shrink.
- NMT stack +268.0 KiB per thread (+67.0 MiB from 16 to 256); `-Xss1m` ratio 3.866.
- In all five starts, one idle worker appeared at the source-derived time.
- The self-check found 98 checks, 0 failed.

Run 1's cluster verdict (Not confirmed) stays on record.

**For stage 3.**
- (e) `SEPExecutor.maybeExecuteImmediately` never runs inline on an idle executor: `takeWorkPermit(false)` also requires a queued task (`SEPExecutor.java:196`).
- (f) An idle node creates one SharedPool worker about 10 s after start-up, from the default-role setup task. A design with an idle baseline of the SharedPool thread count must allow for it.
