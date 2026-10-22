# maxTasksQueued (SEPExecutor pending-task limit) — verification solution

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/concurrent/SEPExecutor.java:135` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI, 2026-10-22 |
| Estimate | `negative`. The line (`if (taskPermits == 0)`) is a thread-wake decision, not a cap. The only "queue limit" SEPExecutor knows is `getMaxTasksQueued()` = `Integer.MAX_VALUE`, and the queue is an unbounded `ConcurrentLinkedQueue`. |
| Ground | `addTask` never rejects or blocks; the "block after the fact if we breached the queue limit" comment (line 130) describes code that no longer exists. The queue of a SEP stage (MutationStage, ReadStage, ...) holds heap objects without any bound from this class. Heap held by it is bounded only indirectly by upstream admission limits (native-transport in-flight bytes, internode receive-queue reserve) and by the JVM heap. Pool size (`concurrent_reads/writes`) caps running threads, not queued tasks. |

## A. Constraint trace

**A1. The constraint.** The "maximum tasks queued" limit of a SEPExecutor: the constant
`SEPExecutor.getMaxTasksQueued()` returning `Integer.MAX_VALUE` (`SEPExecutor.java:102-106`),
exported as the JMX/metric `MaxTasksQueued` (`metrics/ThreadPoolMetrics.java:42,93,105`).
Kind: hard-coded constant (runtime-queried gauge). Historically declared as the `maxTasksQueued`
bound mentioned in the comment at `SEPExecutor.java:58` ("range [0..maxTasksQueued]") and
`:129-130`; no field by that name exists in 5.0.9. Unit: tasks. Default: `Integer.MAX_VALUE`
(2147483647), not derived. Not settable by yaml, `-D` or JMX. The related *settable* knobs are
different things: the work-permit count `maximumPoolSize` (yaml `concurrent_reads`,
`concurrent_writes`, `concurrent_counter_writes`, `concurrent_materialized_view_writes`; bound
in `concurrent/Stage.java:45-48`; changed live via `setMaximumPoolSize`, `SEPExecutor.java:368-396`).

**A2. What it caps.** Intended: number of queued (not yet started) tasks, hence heap held by
queued `Runnable`s and whatever they capture (mutations, read commands, message payloads). The
quantity compared: the low 32 bits of `permits` (`taskPermits`, `:398-401`), which counts
`tasks` entries. Resource: heap.

**A3. Mechanism.** `addTask` (`:119-145`): (1) `tasks.add(task)` onto an unbounded
`ConcurrentLinkedQueue` (`:68,123`); (2) CAS loop increments the task-permit half of `permits`
by one with no comparison against any limit (`:125-133`); (3) line 135 `if (taskPermits == 0)`
tests the *previous* count: if the queue was empty, call `pool.maybeStartSpinningWorker()`
(`:142`) to wake a worker; otherwise do nothing, because an earlier enqueue already started a
worker. Both outcomes return the task (`:144`); neither rejects, blocks or sheds. Bypass/overshoot:
the limit is absent. The only wrap is int overflow of the 32-bit field at 2^31 queued tasks
(unreachable before heap exhaustion; adding past it would corrupt the work-permit half through
the carry). `maybeExecuteImmediately` (`:217-240`) runs inline when a work permit is free, else
calls `addTask`. `takeTaskPermit` (`:156-185`) decrements on dequeue; `shutdownNow` drains (`:310-317`).

**A4. Other consumers.** Same heap: memtables, key/chunk/row caches, off-heap-buffer
metadata, inbound messaging buffers, native-transport request frames (limited by
`native_transport_max_request_data_in_flight[_per_ip]`, `Config.java:296-298`, and
`internode_application_receive_queue_reserve_global_capacity`, `conf/cassandra.yaml:1388-1391`).
Those admission limits are what indirectly bound the queue in practice; they are outside this
constraint. Other (non-SEP) stage executors (`Stage.java:221-227` `pooled`) are different classes
and not covered.

**A5. Evidence beyond the source.** none (design from source only; no web lookups).

## B. Verification solution

**B1. Claim under test.** (Negative.) A SEPExecutor accepts and holds an arbitrary number of
queued tasks: `PendingTasks` rises 1:1 with submissions far beyond any plausible limit with no
rejection or blocking at `addTask`, `MaxTasksQueued` stays 2147483647, and the heap held by the
queue grows linearly with the queued count, independent of the executor's pool-size knob; heap
growth is stopped only by an upstream limit or the JVM heap, not by the executor.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Clone the tag to local disk (never build in the
shared clone): `git clone --branch cassandra-5.0.9 --depth 1 /proj/misconfiguration-PG0/git-repos/cassandra-src /tmp/c509`,
`cd /tmp/c509 && ant jar` (and `ant build-test` for a JUnit variant). Harness: a small `main`
(`SepQueueProbe`) compiled against `build/classes/main` + `lib/*.jar` + `build/lib/jars/*.jar`,
placed outside the clone (`/tmp/probe`). It must set `DatabaseDescriptor.daemonInitialization()`
or only use `SharedExecutorPool` directly (needs `NamedThreadFactory`, `MBeanWrapper`; run with
`-Dcassandra.jmx.local.port` unset and `-Dcassandra.mbean_wrapper` default). JVM:
`-Xms2g -Xmx2g -XX:+UseG1GC -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/tmp/probe/hd`.

**B2b. Knobs.** (i) Submitted task count N in {10^4, 10^5, 10^6, 4x10^6}. (ii) Payload per task
P in {64 B, 1 KiB} (byte[] captured in the Runnable). (iii) Executor `maxConcurrency`
(`SharedExecutorPool.SHARED.newExecutor(c, jmxPath, name)`, `SharedExecutorPool.java:141`) c in
{1, 8}, to show the permit count does not bound the queue. Set in the probe's code/args.

**B2c. Workload.** Create executor with c workers; submit first c tasks that block on a
`CountDownLatch` (so all work permits are held), then submit N further tasks, each
`() -> { sink(payload); }` with a distinct `new byte[P]`. Arithmetic: N=10^6, P=1 KiB gives about
1.0 GB payload plus roughly 100 B/task of `FutureTask` wrapper and queue node (estimate, to be
read from the histogram), so N=10^6 fits in 2 GB but N=4x10^6, P=1 KiB must hit OOM: that
demonstrates heap, not the executor, is the only stop. Use P=64 B for the 4x10^6 run to
reach it without OOM (about 0.7 GB).

**B2d. Observables and instruments.** Per step: `executor.getPendingTaskCount()`,
`getMaxTasksQueued()`, `getActiveTaskCount()`; whether `execute/submit` threw or blocked (wall time
per 10^5 submits via `System.nanoTime`); heap held: `System.gc()` x2 then
`Runtime.totalMemory()-freeMemory()`, and `jcmd <pid> GC.class_histogram` rows for
`ConcurrentLinkedQueue$Node`, `[B`, `FutureTask`/`SEPExecutor` task wrappers. Cannot be seen
directly: queued bytes per class without a histogram.

**B2e. Procedure.** (1) build jar, compile probe. (2) For each c, P, N: start fresh JVM, create
executor, block c workers, submit N, record pending, max, time; histogram+used heap after gc;
release latch; confirm pending falls to 0 and heap returns to baseline. (3) Positive control run
(B2h). (4) Remove `/tmp/probe`, `/tmp/c509`.

**B2f. Predictions (before any run).** `getPendingTaskCount() == N` exactly for every N (no
rejection, no blocking; submit time per 10^5 roughly flat); `getMaxTasksQueued() == 2147483647`
always; retained heap rises about linearly with N*(P+k) with k a constant of order 100 B, same
slope for c=1 and c=8; N=4x10^6 with P=1 KiB OOMs rather than being refused.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| pending == N for all N, no exception/blocking, heap linear in N, same for c=1 and 8; control rejects at its capacity | Claim confirmed: queue not capped by the executor |
| pending plateaus below N, or submit throws/blocks at some count | Claim refuted: a hidden bound exists; locate it |
| heap flat as N grows while pending grows | Tasks not retaining payload (probe bug); not confirmed |
| heap grows with c at fixed N | Pool size influences usage; refutes independence |
| Control executor never rejects, or pending in SEP never reached N (workers drained) | Not confirmed (limit never reached/control did not move) |

**B2h. Controls.** Positive control: a JDK `ThreadPoolExecutor(c,c,0,ms,new ArrayBlockingQueue<>(1000), AbortPolicy)` with the same latch/N/P workload: queue length plateaus at 1000 with `RejectedExecutionException`, retained heap flat beyond 1000. Also a baseline JVM with no tasks (heap before), and the latch-release run showing memory is released when workers drain (so growth is the queue, not a leak).

### B3. Cluster tier

**B3a. Environment and build.** One node (RF=1) on local disk of known size (>= 20 GB free;
data, commitlog, hints, saved_caches under `/tmp/c509run/*`). Build from the local clone as in
B2a (`ant jar`). `cassandra.yaml`: `concurrent_writes: 1`, `concurrent_reads: 1` (in the
pool-size dimension), `commitlog_sync: periodic`, `native_transport_max_request_data_in_flight`
set per B3b, `native_transport_max_threads: 128` (default). JVM: `-Xms1g -Xmx1g`,
`-XX:+UseG1GC`, JMX local. Client load from a second process (cassandra-stress built from the same
clone, `tools/bin/cassandra-stress`).

**B3b. Knobs.** (i) `native_transport_max_request_data_in_flight`: 32MiB vs 256MiB (and default
10% heap) — the known upstream admission cap, positive control for "a bound that does bind".
(ii) `concurrent_writes`: 1 vs 8 (pool size, via yaml or live JMX `setMaximumPoolSize` /
`nodetool setconcurrency mutation 1`). (iii) payload value size: 64 KiB blobs. Set via yaml and
node restart; concurrency live.

**B3c. Workload.** Table with a `blob` column; `cassandra-stress user` or `write n=...` with
`-col size=FIXED(65536) -rate threads=256`, CL=ONE, to a single node. 256 threads x 64 KiB = 16
MiB in flight, below the 32MiB cap; use `threads=1024` (64 MiB) to cross a 32MiB cap and stay
under 256MiB. To make MutationStage the bottleneck, 1 writer thread with `commitlog_sync_period`
default and large values (disk-bound memtable/commitlog) should be slower than 128 native
threads' arrivals; this is the reason for `concurrent_writes: 1`. Duration 5 minutes per
configuration, 1 minute warm-up.

**B3d. Observables and instruments.** JMX/`nodetool tpstats` (`MutationStage` Pending and
Active), JMX MBean `org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name=PendingTasks`
and `MaxTasksQueued`; heap via `jstat -gc <pid> 2000` and old-gen occupancy after
`jcmd <pid> GC.run`; `jcmd <pid> GC.class_histogram` for `FutureTask`/`Mutation`/`ByteBuffer`
retention; RSS for off-heap. Cannot see per-task bytes without the histogram.

**B3e. Procedure.** (1) Build, create dirs. (2) Start node with config A (in-flight 256MiB,
writers 1); create keyspace RF=1 and table. (3) Run stress 1 min warm-up then 5 min; sample
tpstats and jstat every 2 s; take histogram at end of window. (4) Repeat with in-flight 32MiB.
(5) Repeat with writers 8. (6) Repeat with the load deliberately above the in-flight cap to confirm
the admission limit throttles (overload/backpressure). (7) Stop stress and node (`nodetool drain`
then `kill`), `pgrep -f cassandra` clean, delete `/tmp/c509run`.

**B3f. Predictions.** `MaxTasksQueued` reads 2147483647 for the stage throughout. Peak
`MutationStage` pending tracks the upstream cap, not a stage limit: with 32MiB in-flight, queued
bytes at most about 32 MiB / 64 KiB = 512 requests plus a few; with 256MiB, up to about 4096.
Pool size 1 vs 8 changes pending depth (drain rate) but not the maximum permitted queued bytes
(set by in-flight). No `Dropped`/rejection counters from the executor. Heap (old gen) rises
with queued payload and plateaus near the in-flight cap size.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Peak pending scales with in-flight cap (about 8x from 32 to 256 MiB), flat vs a stage-level setting; MaxTasksQueued constant | Claim confirmed (usage follows upstream limit, not the executor's) |
| Pending hits the same plateau regardless of in-flight cap | Refuted: some other bound; find it |
| Pending never grows (workers keep up) in all configs | Not confirmed (limit never reached); increase value size or reduce writers |
| Heap follows `concurrent_writes` at fixed in-flight | Refuted: pool size affects queued memory |
| Positive control: heap/pending moves with in-flight cap while the stage setting does not | Required for confirmation; absent means not confirmed |

**B3h. Controls.** Same stress, in-flight cap varied, executor unchanged (control for
upstream bound); `concurrent_writes` varied, cap unchanged (isolates pool size); compare against
a baseline idle node; `-Xmx` fixed and G1 settled before sampling; ensure no flush or compaction
pressure confounds old-gen readings (record memtable size via `nodetool tablestats`).

**B4. Risks and cleanup.** Unit tier can OOM the probe JVM only (heap dumps to `/tmp/probe/hd`,
delete after). Cluster tier writes tens of GB at most: cap with stress `n=` and local disk quota;
no shared storage. Stop stress, node, and probe JVMs; verify with `pgrep -fl "CassandraDaemon|SepQueueProbe|cassandra-stress"`;
remove `/tmp/c509`, `/tmp/c509run`, `/tmp/probe`.

### Stage-4 audit amendments (2026-10-22, before any reading; stage-4 agent on pc07)

Each amendment is for a reason that does not depend on any reading (source arithmetic or environment). B1, B2f, B3f and every
row of B2g/B3g above stay as filed; the rows added below only cover outcomes the filed table left without a row.

**Environment (E).** E1: clone `~/cassandra-mta` (a fresh clone of the tag, `ant build-test`) replaces `/tmp/c509`; the probe
lives in `~/stage4-mta/probe` (outside the clone), node data in `~/stage4-mta/node1`, logs in `~/stage4-logs/mta/`. E2: the
node uses 127.0.0.4 (listen, rpc, seed), JMX 7204 (Byteman port 9094 is not used); the host is shared with another stage-4
session. E3: no heap dump on OOM (the 2 GiB dump files are not worth the disk); the probe catches the `OutOfMemoryError` and
prints the counts.

**Unit tier (B2).**
- U1 (matrix). 16 fresh JVMs: c in {1, 8} x P in {64, 1024} x N in {10^4, 10^5, 10^6, 4x10^6}, `-Xms2g -Xmx2g -XX:+UseG1GC
  -Xlog:gc`; the probe is a `main` class (package `org.apache.cassandra.concurrent`, which `SharedExecutorPool` needs) with the
  classes of the clone on the classpath. Controls: B2h's `ThreadPoolExecutor` (ArrayBlockingQueue(1000), AbortPolicy) with
  c in {1, 8}, P = 1024, N = 10^6, and a baseline JVM.
- U2 (workload exactness). N counts the tasks submitted after the c blockers; the probe waits for `getActiveTaskCount() == c`
  before the N submissions. Expected pending is then exactly N (the blockers hold the permits).
- U3 (statistics, fixed before the first reading). live = heap used after 3 x `System.gc()` with 300 ms sleeps, minus the same
  taken after the executor and its c blockers exist and before the N submissions. bytes/task = live / N; k = bytes/task - P.
  "Linear in N" = bytes/task for N in {10^5, 10^6, 4x10^6} within +-10 % of their mean for each (c, P) (10^4 is a warm-up
  point, reported but excluded). "Same slope for c = 1 and 8" = bytes/task of c = 1 over c = 8 in [0.9, 1.1] at each (P, N).
  "k of order 100 B" = 20 <= k <= 300. "No blocking" = every block of 10^5 submits took < 5 s of wall time.
- U4 (OOM arm). P = 1024, N = 4x10^6 is expected to exhaust a 2 GiB heap (4.3 GB of payload). The probe stops submitting at the
  first `OutOfMemoryError` and prints the submitted count s, `getPendingTaskCount()`, whether any `RejectedExecutionException`
  was thrown, and the longest block time. Added B2g rows (they follow the existing ones):

| Observation | Meaning |
|---|---|
| (U-a) the OOM arm throws `OutOfMemoryError` to the submitter, pending == s (+-0 after the failing call is excluded, the failing submit may or may not have been counted: pending in {s, s+1}), no `RejectedExecutionException`, no block >= 5 s | Claim confirmed: heap, not the executor, is the only stop |
| (U-b) the OOM arm completes all 4x10^6 submits | Not confirmed (the heap limit was not reached) |
| (U-c) `RejectedExecutionException` or pending < s at any N | Claim refuted: a hidden bound |
| (U-d) after the latch is released pending reaches 0 within 120 s and live heap is back within baseline + 64 MiB (non-OOM arms) | Growth was the queue, not a leak (B2h) |

**Cluster tier (B3).**
- C1 (heap). `-Xms2g -Xmx2g` replaces `-Xms1g -Xmx1g`: 256 MiB of admitted 64 KiB requests held as `Mutation` plus a cached
  serialized copy (`Mutation.java:440-460`, below the 8 MiB cacheable limit) is about 2 x 256 MiB of heap, plus a memtable, which
  does not fit in 1 GiB.
- C2 (admission settings). In every arm `native_transport_max_request_data_in_flight_per_ip` is set equal to
  `native_transport_max_request_data_in_flight` (the per-IP default is heap/40 = 51 MiB, `DatabaseDescriptor.java:654-656`,
  and all stress traffic comes from one IP, so it would bind before the 256 MiB global cap), and
  `native_transport_receive_queue_capacity: 0B` (a connection spends its own 1 MiB receive queue before the per-IP/global
  reserves, `Config.java:302`, so with the default `RequestsSize` would not see the load).
- C3 (client capacity). B3c's `threads=1024` offers at most 64 MiB, below the 256 MiB cap, so the 8x contrast could not
  appear. Every arm uses `threads=6000` (6000 x 64 KiB = 375 MiB offered, above both caps), `-mode native cql3
  connectionsPerHost=16 maxPending=1024` (stress defaults are 8 connections x 128 pending, `SettingsMode.java:138-139`, which
  would cap the load at 64 MiB), `no-warmup`, `cl=ONE`, `-col 'n=FIXED(1)' 'size=FIXED(65536)'` (quoted for the shell).
- C4 (arms). Four fresh node lifetimes, each after `TRUNCATE` + `clearsnapshot` of the previous: A = in-flight 256 MiB,
  concurrent_writes 1; B = 32 MiB, 1; C = 256 MiB, 8; D = 32 MiB, 8. Stress runs 150 s per arm; the measurement window is
  t = 30 s to 150 s of the stress run (replaces "5 minutes + 1 minute warm-up"). `nodetool setconcurrency` is not used; the pool size is the yaml value, read
  back with `nodetool getconcurrency MutationStage`. B3e step 6 (load above the cap) is satisfied by C3 in every arm.
- C5 (statistics, fixed before the first reading). P(arm) = maximum over 1-s JMX samples in the window of the MutationStage
  `PendingTasks` gauge. RS(arm) = maximum `RequestsSize` (`type=Client,name=RequestsSize`) in the window. HQ(arm) = median over
  the 15-s samples in the window of (heap used after `jcmd GC.run` minus the memtable data size from `nodetool tablestats`).
  MTQ = the `MaxTasksQueued` gauge, read at the start and the end of each arm. Guard: if a post-GC heap sample exceeds 1.8 GiB
  the stress is stopped, which is recorded (heap, not the stage, is the stop).
- C6 (definitions of the filed rows). "Peak pending scales with the in-flight cap (about 8x)" = 4 <= P(A)/P(B) <= 12 and
  4 <= P(C)/P(D) <= 12. "Flat vs a stage-level setting" = RS reaches at least 80 % of its cap and does not exceed cap + 1 MiB
  in all four arms (the admission limit, not concurrent_writes, sets the ceiling of what is admitted; B3f says the pool size may
  change the pending depth). "Never grows" = P < 20 in all four arms. "Heap follows concurrent_writes" = HQ(w = 8) >= 1.3 x
  HQ(w = 1) at both caps. "Same plateau regardless of cap" = P(A)/P(B) < 2 and P(C)/P(D) < 2. The positive control is the A-vs-B
  (and C-vs-D) contrast of RS and P with MTQ unchanged.
- C7 (added B3g row, an outcome the filed table has no row for: a queued mutation outlives its admission charge, because the
  client's request is answered, and its bytes released, at the 2000 ms write timeout, `Config.java:150-151`, while the task stays
  queued):

| Observation | Meaning |
|---|---|
| (C-a) MTQ = 2147483647 in all arms, RS <= cap + 1 MiB, but P(arm) x 65536 > 1.25 x cap in at least one arm | Executor claim confirmed (nothing rejected or capped at `addTask`); the sub-prediction "queued bytes at most about cap / 64 KiB" missed, so the admission cap does not bound the queue |


**Runbook fix D1 (2026-10-22, cluster instrument check, before any cluster reading; B1, B3f and every B3g row unchanged).**
The node refuses `concurrent_writes: 1` at start ("concurrent_writes must be at least 2"), so arms A and B cannot be set
through the yaml. B3b already allows the live path: the yaml carries `concurrent_writes: 2` and `nodetool setconcurrency
MutationStage 1` is run before the stress starts (`SetConcurrency.java:42-52`, `StorageService.java:2397-2403`), read back with
`nodetool getconcurrency MutationStage` (must read 1). Arms C and D use the yaml value 8.

## C. Sources read

- /proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/playbook-autonomous.md
- /proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/_TEMPLATE-autonomous.md
- cassandra-src/src/java/org/apache/cassandra/concurrent/SEPExecutor.java
- cassandra-src/src/java/org/apache/cassandra/concurrent/Stage.java (lines 40-70, 215-240)
- cassandra-src/src/java/org/apache/cassandra/concurrent/ExecutorFactory.java (225-260)
- cassandra-src/src/java/org/apache/cassandra/concurrent/SharedExecutorPool.java (grep)
- cassandra-src/src/java/org/apache/cassandra/metrics/ThreadPoolMetrics.java (grep)
- cassandra-src/src/java/org/apache/cassandra/config/Config.java (grep)
- cassandra-src/conf/cassandra.yaml (grep)

## D. Stage-4 feedback

2026-10-22, run 1 (pc07, shared host), results in `stage4-runtime-verification/results/maxTasksQueued-addTask-taskPermits--autonomous.md`; case file untracked, frozen sha256 `e8ac528c…` (audit amendments E1-E3, U1-U4, C1-C7 above), cluster tier ran on `5b27ef30…` (runbook fix D1).

- **Unit: Confirmed - does not cap** (B2g row 1 with the added row U-a; U-a's "no block >= 5 s" clause missed). `getMaxTasksQueued()` 2147483647 in all 16 JVMs; pending == N exactly to 4,000,000 tasks (P = 64) and, at P = 1 KiB, until the 2 GiB heap ran out at 1.91 M tasks (rejected 0); heap 88 B + P per queued task, identical for c = 1 and 8; the bounded `ArrayBlockingQueue(1000)` control rejected 999,000 of 1e6. The OOM arms' 15-19 s blocks coincide with 28-30 s of G1 pauses.
- **Cluster: Not confirmed (no matching row) - undetermined.** `MaxTasksQueued` constant, `Active` = pool size, nothing refused by the executor. `RequestsSize` followed the in-flight cap exactly (255.98 / 31.97 MiB) but peak `PendingTasks` did not: 383 / 383 (w = 1) and 1289 / 376 (w = 8) at 256 / 32 MiB, i.e. P(A)/P(B) = 1.00, P(C)/P(D) = 3.43, queued bytes 0.09-0.75 of the cap. The filed B3f ("about 512 / 4096 requests, 8x") was not met; none of B3g's rows (as defined in C6) nor C-a fits, so no verdict. Heap net of the memtable was 0.9-1.1 GiB in every arm, including the 32 MiB cap.
- **For stage 3:** (1) the queue depth in the 1 w arms moves in steps of 127 / 255 / 383 (multiples of 128 = `native_transport_max_threads` minus one), which suggests the request-thread pool, not the in-flight bytes, sets the depth on this path (inferred; vary `native_transport_max_threads` and take a class histogram to settle it); (2) B3c's `threads=1024` could not reach the 256 MiB cap (fixed by C3), the per-IP default and the per-connection queue bind first (C2), and the yaml refuses `concurrent_writes: 1` (D1); (3) a peak statistic is fragile (C's single 1289 sample, medians 127 / 127 / 120 / 120) - a median or a percentile would have matched the "same plateau" row; (4) `A3`'s line-135 description is correct (verified); the `maybeExecuteImmediately` caller-runs path was not exercised here.
