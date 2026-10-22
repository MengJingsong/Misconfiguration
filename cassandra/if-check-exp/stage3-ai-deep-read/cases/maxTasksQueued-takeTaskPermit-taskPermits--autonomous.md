# SEPExecutor max queued tasks (getMaxTasksQueued = Integer.MAX_VALUE) — verification solution

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/concurrent/SEPExecutor.java:175` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI (Agent SDK), 2026-10-22 |
| Estimate | `negative`. Line 175 is only an emptiness test (`taskPermits == 0`). The one "queue limit" tied to this counter, `getMaxTasksQueued()`, is the constant `Integer.MAX_VALUE` and is never enforced. The task queue is an unbounded `ConcurrentLinkedQueue` of heap objects. |
| Ground | The queued-task counter is the low 32 bits of an `AtomicLong` and is incremented without any limit check (`addTask`, line 131). The comment "range [0..maxTasksQueued]" (line 58) is only documentation. Nothing rejects, blocks or sheds. The only practical bounds on queue memory are upstream and separate: the native-transport in-flight byte limits, `max_mutation_size`, internode/messaging limits and the heap. |

## A. Constraint trace

**A1. The constraint.** Name: maximum queued tasks of a `SEPExecutor`, i.e. `SEPExecutor.getMaxTasksQueued()`. Kind: hard-coded constant (not configurable), exposed as a metric through `ThreadPoolMetrics` (`metrics/ThreadPoolMetrics.java:93`, `maxTasksQueued = executor::getMaxTasksQueued`). Declared at `concurrent/SEPExecutor.java:102-106`, returning `Integer.MAX_VALUE`. Unit: tasks. Default and only value: 2^31-1. It cannot be set by yaml, `-D` or JMX; a change needs a source edit and restart. The related *configurable* limit, `maximumPoolSize` (`SEPExecutor.java:50,369`, set from `concurrent_reads` / `concurrent_writes` etc. via `Stage.java:46-48` and `Config.java:179-180`), caps concurrent workers, not queue length.

**A2. What it caps.** Nominally the number of queued-but-not-started tasks (heap: the `Runnable`/`FutureTask` wrappers plus whatever they capture, e.g. mutations or read commands). The quantity compared at line 175 is `taskPermits(current)`, the queued-task counter, compared to 0, not to any maximum.

**A3. Mechanism.**
- `permits` packs work permits (high 32 bits) and queued-task permits (low 32 bits) (`SEPExecutor.java:57-60`, `398-421`).
- `addTask` (`:119-145`) does `tasks.add(task)` into an unbounded `ConcurrentLinkedQueue` (`:68`), then CAS-increments the task permits (`:131`). The comment at `:129-130` says "we always add our permit, but block after the fact if we breached the queue limit", but no such blocking code exists in 5.0.9. There is no comparison with `getMaxTasksQueued()` anywhere in the file (grep: only the definition).
- `takeTaskPermit` (`:156-185`), the target. If work permits are negative (pool shrinking) and the flag is set, return a work permit (`:165-172`). Otherwise at `:175` `taskPermits == 0` returns `NONE_AVAILABLE` (the worker finds nothing to do); else it decrements and returns `TOOK_PERMIT`. The check guards against underflow, not overflow.
- Bypass/overshoot: the queue can only be bounded by int overflow of the low 32 bits (2^31 tasks), which would corrupt the packed word (`updateTaskPermits` ORs the int unmasked; a negative value would also sign-pollute the high bits). That count is far beyond any heap.
- `maybeExecuteImmediately` (`:218-240`) bypasses the queue when a work permit is free.

**A4. Other consumers.** Heap used by queued tasks competes with memtables, caches, and netty direct buffers. Admission of bytes into the request path is governed elsewhere: `native_transport_max_request_data_in_flight` (default heap/10, `DatabaseDescriptor.java:649-651`) and `..._per_ip` (heap/40, `:654-656`), `native_transport_max_requests_per_second` (`Config.java:300`), `max_mutation_size` (`Config.java:406-407`). These bound payload bytes held by in-flight requests, which include requests sitting in the executor queue.

**A5. Evidence beyond the source.** none (source only; no docs relied on).

## B. Verification solution

**B1. Claim under test.** A `SEPExecutor` does not bound its queue: with all workers blocked, it accepts tasks far beyond any count cap (the counter reaches arbitrary N, no rejection or blocking), and the heap held by the queue grows linearly with N. On a real node, the pending-task count of a request stage (e.g. MutationStage) is not limited by `getMaxTasksQueued`; what limits queued memory there is the upstream in-flight byte limit, not the executor.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Clone the tag to local disk (`git clone --branch cassandra-5.0.9 <local clone> /local/scratch/c509`), never build in the shared clone. `ant jar` (or `ant build-test`). Small program or JUnit test in the local clone's `test/unit/org/apache/cassandra/concurrent/` (local copy only), e.g. `SEPQueueBoundProbe`. JVM options: `-Xmx2g -Xms2g -XX:+UseG1GC -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/local/scratch/dumps`. Run with the build classpath (`build/classes/main`, `build/lib/jars/*`).

**B2b. Knobs.** (1) Task count N: 10^4, 10^5, 10^6, 4x10^6. Chosen to span orders of magnitude, all far below 2^31, so any enforced cap at a smaller value would show. (2) Per-task payload P (bytes captured by the lambda): 0 (empty) and 1024. Distinguishes per-task overhead from payload. (3) Executor `maxConcurrency` = 1. Set in code via `new SharedExecutorPool("probe").newExecutor(1, "internal", "probe")` (`SharedExecutorPool.java:146`).

**B2c. Workload.** Submit one blocking task (waits on a `CountDownLatch`) so the single work permit is held. Then call `execute()` N times with `() -> { blackhole(payload); }`, each with its own `new byte[P]`. Arithmetic: N=4x10^6, P=1024 gives about 4.1 GB of payload, which exceeds the 2 GB heap, so it should reach OOM before any 2^31 limit; run N=10^6, P=1024 (about 1 GB payload plus roughly 100-200 B/task overhead) as the largest "clean" point.

**B2d. Observables and instruments.** `executor.getPendingTaskCount()` (`SEPExecutor.java:336`) after each batch; `getMaxTasksQueued()`; whether `execute` throws or blocks (wall time per batch); used heap after `System.gc()` via `MemoryMXBean` (and `jcmd <pid> GC.class_histogram` for `ConcurrentLinkedQueue$Node` and `byte[]` counts). Not directly observable: the packed `permits` word (private; infer from the counter).

**B2e. Procedure.**
1. Build (`ant jar`) in the local clone.
2. Start the probe JVM; create the executor; submit the blocker.
3. For N in {10^4, 10^5, 10^6}: submit N tasks, record pending count, call time and post-GC used heap; do not release the latch until the end.
4. Record `jcmd GC.class_histogram`.
5. Release the latch; confirm the pending count drains to 0 and `completedTaskCount` equals total.
6. Repeat for P=0 and P=1024. Repeat the whole series with the positive control (B2h).
7. Exit; verify no leftover java process (`pgrep -f SEPQueueBoundProbe`).

**B2f. Predictions.** Pending count equals N exactly at every point; no exception, no blocking (per-call time flat, microseconds); `getMaxTasksQueued()` is always 2147483647. Used heap rises linearly with N: slope is about P + (roughly 100-200 B) per task, so P=0 and P=1024 differ by about 1 KiB per task. The control (bounded queue) stops at its capacity.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Pending == N for all N, no rejection, heap slope about per-task size | Claim confirmed: queue unbounded, usage follows the workload, not any cap |
| `execute` throws/blocks/drops at some N below 10^6 | Claim refuted: a bound exists (find where) |
| Heap flat while N grows | Tasks not retained (re-check the payload and latch setup); not confirmed |
| Heap grows in the executor run but the control (bounded queue) is flat after its capacity | Claim confirmed, the control proves the harness can see a cap |
| Control queue does not stop at its capacity | Harness invalid; not confirmed |
| Pending count != N (e.g. wraps/negative) | A packed-word problem, a different finding |

**B2h. Controls.** Positive control: the same loop against a `ThreadPoolExecutor(1,1,0,ms, new ArrayBlockingQueue<>(10000), AbortPolicy)` with the same blocker and payload; it should reject after 10,000 queued tasks and its retained heap should plateau. Also record baseline heap before submission, and run the GC before each reading.

### B3. Cluster tier

**B3a. Environment and build.** One node (second optional). Build from the local clone (`ant jar`; run from the build dir, never from the shared clone). JVM: `-Xms1g -Xmx1g` (edit `conf/jvm11-server.options` in the local copy), G1, GC logging to local disk. Data, commitlog, hints, saved caches all in `/local/scratch/node1/...` (known size, at least 20 GB free). Single node, `num_tokens: 1`, RF=1, `commitlog_sync: periodic`. Client: `cassandra-stress` built from the same tree, or a Python driver script, run from another directory.

**B3b. Knobs.** (1) `concurrent_writes` (MutationStage pool size): 2 (small, so workers are the bottleneck; minimum allowed value per config validation is 2). (2) `native_transport_max_request_data_in_flight`: run A = 512MiB (large, below the heap-derived maximum so the executor queue is the only practical limit), run B = 16MiB (positive control). `native_transport_max_request_data_in_flight_per_ip` set equal. `native_transport_max_message_size` must not exceed them (`DatabaseDescriptor.java:911-915`); keep at the default or lower. (3) Optional: `native_transport_max_requests_per_second` left at default 1,000,000. All set in `cassandra.yaml` before start (restart per run).

**B3c. Workload.** To make MutationStage back up: write 32 KiB blobs (well under `max_mutation_size`, default commitlog_segment/2) from 512 concurrent async streams (`cassandra-stress user` or `write n=2000000 -col size=FIXED(32768) -rate threads=512`), with an artificial slowdown to keep workers saturated: use many partitions with `commitlog_sync: batch` and `commitlog_sync_batch_window_in_ms: 2` on local disk if needed, or briefly stall the stage via an `nodetool disableautocompaction` plus `flush` storm. Arithmetic: 512 streams x 32 KiB = 16 MiB in flight at most per round trip, so run B's 16 MiB limit binds immediately, while run A's 512 MiB limit lets queue depth grow until the client can't push more (needs enough streams: raise to 2000 threads, giving 64 MiB, still below A's limit). Duration: 10 minutes per run after a 2-minute warmup.

**B3d. Observables and instruments.** MutationStage `PendingTasks` and `MaxTasksQueued` (JMX `org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name=PendingTasks`; `nodetool tpstats` every 5 s); `nodetool info` heap; `jstat -gc <pid> 5000`; GC logs for post-GC live heap; `jcmd <pid> GC.class_histogram` at peak (`ConcurrentLinkedQueue$Node`, `byte[]`); `ClientRequest` rejections / `OverloadedException` counts (`nodetool clientstats`, metric `Client.RequestsDiscarded` / paused-connection logs). Not observable: the packed permit word; per-task size inside the queue (inferred from the histogram).

**B3e. Procedure.**
1. Build and configure in `/local/scratch`; verify heap and directories.
2. Run A: start the node, wait for up; start the sampler (tpstats loop, jstat); run the stress workload for 12 min; at peak take the class histogram; stop the client; stop the node (`nodetool drain`, then kill); archive logs.
3. Wipe the data dirs; run B (16 MiB limit) with the identical workload.
4. Optional run C: A's config with `concurrent_writes` = 8 to show pool size changes drain rate, not the bound.
5. Verify no cassandra/stress process remains (`pgrep -f CassandraDaemon`, `pgrep -f stress`); delete `/local/scratch/node1`.

**B3f. Predictions.** `MaxTasksQueued` reads 2147483647 in all runs. Run A: MutationStage pending count is limited only by in-flight bytes, i.e. pending x about 32 KiB is at most about 512 MiB; with the offered load (64 MiB in flight) pending climbs to the load-generator limit (hundreds to thousands) and is not clipped at any executor value. Live heap tracks pending x (payload + overhead), growing with offered in-flight bytes. Run B: pending x 32 KiB is at most 16 MiB, so pending plateaus at about 500 (16 MiB / 32 KiB), heap plateau is lower than A, and the client sees paused/overloaded behaviour from the transport layer, not the executor. If run A's heap and pending rise with offered load while `MaxTasksQueued` stays constant, the executor does not cap them.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Run A pending/heap rise with offered load, unclipped; `MaxTasksQueued` constant 2^31-1 | Claim confirmed |
| Run B (in-flight 16 MiB) pending/heap plateau at a lower level than A under identical workload | Positive control moved usage where a cap binds; confirms harness sensitivity |
| Pending plateaus in A at a round number independent of in-flight limit | Claim refuted: some executor-level bound exists |
| Pending never exceeds a few in A and B | Limit not reached (workers keep up); not confirmed, increase load / slow the stage |
| Run B does not differ from A | Control did not move; not confirmed (in-flight limit not reached, check the byte arithmetic) |
| OOM in A | Consistent with unbounded queue (heap dump shows queue nodes) but note the cause |

**B3h. Controls.** Same workload, same heap, same data layout across runs; only the in-flight limit changes between A and B. Baseline idle heap before load. Check the memtable share separately (`nodetool tablestats` memtable data size) so heap growth is attributed to the queue and not to memtables: use the class histogram and the pending count. Run C separates pool size from the bound.

**B4. Risks and cleanup.** Unit tier: up to a 2 GB heap, heap dumps on OOM go to `/local/scratch/dumps` (delete). Cluster tier: data and commitlog up to several GB on local disk; the workload writes about 2M x 32 KiB = 64 GB if run to completion, so cap with `n=` or duration and keep local disk at least 100 GB free or lower `n`; do not use shared storage. Always kill the node and stress client, check `pgrep`, delete `/local/scratch/*` run directories. The shared source clone is never written to.

### Stage-4 amendments (step 0 audit and instrument checks, 2026-10-22)

Made by the stage-4 audit before any run-1 reading, for reasons derived from the source and from instrument checks (a node that did not start, a client limit), not from a reading of either tier. B1 and the claim are unchanged. Where this block and B2f/B2g/B3f/B3g differ, this block governs; it only defines terms, adds rows for outcomes the filed table left without one, and fixes runbook steps. The sibling `SEPExecutor` files' results were read for lessons only. Results: `stage4-runtime-verification/results/maxTasksQueued-takeTaskPermit-taskPermits--autonomous.md`.

**Unit tier**
- **R1 (B2a run as a plain JVM).** `ant testsome` forks the test JVM with `maxmemory="1024m"` after `test.jvm.args` (`build.xml:1153`), so B2a's `-Xmx2g` would not apply and N = 10^6, P = 1024 (about 1.1 GB retained) would not fit. The probe (`SEPQueueBoundProbe`, package `org.apache.cassandra.concurrent`, harness folder) is a `main` run with `java -Xms2g -Xmx2g -XX:+UseG1GC` on the clone's `build/classes/main` and `build/lib/jars/*` plus the `--add-exports` lines of `conf/jvm11-server.options`.
- **R2 (B2e series).** Per (kind, P, repetition) a fresh executor: the blocker, then N is raised cumulatively to 10^4, 10^5, 10^6 (and 4 x 10^6 when P = 0, which fits: about 60 B per task). The control runs the same series (P = 0 also to 4 x 10^6). Two repetitions of everything (rep1, rep2), each in its own JVM. P = 0 means `new byte[0]` per task.
- **R3 (definitions for B2f/B2g).** "Pending == N": `getPendingTaskCount()` equals N (the blocker is running, not pending). "No blocking": mean wall time per `execute` call <= 100 us over a batch and the slowest single call <= 1 s. "Slope" = (heap delta after 3 x GC at N2 - at N1) / (N2 - N1) between consecutive points; the predicted per-task cost "P + roughly 100-200 B" is read as slope in [P + 32, P + 250] B for 10^4 -> 10^5 and 10^5 -> 10^6, the two slopes within 25 % of each other; the P = 1024 minus P = 0 difference at 10^6 is 1024 +/- 150 B. "Heap flat" = delta at 10^6 below 0.5 x N x (P + 32). The two repetitions' slopes agree within 10 %. The control's "plateau": accepted = 10,000 exactly, rejected = N - 10,000 from the first rejection, first rejection after 10,000 accepted, and its heap delta at the last N at most 1.2 x its delta at N = 10^4 (or within 2 MiB).
- **R4 (rows added to B2g).** (U7) pending == N at every point but a slope/difference/repeat sub-prediction missed: Claim confirmed for the count and for linear heap growth; the missed sub-prediction is recorded. (U8) OutOfMemoryError before N = 10^6 with pending == N at the last point read: Not confirmed (the workload exceeded the heap before the largest point); the points read still show no bound. (U9) any other pattern: Not confirmed (no matching row).

**Cluster tier**
- **R5 (native-transport threads).** `native_transport_max_threads: 4096` in every run. At the default 128, at most 128 CQL requests can block in `StorageProxy.mutate` (`StorageProxy.java:906`), each on one `MutationStage` task, so MutationStage Pending could never exceed about 128; the bytes of the other requests would wait in the `Native-Transport-Requests` queue (`Dispatcher.java:58`, `Config.java:283`), which is another `SEPExecutor` and not the one B3f names.
- **R6 (receive queue, timeouts).** `native_transport_receive_queue_capacity: 0B` in every run (a connection takes its first bytes from its own 1 MiB queue, `Config.java:302`, so 16 connections would absorb 16 MiB before the reserve is used, and the 16 MiB limit of run B could not bind). `write_request_timeout: 120000ms` and `native_transport_timeout: 120s` in every run, so that queued mutations are not expired and dropped (`Dispatcher.java:238-245`) during the window; B3f's pending/heap relation presumes a queue that holds its entries.
- **R7 (workload).** `commitlog_sync: batch` for every run (B3c names it as the way to keep the workers busy; D1 below: 5.0.9 has no window key). Stress: `write duration=360s cl=ONE no-warmup -col 'n=FIXED(1)' 'size=FIXED(32768)' -pop 'dist=UNIFORM(1..4000)' -rate threads=T -errors ignore retries=0 -mode native cql3 connectionsPerHost=16`; `no-warmup` because the default warm-up is 50,000 unthrottled writes (`StressAction.java:105-110`), the population of 4,000 partitions (131 MB) because B4's 64 GB would not fit the 53 GB disk, and `connectionsPerHost=16` (D2). Duration 360 s instead of 12 min: the closed-loop backlog forms as soon as the clients' pipes fill, and the statistics window (below) has 300 s. The keyspace is `keyspace1` (RF 1), created before a 100-row stress write that makes the table.
- **R8 (arms).** A: in-flight limits (global and per-IP) 512 MiB, T = 2000. B (positive control): 16 MiB, T = 2000, everything else as A. **A2 (added):** as A with T = 256 (8 MiB offered, below both limits), so that "pending rises with offered load" has a second load level. Optional run C of B3e is not run. One fresh node lifetime per arm on wiped directories; the node on 127.0.0.1, JMX 7199, 1 GiB heap (`-Xms1g -Xmx1g` in the node copy of `jvm11-server.options`), `concurrent_writes: 2`.
- **R9 (statistics for B3f/B3g).** Window: from 60 s after the stress starts to its end. Pn = the median, Pmax = the maximum of MutationStage Pending over the 5-s `tpstats` samples in the window. Hn = median of (heap used after `jcmd GC.run` minus `Memtable data size` of `keyspace1.standard1`) over the 15-s samples in the window, minus the same median over the baseline samples before the stress (B3h's memtable separation). `RequestsSize` max over the 1-s JMX samples. Plateau-flat: max/min of the window's Pending <= 1.1. **Sub-predictions** (misses are recorded, they do not change the matched row): Pn(A) >= 1000 and Pmax(A) <= 2200; Pn(A2) in [128, 282]; Pmax(B) <= 563 (1.1 x 16 MiB / 32 KiB); RequestsSize max of B in [14.4, 16.5] MiB; RequestsSize max of A < 512 MiB; heap per queued mutation (Hn / Pn) >= 32 KiB, the payload.
- **R10 (rows of B3g, replacing its table; first match from the top).**
  - (C1) **Confirmed:** MaxTasksQueued = 2147483647 at every JMX sample of every run; Active <= 2; Pn(A2) >= 10; Pn(A) >= 2 x Pn(A2); Hn(A) - Hn(A2) >= 0.5 x (Pn(A) - Pn(A2)) x 32 KiB; Pn(B) <= 0.5 x Pn(A); Hn(A) - Hn(B) >= 0.5 x (Pn(A) - Pn(B)) x 32 KiB; RequestsSize max of B >= 14.4 MiB (the cap was reached). Positive control moved; unclipped by any executor value.
  - (C2) **Refuted:** MaxTasksQueued reads anything but 2147483647, or Pending is clipped at an executor-level value: Pn(A) within +/-10 % of Pn(A2) although the offered load differs 8-fold, while RequestsSize max of both is below 16 MiB.
  - (C3) **Not confirmed (limit not reached):** Pn(A) < 10 or Pn(A2) < 10.
  - (C4) **Not confirmed (control did not move):** Pn(B) > 0.5 x Pn(A), or RequestsSize max of B < 14.4 MiB.
  - (C5) **Not confirmed (heap):** Pending rows as C1 but the Hn conditions fail (the heap does not follow Pending, or the memtable separation fails).
  - (C6) OutOfMemoryError in A or A2: consistent with an unbounded queue; Not confirmed for the readings table unless C1 holds on the samples before it; the cause is noted (heap dump).
  - (C7) any other pattern: Not confirmed (no matching row).

**Runbook defects found by the instrument checks (before run 1)**
- **D1.** B3c's `commitlog_sync_batch_window_in_ms: 2` is not a valid key in 5.0.9 (the node stopped at start: "Invalid yaml. Please remove properties [commitlog_sync_batch_window_in_ms]"). Fix: `commitlog_sync: batch` alone, `commitlog_sync_period` removed. B3f/B3g unchanged.
- **D2.** `cassandra-stress` allows 128 pending requests on each of 8 connections (`SettingsMode.java:138-139`), so T = 2000 threads kept only 1,024 requests in flight (the instrument check read MutationStage Pending 1,022 and the rest of the threads failed with `BusyPoolException`). Fix: `connectionsPerHost=16` (2,048). B3f/B3g unchanged.

## C. Sources read

- `/proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/playbook-autonomous.md`
- `/proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/_TEMPLATE-autonomous.md`
- `src/java/org/apache/cassandra/concurrent/SEPExecutor.java` (whole file)
- `src/java/org/apache/cassandra/concurrent/SharedExecutorPool.java` (grep lines)
- `src/java/org/apache/cassandra/concurrent/Stage.java` (grep lines)
- `src/java/org/apache/cassandra/config/Config.java` (grep lines)
- `src/java/org/apache/cassandra/config/DatabaseDescriptor.java` (grep lines)
- `src/java/org/apache/cassandra/metrics/ThreadPoolMetrics.java` (grep line)
- `src/java/org/apache/cassandra/transport/Dispatcher.java`, `CQLMessageHandler.java` (grep lines only)

## D. Stage-4 feedback

2026-10-22, stage-4 run 1 on `pc13`, no run 2; results `stage4-runtime-verification/results/maxTasksQueued-takeTaskPermit-taskPermits--autonomous.md`, harness `stage4-runtime-verification/harness/maxTasksQueued-takeTaskPermit-taskPermits--autonomous/` (not committed; this file is untracked). Amendments and runbook fixes are the dated block "Stage-4 amendments" in section B (frozen sha256 `eb691cfc516a320bb25fd89e478fa2f11242dc0216e911f08ac5767b8dd654f8`, as filed `58849d2c…`).

- **Unit tier: Confirmed — does not cap** (B2g row 1 and the control row). An `SEPExecutor` with its only work permit held took 10^4, 10^5, 10^6 and (P = 0) 4 x 10^6 queued tasks: pending == N, `getMaxTasksQueued()` = 2147483647, no rejection; heap 80.0 B per task at P = 0 and 1104.0 B at P = 1024 (1052.9 MiB at N = 10^6); the `ArrayBlockingQueue(10000)` control accepted exactly 10,000 and held 10.26 MiB. One `execute` call took 1.70 / 1.76 s at 4 x 10^6 (no GC log; no row names it).
- **Cluster tier: Not confirmed (row C4, positive control did not move) — undetermined.** MutationStage Pending followed the offered load: 1996 at 2000 threads, 252 at 256, Active <= 2, `MaxTasksQueued` constant; heap +267 MiB for +1,744 queued mutations (157 KiB each; 212 KiB per queued mutation in total). But the 16 MiB in-flight limit of run B reached its limit (RequestsSize 15.97 MiB) and left Pending (1996), `Mutation` count (1998) and heap (417.5 vs 413.3 MiB) unchanged. **B1's sentence "what limits queued memory there is the upstream in-flight byte limit" did not hold on this workload**: the bytes the limit counts are not held while the mutation waits in the executor queue (inferred, not tested).
- **Filed-design gaps fixed or recorded:** (R5) with the default 128 native-transport threads MutationStage Pending cannot exceed about 128, so B3c's "2000 threads" needs `native_transport_max_threads` raised; (R6) the 1 MiB per-connection receive queue absorbs the first bytes (`native_transport_receive_queue_capacity: 0B`) and mutations expire at the write timeout unless raised; (D1) `commitlog_sync_batch_window_in_ms` does not exist in 5.0.9; (D2) `cassandra-stress` caps at 1,024 requests in flight by default (`connectionsPerHost=16` for 2,048); (R1) `ant testsome` forces a 1 GiB heap; (R7) B4's 64 GB does not fit the disk, a 4,000-partition population is overwritten instead. Not separated: per-request memory from queued-task memory (the `concurrent_compactors` pattern), and the six other `SEPExecutor`s.
- The estimate (negative) is unchanged; no section A or B text other than the amendment block was changed.
